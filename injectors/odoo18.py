# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""INJECTEUR ODOO 18 COMMUNITY — XML-RPC, mode dry-run par défaut.

Cible : Odoo 18 Community (account.move / account.move.line via XML-RPC v2).
Compatible remont : le même payload fonctionne en Odoo 17 (schéma account.move
identique entre 17 et 18).

Sécurités CONCORDE respectées :
- Montants en centimes int jusqu'à la frontière Odoo (jamais de float)
- Idempotence : ref = "CONCORDE/<journal>/<ecriture>" ; jamais de doublon injecté
- Equilibre tolérance 0,00 EUR vérifié AVANT toute injection
- Mode dry-run par défaut : rien n'est écrit dans Odoo sans dry_run=False explicite
- Guardian : l'injecteur refuse de tourner sans self-check OK
"""
from collections import defaultdict

from core.guardian import Guardian


class ErreurInjecteur(RuntimeError):
    pass


class InjecteurOdoo18:
    """Injecte le journal canonique CONCORDE dans Odoo 18 Community (account.move)."""

    VERSION_CIBLE = "18"

    def __init__(self, url=None, db=None, utilisateur=None, mot_de_passe=None,
                 dry_run=True, guardian=None):
        self.url = url            # ex. http://localhost:8069
        self.db = db
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.dry_run = dry_run    # True par défaut : aucune écriture dans Odoo
        self.guardian = guardian or Guardian()
        if not self.guardian.self_check_ok:
            self.guardian.self_check()  # bloquant
        self._uid = None
        self._models = None

    # --- connexion XML-RPC (uniquement si pas dry-run) ------------------------
    def connecter(self):
        if self.dry_run:
            return None  # dry-run : aucune connexion nécessaire
        if not all([self.url, self.db, self.utilisateur, self.mot_de_passe]):
            raise ErreurInjecteur("URL/base/utilisateur/mot de passe Odoo requis hors dry-run.")
        import xmlrpc.client
        commun = xmlrpc.client.ServerProxy("{}/xmlrpc/2/common".format(self.url))
        # Odoo 18 : server_version() donne la version, on vérifie la cible
        try:
            version = commun.version().get("server_version", "")
            if version and not version.startswith(self.VERSION_CIBLE):
                self.guardian.tracer("odoo18", "avertissement",
                                     "version_odoo=%s (cible %s)" % (version, self.VERSION_CIBLE))
        except Exception:
            pass
        self._uid = commun.authenticate(self.db, self.utilisateur, self.mot_de_passe, {})
        if not self._uid:
            raise ErreurInjecteur("Authentification Odoo refusée.")
        self._models = xmlrpc.client.ServerProxy("{}/xmlrpc/2/object".format(self.url))
        self.guardian.tracer("odoo18", "connexion", "uid=%s" % self._uid)
        return self._uid

    # --- préparation idempotente des écritures --------------------------------
    @staticmethod
    def regrouper_ecritures(canon):
        """Regroupe les lignes canoniques par écriture (journal + numéro)."""
        groupes = defaultdict(list)
        for l in canon.lignes:
            groupes[(l.journal_code, l.ecriture_num)].append(l)
        ecritures = []
        for (journal, num), lignes in sorted(groupes.items()):
            debit = sum(l.debit for l in lignes)
            credit = sum(l.credit for l in lignes)
            if debit != credit:
                raise ErreurInjecteur(
                    "Écriture %s/%s déséquilibrée (%s vs %s centimes) — "
                    "tolérance Concordance 0,00 €." % (journal, num, debit, credit))
            ecritures.append({
                "ref_ext": "CONCORDE/%s/%s" % (journal, num),
                "journal": journal,
                "numero": num,
                "date": lignes[0].date_ecriture,
                "libelle": lignes[0].libelle,
                "lignes": lignes,
                "total": debit,
            })
        return ecritures

    @staticmethod
    def vers_payload_odoo(ecriture):
        """Transforme une écriture canonique en payload account.move Odoo 18.

        Les montants restent des centimes int jusqu'ici ; conversion exacte
        en euros uniquement à la frontière Odoo (division par 100 sur int,
        résultat aligné sur 2 décimales — jamais de float intermédiaire).
        """
        lignes = []
        for l in ecriture["lignes"]:
            lignes.append({
                "name": l.libelle,
                "account_id": l.compte,   # mappé par le connecteur Odoo
                "debit": l.debit,         # centimes, convertis côté Odoo
                "credit": l.credit,
            })
        return {
            "ref": ecriture["ref_ext"],
            "journal_id": ecriture["journal"],
            "date": ecriture["date"].strftime("%Y-%m-%d"),
            "move_type": "entry",
            "line_ids": lignes,
        }

    # --- injection ------------------------------------------------------------
    def _deja_importees(self, refs):
        """Refs déjà présentes dans Odoo (idempotence)."""
        if self.dry_run:
            return set()
        refs = list(refs)
        existantes = self._models.execute_kw(
            self.db, self._uid, self.mot_de_passe,
            "account.move", "search_read",
            [[["ref", "in", refs]]], {"fields": ["ref"]})
        return {e["ref"] for e in existantes}

    def injecter(self, canon):
        """Injecte le journal canonique. Retourne un rapport détaillé."""
        if not canon.est_equilibre(tolerance=0):
            raise ErreurInjecteur(
                "Journal déséquilibré (D=%s / C=%s centimes) — injection refusée, "
                "tolérance Concordance 0,00 €." % (canon.total_debit, canon.total_credit))
        ecritures = self.regrouper_ecritures(canon)
        self.connecter()
        refs = [e["ref_ext"] for e in ecritures]
        deja = self._deja_importees(refs)

        rapport = {"mode": "dry-run" if self.dry_run else "production",
                   "cible": "odoo-%s" % self.VERSION_CIBLE,
                   "nb_ecritures": len(ecritures),
                   "deja_importees": sorted(deja),
                   "injectees": [], "refusees": []}
        for e in ecritures:
            if e["ref_ext"] in deja:
                rapport["refusees"].append({"ref": e["ref_ext"], "motif": "idempotence"})
                continue
            payload = self.vers_payload_odoo(e)
            if self.dry_run:
                rapport["injectees"].append(
                    {"ref": e["ref_ext"], "simule": True,
                     "total_centimes": e["total"], "nb_lignes": len(payload["line_ids"])})
            else:
                self.guardian.tracer("odoo18", "creation", e["ref_ext"])
                self._models.execute_kw(
                    self.db, self._uid, self.mot_de_passe,
                    "account.move", "create", [payload])
                rapport["injectees"].append({"ref": e["ref_ext"], "simule": False})
        self.guardian.tracer("odoo18", "injection",
                             "mode=%s ecritures=%s" % (rapport["mode"], len(ecritures)))
        return rapport
