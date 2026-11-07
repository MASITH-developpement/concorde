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
from datetime import date, datetime
from xml.sax.saxutils import escape

_EPOQUE = date(1899, 12, 30)


class Centimes(int):
    """Montant en centimes à écrire en euros dans la cellule (exact)."""


def _col(n):
    """Numéro de colonne 0-based -> lettres Excel (0 -> A, 26 -> AA)."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def euros_texte(c, separateur="."):
    """Centimes int -> '1234.56' exact (jamais de float)."""
    signe = "-" if c < 0 else ""
    c = abs(int(c))
    return "%s%d%s%02d" % (signe, c // 100, separateur, c % 100)


def _nettoyer(texte):
    # Caractères de contrôle interdits en XML 1.0 (hors tab / retour ligne).
    return "".join(ch for ch in texte if ch in "\t\n\r" or ord(ch) >= 32)


def _cellule(ref, v):
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
        % (ref, escape(_nettoyer(str(v))))
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
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def ecrire_xlsx(chemin, feuilles):
    """Écrit un classeur.

    feuilles : liste de (nom, entetes, lignes) — lignes = itérable de listes.
    La première ligne (entêtes) est en gras et figée. Retourne
    {nom de feuille: nombre de lignes de données}.
    """
    comptes = {}
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        noms = []
        for i, (nom, entetes, lignes) in enumerate(feuilles, 1):
            nom = nom[:31]
            noms.append(nom)
            with z.open("xl/worksheets/sheet%d.xml" % i, "w") as f:
                f.write(
                    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    b'<worksheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0">'
                    b'<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
                    b'state="frozen"/></sheetView></sheetViews><sheetData>'
                )
                entete = "".join(
                    '<c r="%s1" s="3" t="inlineStr"><is><t>%s</t></is></c>'
                    % (_col(j), escape(h))
                    for j, h in enumerate(entetes)
                )
                f.write(('<row r="1">%s</row>' % entete).encode("utf-8"))
                n = 0
                for n, ligne in enumerate(lignes, 1):
                    r = n + 1
                    cellules = "".join(
                        _cellule("%s%d" % (_col(j), r), v)
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
                    % (_col(len(entetes) - 1), n + 1)
                    if entetes
                    else ""
                )
                f.write(
                    ("</sheetData>%s</worksheet>" % filtre).encode("utf-8")
                )
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/'
            'vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                '<Override PartName="/xl/worksheets/sheet%d.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.worksheet+xml"/>' % i
                for i in range(1, len(noms) + 1)
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
            'main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships"><sheets>'
            + "".join(
                '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                % (escape(n, {'"': "&quot;"}), i, i)
                for i, n in enumerate(noms, 1)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships">'
            + "".join(
                '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.'
                'org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet%d.xml"/>' % (i, i)
                for i in range(1, len(noms) + 1)
            )
            + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            % (len(noms) + 1)
            + "</Relationships>",
        )
        z.writestr("xl/styles.xml", _STYLES)
    return comptes
