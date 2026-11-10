# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du mapping des comptes Quadra -> Odoo (core/mapping.py).

Couvre le chargement JSON / paires / dict, la lecture du classeur
« Mapping Quadra Odoo.xlsx » (construit en mémoire avec zipfile ou écrit
par core.xlsx_ecrire), et l'application du mapping au journal canonique.
Les tests déjà présents dans tests/test_moteur.py (TestMapping) ne sont pas
repris ici.
"""

import json
import os
import tempfile
import unittest
from datetime import date
from typing import cast

from core.canonical import Canonique, LigneEcriture
from core.mapping import (
    ErreurMapping,
    SourceMapping,
    _compte_txt,
    _index_colonne,
    _norm_entete,
    charger_mapping,
    charger_mapping_xlsx,
    lire_feuille_xlsx,
    mapper_comptes,
    valeurs_cellules_ligne,
)
from core.xlsx_ecrire import ecrire_xlsx
from tests.classeurs_xlsx import (
    CHEMIN_PREMIERE_FEUILLE,
    ESPACE_TABLEUR,
    ValeurCellule,
    archive_xlsx,
    cellule_brute,
    cellule_texte,
    classeur_feuilles_xml,
    feuille_depuis_lignes,
    feuille_xml,
    ligne_valeurs,
    ligne_xml,
    relations_classeur_xml,
)

# En-tête standard du fichier client « Mapping Quadra Odoo ».
ENTETE_MAPPING_CLIENT = ("Numéro", "Intitulé", "Odoo Acct")


def feuille_tableau(lignes: list[tuple[str, ...]]) -> str:
    """Feuille dont chaque ligne est un tuple de textes (ligne 1 d'abord).

    Rôle : écrire rapidement un tableau texte ; un texte vide laisse la
    cellule absente (comme Excel).
    Paramètres : lignes, une entrée par ligne Excel.
    Retour : document XML de la feuille.
    Erreurs : aucune.
    Usages : classeur_tableau, tests de sélection de feuille.
    """
    valeurs_lignes: list[list[ValeurCellule]] = [
        [texte or None for texte in textes] for textes in lignes
    ]
    return feuille_depuis_lignes(valeurs_lignes)


def classeur_feuilles(
    cibles_feuilles: list[str], parties: dict[str, str]
) -> bytes:
    """Classeur avec workbook.xml et ses relations vers des feuilles.

    Rôle : tester l'ordre et la résolution des feuilles déclarées.
    Paramètres : cibles_feuilles, attribut Target de chaque feuille dans
    l'ordre du classeur ('' = feuille sans relation) ; parties, autres
    fichiers de l'archive (feuilles, sharedStrings…).
    Retour : octets du classeur.
    Erreurs : aucune.
    Usages : classeur_lignes, tests de sélection de feuille.
    """
    contenu = dict(parties)
    contenu["xl/workbook.xml"] = classeur_feuilles_xml(
        ["F%d" % rang for rang in range(1, len(cibles_feuilles) + 1)]
    )
    contenu["xl/_rels/workbook.xml.rels"] = relations_classeur_xml(
        {
            "rId%d" % rang: cible
            for rang, cible in enumerate(cibles_feuilles, 1)
            if cible
        }
    )
    return archive_xlsx(contenu)


def classeur_lignes(lignes: list[str], partages: list[str]) -> bytes:
    """Classeur d'une feuille à partir de lignes <row> déjà écrites.

    Rôle : classeur complet (workbook, relations, chaînes partagées).
    Paramètres : lignes, fragments <row> ; partages, table des chaînes
    partagées (vide = pas de sharedStrings.xml).
    Retour : octets du classeur.
    Erreurs : aucune.
    Usages : tests de cellules typées et de chaînes partagées.
    """
    parties = {CHEMIN_PREMIERE_FEUILLE: feuille_xml(lignes)}
    if partages:
        parties["xl/sharedStrings.xml"] = '<sst xmlns="%s">%s</sst>' % (
            ESPACE_TABLEUR,
            "".join("<si><t>%s</t></si>" % texte for texte in partages),
        )
    return classeur_feuilles(["worksheets/sheet1.xml"], parties)


def classeur_tableau(lignes: list[tuple[str, ...]]) -> bytes:
    """Classeur d'une feuille dont les lignes sont des tuples de textes.

    Rôle : forme la plus courante des tests de charger_mapping_xlsx.
    Paramètres : lignes, une entrée par ligne Excel (ligne 1 d'abord).
    Retour : octets du classeur.
    Erreurs : aucune.
    Usages : tests d'en-tête, de doublons et de lignes vides.
    """
    return classeur_feuilles(
        ["worksheets/sheet1.xml"],
        {CHEMIN_PREMIERE_FEUILLE: feuille_tableau(lignes)},
    )


def valeurs_premiere_ligne(brut: bytes) -> dict[int, object]:
    """Valeurs lues dans la première ligne de la feuille d'un classeur.

    Rôle : enchaîner lire_feuille_xlsx et valeurs_cellules_ligne.
    Paramètres : brut, octets du classeur.
    Retour : {index de colonne: valeur typée}.
    Erreurs : ErreurMapping si le classeur ou une référence est invalide.
    Usages : tests de lecture des cellules typées.
    """
    _feuille, racine, lecteur_valeur = lire_feuille_xlsx(brut)
    premiere_ligne = next(racine.iter("{%s}row" % ESPACE_TABLEUR))
    return dict(valeurs_cellules_ligne(premiere_ligne, lecteur_valeur))


def ligne_canonique(compte: str, debit: int, credit: int) -> LigneEcriture:
    """Ligne d'écriture canonique du journal de vente VT n° 1.

    Rôle : fabriquer une ligne de test lisible.
    Paramètres : compte, compte Quadra ; debit et credit, en centimes.
    Retour : LigneEcriture datée du 01/02/2026.
    Erreurs : aucune.
    Usages : journal_vente.
    """
    return LigneEcriture(
        journal_code="VT",
        ecriture_num="1",
        date_ecriture=date(2026, 2, 1),
        compte=compte,
        libelle="Facture %s" % compte,
        debit=debit,
        credit=credit,
    )


def journal_vente() -> Canonique:
    """Journal canonique d'une facture : client, produit, TVA.

    Rôle : données d'entrée de mapper_comptes.
    Paramètres : aucun.
    Retour : Canonique de trois lignes (41109009, 70609017, 44589011),
    équilibré à 120,00 EUR.
    Erreurs : aucune.
    Usages : tests de mapper_comptes.
    """
    canon = Canonique()
    canon.ajouter(ligne_canonique("41109009", 12000, 0))
    canon.ajouter(ligne_canonique("70609017", 0, 10000))
    canon.ajouter(ligne_canonique("44589011", 0, 2000))
    return canon


# Mapping complet du journal_vente.
MAPPING_VENTE = {
    "41109009": "411000",
    "70609017": "706000",
    "44589011": "445710",
}


class TestNormalisationEntete(unittest.TestCase):
    """Normalisation des en-têtes de colonnes (_norm_entete)."""

    def test_accents_casse_et_separateurs(self) -> None:
        """Vérifie la suppression des accents, majuscules et séparateurs."""
        self.assertEqual(_norm_entete("  Numéro "), "numero")
        self.assertEqual(_norm_entete("Odoo Acct."), "odooacct")
        self.assertEqual(
            _norm_entete("N° (compte-Odoo)/x_y'z"), "n°compteodooxyz"
        )

    def test_valeurs_vides_ou_non_textes(self) -> None:
        """Vérifie qu'une valeur vide donne '' et qu'un nombre est converti."""
        self.assertEqual(_norm_entete(None), "")
        self.assertEqual(_norm_entete(""), "")
        self.assertEqual(_norm_entete(411), "411")


class TestIndexColonne(unittest.TestCase):
    """Conversion des lettres de colonne en index (_index_colonne)."""

    def test_base_vingt_six(self) -> None:
        """Vérifie A=0, Z=25, AA=26, AZ=51, BA=52."""
        attendus = {"A": 0, "B": 1, "Z": 25, "AA": 26, "AZ": 51, "BA": 52}
        for lettres, index_attendu in attendus.items():
            with self.subTest(lettres=lettres):
                self.assertEqual(_index_colonne(lettres), index_attendu)

    def test_lettres_absentes(self) -> None:
        """Vérifie qu'une référence sans colonne est refusée."""
        with self.assertRaisesRegex(ErreurMapping, "sans colonne"):
            _index_colonne("")

    def test_lettres_invalides(self) -> None:
        """Vérifie qu'une lettre hors A-Z est refusée avec la référence."""
        with self.assertRaisesRegex(ErreurMapping, "invalide : 'AÉ'"):
            _index_colonne("AÉ")


class TestCompteTexte(unittest.TestCase):
    """Mise en texte d'un numéro de compte lu en cellule (_compte_txt)."""

    def test_nombres(self) -> None:
        """Vérifie qu'un entier ou un flottant entier perd le '.0'."""
        self.assertEqual(_compte_txt(10139001), "10139001")
        self.assertEqual(_compte_txt(10139001.0), "10139001")
        self.assertEqual(_compte_txt(4011.5), "4011.5")

    def test_textes(self) -> None:
        """Vérifie le nettoyage des espaces et du suffixe '.0' textuel."""
        self.assertEqual(_compte_txt(" 41109009 "), "41109009")
        self.assertEqual(_compte_txt("10139001.0"), "10139001")
        self.assertEqual(_compte_txt("411A.0"), "411A.0")
        self.assertEqual(_compte_txt(".0"), ".0")

    def test_booleen_ignore(self) -> None:
        """Vérifie qu'un booléen n'est jamais pris pour un compte."""
        self.assertEqual(_compte_txt(True), "")
        self.assertEqual(_compte_txt(False), "")


class TestChargerMappingJson(unittest.TestCase):
    """Chargement d'un mapping par charger_mapping (hors paires simples)."""

    def test_chaine_json_liste(self) -> None:
        """Vérifie la lecture d'une liste JSON et le nettoyage des comptes."""
        source = json.dumps(
            [
                {"quadra": " 41109009 ", "odoo": " 411000 "},
                {"quadra": "70609017", "odoo": "706000"},
            ]
        )
        self.assertEqual(
            charger_mapping("  \n" + source),
            {"41109009": "411000", "70609017": "706000"},
        )

    def test_lignes_incompletes_ignorees(self) -> None:
        """Vérifie qu'une ligne sans 'quadra' ou sans 'odoo' est ignorée."""
        source = json.dumps(
            [
                {"quadra": "41109009", "odoo": "411000"},
                {"quadra": "70609017"},
                {"odoo": "445710"},
                {"quadra": "", "odoo": "401000"},
                {"quadra": "60100000", "odoo": ""},
            ]
        )
        self.assertEqual(charger_mapping(source), {"41109009": "411000"})

    def test_comptes_numeriques_convertis(self) -> None:
        """Vérifie qu'un compte JSON numérique devient du texte."""
        source = json.dumps([{"quadra": 41109009, "odoo": 411000}])
        self.assertEqual(charger_mapping(source), {"41109009": "411000"})

    def test_fichier_json(self) -> None:
        """Vérifie la lecture d'un fichier JSON UTF-8 par son chemin."""
        correspondances = [
            {"quadra": "41109009", "odoo": "411000"},
            {"quadra": "44589011", "odoo": "445710"},
        ]
        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemin_mapping = os.path.join(dossier_temporaire, "mapping.json")
            with open(chemin_mapping, "w", encoding="utf-8") as fichier:
                json.dump(correspondances, fichier)
            mapping_lu = charger_mapping(chemin_mapping)
        self.assertEqual(
            mapping_lu, {"41109009": "411000", "44589011": "445710"}
        )

    def test_dict_copie(self) -> None:
        """Vérifie qu'un dict est rendu tel quel, sous forme de copie."""
        source = {"41109009": "411000"}
        mapping_lu = charger_mapping(source)
        self.assertEqual(mapping_lu, {"41109009": "411000"})
        mapping_lu["70609017"] = "706000"
        self.assertEqual(source, {"41109009": "411000"})

    def test_tuple_de_paires(self) -> None:
        """Vérifie un tuple de paires et le nettoyage des espaces."""
        source = ((" 41109009", "411000 "), ("70609017", "706000"))
        self.assertEqual(
            charger_mapping(source),
            {"41109009": "411000", "70609017": "706000"},
        )

    def test_liste_vide(self) -> None:
        """Vérifie qu'une liste vide donne un mapping vide."""
        self.assertEqual(charger_mapping([]), {})

    def test_objet_json_quadra_odoo(self) -> None:
        """Vérifie qu'un objet JSON {quadra: odoo} est lu comme mapping."""
        self.assertEqual(
            charger_mapping('{"41109009": " 411000 ", "70609017": 706000}'),
            {"41109009": "411000", "70609017": "706000"},
        )

    def test_liste_json_de_paires(self) -> None:
        """Vérifie qu'une ligne JSON [quadra, odoo] est lue comme paire."""
        self.assertEqual(
            charger_mapping('[["41109009", "411000"]]'),
            {"41109009": "411000"},
        )

    def test_ligne_json_ni_objet_ni_paire(self) -> None:
        """Vérifie qu'une ligne JSON ni objet ni paire est refusée."""
        for source in ('[["41109009"]]', "[42]", '["41109009"]'):
            with self.subTest(source=source):
                with self.assertRaisesRegex(
                    ErreurMapping, "correspondance illisible"
                ):
                    charger_mapping(source)

    def test_compte_json_non_scalaire(self) -> None:
        """Vérifie qu'un compte JSON objet, liste ou booléen est refusé."""
        for source in (
            '{"41109009": {"compte": "411000"}}',
            '[{"quadra": "41109009", "odoo": ["411000"]}]',
            '[{"quadra": true, "odoo": "411000"}]',
            '{"41109009": NaN}',
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ErreurMapping, "compte illisible"):
                    charger_mapping(source)

    def test_json_invalide(self) -> None:
        """Vérifie qu'un JSON mal formé donne une erreur explicite."""
        with self.assertRaisesRegex(ErreurMapping, "^mapping illisible"):
            charger_mapping('[{"quadra": ')

    def test_fichier_absent(self) -> None:
        """Vérifie que le chemin d'un fichier absent est cité."""
        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemin_absent = os.path.join(dossier_temporaire, "absent.json")
            with self.assertRaises(ErreurMapping) as contexte_erreur:
                charger_mapping(chemin_absent)
        self.assertIn(repr(chemin_absent), str(contexte_erreur.exception))
        self.assertIn("introuvable", str(contexte_erreur.exception))

    def test_fichier_json_invalide_ou_non_utf8(self) -> None:
        """Vérifie un fichier JSON mal formé ou non UTF-8, chemin cité."""
        contenus_illisibles = (
            b'{"41109009": ',
            '{"411é": "411000"}'.encode("latin-1"),
        )
        for contenu in contenus_illisibles:
            with self.subTest(contenu=contenu):
                with tempfile.TemporaryDirectory() as dossier_temporaire:
                    chemin_mapping = os.path.join(
                        dossier_temporaire, "mapping.json"
                    )
                    with open(chemin_mapping, "wb") as fichier:
                        fichier.write(contenu)
                    with self.assertRaises(ErreurMapping) as contexte_erreur:
                        charger_mapping(chemin_mapping)
                self.assertIn(
                    repr(chemin_mapping), str(contexte_erreur.exception)
                )

    def test_fichier_json_scalaire(self) -> None:
        """Vérifie qu'un fichier JSON ni liste ni objet est refusé."""
        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemin_mapping = os.path.join(dossier_temporaire, "mapping.json")
            with open(chemin_mapping, "w", encoding="utf-8") as fichier:
                fichier.write("42")
            with self.assertRaisesRegex(
                ErreurMapping, "attendu une liste ou un objet JSON"
            ):
                charger_mapping(chemin_mapping)

    def test_paire_de_mauvaise_longueur(self) -> None:
        """Vérifie qu'une paire qui n'a pas deux comptes est refusée."""
        for source in ([("411",)], [("411", "411000", "x")]):
            with self.subTest(source=source):
                with self.assertRaisesRegex(
                    ErreurMapping, "correspondance illisible"
                ):
                    charger_mapping(cast(SourceMapping, source))

    def test_source_non_supportee(self) -> None:
        """Vérifie qu'un type de source inconnu lève ErreurMapping."""
        source_entiere = cast(SourceMapping, 41109009)
        with self.assertRaisesRegex(ErreurMapping, "non supportée"):
            charger_mapping(source_entiere)


class TestLireFeuilleXlsx(unittest.TestCase):
    """Ouverture d'un classeur et lecture typée des cellules."""

    def test_contenu_vide(self) -> None:
        """Vérifie le diagnostic d'un fichier vide ou absent (None)."""
        for contenu in (b"", None):
            with self.subTest(contenu=contenu):
                with self.assertRaisesRegex(
                    ErreurMapping, r"^Fichier classeur 'xlsx' : fichier vide"
                ):
                    lire_feuille_xlsx(contenu)

    def test_vieux_format_xls(self) -> None:
        """Vérifie le diagnostic d'un .xls binaire (signature OLE2)."""
        contenu_xls = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16
        with self.assertRaisesRegex(
            ErreurMapping,
            r"^Fichier de mapping 'client\.xls' : vieux format \.xls",
        ):
            lire_feuille_xlsx(contenu_xls, "client.xls", "de mapping")

    def test_csv_renomme(self) -> None:
        """Vérifie que les premiers octets d'un CSV sont cités en clair."""
        with self.assertRaises(ErreurMapping) as contexte_erreur:
            lire_feuille_xlsx(b"Num\xe9ro;Odoo\r\n", "mapping.xlsx")
        message = str(contexte_erreur.exception)
        self.assertIn("contenu non-xlsx", message)
        self.assertIn("4e 75 6d e9 72 6f 3b 4f", message)
        self.assertIn("= Num.ro;O", message)

    def test_archive_tronquee(self) -> None:
        """Vérifie qu'un zip tronqué (commence par PK) est refusé."""
        archive_complete = classeur_tableau([ENTETE_MAPPING_CLIENT])
        with self.assertRaisesRegex(ErreurMapping, "archive illisible"):
            lire_feuille_xlsx(archive_complete[:30], "mapping.xlsx")

    def test_archive_sans_feuille(self) -> None:
        """Vérifie qu'une archive zip sans feuille de calcul est refusée."""
        archive_vide = archive_xlsx({"docProps/app.xml": "<Properties/>"})
        with self.assertRaisesRegex(
            ErreurMapping, "aucune feuille de calcul trouvée"
        ):
            lire_feuille_xlsx(archive_vide)

    def test_bytearray_accepte(self) -> None:
        """Vérifie qu'un bytearray est lu comme des octets."""
        brut = bytearray(classeur_tableau([ENTETE_MAPPING_CLIENT]))
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, CHEMIN_PREMIERE_FEUILLE)

    def test_premiere_feuille_du_classeur(self) -> None:
        """Vérifie que la première feuille déclarée gagne sur sheet1.xml."""
        brut = classeur_feuilles(
            ["worksheets/sheet2.xml", "worksheets/sheet1.xml"],
            {
                CHEMIN_PREMIERE_FEUILLE: feuille_tableau([("seconde",)]),
                "xl/worksheets/sheet2.xml": feuille_tableau([("premiere",)]),
            },
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, "xl/worksheets/sheet2.xml")
        self.assertEqual(valeurs_premiere_ligne(brut), {0: "premiere"})

    def test_cible_prefixee_xl(self) -> None:
        """Vérifie une cible de relation déjà préfixée par 'xl/'."""
        brut = classeur_feuilles(
            ["xl/worksheets/sheet3.xml"],
            {"xl/worksheets/sheet3.xml": feuille_tableau([("trois",)])},
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, "xl/worksheets/sheet3.xml")

    def test_relations_inutilisables(self) -> None:
        """Vérifie le repli sur sheetN.xml (relation absente ou cassée)."""
        brut = classeur_feuilles(
            ["", "worksheets/inexistante.xml"],
            {
                "xl/worksheets/sheet2.xml": feuille_tableau([("deux",)]),
                "xl/worksheets/sheet4.xml": feuille_tableau([("quatre",)]),
            },
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, "xl/worksheets/sheet2.xml")

    def test_sans_workbook(self) -> None:
        """Vérifie le repli sur sheetN.xml quand workbook.xml manque."""
        brut = archive_xlsx(
            {"xl/worksheets/sheet1.xml": feuille_tableau([("seule",)])}
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, CHEMIN_PREMIERE_FEUILLE)
        self.assertEqual(valeurs_premiere_ligne(brut), {0: "seule"})

    def test_types_de_cellules(self) -> None:
        """Vérifie la valeur typée de chaque sorte de cellule."""
        cellules = [
            cellule_brute("A1", "s", "1"),
            cellule_texte("B1", "en ligne"),
            cellule_brute("C1", "b", "1"),
            cellule_brute("D1", "b", "0"),
            cellule_brute("E1", "", "41109009"),
            cellule_brute("F1", "n", "12.5"),
            cellule_brute("G1", "", "10139001.0"),
            cellule_brute("H1", "str", "formule"),
            cellule_brute("I1", "s", "7"),
            cellule_brute("J1", "s", "x"),
            '<c r="K1" t="s"/>',
            '<c r="L1"/>',
            '<c r="M1"><v/></c>',
        ]
        brut = classeur_lignes([ligne_xml(1, cellules)], ["zéro", "partagée"])
        self.assertEqual(
            valeurs_premiere_ligne(brut),
            {
                0: "partagée",
                1: "en ligne",
                2: True,
                3: False,
                4: 41109009,
                5: 12.5,
                6: 10139001,
                7: "formule",
            },
        )

    def test_cellule_numerique_illisible(self) -> None:
        """Vérifie qu'un nombre illisible ou non fini cite la cellule."""
        for texte_valeur in ("abc", "nan", "inf"):
            with self.subTest(valeur=texte_valeur):
                brut = classeur_lignes(
                    [ligne_xml(1, [cellule_brute("B1", "n", texte_valeur)])],
                    [],
                )
                with self.assertRaisesRegex(
                    ErreurMapping, "cellule B1 : nombre illisible"
                ):
                    valeurs_premiere_ligne(brut)

    def test_cellule_booleenne_illisible(self) -> None:
        """Vérifie qu'un booléen autre que 0/1 cite la cellule."""
        for texte_valeur in ("abc", "2"):
            with self.subTest(valeur=texte_valeur):
                brut = classeur_lignes(
                    [ligne_xml(1, [cellule_brute("C1", "b", texte_valeur)])],
                    [],
                )
                with self.assertRaisesRegex(
                    ErreurMapping, "cellule C1 : booléen illisible"
                ):
                    valeurs_premiere_ligne(brut)

    def test_cellule_en_erreur_excel(self) -> None:
        """Vérifie qu'une cellule #N/A n'est jamais lue comme valeur."""
        brut = classeur_lignes(
            [ligne_xml(1, [cellule_brute("D1", "e", "#N/A")])], []
        )
        with self.assertRaisesRegex(
            ErreurMapping, "cellule D1 : erreur Excel '#N/A'"
        ):
            valeurs_premiere_ligne(brut)

    def test_cible_absolue(self) -> None:
        """Vérifie qu'une cible absolue (/xl/...) désigne la bonne feuille."""
        brut = classeur_feuilles(
            ["/xl/worksheets/sheet2.xml"],
            {
                CHEMIN_PREMIERE_FEUILLE: feuille_tableau([("mauvaise",)]),
                "xl/worksheets/sheet2.xml": feuille_tableau([("bonne",)]),
            },
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, "xl/worksheets/sheet2.xml")
        self.assertEqual(valeurs_premiere_ligne(brut), {0: "bonne"})

    def test_cible_relative_avec_retour(self) -> None:
        """Vérifie une cible relative à xl/ contenant « ./ » et « ../ »."""
        brut = classeur_feuilles(
            ["./feuilles/../worksheets/sheet2.xml"],
            {
                CHEMIN_PREMIERE_FEUILLE: feuille_tableau([("mauvaise",)]),
                "xl/worksheets/sheet2.xml": feuille_tableau([("bonne",)]),
            },
        )
        chemin_feuille, _racine, _lecteur = lire_feuille_xlsx(brut)
        self.assertEqual(chemin_feuille, "xl/worksheets/sheet2.xml")

    def test_xml_de_feuille_invalide(self) -> None:
        """Vérifie qu'une feuille au XML mal formé est citée."""
        brut = archive_xlsx({CHEMIN_PREMIERE_FEUILLE: "<worksheet><row>"})
        with self.assertRaisesRegex(
            ErreurMapping,
            "partie 'xl/worksheets/sheet1.xml' illisible",
        ):
            lire_feuille_xlsx(brut, "mapping.xlsx")

    def test_texte_au_lieu_d_octets(self) -> None:
        """Vérifie qu'un str reçu à la place d'octets est refusé."""
        with self.assertRaisesRegex(
            ErreurMapping, "contenu de type str reçu au lieu d'octets"
        ):
            lire_feuille_xlsx(cast(bytes, "PK\x03\x04"), "mapping.xlsx")

    def test_cellules_sans_reference(self) -> None:
        """Vérifie qu'une cellule sans attribut r prend son rang en ligne."""
        cellules = [cellule_texte("", "premier"), cellule_texte("", "second")]
        brut = classeur_lignes([ligne_xml(1, cellules)], [])
        self.assertEqual(
            valeurs_premiere_ligne(brut), {0: "premier", 1: "second"}
        )

    def test_reference_colonne_lointaine(self) -> None:
        """Vérifie qu'une cellule AB1 est rangée en colonne 27."""
        brut = classeur_lignes(
            [ligne_xml(1, [cellule_texte("AB1", "loin")])], []
        )
        self.assertEqual(valeurs_premiere_ligne(brut), {27: "loin"})


class TestChargerMappingXlsx(unittest.TestCase):
    """Lecture du classeur client « Mapping Quadra Odoo.xlsx »."""

    def test_classeur_client_ecrit_par_concorde(self) -> None:
        """Vérifie un classeur écrit par ecrire_xlsx (comptes numériques)."""
        lignes_client: list[list[object]] = [
            [41109009, "Clients", 411000],
            ["70609017", "Prestations", "706000"],
            [44589011, "TVA collectée", 445710],
        ]
        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemin_classeur = os.path.join(
                dossier_temporaire, "Mapping Quadra Odoo.xlsx"
            )
            ecrire_xlsx(
                chemin_classeur,
                [("Mapping", ENTETE_MAPPING_CLIENT, lignes_client)],
            )
            with open(chemin_classeur, "rb") as fichier:
                brut = fichier.read()
        self.assertEqual(
            charger_mapping_xlsx(brut, "Mapping Quadra Odoo.xlsx"),
            {
                "41109009": "411000",
                "70609017": "706000",
                "44589011": "445710",
            },
        )

    def test_entete_decale_et_synonyme(self) -> None:
        """Vérifie un en-tête en ligne 3, colonnes inversées et synonyme."""
        brut = classeur_tableau(
            [
                ("Export Quadra du 01/02/2026",),
                (),
                ("ODOO acct.", "Libellé", "NUMERO"),
                ("411000", "Clients", "41109009"),
                ("706000", "Prestations", "70609017"),
            ]
        )
        self.assertEqual(
            charger_mapping_xlsx(brut),
            {"41109009": "411000", "70609017": "706000"},
        )

    def test_synonyme_odoo_compte(self) -> None:
        """Vérifie l'en-tête « Odoo compte » (commence par odoo + compte)."""
        brut = classeur_tableau(
            [("Numéro", "Odoo-Compte"), ("41109009", "411000")]
        )
        self.assertEqual(charger_mapping_xlsx(brut), {"41109009": "411000"})

    def test_lignes_vides_et_cibles_absentes(self) -> None:
        """Vérifie que lignes vides et cibles vides sont ignorées."""
        brut = classeur_tableau(
            [
                ENTETE_MAPPING_CLIENT,
                ("41109009", "Clients", "411000"),
                (),
                ("", "Sous-total", "999999"),
                ("60100000", "Achats", ""),
                ("44589011", "TVA", "445710"),
            ]
        )
        self.assertEqual(
            charger_mapping_xlsx(brut),
            {"41109009": "411000", "44589011": "445710"},
        )

    def test_lignes_avant_entete_ignorees(self) -> None:
        """Vérifie que rien n'est lu au-dessus de la ligne d'en-tête."""
        brut = classeur_tableau(
            [
                ("10100000", "", "101000"),
                ENTETE_MAPPING_CLIENT,
                ("41109009", "Clients", "411000"),
            ]
        )
        self.assertEqual(charger_mapping_xlsx(brut), {"41109009": "411000"})

    def test_doublon_identique_accepte(self) -> None:
        """Vérifie qu'un doublon de même cible n'est pas une erreur."""
        brut = classeur_tableau(
            [
                ENTETE_MAPPING_CLIENT,
                ("41109009", "Clients", "411000"),
                ("41109009", "Clients bis", "411000"),
            ]
        )
        self.assertEqual(charger_mapping_xlsx(brut), {"41109009": "411000"})

    def test_cibles_contradictoires(self) -> None:
        """Vérifie que des cibles différentes sont toutes citées, triées."""
        brut = classeur_tableau(
            [
                ENTETE_MAPPING_CLIENT,
                ("70609017", "", "706100"),
                ("41109009", "", "411000"),
                ("70609017", "", "706000"),
                ("41109009", "", "411900"),
                ("70609017", "", "706200"),
            ]
        )
        with self.assertRaises(ErreurMapping) as contexte_erreur:
            charger_mapping_xlsx(brut, "mapping.xlsx")
        self.assertEqual(
            str(contexte_erreur.exception),
            "Fichier de mapping 'mapping.xlsx' : comptes Quadra avec cibles "
            "Odoo contradictoires : 41109009->411000/411900, "
            "70609017->706000/706100/706200",
        )

    def test_entete_introuvable(self) -> None:
        """Vérifie l'erreur explicite si « Odoo Acct » manque."""
        brut = classeur_tableau(
            [("Numéro", "Intitulé", "Odoo"), ("41109009", "", "411000")]
        )
        with self.assertRaisesRegex(
            ErreurMapping,
            r"^Fichier de mapping 'xlsx' : en-tête introuvable",
        ):
            charger_mapping_xlsx(brut)

    def test_entete_numero_en_double(self) -> None:
        """Vérifie qu'une colonne « Numéro » en double est ambiguë."""
        brut = classeur_tableau(
            [
                ("Numéro", "Odoo Acct", "Numéro"),
                ("41109009", "411000", "70609017"),
            ]
        )
        with self.assertRaisesRegex(
            ErreurMapping, "colonne « Numéro » ambiguë \\(A, C\\)"
        ):
            charger_mapping_xlsx(brut)

    def test_entete_odoo_en_double(self) -> None:
        """Vérifie qu'une colonne « Odoo Acct » en double est ambiguë."""
        brut = classeur_tableau(
            [("Numéro", "Odoo Acct", "Odoo compte"), ("411", "411000", "x")]
        )
        with self.assertRaisesRegex(
            ErreurMapping, "colonne « Odoo Acct » ambiguë \\(B, C\\)"
        ):
            charger_mapping_xlsx(brut)

    def test_entete_sur_deux_lignes_refuse(self) -> None:
        """Vérifie que « Numéro » et « Odoo Acct » sont sur une même ligne."""
        brut = classeur_tableau(
            [
                ("Numéro", "Intitulé"),
                ("", "", "Odoo Acct"),
                ("41109009", "Clients", "411000"),
            ]
        )
        with self.assertRaisesRegex(ErreurMapping, "en-tête introuvable"):
            charger_mapping_xlsx(brut)

    def test_compte_en_erreur_excel(self) -> None:
        """Vérifie qu'une cible #N/A n'est jamais prise pour un compte."""
        lignes = [
            ligne_valeurs(1, ["Numéro", "Odoo Acct"]),
            ligne_xml(
                2,
                [
                    cellule_texte("A2", "41109009"),
                    cellule_brute("B2", "e", "#N/A"),
                ],
            ),
        ]
        with self.assertRaisesRegex(
            ErreurMapping,
            "^Fichier de mapping 'mapping.xlsx' : cellule B2 : erreur Excel",
        ):
            charger_mapping_xlsx(classeur_lignes(lignes, []), "mapping.xlsx")

    def test_entete_au_dela_de_cinquante_lignes(self) -> None:
        """Vérifie que l'en-tête n'est cherché que dans 50 lignes."""
        lignes_titre: list[tuple[str, ...]] = [("titre",)] * 50
        brut = classeur_tableau(
            lignes_titre + [ENTETE_MAPPING_CLIENT, ("41109009", "", "411000")]
        )
        with self.assertRaisesRegex(ErreurMapping, "en-tête introuvable"):
            charger_mapping_xlsx(brut)

    def test_entete_en_cinquantieme_ligne(self) -> None:
        """Vérifie qu'un en-tête en ligne 50 est encore trouvé."""
        lignes_titre: list[tuple[str, ...]] = [("titre",)] * 49
        brut = classeur_tableau(
            lignes_titre + [ENTETE_MAPPING_CLIENT, ("41109009", "", "411000")]
        )
        self.assertEqual(charger_mapping_xlsx(brut), {"41109009": "411000"})

    def test_aucune_correspondance(self) -> None:
        """Vérifie l'erreur si l'en-tête n'est suivi d'aucune ligne utile."""
        brut = classeur_tableau(
            [ENTETE_MAPPING_CLIENT, ("41109009", "Clients", "")]
        )
        with self.assertRaisesRegex(
            ErreurMapping, "aucune correspondance trouvée sous l'en-tête"
        ):
            charger_mapping_xlsx(brut, "vide.xlsx")

    def test_comptes_en_chaines_partagees(self) -> None:
        """Vérifie des comptes lus dans la table de chaînes partagées."""
        lignes = [
            ligne_xml(
                1,
                [cellule_brute("A1", "s", "0"), cellule_brute("B1", "s", "1")],
            ),
            ligne_xml(
                2,
                [cellule_brute("A2", "s", "2"), cellule_brute("B2", "s", "3")],
            ),
        ]
        brut = classeur_lignes(
            lignes, ["Numéro", "Odoo Acct", "41109009", "411000"]
        )
        self.assertEqual(charger_mapping_xlsx(brut), {"41109009": "411000"})

    def test_contenu_non_xlsx(self) -> None:
        """Vérifie que l'erreur cite le fichier « de mapping »."""
        with self.assertRaisesRegex(
            ErreurMapping, r"^Fichier de mapping 'map\.csv' : contenu non-xlsx"
        ):
            charger_mapping_xlsx(b"Numero;Odoo Acct\n", "map.csv")


class TestMapperComptes(unittest.TestCase):
    """Application du mapping au journal canonique (mapper_comptes)."""

    def test_bilan_et_canonique_modifie(self) -> None:
        """Vérifie le bilan, les comptes remplacés et les montants intacts."""
        canon = journal_vente()
        bilan = mapper_comptes(canon, MAPPING_VENTE)
        self.assertEqual(
            (bilan["nb_lignes"], bilan["nb_mappees"], bilan["inconnus"]),
            (3, 3, 0),
        )
        self.assertIs(bilan["canon"], canon)
        self.assertEqual(
            [ligne.compte for ligne in canon.lignes],
            ["411000", "706000", "445710"],
        )
        self.assertEqual(
            [(ligne.debit, ligne.credit) for ligne in canon.lignes],
            [(12000, 0), (0, 10000), (0, 2000)],
        )
        self.assertTrue(canon.est_equilibre())

    def test_dict_de_pipeline(self) -> None:
        """Vérifie un dict portant 'canon' et un dict 'resultat' imbriqué."""
        for donnees in (
            {"canon": journal_vente()},
            {"resultat": {"canon": journal_vente()}},
        ):
            with self.subTest(cles=list(donnees)):
                bilan = mapper_comptes(donnees, MAPPING_VENTE)
                self.assertEqual(bilan["canon"].lignes[0].compte, "411000")

    def test_mapping_chaine_json(self) -> None:
        """Vérifie un mapping donné en chaîne JSON."""
        source = json.dumps(
            [
                {"quadra": compte_quadra, "odoo": compte_odoo}
                for compte_quadra, compte_odoo in MAPPING_VENTE.items()
            ]
        )
        canon = journal_vente()
        mapper_comptes(canon, source)
        self.assertEqual(canon.lignes[2].compte, "445710")

    def test_un_seul_passage(self) -> None:
        """Vérifie qu'une cible n'est pas remappée une seconde fois."""
        mapping_enchaine = dict(MAPPING_VENTE)
        mapping_enchaine["411000"] = "999999"
        canon = journal_vente()
        mapper_comptes(canon, mapping_enchaine)
        self.assertEqual(canon.lignes[0].compte, "411000")

    def test_journal_vide(self) -> None:
        """Vérifie qu'un journal sans ligne donne un bilan à zéro."""
        bilan = mapper_comptes(Canonique(), {})
        self.assertEqual(
            (bilan["nb_lignes"], bilan["nb_mappees"], bilan["inconnus"]),
            (0, 0, 0),
        )

    def test_comptes_inconnus_comptes_et_tries(self) -> None:
        """Vérifie le détail trié et le nombre d'occurrences des inconnus."""
        canon = journal_vente()
        canon.ajouter(ligne_canonique("44589011", 0, 500))
        with self.assertRaises(ErreurMapping) as contexte_erreur:
            mapper_comptes(canon, {"70609017": "706000"})
        self.assertTrue(
            str(contexte_erreur.exception).endswith(
                "aucun compte deviné : 41109009 (x1), 44589011 (x2)"
            )
        )

    def test_echec_sans_modification(self) -> None:
        """Vérifie qu'un mapping incomplet laisse le canonique intact."""
        canon = journal_vente()
        with self.assertRaisesRegex(ErreurMapping, "70609017"):
            mapper_comptes(canon, {"41109009": "411000"})
        self.assertEqual(
            [ligne.compte for ligne in canon.lignes],
            ["41109009", "70609017", "44589011"],
        )

    def test_canonique_vide_dans_dict(self) -> None:
        """Vérifie qu'un Canonique vide porté par 'canon' est reconnu."""
        canon_vide = Canonique()
        bilan = mapper_comptes({"canon": canon_vide}, {})
        self.assertIs(bilan["canon"], canon_vide)
        self.assertEqual(bilan["nb_lignes"], 0)

    def test_mapping_absent(self) -> None:
        """Vérifie qu'aucun mapping fourni est une erreur bloquante."""
        with self.assertRaisesRegex(ErreurMapping, "Aucun mapping fourni"):
            mapper_comptes(journal_vente())

    def test_sans_journal_canonique(self) -> None:
        """Vérifie qu'un dict sans journal canonique est refusé."""
        with self.assertRaisesRegex(
            ErreurMapping, "Aucun journal canonique à mapper"
        ):
            mapper_comptes({"autre": 1}, MAPPING_VENTE)


if __name__ == "__main__":
    unittest.main()
