# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""MAPPING DES COMPTES — Quadra -> Odoo.

Étape no-code du pipeline : applique le fichier de correspondance fourni par
le client (Mapping Quadra Odoo) aux lignes canoniques.

Règles :
- Un compte Quadra sans correspondance = ERREUR BLOQUANTE (aucune création
  implicite : on ne devine jamais un compte comptable).
- Le mapping est injecté par chemin de fichier, chaîne/liste JSON, dict déjà
  chargé, ou classeur Excel .xlsx uploadé (colonnes « Numéro » et
  « Odoo Acct »).
- Tolérance Concordance inchangée : le mapping ne touche jamais aux montants.
"""
import io
import json
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET


class ErreurMapping(RuntimeError):
    pass


NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _norm_entete(texte):
    """Normalise un en-tête : minuscules, sans accent ni séparateur."""
    s = str(texte or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for sep in (" ", ".", "-", "_", "'", "(", ")", "/"):
        s = s.replace(sep, "")
    return s


def charger_mapping(source):
    """Charge un mapping depuis un chemin JSON, une chaîne JSON, un dict ou une liste de tuples."""
    if isinstance(source, str) and (source.lstrip().startswith("[") or source.lstrip().startswith("{")):
        rows = json.loads(source)
        return {str(r["quadra"]).strip(): str(r["odoo"]).strip() for r in rows
                if r.get("quadra") and r.get("odoo")}
    if isinstance(source, str):
        with open(source, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return {str(r["quadra"]).strip(): str(r["odoo"]).strip() for r in rows
                if r.get("quadra") and r.get("odoo")}
    if isinstance(source, dict):
        return dict(source)
    if isinstance(source, (list, tuple)):
        return {str(q).strip(): str(o).strip() for q, o in source}
    raise ErreurMapping("Source de mapping non supportée (JSON, chemin, dict, tuples).")


def _index_colonne(lettres):
    """'A' -> 0, 'B' -> 1, 'AA' -> 27 (base 26).'' -> erreur."""
    n = 0
    if not lettres:
        raise ErreurMapping("Référence de cellule sans colonne.")
    for ch in lettres:
        if not ("A" <= ch <= "Z"):
            raise ErreurMapping("Référence de cellule invalide : %r" % lettres)
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def lire_feuille_xlsx(brut, nom_fichier="", quoi="classeur"):
    """Ouvre un .xlsx (octets) -> (nom_feuille, racine XML, valeur(c)).

    Lecteur stdlib partagé par le mapping et le plan comptable. Erreurs
    explicites (Marceau : jamais muet).
    """
    def _err(message):
        raise ErreurMapping(
            "Fichier %s %r : %s" % (quoi, nom_fichier or "xlsx", message))

    if not isinstance(brut, (bytes, bytearray)) or not bytes(brut).startswith(b"PK"):
        _err("contenu .xlsx invalide (archive zip attendue). "
             "Re-exportez le fichier depuis Excel.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(brut)))
    except Exception as exc:
        _err("archive illisible (%s)." % exc)

    if "xl/sharedStrings.xml" in zf.namelist():
        sst = []
        racine_sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in racine_sst.iter(NS_MAIN + "si"):
            sst.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))
    else:
        sst = []

    feuille = None
    if "xl/workbook.xml" in zf.namelist() and "xl/_rels/workbook.xml.rels" in zf.namelist():
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        cibles = {r.get("Id"): r.get("Target") for r in rels}
        for sheet in wb.iter(NS_MAIN + "sheet"):
            cible = cibles.get(sheet.get(NS_REL + "id"))
            if not cible:
                continue
            nom = cible if cible.startswith("xl/") else "xl/" + cible.lstrip("/")
            if nom in zf.namelist():
                feuille = nom
                break
    if feuille is None:
        cand = sorted(n for n in zf.namelist()
                      if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not cand:
            _err("aucune feuille de calcul trouvée.")
        feuille = cand[0]

    racine = ET.fromstring(zf.read(feuille))

    def _valeur(c):
        t = c.get("t")
        if t == "s":
            v = c.find(NS_MAIN + "v")
            try:
                return sst[int(v.text)]
            except (TypeError, ValueError, IndexError):
                return None
        if t == "inlineStr":
            return "".join(x.text or "" for x in c.iter(NS_MAIN + "t"))
        v = c.find(NS_MAIN + "v")
        if v is None or v.text is None:
            return None
        if t == "b":
            return bool(int(v.text))
        if t in (None, "n"):
            f = float(v.text)
            return int(f) if f.is_integer() else f
        return v.text

    return feuille, racine, _valeur


def _colonne_cellule(c, rang):
    """Index de colonne d'une cellule : référence ('B17') ou rang d'apparition."""
    ref = c.get("r") or ""
    lettres = "".join(ch for ch in ref if ch.isalpha()).upper()
    if lettres:
        return _index_colonne(lettres)
    return rang


def _compte_txt(v):
    """Numéro de compte -> texte propre (jamais '10130000.0')."""
    if isinstance(v, bool):
        return ""
    if isinstance(v, float):
        v = int(v) if v.is_integer() else v
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def charger_mapping_xlsx(brut, nom_fichier=""):
    """Charge un mapping depuis un classeur Excel .xlsx (octets).

    Attend un en-tête avec une colonne « Numéro » (compte Quadra) et une
    colonne « Odoo Acct » (compte Odoo cible) — mise en page du fichier
    « Mapping Quadra Odoo » du client. Erreurs explicites sinon (Marceau :
    jamais muet, aucun compte deviné).
    """
    def _err(message):
        raise ErreurMapping(
            "Fichier de mapping %r : %s" % (nom_fichier or "xlsx", message))

    feuille, racine, _valeur = lire_feuille_xlsx(
        brut, nom_fichier, quoi="de mapping")

    def _valeurs_ligne(row):
        vals = {}
        for rang, c in enumerate(row.iter(NS_MAIN + "c")):
            col = _colonne_cellule(c, rang)
            val = _valeur(c)
            if val is not None:
                vals[col] = val
        return vals

    lignes = list(racine.iter(NS_MAIN + "row"))

    # 1. détection de l'en-tête (parmi les 50 premières lignes) : colonnes
    # et INDEX de la ligne d'en-tête (la lecture commence après elle).
    col_quadra = col_odoo = None
    idx_entete = None
    for idx, row in enumerate(lignes[:50]):
        entetes = {}
        for col, val in _valeurs_ligne(row).items():
            entetes[_norm_entete(val)] = col
        for texte, col in entetes.items():
            if texte == "numero" and col_quadra is None:
                col_quadra = col
            if texte.startswith("odoo") and ("acct" in texte or "compte" in texte) \
                    and col_odoo is None:
                col_odoo = col
        if col_quadra is not None and col_odoo is not None:
            idx_entete = idx
            break
    if col_quadra is None or col_odoo is None:
        _err("en-tête introuvable — colonnes attendues « Numéro » (compte "
             "Quadra) et « Odoo Acct » (compte Odoo). Vérifiez que le fichier "
             "est bien l'export « Mapping Quadra Odoo ».")

    # 2. lecture des correspondances (strictement après la ligne d'en-tête)
    mapping = {}
    doublons = {}
    for row in lignes[idx_entete + 1:]:
        vals = _valeurs_ligne(row)
        q = _compte_txt(vals.get(col_quadra, "") or "")
        o = _compte_txt(vals.get(col_odoo, "") or "")
        if not q:
            continue
        if not o:
            continue  # cible vide = correspondance absente (jamais devinée)
        if q in mapping and mapping[q] != o:
            doublons.setdefault(q, {mapping[q]}).add(o)
        else:
            mapping[q] = o
    if doublons:
        detail = ", ".join("%s->%s" % (q, "/".join(sorted(s)))
                           for q, s in sorted(doublons.items()))
        _err("comptes Quadra avec cibles Odoo contradictoires : %s" % detail)
    if not mapping:
        _err("aucune correspondance trouvée sous l'en-tête.")
    return mapping


def mapper_comptes(donnees, mapping=None):
    """Étape pipeline : mappe les comptes Quadra vers Odoo sur toutes les lignes."""
    if mapping is None:
        raise ErreurMapping("Aucun mapping fourni (fichier Mapping Quadra Odoo requis).")
    if isinstance(mapping, (str, list, tuple)):
        mapping = charger_mapping(mapping)

    if isinstance(donnees, dict):
        canon = donnees.get("canon") or donnees.get("resultat", {}).get("canon")
    else:
        canon = donnees
    if canon is None:
        raise ErreurMapping("Aucun journal canonique à mapper.")

    inconnus = {}
    for l in canon.lignes:
        cible = mapping.get(l.compte)
        if cible is None:
            inconnus[l.compte] = inconnus.get(l.compte, 0) + 1
        else:
            l.compte = cible
    if inconnus:
        detail = ", ".join("%s (x%s)" % (c, n) for c, n in sorted(inconnus.items()))
        raise ErreurMapping(
            "Comptes Quadra absents du mapping Odoo — aucun compte deviné : %s" % detail)
    return {"nb_lignes": len(canon), "nb_mappees": len(canon),
            "inconnus": 0, "canon": canon}
