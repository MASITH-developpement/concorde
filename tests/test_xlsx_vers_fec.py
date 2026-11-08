# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la lecture .xlsx sans openpyxl (core/xlsx_vers_fec.py)."""

import io
import unittest
import zipfile
from datetime import date

from core.xlsx_vers_fec import _lire_xlsx_stdlib

ESPACE_TABLEUR = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ESPACE_RELATIONS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
# Un style nommé (cellStyleXfs) précède cellXfs ; le style de cellule 1
# est une date (format intégré 14).
STYLES_AVEC_STYLE_NOMME = (
    '<styleSheet xmlns="%s">'
    '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" xfId="0"/>'
    '<xf numFmtId="14" xfId="0"/></cellXfs>'
    "</styleSheet>" % ESPACE_TABLEUR
)
CLASSEUR_UNE_FEUILLE = (
    '<workbook xmlns="%s" xmlns:r="%s"><sheets>'
    '<sheet name="FEC" sheetId="1" r:id="rId1"/>'
    "</sheets></workbook>" % (ESPACE_TABLEUR, ESPACE_RELATIONS)
)
RELATIONS_CLASSEUR = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" '
    'Target="worksheets/sheet1.xml"/></Relationships>'
)
# A1 : série Excel 45296 au style date ; B1 : nombre sans style.
FEUILLE_DATE_ET_NOMBRE = (
    '<worksheet xmlns="%s"><sheetData><row r="1">'
    '<c r="A1" s="1"><v>45296</v></c><c r="B1"><v>12</v></c>'
    "</row></sheetData></worksheet>" % ESPACE_TABLEUR
)


def classeur_xlsx(styles_xml: str) -> bytes:
    """Construit un .xlsx minimal (une feuille) avec les styles donnés.

    Rôle : classeur de test lisible par _lire_xlsx_stdlib.
    Paramètres : styles_xml (contenu de xl/styles.xml).
    Retour : les octets du classeur zippé.
    Erreurs : aucune.
    Usages : TestStylesDate.
    """
    tampon_classeur = io.BytesIO()
    with zipfile.ZipFile(tampon_classeur, "w") as archive:
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/workbook.xml", CLASSEUR_UNE_FEUILLE)
        archive.writestr("xl/_rels/workbook.xml.rels", RELATIONS_CLASSEUR)
        archive.writestr("xl/worksheets/sheet1.xml", FEUILLE_DATE_ET_NOMBRE)
    return tampon_classeur.getvalue()


class TestStylesDate(unittest.TestCase):
    """Styles date : l'attribut s d'une cellule indexe cellXfs seul."""

    def test_style_nomme_ne_decale_pas_les_dates(self) -> None:
        """Une cellule au style date est lue comme une date."""
        lignes_lues = _lire_xlsx_stdlib(classeur_xlsx(STYLES_AVEC_STYLE_NOMME))
        self.assertEqual(lignes_lues, [(date(2024, 1, 5), 12)])


if __name__ == "__main__":
    unittest.main()
