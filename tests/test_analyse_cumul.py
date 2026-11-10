# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Soldes cumulés, rôles de comptes et doublons CABA (ADR-0017).

Données entièrement fictives (Client A, Tiers 1…) : elles reproduisent les
cas réels qui ont motivé l'ADR-0017 (historique comptabilisé, à-nouveaux en
brouillon), sans aucune donnée de client (dépôt public).
"""

import os
import tempfile
import unittest
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from core.analyser import analyser
from core.odoo_source import (
    TYPES_AFFICHAGE,
    ConfigurationComptable,
    Enregistrement,
    SourceXmlRpcOdoo17,
    balance_depuis_lignes,
    balance_tiers_depuis_lignes,
    roles_configuration,
)
from core.passerelle import analyser_source
from core.roles_comptes import (
    SOURCE_COMPORTEMENT,
    SOURCE_CONFIGURATION,
    SOURCE_LIBELLE,
    SOURCE_PREFIXE,
    SOURCE_TABLE,
    SOURCE_TYPE,
    IndicesRoles,
    ObservateurRoles,
    ConfigAnalyse,
    ErreurRoles,
    RoleCompte,
    lire_configuration,
    role_compte,
    table_du_client,
)
from core.soldes_cumules import debut_exercice
from core.surveillance import Instantane
from tests.outils import RACINE_DEPOT, FauxCommun, FauxObjet
from tests.test_odoo_donnees import ligne

DATE_FIN_PERIODE = date(2026, 10, 20)
DATE_DEBUT_PERIODE = date(2026, 1, 1)
HISTORIQUE = date(2025, 6, 30)
EN_2026 = date(2026, 5, 15)

PLAN = (
    ("101000", "Capital", "equity"),
    ("531000", "Caisse", "asset_cash"),
    ("512100", "Banque 1", "asset_cash"),
    ("512200", "Banque 2", "asset_cash"),
    ("512300", "Paiements entrants en suspens", "asset_current"),
    ("512400", "Paiements sortants en suspens", "asset_current"),
    ("411100", "Clients", "asset_receivable"),
    ("410000", "Clients (ancien plan)", "asset_receivable"),
    ("419100", "Clients - acomptes reçus", "asset_receivable"),
    ("401100", "Fournisseurs", "liability_payable"),
    ("400000", "Fournisseurs (ancien plan)", "liability_payable"),
    ("445710", "TVA collectée (compte Odoo)", "liability_current"),
    ("445720", "TVA collectée (ancien logiciel)", "liability_current"),
    ("445740", "TVA collectée sur encaissements", "liability_current"),
    ("445790", "TVA intracommunautaire due", "liability_current"),
    ("499000", "Compte d'attente", "asset_current"),
    ("641200", "Provision congés payés", "expense"),
    ("706000", "Prestations", "income"),
)

# (id, nom, référence) des tiers fictifs des jeux de test.
TIERS_1 = (1001, "Tiers 1", "T1")
TIERS_2 = (1002, "Tiers 2", "T2")


def config_client_a() -> ConfigAnalyse:
    """Réglages du dépôt avec la table fictive du Client A."""
    return lire_configuration(
        os.path.join(RACINE_DEPOT, "concorde.yaml"),
        os.path.join(RACINE_DEPOT, "roles_clients.exemple.yaml"),
    )


class FabriqueEcritures:
    """Fabrique d'écritures équilibrées (contrepartie sur 10100000)."""

    def __init__(self) -> None:
        """Démarre une liste de lignes vide."""
        self.lignes: list[Enregistrement] = []
        self.numero = 0

    def ajouter(
        self,
        compte: str,
        montant: int,
        jour: date,
        journal: str = "OD",
        etat: str = "posted",
        tiers: tuple[int, str, str] | None = None,
        lettrage: str = "",
    ) -> int:
        """Ajoute une écriture : `montant` (centimes, + débit) sur `compte`.

        Retour : l'identifiant de l'écriture.
        """
        self.numero += 1
        eid = self.numero
        types = {code: type_compte for code, _, type_compte in PLAN}
        commun: dict[str, Any] = {
            "ecriture_id": eid,
            "ecriture": "%s/%s/%04d" % (journal, jour.year, eid),
            "journal_code": journal,
            "etat": etat,
            "date": jour,
            "reference": "R%d" % eid,
        }
        for rang, (code, valeur, partenaire, lettre) in enumerate(
            (
                (compte, montant, tiers, lettrage),
                ("101000", -montant, None, ""),
            )
        ):
            self.lignes.append(
                ligne(
                    ligne_id=eid * 10 + rang,
                    compte=code,
                    compte_type=types[code],
                    tiers_id=partenaire[0] if partenaire else None,
                    tiers_nom=partenaire[1] if partenaire else "",
                    tiers_ref=partenaire[2] if partenaire else "",
                    debit=max(valeur, 0),
                    credit=max(-valeur, 0),
                    lettrage=lettre,
                    **commun,
                )
            )
        return eid


# Configuration Odoo du Client A fictif (ce que lirait le connecteur Odoo).
CONFIGURATION_CLIENT_A: ConfigurationComptable = {
    "journaux": [
        ("bank", "512100", ""),
        ("bank", "512200", ""),
        ("cash", "531000", ""),
        ("sale", "706000", ""),
    ],
    "comptes_paiement": ["512300", "512400"],
    "societe": {"account_journal_suspense_account_id": "499000"},
    "repartitions": [
        ("sale", 100.0, "445710"),
        ("purchase", -100.0, "445790"),
    ],
    "transitions": [("sale", "445740")],
}


class SourceSimulee:
    """Source Odoo 17 simulée, calculée sur une liste de lignes.

    Les balances et soldes passent par les fonctions de regroupement de
    core.odoo_source, comme la source XML-RPC.
    """

    nature = "sql"
    societe = 1

    def __init__(
        self,
        lignes: Sequence[Enregistrement],
        base: str = "client_a_preproduction",
        nom_societe: str = "Société A",
        configuration: ConfigurationComptable | None = CONFIGURATION_CLIENT_A,
    ) -> None:
        """Garde les lignes, la base, la société et la configuration Odoo.

        configuration None : logiciel dont on ne lit pas la configuration
        (FEC déposé, par exemple).
        """
        self._lignes = list(lignes)
        self.base = base
        self.nom_societe = nom_societe
        self.configuration = configuration
        self.comptes_plan = [
            {
                "id": rang,
                "code": code,
                "libelle": libelle,
                "type": type_compte,
                "lettrable": type_compte.startswith(("asset_r", "liab")),
                "deprecie": False,
            }
            for rang, (code, libelle, type_compte) in enumerate(PLAN)
        ]

    def societe_info(self) -> Enregistrement:
        """Identité de la société simulée."""
        return {
            "id": 1,
            "nom": self.nom_societe,
            "siren": "",
            "tva": "",
            "devise": "EUR",
        }

    def parametres_comptables(self) -> Enregistrement:
        """Exercice civil, sans ouverture déclarée ni journal CABA."""
        return {
            "fin_exercice_mois": 12,
            "fin_exercice_jour": 31,
            "ouverture_id": None,
            "journal_caba": "",
        }

    def comptes(self) -> list[Enregistrement]:
        """Plan comptable simulé."""
        return self.comptes_plan

    def journaux(self) -> list[Enregistrement]:
        """Journaux présents dans les lignes."""
        return [
            {"id": 0, "code": code, "libelle": code, "type": "general"}
            | {"actif": True}
            for code in sorted(
                {
                    ligne_simulee["journal_code"]
                    for ligne_simulee in self._lignes
                }
            )
        ]

    def tiers(self) -> list[Enregistrement]:
        """Aucun tiers détaillé (contrôles de tiers hors sujet ici)."""
        return []

    def _filtrer(
        self, debut: date | None, fin: date | None, etats: Iterable[str]
    ) -> list[Enregistrement]:
        """Lignes des états et de la période donnés (bornes comprises)."""
        return [
            ligne_simulee
            for ligne_simulee in self._lignes
            if ligne_simulee["etat"] in etats
            and (debut is None or ligne_simulee["date"] >= debut)
            and (fin is None or ligne_simulee["date"] <= fin)
        ]

    def lignes(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
        comptes: Iterable[str] | None = None,
        ecriture: int | None = None,
    ) -> list[Enregistrement]:
        """Lignes filtrées comme la vraie source."""
        codes = set(comptes) if comptes else None
        return [
            ligne_simulee
            for ligne_simulee in self._filtrer(debut, fin, etats)
            if (codes is None or ligne_simulee["compte"] in codes)
            and (ecriture is None or ligne_simulee["ecriture_id"] == ecriture)
        ]

    def balance(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Balance de la période."""
        return balance_depuis_lignes(
            self.comptes_plan, self._filtrer(debut, fin, etats)
        )

    def balance_tiers(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Soldes par tiers des comptes clients et fournisseurs."""
        return balance_tiers_depuis_lignes(self._filtrer(debut, fin, etats))

    def soldes(
        self, depuis: date | None = None, jusqu_au: date | None = None
    ) -> list[Enregistrement]:
        """Soldes comptabilisés par (compte, tiers)."""
        return balance_tiers_depuis_lignes(
            self._filtrer(depuis, jusqu_au, ("posted",)), None
        )

    def ecritures_ouverture(
        self, journaux: Sequence[str], fin: date | None = None
    ) -> list[Enregistrement]:
        """Écritures des journaux d'à-nouveaux (validées ou brouillons)."""
        vues: dict[int, Enregistrement] = {}
        for ligne_simulee in self._filtrer(None, fin, ("posted", "draft")):
            if ligne_simulee["journal_code"] in journaux:
                vues[ligne_simulee["ecriture_id"]] = {
                    "id": ligne_simulee["ecriture_id"],
                    "nom": ligne_simulee["ecriture"],
                    "date": ligne_simulee["date"],
                    "etat": ligne_simulee["etat"],
                    "journal": ligne_simulee["journal_code"],
                }
        return sorted(
            vues.values(),
            key=lambda ouverture: (ouverture["date"], ouverture["id"]),
        )

    def configuration_comptable(self) -> dict[str, str]:
        """Rôles tirés de la configuration simulée ({} sans configuration)."""
        if self.configuration is None:
            return {}
        return roles_configuration(self.configuration)

    def nombre_lignes_avant(self, jour: date) -> int:
        """Nombre de lignes comptabilisées avant `jour`."""
        return sum(
            1
            for ligne_simulee in self._lignes
            if ligne_simulee["etat"] == "posted"
            and ligne_simulee["date"] < jour
        )

    def factures(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted", "draft", "cancel"),
    ) -> list[Enregistrement]:
        """Aucune facture (hors sujet ici)."""
        return []

    def ecriture(self, ident: int | str) -> list[Enregistrement]:
        """Une écriture et ses lignes, tous états confondus."""
        return self.lignes(
            etats=("posted", "draft", "cancel"), ecriture=int(ident)
        )

    def verrous(self) -> dict[str, date | None]:
        """Aucune date de verrouillage."""
        return {"periode": None, "exercice": None, "tva": None}

    def instantane(self) -> Instantane:
        """Photo minimale de la base simulée."""
        return {"ecritures": {}, "comptes": {}, "verrous": {}}

    def noms_analytiques(self) -> dict[int, str]:
        """Aucun compte analytique."""
        return {}

    def fermer(self) -> None:
        """Rien à fermer."""


def jeu_client_a(an_comptabilise: bool = False) -> FabriqueEcritures:
    """Client A fictif au 20/10/2026, historique 2025 comptabilisé.

    Paramètres : an_comptabilise — True pour simuler l'à-nouveaux du
    01/01/2026 comptabilisé (il reprend alors les soldes 2025) ; sinon il
    reste en brouillon.
    """
    jeu = FabriqueEcritures()
    # Historique 2025 comptabilisé.
    jeu.ajouter("531000", 50000, HISTORIQUE)
    jeu.ajouter("512200", 30000000, HISTORIQUE)
    for rang, montant in enumerate([500000] * 8 + [234567]):
        jeu.ajouter(
            "512300",
            montant,
            date(2025, 3 + rang, 1),
            "BNK1",
            tiers=(
                101 + rang % 7,
                "Tiers suspens %d" % (rang % 7),
                "S%d" % rang,
            ),
        )
    jeu.ajouter("411100", 15000000, HISTORIQUE, "VEN", tiers=TIERS_1)
    jeu.ajouter("401100", -50000, HISTORIQUE, "ACH", tiers=TIERS_2)
    jeu.ajouter("445710", -10000000, HISTORIQUE, "CABA")
    jeu.ajouter("641200", 3000000, HISTORIQUE)  # exercice 2025 : ignoré
    jeu.ajouter("706000", -5000000, HISTORIQUE)  # exercice 2025 : ignoré
    # À-nouveaux du 01/01/2026.
    etat_an = "posted" if an_comptabilise else "draft"
    if an_comptabilise:
        for compte, montant, tiers in (
            ("531000", 50000, None),
            ("512200", 30000000, None),
            ("512300", 4234567, None),
            ("411100", 15000000, TIERS_1),
            ("401100", -50000, TIERS_2),
            ("445710", -10000000, None),
        ):
            jeu.ajouter(
                compte, montant, DATE_DEBUT_PERIODE, "AN", etat_an, tiers
            )
    else:
        jeu.ajouter("512100", 1500000, DATE_DEBUT_PERIODE, "AN", etat_an)
    # Mouvements 2026.
    jeu.ajouter("531000", -12000, EN_2026, "CAISS")
    jeu.ajouter("512100", -8000000, EN_2026, "BNK1")
    jeu.ajouter("512200", -20000000, EN_2026, "BNK2")
    jeu.ajouter("512300", -150000, EN_2026, "BNK1", lettrage="P1")
    jeu.ajouter(
        "512400", -6000000, EN_2026, "BNK1", tiers=(108, "Tiers 8", "T8")
    )
    jeu.ajouter("411100", -12000000, EN_2026, "BNK1", tiers=TIERS_1)
    jeu.ajouter("401100", 9000000, EN_2026, "BNK1", tiers=TIERS_2)
    jeu.ajouter("445710", -60000000, EN_2026, "CABA")
    jeu.ajouter("445720", 45000000, EN_2026, "TVA")
    jeu.ajouter("445740", 2000000, EN_2026, "TVA")
    jeu.ajouter("641200", -500000, EN_2026, "SAL")
    jeu.ajouter("706000", 100000, EN_2026, "VEN")
    jeu.ajouter("410000", -50000, EN_2026, "BNK1", tiers=(3, "Tiers 3", "T3"))
    jeu.ajouter("400000", 70000, EN_2026, "BNK1", tiers=(4, "Tiers 4", "T4"))
    jeu.ajouter("419100", -80000, EN_2026, "BNK1", tiers=(5, "Tiers 5", "T5"))
    jeu.ajouter("499000", 12345, EN_2026)
    return jeu


def analyse(
    source: SourceSimulee, config: ConfigAnalyse | None = None
) -> dict[str, Any]:
    """Analyse de la source simulée du 01/01/2026 au 20/10/2026."""
    return analyser_source(
        source,
        DATE_DEBUT_PERIODE,
        DATE_FIN_PERIODE,
        config=config or config_client_a(),
        aujourd_hui=date(2026, 11, 10),
    )


def elements_du_constat(rapport: dict[str, Any], code: str) -> list[str]:
    """Éléments du constat `code` ([] s'il est absent)."""
    for constat_lu in rapport["constats"]:
        if constat_lu["code"] == code:
            elements: list[str] = constat_lu["elements"]
            return elements
    return []


def niveau(rapport: dict[str, Any], code: str) -> str:
    """Niveau du constat `code` ('' s'il est absent)."""
    return next(
        (
            constat_lu["niveau"]
            for constat_lu in rapport["constats"]
            if constat_lu["code"] == code
        ),
        "",
    )


def codes_en_tete(elements: Sequence[str]) -> list[str]:
    """Numéros de compte en tête des éléments d'un constat."""
    return [element.split(" ", 1)[0] for element in elements]


class TestClientA(unittest.TestCase):
    """Client A fictif, cumul au 20/10/2026 : historique 2025 comptabilisé,
    à-nouveaux 2026 en brouillon (mêmes cas que le dossier réel qui a
    motivé l'ADR-0017)."""

    rapport: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        """Analyse le Client A une seule fois."""
        cls.rapport = analyse(SourceSimulee(jeu_client_a().lignes))

    def test_caisse_redevenue_debitrice(self) -> None:
        """531000 : −120,00 sur 2026, +500,00 en 2025 → 380,00 D."""
        self.assertEqual(
            elements_du_constat(self.rapport, "CAISSE_CREDITRICE"), []
        )
        self.assertNotEqual(self.rapport["statut"], "bloquant")

    def test_client_explique_par_historique(self) -> None:
        """Tiers 1 : −120 000,00 en 2026 + 150 000,00 en 2025 = 30 000,00 D."""
        self.assertFalse(
            [
                element
                for element in elements_du_constat(
                    self.rapport, "CLIENT_CREDITEUR"
                )
                if "Tiers 1 " in element
            ]
        )

    def test_fournisseur_toujours_debiteur(self) -> None:
        """Tiers 2 : −500,00 en 2025 + 90 000,00 en 2026 = 89 500,00 D."""
        self.assertIn(
            "401100 — Tiers 2 (T2) [fournisseur, table client] : "
            "période 90000,00 D / cumul 89500,00 D",
            elements_du_constat(self.rapport, "FOURNISSEUR_DEBITEUR"),
        )

    def test_banques(self) -> None:
        """512100 reste créditrice (ouverture dans l'à-nouveaux en
        brouillon) ; 512200 : 300 000,00 − 200 000,00 = 100 000,00 D ;
        512300 et 512400 ne sont pas des banques."""
        self.assertEqual(
            elements_du_constat(self.rapport, "BANQUE_CREDITRICE"),
            [
                "512100 Banque 1 [banque, table client] : "
                "période 80000,00 C / cumul 80000,00 C"
            ],
        )

    def test_paiements_en_suspens(self) -> None:
        """512300 (40 845,67 D) et 512400 (60 000,00 C) : lignes non
        lettrées, plus anciennes d'abord (9 paiements 2025, 7 tiers)."""
        elements = elements_du_constat(
            self.rapport, "PAIEMENT_EN_SUSPENS_NON_SOLDE"
        )
        entrants = [
            element for element in elements if element.startswith("512300")
        ]
        self.assertEqual(len(entrants), 9)
        self.assertEqual(
            len(
                {element.split("Tiers suspens ")[1][0] for element in entrants}
            ),
            7,
        )
        self.assertIn(
            "[paiement_en_suspens, table client] : "
            "période 1500,00 C / cumul 40845,67 D — 01/03/2025",
            entrants[0],
        )
        self.assertIn("cumul 60000,00 C", elements[-1])
        self.assertEqual(len(elements), 10)
        self.assertEqual(
            niveau(self.rapport, "PAIEMENT_EN_SUSPENS_NON_SOLDE"), "ALERTE"
        )

    def test_groupe_tva_reparti(self) -> None:
        """445710 700 000,00 C, 445720 450 000,00 D, 445740 20 000,00 D :
        groupe 230 000,00 C, réparti, deux comptes de sens contraire."""
        self.assertEqual(
            elements_du_constat(self.rapport, "TVA_COLLECTEE_DEBITRICE"), []
        )
        repartie = elements_du_constat(self.rapport, "TVA_COLLECTEE_REPARTIE")
        self.assertIn("cumul 230000,00 C", repartie[0])
        self.assertEqual(
            repartie[1:],
            [
                "445710 TVA collectée (compte Odoo) "
                "[tva_collectee, table client] : "
                "période 600000,00 C / cumul 700000,00 C",
                "445720 TVA collectée (ancien logiciel) "
                "[tva_collectee, table client] : "
                "période 450000,00 D / cumul 450000,00 D",
                "445740 TVA collectée sur encaissements "
                "[tva_collectee, table client] : "
                "période 20000,00 D / cumul 20000,00 D",
            ],
        )
        contraires = elements_du_constat(
            self.rapport, "TVA_COLLECTEE_SENS_CONTRAIRE"
        )
        self.assertEqual(codes_en_tete(contraires), ["445720", "445740"])
        self.assertTrue(contraires[0].endswith("groupe : 230000,00 C"))

    def test_provision_en_info(self) -> None:
        """641200 : −5 000,00 sur l'exercice, 2025 ignoré → INFO."""
        self.assertEqual(
            elements_du_constat(self.rapport, "CHARGE_PROVISION_CREDITRICE"),
            [
                "641200 Provision congés payés "
                "[charge_provision, table client] : "
                "période 5000,00 C / cumul 5000,00 C"
            ],
        )
        self.assertEqual(
            niveau(self.rapport, "CHARGE_PROVISION_CREDITRICE"), "INFO"
        )
        self.assertEqual(
            elements_du_constat(self.rapport, "CHARGE_CREDITRICE"), []
        )

    def test_produits_depuis_debut_exercice(self) -> None:
        """706000 : +1 000,00 D en 2026 ; le crédit de 2025 (autre
        exercice) n'est pas cumulé, le produit reste débiteur."""
        self.assertEqual(
            elements_du_constat(self.rapport, "PRODUIT_DEBITEUR"),
            [
                "706000 Prestations [produit, account_type] : "
                "période 1000,00 D / cumul 1000,00 D"
            ],
        )

    def test_tiers_par_account_type_et_acomptes(self) -> None:
        """410000 / 400000 : rôle par account_type ; 419 sans alerte."""
        self.assertIn(
            "410000 — Tiers 3 (T3) [client, account_type] : "
            "période 500,00 C / cumul 500,00 C",
            elements_du_constat(self.rapport, "CLIENT_CREDITEUR"),
        )
        self.assertIn(
            "400000 — Tiers 4 (T4) [fournisseur, account_type] : "
            "période 700,00 D / cumul 700,00 D",
            elements_du_constat(self.rapport, "FOURNISSEUR_DEBITEUR"),
        )
        self.assertFalse(
            [
                element
                for element in elements_du_constat(
                    self.rapport, "CLIENT_CREDITEUR"
                )
                if "Tiers 5" in element
            ]
        )

    def test_attente(self) -> None:
        """499000 est un compte d'attente chez le Client A."""
        self.assertEqual(
            codes_en_tete(
                elements_du_constat(self.rapport, "COMPTE_ATTENTE_NON_SOLDE")
            ),
            ["499000"],
        )

    def test_infos_calcul(self) -> None:
        """Mode de calcul, lignes antérieures, à-nouveaux ignoré, rôles."""
        calcul = self.rapport["infos"]["calcul_soldes"]
        self.assertEqual(calcul["mode"], "solde cumulé à la date de fin")
        self.assertIsNone(calcul["comptes_bilan_depuis"])
        self.assertEqual(calcul["comptes_gestion_depuis"], DATE_DEBUT_PERIODE)
        # 2025, comptes de bilan : 15 écritures de 2 lignes (les lignes de
        # 641200 et 706000, comptes de gestion, ne comptent pas).
        self.assertEqual(calcul["lignes_anterieures_prises"], 30)
        self.assertEqual(calcul["a_nouveaux_comptabilises"], [])
        self.assertEqual(len(calcul["a_nouveaux_brouillons_ignores"]), 1)
        self.assertEqual(self.rapport["infos"]["table_roles"], "Client A")
        self.assertEqual(
            self.rapport["infos"]["roles_comptes"]["512100"],
            {"role": "banque", "source": SOURCE_TABLE},
        )
        ouverture = elements_du_constat(
            self.rapport, "OUVERTURE_DOUBLE_POSSIBLE"
        )
        self.assertEqual(len(ouverture), 1)
        self.assertIn(
            "brouillon : l'à-nouveaux n'est pas compté", ouverture[0]
        )


class TestOuvertureComptabilisee(unittest.TestCase):
    """À-nouveaux comptabilisé : l'ouverture n'est jamais comptée deux fois."""

    def test_pas_de_double_ouverture(self) -> None:
        """Historique 2025 ET à-nouveaux comptabilisé : mêmes cumuls."""
        rapport = analyse(
            SourceSimulee(jeu_client_a(an_comptabilise=True).lignes)
        )
        self.assertEqual(elements_du_constat(rapport, "CAISSE_CREDITRICE"), [])
        # L'à-nouveaux du 01/01/2026 fait partie des mouvements de la
        # période : période et cumul se confondent.
        self.assertIn(
            "401100 — Tiers 2 (T2) [fournisseur, table client] : "
            "période 89500,00 D / cumul 89500,00 D",
            elements_du_constat(rapport, "FOURNISSEUR_DEBITEUR"),
        )
        self.assertIn(
            "cumul 230000,00 C",
            elements_du_constat(rapport, "TVA_COLLECTEE_REPARTIE")[0],
        )
        calcul = rapport["infos"]["calcul_soldes"]
        self.assertEqual(calcul["comptes_bilan_depuis"], DATE_DEBUT_PERIODE)
        self.assertEqual(calcul["lignes_anterieures_prises"], 0)
        self.assertIn(
            "comptabilisée : l'à-nouveaux est compté",
            elements_du_constat(rapport, "OUVERTURE_DOUBLE_POSSIBLE")[0],
        )

    def test_brouillons_exclus(self) -> None:
        """Une écriture en brouillon ne change aucun cumul."""
        jeu = jeu_client_a()
        jeu.ajouter("531000", -99999999, EN_2026, "CAISS", "draft")
        self.assertEqual(
            elements_du_constat(
                analyse(SourceSimulee(jeu.lignes)), "CAISSE_CREDITRICE"
            ),
            [],
        )


def resume(rapport: dict[str, Any]) -> dict[str, list[str]]:
    """Constats de solde réduits à leurs comptes (sans le texte du rôle)."""
    return {
        constat_lu["code"]: [
            element.split(" [", 1)[0] for element in constat_lu["elements"]
        ]
        for constat_lu in rapport["constats"]
        if constat_lu.get("origine") == "balance"
    }


class TestSansTableClient(unittest.TestCase):
    """Sans table client : rôles déduits automatiquement (ADR-0018)."""

    def test_configuration_odoo_comme_la_table(self) -> None:
        """Test de référence : sans table, mêmes constats qu'avec la table."""
        avec_table = analyse(SourceSimulee(jeu_client_a().lignes))
        sans_table = analyse(
            SourceSimulee(jeu_client_a().lignes, "autre_base", "Autre")
        )
        self.assertIsNone(sans_table["infos"]["table_roles"])
        self.assertEqual(resume(sans_table), resume(avec_table))
        self.assertEqual(
            elements_du_constat(sans_table, "BANQUE_CREDITRICE"),
            [
                "512100 Banque 1 [banque, configuration du logiciel] : "
                "période 80000,00 C / cumul 80000,00 C"
            ],
        )
        self.assertIn(
            "[attente, configuration du logiciel]",
            elements_du_constat(sans_table, "COMPTE_ATTENTE_NON_SOLDE")[0],
        )
        self.assertEqual(
            sans_table["infos"]["roles_deduits"],
            {"configuration_du_logiciel": 9, "comportement_des_ecritures": 0},
        )

    def test_sans_configuration_du_logiciel(self) -> None:
        """Logiciel sans configuration lisible : libellés et préfixes."""
        rapport = analyse(
            SourceSimulee(
                jeu_client_a().lignes,
                "autre_base",
                "Autre",
                configuration=None,
            )
        )
        attendu = resume(analyse(SourceSimulee(jeu_client_a().lignes)))
        self.assertEqual(resume(rapport), attendu)
        suspens = elements_du_constat(rapport, "PAIEMENT_EN_SUSPENS_NON_SOLDE")
        self.assertIn("[paiement_en_suspens, libellé du compte]", suspens[0])
        self.assertIn(
            "[tva_collectee, préfixe]",
            elements_du_constat(rapport, "TVA_COLLECTEE_REPARTIE")[1],
        )
        self.assertIn(
            "[charge_provision, libellé du compte]",
            elements_du_constat(rapport, "CHARGE_PROVISION_CREDITRICE")[0],
        )

    def test_fichier_des_roles_absent(self) -> None:
        """Sans roles_clients.yaml : aucune table, préfixes seuls."""
        config = lire_configuration(
            os.path.join(RACINE_DEPOT, "concorde.yaml"),
            os.path.join(tempfile.mkdtemp(), "roles_clients.yaml"),
        )
        self.assertEqual(config.tables, ())
        rapport = analyse(SourceSimulee(jeu_client_a().lignes), config)
        self.assertIsNone(rapport["infos"]["table_roles"])

    def test_societe_en_secours(self) -> None:
        """Copie renommée : client reconnu par le nom de la société Odoo."""
        rapport = analyse(
            SourceSimulee(jeu_client_a().lignes, "copie_renommee")
        )
        self.assertEqual(rapport["infos"]["table_roles"], "Client A")


class TestRoles(unittest.TestCase):
    """Résolution des rôles et lecture de la table."""

    def test_ordre_de_resolution(self) -> None:
        """Table (code, préfixe le plus long), account_type, préfixe."""
        table = table_du_client(config_client_a(), "client_a_production", "")
        if table is None:
            self.fail("table du Client A absente de l'exemple")
        self.assertEqual(
            role_compte("512300", "asset_current", table),
            RoleCompte("paiement_en_suspens", SOURCE_TABLE),
        )
        self.assertEqual(
            role_compte("419100", "asset_receivable", table),
            RoleCompte("client_acompte", SOURCE_TABLE),
        )
        self.assertEqual(
            role_compte("531000", "asset_cash", table),
            RoleCompte("caisse", SOURCE_TYPE),
        )
        self.assertEqual(
            role_compte("609000", "expense", table),
            RoleCompte("charge_sens_libre", SOURCE_TYPE),
        )
        self.assertEqual(
            role_compte("445711", "liability_current", table),
            RoleCompte("tva_collectee_a_part", SOURCE_PREFIXE),
        )
        self.assertEqual(
            role_compte("512300", "asset_current", None),
            RoleCompte("banque", SOURCE_PREFIXE),
        )
        self.assertEqual(
            role_compte("411000", "asset_receivable", None),
            RoleCompte("client", SOURCE_TYPE),
        )
        self.assertEqual(role_compte("101000", "equity", None).role, "")

    def test_clients_interdits_dans_concorde_yaml(self) -> None:
        """Section clients dans concorde.yaml (dépôt public) : refusée."""
        dossier = tempfile.mkdtemp()
        chemin = os.path.join(dossier, "concorde.yaml")
        with open(chemin, "w", encoding="utf-8") as fichier:
            fichier.write("clients:\n  - nom: X\n")
        with self.assertRaises(ErreurRoles):
            lire_configuration(chemin, os.path.join(dossier, "absent.yaml"))

    def lire(self, analyse: str = "", clients: str = "") -> ConfigAnalyse:
        """Lit une configuration écrite dans deux fichiers temporaires.

        Paramètres : analyse — contenu de concorde.yaml ; clients — contenu
        de roles_clients.yaml.
        """
        dossier = tempfile.mkdtemp()
        chemins = []
        for nom, texte in (
            ("concorde.yaml", analyse),
            ("roles_clients.yaml", clients),
        ):
            chemins.append(os.path.join(dossier, nom))
            with open(chemins[-1], "w", encoding="utf-8") as fichier:
                fichier.write(texte)
        return lire_configuration(chemins[0], chemins[1])

    def test_configuration(self) -> None:
        """Valeurs par défaut, fichiers absents, erreurs jamais ignorées."""
        dossier = tempfile.mkdtemp()
        absent = lire_configuration(
            os.path.join(dossier, "x"), os.path.join(dossier, "y")
        )
        self.assertEqual(absent, ConfigAnalyse(("AN", "RAN"), ()))
        config = self.lire(
            "analyse:\n  seuil_tva_repartie_euros: 5\n",
            "clients:\n  - nom: X\n    bases: [b]\n",
        )
        self.assertEqual(config.tables[0].seuil_tva_repartie, 500)
        self.assertEqual(config.journaux_a_nouveaux, ("AN", "RAN"))
        for analyse, clients in (
            (
                "",
                'clients:\n  - nom: X\n    comptes:\n      "512": banquier\n',
            ),
            ("", "clients:\n  - bases: [b]\n"),
            ("", "clients:\n  - nom: X\n    bases: b\n"),
            ("", "clients:\n  - nom: X\n    prefixes: [a]\n"),
            ("", "clients:\n  - nom: X\n    seuil_tva_repartie_euros: x\n"),
            ("", "clients: x\n"),
            ("", "- a\n"),
            ("analyse:\n  seuil_tva_repartie_euros: -1\n", ""),
            ("analyse: [a]\n", ""),
            ("analyse:\n  journaux_a_nouveaux: AN\n", ""),
            ("clients:\n  - nom: X\n", ""),
        ):
            with self.subTest(analyse=analyse, clients=clients):
                with self.assertRaises(ErreurRoles):
                    self.lire(analyse, clients)


class TestRolesAutomatiques(unittest.TestCase):
    """Rôles déduits du logiciel, des écritures et des libellés."""

    def test_priorites_de_la_configuration(self) -> None:
        """Banque avant suspens avant attente avant TVA ; autoliquidation."""
        roles = roles_configuration(
            {
                "journaux": [("bank", "512100", "471000"), ("cash", "", "")],
                "comptes_paiement": ["512300", "471000"],
                "societe": {
                    "transfer_account_id": "580000",
                    "account_journal_payment_debit_account_id": "512300",
                },
                "repartitions": [
                    ("sale", 100.0, "445710"),
                    ("purchase", 100.0, "445660"),
                    ("purchase", -100.0, "445200"),
                    ("purchase", -100.0, "445710"),
                ],
                "transitions": [("sale", "445740"), ("purchase", "445640")],
            }
        )
        self.assertEqual(
            roles,
            {
                "512100": "banque",
                "512300": "paiement_en_suspens",
                "471000": "paiement_en_suspens",
                "580000": "attente",
                "445710": "tva_collectee",
                "445740": "tva_collectee",
                "445660": "tva_deductible",
                "445640": "tva_deductible",
                "445200": "tva_collectee_a_part",
            },
        )

    def test_ordre_des_sources(self) -> None:
        """Configuration, comportement, libellé, type, préfixe."""
        indices = IndicesRoles({"512300": "banque"}, {"445200": "x"})
        cas = (
            (
                "512300",
                "asset_current",
                "Paiements entrants en suspens",
                RoleCompte("banque", SOURCE_CONFIGURATION),
            ),
            ("445200", "", "", RoleCompte("x", SOURCE_COMPORTEMENT)),
            (
                "499000",
                "asset_current",
                "Suspense Account",
                RoleCompte("attente", SOURCE_LIBELLE),
            ),
            (
                "512400",
                "asset_current",
                "Outstanding Payments",
                RoleCompte("paiement_en_suspens", SOURCE_LIBELLE),
            ),
            (
                "445790",
                "",
                "TVA due intracommunautaire",
                RoleCompte("tva_collectee_a_part", SOURCE_LIBELLE),
            ),
            (
                "641200",
                "expense",
                "Provision congés payés",
                RoleCompte("charge_provision", SOURCE_LIBELLE),
            ),
            (
                "606000",
                "expense",
                "Achats en attente",
                RoleCompte("charge", SOURCE_TYPE),
            ),
            (
                "419100",
                "asset_receivable",
                "Clients",
                RoleCompte("client_acompte", SOURCE_TYPE),
            ),
            (
                "445720",
                "",
                "TVA 20 %",
                RoleCompte("tva_collectee", SOURCE_PREFIXE),
            ),
            (
                "641300",
                "",
                "Primes",
                RoleCompte("charge_provision", SOURCE_PREFIXE),
            ),
            ("101000", "equity", "Capital", RoleCompte("", SOURCE_PREFIXE)),
        )
        for code, type_compte, libelle, attendu in cas:
            with self.subTest(code=code):
                self.assertEqual(
                    role_compte(code, type_compte, None, libelle, indices),
                    attendu,
                )

    def ligne_obs(
        self,
        eid: int,
        compte: str,
        debit: int = 0,
        credit: int = 0,
        lettrage: str = "",
        etat: str = "posted",
    ) -> Enregistrement:
        """Ligne minimale pour l'observateur."""
        return {
            "ecriture_id": eid,
            "compte": compte,
            "debit": debit,
            "credit": credit,
            "lettrage": lettrage,
            "etat": etat,
        }

    def test_autoliquidation_observee(self) -> None:
        """TVA collectée compensée par une déductible du même montant."""
        observateur = ObservateurRoles()
        lignes = []
        for eid in range(1, 4):
            lignes += [
                self.ligne_obs(eid, "445200", credit=2000),
                self.ligne_obs(eid, "445660", debit=2000),
                self.ligne_obs(eid, "445710", credit=500),
            ]
        lignes.append(self.ligne_obs(9, "445200", credit=7, etat="draft"))
        self.assertEqual(len(list(observateur.suivre(lignes))), 10)
        self.assertEqual(
            observateur.roles(), {"445200": "tva_collectee_a_part"}
        )

    def test_compte_de_transit_lettre(self) -> None:
        """512x lettré à plus de moitié : transit ; banque non lettrée."""
        observateur = ObservateurRoles()
        for rang in range(12):
            observateur.voir(
                self.ligne_obs(
                    rang, "512300", 100, lettrage="A" if rang else ""
                )
            )
            observateur.voir(self.ligne_obs(rang, "512100", 100))
        self.assertEqual(
            observateur.roles(), {"512300": "paiement_en_suspens"}
        )


class TestExercice(unittest.TestCase):
    """Début d'exercice lu dans la société Odoo."""

    def test_debut_exercice(self) -> None:
        """Exercice civil, décalé, et fin au 29 février ramenée au 28."""
        self.assertEqual(
            debut_exercice(DATE_FIN_PERIODE, 12, 31), DATE_DEBUT_PERIODE
        )
        self.assertEqual(
            debut_exercice(date(2026, 10, 20), 6, 30), date(2026, 7, 1)
        )
        self.assertEqual(
            debut_exercice(date(2026, 3, 1), 6, 30), date(2025, 7, 1)
        )
        self.assertEqual(
            debut_exercice(date(2027, 1, 5), 2, 29), date(2026, 3, 1)
        )


class TestCaba(unittest.TestCase):
    """Doublons et lignes nulles du journal de TVA sur encaissements."""

    def ecriture(
        self,
        eid: int,
        journal: str = "CABA",
        rapprochement: int | None = None,
        extourne_de: int | None = None,
        montant: int = 1000,
    ) -> list[Enregistrement]:
        """Écriture de deux lignes, même date et même référence."""
        commun: dict[str, Any] = {
            "ecriture_id": eid,
            "ecriture": "%s/2026/%04d" % (journal, eid),
            "journal_code": journal,
            "date": EN_2026,
            "reference": "REF-0001",
            "caba_rapprochement_id": rapprochement,
            "extourne_de_id": extourne_de,
        }
        return [
            ligne(ligne_id=eid * 10, debit=montant, **commun),
            ligne(ligne_id=eid * 10 + 1, credit=montant, **commun),
        ]

    def doublons(self, lignes: list[Enregistrement]) -> list[str]:
        """Éléments DOUBLON_PROBABLE avec CABA comme journal de TVA."""
        rapport = analyser(
            lignes, aujourd_hui=date(2026, 11, 10), journal_caba="CABA"
        ).en_dict()
        return elements_du_constat(rapport, "DOUBLON_PROBABLE")

    def test_reglements_partiels(self) -> None:
        """Rapprochements différents : pas de doublon."""
        self.assertEqual(
            self.doublons(
                self.ecriture(1, rapprochement=7)
                + self.ecriture(2, rapprochement=8)
            ),
            [],
        )

    def test_meme_rapprochement(self) -> None:
        """Même rapprochement : doublon."""
        self.assertEqual(
            self.doublons(
                self.ecriture(1, rapprochement=7)
                + self.ecriture(2, rapprochement=7)
            ),
            ["REF-0001 : CABA/2026/0001, CABA/2026/0002"],
        )

    def test_extourne_ecartee(self) -> None:
        """Écriture + extourne : pas de doublon ; un tiers reste signalé."""
        paire = self.ecriture(1, rapprochement=7) + self.ecriture(
            2, rapprochement=7, extourne_de=1
        )
        self.assertEqual(self.doublons(paire), [])
        self.assertEqual(
            self.doublons(paire + self.ecriture(3, rapprochement=7)), []
        )
        self.assertEqual(
            self.doublons(
                paire
                + self.ecriture(3, rapprochement=7)
                + self.ecriture(4, rapprochement=7)
            ),
            ["REF-0001 : CABA/2026/0003, CABA/2026/0004"],
        )

    def test_sans_rapprochement_et_autres_journaux(self) -> None:
        """Sans rapprochement, et hors CABA : règle inchangée."""
        self.assertEqual(
            len(self.doublons(self.ecriture(1) + self.ecriture(2))), 1
        )
        self.assertEqual(
            len(
                self.doublons(
                    self.ecriture(1, "VEN", 7) + self.ecriture(2, "VEN", 8)
                )
            ),
            1,
        )

    def test_lignes_nulles(self) -> None:
        """Lignes nulles CABA écartées ; les autres ventilées par journal."""
        lignes = (
            self.ecriture(1, montant=0)
            + self.ecriture(2, "41", montant=0)
            + self.ecriture(3, "ACH", montant=0)[:1]
        )
        releve = analyser(
            lignes, aujourd_hui=date(2026, 11, 10), journal_caba="CABA"
        ).en_dict()
        self.assertEqual(
            elements_du_constat(releve, "LIGNE_MONTANT_NUL"),
            [
                "41/2026/0002 (ligne 20) — journal 41",
                "41/2026/0002 (ligne 21) — journal 41",
                "ACH/2026/0003 (ligne 30) — journal ACH",
            ],
        )
        self.assertEqual(
            releve["infos"]["lignes_montant_nul_par_journal"],
            {"41": 2, "ACH": 1},
        )
        self.assertEqual(
            releve["infos"]["lignes_montant_nul_caba_ecartees"], 2
        )


class FauxObjetCumul(FauxObjet):
    """Odoo simulé : domaines relevés, search_count, CABA et ouverture."""

    def __init__(self) -> None:
        """Ajoute un journal CABA, une ouverture et une ligne 2024."""
        super().__init__()
        self.domaines: list[tuple[str, list[Any]]] = []
        self.donnees["account.journal"].append(
            {
                "id": 2,
                "code": "CABA",
                "name": "TVA encaissements",
                "type": "general",
                "active": True,
                "default_account_id": False,
                "suspense_account_id": False,
            }
        )
        societe = self.donnees["res.company"][0]
        societe["account_opening_move_id"] = [5, "VEN/1"]
        societe["tax_cash_basis_journal_id"] = [2, "TVA encaissements"]
        societe["account_journal_suspense_account_id"] = [8, "471000"]
        for ident, code in (
            (3, "512100"),
            (4, "512300"),
            (5, "445710"),
            (6, "445740"),
            (7, "445200"),
            (8, "471000"),
        ):
            self.donnees["account.account"].append(
                {
                    "id": ident,
                    "code": code,
                    "name": code,
                    "account_type": "asset_current",
                    "reconcile": False,
                    "deprecated": False,
                }
            )
        self.donnees["account.journal"].append(
            {
                "id": 3,
                "code": "BNK1",
                "name": "Banque",
                "type": "bank",
                "active": True,
                "default_account_id": [3, "512100"],
                "suspense_account_id": [8, "471000"],
            }
        )
        self.donnees["account.payment.method.line"] = [
            {
                "id": 1,
                "journal_id": [3, "BNK1"],
                "payment_account_id": [4, "x"],
            },
            {
                "id": 2,
                "journal_id": [99, "autre"],
                "payment_account_id": [5, "x"],
            },
        ]
        self.donnees["account.tax"] = [
            {
                "id": 1,
                "type_tax_use": "sale",
                "cash_basis_transition_account_id": [6, "x"],
            },
            {
                "id": 2,
                "type_tax_use": "purchase",
                "cash_basis_transition_account_id": False,
            },
        ]
        self.donnees["account.tax.repartition.line"] = [
            {
                "id": 1,
                "tax_id": [1, "x"],
                "account_id": [5, "x"],
                "repartition_type": "tax",
                "factor_percent": 100.0,
            },
            {
                "id": 2,
                "tax_id": [2, "x"],
                "account_id": [7, "x"],
                "repartition_type": "tax",
                "factor_percent": -100.0,
            },
            {
                "id": 3,
                "tax_id": [1, "x"],
                "account_id": False,
                "repartition_type": "base",
                "factor_percent": 100.0,
            },
        ]
        self.donnees["account.move.line"].append(
            dict(
                self.donnees["account.move.line"][0],
                id=13,
                date="2024-01-01",
            )
        )

    def execute_kw(
        self,
        db: str,
        uid: int,
        cle: str,
        modele: str,
        methode: str,
        args: list[Any],
        kw: dict[str, Any],
    ) -> Any:
        """Relève les domaines ; compte les lignes pour search_count."""
        if methode in ("search_read", "search_count"):
            self.domaines.append((modele, args[0]))
        if methode == "search_count":
            self.appels.append((modele, methode))
            return len(self.donnees[modele])
        return super().execute_kw(db, uid, cle, modele, methode, args, kw)


class TestSourceXmlRpcCumul(unittest.TestCase):
    """Nouvelles lectures de la source XML-RPC (lecture seule)."""

    def setUp(self) -> None:
        """Ouvre la source sur l'Odoo simulé."""
        self.objet = FauxObjetCumul()
        self.source = SourceXmlRpcOdoo17(
            "http://x",
            "b",
            "u",
            "cle",
            proxy_commun=FauxCommun(),
            proxy_objet=self.objet,
        )

    def domaine_lignes(self) -> list[Any]:
        """Domaine de la première lecture des lignes d'écritures."""
        return next(
            releve
            for modele, releve in self.objet.domaines
            if modele == "account.move.line"
        )

    def test_parametres_et_ouverture(self) -> None:
        """Fin d'exercice, ouverture déclarée, code du journal CABA."""
        self.assertEqual(
            self.source.parametres_comptables(),
            {
                "fin_exercice_mois": 12,
                "fin_exercice_jour": 31,
                "ouverture_id": 5,
                "journal_caba": "CABA",
            },
        )
        ouvertures = self.source.ecritures_ouverture(["AN"], DATE_FIN_PERIODE)
        self.assertEqual(
            [
                (ouverture["id"], ouverture["etat"], ouverture["date"])
                for ouverture in ouvertures
            ],
            [(5, "posted", date(2025, 10, 3))],
        )
        self.assertEqual(
            self.source.ecritures_ouverture(["AN"], date(2024, 1, 1)), []
        )

    def test_soldes_filtres_et_lecture_seule(self) -> None:
        """Soldes par (compte, tiers), bornes de date, section/note exclues."""
        soldes = self.source.soldes(date(2025, 1, 1), DATE_FIN_PERIODE)
        self.assertEqual(
            sorted(
                (solde["compte"], solde["debit"], solde["credit"])
                for solde in soldes
            ),
            [("411000", 10010, 0), ("706000", 0, 10010)],
        )
        self.assertEqual(soldes[0]["tiers_nom"], "ACME")
        self.assertEqual(len(self.source.soldes(None, DATE_FIN_PERIODE)), 2)
        self.assertEqual(
            sum(
                solde["lignes"]
                for solde in self.source.soldes(None, DATE_FIN_PERIODE)
            ),
            3,
        )
        domaine_releve = self.domaine_lignes()
        self.assertIn(
            ("display_type", "not in", list(TYPES_AFFICHAGE)), domaine_releve
        )
        self.assertIn(("parent_state", "=", "posted"), domaine_releve)
        self.assertEqual(
            self.source.nombre_lignes_avant(DATE_DEBUT_PERIODE), 3
        )
        self.assertTrue(
            all(
                modele in SourceXmlRpcOdoo17.METHODES_AUTORISEES
                for _, modele in self.objet.appels
            )
        )

    def test_configuration_comptable(self) -> None:
        """Banque, paiements en suspens, attente et TVA lus par l'API."""
        self.assertEqual(
            self.source.configuration_comptable(),
            {
                "512100": "banque",
                "512300": "paiement_en_suspens",
                "471000": "attente",
                "445710": "tva_collectee",
                "445740": "tva_collectee",
                "445200": "tva_collectee_a_part",
            },
        )

    def test_lignes_portent_rapprochement_et_extourne(self) -> None:
        """Les lignes lues portent tax_cash_basis_rec_id et l'extourne."""
        self.objet.donnees["account.move"][0]["tax_cash_basis_rec_id"] = [
            44,
            "x",
        ]
        self.objet.donnees["account.move"][0]["reversed_entry_id"] = [3, "y"]
        premiere = self.source.lignes()[0]
        self.assertEqual(
            (premiere["caba_rapprochement_id"], premiere["extourne_de_id"]),
            (44, 3),
        )
        self.assertIn(
            ("display_type", "not in", list(TYPES_AFFICHAGE)),
            self.domaine_lignes(),
        )


if __name__ == "__main__":
    unittest.main()
