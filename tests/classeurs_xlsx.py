# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Fabrication de classeurs .xlsx de test (zip + XML), commune aux tests.

Rôle : écrire à la main les parties d'un classeur SpreadsheetML (cellules,
lignes, feuille, workbook, relations, archive zip) pour que chaque test
maîtrise exactement le contenu lu par les lecteurs de CONCORDE.
Usages : tests/test_xlsx_vers_fec.py, tests/test_mapping.py.
"""

import html
import io
import zipfile
from collections.abc import Mapping, Sequence

from core.xlsx_ecrire import lettres_colonne

# Espace de noms principal d'un classeur SpreadsheetML.
ESPACE_TABLEUR = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
# Espace de noms des relations Office (attribut r:id, type des relations).
ESPACE_RELATIONS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
# Racine des espaces de noms d'un paquet Open XML.
ESPACE_PAQUET = "http://schemas.openxmlformats.org/package/2006"
# Espace de noms des fichiers .rels d'un paquet Open XML.
ESPACE_RELATIONS_PAQUET = ESPACE_PAQUET + "/relationships"
# Chemin de la première feuille dans l'archive d'un classeur.
CHEMIN_PREMIERE_FEUILLE = "xl/worksheets/sheet1.xml"

# Valeur que les classeurs de test savent écrire dans une cellule.
ValeurCellule = str | int | float | None


def cellule_texte(reference: str, texte: str) -> str:
    """Rend le XML d'une cellule texte en ligne (inlineStr).

    Rôle : écrire une cellule texte comme Excel sans table partagée ; le
    texte est échappé pour XML.
    Paramètres : reference, référence de cellule (« A1 ») ou « » pour une
    cellule sans attribut r ; texte, contenu de la cellule.
    Retour : fragment XML <c t="inlineStr">.
    Erreurs : aucune.
    Usages : cellule_xml, tests de lecture des cellules (test_mapping).
    """
    attribut_reference = ' r="%s"' % reference if reference else ""
    return '<c%s t="inlineStr"><is><t>%s</t></is></c>' % (
        attribut_reference,
        html.escape(texte, quote=False),
    )


def cellule_brute(reference: str, type_cellule: str, valeur: str) -> str:
    """Rend le XML d'une cellule <c> avec une balise <v>.

    Rôle : écrire une cellule nombre, booléen, chaîne partagée ou erreur.
    Paramètres : reference, référence (« B3 ») ; type_cellule, attribut t
    (« » pour l'omettre) ; valeur, texte de <v>.
    Retour : fragment XML <c><v>…</v></c>.
    Erreurs : aucune.
    Usages : cellule_xml, tests de typage des cellules (test_mapping).
    """
    attribut_type = ' t="%s"' % type_cellule if type_cellule else ""
    return '<c r="%s"%s><v>%s</v></c>' % (reference, attribut_type, valeur)


def cellule_xml(reference: str, valeur: ValeurCellule) -> str:
    """Rend l'élément <c> d'une cellule selon le type Python de sa valeur.

    Rôle : booléen en t="b", nombre en valeur brute, texte en inlineStr.
    Paramètres : reference (ex. « B3 ») ; valeur de la cellule.
    Retour : le XML de la cellule, ou « » pour None (cellule absente).
    Erreurs : aucune.
    Usages : ligne_valeurs.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return cellule_brute(reference, "b", "%d" % valeur)
    if isinstance(valeur, (int, float)):
        return cellule_brute(reference, "", repr(valeur))
    return cellule_texte(reference, valeur)


def ligne_xml(numero: int, cellules: Sequence[str]) -> str:
    """Assemble une ligne <row> à partir de fragments de cellules.

    Rôle : composer une ligne de feuille.
    Paramètres : numero, numéro de ligne Excel (1 = première) ; cellules,
    fragments XML produits par cellule_texte / cellule_brute / cellule_xml.
    Retour : fragment XML <row>.
    Erreurs : aucune.
    Usages : ligne_valeurs, tests de feuilles construites à la main.
    """
    return '<row r="%d">%s</row>' % (numero, "".join(cellules))


def ligne_valeurs(numero: int, valeurs: Sequence[ValeurCellule]) -> str:
    """Ligne <row> dont les valeurs occupent les colonnes A, B, C…

    Rôle : écrire une ligne de tableau ; None laisse la cellule absente.
    Paramètres : numero, numéro de ligne Excel ; valeurs, dans l'ordre des
    colonnes.
    Retour : fragment XML <row>.
    Erreurs : aucune.
    Usages : feuille_depuis_lignes.
    """
    return ligne_xml(
        numero,
        [
            cellule_xml("%s%d" % (lettres_colonne(index), numero), valeur)
            for index, valeur in enumerate(valeurs)
        ],
    )


def feuille_xml(lignes: Sequence[str]) -> str:
    """Document <worksheet> complet à partir de lignes <row>.

    Rôle : éviter de répéter l'enveloppe worksheet/sheetData.
    Paramètres : lignes, fragments XML <row>.
    Retour : le XML complet de la feuille.
    Erreurs : aucune.
    Usages : feuille_depuis_lignes, tests de lecture de feuille.
    """
    return '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (
        ESPACE_TABLEUR,
        "".join(lignes),
    )


def feuille_depuis_lignes(lignes: Sequence[Sequence[ValeurCellule]]) -> str:
    """Construit le XML d'une feuille à partir de lignes de valeurs.

    Rôle : écrire un tableau dont la première entrée est la ligne 1.
    Paramètres : lignes, une séquence de valeurs par ligne Excel.
    Retour : le XML complet de la feuille.
    Erreurs : aucune.
    Usages : convertir_lignes, TestLectureOpenpyxl (test_xlsx_vers_fec) ;
    feuille_tableau (test_mapping).
    """
    return feuille_xml(
        [
            ligne_valeurs(numero_ligne, valeurs)
            for numero_ligne, valeurs in enumerate(lignes, start=1)
        ]
    )


def classeur_feuilles_xml(noms_feuilles: Sequence[str]) -> str:
    """Rend le xl/workbook.xml déclarant les feuilles données.

    Rôle : déclarer les feuilles dans l'ordre du classeur ; la feuille de
    rang n porte sheetId n et la relation rIdn.
    Paramètres : noms_feuilles, nom de chaque feuille (vide = aucune).
    Retour : le XML du classeur.
    Erreurs : aucune.
    Usages : CLASSEUR_UNE_FEUILLE, CLASSEUR_SANS_FEUILLE
    (test_xlsx_vers_fec) ; classeur_feuilles (test_mapping).
    """
    declarations_feuilles = "".join(
        '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (nom, rang, rang)
        for rang, nom in enumerate(noms_feuilles, start=1)
    )
    return (
        '<workbook xmlns="%s" xmlns:r="%s"><sheets>%s</sheets></workbook>'
        % (ESPACE_TABLEUR, ESPACE_RELATIONS, declarations_feuilles)
    )


def relations_classeur_xml(cibles_par_identifiant: Mapping[str, str]) -> str:
    """Rend le xl/_rels/workbook.xml.rels reliant le classeur aux feuilles.

    Rôle : écrire une relation de type worksheet par feuille.
    Paramètres : cibles_par_identifiant, {identifiant (« rId1 »): attribut
    Target de la feuille}.
    Retour : le XML des relations.
    Erreurs : aucune.
    Usages : RELATIONS_CLASSEUR, tests de recherche de feuille
    (test_xlsx_vers_fec) ; classeur_feuilles (test_mapping).
    """
    relations = "".join(
        '<Relationship Id="%s" Type="%s/worksheet" Target="%s"/>'
        % (identifiant, ESPACE_RELATIONS, cible)
        for identifiant, cible in cibles_par_identifiant.items()
    )
    return '<Relationships xmlns="%s">%s</Relationships>' % (
        ESPACE_RELATIONS_PAQUET,
        relations,
    )


def archive_xlsx(parties: Mapping[str, str]) -> bytes:
    """Archive zip (octets) contenant les parties XML données.

    Rôle : fabriquer un .xlsx en mémoire, parties écrites dans l'ordre.
    Paramètres : parties, {chemin dans l'archive: contenu XML}.
    Retour : octets de l'archive (commence par « PK »).
    Erreurs : aucune.
    Usages : classeur_xlsx (test_xlsx_vers_fec) ; classeur_feuilles et
    tests sans classeur (test_mapping).
    """
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        for chemin, contenu in parties.items():
            archive.writestr(chemin, contenu)
    return tampon.getvalue()
