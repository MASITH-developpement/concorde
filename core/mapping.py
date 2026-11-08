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
import math
import posixpath
import re
import unicodedata
import zipfile
import zlib
from typing import Any, Callable, NoReturn, Optional, TypedDict, Union

from .xml_sur import ElementXml, ErreurLectureXml, lire_xml

from .canonical import Canonique, extraire_canon
from .xlsx_ecrire import lettres_colonne


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


def _texte_compte_mapping(valeur: object, origine: str) -> str:
    """Compte lu dans un mapping JSON ou une paire -> texte nettoyé.

    Rôle : refuser tout compte qui n'est ni un texte ni un nombre.
    Paramètres : valeur, compte lu (contenu dynamique) ; origine, source
    citée dans le message d'erreur.
    Retour : le compte en texte (strip, jamais '411000.0').
    Erreurs : ErreurMapping si valeur est un booléen, None, un objet, une
    liste ou un nombre non fini (NaN, Infinity).
    Usages : _paire_mapping, _mapping_depuis_json.
    """
    if (
        isinstance(valeur, bool)
        or not isinstance(valeur, (str, int, float))
        or (isinstance(valeur, float) and not math.isfinite(valeur))
    ):
        raise ErreurMapping(
            "%s : compte illisible %r — attendu un numéro de compte (texte "
            "ou nombre)." % (origine, valeur)
        )
    return _compte_txt(valeur)


def _paire_mapping(paire: object, origine: str) -> tuple[str, str]:
    """Paire (compte Quadra, compte Odoo) validée.

    Rôle : lecture commune d'une correspondance donnée en paire.
    Paramètres : paire, liste ou tuple attendu de deux comptes ; origine,
    source citée dans le message d'erreur.
    Retour : (compte Quadra, compte Odoo) en texte nettoyé.
    Erreurs : ErreurMapping si ce n'est pas une paire de deux comptes.
    Usages : charger_mapping (paires Python), _mapping_depuis_json (objet
    JSON et lignes JSON [quadra, odoo]).
    """
    if not isinstance(paire, (list, tuple)) or len(paire) != 2:
        raise ErreurMapping(
            "%s : correspondance illisible %r — attendu une paire (compte "
            "Quadra, compte Odoo) ou un objet {quadra, odoo}."
            % (origine, paire)
        )
    return (
        _texte_compte_mapping(paire[0], origine),
        _texte_compte_mapping(paire[1], origine),
    )


def _mapping_depuis_json(contenu: Any, origine: str) -> dict[str, str]:
    """Contenu JSON décodé -> {compte Quadra: compte Odoo}.

    Rôle : lecture commune des mappings JSON (chaîne ou fichier).
    Paramètres : contenu, JSON décodé (dynamique, d'où Any) : objet
    {quadra: odoo}, ou liste de lignes {quadra, odoo} ou [quadra, odoo] ;
    une ligne objet sans 'quadra' ou sans 'odoo' est ignorée ; origine,
    source citée dans les messages d'erreur.
    Retour : dict des correspondances, comptes nettoyés.
    Erreurs : ErreurMapping si le contenu n'est ni liste ni objet, si une
    ligne n'est ni objet ni paire, ou si un compte est illisible.
    Usages : charger_mapping (chaîne JSON et chemin de fichier).
    """
    if isinstance(contenu, dict):
        return dict(
            _paire_mapping(paire, origine) for paire in contenu.items()
        )
    if not isinstance(contenu, list):
        raise ErreurMapping(
            "%s : attendu une liste ou un objet JSON, reçu %s."
            % (origine, type(contenu).__name__)
        )
    mapping: dict[str, str] = {}
    for ligne in contenu:
        if not isinstance(ligne, dict):
            compte_quadra, compte_odoo = _paire_mapping(ligne, origine)
            mapping[compte_quadra] = compte_odoo
        elif ligne.get("quadra") and ligne.get("odoo"):
            compte_quadra = _texte_compte_mapping(ligne["quadra"], origine)
            mapping[compte_quadra] = _texte_compte_mapping(
                ligne["odoo"], origine
            )
    return mapping


def charger_mapping(source: SourceMapping) -> dict[str, str]:
    """Charge un mapping : chemin JSON, chaîne JSON, dict ou paires.

    Rôle : point d'entrée unique du mapping hors classeur .xlsx.
    Paramètres : source, chaîne JSON (commence par '[' ou '{'), chemin
    d'un fichier JSON UTF-8, dict {quadra: odoo} ou paires.
    Retour : {compte Quadra: compte Odoo}.
    Erreurs : ErreurMapping explicite si le JSON est mal formé, si le
    fichier est absent ou illisible (chemin cité), ou si une
    correspondance n'est pas une paire de comptes.
    Usages : mapper_comptes, tests.
    """
    if isinstance(source, str) and (
        source.lstrip().startswith("[") or source.lstrip().startswith("{")
    ):
        try:
            contenu = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ErreurMapping(
                "mapping illisible : JSON mal formé (%s)." % exc
            ) from exc
        return _mapping_depuis_json(contenu, "mapping JSON")
    if isinstance(source, str):
        origine = "fichier de mapping %r" % source
        try:
            with open(source, "r", encoding="utf-8") as fichier:
                contenu = json.load(fichier)
        except FileNotFoundError as exc:
            raise ErreurMapping("%s introuvable." % origine) from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErreurMapping(
                "%s illisible : JSON UTF-8 attendu (%s)." % (origine, exc)
            ) from exc
        return _mapping_depuis_json(contenu, origine)
    if isinstance(source, dict):
        return dict(source)
    if isinstance(source, (list, tuple)):
        return dict(_paire_mapping(paire, "mapping") for paire in source)
    raise ErreurMapping(
        "Source de mapping non supportée (JSON, chemin, dict, tuples)."
    )


def _index_colonne(lettres: str) -> int:
    """'A' -> 0, 'B' -> 1, 'Z' -> 25, 'AA' -> 26 (base 26) ; '' -> erreur."""
    n = 0
    if not lettres:
        raise ErreurMapping("Référence de cellule sans colonne.")
    for ch in lettres:
        if not ("A" <= ch <= "Z"):
            raise ErreurMapping("Référence de cellule invalide : %r" % lettres)
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _chemins_cible_feuille(cible: str) -> list[str]:
    """Chemins candidats, dans l'archive, d'une cible de relation.

    Rôle : résoudre l'attribut Target de xl/_rels/workbook.xml.rels :
    absolue ('/xl/…') depuis la racine du paquet, relative depuis 'xl/'
    ('./' et '../' résolus) ; une cible relative déjà préfixée 'xl/'
    (écart fréquent des producteurs) est aussi essayée telle quelle.
    Paramètres : cible, valeur de Target.
    Retour : chemins à essayer dans l'ordre (vide si la cible sort de
    l'archive).
    Erreurs : aucune.
    Usages : lire_feuille_xlsx.
    """
    if cible.startswith("/"):
        candidats = [posixpath.normpath(cible).lstrip("/")]
    else:
        candidats = [posixpath.normpath(posixpath.join("xl", cible))]
        if cible.startswith("xl/"):
            candidats.append(posixpath.normpath(cible))
    return [chemin for chemin in candidats if not chemin.startswith("..")]


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
    contenu n'est pas un .xlsx lisible (type reçu, archive, XML d'une
    partie) ; le lecteur de valeur lève aussi ErreurMapping, cellule
    citée, pour un nombre ou un booléen illisible et une erreur Excel.
    Usages : charger_mapping_xlsx, plan_comptable.charger_plan_xlsx.
    """

    def _err(message: str) -> NoReturn:
        """Erreur ErreurMapping pour ce fichier."""
        _erreur_fichier(ErreurMapping, quoi, nom_fichier, message)

    def _lire_partie(chemin: str) -> ElementXml:
        """Racine XML d'une partie de l'archive ; ErreurMapping sinon."""
        try:
            return lire_xml(zf.read(chemin))
        except (
            ErreurLectureXml,
            ValueError,
            zipfile.BadZipFile,
            zlib.error,
        ) as exc:
            _err("partie %r illisible (%s)." % (chemin, exc))

    if brut is not None and not isinstance(brut, (bytes, bytearray)):
        _err(
            "contenu de type %s reçu au lieu d'octets — le fichier doit "
            "être lu en binaire." % type(brut).__name__
        )
    if not bytes(brut or b"").startswith(b"PK"):
        # Diagnostic explicite : dire ce qui a été reçu, pas juste le refus.
        # (Marceau : jamais muet — un .xlsx EST une archive zip ; un contenu
        # non-zip signifie un .xls binaire, un CSV renommé ou un fichier
        # vide.)
        tete = bytes(brut or b"")[:8]
        if tete.startswith(b"\xd0\xcf\x11\xe0"):
            cause = (
                "vieux format .xls (Excel 97-2003, signature OLE2) détecté — "
                "réexportez le fichier depuis Excel au format "
                "« Classeur Excel (*.xlsx) »."
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
        zf = zipfile.ZipFile(io.BytesIO(bytes(brut or b"")))
    except Exception as exc:
        _err("archive illisible (%s)." % exc)

    sst: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        racine_sst = _lire_partie("xl/sharedStrings.xml")
        for si in racine_sst.iter(NS_MAIN + "si"):
            sst.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))

    feuille: Optional[str] = None
    if (
        "xl/workbook.xml" in zf.namelist()
        and "xl/_rels/workbook.xml.rels" in zf.namelist()
    ):
        wb = _lire_partie("xl/workbook.xml")
        rels = _lire_partie("xl/_rels/workbook.xml.rels")
        cibles = {r.get("Id"): r.get("Target") for r in rels}
        for sheet in wb.iter(NS_MAIN + "sheet"):
            cible = cibles.get(sheet.get(NS_REL + "id"))
            if not cible:
                continue
            presents = [
                chemin
                for chemin in _chemins_cible_feuille(cible)
                if chemin in zf.namelist()
            ]
            if presents:
                feuille = presents[0]
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

    racine = _lire_partie(feuille)

    def _valeur(c: ElementXml) -> Optional[ValeurCellule]:
        """Valeur typée d'une cellule <c>.

        None si la cellule est vide ou si son index de chaîne partagée
        est hors table ; ErreurMapping (cellule citée) si un nombre ou un
        booléen est illisible, ou si la cellule est une erreur Excel.
        """
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
        if t == "e":
            _err(
                "cellule %s : erreur Excel %r — corrigez la formule, une "
                "erreur n'est jamais lue comme valeur."
                % (c.get("r", "?"), v.text)
            )
        if t == "b":
            if v.text not in ("0", "1"):
                _err(
                    "cellule %s : booléen illisible %r (0 ou 1 attendu)."
                    % (c.get("r", "?"), v.text)
                )
            return v.text == "1"
        if t in (None, "n"):
            try:
                f = float(v.text)
            except ValueError:
                f = math.nan
            if not math.isfinite(f):
                _err(
                    "cellule %s : nombre illisible %r."
                    % (c.get("r", "?"), v.text)
                )
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

    def _colonne_entete_unique(colonnes: list[int], intitule: str) -> int:
        """Unique colonne d'un intitulé ; ErreurMapping si plusieurs."""
        if len(colonnes) > 1:
            _err(
                "colonne « %s » ambiguë (%s) — une seule colonne de ce nom "
                "est attendue sur la ligne d'en-tête."
                % (intitule, ", ".join(map(lettres_colonne, colonnes)))
            )
        return colonnes[0]

    # 1. détection de l'en-tête (parmi les 50 premières lignes) : les deux
    # colonnes sur UNE même ligne, et l'INDEX de cette ligne (la lecture
    # commence après elle).
    col_quadra: Optional[int] = None
    col_odoo: Optional[int] = None
    idx_entete = 0  # fixé dès que l'en-tête est trouvé (sinon _err)
    for idx, row in enumerate(lignes[:50]):
        cols_numero: list[int] = []
        cols_odoo: list[int] = []
        for col, val in sorted(valeurs_cellules_ligne(row, _valeur).items()):
            texte = _norm_entete(val)
            if texte == "numero":
                cols_numero.append(col)
            if texte.startswith("odoo") and (
                "acct" in texte or "compte" in texte
            ):
                cols_odoo.append(col)
        if cols_numero and cols_odoo:
            col_quadra = _colonne_entete_unique(cols_numero, "Numéro")
            col_odoo = _colonne_entete_unique(cols_odoo, "Odoo Acct")
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

    Rôle : remplacer chaque compte Quadra par sa cible Odoo, tout ou rien.
    Paramètres : donnees, Canonique ou dict de pipeline portant 'canon'
    (dynamique) ; mapping, source acceptée par charger_mapping ou dict.
    Retour : BilanMapping (le canonique est modifié en place).
    Erreurs : ErreurMapping si le mapping ou le journal manque, ou si un
    compte est absent du mapping : TOUS les comptes sont vérifiés avant
    la moindre modification, le canonique reste alors intact.
    Usages : moteur (étape « mapper_comptes »), tests.
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
        if ligne.compte not in mapping:
            inconnus[ligne.compte] = inconnus.get(ligne.compte, 0) + 1
    if inconnus:
        detail = ", ".join(
            "%s (x%s)" % (c, n) for c, n in sorted(inconnus.items())
        )
        raise ErreurMapping(
            "Comptes Quadra absents du mapping Odoo — aucun compte "
            "deviné : %s" % detail
        )
    for ligne in canon.lignes:
        ligne.compte = mapping[ligne.compte]
    return {
        "nb_lignes": len(canon),
        "nb_mappees": len(canon),
        "inconnus": 0,
        "canon": canon,
    }
