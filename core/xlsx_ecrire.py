# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écriture de classeurs xlsx — bibliothèque standard uniquement (zipfile).

Chaque feuille est écrite en flux dans le zip : 150 000 lignes passent
sans charger tout le classeur en mémoire.

Valeurs acceptées dans une cellule :
  str            texte (chaîne en ligne, pas de table partagée)
  int            nombre entier
  Centimes(n)    montant : écrit en euros exacts (n / 100, sans float)
  date           date Excel (numéro de série), format JJ/MM/AAAA
  None / ""      cellule vide
"""

import zipfile
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from os import PathLike

_EPOQUE = date(1899, 12, 30)

# Préfixes d'URL des espaces de noms Office Open XML, communs à plusieurs
# parties du classeur.
_SCHEMAS_OPENXML = "http://schemas.openxmlformats.org/"
_DOC_OFFICE = _SCHEMAS_OPENXML + "officeDocument/2006/relationships"
_TYPE_OFFICE = "application/vnd.openxmlformats-officedocument."
_ENTETE_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

# Une feuille : (nom, entêtes, lignes de cellules).
Feuille = tuple[str, Sequence[str], Iterable[Sequence[object]]]


class Centimes(int):
    """Montant en centimes à écrire en euros dans la cellule (exact)."""


def echapper_xml(texte: str, entites: dict[str, str] | None = None) -> str:
    """Échappe un texte pour l'écrire dans un document XML.

    Rôle : remplacer « & », « < », « > » (et les entités demandées) ;
    même résultat que ``xml.sax.saxutils.escape``, sans importer le
    paquet XML de la bibliothèque standard (écriture seulement).
    Paramètres : texte ; entites — remplacements supplémentaires,
    ex. ``{'"': "&quot;"}`` pour une valeur d'attribut.
    Retour : le texte échappé.
    Erreurs : aucune.
    Usages : écriture des cellules, des en-têtes et des noms de feuilles.
    """
    texte = (
        texte.replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;")
    )
    for caractere, entite in (entites or {}).items():
        texte = texte.replace(caractere, entite)
    return texte


def lettres_colonne(index_colonne: int) -> str:
    """Lettres Excel d'une colonne : 0 -> 'A', 25 -> 'Z', 26 -> 'AA'.

    Rôle : composer ou citer la référence d'une cellule.
    Paramètres : index_colonne, index de colonne à partir de 0.
    Retour : les lettres de la colonne.
    Erreurs : aucune.
    Usages : ecrire_xlsx, mapping (colonnes citées dans les erreurs),
    tests/classeurs_xlsx.py.
    """
    lettres = ""
    reste = index_colonne + 1
    while reste:
        reste, chiffre = divmod(reste - 1, 26)
        lettres = chr(65 + chiffre) + lettres
    return lettres


def euros_texte(c: int, separateur: str = ".") -> str:
    """Convertit un montant en centimes en texte décimal exact.

    Rôle : écrire un montant sans passer par un float.
    Paramètres : c, montant en centimes (entier, signé) ; separateur,
    séparateur décimal ('.' par défaut, ',' pour l'affichage français).
    Retour : texte, ex. -123456 -> '-1234.56'.
    Erreurs : aucune (int() lève TypeError / ValueError si c n'est pas
    convertible en entier).
    Usages : cellules Centimes, comptes, analyser, comparaison, passerelle,
    telecharger, migration.
    """
    signe = "-" if c < 0 else ""
    c = abs(int(c))
    return "%s%d%s%02d" % (signe, c // 100, separateur, c % 100)


def _nettoyer(texte: str) -> str:
    """Retire les caractères de contrôle interdits en XML 1.0.

    Tabulation et retours à la ligne sont conservés.
    """
    return "".join(ch for ch in texte if ch in "\t\n\r" or ord(ch) >= 32)


def _cellule(ref: str, v: object) -> str:
    """Rend le XML d'une cellule de référence `ref` selon le type de `v`.

    Retourne une chaîne vide pour une cellule vide (None ou "").
    """
    if v is None or v == "":
        return ""
    if isinstance(v, Centimes):
        return '<c r="%s" s="2"><v>%s</v></c>' % (ref, euros_texte(v))
    if isinstance(v, bool):
        return '<c r="%s" t="b"><v>%d</v></c>' % (ref, int(v))
    if isinstance(v, int):
        return '<c r="%s"><v>%d</v></c>' % (ref, v)
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return '<c r="%s" s="1"><v>%d</v></c>' % (ref, (v - _EPOQUE).days)
    return (
        '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
        % (ref, echapper_xml(_nettoyer(str(v))))
    )


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="4"><xf/>
<xf numFmtId="164" applyNumberFormat="1"/>
<xf numFmtId="4" applyNumberFormat="1"/>
<xf fontId="1" applyFont="1"/></cellXfs>
<cellStyles count="1">\
<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def ecrire_xlsx(
    chemin: str | PathLike[str], feuilles: Iterable[Feuille]
) -> dict[str, int]:
    """Écrit un classeur xlsx en flux.

    Rôle : produire un classeur sans dépendance externe.
    Paramètres : chemin, fichier à créer (écrasé s'il existe) ; feuilles,
    itérable de (nom, entetes, lignes) — lignes = itérable de listes de
    valeurs (voir l'en-tête du module). La première ligne (entêtes) est en
    gras et figée.
    Retour : {nom de feuille (tronqué à 31 caractères): nombre de lignes de
    données}.
    Erreurs : OSError si le fichier ne peut pas être écrit.
    Usages : comparaison, telecharger, migration (export, correspondance,
    circuit), tests.
    """
    comptes: dict[str, int] = {}
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        noms: list[str] = []
        for i, (nom, entetes, lignes) in enumerate(feuilles, 1):
            nom = nom[:31]
            noms.append(nom)
            with z.open("xl/worksheets/sheet%d.xml" % i, "w") as f:
                f.write(
                    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    b'<worksheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main"><sheetViews>'
                    b'<sheetView workbookViewId="0">'
                    b'<pane ySplit="1" topLeftCell="A2" '
                    b'activePane="bottomLeft" '
                    b'state="frozen"/></sheetView></sheetViews><sheetData>'
                )
                entete = "".join(
                    '<c r="%s1" s="3" t="inlineStr"><is><t>%s</t></is></c>'
                    % (lettres_colonne(j), echapper_xml(h))
                    for j, h in enumerate(entetes)
                )
                f.write(('<row r="1">%s</row>' % entete).encode("utf-8"))
                n = 0
                for n, ligne in enumerate(lignes, 1):
                    r = n + 1
                    cellules = "".join(
                        _cellule("%s%d" % (lettres_colonne(j), r), v)
                        for j, v in enumerate(ligne)
                    )
                    f.write(
                        ('<row r="%d">%s</row>' % (r, cellules)).encode(
                            "utf-8"
                        )
                    )
                comptes[nom] = n
                filtre = (
                    '<autoFilter ref="A1:%s%d"/>'
                    % (lettres_colonne(len(entetes) - 1), n + 1)
                    if entetes
                    else ""
                )
                f.write(
                    ("</sheetData>%s</worksheet>" % filtre).encode("utf-8")
                )
        z.writestr(
            "[Content_Types].xml",
            _ENTETE_XML
            + '<Types xmlns="'
            + _SCHEMAS_OPENXML
            + 'package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/'
            'vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="'
            + _TYPE_OFFICE
            + 'spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="'
            + _TYPE_OFFICE
            + 'spreadsheetml.styles+xml"/>'
            + "".join(
                '<Override PartName="/xl/worksheets/sheet%d.xml" '
                'ContentType="%sspreadsheetml.worksheet+xml"/>'
                % (i, _TYPE_OFFICE)
                for i in range(1, len(noms) + 1)
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            _ENTETE_XML
            + '<Relationships xmlns="'
            + _SCHEMAS_OPENXML
            + 'package/2006/relationships"><Relationship Id="rId1" Type="'
            + _DOC_OFFICE
            + '/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        z.writestr(
            "xl/workbook.xml",
            _ENTETE_XML
            + '<workbook xmlns="'
            + _SCHEMAS_OPENXML
            + 'spreadsheetml/2006/main" xmlns:r="'
            + _DOC_OFFICE
            + '"><sheets>'
            + "".join(
                '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                % (echapper_xml(n, {'"': "&quot;"}), i, i)
                for i, n in enumerate(noms, 1)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            _ENTETE_XML
            + '<Relationships xmlns="'
            + _SCHEMAS_OPENXML
            + 'package/2006/relationships">'
            + "".join(
                '<Relationship Id="rId%d" Type="%s/worksheet" '
                'Target="worksheets/sheet%d.xml"/>' % (i, _DOC_OFFICE, i)
                for i in range(1, len(noms) + 1)
            )
            + '<Relationship Id="rId%d" Type="%s/styles" Target="styles.xml"/>'
            % (len(noms) + 1, _DOC_OFFICE)
            + "</Relationships>",
        )
        z.writestr("xl/styles.xml", _STYLES)
    return comptes
