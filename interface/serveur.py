# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Interface web de CONCORDE — bibliothèque standard Python uniquement (ADR-0002, 0003).

Écoute sur 127.0.0.1 seulement : Caddy fournit le HTTPS devant.
Un seul utilisateur, mot de passe haché (interface/auth.py).

Configuration (variables d'environnement) :
  CONCORDE_UI_MDP           empreinte scrypt du mot de passe (scripts/concorde_interface_mdp.py)
  CONCORDE_UI_PORT          port d'écoute (défaut 18090)
  CONCORDE_UI_DONNEES       dossier des résultats (défaut /var/lib/concorde-interface)
  CONCORDE_UI_SURVEILLANCE  minutes entre deux passages de surveillance (défaut 15, 0 = jamais)
  CONCORDE_ODOO_URL         Odoo à surveiller (défaut http://127.0.0.1:8017)
  PGHOST PGPORT PGUSER PGPASSWORD   accès PostgreSQL des bases Odoo 17 ;
                            à défaut, POSTGRES_USER / POSTGRES_PASSWORD (deploy/.env).

API (JSON ; toute requête qui modifie exige l'en-tête X-Concorde: 1) :
  POST /api/connexion  /api/deconnexion          GET /api/etat
  GET  /api/bases                                POST /api/distants  DELETE /api/distants/<id>
  POST /api/taches     GET /api/taches           GET /api/taches/<id>?depuis=<n>
  GET  /api/taches/<id>/fichiers/<n>  /zip  /rapport.json  /constats/<code>.csv
  GET  /api/comptes?base=…            GET /api/comptes/<code>/grand-livre?base=…
  GET  /api/ecritures/<id>?base=…
  GET  /api/alertes   GET /api/alertes/resume    POST /api/alertes/vue
  POST /api/surveillance                         GET /api/journal?depuis=<n>
  GET  /api/sauvegardes    GET /api/cles    POST /api/cles/revoquer
  GET  /api/comparer/choix?base_a=…&base_b=…   comptes et analytiques des deux bases
  GET  /api/rapport?jour=…   POST /api/rapport   GET /api/rapport/export?jour=…  (rapport du jour)
  POST /api/distants/<id>/cle   DELETE /api/distants/<id>/cle
  POST /api/bases/nom  {base_id, libelle}   nom parlant d'une base (vide = retiré)
  (suppression / réinitialisation d'une base LOCALE : POST /api/taches avec
   action = supprimer_base | reinitialiser_base et confirmation = nom retapé — ADR-0005)
"""

import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import traceback
import uuid
import zipfile
from datetime import date, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


from core import bases_locales
from core import rapport_jour
from core.comparaison import comparer_bases
from core.comptes import alertes_balance, grand_livre
from core.guardian import Guardian
from core.journal import Journal, duree_texte, nombre_texte
from core.marceau import Marceau
from core.odoo_source import (
    ETATS,
    ErreurSource,
    SourceSqlOdoo17,
    SourceXmlRpcOdoo17,
)
from core.passerelle import FORMATS, OBJETS, analyser_source, telecharger
from core.surveillance import (
    DOSSIER_SECURITE,
    CentreAlertes,
    comparer_instantanes,
    constats_securite,
    controles_techniques,
    depuis_24h,
)
from interface.auth import Sessions, verifier

STATIQUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
COOKIE = "concorde_session"
CORPS_MAX = 64 * 1024
TACHES_SIMULTANEES = 2
LIMITE_GRAND_LIVRE = 500
_marceau = Marceau()


def _bases_ecriture_configurees():
    """Bases locales dont CONCORDE a les identifiants d'écriture (API Odoo).

    Aujourd'hui : la base de test (CONCORDE_TEST_BASE / CONCORDE_TEST_MDP dans
    /etc/concorde/interface.env). Les mots de passe ne sortent jamais d'ici.
    """
    base = os.environ.get("CONCORDE_TEST_BASE")
    return {base} if base and os.environ.get("CONCORDE_TEST_MDP") else set()


def _json_defaut(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def _date(texte):
    return date.fromisoformat(texte) if texte else None


# ---------------------------------------------------------------------------
# Bases Odoo : bases SQL du serveur + Odoo distants (XML-RPC, clé en mémoire)
# ---------------------------------------------------------------------------


class Bases:
    """Annuaire des bases. Les clés API des Odoo distants restent en mémoire."""

    DUREE_CACHE = 60

    def __init__(self, fabrique_sql=None):
        self._fabrique_sql = fabrique_sql or SourceSqlOdoo17
        self._distants = {}
        self._cache = (0, [])
        self._verrou = threading.Lock()
        self.pg_ok, self.pg_erreur = True, ""
        self._libelles = {}  # {id de base : nom parlant} — bases du serveur
        self._fichier_libelles = None

    # --- noms parlants -------------------------------------------------------------------
    LIBELLE_MAX = 60

    def charger_libelles(self, chemin):
        """Noms parlants des bases du serveur, gardés d'un redémarrage à l'autre."""
        self._fichier_libelles = chemin
        if os.path.isfile(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    self._libelles = {
                        k: str(v) for k, v in json.load(f).items()
                    }
            except (OSError, ValueError):
                self._libelles = {}

    @classmethod
    def nettoyer_libelle(cls, libelle):
        libelle = " ".join(
            str(libelle or "").split()
        )  # espaces et retours ligne
        if len(libelle) > cls.LIBELLE_MAX:
            raise ValueError(
                "Nom trop long (%d caractères au plus)." % cls.LIBELLE_MAX
            )
        return libelle

    def renommer(self, ident, libelle):
        """Donne (ou retire, si vide) un nom parlant à une base. Retourne le nom gardé."""
        libelle = self.nettoyer_libelle(libelle)
        connues = {
            b["id"] for b in self.lister()
        }  # hors verrou (lister le prend)
        if ident not in connues:
            raise ValueError("Base inconnue : %s" % ident)
        with self._verrou:
            if ident in self._distants:
                self._distants[ident]["libelle"] = libelle
                return libelle
            if libelle:
                self._libelles[ident] = libelle
            else:
                self._libelles.pop(ident, None)
            if self._fichier_libelles:
                tmp = self._fichier_libelles + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._libelles, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self._fichier_libelles)
        return libelle

    def _lister_sql(self):
        try:
            import psycopg2
        except ImportError:
            self.pg_ok, self.pg_erreur = False, "psycopg2 n'est pas installé"
            return []
        try:
            cx = psycopg2.connect(dbname="postgres", connect_timeout=5)
        except Exception as exc:
            self.pg_ok = False
            self.pg_erreur = "%s (PGHOST=%s)" % (
                str(exc).strip().splitlines()[0],
                os.environ.get("PGHOST", "?"),
            )
            return []
        self.pg_ok, self.pg_erreur = True, ""
        try:
            with cx.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_database WHERE NOT datistemplate "
                    "AND datname <> 'postgres' ORDER BY datname"
                )
                noms = [r[0] for r in cur.fetchall()]
        finally:
            cx.close()
        bases = []
        for nom in noms:
            try:
                s = self._fabrique_sql(nom)
            except Exception:
                continue  # pas une base Odoo 17 (ou inaccessible)
            try:
                soc = s.societe_info()
                bases.append(
                    {
                        "id": "sql:" + nom,
                        "nom": nom,
                        "source": "sql",
                        "version": s.version_serveur,
                        "societe": soc["nom"],
                        "devise": soc["devise"],
                        "siren": soc["siren"],
                    }
                )
            except Exception:
                pass
            finally:
                s.fermer()
        return bases

    def _modeles(self):
        try:
            return bases_locales.lister_modeles()
        except Exception:
            return {}

    def lister(self, rafraichir=False):
        with self._verrou:
            t, sql = self._cache
            if rafraichir or time.monotonic() - t > self.DUREE_CACHE:
                sql = self._lister_sql()
                modeles = self._modeles() if sql else {}
                prot = bases_locales.protegees()
                ecriture = _bases_ecriture_configurees()
                for b in sql:
                    b["modele"] = modeles.get(b["nom"])
                    b["protegee"] = b["nom"] in prot
                    # Lecture : SQL en lecture seule. Écriture : toujours par l'API d'Odoo
                    # (ADR-0001), possible seulement si CONCORDE a les identifiants.
                    b["lecture"] = "SQL direct (lecture seule)"
                    b["ecriture"] = (
                        "API Odoo — identifiants configurés"
                        if b["nom"] in ecriture
                        else "API Odoo — à configurer"
                    )
                    b["ecriture_ok"] = b["nom"] in ecriture
                self._cache = (time.monotonic(), sql)
            distants = [
                dict(
                    {k: v for k, v in d.items() if k != "cle"},
                    cle_presente=bool(d.get("cle")),
                    lecture="API Odoo (%s)" % d["url"],
                    ecriture="API Odoo — même clé (étapes 7 et 8 de la migration)",
                    ecriture_ok=bool(d.get("cle")),
                )
                for d in self._distants.values()
            ]
            sql = [
                dict(b, libelle=self._libelles.get(b["id"], "")) for b in sql
            ]
        return sql + distants

    def ajouter_distant(self, url, base, utilisateur, cle, libelle=""):
        if not re.match(r"^https?://", url or ""):
            raise ErreurSource("URL invalide (http:// ou https://).")
        libelle = self.nettoyer_libelle(libelle)
        s = SourceXmlRpcOdoo17(url, base, utilisateur, cle, timeout=30)
        soc = s.societe_info()
        ident = "xmlrpc:" + uuid.uuid4().hex[:8]
        with self._verrou:
            self._distants[ident] = {
                "id": ident,
                "nom": base,
                "source": "xmlrpc",
                "url": url.rstrip("/"),
                "utilisateur": utilisateur,
                "version": s.version_serveur,
                "societe": soc["nom"],
                "devise": soc["devise"],
                "siren": soc["siren"],
                "cle": cle,
                "libelle": libelle or "%s (%s)" % (soc["nom"], base),
            }
        return ident

    def supprimer_cle(self, ident):
        """Efface la clé API gardée par CONCORDE ; la base reste listée, déconnectée."""
        with self._verrou:
            d = self._distants.get(ident)
            if not d:
                return False
            d["cle"] = None
            return True

    def saisir_cle(self, ident, cle):
        with self._verrou:
            d = self._distants.get(ident)
        if not d:
            raise ErreurSource("Base inconnue : %s" % ident)
        SourceXmlRpcOdoo17(
            d["url"], d["nom"], d["utilisateur"], cle, timeout=30
        )  # test
        with self._verrou:
            d["cle"] = cle

    def retirer_distant(self, ident):
        with self._verrou:
            return self._distants.pop(ident, None) is not None

    def ouvrir(self, ident, journal=None):
        if ident.startswith("sql:"):
            return self._fabrique_sql(ident[4:], journal=journal)
        with self._verrou:
            d = self._distants.get(ident)
        if not d:
            raise ErreurSource("Base inconnue : %s" % ident)
        if not d.get("cle"):
            raise ErreurSource(
                "Clé API supprimée pour « %s » : ressaisissez-la dans l'écran "
                "Bases." % d["nom"]
            )
        return SourceXmlRpcOdoo17(
            d["url"], d["nom"], d["utilisateur"], d["cle"], journal=journal
        )

    def nom(self, ident):
        b = next((b for b in self.lister() if b["id"] == ident), None)
        if not b:
            return ident
        return (
            "%s (%s)" % (b["libelle"], b["nom"])
            if b.get("libelle")
            else b["nom"]
        )


# ---------------------------------------------------------------------------
# Tâches (analyse, téléchargement) : exécutées en arrière-plan, racontées
# ---------------------------------------------------------------------------


class Taches:
    def __init__(self, dossier, bases, centre=None):
        self.dossier = dossier
        self.bases = bases
        self.centre = centre
        self._taches = {}
        self._journaux = {}
        self._verrou = threading.Lock()
        self._places = threading.Semaphore(TACHES_SIMULTANEES)
        os.makedirs(dossier, exist_ok=True)
        self._recharger()

    def _meta(self, ident):
        return os.path.join(self.dossier, ident, "tache.json")

    def _recharger(self):
        """Historique : relit les tâches des sessions précédentes."""
        for nom in sorted(os.listdir(self.dossier)):
            chemin = self._meta(nom)
            if os.path.isfile(chemin):
                try:
                    with open(chemin, encoding="utf-8") as f:
                        t = json.load(f)
                except (OSError, ValueError):
                    continue
                if t.get("statut") in ("en_attente", "en_cours"):
                    t["statut"] = "interrompue"
                    t["erreur"] = "Service redémarré pendant la tâche."
                self._taches[t["id"]] = t

    def _sauver(self, t):
        os.makedirs(os.path.join(self.dossier, t["id"]), exist_ok=True)
        tmp = self._meta(t["id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, default=_json_defaut)
        os.replace(tmp, self._meta(t["id"]))

    ACTIONS = {
        "analyser": "analyse",
        "telecharger": "téléchargement",
        "supprimer_base": "suppression",
        "reinitialiser_base": "réinitialisation",
        "comparer": "comparaison",
    }

    def creer(self, action, base_id, params):
        if action not in self.ACTIONS:
            raise ValueError("Action inconnue : %s" % action)
        if action in ("supprimer_base", "reinitialiser_base") and not str(
            base_id
        ).startswith("sql:"):
            raise ValueError(
                "Seules les bases de ce serveur peuvent être supprimées ou "
                "réinitialisées. Une base client distante ne se supprime jamais "
                "depuis CONCORDE : utilisez « Retirer de CONCORDE »."
            )
        base = next(
            (b for b in self.bases.lister() if b["id"] == base_id), None
        )
        if base is None:
            raise ValueError("Base inconnue : %s" % base_id)
        if action == "comparer" and not any(
            b["id"] == params.get("base_b") for b in self.bases.lister()
        ):
            raise ValueError("Base B inconnue : %s" % params.get("base_b"))
        ident = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(
            3
        )
        t = {
            "id": ident,
            "action": action,
            "base_id": base_id,
            "base": base["nom"],
            "societe": base.get("societe", ""),
            "params": params,
            "statut": "en_attente",
            "cree_le": datetime.now().isoformat(timespec="seconds"),
            "duree_s": None,
            "erreur": None,
            "resultat": None,
            "fichiers": [],
            "journal": [],
        }
        journal = Journal()
        journal.dire(
            "Tâche créée : %s de la base %s"
            % (self.ACTIONS[action], base["nom"]),
            "etape",
        )
        with self._verrou:
            self._taches[ident] = t
            self._journaux[ident] = journal
        self._sauver(t)
        threading.Thread(
            target=self._executer, args=(t, journal), daemon=True
        ).start()
        return ident

    def _executer(self, t, j):
        if not self._places.acquire(blocking=False):
            j.dire(
                "Deux tâches tournent déjà : celle-ci attend son tour", "info"
            )
            self._places.acquire()
        try:
            self._executer_tache(t, j)
        finally:
            self._places.release()

    def _executer_tache(self, t, j):
        t["statut"] = "en_cours"
        self._sauver(t)
        debut = time.monotonic()
        guardian = Guardian()
        guardian.self_check()
        j.dire("Guardian : contrôle d'intégrité de démarrage réussi", "detail")
        source = None
        try:
            p = t["params"]
            if t["action"] in ("supprimer_base", "reinitialiser_base"):
                self._supprimer_base(t, p, j, guardian)
                t["statut"] = "terminee"
                return
            if t["action"] == "comparer":
                self._comparer(t, p, j, guardian)
                t["statut"] = "terminee"
                return
            source = self.bases.ouvrir(t["base_id"], journal=j)
            if t["action"] == "analyser":
                rapport = analyser_source(
                    source,
                    _date(p.get("du")),
                    _date(p.get("au")),
                    bool(p.get("validees")),
                    guardian,
                    journal=j,
                )
                chemin = os.path.join(self.dossier, t["id"], "rapport.json")
                with open(chemin, "w", encoding="utf-8") as f:
                    json.dump(
                        rapport, f, ensure_ascii=False, default=_json_defaut
                    )
                # Résultat allégé (exemples) ; listes complètes dans rapport.json.
                t["resultat"] = json.loads(
                    json.dumps(
                        {k: v for k, v in rapport.items() if k != "constats"},
                        default=_json_defaut,
                    )
                )
                t["resultat"]["constats"] = [
                    dict(
                        {k: v for k, v in c.items() if k != "elements"},
                        explication=_marceau.expliquer_alerte(
                            c["code"], c["message"]
                        ),
                    )
                    for c in rapport["constats"]
                ]
                if (
                    self.centre is not None
                    and not p.get("du")
                    and not p.get("au")
                ):
                    for origine in ("analyse", "balance"):
                        nouvelles, resolues = self.centre.synchroniser(
                            origine,
                            t["base"],
                            [
                                c
                                for c in rapport["constats"]
                                if c.get("origine", "analyse") == origine
                            ],
                        )
                        _raconter_centre(j, nouvelles, resolues)
            else:
                sortie = os.path.join(self.dossier, t["id"], "fichiers")
                produits = telecharger(
                    source,
                    sortie,
                    formats=p.get("formats") or ["xlsx"],
                    objets=p.get("objets") or list(OBJETS),
                    du=_date(p.get("du")),
                    au=_date(p.get("au")),
                    brouillons=bool(p.get("brouillons")),
                    separateur="\t" if p.get("separateur") == "tab" else "|",
                    encodage=p.get("encodage") or "iso-8859-15",
                    guardian=guardian,
                    journal=j,
                )
                fichiers = []
                for prod in produits:
                    for f in prod["fichiers"]:
                        fichiers.append(
                            {
                                "n": len(fichiers),
                                "format": prod["format"],
                                "nom": os.path.relpath(f, sortie),
                                "chemin": f,
                                "taille": os.path.getsize(f),
                            }
                        )
                t["fichiers"] = fichiers
                t["resultat"] = {
                    "produits": [
                        {
                            "format": p_["format"],
                            "resume": p_["resume"],
                            "alertes": p_["alertes"],
                        }
                        for p_ in produits
                    ]
                }
                j.dire(
                    "%d fichier(s) prêt(s) au téléchargement" % len(fichiers),
                    "ok",
                )
            t["statut"] = "terminee"
        except (
            Exception
        ) as exc:  # erreur rendue telle quelle à l'écran (jamais muet)
            t["statut"] = "echec"
            t["erreur"] = "%s : %s" % (type(exc).__name__, exc)
            j.dire("Échec : %s" % t["erreur"], "erreur")
            traceback.print_exc()
        finally:
            if source is not None:
                source.fermer()
            t["duree_s"] = round(time.monotonic() - debut, 1)
            t["empreinte_guardian"] = guardian.empreinte_courante()
            if t["statut"] == "terminee":
                j.dire(
                    "Terminé en %s" % duree_texte(time.monotonic() - debut),
                    "ok",
                )
            t["journal"] = j.tout()
            self._sauver(t)

    def _supprimer_base(self, t, p, j, guardian):
        """Suppression / réinitialisation d'une base LOCALE (core/bases_locales, ADR-0005)."""
        nom = t["base"]
        locales = [
            b["nom"]
            for b in self.bases.lister(rafraichir=True)
            if b["source"] == "sql"
        ]
        with self._verrou:
            en_cours = {
                x["base"]
                for x in self._taches.values()
                if x["id"] != t["id"]
                and x["statut"] in ("en_attente", "en_cours")
            }
        dossier = os.path.join(self.dossier, "sauvegardes")
        modeles = (
            bases_locales.lister_modeles()
        )  # côté serveur : décide « base de test »
        if t["action"] == "reinitialiser_base":
            chemin = bases_locales.reinitialiser(
                nom,
                p.get("confirmation"),
                locales,
                modeles,
                dossier,
                en_cours,
                journal=j,
            )
        else:
            chemin = bases_locales.supprimer(
                nom,
                p.get("confirmation"),
                locales,
                dossier,
                en_cours,
                journal=j,
                modeles=modeles,
            )
        sauvegarde = os.path.basename(chemin) if chemin else None
        guardian.tracer(
            "bases", t["action"], "%s sauvegarde=%s" % (nom, sauvegarde)
        )
        t["resultat"] = {"sauvegarde": sauvegarde, "base": nom}
        self.bases.lister(rafraichir=True)
        if self.centre is not None:
            code = (
                "BASE_SUPPRIMEE"
                if t["action"] == "supprimer_base"
                else "BASE_REINITIALISEE"
            )
            self.centre.evenements(
                nom,
                [
                    {
                        "code": code,
                        "niveau": "INFO",
                        "nombre": 1,
                        "message": (
                            "Base supprimée"
                            if code == "BASE_SUPPRIMEE"
                            else "Base réinitialisée"
                        ),
                        "exemples": [
                            (
                                "Sauvegarde : %s" % sauvegarde
                                if sauvegarde
                                else "Base de test : pas de sauvegarde"
                            )
                        ],
                    }
                ],
            )
            if t["action"] == "supprimer_base":
                self.centre.tout_resoudre_absents(
                    {
                        b["nom"]
                        for b in self.bases.lister()
                        if b["source"] == "sql"
                    }
                )
        if self.surveillance_dossier:
            photo = os.path.join(
                self.surveillance_dossier,
                re.sub(r"[^\w-]", "_", nom) + ".json",
            )
            if os.path.isfile(photo):
                os.remove(photo)  # la prochaine photo repart de zéro

    surveillance_dossier = None

    def _comparer(self, t, p, j, guardian):
        """Vérifier, analyser et comparer deux bases sur une période (lecture seule)."""
        a = self.bases.ouvrir(t["base_id"], journal=j)
        try:
            b = self.bases.ouvrir(p["base_b"], journal=j)
        except Exception:
            a.fermer()
            raise
        try:
            etats = ("posted", "draft") if p.get("brouillons") else ("posted",)
            res = comparer_bases(
                a,
                b,
                _date(p.get("du")),
                _date(p.get("au")),
                etats,
                p.get("date_copie") or None,
                os.path.join(self.dossier, t["id"], "fichiers"),
                j,
                p.get("comptes") or None,
                p.get("analytiques") or None,
            )
        finally:
            a.fermer()
            b.fermer()
        guardian.tracer(
            "comparer",
            res["comparaison"]["statut"],
            res["comparaison"]["empreinte"],
        )
        for c in res["comparaison"]["constats"]:
            c["explication"] = _marceau.expliquer_alerte(
                c["code"], c["message"]
            )
        for cote in ("analyse_A", "analyse_B"):
            for c in res[cote]["constats"]:
                c["explication"] = _marceau.expliquer_alerte(
                    c["code"], c["message"]
                )
        if res.get("fichier"):
            t["fichiers"] = [
                {
                    "n": 0,
                    "format": "xlsx",
                    "nom": os.path.basename(res["fichier"]),
                    "chemin": res["fichier"],
                    "taille": os.path.getsize(res["fichier"]),
                }
            ]
            res["fichier"] = os.path.basename(res["fichier"])
        t["base_b"] = self.bases.nom(p["base_b"])
        t["resultat"] = json.loads(json.dumps(res, default=_json_defaut))

    def lister(self):
        with self._verrou:
            taches = list(self._taches.values())
        taches.sort(key=lambda t: t["cree_le"], reverse=True)
        return [
            {
                k: t.get(k)
                for k in (
                    "id",
                    "action",
                    "base",
                    "societe",
                    "statut",
                    "cree_le",
                    "duree_s",
                    "erreur",
                    "params",
                )
            }
            for t in taches
        ]

    def du_jour(self, jour):
        """Tâches créées ce jour-là (copies complètes, sans leur journal)."""
        with self._verrou:
            return [
                {k: v for k, v in t.items() if k != "journal"}
                for t in self._taches.values()
                if (t.get("cree_le") or "")[:10] == jour
            ]

    def echecs_24h(self):
        with self._verrou:
            taches = list(self._taches.values())
        return [
            (t["cree_le"], t["action"], t["base"], t.get("erreur") or "?")
            for t in taches
            if t["statut"] == "echec" and depuis_24h(t["cree_le"])
        ]

    def obtenir(self, ident, depuis=0):
        with self._verrou:
            t = self._taches.get(ident)
            journal = self._journaux.get(ident)
        if t is None:
            return None
        vue = {k: v for k, v in t.items() if k != "journal"}
        vue["fichiers"] = [
            {k: f[k] for k in ("n", "format", "nom", "taille")}
            for f in t["fichiers"]
        ]
        if journal is not None:
            vue["journal"], vue["journal_suivant"] = journal.depuis(depuis)
        else:
            evs = t.get("journal") or []
            vue["journal"], vue["journal_suivant"] = evs[depuis:], len(evs)
        return vue

    def fichier(self, ident, n):
        """Chemin d'un fichier produit, uniquement s'il est enregistré dans la tâche."""
        with self._verrou:
            t = self._taches.get(ident)
        if not t:
            return None
        f = next((f for f in t["fichiers"] if f["n"] == n), None)
        if not f:
            return None
        chemin = os.path.realpath(f["chemin"])
        if not chemin.startswith(os.path.realpath(self.dossier) + os.sep):
            return None
        return chemin if os.path.isfile(chemin) else None

    def rapport(self, ident):
        with self._verrou:
            t = self._taches.get(ident)
        if not t or t["action"] != "analyser" or t["statut"] != "terminee":
            return None
        chemin = os.path.join(self.dossier, ident, "rapport.json")
        return chemin if os.path.isfile(chemin) else None


def _raconter_centre(j, nouvelles, resolues):
    for m in nouvelles:
        j.dire("Nouvelle alerte : %s" % m, "alerte")
    for m in resolues:
        j.dire("Alerte résolue : %s" % m, "ok")


# ---------------------------------------------------------------------------
# Surveillance périodique : techniques, changements, anomalies par compte
# ---------------------------------------------------------------------------


class Surveillance:
    def __init__(self, app, minutes):
        self.app = app
        self.minutes = minutes
        self.dossier = os.path.join(app.dossier, "instantanes")
        os.makedirs(self.dossier, exist_ok=True)
        self._verrou = threading.Lock()
        self.dernier_passage = None
        self.en_cours = False

    def demarrer(self):
        if self.minutes > 0:
            threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self):
        time.sleep(10)  # laisse le service démarrer
        while True:
            try:
                self.passer()
            except Exception:
                traceback.print_exc()
            time.sleep(self.minutes * 60)

    def lancer_maintenant(self):
        if self.en_cours:
            return False
        threading.Thread(target=self.passer, daemon=True).start()
        return True

    def _verifier_odoo(self):
        import xmlrpc.client

        url = os.environ.get(
            "CONCORDE_ODOO_URL", "http://127.0.0.1:8017"
        ).rstrip("/")

        class _Transport(xmlrpc.client.Transport):
            def make_connection(self, host):
                c = super().make_connection(host)
                c.timeout = 5
                return c

        try:
            v = xmlrpc.client.ServerProxy(
                url + "/xmlrpc/2/common", transport=_Transport()
            ).version()
            return True, "Odoo %s répond (%s)" % (
                v.get("server_version", "?"),
                url,
            )
        except Exception as exc:
            return False, "%s : %s" % (url, exc)

    def passer(self):
        if not self._verrou.acquire(blocking=False):
            return
        self.en_cours = True
        j = self.app.journal
        debut = time.monotonic()
        try:
            j.dire("Surveillance : début du passage", "etape")
            bases = [
                b
                for b in self.app.bases.lister(rafraichir=True)
                if b["source"] == "sql"
            ]
            if self.app.bases.pg_ok:
                j.dire(
                    "PostgreSQL joignable : %d base(s) Odoo 17" % len(bases),
                    "ok",
                )
            else:
                j.dire(
                    "PostgreSQL injoignable : %s" % self.app.bases.pg_erreur,
                    "erreur",
                )
            odoo_ok, odoo_msg = self._verifier_odoo()
            j.dire(
                odoo_msg if odoo_ok else "Odoo injoignable : %s" % odoo_msg,
                "ok" if odoo_ok else "erreur",
            )
            for b in bases:
                try:
                    self._surveiller_base(b, j)
                except Exception as exc:
                    j.dire(
                        "Base %s : surveillance impossible — %s"
                        % (b["nom"], exc),
                        "erreur",
                    )
            tech = controles_techniques(
                self.app.bases.pg_ok,
                self.app.bases.pg_erreur,
                odoo_ok,
                odoo_msg,
                self.app.dossier,
                self.app.taches.echecs_24h(),
                [
                    e
                    for e in list(self.app.sessions.historique_echecs)
                    if depuis_24h(e[0])
                ],
            )
            nouvelles, resolues = self.app.centre.synchroniser(
                "technique", "serveur", tech.constats
            )
            _raconter_centre(j, nouvelles, resolues)
            sec, sec_infos = constats_securite()
            nouvelles, resolues = self.app.centre.synchroniser(
                "securite", "serveur", sec
            )
            _raconter_centre(j, nouvelles, resolues)
            for nom, i in sec_infos.items():
                j.dire(
                    "Sécurité — dernier %s : %s (%s)"
                    % (
                        (
                            "contrôle mineur / rançongiciel"
                            if nom == "controle"
                            else "antivirus ClamAV"
                        ),
                        (i.get("statut") or "?").upper(),
                        i["date"].replace("T", " "),
                    ),
                    "ok" if i.get("statut") == "conforme" else "alerte",
                )
            j.dire(
                "Disque : %s libre" % tech.infos.get("disque_libre", "?"),
                "detail",
            )
            bases_locales.purger_sauvegardes(
                os.path.join(self.app.dossier, "sauvegardes"), journal=j
            )
            r = self.app.centre.resume()
            j.dire(
                "Surveillance terminée en %s — %d alerte(s) active(s), %d à voir"
                % (
                    duree_texte(time.monotonic() - debut),
                    r["actives"],
                    r["non_vues"],
                ),
                "alerte" if r["non_vues"] else "ok",
            )
            self.dernier_passage = datetime.now().isoformat(timespec="seconds")
        finally:
            self.en_cours = False
            self._verrou.release()

    def _surveiller_base(self, b, j):
        source = self.app.bases.ouvrir(b["id"])  # sans journal : on résume ici
        try:
            chemin = os.path.join(
                self.dossier, re.sub(r"[^\w-]", "_", b["nom"]) + ".json"
            )
            ancien = None
            if os.path.isfile(chemin):
                with open(chemin, encoding="utf-8") as f:
                    ancien = json.load(f)
            nouveau = source.instantane()
            changements = comparer_instantanes(ancien, nouveau)
            presents = [c for c in changements.constats if c["nombre"]]
            if presents:
                self.app.centre.evenements(b["nom"], presents)
                for c in presents:
                    j.dire(
                        "%s — %s : %s"
                        % (b["nom"], c["message"], nombre_texte(c["nombre"])),
                        "alerte" if c["niveau"] == "ALERTE" else "info",
                    )
            else:
                j.dire(
                    "%s — aucun changement depuis le dernier passage"
                    % b["nom"],
                    "detail",
                )
            tmp = chemin + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(nouveau, f)
            os.replace(tmp, chemin)

            bal, _ = alertes_balance(source.balance(), source.balance_tiers())
            nouvelles, resolues = self.app.centre.synchroniser(
                "balance", b["nom"], bal.constats
            )
            n = sum(
                1
                for c in bal.constats
                if c["niveau"] in ("BLOQUANT", "ALERTE")
            )
            j.dire(
                "%s — balance : %s, %d anomalie(s) par compte"
                % (
                    b["nom"],
                    (
                        "équilibrée"
                        if not any(
                            c["code"] == "BALANCE_DESEQUILIBREE"
                            for c in bal.constats
                        )
                        else "DÉSÉQUILIBRÉE"
                    ),
                    n,
                ),
                "alerte" if n else "ok",
            )
            for m in nouvelles:
                j.dire("%s — nouvelle alerte : %s" % (b["nom"], m), "alerte")
            for m in resolues:
                j.dire("%s — alerte résolue : %s" % (b["nom"], m), "ok")
        finally:
            source.fermer()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Application:
    def __init__(
        self, empreinte_mdp, dossier, bases=None, minutes_surveillance=0
    ):
        self.empreinte_mdp = empreinte_mdp
        self.dossier = dossier
        os.makedirs(dossier, exist_ok=True)
        self.sessions = Sessions()
        self.bases = bases or Bases()
        if hasattr(self.bases, "charger_libelles"):
            self.bases.charger_libelles(
                os.path.join(dossier, "noms_bases.json")
            )
        self.journal = Journal(taille_max=1000)
        self.centre = CentreAlertes(os.path.join(dossier, "alertes.json"))
        self.taches = Taches(dossier, self.bases, self.centre)
        self.surveillance = Surveillance(self, minutes_surveillance)
        self.taches.surveillance_dossier = self.surveillance.dossier
        self.journal.dire("Service CONCORDE démarré", "ok")


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "CONCORDE"
    sys_version = ""
    app = None  # Application, injectée par creer_serveur()

    # --- outils ---------------------------------------------------------------
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self._ip(), fmt % args))

    def _ip(self):
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):  # derrière Caddy : IP réelle transmise
            transmise = self.headers.get("X-Forwarded-For", "")
            if transmise:
                return transmise.split(",")[-1].strip()
        return ip

    def _entetes_securite(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")

    def _envoyer(
        self,
        code,
        corps=b"",
        type_="application/json; charset=utf-8",
        entetes=None,
    ):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self._entetes_securite()
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _json(self, code, donnees, entetes=None):
        self._envoyer(
            code,
            json.dumps(
                donnees, ensure_ascii=False, default=_json_defaut
            ).encode("utf-8"),
            entetes=entetes,
        )

    def _erreur(self, code, message):
        self._json(code, {"erreur": message})

    def _corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > CORPS_MAX:
            raise ValueError("Requête trop volumineuse.")
        brut = self.rfile.read(n) if n else b"{}"
        donnees = json.loads(brut.decode("utf-8") or "{}")
        if not isinstance(donnees, dict):
            raise ValueError("Objet JSON attendu.")
        return donnees

    def _requete(self):
        return {
            k: v[-1] for k, v in parse_qs(urlparse(self.path).query).items()
        }

    def _jeton(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None

    def _connecte(self):
        return self.app.sessions.valide(self._jeton())

    def _fichier(self, chemin, nom, type_=None):
        type_ = (
            type_ or mimetypes.guess_type(nom)[0] or "application/octet-stream"
        )
        taille = os.path.getsize(chemin)
        self.send_response(200)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(taille))
        nom_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", nom)
        self.send_header(
            "Content-Disposition", 'attachment; filename="%s"' % nom_ascii
        )
        self._entetes_securite()
        self.end_headers()
        with open(chemin, "rb") as f:
            while True:
                bloc = f.read(1 << 16)
                if not bloc:
                    break
                self.wfile.write(bloc)

    # --- routage --------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        chemin = urlparse(self.path).path
        if not chemin.startswith("/api/"):
            return self._statique(chemin)
        if chemin == "/api/etat":
            return self._json(200, {"connecte": self._connecte()})
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        q = self._requete()
        if chemin == "/api/bases":
            return self._json(
                200,
                {"bases": self.app.bases.lister(rafraichir="rafraichir" in q)},
            )
        if chemin == "/api/taches":
            return self._json(200, {"taches": self.app.taches.lister()})
        m = re.fullmatch(r"/api/taches/([\w-]+)", chemin)
        if m:
            t = self.app.taches.obtenir(m.group(1), int(q.get("depuis") or 0))
            return (
                self._json(200, t)
                if t
                else self._erreur(404, "Tâche inconnue.")
            )
        m = re.fullmatch(r"/api/taches/([\w-]+)/fichiers/(\d+)", chemin)
        if m:
            f = self.app.taches.fichier(m.group(1), int(m.group(2)))
            if not f:
                return self._erreur(404, "Fichier inconnu.")
            return self._fichier(f, os.path.basename(f))
        m = re.fullmatch(r"/api/taches/([\w-]+)/zip", chemin)
        if m:
            return self._zip(m.group(1))
        m = re.fullmatch(r"/api/taches/([\w-]+)/rapport\.json", chemin)
        if m:
            r = self.app.taches.rapport(m.group(1))
            if not r:
                return self._erreur(404, "Rapport indisponible.")
            return self._fichier(r, "concorde_analyse_%s.json" % m.group(1))
        m = re.fullmatch(
            r"/api/taches/([\w-]+)/constats/([A-Z_]+)\.csv", chemin
        )
        if m:
            return self._constat_csv(m.group(1), m.group(2))
        if chemin == "/api/comptes":
            return self._balance(q)
        m = re.fullmatch(r"/api/comptes/([\w.-]+)/grand-livre", chemin)
        if m:
            return self._grand_livre(m.group(1), q)
        m = re.fullmatch(r"/api/ecritures/(\d+)", chemin)
        if m:
            return self._ecriture(int(m.group(1)), q)
        if chemin == "/api/alertes":
            return self._json(
                200,
                {
                    "alertes": self.app.centre.lister(q.get("statut")),
                    "dernier_passage": self.app.surveillance.dernier_passage,
                    "en_cours": self.app.surveillance.en_cours,
                },
            )
        if chemin == "/api/alertes/resume":
            return self._json(200, self.app.centre.resume())
        if chemin == "/api/cles":
            locales = [
                b["nom"]
                for b in self.app.bases.lister()
                if b["source"] == "sql"
            ]
            try:
                cles = bases_locales.lister_cles_api(locales)
            except Exception as exc:
                return self._erreur(
                    500, "Lecture des clés impossible : %s" % exc
                )
            return self._json(200, {"cles": cles})
        if chemin == "/api/rapport":
            return self._rapport(q)
        if chemin == "/api/rapport/export":
            return self._rapport(q, export=True)
        if chemin == "/api/comparer/choix":
            return self._choix_comparaison(q)
        if chemin == "/api/sauvegardes":
            return self._json(
                200,
                {
                    "sauvegardes": bases_locales.lister_sauvegardes(
                        os.path.join(self.app.dossier, "sauvegardes")
                    ),
                    "retention_jours": bases_locales._retention(),
                },
            )
        if chemin == "/api/journal":
            evs, suivant = self.app.journal.depuis(int(q.get("depuis") or 0))
            return self._json(200, {"journal": evs, "suivant": suivant})
        return self._erreur(404, "Route inconnue.")

    def _verifier_origine(self):
        """Anti-CSRF : en-tête personnalisé exigé (impossible depuis un formulaire tiers)."""
        return self.headers.get("X-Concorde") == "1"

    def do_POST(self):
        chemin = urlparse(self.path).path
        if not self._verifier_origine():
            return self._erreur(403, "Requête refusée.")
        try:
            corps = self._corps()
        except (ValueError, UnicodeDecodeError) as exc:
            return self._erreur(400, str(exc))
        if chemin == "/api/connexion":
            return self._connexion(corps)
        if chemin == "/api/deconnexion":
            self.app.sessions.fermer(self._jeton())
            return self._json(
                200,
                {"ok": True},
                entetes={
                    "Set-Cookie": "%s=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"
                    % COOKIE
                },
            )
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        if chemin == "/api/taches":
            try:
                params = self._params_tache(corps)
                ident = self.app.taches.creer(
                    corps.get("action"), corps.get("base_id"), params
                )
            except ValueError as exc:
                return self._erreur(400, str(exc))
            return self._json(201, {"id": ident})
        if chemin == "/api/distants":
            try:
                ident = self.app.bases.ajouter_distant(
                    corps.get("url", "").strip(),
                    corps.get("base", "").strip(),
                    corps.get("utilisateur", "").strip(),
                    corps.get("cle", ""),
                    corps.get("libelle", ""),
                )
            except Exception as exc:
                return self._erreur(400, "Connexion impossible : %s" % exc)
            self.app.journal.dire(
                "Odoo distant ajouté : %s" % corps.get("url"), "info"
            )
            return self._json(201, {"id": ident})
        if chemin == "/api/bases/nom":
            try:
                nom = self.app.bases.renommer(
                    str(corps.get("base_id") or ""), corps.get("libelle", "")
                )
            except ValueError as exc:
                return self._erreur(400, str(exc))
            self.app.journal.dire(
                "Base %s : nom « %s »"
                % (corps.get("base_id"), nom or "(retiré)"),
                "info",
            )
            return self._json(200, {"ok": True, "libelle": nom})
        m = re.fullmatch(r"/api/distants/(xmlrpc:\w+)/cle", chemin)
        if m:
            try:
                self.app.bases.saisir_cle(
                    m.group(1), str(corps.get("cle") or "")
                )
            except Exception as exc:
                return self._erreur(400, "Clé refusée : %s" % exc)
            self.app.journal.dire(
                "Clé API ressaisie pour %s" % self.app.bases.nom(m.group(1))
            )
            return self._json(200, {"ok": True})
        if chemin == "/api/cles/revoquer":
            locales = [
                b["nom"]
                for b in self.app.bases.lister()
                if b["source"] == "sql"
            ]
            base = str(corps.get("base") or "")
            try:
                nom = bases_locales.revoquer_cle_api(
                    base,
                    corps.get("id"),
                    str(corps.get("confirmation") or ""),
                    locales,
                    journal=self.app.journal,
                )
            except bases_locales.SuppressionInterdite as exc:
                return self._erreur(400, str(exc))
            except Exception as exc:
                return self._erreur(500, "Révocation impossible : %s" % exc)
            self.app.centre.evenements(
                base,
                [
                    {
                        "code": "CLE_API_REVOQUEE",
                        "niveau": "INFO",
                        "nombre": 1,
                        "message": "Clé API révoquée",
                        "exemples": ["Clé « %s »" % nom],
                    }
                ],
            )
            return self._json(200, {"ok": True, "cle": nom})
        if chemin == "/api/rapport":
            jour = str(corps.get("jour") or "")
            try:
                date.fromisoformat(jour)
            except ValueError:
                return self._erreur(400, "Date invalide (AAAA-MM-JJ).")
            saisie = rapport_jour.nettoyer_saisie(corps)
            dossier = os.path.join(self.app.dossier, "rapports")
            os.makedirs(dossier, exist_ok=True)
            tmp = os.path.join(dossier, jour + ".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(saisie, f, ensure_ascii=False, indent=1)
            os.replace(tmp, os.path.join(dossier, jour + ".json"))
            self.app.journal.dire(
                "Rapport du %s enregistré (%d conclusion(s) masquée(s), "
                "%d ajout(s))"
                % (
                    jour,
                    sum(1 for c in saisie["conclusions"] if not c["visible"]),
                    len(saisie["ajouts"]),
                ),
                "info",
            )
            return self._rapport({"jour": jour})
        if chemin == "/api/alertes/vue":
            self.app.centre.marquer_vue(corps.get("id"))
            return self._json(200, self.app.centre.resume())
        if chemin == "/api/surveillance":
            lance = self.app.surveillance.lancer_maintenant()
            return self._json(
                202 if lance else 409,
                {
                    "lance": lance,
                    "message": (
                        "Passage lancé."
                        if lance
                        else "Un passage est déjà en cours."
                    ),
                },
            )
        return self._erreur(404, "Route inconnue.")

    def do_DELETE(self):
        chemin = urlparse(self.path).path
        if not self._verifier_origine():
            return self._erreur(403, "Requête refusée.")
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        m = re.fullmatch(r"/api/distants/(xmlrpc:\w+)/cle", chemin)
        if m and self.app.bases.supprimer_cle(m.group(1)):
            self.app.journal.dire(
                "Clé API supprimée de CONCORDE pour %s (rien ne change chez "
                "le client)" % self.app.bases.nom(m.group(1)),
                "info",
            )
            return self._json(200, {"ok": True})
        m = re.fullmatch(r"/api/distants/(xmlrpc:\w+)", chemin)
        if m and self.app.bases.retirer_distant(m.group(1)):
            self.app.journal.dire("Base distante retirée de CONCORDE", "info")
            return self._json(200, {"ok": True})
        return self._erreur(404, "Base inconnue.")

    # --- actions --------------------------------------------------------------
    def _connexion(self, corps):
        ip = self._ip()
        if self.app.sessions.bloquee(ip):
            self.app.journal.dire(
                "Connexion bloquée (trop d'essais) depuis %s" % ip, "alerte"
            )
            return self._erreur(
                429, "Trop d'essais. Réessayez dans 15 minutes."
            )
        if not verifier(str(corps.get("mdp", "")), self.app.empreinte_mdp):
            self.app.sessions.echec(ip)
            self.app.journal.dire(
                "Mot de passe refusé depuis %s" % ip, "alerte"
            )
            time.sleep(0.5)
            return self._erreur(401, "Mot de passe incorrect.")
        jeton = self.app.sessions.ouvrir(ip)
        self.app.journal.dire("Connexion réussie depuis %s" % ip, "info")
        return self._json(
            200,
            {"ok": True},
            entetes={
                "Set-Cookie": "%s=%s; Path=/; HttpOnly; Secure; SameSite=Strict"
                % (COOKIE, jeton)
            },
        )

    @staticmethod
    def _params_tache(corps):
        p = {}
        for cle in ("du", "au"):
            v = corps.get(cle) or None
            if v:
                _date(v)  # valide AAAA-MM-JJ (ValueError sinon)
            p[cle] = v
        if p["du"] and p["au"] and p["du"] > p["au"]:
            raise ValueError("La date de début est après la date de fin.")
        p["validees"] = bool(corps.get("validees"))
        p["brouillons"] = bool(corps.get("brouillons"))
        p["formats"] = [f for f in corps.get("formats") or [] if f in FORMATS]
        p["objets"] = [o for o in corps.get("objets") or [] if o in OBJETS]
        if corps.get("action") == "telecharger" and not p["formats"]:
            raise ValueError("Choisissez au moins un format.")
        if corps.get("action") == "telecharger" and not p["objets"]:
            raise ValueError("Choisissez au moins un type de données.")
        p["separateur"] = "tab" if corps.get("separateur") == "tab" else "pipe"
        p["encodage"] = (
            "utf-8" if corps.get("encodage") == "utf-8" else "iso-8859-15"
        )
        if corps.get("action") in ("supprimer_base", "reinitialiser_base"):
            p["confirmation"] = str(corps.get("confirmation") or "")
        if corps.get("action") == "comparer":
            p["base_b"] = str(corps.get("base_id_b") or "")
            if not p["base_b"] or p["base_b"] == corps.get("base_id"):
                raise ValueError("Choisissez deux bases différentes.")
            dc = (corps.get("date_copie") or "").strip()
            if dc:
                datetime.fromisoformat(
                    dc
                )  # ValueError si la date est invalide
            p["date_copie"] = dc
            for cle in ("comptes", "analytiques"):
                v = corps.get(cle) or []
                if not isinstance(v, list) or len(v) > 5000:
                    raise ValueError("Liste « %s » invalide." % cle)
                p[cle] = sorted(
                    {str(x).strip()[:120] for x in v if str(x).strip()}
                )
        return p

    def _source_requete(self, q):
        """Ouvre la base demandée (?base=…) avec les filtres communs, ou lève ValueError."""
        base = q.get("base") or ""
        if not any(b["id"] == base for b in self.app.bases.lister()):
            raise ValueError("Base inconnue.")
        du, au = _date(q.get("du")), _date(q.get("au"))
        etats = (
            ("posted", "draft") if q.get("brouillons") == "1" else ("posted",)
        )
        return self.app.bases.ouvrir(base), du, au, etats

    def _rapport(self, q, export=False):
        """Rapport du jour : automatique + choix enregistrés ; export = page imprimable."""
        jour = q.get("jour") or date.today().isoformat()
        try:
            date.fromisoformat(jour)
        except ValueError:
            return self._erreur(400, "Date invalide (AAAA-MM-JJ).")
        securite = {}
        for nom in ("controle", "antivirus"):
            chemin = os.path.join(DOSSIER_SECURITE, nom + ".json")
            try:
                with open(chemin, encoding="utf-8") as f:
                    securite[nom] = json.load(f)
            except (OSError, ValueError):
                pass
        auto = rapport_jour.construire(
            jour,
            self.app.centre.lister(),
            self.app.taches.du_jour(jour),
            securite,
        )
        enregistre = None
        chemin = os.path.join(self.app.dossier, "rapports", jour + ".json")
        if os.path.isfile(chemin):
            with open(chemin, encoding="utf-8") as f:
                enregistre = json.load(f)
        r = rapport_jour.fusionner(auto, enregistre)
        if not export:
            return self._json(200, r)
        corps = rapport_jour.rendu_html(r).encode("utf-8")
        self._envoyer(
            200,
            corps,
            "text/html; charset=utf-8",
            {
                "Content-Disposition": 'attachment; filename="concorde_rapport_%s.html"'
                % jour
            },
        )

    def _choix_comparaison(self, q):
        """Comptes comptables et analytiques existant dans l'une ou l'autre des deux bases."""
        connues = {b["id"] for b in self.app.bases.lister()}
        ids = [q.get("base_a") or "", q.get("base_b") or ""]
        if not all(i in connues for i in ids):
            return self._erreur(400, "Base inconnue.")
        comptes, analytiques = {}, {}
        for lettre, ident in zip("AB", ids):
            try:
                s = self.app.bases.ouvrir(ident)
            except Exception as exc:
                return self._erreur(
                    500, "Base %s illisible : %s" % (lettre, exc)
                )
            try:
                for c in s.comptes():
                    e = comptes.setdefault(
                        c["code"],
                        {
                            "code": c["code"],
                            "libelle": c["libelle"],
                            "bases": "",
                        },
                    )
                    e["bases"] += lettre
                for nom in sorted(set(s.noms_analytiques().values())):
                    e = analytiques.setdefault(nom, {"nom": nom, "bases": ""})
                    if lettre not in e["bases"]:
                        e["bases"] += lettre
            finally:
                s.fermer()
        return self._json(
            200,
            {
                "comptes": sorted(comptes.values(), key=lambda c: c["code"]),
                "analytiques": sorted(
                    analytiques.values(), key=lambda a: a["nom"].lower()
                ),
            },
        )

    def _balance(self, q):
        try:
            source, du, au, etats = self._source_requete(q)
        except ValueError as exc:
            return self._erreur(400, str(exc))
        t = time.monotonic()
        try:
            bal = source.balance(du, au, etats)
            rapport, par_compte = alertes_balance(
                bal, source.balance_tiers(du, au, etats)
            )
        except Exception as exc:
            return self._erreur(500, "Balance impossible : %s" % exc)
        finally:
            source.fermer()
        constats = [
            dict(
                {k: v for k, v in c.items() if k != "elements"},
                explication=_marceau.expliquer_alerte(c["code"], c["message"]),
            )
            for c in rapport.en_dict()["constats"]
        ]
        self.app.journal.dire(
            "Balance de %s consultée (%s comptes, %s)"
            % (
                self.app.bases.nom(q["base"]),
                nombre_texte(len(bal)),
                duree_texte(time.monotonic() - t),
            ),
            "detail",
        )
        return self._json(
            200,
            {
                "comptes": [
                    dict(c, alertes=par_compte.get(c["code"], [])) for c in bal
                ],
                "infos": rapport.infos,
                "constats": constats,
            },
        )

    def _grand_livre(self, code, q):
        try:
            source, du, au, etats = self._source_requete(q)
            offset = max(0, int(q.get("offset") or 0))
        except ValueError as exc:
            return self._erreur(400, str(exc))
        try:
            page, totaux = grand_livre(
                source.lignes(du, au, etats, comptes=[code]),
                offset,
                LIMITE_GRAND_LIVRE,
            )
        except Exception as exc:
            return self._erreur(500, "Grand livre impossible : %s" % exc)
        finally:
            source.fermer()
        return self._json(
            200,
            {
                "compte": code,
                "lignes": page,
                "totaux": totaux,
                "offset": offset,
                "limite": LIMITE_GRAND_LIVRE,
            },
        )

    def _ecriture(self, ident, q):
        try:
            source, _, _, _ = self._source_requete(q)
        except ValueError as exc:
            return self._erreur(400, str(exc))
        try:
            lignes = source.ecriture(ident)
        except Exception as exc:
            return self._erreur(500, "Écriture illisible : %s" % exc)
        finally:
            source.fermer()
        if not lignes:
            return self._erreur(404, "Écriture introuvable.")
        return self._json(200, {"lignes": lignes, "etats": list(ETATS)})

    def _zip(self, ident):
        t = self.app.taches.obtenir(ident)
        if not t or not t["fichiers"]:
            return self._erreur(404, "Aucun fichier.")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in t["fichiers"]:
                chemin = self.app.taches.fichier(ident, f["n"])
                if chemin:
                    z.write(chemin, f["nom"])
        self._envoyer(
            200,
            buf.getvalue(),
            "application/zip",
            {
                "Content-Disposition": 'attachment; filename="concorde_%s.zip"'
                % ident
            },
        )

    def _constat_csv(self, ident, code):
        r = self.app.taches.rapport(ident)
        if not r:
            return self._erreur(404, "Rapport indisponible.")
        with open(r, encoding="utf-8") as f:
            rapport = json.load(f)
        c = next((c for c in rapport["constats"] if c["code"] == code), None)
        if not c:
            return self._erreur(404, "Constat inconnu.")
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow([c["message"]])
        for e in c["elements"]:
            w.writerow([e])
        self._envoyer(
            200,
            ("﻿" + buf.getvalue()).encode("utf-8"),
            "text/csv; charset=utf-8",
            {
                "Content-Disposition": 'attachment; filename="%s_%s.csv"'
                % (code.lower(), ident)
            },
        )

    def _statique(self, chemin):
        if chemin in ("/", ""):
            chemin = "/index.html"
        nom = os.path.normpath(chemin.lstrip("/"))
        complet = os.path.realpath(os.path.join(STATIQUE, nom))
        if not complet.startswith(
            os.path.realpath(STATIQUE) + os.sep
        ) or not os.path.isfile(complet):
            return self._erreur(404, "Introuvable.")
        with open(complet, "rb") as f:
            corps = f.read()
        type_ = mimetypes.guess_type(complet)[0] or "application/octet-stream"
        if type_.startswith("text/") or type_ in ("application/javascript",):
            type_ += "; charset=utf-8"
        self._envoyer(200, corps, type_)


def creer_serveur(app, hote="127.0.0.1", port=18090):
    gestionnaire = type("GestionnaireConcorde", (Gestionnaire,), {"app": app})
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    return serveur


def _env_postgres():
    """PG* (libpq) à défaut repris de POSTGRES_USER / POSTGRES_PASSWORD (deploy/.env)."""
    for pg, docker in (
        ("PGUSER", "POSTGRES_USER"),
        ("PGPASSWORD", "POSTGRES_PASSWORD"),
    ):
        if not os.environ.get(pg) and os.environ.get(docker):
            os.environ[pg] = os.environ[docker]


def main():
    empreinte = os.environ.get("CONCORDE_UI_MDP", "")
    if not empreinte.startswith("scrypt$"):
        print(
            "ERREUR : CONCORDE_UI_MDP absent. Lancez scripts/concorde_interface_mdp.py.",
            file=sys.stderr,
        )
        return 1
    _env_postgres()
    port = int(os.environ.get("CONCORDE_UI_PORT", "18090"))
    dossier = os.environ.get(
        "CONCORDE_UI_DONNEES", "/var/lib/concorde-interface"
    )
    minutes = int(os.environ.get("CONCORDE_UI_SURVEILLANCE", "15"))
    app = Application(empreinte, dossier, minutes_surveillance=minutes)
    serveur = creer_serveur(app, "127.0.0.1", port)
    app.surveillance.demarrer()
    print(
        "CONCORDE interface : http://127.0.0.1:%d (données : %s, surveillance : %s)"
        % (
            port,
            dossier,
            "toutes les %d min" % minutes if minutes else "désactivée",
        )
    )
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
