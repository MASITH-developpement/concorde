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
from typing import Any, Callable, NoReturn, Optional, TypedDict, Union
from .xml_sur import ElementXml, lire_xml

from .canonical import Canonique, extraire_canon


class ErreurMapping(RuntimeError):
    """Mapping illisible, incomplet ou contradictoire (jamais deviné)."""


# Valeur lue dans une cellule .xlsx : texte, nombre ou booléen.
ValeurCellule = Union[str, int, float, bool]
# Lecteur de valeur d'une cellule <c> (None si cellule vide/illisible).
LecteurValeur = Callable[[ElementXml], Optional[ValeurCellule]]
# Mapping accepté : chaîne/chemin JSON, dict, liste ou tuple de paires.
SourceMapping = Union[
    str,
    dict[str, str],
    list[tuple[str, str]],
    tuple[tuple[str, str], ...],
]


class BilanMapping(TypedDict):
    """Résultat de l'étape mapper_comptes."""

    nb_lignes: int
    nb_mappees: int
    inconnus: int
    canon: Canonique


NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
)


def _erreur_fichier(
    classe_erreur: type[Exception], quoi: str, nom_fichier: str, message: str
) -> NoReturn:
    """Lève l'erreur explicite d'un fichier .xlsx illisible.

    Rôle : message unique « Fichier <quoi> <nom> : <message> ».
    Paramètres : classe_erreur, exception à lever ; quoi, nature du
    fichier ('de mapping', 'du plan comptable'...) ; nom_fichier ('xlsx'
    si vide) ; message, cause lisible.
    Retour : aucun (lève toujours).
    Erreurs : classe_erreur.
    Usages : lire_feuille_xlsx, charger_mapping_xlsx,
    plan_comptable.charger_plan_xlsx.
    """
    raise classe_erreur(
        "Fichier %s %r : %s" % (quoi, nom_fichier or "xlsx", message)
    )


def _norm_entete(texte: object) -> str:
    """Normalise un en-tête : minuscules, sans accent ni séparateur."""
    s = str(texte or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for sep in (" ", ".", "-", "_", "'", "(", ")", "/"):
        s = s.replace(sep, "")
    return s


def _mapping_depuis_lignes(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Lignes JSON {quadra, odoo} -> {compte Quadra: compte Odoo}.

    Rôle : lecture commune des mappings JSON (chaîne ou fichier).
    Paramètres : rows, lignes JSON (contenu dynamique, d'où Any) ; une
    ligne sans 'quadra' ou sans 'odoo' est ignorée.
    Retour : dict des correspondances, comptes nettoyés (strip).
    Erreurs : aucune propre.
    Usages : charger_mapping (chaîne JSON et chemin de fichier).
    """
    return {
        str(r["quadra"]).strip(): str(r["odoo"]).strip()
        for r in rows
        if r.get("quadra") and r.get("odoo")
    }


def charger_mapping(source: SourceMapping) -> dict[str, str]:
    """Charge un mapping : chemin JSON, chaîne JSON, dict ou paires."""
    if isinstance(source, str) and (
        source.lstrip().startswith("[") or source.lstrip().startswith("{")
    ):
        return _mapping_depuis_lignes(json.loads(source))
    if isinstance(source, str):
        with open(source, "r", encoding="utf-8") as f:
            return _mapping_depuis_lignes(json.load(f))
    if isinstance(source, dict):
        return dict(source)
    if isinstance(source, (list, tuple)):
        return {str(q).strip(): str(o).strip() for q, o in source}
    raise ErreurMapping(
        "Source de mapping non supportée (JSON, chemin, dict, tuples)."
    )


def _index_colonne(lettres: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 27 (base 26).'' -> erreur."""
    n = 0
    if not lettres:
        raise ErreurMapping("Référence de cellule sans colonne.")
    for ch in lettres:
        if not ("A" <= ch <= "Z"):
            raise ErreurMapping("Référence de cellule invalide : %r" % lettres)
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def lire_feuille_xlsx(
    brut: Optional[Union[bytes, bytearray]],
    nom_fichier: str = "",
    quoi: str = "classeur",
) -> tuple[str, ElementXml, LecteurValeur]:
    """Ouvre un .xlsx (octets) -> (nom_feuille, racine XML, valeur(c)).

    Rôle : lecteur stdlib de la première feuille d'un classeur.
    Paramètres : brut, octets du fichier ; nom_fichier et quoi, pour les
    messages d'erreur.
    Retour : (chemin de la feuille dans l'archive, élément <worksheet>,
    lecteur de valeur d'une cellule <c>).
    Erreurs : ErreurMapping explicite (Marceau : jamais muet) si le
    contenu n'est pas un .xlsx lisible.
    Usages : charger_mapping_xlsx, plan_comptable.charger_plan_xlsx.
    """

    def _err(message: str) -> NoReturn:
        """Erreur ErreurMapping pour ce fichier."""
        _erreur_fichier(ErreurMapping, quoi, nom_fichier, message)

    if not isinstance(brut, (bytes, bytearray)) or not bytes(brut).startswith(
        b"PK"
    ):
        # Diagnostic explicite : dire ce qui a été reçu, pas juste le refus.
        # (Marceau : jamais muet — un .xlsx EST une archive zip ; un contenu
        # non-zip signifie un .xls binaire, un CSV renommé ou un fichier
        # corrompu/téléchargé incomplètement.)
        tete = bytes(brut or b"")[:8]
        if tete.startswith(b"\xd0\xcf\x11\xe0"):
            cause = (
                "vieux format .xls (Excel 97-2003, signature OLE2) détecté — "
                "réexportez le fichier depuis Excel au format "
                "« Classeur Excel (*.xlsx) »."
            )
        elif tete.startswith(b"PK"):
            cause = (
                "archive zip invalide ou incomplète — retéléchargez/"
                "recopiez le fichier, il est tronqué."
            )
        elif not tete:
            cause = "fichier vide (0 octet) — vérifiez le fichier joint."
        else:
            extrait = "".join(chr(b) if 32 <= b < 127 else "." for b in tete)
            cause = (
                "contenu non-xlsx détecté (premiers octets : %r = %s) — "
                "un .xlsx est une archive zip (PK). Il s'agit probablement "
                "d'un .xls binaire, d'un CSV renommé ou d'un autre "
                "fichier. Réexportez depuis Excel au format "
                "« Classeur Excel (*.xlsx) »."
                % (" ".join("%02x" % b for b in tete), extrait)
            )
        _err(cause)
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(brut)))
    except Exception as exc:
        _err("archive illisible (%s)." % exc)

    sst: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        racine_sst = lire_xml(zf.read("xl/sharedStrings.xml"))
        for si in racine_sst.iter(NS_MAIN + "si"):
            sst.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))

    feuille: Optional[str] = None
    if (
        "xl/workbook.xml" in zf.namelist()
        and "xl/_rels/workbook.xml.rels" in zf.namelist()
    ):
        wb = lire_xml(zf.read("xl/workbook.xml"))
        rels = lire_xml(zf.read("xl/_rels/workbook.xml.rels"))
        cibles = {r.get("Id"): r.get("Target") for r in rels}
        for sheet in wb.iter(NS_MAIN + "sheet"):
            cible = cibles.get(sheet.get(NS_REL + "id"))
            if not cible:
                continue
            nom = (
                cible if cible.startswith("xl/") else "xl/" + cible.lstrip("/")
            )
            if nom in zf.namelist():
                feuille = nom
                break
    if feuille is None:
        cand = sorted(
            n
            for n in zf.namelist()
            if re.match(r"xl/worksheets/sheet\d+\.xml$", n)
        )
        if not cand:
            _err("aucune feuille de calcul trouvée.")
        feuille = cand[0]

    racine = lire_xml(zf.read(feuille))

    def _valeur(c: ElementXml) -> Optional[ValeurCellule]:
        """Valeur typée d'une cellule <c> ; None si vide ou illisible."""
        t = c.get("t")
        if t == "s":
            v = c.find(NS_MAIN + "v")
            if v is None or v.text is None:
                return None
            try:
                return sst[int(v.text)]
            except (ValueError, IndexError):
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


def _colonne_cellule(c: ElementXml, rang: int) -> int:
    """Index de colonne d'une cellule : référence ('B17') ou rang lu."""
    ref = c.get("r") or ""
    lettres = "".join(ch for ch in ref if ch.isalpha()).upper()
    if lettres:
        return _index_colonne(lettres)
    return rang


def valeurs_cellules_ligne(
    row: ElementXml, valeur: LecteurValeur
) -> dict[int, ValeurCellule]:
    """Valeurs non vides d'une ligne <row>, indexées par colonne.

    Rôle : lecture commune d'une ligne de classeur.
    Paramètres : row, élément <row> ; valeur, lecteur rendu par
    lire_feuille_xlsx.
    Retour : {index de colonne (0 = A): valeur}, cellules vides omises.
    Erreurs : ErreurMapping si une référence de cellule est invalide.
    Usages : charger_mapping_xlsx, plan_comptable.charger_plan_xlsx.
    """
    vals: dict[int, ValeurCellule] = {}
    for rang, c in enumerate(row.iter(NS_MAIN + "c")):
        col = _colonne_cellule(c, rang)
        val = valeur(c)
        if val is not None:
            vals[col] = val
    return vals


def _compte_txt(v: object) -> str:
    """Numéro de compte -> texte propre (jamais '10130000.0')."""
    if isinstance(v, bool):
        return ""
    if isinstance(v, float):
        v = int(v) if v.is_integer() else v
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def charger_mapping_xlsx(
    brut: Optional[Union[bytes, bytearray]], nom_fichier: str = ""
) -> dict[str, str]:
    """Charge un mapping depuis un classeur Excel .xlsx (octets).

    Attend un en-tête avec une colonne « Numéro » (compte Quadra) et une
    colonne « Odoo Acct » (compte Odoo cible) — mise en page du fichier
    « Mapping Quadra Odoo » du client. Erreurs explicites sinon (Marceau :
    jamais muet, aucun compte deviné).
    """

    def _err(message: str) -> NoReturn:
        """Erreur ErreurMapping pour ce fichier de mapping."""
        _erreur_fichier(ErreurMapping, "de mapping", nom_fichier, message)

    feuille, racine, _valeur = lire_feuille_xlsx(
        brut, nom_fichier, quoi="de mapping"
    )

    lignes = list(racine.iter(NS_MAIN + "row"))

    # 1. détection de l'en-tête (parmi les 50 premières lignes) : colonnes
    # et INDEX de la ligne d'en-tête (la lecture commence après elle).
    col_quadra: Optional[int] = None
    col_odoo: Optional[int] = None
    idx_entete = 0  # fixé dès que l'en-tête est trouvé (sinon _err)
    for idx, row in enumerate(lignes[:50]):
        entetes: dict[str, int] = {}
        for col, val in valeurs_cellules_ligne(row, _valeur).items():
            entetes[_norm_entete(val)] = col
        for texte, col in entetes.items():
            if texte == "numero" and col_quadra is None:
                col_quadra = col
            if (
                texte.startswith("odoo")
                and ("acct" in texte or "compte" in texte)
                and col_odoo is None
            ):
                col_odoo = col
        if col_quadra is not None and col_odoo is not None:
            idx_entete = idx
            break
    if col_quadra is None or col_odoo is None:
        _err(
            "en-tête introuvable — colonnes attendues « Numéro » (compte "
            "Quadra) et « Odoo Acct » (compte Odoo). Vérifiez que le fichier "
            "est bien l'export « Mapping Quadra Odoo »."
        )

    # 2. lecture des correspondances (strictement après la ligne d'en-tête)
    mapping: dict[str, str] = {}
    doublons: dict[str, set[str]] = {}
    debut_donnees = idx_entete + 1
    for row in lignes[debut_donnees:]:
        vals = valeurs_cellules_ligne(row, _valeur)
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
        detail = ", ".join(
            "%s->%s" % (q, "/".join(sorted(s)))
            for q, s in sorted(doublons.items())
        )
        _err("comptes Quadra avec cibles Odoo contradictoires : %s" % detail)
    if not mapping:
        _err("aucune correspondance trouvée sous l'en-tête.")
    return mapping


def mapper_comptes(
    donnees: Union[Canonique, dict[str, Any]],
    mapping: Optional[SourceMapping] = None,
) -> BilanMapping:
    """Étape pipeline : mappe les comptes Quadra vers Odoo (toutes lignes).

    donnees : Canonique ou dict de pipeline portant 'canon' (dynamique).
    """
    if mapping is None:
        raise ErreurMapping(
            "Aucun mapping fourni (fichier Mapping Quadra Odoo requis)."
        )
    if isinstance(mapping, (str, list, tuple)):
        mapping = charger_mapping(mapping)

    canon = extraire_canon(donnees)
    if canon is None:
        raise ErreurMapping("Aucun journal canonique à mapper.")

    inconnus: dict[str, int] = {}
    for ligne in canon.lignes:
        cible = mapping.get(ligne.compte)
        if cible is None:
            inconnus[ligne.compte] = inconnus.get(ligne.compte, 0) + 1
        else:
            ligne.compte = cible
    if inconnus:
        detail = ", ".join(
            "%s (x%s)" % (c, n) for c, n in sorted(inconnus.items())
        )
        raise ErreurMapping(
            "Comptes Quadra absents du mapping Odoo — aucun compte "
            "deviné : %s" % detail
        )
    return {
        "nb_lignes": len(canon),
        "nb_mappees": len(canon),
        "inconnus": 0,
        "canon": canon,
    }
