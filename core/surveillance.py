# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Surveillance : changements dans Odoo, contrôles techniques, centre d'alertes.

  comparer_instantanes(ancien, nouveau)  -> constats « changement »
  controles_techniques(...)               -> constats « technique »
  CentreAlertes                           -> mémoire des alertes (fichier JSON)

Le centre distingue deux sortes d'alertes :
  - ÉTATS (anomalies comptables, techniques) : synchronisées à chaque passage ;
    une alerte qui ne se reproduit plus passe « résolue » toute seule.
  - ÉVÉNEMENTS (changements dans Odoo) : ajoutés à chaque passage, jamais résolus,
    seulement « vus ».
Chaque alerte porte l'explication de Marceau (pourquoi, que faire).
"""
import json
import os
import shutil
import threading
from datetime import date, datetime, timedelta

from .analyser import Rapport
from .marceau import Marceau

EXEMPLES_MAX = 20
EVENEMENTS_MAX = 500
_marceau = Marceau()


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Changements dans Odoo
# ---------------------------------------------------------------------------

def comparer_instantanes(ancien, nouveau):
    """Compare deux photos (source.instantane()). Retourne un Rapport."""
    r = Rapport()
    if not ancien:
        r.constat("INFO", "INSTANTANE_INITIAL", "Surveillance des changements démarrée",
                  ["%d écritures, %d comptes photographiés"
                   % (len(nouveau["ecritures"]), len(nouveau["comptes"]))])
        return r
    a, n = ancien["ecritures"], nouveau["ecritures"]
    nouvelles = [i for i in n if i not in a]
    supprimees = [i for i in a if i not in n]
    brouillon, validees, modifiees = [], [], []
    for i in n.keys() & a.keys():
        (etat_a, date_a, _), (etat_n, date_n, nom) = a[i], n[i]
        if etat_a == "posted" and etat_n == "draft":
            brouillon.append(i)
        elif etat_a == "draft" and etat_n == "posted":
            validees.append(i)
        elif date_a != date_n:
            modifiees.append(i)

    def noms(ids, source):
        return ["%s (id %s)" % (source[i][2] if source[i][2] not in ("", "/")
                                else "brouillon", i) for i in sorted(ids, key=int)]

    r.constat("ALERTE", "ECRITURES_SUPPRIMEES", "Écritures supprimées",
              noms([i for i in supprimees if a[i][0] == "posted"], a))
    r.constat("INFO", "BROUILLONS_SUPPRIMES", "Brouillons supprimés",
              noms([i for i in supprimees if a[i][0] != "posted"], a))
    r.constat("ALERTE", "ECRITURES_REMISES_BROUILLON",
              "Écritures validées remises en brouillon", noms(brouillon, n))
    r.constat("INFO", "ECRITURES_NOUVELLES", "Nouvelles écritures", noms(nouvelles, n))
    r.constat("INFO", "ECRITURES_VALIDEES", "Écritures validées", noms(validees, n))
    r.constat("INFO", "ECRITURES_MODIFIEES", "Écritures modifiées", noms(modifiees, n))
    ca, cn = ancien["comptes"], nouveau["comptes"]
    r.constat("INFO", "COMPTES_CREES", "Comptes créés",
              sorted(cn[i] for i in cn if i not in ca))
    r.constat("ALERTE", "COMPTES_SUPPRIMES", "Comptes supprimés",
              sorted(ca[i] for i in ca if i not in cn))
    noms_verrous = {"periode": "période (hors conseillers)", "exercice": "exercice",
                    "tva": "TVA"}
    recul, avance = [], []
    for k, nom in noms_verrous.items():
        va, vn = ancien["verrous"].get(k), nouveau["verrous"].get(k)
        if va == vn:
            continue
        texte = "Verrou %s : %s → %s" % (nom, _date_fr(va), _date_fr(vn))
        if va and (not vn or vn < va):
            recul.append(texte)
        else:
            avance.append(texte)
    r.constat("ALERTE", "PERIODE_DEVERROUILLEE", "Période déverrouillée", recul)
    r.constat("INFO", "VERROU_AVANCE", "Période verrouillée", avance)
    return r


def _date_fr(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "aucun"


# ---------------------------------------------------------------------------
# Contrôles techniques
# ---------------------------------------------------------------------------

def controles_techniques(pg_ok, pg_erreur, odoo_ok, odoo_erreur, dossier,
                         taches_echec, echecs_connexion):
    """Constats techniques à partir de mesures déjà prises (fonction pure, testable).

    taches_echec : [(date ISO, action, base, erreur)] des dernières 24 h
    echecs_connexion : [(date ISO, ip)] des dernières 24 h
    """
    r = Rapport()
    if not pg_ok:
        r.constat("BLOQUANT", "PG_INJOIGNABLE", "Base PostgreSQL injoignable", [pg_erreur])
    if not odoo_ok:
        r.constat("ALERTE", "ODOO_INJOIGNABLE", "Odoo injoignable", [odoo_erreur])
    try:
        u = shutil.disk_usage(dossier)
        libre = u.free / u.total
        r.info("disque_libre", "%.0f %%" % (libre * 100))
        if libre < 0.10:
            r.constat("BLOQUANT" if libre < 0.05 else "ALERTE", "DISQUE_PLEIN",
                      "Disque presque plein",
                      ["%.1f %% libre (%d Go sur %d Go)" % (
                          libre * 100, u.free // 2 ** 30, u.total // 2 ** 30)])
    except OSError as exc:
        r.constat("ALERTE", "DISQUE_PLEIN", "Espace disque illisible", [str(exc)])
    r.constat("ALERTE", "TACHE_ECHEC", "Tâches en échec (24 h)",
              ["%s — %s sur %s : %s" % t for t in taches_echec])
    par_ip = {}
    for _, ip in echecs_connexion:
        par_ip[ip] = par_ip.get(ip, 0) + 1
    if len(echecs_connexion) >= 3:
        r.constat("ALERTE", "CONNEXIONS_REFUSEES", "Tentatives de connexion refusées (24 h)",
                  ["%s : %d essai(s)" % kv for kv in
                   sorted(par_ip.items(), key=lambda kv: -kv[1])])
    return r


# ---------------------------------------------------------------------------
# Centre d'alertes
# ---------------------------------------------------------------------------

CATEGORIES = {"analyse": "comptable", "balance": "comptable", "technique": "technique",
              "changement": "changement", "securite": "technique"}

# Résultats de securite/concorde_securite.py (lancé en root par systemd, ADR-0007).
DOSSIER_SECURITE = os.environ.get("CONCORDE_SECURITE_DOSSIER", "/var/lib/concorde-securite")
AGE_MAX_S = {"controle": 3600, "antivirus": 36 * 3600}


def constats_securite(dossier=None, maintenant=None):
    """Constats du dernier contrôle et du dernier antivirus, plus une alerte si l'un d'eux
    n'a pas tourné depuis trop longtemps (la surveillance elle-même s'est arrêtée)."""
    dossier = dossier or DOSSIER_SECURITE
    maintenant = maintenant or datetime.now()
    constats, infos = [], {}
    for nom, age_max in AGE_MAX_S.items():
        chemin = os.path.join(dossier, nom + ".json")
        try:
            with open(chemin, encoding="utf-8") as f:
                d = json.load(f)
            date_r = datetime.fromisoformat(d["date"])
        except (OSError, ValueError, KeyError):
            constats.append({"niveau": "ALERTE", "code": "SEC_SURVEILLANCE_ARRETEE",
                             "message": "Surveillance de sécurité sans résultat (%s)" % nom,
                             "nombre": 1, "exemples": ["%s absent ou illisible" % chemin]})
            continue
        infos[nom] = {"date": d["date"], "statut": d.get("statut"),
                      "synthese": d.get("synthese")}
        age = (maintenant - date_r).total_seconds()
        if age > age_max:
            constats.append({"niveau": "ALERTE", "code": "SEC_SURVEILLANCE_ARRETEE",
                             "message": "Surveillance de sécurité arrêtée (%s)" % nom,
                             "nombre": 1, "exemples": ["dernier passage : %s (il y a %d h)" % (
                                 d["date"], age // 3600)]})
        constats.extend(c for c in d.get("constats", []))
    return constats, infos


class CentreAlertes:
    """Mémoire des alertes, dans un fichier JSON (écriture atomique)."""

    def __init__(self, chemin):
        self.chemin = chemin
        self._verrou = threading.Lock()
        self._alertes = {}
        if os.path.isfile(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    self._alertes = {a["id"]: a for a in json.load(f)}
            except (OSError, ValueError):
                self._alertes = {}

    def _sauver(self):
        tmp = self.chemin + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self._alertes.values()), f, ensure_ascii=False, default=str)
        os.replace(tmp, self.chemin)

    @staticmethod
    def _nouvelle(ident, source, base, c):
        maintenant = _maintenant()
        return {"id": ident, "source": source, "categorie": CATEGORIES[source],
                "base": base, "code": c["code"], "niveau": c["niveau"],
                "message": c["message"], "nombre": c["nombre"],
                "exemples": c["exemples"][:EXEMPLES_MAX],
                "explication": _marceau.expliquer_alerte(c["code"], c["message"]),
                "premiere_fois": maintenant, "derniere_fois": maintenant,
                "statut": "active", "vue": False, "resolue_le": None}

    def synchroniser(self, source, base, constats, niveaux=("BLOQUANT", "ALERTE")):
        """Alertes d'ÉTAT. Retourne (nouvelles, resolues) : listes de messages."""
        nouvelles, resolues = [], []
        presentes = set()
        with self._verrou:
            for c in constats:
                if c["niveau"] not in niveaux:
                    continue
                ident = "%s|%s|%s" % (source, base, c["code"])
                presentes.add(ident)
                a = self._alertes.get(ident)
                if a is None or a["statut"] == "resolue":
                    self._alertes[ident] = self._nouvelle(ident, source, base, c)
                    nouvelles.append(c["message"])
                else:
                    if c["nombre"] > a["nombre"]:
                        a["vue"] = False         # ça s'aggrave : on la remontre
                    a.update(niveau=c["niveau"], message=c["message"], nombre=c["nombre"],
                             exemples=c["exemples"][:EXEMPLES_MAX],
                             derniere_fois=_maintenant())
            for ident, a in self._alertes.items():
                if (a["source"] == source and a["base"] == base and a["statut"] == "active"
                        and ident not in presentes):
                    a.update(statut="resolue", resolue_le=_maintenant())
                    resolues.append(a["message"])
            self._sauver()
        return nouvelles, resolues

    def evenements(self, base, constats):
        """Alertes d'ÉVÉNEMENT (changements) : toujours ajoutées."""
        horodatage = _maintenant()
        with self._verrou:
            for c in constats:
                ident = "changement|%s|%s|%s|%s" % (base, c["code"], c["niveau"], horodatage)
                a = self._nouvelle(ident, "changement", base, c)
                a["statut"] = "evenement"
                self._alertes[ident] = a
            # On ne garde que les EVENEMENTS_MAX événements les plus récents.
            evs = sorted((a for a in self._alertes.values() if a["statut"] == "evenement"),
                         key=lambda a: a["premiere_fois"])
            for a in evs[:-EVENEMENTS_MAX]:
                del self._alertes[a["id"]]
            self._sauver()

    def lister(self, statut=None):
        with self._verrou:
            alertes = [dict(a) for a in self._alertes.values()]
        if statut:
            alertes = [a for a in alertes if a["statut"] == statut]
        ordre = {"BLOQUANT": 0, "ALERTE": 1, "INFO": 2}
        # Plus récentes d'abord, puis (tri stable) actives, non vues, les plus graves.
        alertes.sort(key=lambda a: a["derniere_fois"] or "", reverse=True)
        alertes.sort(key=lambda a: (a["statut"] != "active", a["vue"],
                                    ordre.get(a["niveau"], 3)))
        return alertes

    def resume(self):
        """Pour la cloche : alertes actives ou événements importants non vus."""
        with self._verrou:
            a_voir = [a for a in self._alertes.values() if not a["vue"]
                      and a["statut"] in ("active", "evenement")
                      and a["niveau"] in ("BLOQUANT", "ALERTE")]
            actives = [a for a in self._alertes.values() if a["statut"] == "active"]
        return {"non_vues": len(a_voir),
                "bloquantes": sum(1 for a in actives if a["niveau"] == "BLOQUANT"),
                "actives": len(actives)}

    def marquer_vue(self, ident=None):
        with self._verrou:
            for a in self._alertes.values():
                if ident is None or a["id"] == ident:
                    a["vue"] = True
            self._sauver()

    def tout_resoudre_absents(self, sources_bases):
        """Résout les alertes d'état dont la base a disparu de l'annuaire."""
        with self._verrou:
            for a in self._alertes.values():
                if (a["statut"] == "active" and a["source"] in ("analyse", "balance")
                        and a["base"] not in sources_bases):
                    a.update(statut="resolue", resolue_le=_maintenant())
            self._sauver()


def depuis_24h(iso):
    try:
        return datetime.fromisoformat(iso) > datetime.now() - timedelta(hours=24)
    except (TypeError, ValueError):
        return False
