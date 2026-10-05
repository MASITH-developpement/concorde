# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Convertisseur Excel -> FEC (exports d'ecritures comptables).

Construit pour les exports Excel Quadra / peripheriques qui ne sont pas
des FEC texte : CONCORDE les convertit en FEC standard avant le pipeline.

Regles CONCORDE :
- Tolerance 0 : aucun arrondi silencieux (montant a plus de 2 decimales = refus)
- Aucun compte devine, aucune colonne devine : colonnes obligatoires
  explicites, messages d'erreur explicites (Marceau : jamais muet)
- Montants convertis en centimes via core.canonical.vers_centimes
- Dates normalisees en AAAAMMJJ (format FEC obligatoire)
"""
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

from .canonical import vers_centimes

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None


class ErreurFEC(ValueError):
    pass


# Colonnes FEC produites (ordre FEC standard, separateur tabulation)
CHAMPS_FEC = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise",
]

# Synonymes de colonnes d'entete Excel, normalises (minuscules, sans accent,
# sans espace/point/tiret/underscore).
SYNONYMES = {
    "JournalCode": [
        "journalcode", "journal", "jnl", "codejournal", "jl", "codejnl",
    ],
    "JournalLib": ["journallib", "journallibelle", "libjournal"],
    "EcritureNum": [
        "ecriturenum", "ecrituren", "numecriture", "noecriture",
        "numeroecriture", "nbecriture", "idecriture", "ecriture",
        "ecritureno", "necriture", "numecrire",
    ],
    "EcritureDate": [
        "ecrituredate", "dateecriture", "date", "datecomptable",
        "datepiece", "dat", "datee",
    ],
    "CompteNum": [
        "comptenum", "compte", "accountn", "account", "numcompte",
        "numerocompte", "nocompte", "codecompte", "general",
        "cpte", "comptegeneral",
    ],
    "CompteLib": ["comptelib", "libcompte", "intitulecompte", "libellecompte"],
    "PieceRef": ["pieceref", "piece", "numpiece", "refpiece", "ref"],
    "EcritureLib": [
        "ecriturelib", "libelle", "lib", "libelleecriture", "libecriture",
        "intitule", "description", "libellé",
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


def _norm(texte) -> str:
    """Normalise un en-tete : minuscules, sans accent, sans separators."""
    s = str(texte or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for sep in (" ", ".", "-", "_", "'", "(", ")", "/", "\u00a0", "°"):
        s = s.replace(sep, "")
    return s


def _nettoyer_texte(v) -> str:
    """Texte FEC sur : tabulations/retours interdits (separateur tab)."""
    if v is None:
        return ""
    s = str(v).strip()
    for bad in ("\t", "\r", "\n"):
        s = s.replace(bad, " ")
    return s


def _date_fec(v, contexte: str) -> str:
    """Convertit une cellule date en AAAAMMJJ. Jamais de date devinee."""
    if isinstance(v, datetime):
        return v.strftime("%Y%m%d")
    if isinstance(v, date):
        return v.strftime("%Y%m%d")
    s = _nettoyer_texte(v)
    chiffres = s.replace("/", "").replace("-", "").replace(".", "").replace(" ", "")
    if len(chiffres) == 8 and chiffres.isdigit():
        # AAAAMMJJ ou JJMMAAAA : leve par plausibilite de l'annee,
        # CONCORDE ne devine jamais une date ambigue.
        if 1900 <= int(chiffres[:4]) <= 2100:
            annee, mois, jour = int(chiffres[:4]), int(chiffres[4:6]), int(chiffres[6:8])
            ordre = "AAAAMMJJ"
        elif 1900 <= int(chiffres[4:]) <= 2100:
            jour, mois, annee = int(chiffres[:2]), int(chiffres[2:4]), int(chiffres[4:])
            ordre = "JJMMAAAA"
        else:
            raise ErreurFEC(
                "Date ambigue en colonne %s : %r (ni AAAAMMJJ ni JJMMAAAA "
                "plausibles : re-exportez la colonne en date Excel)" %
                (contexte, v))
    elif len(chiffres) == 6 and chiffres.isdigit():
        # JJMMAA (Quadra) : annee 19xx/20xx selon le siecle plausible
        jour, mois, annee = int(chiffres[:2]), int(chiffres[2:4]), int(chiffres[4:6])
        annee += 2000 if annee < 70 else 1900
        ordre = "JJMMAA"
    else:
        raise ErreurFEC(
            "Date invalide en colonne %s : %r "
            "(formats attendus : date Excel, AAAAMMJJ, JJ/MM/AAAA)" %
            (contexte, v))
    try:
        date(annee, mois, jour)
    except ValueError:
        raise ErreurFEC(
            "Date invalide en colonne %s : %r (ordre %s)" %
            (contexte, v, ordre))
    return "%04d%02d%02d" % (annee, mois, jour)


def _centimes(v, contexte: str) -> int:
    """Cellule montant -> centimes int. Aucun arrondi silencieux."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return 0
    if isinstance(v, (int, float)):
        cent = v * 100
        arrondi = round(cent)
        if abs(cent - arrondi) > 1e-6:
            raise ErreurFEC(
                "Arrondi silencieux interdit : %.6f en colonne %s "
                "(plus de 2 decimales, tolerance 0)" % (v, contexte))
        return int(arrondi)
    return vers_centimes(_nettoyer_texte(v))


def _nombre_texte(v) -> str:
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


def _trouver_entete(rows):
    """Cherche la ligne d'en-tete dans les MAX_RECHERCHE_ENTETE premieres
    lignes. Retourne (index_ligne, {champ_fec: index_colonne}).
    """
    for i, ligne in enumerate(rows):
        if i >= MAX_RECHERCHE_ENTETE:
            break
        if ligne is None:
            continue
        trouve = {}
        for j, cellule in enumerate(ligne):
            nom = _norm(cellule)
            if not nom:
                continue
            for champ, synos in SYNONYMES.items():
                if champ in trouve:
                    continue
                if nom in synos:
                    trouve[champ] = j
        manquants = [c for c in OBLIGATOIRES if c not in trouve]
        # Entete valide si Debit+Credit+une date+un numero d'ecriture/compte
        noyau = {"Debit", "Credit"} & set(trouve)
        if not manquants and len(noyau) == 2:
            return i, trouve
    return None, None


def _lire_avec_openpyxl(brut):
    """Lecture via openpyxl (si installe). Retourne une liste de lignes."""
    if load_workbook is None:
        raise ImportError("openpyxl absent")
    wb = load_workbook(io.BytesIO(brut), read_only=True, data_only=True)
    try:
        feuille = wb.worksheets[0]
        rows = []
        for row in feuille.iter_rows(values_only=True):
            rows.append(row)
            if len(rows) > 200000:
                break
        return rows
    finally:
        wb.close()


# ---- Lecteur xlsx interne, bibliotheque standard uniquement ----
NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL_OFFICE = ("{http://schemas.openxmlformats.org/"
                 "officeDocument/2006/relationships}")
EPOQUE_EXCEL = date(1899, 12, 30)  # serie 0 = 30/12/1899
FORMATS_DATE_BUILTIN = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
_RE_DATE = re.compile(r"[dmyhs]", re.IGNORECASE)


def _colonne_xlsx(ref):
    """'B12' -> 1 (index 0)."""
    lettres = re.match(r"([A-Z]+)", ref or "")
    if not lettres:
        raise ErreurFEC("Reference de cellule invalide : %r" % (ref,))
    n = 0
    for ch in lettres.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _est_format_date(code):
    """Format de nombre date ? (guillemets et echappements ignores)."""
    code = re.sub(r'"[^"]*"', "", code).replace("\\", "")
    return bool(_RE_DATE.search(code))


def _styles_date(zf):
    """Indices de style (cellXfs) correspondant a des formats date."""
    try:
        racine = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return set()
    formats_date = set(FORMATS_DATE_BUILTIN)
    for fmt in racine.iter(NS_MAIN + "numFmt"):
        fid = fmt.get("numFmtId")
        if fid and _est_format_date(fmt.get("formatCode") or ""):
            formats_date.add(int(fid))
    indices = set()
    for i, xf in enumerate(racine.iter(NS_MAIN + "xf")):
        fid = xf.get("numFmtId")
        if fid and int(fid) in formats_date:
            indices.add(i)
    return indices


def _valeur_date(serie):
    """Numero de serie Excel -> date. Jamais de date devinee."""
    return EPOQUE_EXCEL + timedelta(days=int(serie))


def _lire_xlsx_stdlib(brut, nom_fichier=""):
    """Lecture d'un classeur .xlsx sans openpyxl (zipfile + ElementTree).

    Gere : sharedStrings, inlineStr, chaines de formule, references de
    cellules (colonnes eparses), styles date (serie Excel -> date).
    Retourne une liste de tuples (une ligne = un tuple).
    """
    zf = zipfile.ZipFile(io.BytesIO(brut))

    # 1. Chaines partagees
    sst = []
    if "xl/sharedStrings.xml" in zf.namelist():
        racine = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in racine.iter(NS_MAIN + "si"):
            sst.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))

    # 2. Indices de style date
    styles_date = _styles_date(zf)

    # 3. Premiere feuille declaree (via les relations du classeur)
    feuille_xml = None
    try:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheet = next(iter(wb.iter(NS_MAIN + "sheet")))
        rid = sheet.get(NS_REL_OFFICE + "id")
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
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
    except StopIteration:
        pass
    if not feuille_xml or feuille_xml not in zf.namelist():
        # repli : premiere feuille triee si relations absentes
        cands = sorted(n for n in zf.namelist()
                       if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not cands:
            raise ErreurFEC(
                "Aucune feuille de calcul trouvee dans %r." % (nom_fichier,))
        feuille_xml = cands[0]

    # 4. Lecture des lignes
    racine = ET.fromstring(zf.read(feuille_xml))
    lignes = []
    largeur = 0
    for row in racine.iter(NS_MAIN + "row"):
        if len(lignes) > 200000:
            break
        vals = {}
        for c in row.iter(NS_MAIN + "c"):
            ref = c.get("r") or ""
            j = _colonne_xlsx(ref)
            t = c.get("t")
            v = c.find(NS_MAIN + "v")
            is_elem = c.find(NS_MAIN + "is")
            if t == "s" and v is not None:
                try:
                    val = sst[int(v.text)]
                except (ValueError, IndexError):
                    raise ErreurFEC(
                        "Indice de chaine partagee invalide en %s de %r." %
                        (ref, nom_fichier))
            elif t == "inlineStr" and is_elem is not None:
                val = "".join(x.text or ""
                              for x in is_elem.iter(NS_MAIN + "t"))
            elif t == "str" and v is not None:
                val = v.text
            elif v is not None and v.text is not None:
                texte = v.text.strip()
                if c.get("s") and int(c.get("s")) in styles_date:
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
# Regroupement explicite en ecritures equilibrees : accumulation
# sequentielle des lignes (meme journal, meme date) jusqu'a ce que le
# cumul debit egale le cumul credit au centime (tolerance 0). Aucun
# regroupement devine : un groupe non solde = erreur explicite.

QUADRA_OBLIGATOIRES = ["Periode", "Jour", "JournalCode", "CompteNum",
                       "EcritureLib", "Debit", "Credit", "NumUniq"]
QUADRA_MAX_LIGNES_GROUPE = 1000


def _trouver_entete_quadra(rows):
    """Detecte l'en-tete d'un export Cegid Quadra. Retourne
    (index_ligne, {champ: index_colonne}) ou (None, None)."""
    for i, ligne in enumerate(rows):
        if i >= MAX_RECHERCHE_ENTETE:
            break
        if ligne is None:
            continue
        trouve = {}
        for j, cellule in enumerate(ligne):
            nom = _norm(cellule)
            if not nom:
                continue
            for champ, synos in SYNONYMES.items():
                if champ in trouve:
                    continue
                if nom in synos:
                    trouve[champ] = j
        manquants = [c for c in QUADRA_OBLIGATOIRES if c not in trouve]
        if not manquants:
            return i, trouve
    return None, None


def _date_quadra(periode, jour, contexte):
    """Periode (JJ/MM/AAAA) + Jour -> date AAAAMMJJ. Le jour vient de la
    colonne Jour, le mois et l'annee de la Periode. Jamais devine."""
    p = _date_fec(periode, contexte + "/Periode")  # valide JJ/MM/AAAA
    mois, annee = int(p[4:6]), int(p[:4])
    j_txt = str(jour or "").strip()
    if not j_txt.isdigit() or not 1 <= int(j_txt) <= 31:
        raise ErreurFEC(
            "Jour invalide (%r) en colonne %s/Jour : CONCORDE attend un "
            "numero de jour 1-31." % (jour, contexte))
    try:
        date(annee, mois, int(j_txt))
    except ValueError:
        raise ErreurFEC(
            "Date invalide : jour %s inexistant en %02d/%d "
            "(colonnes Periode/Jour)." % (j_txt, mois, annee))
    return "%04d%02d%02d" % (annee, mois, int(j_txt))


def _convertir_quadra(rows, idx, colonnes, nom_fichier):
    """Convertit un export Cegid Quadra en FEC standard.

    Regroupement en ecritures equilibrees : coupe des que le cumul
    debit == cumul credit (meme journal + meme date). Le numero
    d'ecriture retenu est le NumUniq de la premiere ligne du groupe.
    """
    def val(row, champ):
        j = colonnes.get(champ)
        if j is None or j >= len(row):
            return None
        return row[j]

    out = ["\t".join(CHAMPS_FEC)]
    nb_lignes = 0
    nb_ecritures = 0
    # groupe en cours
    g_lignes = []       # lignes FEC en attente de numerotation
    g_journal = None
    g_date = None
    g_debit = 0
    g_credit = 0
    g_premier = None    # NumUniq de la premiere ligne

    def soldage_err():
        return ErreurFEC(
            "Ecriture non soldee apres %d lignes (journal %s, date %s, "
            "NumUniq %s..%s, debit %d != credit %d centimes) : CONCORDE "
            "ne cree jamais une ecriture desequilibree. Verifiez "
            "l'export Quadra (tranchee complete, meme journal/date)." %
            (len(g_lignes), g_journal, g_date, g_premier,
             g_lignes[-1]["numuniq"] if g_lignes else "?",
             g_debit, g_credit))

    def clorre_groupe():
        nonlocal nb_lignes, g_lignes, g_journal, g_date
        nonlocal g_debit, g_credit, g_premier
        # Lignes strictement identiques (compte/montants/libelle) dans la
        # meme ecriture : l'idempotence canonique les fusionnerait et
        # desequilibrerait l'ecriture. On distingue les occurrences par
        # leur NumUniq, appose au libelle (jamais silencieusement).
        vus = set()
        for d in g_lignes:
            f = d["fec"]
            cle = (f["CompteNum"], f["Debit"], f["Credit"], f["EcritureLib"])
            if cle in vus:
                f["EcritureLib"] = "%s [%s]" % (f["EcritureLib"], d["numuniq"])
            else:
                vus.add(cle)
        for d in g_lignes:
            ligne = dict(d["fec"])
            ligne["EcritureNum"] = g_premier
            out.append("\t".join(ligne[c] for c in CHAMPS_FEC))
            nb_lignes += 1
        g_lignes, g_journal, g_date = [], None, None
        g_debit, g_credit, g_premier = 0, 0, None

    for row in rows[idx + 1:]:
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
                "un identifiant." % (nom_fichier,))
        if not compte:
            raise ErreurFEC(
                "Ligne NumUniq %s sans numero de compte : CONCORDE ne "
                "devine jamais un compte." % numuniq)
        typ = _nettoyer_texte(val(row, "TypeLigne"))
        if typ and typ != "E":
            raise ErreurFEC(
                "TypeLigne %r inconnu (NumUniq %s) : CONCORDE ne traite "
                "que les lignes d'ecriture 'E'. Aucune ligne devinee." %
                (typ, numuniq))
        journal = _nettoyer_texte(val(row, "JournalCode"))
        if not journal:
            raise ErreurFEC(
                "Ligne NumUniq %s sans journal : CONCORDE ne devine "
                "jamais un journal." % numuniq)
        date_ecr = _date_quadra(val(row, "Periode"), val(row, "Jour"),
                                "NumUniq %s" % numuniq)
        libelle = _nettoyer_texte(val(row, "EcritureLib"))

        # regroupement : un groupe ne peut pas couvrir deux journaux
        # ni deux dates ; un groupe non solde est une erreur explicite.
        if g_lignes and (journal != g_journal or date_ecr != g_date):
            raise soldage_err()
        if len(g_lignes) >= QUADRA_MAX_LIGNES_GROUPE:
            raise soldage_err()
        if not g_lignes:
            g_journal, g_date, g_premier = journal, date_ecr, numuniq
        g_lignes.append({
            "numuniq": numuniq,
            "fec": {
                "JournalCode": journal,
                "JournalLib": journal,
                "EcritureNum": "",  # remplace a la cloture du groupe
                "EcritureDate": date_ecr,
                "CompteNum": compte,
                "CompteLib": "",
                "CompAuxNum": "",
                "CompAuxLib": "",
                "PieceRef": _nettoyer_texte(val(row, "PieceRef")),
                "PieceDate": date_ecr,
                "EcritureLib": libelle or ("Ecriture %s" % numuniq),
                "Debit": _fmt_centimes(debit_c),
                "Credit": _fmt_centimes(credit_c),
                "EcritureLet": "",
                "DateLet": "",
                "ValidDate": date_ecr,
                "Montantdevise": "",
                "Idevise": "",
            },
        })
        g_debit += debit_c
        g_credit += credit_c
        if g_debit == g_credit:
            clorre_groupe()
            nb_ecritures += 1

    if g_lignes:
        raise soldage_err()

    if nb_lignes == 0:
        raise ErreurFEC(
            "Aucune ligne d'ecriture exploitable dans %r apres l'en-tete "
            "(ligne %d)." % (nom_fichier, idx + 1))
    return ("\n".join(out) + "\n").encode("utf-8")

def xlsx_vers_fec(brut: bytes, nom_fichier: str = "") -> bytes:
    """Convertit un classeur xlsx (bytes) en texte FEC (bytes UTF-8).

    Le FEC produit respecte le format attendu par core.fec_parser :
    en-tete JournalCode/EcritureNum..., dates AAAAMMJJ, montants texte.
    """
    if not brut.startswith(b"PK"):
        raise ErreurFEC(
            "Fichier %r non reconnu comme classeur .xlsx (binaire zip "
            "attendu). L'ancien format .xls n'est pas supporte : "
            "re-exportez en .xlsx depuis Excel/Quadra." % (nom_fichier,))

    # Lecture : openpyxl si disponible, sinon lecteur interne stdlib
    # (zipfile + XML) - aucune dependance externe obligatoire.
    try:
        rows = _lire_avec_openpyxl(brut)
    except ErreurFEC:
        raise
    except Exception as exc:
        if load_workbook is None:
            try:
                rows = _lire_xlsx_stdlib(brut, nom_fichier)
            except ErreurFEC:
                raise
            except Exception as exc2:
                raise ErreurFEC(
                    "Classeur Excel illisible (%s) : %s" % (nom_fichier, exc2))
        else:
            raise ErreurFEC(
                "Classeur Excel illisible (%s) : %s" % (nom_fichier, exc))

    idx, colonnes = _trouver_entete(rows)
    if colonnes is None:
        # Export "Liste des ecritures" Cegid Quadra (Periode + Jour +
        # NumUniq, sans numero d'ecriture) : conversion dediee.
        idx_q, col_q = _trouver_entete_quadra(rows)
        if col_q is not None:
            return _convertir_quadra(rows, idx_q, col_q, nom_fichier)
        raise ErreurFEC(
            "Ligne d'en-tete introuvable dans %r : CONCORDE attend au "
            "minimum les colonnes EcritureNum, EcritureDate, CompteNum, "
            "Debit, Credit (synonymes acceptes : Date, Compte, Libelle, "
            "Journal...) ou un export Cegid Quadra (Periode, Jour, "
            "Journal, Compte, Debit, Credit, NumUniq, TypeLigne). "
            "Aucune colonne n'est devinee." % (nom_fichier,))

    def val(row, champ):
        j = colonnes.get(champ)
        if j is None or j >= len(row):
            return None
        return row[j]

    out = ["\t".join(CHAMPS_FEC)]
    nb_lignes = 0
    for row in rows[idx + 1:]:
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
                "vide) : CONCORDE ne devine jamais un identifiant.")
        if not compte:
            raise ErreurFEC(
                "Ecriture %s sans numero de compte (colonne CompteNum "
                "vide) : CONCORDE ne devine jamais un compte." % ecriture_num)
        journal = _nettoyer_texte(val(row, "JournalCode")) or JOURNAL_DEFAUT
        journal_lib = _nettoyer_texte(val(row, "JournalLib")) or journal
        date_ecr = _date_fec(val(row, "EcritureDate"), "EcritureDate")
        libelle = _nettoyer_texte(val(row, "EcritureLib"))
        piece = _nettoyer_texte(val(row, "PieceRef"))
        compte_lib = _nettoyer_texte(val(row, "CompteLib"))

        ligne = {
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
            "EcritureLib": libelle or piece or "Ecriture %s" % ecriture_num,
            "Debit": _fmt_centimes(debit_c),
            "Credit": _fmt_centimes(credit_c),
            "EcritureLet": "",
            "DateLet": "",
            "ValidDate": date_ecr,
            "Montantdevise": "",
            "Idevise": "",
        }
        out.append("\t".join(ligne[c] for c in CHAMPS_FEC))
        nb_lignes += 1

    if nb_lignes == 0:
        raise ErreurFEC(
            "Aucune ligne d'ecriture exploitable dans %r apres l'en-tete "
            "(colonne %s)." % (nom_fichier, "ligne %d" % (idx + 1)))
    return ("\n".join(out) + "\n").encode("utf-8")


def _fmt_centimes(centimes: int) -> str:
    """Centimes int -> texte FEC a 2 decimales ('123.45', '-12.50')."""
    negatif = centimes < 0
    v = abs(int(centimes))
    s = "%d.%02d" % (v // 100, v % 100)
    return "-" + s if negatif else s
