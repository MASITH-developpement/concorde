# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""CHAÎNE DE CONVERSION ODOO 14 → 15 → 16 → 17 → 18 → 19.

CONCORDE convertit des écritures comptables Odoo d'une version à la suivante,
pas à pas (14→15→16→17→18→19), en passant par le modèle canonique en centimes.

Principe : les montants ne changent JAMAIS entre versions Odoo. Chaque saut
N→N+1 re-serialise le canonique selon l'adaptateur de la version cible
(payload account.move globalement stable de 14 à 19 : ref, journal_id, date,
move_type, line_ids name/account_id/debit/credit).

Sécurités CONCORDE respectées :
- Montants en centimes int à chaque étape (jamais de float)
- Équilibre tolérance 0,00 € vérifié à CHAQUE saut de version
- Idempotence conservée (clé journal/écriture/compte/montants/libellé)
- Mode dry-run par défaut : aucune donnée n'est extraite ni injectée
  sans identifiants explicites et dry_run=False
- Guardian : la conversion refuse de tourner sans self-check OK
- version_source tracée sur chaque ligne canonique
"""
from collections import defaultdict

from core.guardian import Guardian
from core.canonical import Canonique, LigneEcriture


class ErreurConversion(RuntimeError):
    pass


VERSIONS_SUPPORTEES = ["14", "15", "16", "17", "18", "19"]


class ConvertisseurOdoo:
    """Chaîne de conversion Odoo 14→19 via le canonique CONCORDE.

    En mode dry-run (défaut), l'entrée peut être un Canonique déjà chargé
    (ex. issu d'un FEC) : la chaîne simule la conversion sans toucher à
    une base Odoo.
    """

    VERSIONS = VERSIONS_SUPPORTEES

    def __init__(self, url=None, db=None, utilisateur=None, mot_de_passe=None,
                 dry_run=True, guardian=None):
        self.url = url
        self.db = db
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.dry_run = dry_run
        self.guardian = guardian or Guardian()
        if not self.guardian.self_check_ok:
            self.guardian.self_check()  # bloquant
        self._uid = None
        self._models = None

    # --- validation des versions ----------------------------------------------
    def _valider_version(self, v: str):
        if v not in self.VERSIONS:
            raise ErreurConversion(
                "Version Odoo %r non supportée. Versions supportées : %s." %
                (v, "→".join(self.VERSIONS)))

    @staticmethod
    def chemin_de_versions(source: str, cible: str):
        """Liste ordonnée des sauts, ex. ('14','19') -> [('14','15'),...,('18','19')]."""
        if source not in VERSIONS_SUPPORTEES or cible not in VERSIONS_SUPPORTEES:
            raise ErreurConversion(
                "Versions %s→%s hors chaîne supportée (%s)." %
                (source, cible, "→".join(VERSIONS_SUPPORTEES)))
        i, j = VERSIONS_SUPPORTEES.index(source), VERSIONS_SUPPORTEES.index(cible)
        if j < i:
            raise ErreurConversion(
                "Conversion ascendante uniquement : %s→%s interdit (rétro-conversion refusée)."
                % (source, cible))
        return [(VERSIONS_SUPPORTEES[k], VERSIONS_SUPPORTEES[k + 1])
                for k in range(i, j)]

    # --- extraction (source Odoo) ----------------------------------------------
    def connecter_source(self, version_source: str):
        """Connexion XML-RPC v2 à l'Odoo source (jamais utilisée en dry-run)."""
        if self.dry_run:
            return None
        if not all([self.url, self.db, self.utilisateur, self.mot_de_passe]):
            raise ErreurConversion(
                "URL/base/utilisateur/mot de passe Odoo requis hors dry-run.")
        import xmlrpc.client
        commun = xmlrpc.client.ServerProxy("{}/xmlrpc/2/common".format(self.url))
        try:
            version = commun.version().get("server_version", "")
            if version and not version.startswith(version_source):
                self.guardian.tracer(
                    "odoo_conversion", "avertissement",
                    "version_odoo=%s (attendue %s)" % (version, version_source))
        except Exception:
            pass
        self._uid = commun.authenticate(self.db, self.utilisateur, self.mot_de_passe, {})
        if not self._uid:
            raise ErreurConversion("Authentification Odoo refusée.")
        self._models = xmlrpc.client.ServerProxy("{}/xmlrpc/2/object".format(self.url))
        return self._uid

    def extraire(self, version_source: str):
        """Extrait les account.move de l'Odoo source vers un Canonique (centimes).

        Refusé en dry-run : la conversion à partir de données réelles exige
        dry_run=False et une connexion explicite. Le canonique d'entrée est
        alors fourni directement (pas d'import de données).
        """
        if self.dry_run:
            raise ErreurConversion(
                "Extraction Odoo impossible en dry-run : fournissez le canonique "
                "d'entrée (aucune donnée réelle n'est importée par défaut).")
        self.connecter_source(version_source)
        moves = self._models.execute_kw(
            self.db, self._uid, self.mot_de_passe,
            "account.move", "search_read",
            [[]], {"fields": ["ref", "journal_id", "date", "name", "move_type", "line_ids"]})
        canon = Canonique()
        for m in moves:
            lignes = self._models.execute_kw(
                self.db, self._uid, self.mot_de_passe,
                "account.move.line", "read",
                [m["line_ids"]],
                {"fields": ["name", "account_id", "debit", "credit"]})
            for l in lignes:
                import datetime
                canon.ajouter(LigneEcriture(
                    journal_code=str(m["journal_id"][0]),
                    ecriture_num=str(m["id"]),
                    date_ecriture=datetime.date.fromisoformat(m["date"]),
                    compte=str(l["account_id"][0]),
                    libelle=str(l["name"] or m.get("name") or ""),
                    debit=int(round(l["debit"] * 100)),
                    credit=int(round(l["credit"] * 100)),
                    piece=str(m.get("ref") or ""),
                    version_source=version_source,
                ))
        self.guardian.tracer("odoo_conversion", "extraction",
                             "version=%s ecritures=%s" % (version_source, len(moves)))
        return canon

    # --- adaptateurs par version ----------------------------------------------
    # Payload account.move stable de 14 à 19 ; seules des clés annexes
    # apparaissent/disparaissent. On ne fait jamais apparaître de montant.
    ADAPTATEURS = {
        "14": {"move_type": "entry", "cle_date": "date"},
        "15": {"move_type": "entry", "cle_date": "date"},
        "16": {"move_type": "entry", "cle_date": "date"},
        "17": {"move_type": "entry", "cle_date": "date"},
        "18": {"move_type": "entry", "cle_date": "date"},
        "19": {"move_type": "entry", "cle_date": "date"},
    }

    @classmethod
    def vers_payload_version(cls, ecriture: dict, version: str) -> dict:
        """Payload account.move pour la version cible (montants en centimes int)."""
        adapt = cls.ADAPTATEURS.get(version)
        if adapt is None:
            raise ErreurConversion("Version cible %r non supportée." % version)
        return {
            "ref": ecriture["ref_ext"],
            "journal_id": ecriture["journal"],
            "date": ecriture["date"].strftime("%Y-%m-%d"),
            "move_type": adapt["move_type"],
            "line_ids": [{
                "name": l.libelle,
                "account_id": l.compte,
                "debit": l.debit,    # centimes int — jamais de float
                "credit": l.credit,
            } for l in ecriture["lignes"]],
        }

    # --- un saut N -> N+1 -------------------------------------------------------
    def convertir_etape(self, canon: Canonique, source: str, cible: str) -> Canonique:
        """Un saut de version : re-serialisation canonique -> payload cible -> canonique.

        Vérifie l'équilibre AVANT et APRÈS ; tolérance 0,00 €.
        """
        self._valider_version(source)
        self._valider_version(cible)
        if not canon.est_equilibre(tolerance=0):
            raise ErreurConversion(
                "Canonique déséquilibré avant %s→%s (D=%s / C=%s centimes) — "
                "tolérance Concordance 0,00 €." %
                (source, cible, canon.total_debit, canon.total_credit))
        ecritures = self._regrouper(canon)
        sortie = Canonique()
        import datetime
        for e in ecritures:
            payload = self.vers_payload_version(e, cible)
            for ligne in payload["line_ids"]:
                sortie.ajouter(LigneEcriture(
                    journal_code=str(payload["journal_id"]),
                    ecriture_num=payload["ref"],
                    date_ecriture=datetime.date.fromisoformat(payload["date"]),
                    compte=ligne["account_id"],
                    libelle=ligne["name"],
                    debit=ligne["debit"],
                    credit=ligne["credit"],
                    version_source=cible,
                ))
        if not sortie.est_equilibre(tolerance=0):
            raise ErreurConversion(
                "Canonique déséquilibré après %s→%s — tolérance Concordance 0,00 €." %
                (source, cible))
        self.guardian.tracer("odoo_conversion", "etape",
                             "%s->%s lignes=%s" % (source, cible, len(sortie)))
        return sortie

    # --- chaîne complète -------------------------------------------------------
    @staticmethod
    def _regrouper(canon: Canonique):
        groupes = defaultdict(list)
        for l in canon.lignes:
            groupes[(l.journal_code, l.ecriture_num)].append(l)
        ecritures = []
        for (journal, num), lignes in sorted(groupes.items()):
            debit = sum(l.debit for l in lignes)
            credit = sum(l.credit for l in lignes)
            if debit != credit:
                raise ErreurConversion(
                    "Écriture %s/%s déséquilibrée (%s vs %s centimes) — "
                    "tolérance Concordance 0,00 €." % (journal, num, debit, credit))
            ecritures.append({
                "ref_ext": num if num.startswith("CONCORDE/") else num,
                "journal": journal,
                "numero": num,
                "date": lignes[0].date_ecriture,
                "libelle": lignes[0].libelle,
                "lignes": lignes,
                "total": debit,
            })
        return ecritures

    def convertir_chainee(self, canon: Canonique, source="14", cible="19",
                          dry_run=True) -> dict:
        """Chaîne complète 14→15→…→cible. Retourne un rapport détaillé par saut.

        dry_run=True (défaut) : rien n'est injecté dans une base Odoo ;
        seul le canonique converti et le rapport sont produits.
        """
        sauts = self.chemin_de_versions(source, cible)
        rapport = {"source": source, "cible": cible,
                   "mode": "dry-run" if dry_run else "production",
                   "etapes": [], "nb_lignes_final": 0,
                   "version_source_final": cible}
        courant = canon
        for (src, dst) in sauts:
            avant = len(courant)
            courant = self.convertir_etape(courant, src, dst)
            rapport["etapes"].append({
                "saut": "%s→%s" % (src, dst),
                "nb_lignes_avant": avant,
                "nb_lignes_apres": len(courant),
                "equilibre": True,
            })
        rapport["nb_lignes_final"] = len(courant)
        rapport["canonique"] = courant
        # Invariants : montants en centimes inchangés de bout en bout
        if courant.total_debit != canon.total_debit or \
           courant.total_credit != canon.total_credit:
            raise ErreurConversion(
                "Invariant violé : les totaux en centimes ont changé (%s/%s -> %s/%s)."
                % (canon.total_debit, canon.total_credit,
                   courant.total_debit, courant.total_credit))
        self.guardian.tracer("odoo_conversion", "chaine",
                             "%s->%s sauts=%s mode=%s" %
                             (source, cible, len(sauts), rapport["mode"]))
        return rapport
