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

from datetime import date
from typing import ClassVar, TypedDict

from core.canonical import Canonique, LigneEcriture
from core.guardian import Guardian
from injectors.socle_odoo import (
    ConnexionOdoo,
    EcritureRegroupee,
    connecter_odoo,
    regrouper_ecritures,
)


class ErreurConversion(RuntimeError):
    """Refus de conversion : version hors chaîne, déséquilibre, accès."""


class LignePayloadVersion(TypedDict):
    """Ligne du payload converti (montants en centimes int)."""

    name: str
    account_id: str
    debit: int
    credit: int


class PayloadVersion(TypedDict):
    """Payload account.move d'une version cible, en centimes."""

    ref: str
    journal_id: str
    date: str
    move_type: str
    line_ids: list[LignePayloadVersion]


class EtapeConversion(TypedDict):
    """Compte rendu d'un saut de version N -> N+1."""

    saut: str
    nb_lignes_avant: int
    nb_lignes_apres: int
    equilibre: bool


class RapportConversion(TypedDict):
    """Rapport rendu par `ConvertisseurOdoo.convertir_chainee`."""

    source: str
    cible: str
    mode: str
    etapes: list[EtapeConversion]
    nb_lignes_final: int
    version_source_final: str
    canonique: Canonique


VERSIONS_SUPPORTEES = ["14", "15", "16", "17", "18", "19"]


class ConvertisseurOdoo:
    """Chaîne de conversion Odoo 14→19 via le canonique CONCORDE.

    En mode dry-run (défaut), l'entrée peut être un Canonique déjà chargé
    (ex. issu d'un FEC) : la chaîne simule la conversion sans toucher à
    une base Odoo.
    """

    VERSIONS: ClassVar[list[str]] = VERSIONS_SUPPORTEES

    def __init__(
        self,
        url: str | None = None,
        db: str | None = None,
        utilisateur: str | None = None,
        mot_de_passe: str | None = None,
        dry_run: bool = True,
        guardian: Guardian | None = None,
    ) -> None:
        """Prépare la chaîne ; le Guardian doit passer son self-check.

        dry_run=True (défaut) : aucune extraction ni injection Odoo.
        """
        self.url = url
        self.db = db
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.dry_run = dry_run
        self.guardian = guardian or Guardian()
        if not self.guardian.self_check_ok:
            self.guardian.self_check()  # bloquant
        self._connexion: ConnexionOdoo | None = None

    # --- validation des versions ---------------------------------------------
    def _valider_version(self, v: str) -> None:
        """Refuse une version absente de la chaîne supportée."""
        if v not in self.VERSIONS:
            raise ErreurConversion(
                "Version Odoo %r non supportée. Versions supportées : %s."
                % (v, "→".join(self.VERSIONS))
            )

    @staticmethod
    def chemin_de_versions(source: str, cible: str) -> list[tuple[str, str]]:
        """Liste ordonnée des sauts de version.

        Exemple : ('14', '19') -> [('14', '15'), ..., ('18', '19')].
        """
        if (
            source not in VERSIONS_SUPPORTEES
            or cible not in VERSIONS_SUPPORTEES
        ):
            raise ErreurConversion(
                "Versions %s→%s hors chaîne supportée (%s)."
                % (source, cible, "→".join(VERSIONS_SUPPORTEES))
            )
        i = VERSIONS_SUPPORTEES.index(source)
        j = VERSIONS_SUPPORTEES.index(cible)
        if j < i:
            raise ErreurConversion(
                "Conversion ascendante uniquement : %s→%s interdit "
                "(rétro-conversion refusée)." % (source, cible)
            )
        return [
            (VERSIONS_SUPPORTEES[k], VERSIONS_SUPPORTEES[k + 1])
            for k in range(i, j)
        ]

    # --- extraction (source Odoo) --------------------------------------------
    def connecter_source(self, version_source: str) -> int | None:
        """Connexion XML-RPC v2 à l'Odoo source (jamais utilisée en dry-run).

        Rend l'uid Odoo, ou None en dry-run.
        """
        if self.dry_run:
            return None
        if not (
            self.url and self.db and self.utilisateur and self.mot_de_passe
        ):
            raise ErreurConversion(
                "URL/base/utilisateur/mot de passe Odoo requis hors dry-run."
            )
        self._connexion = connecter_odoo(
            self.url,
            self.db,
            self.utilisateur,
            self.mot_de_passe,
            version_source,
            self.guardian,
            "odoo_conversion",
            "attendue",
            ErreurConversion,
        )
        return self._connexion.uid

    def extraire(self, version_source: str) -> Canonique:
        """Extrait les account.move de l'Odoo source vers un Canonique.

        Montants convertis en centimes int.

        Refusé en dry-run : la conversion à partir de données réelles exige
        dry_run=False et une connexion explicite. Le canonique d'entrée est
        alors fourni directement (pas d'import de données).
        """
        if self.dry_run:
            raise ErreurConversion(
                "Extraction Odoo impossible en dry-run : fournissez le "
                "canonique d'entrée (aucune donnée réelle n'est importée par "
                "défaut)."
            )
        self.connecter_source(version_source)
        if self._connexion is None:
            raise ErreurConversion("Aucune connexion Odoo ouverte.")
        connexion = self._connexion
        moves = connexion.executer(
            "account.move",
            "search_read",
            [[]],
            {
                "fields": [
                    "ref",
                    "journal_id",
                    "date",
                    "name",
                    "move_type",
                    "line_ids",
                ]
            },
        )
        canon = Canonique()
        for m in moves:
            lignes = connexion.executer(
                "account.move.line",
                "read",
                [m["line_ids"]],
                {"fields": ["name", "account_id", "debit", "credit"]},
            )
            for ligne in lignes:
                canon.ajouter(
                    LigneEcriture(
                        journal_code=str(m["journal_id"][0]),
                        ecriture_num=str(m["id"]),
                        date_ecriture=date.fromisoformat(m["date"]),
                        compte=str(ligne["account_id"][0]),
                        libelle=str(ligne["name"] or m.get("name") or ""),
                        debit=int(round(ligne["debit"] * 100)),
                        credit=int(round(ligne["credit"] * 100)),
                        piece=str(m.get("ref") or ""),
                        version_source=version_source,
                    )
                )
        self.guardian.tracer(
            "odoo_conversion",
            "extraction",
            "version=%s ecritures=%s" % (version_source, len(moves)),
        )
        return canon

    # --- adaptateurs par version ---------------------------------------------
    # Payload account.move stable de 14 à 19 ; seules des clés annexes
    # apparaissent/disparaissent. On ne fait jamais apparaître de montant.
    ADAPTATEURS: ClassVar[dict[str, dict[str, str]]] = {
        "14": {"move_type": "entry", "cle_date": "date"},
        "15": {"move_type": "entry", "cle_date": "date"},
        "16": {"move_type": "entry", "cle_date": "date"},
        "17": {"move_type": "entry", "cle_date": "date"},
        "18": {"move_type": "entry", "cle_date": "date"},
        "19": {"move_type": "entry", "cle_date": "date"},
    }

    @classmethod
    def vers_payload_version(
        cls, ecriture: EcritureRegroupee, version: str
    ) -> PayloadVersion:
        """Payload account.move de la version cible (montants en centimes)."""
        adapt = cls.ADAPTATEURS.get(version)
        if adapt is None:
            raise ErreurConversion("Version cible %r non supportée." % version)
        return {
            "ref": ecriture["ref_ext"],
            "journal_id": ecriture["journal"],
            "date": ecriture["date"].strftime("%Y-%m-%d"),
            "move_type": adapt["move_type"],
            "line_ids": [
                {
                    "name": ligne.libelle,
                    "account_id": ligne.compte,
                    "debit": ligne.debit,  # centimes int — jamais de float
                    "credit": ligne.credit,
                }
                for ligne in ecriture["lignes"]
            ],
        }

    # --- un saut N -> N+1 ----------------------------------------------------
    def convertir_etape(
        self, canon: Canonique, source: str, cible: str
    ) -> Canonique:
        """Un saut de version : canonique -> payload cible -> canonique.

        Vérifie l'équilibre AVANT et APRÈS ; tolérance 0,00 €.
        """
        self._valider_version(source)
        self._valider_version(cible)
        if not canon.est_equilibre(tolerance=0):
            raise ErreurConversion(
                "Canonique déséquilibré avant %s→%s (D=%s / C=%s centimes) — "
                "tolérance Concordance 0,00 €."
                % (source, cible, canon.total_debit, canon.total_credit)
            )
        ecritures = self._regrouper(canon)
        sortie = Canonique()
        for e in ecritures:
            payload = self.vers_payload_version(e, cible)
            for ligne in payload["line_ids"]:
                sortie.ajouter(
                    LigneEcriture(
                        journal_code=str(payload["journal_id"]),
                        ecriture_num=payload["ref"],
                        date_ecriture=date.fromisoformat(payload["date"]),
                        compte=ligne["account_id"],
                        libelle=ligne["name"],
                        debit=ligne["debit"],
                        credit=ligne["credit"],
                        version_source=cible,
                    )
                )
        if not sortie.est_equilibre(tolerance=0):
            raise ErreurConversion(
                "Canonique déséquilibré après %s→%s — tolérance Concordance "
                "0,00 €." % (source, cible)
            )
        self.guardian.tracer(
            "odoo_conversion",
            "etape",
            "%s->%s lignes=%s" % (source, cible, len(sortie)),
        )
        return sortie

    # --- chaîne complète -----------------------------------------------------
    @staticmethod
    def _regrouper(canon: Canonique) -> list[EcritureRegroupee]:
        """Écritures du canonique, référencées par leur numéro."""
        return regrouper_ecritures(canon, False, ErreurConversion)

    def convertir_chainee(
        self,
        canon: Canonique,
        source: str = "14",
        cible: str = "19",
        dry_run: bool = True,
    ) -> RapportConversion:
        """Chaîne complète 14→15→…→cible.

        Retourne un rapport détaillé par saut.

        dry_run=True (défaut) : rien n'est injecté dans une base Odoo ;
        seul le canonique converti et le rapport sont produits.
        """
        sauts = self.chemin_de_versions(source, cible)
        etapes: list[EtapeConversion] = []
        courant = canon
        for src, dst in sauts:
            avant = len(courant)
            courant = self.convertir_etape(courant, src, dst)
            etapes.append(
                {
                    "saut": "%s→%s" % (src, dst),
                    "nb_lignes_avant": avant,
                    "nb_lignes_apres": len(courant),
                    "equilibre": True,
                }
            )
        rapport: RapportConversion = {
            "source": source,
            "cible": cible,
            "mode": "dry-run" if dry_run else "production",
            "etapes": etapes,
            "nb_lignes_final": len(courant),
            "version_source_final": cible,
            "canonique": courant,
        }
        # Invariants : montants en centimes inchangés de bout en bout
        if (
            courant.total_debit != canon.total_debit
            or courant.total_credit != canon.total_credit
        ):
            raise ErreurConversion(
                "Invariant violé : les totaux en centimes ont changé "
                "(%s/%s -> %s/%s)."
                % (
                    canon.total_debit,
                    canon.total_credit,
                    courant.total_debit,
                    courant.total_credit,
                )
            )
        self.guardian.tracer(
            "odoo_conversion",
            "chaine",
            "%s->%s sauts=%s mode=%s"
            % (source, cible, len(sauts), rapport["mode"]),
        )
        return rapport
