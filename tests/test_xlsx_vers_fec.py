# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du convertisseur Excel -> FEC (core/xlsx_vers_fec.py).

Les classeurs .xlsx sont construits à la main (zip + XML) : chaque test
maîtrise exactement le contenu lu, par le lecteur interne comme par
openpyxl.
"""

import importlib.util
import sys
import unittest
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from datetime import date, datetime
from unittest import mock

from core import xlsx_vers_fec as module_conversion
from core.canonical import ErreurMontant
from core.xlsx_vers_fec import (
    ErreurFEC,
    _centimes,
    _colonne_xlsx,
    _colonnes_reconnues,
    _convertir_quadra,
    _date_fec,
    _date_quadra,
    _fmt_centimes,
    _lire_avec_openpyxl,
    _lire_xlsx_stdlib,
    _nettoyer_texte,
    _nombre_texte,
    _norm,
    _trouver_entete,
    _valeur_colonne,
    _valeur_date,
    xlsx_vers_fec,
)
from tests.classeurs_xlsx import (
    CHEMIN_PREMIERE_FEUILLE,
    ESPACE_PAQUET,
    ESPACE_RELATIONS,
    ESPACE_RELATIONS_PAQUET,
    ESPACE_TABLEUR,
    ValeurCellule,
    archive_xlsx,
    classeur_feuilles_xml,
    feuille_depuis_lignes,
    feuille_xml,
    relations_classeur_xml,
)

TYPE_CONTENU_TABLEUR = "application/vnd.openxmlformats-officedocument"
# Police, remplissage et bordure par défaut, puis style nommé « Normal » :
# parties qu'openpyxl exige pour lire les styles sans avertissement.
STYLES_PAR_DEFAUT = (
    '<fonts count="1"><font/></fonts>'
    '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
    '<borders count="1"><border/></borders>'
)
STYLE_NORMAL = (
    '<cellStyles count="1">'
    '<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
)
# Un style nommé (cellStyleXfs) précède cellXfs ; le style de cellule 1
# est une date (format intégré 14).
STYLES_AVEC_STYLE_NOMME = (
    '<styleSheet xmlns="%s">%s'
    '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" xfId="0"/>'
    '<xf numFmtId="14" xfId="0"/></cellXfs>%s'
    "</styleSheet>" % (ESPACE_TABLEUR, STYLES_PAR_DEFAUT, STYLE_NORMAL)
)
# Style 1 : format personnalisé date (164) ; style 2 : format personnalisé
# dont le seul « d » est entre guillemets (texte littéral, pas une date).
STYLES_FORMATS_PERSONNALISES = (
    '<styleSheet xmlns="%s"><numFmts count="2">'
    '<numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
    '<numFmt numFmtId="165" formatCode="0&quot; d&quot;"/>'
    "</numFmts>%s"
    '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
    '<cellXfs count="3"><xf numFmtId="0"/>'
    '<xf numFmtId="164"/><xf numFmtId="165"/></cellXfs>%s'
    "</styleSheet>" % (ESPACE_TABLEUR, STYLES_PAR_DEFAUT, STYLE_NORMAL)
)
# Formats déclarés mais aucune liste cellXfs : aucun style n'est une date.
STYLES_SANS_CELLXFS = (
    '<styleSheet xmlns="%s"><numFmts count="1">'
    '<numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
    "</numFmts></styleSheet>" % ESPACE_TABLEUR
)
CLASSEUR_UNE_FEUILLE = classeur_feuilles_xml(["FEC"])
CLASSEUR_SANS_FEUILLE = classeur_feuilles_xml([])
RELATIONS_CLASSEUR = relations_classeur_xml({"rId1": "worksheets/sheet1.xml"})
RELATIONS_RACINE = (
    '<Relationships xmlns="%s"><Relationship Id="rId1" '
    'Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    % (ESPACE_RELATIONS_PAQUET, ESPACE_RELATIONS)
)
# A1 : série Excel 45296 au style date ; B1 : nombre sans style.
FEUILLE_DATE_ET_NOMBRE = (
    '<worksheet xmlns="%s"><sheetData><row r="1">'
    '<c r="A1" s="1"><v>45296</v></c><c r="B1"><v>12</v></c>'
    "</row></sheetData></worksheet>" % ESPACE_TABLEUR
)
# A1 : style date personnalisé ; B1 : format texte « d » ; C1 : sans style.
FEUILLE_TROIS_STYLES = (
    '<worksheet xmlns="%s"><sheetData><row r="1">'
    '<c r="A1" s="1"><v>45296</v></c><c r="B1" s="2"><v>7</v></c>'
    '<c r="C1"><v>45296</v></c>'
    "</row></sheetData></worksheet>" % ESPACE_TABLEUR
)
# Chaînes partagées : « Compte » puis un texte riche en deux morceaux.
CHAINES_PARTAGEES = (
    '<sst xmlns="%s"><si><t>Compte</t></si>'
    "<si><r><t>Ventes </t></r><r><t>France</t></r></si></sst>" % ESPACE_TABLEUR
)
# Feuille d'un seul texte : sert là où seule la recherche de feuille compte.
FEUILLE_UN_TEXTE = (
    '<worksheet xmlns="%s"><sheetData><row r="1">'
    '<c r="A1" t="inlineStr"><is><t>trouvée</t></is></c>'
    "</row></sheetData></worksheet>" % ESPACE_TABLEUR
)
ENTETE_FEC_ATTENDUE = "\t".join(
    (
        "JournalCode",
        "JournalLib",
        "EcritureNum",
        "EcritureDate",
        "CompteNum",
        "CompteLib",
        "CompAuxNum",
        "CompAuxLib",
        "PieceRef",
        "PieceDate",
        "EcritureLib",
        "Debit",
        "Credit",
        "EcritureLet",
        "DateLet",
        "ValidDate",
        "Montantdevise",
        "Idevise",
    )
)
ENTETE_STANDARD = (
    "Journal",
    "Lib journal",
    "N° écriture",
    "Date",
    "Compte",
    "Intitulé compte",
    "Pièce",
    "Libellé",
    "Débit",
    "Crédit",
)
# Les seules colonnes obligatoires d'un FEC standard, intitulés simples.
ENTETE_MINIMALE = ("Ecriture", "Date", "Compte", "Debit", "Credit")
ENTETE_QUADRA = (
    "Période",
    "Jour",
    "Journal",
    "Compte",
    "Libellé",
    "Débit",
    "Crédit",
    "NumUniq",
    "TypeLigne",
    "Pièce",
)
NOM_FICHIER_ESSAI = "essai.xlsx"
JOURNAL_ESSAI = "VE"
PERIODE_ESSAI = "01/03/2024"
SIGNATURE_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def types_contenu(
    styles_presents: bool, chaines_presentes: bool, chemin_feuille: str
) -> str:
    """Rend le [Content_Types].xml du classeur (requis par openpyxl).

    Paramètres : styles_presents, chaines_presentes (parties déclarées) ;
    chemin_feuille, chemin de la feuille dans l'archive.
    Retour : le XML des types de contenu.
    Erreurs : aucune.
    Usages : classeur_xlsx.
    """
    parties = [
        ("/xl/workbook.xml", "spreadsheetml.sheet.main+xml"),
        ("/" + chemin_feuille, "spreadsheetml.worksheet+xml"),
    ]
    if styles_presents:
        parties.append(("/xl/styles.xml", "spreadsheetml.styles+xml"))
    if chaines_presentes:
        parties.append(
            ("/xl/sharedStrings.xml", "spreadsheetml.sharedStrings+xml")
        )
    declarations = "".join(
        '<Override PartName="%s" ContentType="%s.%s"/>'
        % (partie, TYPE_CONTENU_TABLEUR, type_partie)
        for partie, type_partie in parties
    )
    return (
        '<Types xmlns="%s/content-types">'
        '<Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "%s</Types>" % (ESPACE_PAQUET, declarations)
    )


def classeur_xlsx(
    contenu_feuille: str,
    styles_xml: str | None = None,
    *,
    chaines_partagees_xml: str | None = None,
    classeur_xml: str = CLASSEUR_UNE_FEUILLE,
    relations_xml: str | None = RELATIONS_CLASSEUR,
    chemin_feuille: str | None = CHEMIN_PREMIERE_FEUILLE,
) -> bytes:
    """Construit un .xlsx minimal (une feuille) lisible par les deux lecteurs.

    Rôle : classeur de test pour _lire_xlsx_stdlib, openpyxl et
    xlsx_vers_fec.
    Paramètres : contenu_feuille, XML de la feuille ; styles_xml et
    chaines_partagees_xml, parties optionnelles (absentes si None) ;
    classeur_xml, XML de xl/workbook.xml ; relations_xml, relations du
    classeur (absentes si None) ; chemin_feuille, chemin de la feuille
    dans l'archive (aucune feuille si None).
    Retour : les octets du classeur zippé.
    Erreurs : aucune.
    Usages : tous les tests de lecture et de conversion.
    """
    parties = {
        "[Content_Types].xml": types_contenu(
            styles_xml is not None,
            chaines_partagees_xml is not None,
            chemin_feuille or CHEMIN_PREMIERE_FEUILLE,
        ),
        "_rels/.rels": RELATIONS_RACINE,
        "xl/workbook.xml": classeur_xml,
    }
    if relations_xml is not None:
        parties["xl/_rels/workbook.xml.rels"] = relations_xml
    if styles_xml is not None:
        parties["xl/styles.xml"] = styles_xml
    if chaines_partagees_xml is not None:
        parties["xl/sharedStrings.xml"] = chaines_partagees_xml
    if chemin_feuille is not None:
        parties[chemin_feuille] = contenu_feuille
    return archive_xlsx(parties)


def convertir_lignes(
    lignes: Sequence[Sequence[ValeurCellule]],
) -> bytes:
    """Convertit des lignes de valeurs en FEC via un vrai classeur .xlsx.

    Paramètres : lignes, cellules de chaque ligne du classeur.
    Retour : les octets FEC produits par xlsx_vers_fec.
    Erreurs : ErreurFEC (ou ErreurMontant) si le classeur est refusé.
    Usages : TestConversionStandard, TestConversionQuadra.
    """
    return xlsx_vers_fec(
        classeur_xlsx(feuille_depuis_lignes(lignes)), NOM_FICHIER_ESSAI
    )


def sans_openpyxl() -> AbstractContextManager[object]:
    """Simule l'absence d'openpyxl le temps d'un bloc « with ».

    Rôle : forcer le repli sur le lecteur interne de bibliothèque standard.
    Paramètres : aucun.
    Retour : le gestionnaire de contexte du remplacement.
    Erreurs : aucune.
    Usages : TestLectureOpenpyxl, TestConversionStandard.
    """
    return mock.patch.object(module_conversion, "_OPENPYXL_DISPONIBLE", False)


def message_erreur(
    cas_de_test: unittest.TestCase,
    type_erreur: type[Exception],
    action: AbstractContextManager[object] | None,
    lignes: Sequence[Sequence[ValeurCellule]] | bytes,
) -> str:
    """Exécute une conversion qui doit échouer et rend son message.

    Paramètres : cas_de_test, test en cours ; type_erreur, exception
    attendue ; action, contexte actif pendant la conversion (ou None) ;
    lignes, lignes du classeur ou octets bruts du fichier.
    Retour : le texte de l'exception levée.
    Erreurs : échec du test si aucune exception type_erreur n'est levée.
    Usages : TestConversionStandard, TestConversionQuadra.
    """
    with cas_de_test.assertRaises(type_erreur) as contexte_erreur:
        with action if action is not None else nullcontext():
            if isinstance(lignes, bytes):
                xlsx_vers_fec(lignes, NOM_FICHIER_ESSAI)
            else:
                convertir_lignes(lignes)
    return str(contexte_erreur.exception)


def ligne_fec_attendue(
    *,
    journal: str,
    numero: str,
    date_ecriture: str,
    compte: str,
    libelle: str,
    debit: str,
    credit: str,
    journal_lib: str = "",
    compte_lib: str = "",
    piece: str = "",
) -> str:
    """Rend une ligne FEC attendue (18 champs séparés par tabulation).

    Rôle : oracle écrit indépendamment du code testé ; PieceDate et
    ValidDate reprennent la date d'écriture, les autres champs sont vides.
    Paramètres : valeurs des champs (journal_lib vide = journal).
    Retour : la ligne, sans fin de ligne.
    Erreurs : aucune.
    Usages : TestConversionStandard, TestConversionQuadra.
    """
    return "\t".join(
        (
            journal,
            journal_lib or journal,
            numero,
            date_ecriture,
            compte,
            compte_lib,
            "",
            "",
            piece,
            date_ecriture,
            libelle,
            debit,
            credit,
            "",
            "",
            date_ecriture,
            "",
            "",
        )
    )


def fec_attendu(*lignes_fec: str) -> bytes:
    """Rend le FEC attendu complet : en-tête, lignes, fin de ligne LF.

    Paramètres : lignes_fec, lignes rendues par ligne_fec_attendue.
    Retour : les octets UTF-8 attendus.
    Erreurs : aucune.
    Usages : TestConversionStandard, TestConversionQuadra.
    """
    return ("\n".join((ENTETE_FEC_ATTENDUE,) + lignes_fec) + "\n").encode(
        "utf-8"
    )


def ligne_quadra(
    numuniq: ValeurCellule,
    jour: ValeurCellule,
    compte: ValeurCellule,
    libelle: str,
    debit: ValeurCellule,
    credit: ValeurCellule,
    *,
    journal: str = JOURNAL_ESSAI,
    type_ligne: str = "E",
    piece: str = "",
) -> tuple[ValeurCellule, ...]:
    """Rend une ligne d'export Cegid Quadra dans l'ordre d'ENTETE_QUADRA.

    Paramètres : valeurs des colonnes ; la période est PERIODE_ESSAI.
    Retour : les cellules de la ligne.
    Erreurs : aucune.
    Usages : TestConversionQuadra.
    """
    return (
        PERIODE_ESSAI,
        jour,
        journal,
        compte,
        libelle,
        debit,
        credit,
        numuniq,
        type_ligne,
        piece,
    )


def ligne_quadra_attendue(
    numero: str,
    jour: int,
    compte: str,
    libelle: str,
    debit: str,
    credit: str,
    piece: str = "",
) -> str:
    """Rend la ligne FEC attendue d'une ligne Quadra du journal d'essai.

    Paramètres : numero, numéro d'écriture retenu ; jour (mars 2024) ;
    compte, libelle, debit, credit, piece, champs attendus.
    Retour : la ligne FEC attendue.
    Erreurs : aucune.
    Usages : TestConversionQuadra.
    """
    return ligne_fec_attendue(
        journal=JOURNAL_ESSAI,
        numero=numero,
        date_ecriture="202403%02d" % jour,
        compte=compte,
        libelle=libelle,
        debit=debit,
        credit=credit,
        piece=piece,
    )


class TestStylesDate(unittest.TestCase):
    """Styles date : l'attribut s d'une cellule indexe cellXfs seul."""

    def test_style_nomme_ne_decale_pas_les_dates(self) -> None:
        """Une cellule au style date est lue comme une date."""
        lignes_lues = _lire_xlsx_stdlib(
            classeur_xlsx(FEUILLE_DATE_ET_NOMBRE, STYLES_AVEC_STYLE_NOMME)
        )
        self.assertEqual(lignes_lues, [(date(2024, 1, 5), 12)])

    def test_formats_personnalises(self) -> None:
        """Format date personnalisé : date ; « d » littéral : nombre."""
        lignes_lues = _lire_xlsx_stdlib(
            classeur_xlsx(FEUILLE_TROIS_STYLES, STYLES_FORMATS_PERSONNALISES)
        )
        self.assertEqual(lignes_lues, [(date(2024, 1, 5), 7, 45296)])

    def test_sans_fichier_de_styles(self) -> None:
        """Sans xl/styles.xml, aucune cellule n'est convertie en date."""
        lignes_lues = _lire_xlsx_stdlib(classeur_xlsx(FEUILLE_TROIS_STYLES))
        self.assertEqual(lignes_lues, [(45296, 7, 45296)])

    def test_sans_cellxfs(self) -> None:
        """Sans liste cellXfs, aucun indice de style n'est une date."""
        lignes_lues = _lire_xlsx_stdlib(
            classeur_xlsx(FEUILLE_TROIS_STYLES, STYLES_SANS_CELLXFS)
        )
        self.assertEqual(lignes_lues, [(45296, 7, 45296)])

    def test_serie_avec_heure_tronquee(self) -> None:
        """La partie horaire d'une série Excel est ignorée."""
        self.assertEqual(_valeur_date(45296.75), date(2024, 1, 5))
        self.assertEqual(_valeur_date(1), date(1899, 12, 31))


class TestLectureStdlib(unittest.TestCase):
    """Lecteur interne (zipfile + XML) : cellules, feuilles, erreurs."""

    def lire_feuille(
        self, contenu_lignes: str
    ) -> list[module_conversion.LigneXlsx]:
        """Lit une feuille construite à partir de ses lignes <row>.

        Paramètres : contenu_lignes, XML des éléments <row>.
        Retour : les lignes lues par _lire_xlsx_stdlib.
        Erreurs : ErreurFEC si la feuille est refusée.
        Usages : tests de cellules de cette classe.
        """
        return list(
            _lire_xlsx_stdlib(
                classeur_xlsx(
                    feuille_xml([contenu_lignes]),
                    chaines_partagees_xml=CHAINES_PARTAGEES,
                ),
                NOM_FICHIER_ESSAI,
            )
        )

    def test_chaines_partagees(self) -> None:
        """Les chaînes partagées (texte riche compris) sont résolues."""
        self.assertEqual(
            self.lire_feuille(
                '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                '<c r="B1" t="s"><v>1</v></c></row>'
            ),
            [("Compte", "Ventes France")],
        )

    def test_indice_chaine_partagee_invalide(self) -> None:
        """Un indice hors table est refusé avec la cellule en cause."""
        with self.assertRaises(ErreurFEC) as contexte_erreur:
            self.lire_feuille('<row r="1"><c r="C4" t="s"><v>9</v></c></row>')
        self.assertEqual(
            str(contexte_erreur.exception),
            "Indice de chaine partagee invalide en C4 de 'essai.xlsx'.",
        )

    def test_texte_en_ligne_et_formule(self) -> None:
        """inlineStr et résultat texte de formule (t="str") sont lus."""
        self.assertEqual(
            self.lire_feuille(
                '<row r="1"><c r="A1" t="inlineStr"><is><r><t>Lib</t></r>'
                "<r><t>ellé</t></r></is></c>"
                '<c r="B1" t="str"><f>A1</f><v>Libellé</v></c></row>'
            ),
            [("Libellé", "Libellé")],
        )

    def test_colonnes_eparses_et_largeur(self) -> None:
        """Les colonnes sautées valent None ; la largeur ne diminue pas."""
        self.assertEqual(
            self.lire_feuille(
                '<row r="1"><c r="A1"><v>1</v></c><c r="C1"><v>3</v></c>'
                '</row><row r="2"><c r="B2"><v>2</v></c></row>'
                '<row r="3"/>'
            ),
            [(1, None, 3), (None, 2, None), (None, None, None)],
        )

    def test_ligne_vide_en_tete(self) -> None:
        """Une première ligne sans cellule est une ligne vide."""
        self.assertEqual(
            self.lire_feuille('<row r="1"/><row r="2"><c r="A2"/></row>'),
            [(), (None,)],
        )

    def test_booleens_nombres_et_textes(self) -> None:
        """Booléens, entiers, décimaux, textes bruts et valeurs vides."""
        self.assertEqual(
            self.lire_feuille(
                '<row r="1"><c r="A1" t="b"><v>1</v></c>'
                '<c r="B1" t="b"><v>0</v></c><c r="C1"><v>3.0</v></c>'
                '<c r="D1"><v>12.5</v></c><c r="E1"><v>abc</v></c>'
                '<c r="F1"><v> </v></c><c r="G1"><v/></c></row>'
            ),
            [(True, False, 3, 12.5, "abc", None, None)],
        )

    def test_reference_de_cellule_invalide(self) -> None:
        """Une référence sans lettre de colonne est refusée."""
        with self.assertRaises(ErreurFEC) as contexte_erreur:
            self.lire_feuille('<row r="1"><c r="12"><v>1</v></c></row>')
        self.assertEqual(
            str(contexte_erreur.exception),
            "Reference de cellule invalide : '12'",
        )

    def test_colonne_xlsx(self) -> None:
        """Les lettres de colonne sont converties en index (base 0)."""
        self.assertEqual(
            [_colonne_xlsx(reference) for reference in ("A1", "Z9", "AA3")],
            [0, 25, 26],
        )
        self.assertEqual(_colonne_xlsx("AB12"), 27)

    def lire_feuille_deplacee(
        self,
        classeur_xml: str,
        relations_xml: str | None,
        chemin_feuille: str,
    ) -> list[module_conversion.LigneXlsx]:
        """Lit un classeur dont la feuille unique est rangée à part.

        Paramètres : classeur_xml, relations_xml (None = absentes),
        chemin_feuille, chemin de la feuille dans l'archive.
        Retour : les lignes lues par _lire_xlsx_stdlib.
        Erreurs : ErreurFEC si aucune feuille n'est trouvée.
        Usages : tests de recherche de feuille de cette classe.
        """
        return list(
            _lire_xlsx_stdlib(
                classeur_xlsx(
                    FEUILLE_UN_TEXTE,
                    classeur_xml=classeur_xml,
                    relations_xml=relations_xml,
                    chemin_feuille=chemin_feuille,
                ),
                NOM_FICHIER_ESSAI,
            )
        )

    def test_cible_absolue(self) -> None:
        """Une cible de relation absolue (« /xl/... ») est suivie."""
        relations_absolues = relations_classeur_xml(
            {"rId1": "/xl/feuilles/donnees.xml"}
        )
        self.assertEqual(
            self.lire_feuille_deplacee(
                CLASSEUR_UNE_FEUILLE,
                relations_absolues,
                "xl/feuilles/donnees.xml",
            ),
            [("trouvée",)],
        )

    def test_relation_introuvable_repli(self) -> None:
        """Identifiant de relation inconnu : repli sur sheetN.xml."""
        relations_autres = relations_classeur_xml(
            {"rId7": "worksheets/autre.xml"}
        )
        self.assertEqual(
            self.lire_feuille_deplacee(
                CLASSEUR_UNE_FEUILLE,
                relations_autres,
                "xl/worksheets/sheet3.xml",
            ),
            [("trouvée",)],
        )

    def test_classeur_sans_feuille_declaree_repli(self) -> None:
        """Aucune feuille déclarée ni relation : repli sur sheetN.xml."""
        self.assertEqual(
            self.lire_feuille_deplacee(
                CLASSEUR_SANS_FEUILLE, None, "xl/worksheets/sheet2.xml"
            ),
            [("trouvée",)],
        )

    def test_aucune_feuille(self) -> None:
        """Sans aucune feuille de calcul, l'erreur nomme le fichier."""
        with self.assertRaises(ErreurFEC) as contexte_erreur:
            self.lire_feuille_deplacee(
                CLASSEUR_UNE_FEUILLE, RELATIONS_CLASSEUR, "xl/autre.xml"
            )
        self.assertEqual(
            str(contexte_erreur.exception),
            "Aucune feuille de calcul trouvee dans 'essai.xlsx'.",
        )


class TestLectureOpenpyxl(unittest.TestCase):
    """Lecture par openpyxl : mêmes valeurs que le lecteur interne."""

    def test_valeurs_lues(self) -> None:
        """Textes, nombres, booléens et colonnes éparses."""
        classeur = classeur_xlsx(
            feuille_depuis_lignes(
                [("Compte", None, 12.5, True), (None, 3)],
            )
        )
        self.assertEqual(
            _lire_avec_openpyxl(classeur),
            [("Compte", None, 12.5, True), (None, 3)],
        )

    def test_chaines_partagees_et_date(self) -> None:
        """Chaînes partagées et style date (lue en datetime)."""
        classeur = classeur_xlsx(
            feuille_xml(
                [
                    '<row r="1"><c r="A1" t="s"><v>1</v></c>'
                    '<c r="B1" s="1"><v>45296</v></c></row>'
                ]
            ),
            STYLES_FORMATS_PERSONNALISES,
            chaines_partagees_xml=CHAINES_PARTAGEES,
        )
        self.assertEqual(
            _lire_avec_openpyxl(classeur),
            [("Ventes France", datetime(2024, 1, 5))],
        )

    def test_absent(self) -> None:
        """Sans openpyxl, la lecture lève ImportError (repli prévu)."""
        with sans_openpyxl():
            with self.assertRaises(ImportError):
                _lire_avec_openpyxl(classeur_xlsx(FEUILLE_UN_TEXTE))

    def test_import_sans_openpyxl(self) -> None:
        """Module importé sans openpyxl : repli sur le lecteur interne."""
        spec_module = importlib.util.find_spec("core.xlsx_vers_fec")
        if spec_module is None or spec_module.loader is None:
            self.fail("Module core.xlsx_vers_fec introuvable.")
        module_sans_openpyxl = importlib.util.module_from_spec(spec_module)
        # Une entrée None dans sys.modules fait lever ImportError à import.
        with mock.patch.dict(sys.modules, {"openpyxl": None}):
            spec_module.loader.exec_module(module_sans_openpyxl)
        self.assertFalse(vars(module_sans_openpyxl)["_OPENPYXL_DISPONIBLE"])


class TestNormalisation(unittest.TestCase):
    """En-têtes, textes, identifiants et montants mis en forme."""

    def test_norm(self) -> None:
        """Minuscules, sans accent ni séparateur."""
        self.assertEqual(_norm(" N° Écriture "), "necriture")
        self.assertEqual(_norm("Date_Pièce (jour)"), "datepiecejour")
        self.assertEqual(_norm("Num.\u00a0compte/réf-x'"), "numcompterefx")
        self.assertEqual(_norm(None), "")

    def test_nettoyer_texte(self) -> None:
        """Tabulations et retours deviennent des espaces, bords rognés."""
        self.assertEqual(_nettoyer_texte("  a\tb\nc\rd  "), "a b c d")
        self.assertEqual(_nettoyer_texte(None), "")
        self.assertEqual(_nettoyer_texte(12.5), "12.5")

    def test_nombre_texte(self) -> None:
        """Les flottants entiers d'Excel perdent leur « .0 »."""
        self.assertEqual(_nombre_texte(10130000.0), "10130000")
        self.assertEqual(_nombre_texte(401), "401")
        self.assertEqual(_nombre_texte(12.5), "12.5")
        self.assertEqual(_nombre_texte(" 411A "), "411A")
        self.assertEqual(_nombre_texte(None), "")

    def test_fmt_centimes(self) -> None:
        """Centimes -> texte à 2 décimales, signe conservé."""
        self.assertEqual(
            [_fmt_centimes(montant) for montant in (12345, -1250, 5, 0)],
            ["123.45", "-12.50", "0.05", "0.00"],
        )


class TestEntete(unittest.TestCase):
    """Détection de la ligne d'en-tête et synonymes de colonnes."""

    def test_synonymes_et_premiere_colonne(self) -> None:
        """Synonymes reconnus ; un champ garde sa première colonne."""
        self.assertEqual(
            _colonnes_reconnues(
                ["", None, "Débit", "N° écriture", "Compte", "cpte", "C"]
            ),
            {"Debit": 2, "EcritureNum": 3, "CompteNum": 4, "Credit": 6},
        )

    def test_entete_apres_titre(self) -> None:
        """Lignes de titre et lignes absentes sont sautées."""
        lignes_classeur = [
            ("Grand livre 2024",),
            None,
            ("Pièce", "Date", "Compte", "Débit", "Crédit", "Ecriture"),
        ]
        self.assertEqual(
            _trouver_entete(lignes_classeur, module_conversion.OBLIGATOIRES),
            (
                2,
                {
                    "PieceRef": 0,
                    "EcritureDate": 1,
                    "CompteNum": 2,
                    "Debit": 3,
                    "Credit": 4,
                    "EcritureNum": 5,
                },
            ),
        )

    def test_limite_de_recherche(self) -> None:
        """L'en-tête doit figurer dans les 30 premières lignes."""
        lignes_titre: list[module_conversion.LigneXlsx] = [("titre",)] * 29
        self.assertEqual(
            _trouver_entete(
                lignes_titre + [ENTETE_MINIMALE],
                module_conversion.OBLIGATOIRES,
            ),
            (
                29,
                {
                    "EcritureNum": 0,
                    "EcritureDate": 1,
                    "CompteNum": 2,
                    "Debit": 3,
                    "Credit": 4,
                },
            ),
        )
        self.assertIsNone(
            _trouver_entete(
                lignes_titre + [("titre",), ENTETE_MINIMALE],
                module_conversion.OBLIGATOIRES,
            )
        )

    def test_valeur_colonne(self) -> None:
        """Champ absent ou ligne trop courte : None."""
        colonnes = {"CompteNum": 0, "Debit": 3}
        self.assertEqual(
            _valeur_colonne(("411",), colonnes, "CompteNum"), "411"
        )
        self.assertIsNone(_valeur_colonne(("411",), colonnes, "Debit"))
        self.assertIsNone(_valeur_colonne(("411",), colonnes, "Credit"))


class TestDateFec(unittest.TestCase):
    """Dates d'écriture normalisées en AAAAMMJJ, jamais devinées."""

    def test_formats_acceptes(self) -> None:
        """Dates Excel, AAAAMMJJ, JJ/MM/AAAA, séparateurs et JJMMAA."""
        cas_acceptes = [
            (datetime(2024, 1, 5, 13, 30), "20240105"),
            (date(2024, 1, 5), "20240105"),
            ("20240105", "20240105"),
            (20240105, "20240105"),
            ("2024-01-05", "20240105"),
            ("05/01/2024", "20240105"),
            ("05.01.2024", "20240105"),
            ("31 12 1999", "19991231"),
            ("050124", "20240105"),
            ("050169", "20690105"),
            ("050170", "19700105"),
        ]
        for valeur, attendu in cas_acceptes:
            with self.subTest(valeur=valeur):
                self.assertEqual(_date_fec(valeur, "EcritureDate"), attendu)

    def test_refus(self) -> None:
        """Chaque refus est un message explicite citant la colonne."""
        cas_refuses = [
            (
                "31022024",
                "Date invalide en colonne EcritureDate : '31022024' "
                "(ordre JJMMAAAA)",
            ),
            (
                "20241332",
                "Date invalide en colonne EcritureDate : '20241332' "
                "(ordre AAAAMMJJ)",
            ),
            (
                "310224",
                "Date invalide en colonne EcritureDate : '310224' "
                "(ordre JJMMAA)",
            ),
            (
                "01010000",
                "Date ambigue en colonne EcritureDate : '01010000' (ni "
                "AAAAMMJJ ni JJMMAAAA plausibles : re-exportez la colonne "
                "en date Excel)",
            ),
            (
                "janvier",
                "Date invalide en colonne EcritureDate : 'janvier' "
                "(formats attendus : date Excel, AAAAMMJJ, JJ/MM/AAAA)",
            ),
            (
                None,
                "Date invalide en colonne EcritureDate : None "
                "(formats attendus : date Excel, AAAAMMJJ, JJ/MM/AAAA)",
            ),
        ]
        for valeur, message_attendu in cas_refuses:
            with self.subTest(valeur=valeur):
                with self.assertRaises(ErreurFEC) as contexte_erreur:
                    _date_fec(valeur, "EcritureDate")
                self.assertEqual(
                    str(contexte_erreur.exception), message_attendu
                )


class TestCentimes(unittest.TestCase):
    """Montants en centimes : tolérance 0, aucun arrondi silencieux."""

    def test_montants_acceptes(self) -> None:
        """Vides, entiers, décimaux, flottants imprécis et textes."""
        cas_acceptes: list[tuple[object, int]] = [
            (None, 0),
            ("   ", 0),
            (12, 1200),
            (12.5, 1250),
            (0.1 + 0.2, 30),
            (-3.75, -375),
            ("1 234,56", 123456),
            ("-12.5", -1250),
        ]
        for valeur, attendu in cas_acceptes:
            with self.subTest(valeur=valeur):
                self.assertEqual(_centimes(valeur, "Debit"), attendu)

    def test_nombre_a_trois_decimales_refuse(self) -> None:
        """Un nombre à plus de 2 décimales est refusé, jamais arrondi."""
        with self.assertRaises(ErreurFEC) as contexte_erreur:
            _centimes(12.345, "Debit")
        self.assertEqual(
            str(contexte_erreur.exception),
            "Arrondi silencieux interdit : 12.345000 en colonne Debit "
            "(plus de 2 decimales, tolerance 0)",
        )

    def test_texte_refuse(self) -> None:
        """Texte à 3 décimales ou non numérique : refus explicite."""
        for valeur in ("12,345", "abc"):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ErreurMontant):
                    _centimes(valeur, "Credit")


class TestDateQuadra(unittest.TestCase):
    """Date Quadra : mois et année de la Période, jour de la colonne Jour."""

    def test_dates_acceptees(self) -> None:
        """Période texte ou date Excel, jour nombre ou texte."""
        self.assertEqual(_date_quadra("01/03/2024", 15, "N 7"), "20240315")
        self.assertEqual(
            _date_quadra(datetime(2024, 2, 1), " 29 ", "N 7"), "20240229"
        )

    def test_refus(self) -> None:
        """Jour hors 1-31, jour inexistant, période invalide."""
        cas_refuses: list[tuple[object, object, str]] = [
            (
                "01/03/2024",
                0,
                "Jour invalide (0) en colonne N 7/Jour : CONCORDE attend "
                "un numero de jour 1-31.",
            ),
            (
                "01/03/2024",
                None,
                "Jour invalide (None) en colonne N 7/Jour : CONCORDE "
                "attend un numero de jour 1-31.",
            ),
            (
                "01/02/2023",
                29,
                "Date invalide : jour 29 inexistant en 02/2023 (colonnes "
                "Periode/Jour).",
            ),
            (
                "mars",
                5,
                "Date invalide en colonne N 7/Periode : 'mars' (formats "
                "attendus : date Excel, AAAAMMJJ, JJ/MM/AAAA)",
            ),
        ]
        for periode, jour, message_attendu in cas_refuses:
            with self.subTest(periode=periode, jour=jour):
                with self.assertRaises(ErreurFEC) as contexte_erreur:
                    _date_quadra(periode, jour, "N 7")
                self.assertEqual(
                    str(contexte_erreur.exception), message_attendu
                )


class TestConversionStandard(unittest.TestCase):
    """xlsx_vers_fec de bout en bout sur un en-tête FEC standard."""

    def test_classeur_complet(self) -> None:
        """Titre sauté, synonymes, nombres Excel, montants à 2 décimales."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ("Export comptable",),
            ENTETE_STANDARD,
            (
                "VT",
                "Ventes",
                5535,
                "05/01/2024",
                411000,
                "Clients",
                "F1",
                "Facture\tDupont",
                100.5,
                None,
            ),
            (
                "VT",
                "Ventes",
                5535.0,
                "20240105",
                "706000",
                "Ventes",
                "F1",
                "Facture Dupont",
                "",
                "100,50",
            ),
            (None, None, None, None, None, None, None, "Sous-total"),
        ]
        self.assertEqual(
            convertir_lignes(lignes_classeur),
            fec_attendu(
                ligne_fec_attendue(
                    journal="VT",
                    journal_lib="Ventes",
                    numero="5535",
                    date_ecriture="20240105",
                    compte="411000",
                    compte_lib="Clients",
                    piece="F1",
                    libelle="Facture Dupont",
                    debit="100.50",
                    credit="0.00",
                ),
                ligne_fec_attendue(
                    journal="VT",
                    journal_lib="Ventes",
                    numero="5535",
                    date_ecriture="20240105",
                    compte="706000",
                    compte_lib="Ventes",
                    piece="F1",
                    libelle="Facture Dupont",
                    debit="0.00",
                    credit="100.50",
                ),
            ),
        )

    def test_valeurs_par_defaut(self) -> None:
        """Journal par défaut, libellé repris de la pièce ou du numéro."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ("Ecriture", "Date", "Compte", "Pièce", "Débit", "Crédit"),
            ("E1", "05/01/2024", "512", "CHQ12", 20, None),
            ("E1", "05/01/2024", "411", None, None, 20),
        ]
        self.assertEqual(
            convertir_lignes(lignes_classeur),
            fec_attendu(
                ligne_fec_attendue(
                    journal="CONCORDE",
                    numero="E1",
                    date_ecriture="20240105",
                    compte="512",
                    piece="CHQ12",
                    libelle="CHQ12",
                    debit="20.00",
                    credit="0.00",
                ),
                ligne_fec_attendue(
                    journal="CONCORDE",
                    numero="E1",
                    date_ecriture="20240105",
                    compte="411",
                    libelle="Ecriture E1",
                    debit="0.00",
                    credit="20.00",
                ),
            ),
        )

    def test_lecteur_interne_identique(self) -> None:
        """Sans openpyxl, le lecteur interne produit le même FEC."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_STANDARD,
            (
                "OD",
                "Divers",
                7,
                "20240105",
                471,
                "Attente",
                "",
                "Virement",
                12.34,
                None,
            ),
        ]
        fec_openpyxl = convertir_lignes(lignes_classeur)
        with sans_openpyxl():
            fec_interne = convertir_lignes(lignes_classeur)
        self.assertEqual(fec_interne, fec_openpyxl)
        self.assertEqual(
            fec_interne,
            fec_attendu(
                ligne_fec_attendue(
                    journal="OD",
                    journal_lib="Divers",
                    numero="7",
                    date_ecriture="20240105",
                    compte="471",
                    compte_lib="Attente",
                    libelle="Virement",
                    debit="12.34",
                    credit="0.00",
                )
            ),
        )

    def test_date_excel_lecteur_interne(self) -> None:
        """Une série Excel au style date devient AAAAMMJJ (lecteur interne)."""
        classeur = classeur_xlsx(
            feuille_xml(
                [
                    '<row r="1">'
                    '<c r="A1" t="inlineStr"><is><t>Ecriture</t></is></c>'
                    '<c r="B1" t="inlineStr"><is><t>Date</t></is></c>'
                    '<c r="C1" t="inlineStr"><is><t>Compte</t></is></c>'
                    '<c r="D1" t="inlineStr"><is><t>Debit</t></is></c>'
                    '<c r="E1" t="inlineStr"><is><t>Credit</t></is></c>'
                    "</row>",
                    '<row r="2"><c r="A2"><v>1</v></c>'
                    '<c r="B2" s="1"><v>45296</v></c>'
                    '<c r="C2"><v>512</v></c><c r="D2"><v>5</v></c></row>',
                ]
            ),
            STYLES_AVEC_STYLE_NOMME,
        )
        fec_openpyxl = xlsx_vers_fec(classeur, NOM_FICHIER_ESSAI)
        with sans_openpyxl():
            fec_interne = xlsx_vers_fec(classeur, NOM_FICHIER_ESSAI)
        self.assertEqual(fec_interne, fec_openpyxl)
        self.assertEqual(
            fec_interne,
            fec_attendu(
                ligne_fec_attendue(
                    journal="CONCORDE",
                    numero="1",
                    date_ecriture="20240105",
                    compte="512",
                    libelle="Ecriture 1",
                    debit="5.00",
                    credit="0.00",
                )
            ),
        )

    def test_ligne_absente_ignoree(self) -> None:
        """Une ligne absente (None) rendue par le lecteur est sautée."""
        lignes_lues: list[module_conversion.LigneXlsx] = [
            ENTETE_MINIMALE,
            None,
            ("E2", "20240105", "512", None, 1),
        ]
        with mock.patch.object(
            module_conversion,
            "_lire_avec_openpyxl",
            return_value=lignes_lues,
        ):
            fec_produit = xlsx_vers_fec(b"PK", NOM_FICHIER_ESSAI)
        self.assertEqual(
            fec_produit,
            fec_attendu(
                ligne_fec_attendue(
                    journal="CONCORDE",
                    numero="E2",
                    date_ecriture="20240105",
                    compte="512",
                    libelle="Ecriture E2",
                    debit="0.00",
                    credit="1.00",
                )
            ),
        )

    def test_refus_des_lignes_incompletes(self) -> None:
        """Numéro d'écriture ou compte manquant : refus explicite."""
        self.assertEqual(
            message_erreur(
                self,
                ErreurFEC,
                None,
                [ENTETE_MINIMALE, (None, "20240105", "512", 1, None)],
            ),
            "Ligne sans numero d'ecriture (colonne EcritureNum vide) : "
            "CONCORDE ne devine jamais un identifiant.",
        )
        self.assertEqual(
            message_erreur(
                self,
                ErreurFEC,
                None,
                [ENTETE_MINIMALE, ("E9", "20240105", None, 1, None)],
            ),
            "Ecriture E9 sans numero de compte (colonne CompteNum vide) : "
            "CONCORDE ne devine jamais un compte.",
        )

    def test_refus_classeur_sans_donnees(self) -> None:
        """En-tête sans ligne exploitable : erreur nommant le fichier."""
        self.assertTrue(
            message_erreur(
                self,
                ErreurFEC,
                None,
                [ENTETE_MINIMALE],
            ).startswith(
                "Aucune ligne d'ecriture exploitable dans 'essai.xlsx' "
                "apres l'en-tete"
            )
        )

    def test_refus_entete_introuvable(self) -> None:
        """Sans colonnes obligatoires, aucune colonne n'est devinée."""
        self.assertTrue(
            message_erreur(
                self, ErreurFEC, None, [("Code", "Montant"), ("A", 1)]
            ).startswith(
                "Ligne d'en-tete introuvable dans 'essai.xlsx' : CONCORDE "
                "attend au minimum les colonnes EcritureNum, EcritureDate, "
                "CompteNum, Debit, Credit"
            )
        )

    def test_refus_fichiers_non_xlsx(self) -> None:
        """Contenu non zip : diagnostic de ce qui a été reçu."""
        self.assertEqual(
            message_erreur(self, ErreurFEC, None, b""),
            "Fichier 'essai.xlsx' : fichier vide (0 octet) — vérifiez le "
            "fichier joint.",
        )
        self.assertIn(
            "vieux format .xls (Excel 97-2003, signature OLE2)",
            message_erreur(self, ErreurFEC, None, SIGNATURE_OLE2 + b"x"),
        )
        self.assertIn(
            "(premiers octets : 44 61 74 65 3b 43 0a ff = Date;C..)",
            message_erreur(self, ErreurFEC, None, b"Date;C\n\xff;suite"),
        )

    def test_refus_zip_illisible(self) -> None:
        """Archive invalide : « illisible », avec ou sans openpyxl."""
        archive_cassee = b"PK\x03\x04tronque"
        for action in (None, sans_openpyxl()):
            with self.subTest(openpyxl=action is None):
                self.assertTrue(
                    message_erreur(
                        self, ErreurFEC, action, archive_cassee
                    ).startswith("Classeur Excel illisible (essai.xlsx) : ")
                )

    def test_erreur_du_lecteur_interne_transmise(self) -> None:
        """Sans openpyxl, l'erreur explicite du lecteur interne remonte."""
        archive_sans_feuille = classeur_xlsx(
            FEUILLE_UN_TEXTE, chemin_feuille=None
        )
        self.assertEqual(
            message_erreur(
                self, ErreurFEC, sans_openpyxl(), archive_sans_feuille
            ),
            "Aucune feuille de calcul trouvee dans 'essai.xlsx'.",
        )

    def test_erreur_fec_du_lecteur_openpyxl_transmise(self) -> None:
        """Une ErreurFEC levée à la lecture remonte telle quelle."""
        erreur_lecture = ErreurFEC("lecture refusée")
        remplacement = mock.patch.object(
            module_conversion,
            "_lire_avec_openpyxl",
            side_effect=erreur_lecture,
        )
        self.assertEqual(
            message_erreur(self, ErreurFEC, remplacement, b"PK"),
            "lecture refusée",
        )

    def test_montant_texte_a_trois_decimales(self) -> None:
        """Un montant texte à 3 décimales est refusé (tolérance 0)."""
        self.assertIn(
            "Arrondi silencieux interdit",
            message_erreur(
                self,
                ErreurMontant,
                None,
                [
                    ENTETE_MINIMALE,
                    ("E1", "20240105", "512", "1,005", None),
                ],
            ),
        )


class TestConversionQuadra(unittest.TestCase):
    """Export « Liste des écritures » Cegid Quadra : cascades explicites."""

    def test_cascade_par_libelle(self) -> None:
        """Lignes entrelacées regroupées par (journal, date, libellé)."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_QUADRA,
            ligne_quadra(101, 5, 411, "Facture A", 100, None, piece="FA"),
            ligne_quadra(102, 6, 411, "Facture B", 50, None),
            ligne_quadra(103, 5, 706, "Facture A", None, 100, piece="FA"),
            ligne_quadra(104, 6, 706, "Facture B", None, 50),
            ligne_quadra(None, None, None, "", None, None, type_ligne=""),
        ]
        self.assertEqual(
            convertir_lignes(lignes_classeur),
            fec_attendu(
                ligne_quadra_attendue(
                    "101", 5, "411", "Facture A", "100.00", "0.00", "FA"
                ),
                ligne_quadra_attendue(
                    "101", 5, "706", "Facture A", "0.00", "100.00", "FA"
                ),
                ligne_quadra_attendue(
                    "102", 6, "411", "Facture B", "50.00", "0.00"
                ),
                ligne_quadra_attendue(
                    "102", 6, "706", "Facture B", "0.00", "50.00"
                ),
            ),
        )

    def test_cascade_par_date(self) -> None:
        """Libellés soldés ensemble sur (journal, date), après cascade 1.

        La paire « Frais », soldée dès la cascade 1, n'est pas reprise.
        """
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_QUADRA,
            ligne_quadra(199, 8, 627, "Frais", 5, None),
            ligne_quadra(200, 8, 512, "Frais", None, 5),
            ligne_quadra(201, 8, 512, "Encaissement", 100, None),
            ligne_quadra(202, 8, 411, "Client X", None, 60),
            ligne_quadra(203, 8, 411, "", None, 40),
        ]
        with self.assertLogs("core.xlsx_vers_fec", "INFO") as journal_log:
            fec_produit = convertir_lignes(lignes_classeur)
        self.assertEqual(
            fec_produit,
            fec_attendu(
                ligne_quadra_attendue(
                    "199", 8, "627", "Frais", "5.00", "0.00"
                ),
                ligne_quadra_attendue(
                    "199", 8, "512", "Frais", "0.00", "5.00"
                ),
                ligne_quadra_attendue(
                    "201", 8, "512", "Encaissement", "100.00", "0.00"
                ),
                ligne_quadra_attendue(
                    "201", 8, "411", "Client X", "0.00", "60.00"
                ),
                ligne_quadra_attendue(
                    "201", 8, "411", "Ecriture 203", "0.00", "40.00"
                ),
            ),
        )
        self.assertEqual(
            journal_log.output,
            [
                "INFO:core.xlsx_vers_fec:Quadra essai.xlsx : cascade 1 "
                "laisse 3 ligne(s) non soldee(s), consolidation par "
                "(journal, date)."
            ],
        )

    def test_cascade_par_journal(self) -> None:
        """Dates différentes : une écriture consolidée par journal."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_QUADRA,
            ligne_quadra(301, 9, 471, "Avance", 30, None),
            ligne_quadra(302, 10, 512, "Retour", None, 30),
        ]
        with self.assertLogs("core.xlsx_vers_fec", "WARNING") as journal_log:
            fec_produit = convertir_lignes(lignes_classeur)
        self.assertEqual(
            fec_produit,
            fec_attendu(
                ligne_quadra_attendue(
                    "301", 9, "471", "Avance", "30.00", "0.00"
                ),
                ligne_quadra_attendue(
                    "301", 10, "512", "Retour", "0.00", "30.00"
                ),
            ),
        )
        self.assertEqual(len(journal_log.records), 1)
        self.assertIn("2 ligne(s) encore non soldee(s)", journal_log.output[0])

    def test_doublons_distingues(self) -> None:
        """Lignes identiques d'une écriture : NumUniq apposé au libellé."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_QUADRA,
            ligne_quadra(401.0, 3, 411, "Lot", 50, None),
            ligne_quadra(402.0, 3, 411, "Lot", 50, None),
            ligne_quadra(403.0, 3, 706, "Lot", None, 100),
        ]
        self.assertEqual(
            convertir_lignes(lignes_classeur),
            fec_attendu(
                ligne_quadra_attendue("401", 3, "411", "Lot", "50.00", "0.00"),
                ligne_quadra_attendue(
                    "401", 3, "411", "Lot [402]", "50.00", "0.00"
                ),
                ligne_quadra_attendue(
                    "401", 3, "706", "Lot", "0.00", "100.00"
                ),
            ),
        )

    def test_ligne_absente_ignoree(self) -> None:
        """Une ligne absente (None) après l'en-tête est sautée."""
        lignes_lues: list[module_conversion.LigneXlsx] = [
            ENTETE_QUADRA,
            None,
            ligne_quadra(501, 2, 512, "Solde", 0, 0),
        ]
        entete_quadra = _trouver_entete(
            lignes_lues, module_conversion.QUADRA_OBLIGATOIRES
        )
        if entete_quadra is None:
            self.fail("En-tête Quadra non reconnu.")
        self.assertEqual(
            _convertir_quadra(lignes_lues, *entete_quadra, NOM_FICHIER_ESSAI),
            fec_attendu(
                ligne_quadra_attendue("501", 2, "512", "Solde", "0.00", "0.00")
            ),
        )

    def test_residu_non_soldable(self) -> None:
        """Un journal déséquilibré est refusé avec son détail chiffré."""
        lignes_classeur: list[Sequence[ValeurCellule]] = [
            ENTETE_QUADRA,
            ligne_quadra(601, 4, 512, "A", 100, None),
            ligne_quadra(602, 4, 411, "B", None, 90),
            ligne_quadra(603, 4, 401, "C", 1, None, journal="AC"),
        ]
        with self.assertLogs("core.xlsx_vers_fec", "INFO"):
            message_obtenu = message_erreur(
                self, ErreurFEC, None, lignes_classeur
            )
        self.assertEqual(
            message_obtenu,
            "Lignes non soldables dans 'essai.xlsx' apres les cascades "
            "(journal+date+libelle, journal+date, journal) : CONCORDE ne "
            "cree jamais une ecriture desequilibree. Detail par journal : "
            "AC : 1 ligne(s), debit 100 != credit 0 centimes (ecart 100), "
            "VE : 2 ligne(s), debit 10000 != credit 9000 centimes (ecart "
            "1000). Verifiez l'export Quadra (tranchee complete).",
        )

    def test_refus_des_lignes_invalides(self) -> None:
        """NumUniq, compte, TypeLigne ou journal invalides : refus."""
        cas_refuses: list[tuple[tuple[ValeurCellule, ...], str]] = [
            (
                ligne_quadra(None, 2, 512, "A", 1, None),
                "Ligne sans NumUniq dans 'essai.xlsx' : CONCORDE ne "
                "devine jamais un identifiant.",
            ),
            (
                ligne_quadra(701, 2, None, "A", 1, None),
                "Ligne NumUniq 701 sans numero de compte : CONCORDE ne "
                "devine jamais un compte.",
            ),
            (
                ligne_quadra(702, 2, 512, "A", 1, None, type_ligne="T"),
                "TypeLigne 'T' inconnu (NumUniq 702) : CONCORDE ne traite "
                "que les lignes d'ecriture 'E'. Aucune ligne devinee.",
            ),
            (
                ligne_quadra(703, 2, 512, "A", 1, None, journal=" "),
                "Ligne NumUniq 703 sans journal : CONCORDE ne devine "
                "jamais un journal.",
            ),
        ]
        for ligne_refusee, message_attendu in cas_refuses:
            with self.subTest(message=message_attendu):
                self.assertEqual(
                    message_erreur(
                        self, ErreurFEC, None, [ENTETE_QUADRA, ligne_refusee]
                    ),
                    message_attendu,
                )

    def test_refus_export_sans_ligne(self) -> None:
        """En-tête Quadra seul : erreur citant la ligne d'en-tête."""
        self.assertEqual(
            message_erreur(self, ErreurFEC, None, [("Titre",), ENTETE_QUADRA]),
            "Aucune ligne d'ecriture exploitable dans 'essai.xlsx' apres "
            "l'en-tete (ligne 2).",
        )


if __name__ == "__main__":
    unittest.main()
