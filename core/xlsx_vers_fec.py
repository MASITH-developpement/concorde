# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Convertisseur Excel -> FEC (exports d'ecritures comptables).

Construit pour les exports Excel Quadra / peripheriques qui ne sont pas
des FEC texte : CONCORDE les convertit en FEC standard avant le pipeline.

Regles CONCORDE :
- Tolerance 0 : aucun arrondi silencieux (montant a plus de 2 decimales
  = refus)
- Aucun compte devine, aucune colonne devine : colonnes obligatoires
  explicites, messages d'erreur explicites (Marceau : jamais muet)
- Montants convertis en centimes via core.canonical.vers_centimes
- Dates normalisees en AAAAMMJJ (format FEC obligatoire)
"""

import io
import logging
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import TypedDict
from .xml_sur import lire_xml

from .canonical import vers_centimes

try:
    import openpyxl
except ImportError:  # pragma: no cover
    _OPENPYXL_DISPONIBLE = False
else:
    _OPENPYXL_DISPONIBLE = True


_LOGGER = logging.getLogger(__name__)

# Valeur d'une cellule lue : texte, nombre (bool compris), date (datetime
# comprise) ou vide.
CelluleXlsx = str | int | float | date | None
# Une ligne du classeur ; None est toléré (ligne absente).
LigneXlsx = Sequence[CelluleXlsx] | None


class ErreurFEC(ValueError):
    """Classeur impossible à convertir en FEC : message explicite."""


class LigneQuadra(TypedDict):
    """Ligne validée d'un export Cegid Quadra, avant regroupement.

    niveau_cascade : 0 tant que la ligne n'est rattachée à aucune écriture,
    sinon numéro de la cascade qui l'a rattachée.
    """

    numuniq: str
    ordre: int
    journal: str
    date: str
    libelle: str
    debit: int
    credit: int
    fec: dict[str, str]
    niveau_cascade: int


# Colonnes FEC produites (ordre FEC standard, separateur tabulation)
CHAMPS_FEC = [
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
]

# Synonymes de colonnes d'entete Excel, normalises (minuscules, sans accent,
# sans espace/point/tiret/underscore).
SYNONYMES = {
    "JournalCode": [
        "journalcode",
        "journal",
        "jnl",
        "codejournal",
        "jl",
        "codejnl",
    ],
    "JournalLib": ["journallib", "journallibelle", "libjournal"],
    "EcritureNum": [
        "ecriturenum",
        "ecrituren",
        "numecriture",
        "noecriture",
        "numeroecriture",
        "nbecriture",
        "idecriture",
        "ecriture",
        "ecritureno",
        "necriture",
        "numecrire",
    ],
    "EcritureDate": [
        "ecrituredate",
        "dateecriture",
        "date",
        "datecomptable",
        "datepiece",
        "dat",
        "datee",
    ],
    "CompteNum": [
        "comptenum",
        "compte",
        "accountn",
        "account",
        "numcompte",
        "numerocompte",
        "nocompte",
        "codecompte",
        "general",
        "cpte",
        "comptegeneral",
    ],
    "CompteLib": ["comptelib", "libcompte", "intitulecompte", "libellecompte"],
    "PieceRef": ["pieceref", "piece", "numpiece", "refpiece", "ref"],
    "EcritureLib": [
        "ecriturelib",
        "libelle",
        "lib",
        "libelleecriture",
        "libecriture",
        "intitule",
        "description",
        "libellé",
    ],
    "Debit": ["debit", "dbt", "montantdebit", "d"],
    "Credit": ["credit", "crdt", "montantcredit", "c", "crebit"],
    # Export "Liste des ecritures" Cegid Quadra
    "Periode": ["periode"],
    "Jour": ["jour"],
    "NumUniq": ["numuniq"],
    "TypeLigne": ["typeligne"],
}

OBLIGATOIRES = ["EcritureNum", "EcritureDate", "CompteNum", "Debit", "Credit"]

JOURNAL_DEFAUT = "CONCORDE"

MAX_RECHERCHE_ENTETE = 30  # lignes scannees avant abandon


def _norm(texte: object) -> str:
    """Normalise un en-tete : minuscules, sans accent, sans separators."""
    s = str(texte or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for sep in (" ", ".", "-", "_", "'", "(", ")", "/", "\u00a0", "°"):
        s = s.replace(sep, "")
    return s


def _nettoyer_texte(v: object) -> str:
    """Texte FEC sur : tabulations/retours interdits (separateur tab)."""
    if v is None:
        return ""
    s = str(v).strip()
    for bad in ("\t", "\r", "\n"):
        s = s.replace(bad, " ")
    return s


def _date_fec(v: object, contexte: str) -> str:
    """Convertit une cellule date en AAAAMMJJ. Jamais de date devinee."""
    if isinstance(v, datetime):
        return v.strftime("%Y%m%d")
    if isinstance(v, date):
        return v.strftime("%Y%m%d")
    s = _nettoyer_texte(v)
    chiffres = (
        s.replace("/", "").replace("-", "").replace(".", "").replace(" ", "")
    )
    if len(chiffres) == 8 and chiffres.isdigit():
        # AAAAMMJJ ou JJMMAAAA : leve par plausibilite de l'annee,
        # CONCORDE ne devine jamais une date ambigue.
        if 1900 <= int(chiffres[:4]) <= 2100:
            annee, mois, jour = (
                int(chiffres[:4]),
                int(chiffres[4:6]),
                int(chiffres[6:8]),
            )
            ordre = "AAAAMMJJ"
        elif 1900 <= int(chiffres[4:]) <= 2100:
            jour, mois, annee = (
                int(chiffres[:2]),
                int(chiffres[2:4]),
                int(chiffres[4:]),
            )
            ordre = "JJMMAAAA"
        else:
            raise ErreurFEC(
                "Date ambigue en colonne %s : %r (ni AAAAMMJJ ni JJMMAAAA "
                "plausibles : re-exportez la colonne en date Excel)"
                % (contexte, v)
            )
    elif len(chiffres) == 6 and chiffres.isdigit():
        # JJMMAA (Quadra) : annee 19xx/20xx selon le siecle plausible
        jour, mois, annee = (
            int(chiffres[:2]),
            int(chiffres[2:4]),
            int(chiffres[4:6]),
        )
        annee += 2000 if annee < 70 else 1900
        ordre = "JJMMAA"
    else:
        raise ErreurFEC(
            "Date invalide en colonne %s : %r "
            "(formats attendus : date Excel, AAAAMMJJ, JJ/MM/AAAA)"
            % (contexte, v)
        )
    try:
        date(annee, mois, jour)
    except ValueError:
        raise ErreurFEC(
            "Date invalide en colonne %s : %r (ordre %s)"
            % (contexte, v, ordre)
        )
    return "%04d%02d%02d" % (annee, mois, jour)


def _centimes(v: object, contexte: str) -> int:
    """Cellule montant -> centimes int. Aucun arrondi silencieux."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return 0
    if isinstance(v, (int, float)):
        cent = v * 100
        arrondi = round(cent)
        if abs(cent - arrondi) > 1e-6:
            raise ErreurFEC(
                "Arrondi silencieux interdit : %.6f en colonne %s "
                "(plus de 2 decimales, tolerance 0)" % (v, contexte)
            )
        return int(arrondi)
    return vers_centimes(_nettoyer_texte(v))


def _nombre_texte(v: object) -> str:
    """Normalise un identifiant (EcritureNum, CompteNum) depuis une cellule.

    Excel stocke souvent les numeros en float (5535.0, 10130000.0) :
    on affiche sans decimale parasite, sans deviner autre chose.
    """
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return _nettoyer_texte(v)


def _colonnes_reconnues(ligne: Sequence[CelluleXlsx]) -> dict[str, int]:
    """Reconnaît les colonnes d'une ligne candidate à l'en-tête.

    Rôle : associer chaque champ de SYNONYMES à la première colonne dont
    l'intitulé normalisé est l'un de ses synonymes.
    Paramètres : ligne, cellules de la ligne.
    Retour : {champ: index de colonne}.
    Erreurs : aucune.
    Usages : _trouver_entete (en-tête FEC standard et Cegid Quadra).
    """
    trouve: dict[str, int] = {}
    for j, cellule in enumerate(ligne):
        nom = _norm(cellule)
        if not nom:
            continue
        for champ, synos in SYNONYMES.items():
            if champ in trouve:
                continue
            if nom in synos:
                trouve[champ] = j
    return trouve


def _trouver_entete(
    rows: Sequence[LigneXlsx], obligatoires: Sequence[str]
) -> tuple[int, dict[str, int]] | None:
    """Cherche la ligne d'en-tête dans les premières lignes du classeur.

    Rôle : repérer l'en-tête sans jamais deviner une colonne.
    Paramètres : rows, lignes du classeur (MAX_RECHERCHE_ENTETE premières
    examinées) ; obligatoires, champs qui doivent tous être reconnus
    (OBLIGATOIRES pour un FEC standard, QUADRA_OBLIGATOIRES pour un export
    Cegid Quadra).
    Retour : (index de ligne, {champ: index de colonne}) ou None.
    Erreurs : aucune.
    Usages : xlsx_vers_fec (FEC standard, puis repli Cegid Quadra).
    """
    for i, ligne in enumerate(rows):
        if i >= MAX_RECHERCHE_ENTETE:
            break
        if ligne is None:
            continue
        trouve = _colonnes_reconnues(ligne)
        if all(c in trouve for c in obligatoires):
            return i, trouve
    return None


def _valeur_colonne(
    row: Sequence[CelluleXlsx], colonnes: Mapping[str, int], champ: str
) -> CelluleXlsx:
    """Lit la cellule d'un champ dans une ligne.

    Rôle : accès tolérant aux lignes plus courtes que l'en-tête.
    Paramètres : row, cellules de la ligne ; colonnes, {champ: index de
    colonne} ; champ, nom du champ.
    Retour : la valeur, ou None si le champ est absent ou hors ligne.
    Erreurs : aucune.
    Usages : _convertir_quadra, xlsx_vers_fec.
    """
    j = colonnes.get(champ)
    if j is None or j >= len(row):
        return None
    return row[j]


def _construire_ligne_fec(
    *,
    journal: str,
    journal_lib: str,
    ecriture_num: str,
    date_ecr: str,
    compte: str,
    compte_lib: str,
    piece: str,
    libelle: str,
    debit_c: int,
    credit_c: int,
) -> dict[str, str]:
    """Construit une ligne FEC (tous les champs de CHAMPS_FEC).

    Rôle : forme unique des lignes produites ; les dates de pièce et de
    validation reprennent la date d'écriture, les champs auxiliaires,
    lettrage et devise restent vides.
    Paramètres : journal, journal_lib, ecriture_num, date_ecr (AAAAMMJJ),
    compte, compte_lib, piece, libelle ; debit_c, credit_c en centimes.
    Retour : {champ FEC: texte}.
    Erreurs : aucune.
    Usages : _convertir_quadra, xlsx_vers_fec.
    """
    return {
        "JournalCode": journal,
        "JournalLib": journal_lib,
        "EcritureNum": ecriture_num,
        "EcritureDate": date_ecr,
        "CompteNum": compte,
        "CompteLib": compte_lib,
        "CompAuxNum": "",
        "CompAuxLib": "",
        "PieceRef": piece,
        "PieceDate": date_ecr,
        "EcritureLib": libelle,
        "Debit": _fmt_centimes(debit_c),
        "Credit": _fmt_centimes(credit_c),
        "EcritureLet": "",
        "DateLet": "",
        "ValidDate": date_ecr,
        "Montantdevise": "",
        "Idevise": "",
    }


def _encoder_fec(lignes: Iterable[Mapping[str, str]]) -> bytes:
    """Rend le texte FEC complet (en-tête + lignes) en UTF-8.

    Rôle : sérialisation unique du FEC (séparateur tabulation, fin de
    ligne LF, retour final).
    Paramètres : lignes, lignes FEC (_construire_ligne_fec).
    Retour : octets UTF-8.
    Erreurs : KeyError si un champ de CHAMPS_FEC manque.
    Usages : _convertir_quadra, xlsx_vers_fec.
    """
    out = ["\t".join(CHAMPS_FEC)]
    for ligne in lignes:
        out.append("\t".join(ligne[c] for c in CHAMPS_FEC))
    return ("\n".join(out) + "\n").encode("utf-8")


def _lire_avec_openpyxl(brut: bytes) -> list[LigneXlsx]:
    """Lecture via openpyxl (si installe). Retourne une liste de lignes."""
    if not _OPENPYXL_DISPONIBLE:
        raise ImportError("openpyxl absent")
    wb = openpyxl.load_workbook(
        io.BytesIO(brut), read_only=True, data_only=True
    )
    try:
        feuille = wb.worksheets[0]
        rows: list[LigneXlsx] = []
        for row in feuille.iter_rows(values_only=True):
            rows.append(row)
            if len(rows) > 200000:
                break
        return rows
    finally:
        wb.close()


# ---- Lecteur xlsx interne, bibliotheque standard uniquement ----
NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL_OFFICE = (
    "{http://schemas.openxmlformats.org/" "officeDocument/2006/relationships}"
)
EPOQUE_EXCEL = date(1899, 12, 30)  # serie 0 = 30/12/1899
FORMATS_DATE_BUILTIN = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
_RE_DATE = re.compile(r"[dmyhs]", re.IGNORECASE)


def _colonne_xlsx(ref: str) -> int:
    """'B12' -> 1 (index 0)."""
    lettres = re.match(r"([A-Z]+)", ref or "")
    if not lettres:
        raise ErreurFEC("Reference de cellule invalide : %r" % (ref,))
    n = 0
    for ch in lettres.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _est_format_date(code: str) -> bool:
    """Format de nombre date ? (guillemets et echappements ignores)."""
    code = re.sub(r'"[^"]*"', "", code).replace("\\", "")
    return bool(_RE_DATE.search(code))


def _styles_date(zf: zipfile.ZipFile) -> set[int]:
    """Indices de style (cellXfs) correspondant a des formats date."""
    try:
        racine = lire_xml(zf.read("xl/styles.xml"))
    except KeyError:
        return set()
    formats_date = set(FORMATS_DATE_BUILTIN)
    for fmt in racine.iter(NS_MAIN + "numFmt"):
        fid = fmt.get("numFmtId")
        if fid and _est_format_date(fmt.get("formatCode") or ""):
            formats_date.add(int(fid))
    # L'attribut s d'une cellule indexe cellXfs seul : les <xf> de
    # cellStyleXfs (styles nommés) ne doivent pas décaler les indices.
    styles_cellules = racine.find(NS_MAIN + "cellXfs")
    if styles_cellules is None:
        return set()
    indices: set[int] = set()
    for i, xf in enumerate(styles_cellules):
        fid = xf.get("numFmtId")
        if fid and int(fid) in formats_date:
            indices.add(i)
    return indices


def _valeur_date(serie: float) -> date:
    """Numero de serie Excel -> date. Jamais de date devinee."""
    return EPOQUE_EXCEL + timedelta(days=int(serie))


def _lire_xlsx_stdlib(brut: bytes, nom_fichier: str = "") -> list[LigneXlsx]:
    """Lecture d'un classeur .xlsx sans openpyxl (zipfile + ElementTree).

    Gere : sharedStrings, inlineStr, chaines de formule, references de
    cellules (colonnes eparses), styles date (serie Excel -> date).
    Retourne une liste de tuples (une ligne = un tuple).
    """
    zf = zipfile.ZipFile(io.BytesIO(brut))

    # 1. Chaines partagees
    sst: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        racine = lire_xml(zf.read("xl/sharedStrings.xml"))
        for si in racine.iter(NS_MAIN + "si"):
            sst.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))

    # 2. Indices de style date
    styles_date = _styles_date(zf)

    # 3. Premiere feuille declaree (via les relations du classeur)
    feuille_xml = None
    wb = lire_xml(zf.read("xl/workbook.xml"))
    sheet = next(iter(wb.iter(NS_MAIN + "sheet")), None)
    if sheet is not None:
        rid = sheet.get(NS_REL_OFFICE + "id")
        rels = lire_xml(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.iter():
            if rel.get("Id") == rid:
                cible = rel.get("Target")
                break
        else:
            cible = None
        if cible:
            if cible.startswith("/"):
                feuille_xml = cible.lstrip("/")
            else:
                feuille_xml = "xl/" + cible.lstrip("./")
    if not feuille_xml or feuille_xml not in zf.namelist():
        # repli : premiere feuille triee si relations absentes
        cands = sorted(
            n
            for n in zf.namelist()
            if re.match(r"xl/worksheets/sheet\d+\.xml$", n)
        )
        if not cands:
            raise ErreurFEC(
                "Aucune feuille de calcul trouvee dans %r." % (nom_fichier,)
            )
        feuille_xml = cands[0]

    # 4. Lecture des lignes
    racine = lire_xml(zf.read(feuille_xml))
    lignes: list[LigneXlsx] = []
    largeur = 0
    for row in racine.iter(NS_MAIN + "row"):
        if len(lignes) > 200000:
            break
        vals: dict[int, CelluleXlsx] = {}
        for c in row.iter(NS_MAIN + "c"):
            ref = c.get("r") or ""
            j = _colonne_xlsx(ref)
            t = c.get("t")
            v = c.find(NS_MAIN + "v")
            is_elem = c.find(NS_MAIN + "is")
            val: CelluleXlsx
            if t == "s" and v is not None:
                try:
                    val = sst[int(v.text or "")]
                except (ValueError, IndexError):
                    raise ErreurFEC(
                        "Indice de chaine partagee invalide en %s de %r."
                        % (ref, nom_fichier)
                    )
            elif t == "inlineStr" and is_elem is not None:
                val = "".join(
                    x.text or "" for x in is_elem.iter(NS_MAIN + "t")
                )
            elif t == "str" and v is not None:
                val = v.text
            elif v is not None and v.text is not None:
                texte = v.text.strip()
                style_cellule = c.get("s")
                if style_cellule and int(style_cellule) in styles_date:
                    val = _valeur_date(float(texte))  # serie -> date
                elif t == "b":
                    val = bool(int(texte))
                elif texte == "":
                    val = None
                else:
                    try:
                        f = float(texte)
                        val = int(f) if f.is_integer() else f
                    except ValueError:
                        val = texte
            else:
                val = None
            vals[j] = val
            largeur = max(largeur, j + 1)
        ligne = tuple(vals.get(j) for j in range(largeur)) if largeur else ()
        lignes.append(ligne)
    return lignes


# ---- Export "Liste des ecritures" Cegid Quadra ----
# Ce format n'a pas de numero d'ecriture : NumUniq identifie chaque LIGNE.
# Les lignes d'une meme ecriture ne sont pas contigues dans l'export :
# regroupement par CASCADES explicites (journal+date+libelle, puis
# journal+date, puis journal), chaque niveau solde au centime pres
# (tolerance 0). Un residu non solde = erreur explicite, jamais muette.

QUADRA_OBLIGATOIRES = [
    "Periode",
    "Jour",
    "JournalCode",
    "CompteNum",
    "EcritureLib",
    "Debit",
    "Credit",
    "NumUniq",
]


def _date_quadra(periode: object, jour: object, contexte: str) -> str:
    """Periode (JJ/MM/AAAA) + Jour -> date AAAAMMJJ.

    Le jour vient de la colonne Jour, le mois et l'annee de la Periode.
    Jamais devine.
    """
    p = _date_fec(periode, contexte + "/Periode")  # valide JJ/MM/AAAA
    mois, annee = int(p[4:6]), int(p[:4])
    j_txt = str(jour or "").strip()
    if not j_txt.isdigit() or not 1 <= int(j_txt) <= 31:
        raise ErreurFEC(
            "Jour invalide (%r) en colonne %s/Jour : CONCORDE attend un "
            "numero de jour 1-31." % (jour, contexte)
        )
    try:
        date(annee, mois, int(j_txt))
    except ValueError:
        raise ErreurFEC(
            "Date invalide : jour %s inexistant en %02d/%d "
            "(colonnes Periode/Jour)." % (j_txt, mois, annee)
        )
    return "%04d%02d%02d" % (annee, mois, int(j_txt))


def _convertir_quadra(
    rows: Sequence[LigneXlsx],
    idx: int,
    colonnes: Mapping[str, int],
    nom_fichier: str,
) -> bytes:
    """Convertit un export Cegid Quadra en FEC standard.

    Regroupement en ecritures equilibrees par CASCADES EXPLICITES
    (tolerance 0, jamais muet) :

      1. (journal, date, libelle) -> une ecriture si le groupe est solde ;
      2. groupes non soldes consolides par (journal, date) -> une
         ecriture consolidee si le cumul s'equilibre ;
      3. reste consolide par journal seul (une ecriture par journal,
         date = premiere ligne du journal) ;
      4. desequilibre residuel = ErreurFEC explicite.

    Le numero d'ecriture retenu est le NumUniq de la premiere ligne du
    groupe. Aucun groupement devine : chaque niveau de la cascade est
    tracé (logging) et un residu non solde est une erreur explicite.
    """

    def val(row: Sequence[CelluleXlsx], champ: str) -> CelluleXlsx:
        """Lit la cellule du champ `champ` dans la ligne `row`."""
        return _valeur_colonne(row, colonnes, champ)

    # ---- passe 0 : lecture et validation de toutes les lignes ----
    lignes: list[LigneQuadra] = []
    debut_donnees = idx + 1
    for row in rows[debut_donnees:]:
        if row is None:
            continue
        debit_c = _centimes(val(row, "Debit"), "Debit")
        credit_c = _centimes(val(row, "Credit"), "Credit")
        compte = _nombre_texte(val(row, "CompteNum"))
        numuniq = _nombre_texte(val(row, "NumUniq"))
        if not compte and debit_c == 0 and credit_c == 0 and not numuniq:
            continue  # ligne vide / de presentation
        if not numuniq:
            raise ErreurFEC(
                "Ligne sans NumUniq dans %r : CONCORDE ne devine jamais "
                "un identifiant." % (nom_fichier,)
            )
        if not compte:
            raise ErreurFEC(
                "Ligne NumUniq %s sans numero de compte : CONCORDE ne "
                "devine jamais un compte." % numuniq
            )
        typ = _nettoyer_texte(val(row, "TypeLigne"))
        if typ and typ != "E":
            raise ErreurFEC(
                "TypeLigne %r inconnu (NumUniq %s) : CONCORDE ne traite "
                "que les lignes d'ecriture 'E'. Aucune ligne devinee."
                % (typ, numuniq)
            )
        journal = _nettoyer_texte(val(row, "JournalCode"))
        if not journal:
            raise ErreurFEC(
                "Ligne NumUniq %s sans journal : CONCORDE ne devine "
                "jamais un journal." % numuniq
            )
        date_ecr = _date_quadra(
            val(row, "Periode"), val(row, "Jour"), "NumUniq %s" % numuniq
        )
        libelle = _nettoyer_texte(val(row, "EcritureLib"))
        lignes.append(
            {
                "numuniq": numuniq,
                "ordre": len(lignes),
                "journal": journal,
                "date": date_ecr,
                "libelle": libelle or ("Ecriture %s" % numuniq),
                "debit": debit_c,
                "credit": credit_c,
                "fec": _construire_ligne_fec(
                    journal=journal,
                    journal_lib=journal,
                    ecriture_num="",  # remplace a la cloture du groupe
                    date_ecr=date_ecr,
                    compte=compte,
                    compte_lib="",
                    piece=_nettoyer_texte(val(row, "PieceRef")),
                    libelle=libelle or ("Ecriture %s" % numuniq),
                    debit_c=debit_c,
                    credit_c=credit_c,
                ),
                "niveau_cascade": 0,
            }
        )

    if not lignes:
        raise ErreurFEC(
            "Aucune ligne d'ecriture exploitable dans %r apres l'en-tete "
            "(ligne %d)." % (nom_fichier, idx + 1)
        )

    # ---- cascades : regroupements explicites, du plus fin au plus large --
    # Un groupe = liste de lignes + cumuls. Soldé = debit == credit.
    # [(premiere ligne du groupe, [lignes])]
    ecritures: list[tuple[LigneQuadra, list[LigneQuadra]]] = []

    def appliquer_cascade(
        niveau: int, cles: Callable[[LigneQuadra], tuple[str, ...]]
    ) -> list[LigneQuadra]:
        """Regroupe les lignes non encore rattachées par `cles`.

        Chaque groupe soldé devient une écriture (lignes marquées du
        `niveau` de cascade), dans l'ordre d'apparition. Retourne les
        lignes des groupes non soldés.
        """
        groupes: dict[tuple[str, ...], list[LigneQuadra]] = {}
        for ligne in lignes:
            if ligne["niveau_cascade"]:
                continue  # deja prise par une cascade precedente
            groupes.setdefault(cles(ligne), []).append(ligne)
        restantes: list[LigneQuadra] = []
        for groupe in groupes.values():
            debit = sum(ligne["debit"] for ligne in groupe)
            credit = sum(ligne["credit"] for ligne in groupe)
            if debit == credit:
                ecritures.append((groupe[0], groupe))
                for ligne in groupe:
                    ligne["niveau_cascade"] = niveau
            else:
                restantes.extend(groupe)
        return restantes

    # Cascade 1 : (journal, date, libelle)
    restantes = appliquer_cascade(
        1, lambda ligne: (ligne["journal"], ligne["date"], ligne["libelle"])
    )

    # Cascade 2 : (journal, date) — seulement sur ce qui reste
    if restantes:
        _LOGGER.info(
            "Quadra %s : cascade 1 laisse %d ligne(s) non soldee(s), "
            "consolidation par (journal, date).",
            nom_fichier,
            len(restantes),
        )
        restantes = appliquer_cascade(
            2, lambda ligne: (ligne["journal"], ligne["date"])
        )

    # Cascade 3 : journal seul — une ecriture consolidee par journal
    if restantes:
        _LOGGER.warning(
            "Quadra %s : %d ligne(s) encore non soldee(s) apres "
            "consolidation par (journal, date) ; consolidation finale par "
            "journal (une ecriture regroupee par journal, date = premiere "
            "ligne).",
            nom_fichier,
            len(restantes),
        )
        restantes = appliquer_cascade(3, lambda ligne: (ligne["journal"],))

    # Cascade 4 : residu = erreur explicite (tolerance 0)
    if restantes:
        par_journal: dict[str, list[int]] = {}
        for ligne in restantes:
            par_journal.setdefault(ligne["journal"], [0, 0, 0])
            par_journal[ligne["journal"]][0] += ligne["debit"]
            par_journal[ligne["journal"]][1] += ligne["credit"]
            par_journal[ligne["journal"]][2] += 1
        detail = ", ".join(
            "%s : %d ligne(s), debit %d != credit %d centimes (ecart %d)"
            % (j, v[2], v[0], v[1], v[0] - v[1])
            for j, v in sorted(par_journal.items())
        )
        raise ErreurFEC(
            "Lignes non soldables dans %r apres les cascades "
            "(journal+date+libelle, journal+date, journal) : CONCORDE ne "
            "cree jamais une ecriture desequilibree. Detail par journal : "
            "%s. Verifiez l'export Quadra (tranchee complete)."
            % (nom_fichier, detail)
        )

    # ---- emission : ordre d'apparition dans le fichier, doublons distincts
    ecritures.sort(key=lambda e: e[0]["ordre"])
    lignes_fec: list[dict[str, str]] = []
    for premiere, groupe in ecritures:
        ecriture_num = premiere["numuniq"]
        # Lignes strictement identiques (compte/montants/libelle) dans la
        # meme ecriture : l'idempotence canonique les fusionnerait et
        # desequilibrerait l'ecriture. On distingue les occurrences par
        # leur NumUniq, appose au libelle (jamais silencieusement).
        vus: set[tuple[str, str, str, str]] = set()
        for ligne in groupe:
            f = ligne["fec"]
            cle = (f["CompteNum"], f["Debit"], f["Credit"], f["EcritureLib"])
            if cle in vus:
                f["EcritureLib"] = "%s [%s]" % (
                    f["EcritureLib"],
                    ligne["numuniq"],
                )
            else:
                vus.add(cle)
        for ligne in groupe:
            lignes_fec.append(dict(ligne["fec"], EcritureNum=ecriture_num))

    return _encoder_fec(lignes_fec)


def xlsx_vers_fec(brut: bytes, nom_fichier: str = "") -> bytes:
    """Convertit un classeur xlsx (bytes) en texte FEC (bytes UTF-8).

    Le FEC produit respecte le format attendu par core.fec_parser :
    en-tete JournalCode/EcritureNum..., dates AAAAMMJJ, montants texte.
    """
    if not brut.startswith(b"PK"):
        # Diagnostic explicite : dire ce qui a été reçu, pas juste le refus.
        # (Marceau : jamais muet — un .xlsx EST une archive zip ; un contenu
        # non-zip signifie .xls binaire, fichier chiffré/placeholder cloud,
        # CSV renommé ou fichier vide/tronqué.)
        tete = bytes(brut or b"")[:8]
        if tete.startswith(b"\xd0\xcf\x11\xe0"):
            cause = (
                "Fichier %r : vieux format .xls (Excel 97-2003, "
                "signature OLE2) détecté — export Quadra typique. "
                "Ouvrez-le dans Excel et enregistrez-le au format "
                "« Classeur Excel (*.xlsx) », puis rejoignez ce "
                "nouveau fichier." % (nom_fichier,)
            )
        elif not tete:
            cause = (
                "Fichier %r : fichier vide (0 octet) — vérifiez le "
                "fichier joint." % (nom_fichier,)
            )
        else:
            extrait = "".join(chr(b) if 32 <= b < 127 else "." for b in tete)
            cause = (
                "Fichier %r : contenu non-xlsx détecté (premiers "
                "octets : %s = %s) — un .xlsx est une archive zip "
                "(PK). Il s'agit probablement d'un fichier chiffré "
                "(propriétés Windows « chiffrer le contenu »), d'un "
                "fichier OneDrive/Teams non téléchargé, d'un CSV "
                "renommé ou d'un .xls. Ouvrez-le dans Excel et "
                "enregistrez-le au format « Classeur Excel (*.xlsx) »."
                % (nom_fichier, " ".join("%02x" % b for b in tete), extrait)
            )
        raise ErreurFEC(cause)

    # Lecture : openpyxl si disponible, sinon lecteur interne stdlib
    # (zipfile + XML) - aucune dependance externe obligatoire.
    try:
        rows = _lire_avec_openpyxl(brut)
    except ErreurFEC:
        raise
    except Exception as exc:
        if not _OPENPYXL_DISPONIBLE:
            try:
                rows = _lire_xlsx_stdlib(brut, nom_fichier)
            except ErreurFEC:
                raise
            except Exception as exc2:
                raise ErreurFEC(
                    "Classeur Excel illisible (%s) : %s" % (nom_fichier, exc2)
                )
        else:
            raise ErreurFEC(
                "Classeur Excel illisible (%s) : %s" % (nom_fichier, exc)
            )

    entete = _trouver_entete(rows, OBLIGATOIRES)
    if entete is None:
        # Export "Liste des ecritures" Cegid Quadra (Periode + Jour +
        # NumUniq, sans numero d'ecriture) : conversion dediee.
        entete_quadra = _trouver_entete(rows, QUADRA_OBLIGATOIRES)
        if entete_quadra is not None:
            idx_q, col_q = entete_quadra
            return _convertir_quadra(rows, idx_q, col_q, nom_fichier)
        raise ErreurFEC(
            "Ligne d'en-tete introuvable dans %r : CONCORDE attend au "
            "minimum les colonnes EcritureNum, EcritureDate, CompteNum, "
            "Debit, Credit (synonymes acceptes : Date, Compte, Libelle, "
            "Journal...) ou un export Cegid Quadra (Periode, Jour, "
            "Journal, Compte, Debit, Credit, NumUniq, TypeLigne). "
            "Aucune colonne n'est devinee." % (nom_fichier,)
        )

    idx, colonnes = entete

    def val(row: Sequence[CelluleXlsx], champ: str) -> CelluleXlsx:
        """Lit la cellule du champ `champ` dans la ligne `row`."""
        return _valeur_colonne(row, colonnes, champ)

    lignes_fec: list[dict[str, str]] = []
    debut_donnees = idx + 1
    for row in rows[debut_donnees:]:
        if row is None:
            continue
        compte = _nombre_texte(val(row, "CompteNum"))
        debit_c = _centimes(val(row, "Debit"), "Debit")
        credit_c = _centimes(val(row, "Credit"), "Credit")
        if not compte and debit_c == 0 and credit_c == 0:
            continue  # ligne vide / de presentation
        ecriture_num = _nombre_texte(val(row, "EcritureNum"))
        if not ecriture_num:
            raise ErreurFEC(
                "Ligne sans numero d'ecriture (colonne EcritureNum "
                "vide) : CONCORDE ne devine jamais un identifiant."
            )
        if not compte:
            raise ErreurFEC(
                "Ecriture %s sans numero de compte (colonne CompteNum "
                "vide) : CONCORDE ne devine jamais un compte." % ecriture_num
            )
        journal = _nettoyer_texte(val(row, "JournalCode")) or JOURNAL_DEFAUT
        journal_lib = _nettoyer_texte(val(row, "JournalLib")) or journal
        date_ecr = _date_fec(val(row, "EcritureDate"), "EcritureDate")
        libelle = _nettoyer_texte(val(row, "EcritureLib"))
        piece = _nettoyer_texte(val(row, "PieceRef"))
        compte_lib = _nettoyer_texte(val(row, "CompteLib"))

        lignes_fec.append(
            _construire_ligne_fec(
                journal=journal,
                journal_lib=journal_lib,
                ecriture_num=ecriture_num,
                date_ecr=date_ecr,
                compte=compte,
                compte_lib=compte_lib,
                piece=piece,
                libelle=libelle or piece or "Ecriture %s" % ecriture_num,
                debit_c=debit_c,
                credit_c=credit_c,
            )
        )

    if not lignes_fec:
        raise ErreurFEC(
            "Aucune ligne d'ecriture exploitable dans %r apres l'en-tete "
            "(colonne %s)." % (nom_fichier, "ligne %d" % (idx + 1))
        )
    return _encoder_fec(lignes_fec)


def _fmt_centimes(centimes: int) -> str:
    """Centimes int -> texte FEC a 2 decimales ('123.45', '-12.50')."""
    negatif = centimes < 0
    v = abs(int(centimes))
    s = "%d.%02d" % (v // 100, v % 100)
    return "-" + s if negatif else s
