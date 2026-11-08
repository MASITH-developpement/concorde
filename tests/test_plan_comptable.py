# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Plan comptable client (core/plan_comptable.py) : lecture du .xlsx.

Vérifie la détection des en-têtes et de leurs synonymes, la lecture des
comptes (code, intitulé, type Odoo), les lignes ignorées, les doublons,
la déduction prudente du type par la classe PCG et les erreurs
explicites (Marceau : jamais muet, aucun compte inventé).
"""

import os
import tempfile
import unittest
from collections.abc import Sequence
from typing import Optional

from core.mapping import ErreurMapping
from core.plan_comptable import (
    CORRESP_TYPE,
    TYPES_ACCOUNT,
    CompteLu,
    ErreurPlanComptable,
    charger_plan_xlsx,
    dictionnaire_plan,
)
from core.xlsx_ecrire import ecrire_xlsx

# En-têtes usuels d'un plan comptable client (code, intitulé, type).
ENTETES_PLAN = ("Numéro", "Libellé", "Type")

# account_type valides, mesurés dans les images odoo:17 et odoo:18
# (champ account.account.account_type) ; communs aux versions 17 à 20.
TYPES_ODOO_MESURES = frozenset(
    {
        "asset_receivable",
        "asset_cash",
        "asset_current",
        "asset_non_current",
        "asset_prepayments",
        "asset_fixed",
        "liability_payable",
        "liability_credit_card",
        "liability_current",
        "liability_non_current",
        "equity",
        "equity_unaffected",
        "income",
        "income_other",
        "expense",
        "expense_depreciation",
        "expense_direct_cost",
        "off_balance",
    }
)


def classeur_plan(
    entetes: Sequence[str], lignes: Sequence[Sequence[object]]
) -> bytes:
    """Construit un classeur .xlsx d'une feuille et rend ses octets.

    Rôle : fabriquer le fichier tel que l'utilisateur l'uploade.
    Paramètres : entetes, première ligne du classeur ; lignes, lignes de
    cellules suivantes (texte, entier, None pour une cellule vide).
    Retour : contenu binaire du classeur.
    Erreurs : OSError si le dossier temporaire n'est pas inscriptible.
    Usages : tous les tests de lecture de ce fichier.
    """
    with tempfile.TemporaryDirectory() as dossier:
        chemin = os.path.join(dossier, "plan.xlsx")
        ecrire_xlsx(chemin, [("Plan", entetes, lignes)])
        with open(chemin, "rb") as fichier:
            return fichier.read()


def lire_plan(
    entetes: Sequence[str], lignes: Sequence[Sequence[object]]
) -> list[CompteLu]:
    """Construit un classeur puis le lit avec charger_plan_xlsx.

    Rôle : raccourci « fichier uploadé -> comptes lus ».
    Paramètres : entetes et lignes, comme classeur_plan.
    Retour : comptes rendus par charger_plan_xlsx (nom 'plan.xlsx').
    Erreurs : ErreurPlanComptable si le plan est refusé.
    Usages : tests de lecture et de déduction des types.
    """
    return charger_plan_xlsx(classeur_plan(entetes, lignes), "plan.xlsx")


def compte_attendu(code: str, nom: str, type_odoo: Optional[str]) -> CompteLu:
    """Construit le compte attendu en sortie de charger_plan_xlsx.

    Rôle : écrire lisiblement les valeurs attendues.
    Paramètres : code, nom (intitulé) et type_odoo (account_type ou None).
    Retour : dict CompteLu.
    Erreurs : aucune.
    Usages : assertions des tests de lecture.
    """
    return {"code": code, "nom": nom, "type": type_odoo}


def type_lu(type_texte: str, code: str = "512000") -> Optional[str]:
    """Rend le type Odoo déduit pour un compte au type texte donné.

    Rôle : isoler la conversion « texte du client -> account_type ».
    Paramètres : type_texte, valeur de la colonne type ; code, numéro du
    compte (512000 par défaut : aucune déduction par la classe PCG).
    Retour : type du seul compte lu (account_type Odoo ou None).
    Erreurs : ErreurPlanComptable si le plan est refusé.
    Usages : TestTypesComptes.
    """
    comptes = lire_plan(ENTETES_PLAN, [(code, "Compte", type_texte)])
    return comptes[0]["type"]


class TestLecturePlan(unittest.TestCase):
    """Lecture des comptes : en-têtes, synonymes, lignes ignorées."""

    def test_plan_complet_lu_dans_l_ordre(self) -> None:
        """Les comptes sont rendus dans l'ordre du fichier, typés."""
        comptes = lire_plan(
            ENTETES_PLAN,
            [
                ("101300", "Capital souscrit appelé", "Capitaux propres"),
                ("411000", "Clients", "Client"),
                ("607000", "Achats de marchandises", "Charge"),
            ],
        )
        self.assertEqual(
            comptes,
            [
                compte_attendu("101300", "Capital souscrit appelé", "equity"),
                compte_attendu("411000", "Clients", "asset_receivable"),
                compte_attendu("607000", "Achats de marchandises", "expense"),
            ],
        )

    def test_synonymes_anglais_et_colonnes_dans_le_desordre(self) -> None:
        """« Account Name » / « Account Code » sont reconnus, ordre libre."""
        comptes = lire_plan(
            ("Account Name", "Account Code"),
            [("Sales of goods", "707000")],
        )
        self.assertEqual(
            comptes, [compte_attendu("707000", "Sales of goods", None)]
        )

    def test_en_tete_sous_un_titre(self) -> None:
        """L'en-tête est cherché sous des lignes de titre."""
        comptes = lire_plan(
            ("Plan comptable 2026",),
            [
                (),
                ("Compte", "Intitulé"),
                ("401000", "Fournisseurs"),
            ],
        )
        self.assertEqual(
            comptes,
            [compte_attendu("401000", "Fournisseurs", "liability_payable")],
        )

    def test_code_numerique_converti_en_texte(self) -> None:
        """Un code saisi en nombre (ou « 10130000.0 ») devient un texte."""
        comptes = lire_plan(
            ("Code", "Nom"),
            [(10130000, "Capital"), ("10140000.0", "Capital non appelé")],
        )
        self.assertEqual(
            [compte["code"] for compte in comptes], ["10130000", "10140000"]
        )

    def test_espaces_retires(self) -> None:
        """Les espaces autour du code et de l'intitulé sont retirés."""
        comptes = lire_plan(("Code", "Nom"), [("  512000 ", "  Banque  ")])
        self.assertEqual(comptes, [compte_attendu("512000", "Banque", None)])

    def test_lignes_sans_code_ignorees(self) -> None:
        """Lignes vides ou de présentation (sans code) : sautées."""
        comptes = lire_plan(
            ("Code", "Libellé"),
            [
                (None, "Classe 6 — Charges"),
                (),
                ("606100", "Fournitures non stockables"),
                ("   ", "Sous-total"),
            ],
        )
        self.assertEqual(
            comptes,
            [compte_attendu("606100", "Fournitures non stockables", None)],
        )

    def test_doublon_identique_accepte(self) -> None:
        """Un compte répété à l'identique n'est pas une contradiction."""
        comptes = lire_plan(
            ("Code", "Libellé"),
            [("706000", "Prestations"), ("706000", "Prestations")],
        )
        self.assertEqual(
            dictionnaire_plan(comptes), {"706000": ("Prestations", None)}
        )

    def test_doublon_identique_rendu_une_seule_fois(self) -> None:
        """Un compte répété à l'identique n'est rendu qu'une fois."""
        comptes = lire_plan(
            ("Code", "Libellé"),
            [
                ("706000", "Prestations"),
                ("411000", "Clients"),
                ("706000", "Prestations"),
            ],
        )
        self.assertEqual(
            comptes,
            [
                compte_attendu("706000", "Prestations", None),
                compte_attendu("411000", "Clients", "asset_receivable"),
            ],
        )

    def test_en_tetes_avec_de_compte(self) -> None:
        """« Numéro de compte », « Intitulé de compte », « Type de compte »."""
        comptes = lire_plan(
            ("Numéro de compte", "Intitulé de compte", "Type de compte"),
            [("706000", "Ventes", "Produit")],
        )
        self.assertEqual(
            comptes, [compte_attendu("706000", "Ventes", "income")]
        )

    def test_synonymes_de_compte(self) -> None:
        """« Code de compte », « Libellé de compte », « Nom de compte »."""
        for entete_code, entete_intitule in (
            ("Code de compte", "Libellé de compte"),
            ("Numéro de compte", "Nom de compte"),
        ):
            with self.subTest(entete_code=entete_code):
                comptes = lire_plan(
                    (entete_code, entete_intitule), [("706000", "Ventes")]
                )
                self.assertEqual(
                    comptes, [compte_attendu("706000", "Ventes", None)]
                )


class TestTypesComptes(unittest.TestCase):
    """Type Odoo : colonne type du client, sinon classe PCG évidente."""

    def test_libelles_francais(self) -> None:
        """Les libellés humains français donnent le type Odoo 17."""
        attendus = {
            "Client": "asset_receivable",
            "Fournisseur": "liability_payable",
            "Actif": "asset_current",
            "Actif circulant": "asset_current",
            "Immobilisation": "asset_fixed",
            "Passif": "liability_current",
            "Passif circulant": "liability_current",
            "Capitaux propres": "equity",
            "Produit": "income",
            "Revenu": "income",
            "Charge": "expense",
            "Dépense": "expense",
        }
        for type_texte, type_odoo in attendus.items():
            with self.subTest(type_texte=type_texte):
                self.assertEqual(type_lu(type_texte), type_odoo)

    def test_types_odoo_ecrits_tels_quels(self) -> None:
        """Un account_type Odoo 17 déjà renseigné est conservé."""
        for type_odoo in (
            "asset_receivable",
            "liability_payable",
            "asset_current",
            "liability_current",
            "equity",
            "income",
            "expense",
        ):
            with self.subTest(type_odoo=type_odoo):
                self.assertEqual(type_lu(type_odoo), type_odoo)

    def test_tous_types_odoo_ecrits_tels_quels(self) -> None:
        """Chaque account_type Odoo valide (avec « _ ») est rendu tel quel."""
        for type_odoo in sorted(TYPES_ODOO_MESURES):
            with self.subTest(type_odoo=type_odoo):
                self.assertEqual(type_lu(type_odoo), type_odoo)

    def test_types_odoo_exactement_la_liste_mesuree(self) -> None:
        """TYPES_ACCOUNT est exactement la liste mesurée dans Odoo."""
        self.assertEqual(set(TYPES_ACCOUNT), set(TYPES_ODOO_MESURES))

    def test_correspondances_vers_types_odoo_valides(self) -> None:
        """Chaque correspondance de libellé rend un account_type valide."""
        for libelle, type_odoo in CORRESP_TYPE.items():
            with self.subTest(libelle=libelle):
                self.assertIn(type_odoo, TYPES_ODOO_MESURES)

    def test_libelles_specifiques(self) -> None:
        """Le libellé le plus spécifique gagne sur une clé plus courte."""
        attendus = {
            "Banque": "asset_cash",
            "Caisse": "asset_cash",
            "Carte de crédit": "liability_credit_card",
            "Hors bilan": "off_balance",
            "Non affecté": "equity_unaffected",
            "Résultat non affecté": "equity_unaffected",
            "Immobilisations": "asset_fixed",
            "Actif non courant": "asset_non_current",
            "Actif non circulant": "asset_non_current",
            "Passif non courant": "liability_non_current",
            "Charges constatées d'avance": "asset_prepayments",
            "Amortissement": "expense_depreciation",
            "Dotation aux amortissements": "expense_depreciation",
            "Coût direct": "expense_direct_cost",
            "Autres produits": "income_other",
        }
        for type_texte, type_odoo in attendus.items():
            with self.subTest(type_texte=type_texte):
                self.assertEqual(type_lu(type_texte), type_odoo)

    def test_anciens_alias_anglais(self) -> None:
        """Les anciens alias anglais donnent un account_type valide."""
        attendus = {
            "receivable": "asset_receivable",
            "payable": "liability_payable",
            "bank": "asset_cash",
            "cash": "asset_cash",
            "credit_card": "liability_credit_card",
            "off_sheet": "off_balance",
            "unaffected": "equity_unaffected",
        }
        for type_texte, type_odoo in attendus.items():
            with self.subTest(type_texte=type_texte):
                self.assertEqual(type_lu(type_texte), type_odoo)

    def test_libelle_ambigu_non_devine(self) -> None:
        """Deux correspondances de types différents : None, jamais deviné."""
        self.assertIsNone(type_lu("Charges et produits", code="471000"))

    def test_type_inconnu_sans_classe_evidente(self) -> None:
        """Type illisible et classe non évidente : None, jamais deviné."""
        self.assertIsNone(type_lu("Divers", code="471000"))

    def test_type_vide_classes_clients(self) -> None:
        """Sans type, 411 / 416 / 419 (zéros de tête ignorés) : client."""
        for code in ("411100", "416000", "419000", "00411000"):
            with self.subTest(code=code):
                self.assertEqual(type_lu("", code=code), "asset_receivable")

    def test_type_vide_classes_fournisseurs(self) -> None:
        """Sans type, 401 / 408 / 409 : fournisseur."""
        for code in ("401100", "408000", "409000"):
            with self.subTest(code=code):
                self.assertEqual(type_lu("", code=code), "liability_payable")

    def test_type_illisible_classe_client(self) -> None:
        """Type non reconnu : la classe PCG évidente s'applique."""
        self.assertEqual(type_lu("Tiers", code="411000"), "asset_receivable")

    def test_sans_colonne_type(self) -> None:
        """Sans colonne type : classe évidente, sinon None."""
        comptes = lire_plan(
            ("Code", "Intitulé"),
            [("401000", "Fournisseurs"), ("445660", "TVA déductible")],
        )
        self.assertEqual(
            [compte["type"] for compte in comptes],
            ["liability_payable", None],
        )

    def test_colonne_nature_reconnue(self) -> None:
        """La colonne « Nature » est un synonyme de la colonne type."""
        comptes = lire_plan(
            ("Code", "Intitulé", "Nature"), [("706000", "Ventes", "Produit")]
        )
        self.assertEqual(comptes[0]["type"], "income")


class TestErreursPlan(unittest.TestCase):
    """Erreurs explicites : le plan refusé dit pourquoi."""

    def verifier_refus(
        self,
        entetes: Sequence[str],
        lignes: Sequence[Sequence[object]],
        extrait_message: str,
    ) -> None:
        """Vérifie que le plan est refusé avec un message explicite.

        Rôle : assertion commune des refus de plan comptable.
        Paramètres : entetes et lignes du classeur ; extrait_message,
        texte devant figurer dans le message d'erreur.
        Retour : aucun.
        Erreurs : AssertionError si le plan est accepté ou si le message
        ne nomme ni le fichier ni la cause.
        Usages : tests de cette classe.
        """
        with self.assertRaises(ErreurPlanComptable) as contexte:
            lire_plan(entetes, lignes)
        message = str(contexte.exception)
        self.assertIn("Fichier du plan comptable 'plan.xlsx'", message)
        self.assertIn(extrait_message, message)

    def test_en_tete_introuvable(self) -> None:
        """Aucune colonne code / intitulé : refus explicite."""
        self.verifier_refus(
            ("Débit", "Crédit"), [("10", "20")], "en-tête introuvable"
        )

    def test_en_tete_sans_intitule(self) -> None:
        """Une colonne code seule ne suffit pas."""
        self.verifier_refus(
            ("Code", "Solde"), [("512000", "10")], "en-tête introuvable"
        )

    def test_en_tete_au_dela_de_cinquante_lignes(self) -> None:
        """L'en-tête n'est cherché que dans les 50 premières lignes."""
        lignes: list[Sequence[object]] = [("titre",)] * 50
        lignes.append(("Code", "Intitulé"))
        lignes.append(("512000", "Banque"))
        self.verifier_refus(("Rapport",), lignes, "en-tête introuvable")

    def test_compte_sans_intitule(self) -> None:
        """Un code sans intitulé est refusé (libellé jamais deviné)."""
        self.verifier_refus(
            ("Code", "Intitulé"),
            [("512000", "Banque"), ("530000", None)],
            "compte 530000 sans intitulé",
        )

    def test_doublon_contradictoire(self) -> None:
        """Un même code avec deux intitulés différents est refusé."""
        self.verifier_refus(
            ("Code", "Intitulé"),
            [("512000", "Banque A"), ("512000", "Banque B")],
            "compte 512000 défini plusieurs fois",
        )

    def test_doublon_types_differents(self) -> None:
        """Même code et intitulé, types différents : les types sont cités."""
        self.verifier_refus(
            ("Code", "Intitulé", "Type"),
            [("512000", "Banque", "Banque"), ("512000", "Banque", "Actif")],
            "compte 512000 défini plusieurs fois avec des types différents "
            "('asset_cash' / 'asset_current')",
        )

    def test_aucun_compte_sous_l_en_tete(self) -> None:
        """En-tête présent mais aucune ligne de compte : refus."""
        self.verifier_refus(
            ("Code", "Intitulé"), [(None, "Total")], "aucun compte trouvé"
        )

    def test_fichier_non_xlsx(self) -> None:
        """Un contenu non-zip est refusé au nom du plan comptable."""
        with self.assertRaises(ErreurMapping) as contexte:
            charger_plan_xlsx(b"Code;Intitule\n512000;Banque\n", "plan.csv")
        message = str(contexte.exception)
        self.assertIn("Fichier du plan comptable 'plan.csv'", message)
        self.assertIn("contenu non-xlsx", message)

    def test_fichier_absent(self) -> None:
        """Aucun contenu (None) : refus explicite « fichier vide »."""
        with self.assertRaises(ErreurMapping) as contexte:
            charger_plan_xlsx(None)
        self.assertIn("fichier vide", str(contexte.exception))


class TestDictionnairePlan(unittest.TestCase):
    """dictionnaire_plan : liste de comptes -> {code: (nom, type)}."""

    def test_conversion(self) -> None:
        """Chaque compte devient une entrée code -> (nom, type)."""
        comptes = [
            compte_attendu("411000", "Clients", "asset_receivable"),
            compte_attendu("512000", "Banque", None),
        ]
        self.assertEqual(
            dictionnaire_plan(comptes),
            {
                "411000": ("Clients", "asset_receivable"),
                "512000": ("Banque", None),
            },
        )

    def test_liste_vide(self) -> None:
        """Aucun compte : dictionnaire vide."""
        self.assertEqual(dictionnaire_plan([]), {})


if __name__ == "__main__":
    unittest.main()
