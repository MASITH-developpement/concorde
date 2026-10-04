# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Parseur FEC (Fichier des Écritures Comptables).

- Encodage auto-détecté : UTF-8 puis ISO-8859-1 (Quadra exporte en ISO-8859-1)
- Séparateur auto-détecté : tabulation, ';' ou '|'
- Préambule ignoré (jusqu'à 14 lignes) avant la ligne d'en-tête FEC
- Refus strict des montants à plus de 2 décimales (pas d'arrondi silencieux)
"""
from datetime import date

from .canonical import Canonique, LigneEcriture, vers_centimes

SEPARATEURS = ["\t", ";", "|"]
MAX_PREAMBULE = 14
CHAMPS_REQUIS = {"JournalCode", "EcritureNum", "EcritureDate",
                 "CompteNum", "EcritureLib", "Debit", "Credit"}


class ErreurFEC(ValueError):
    pass


def _detecter_encodage(brut: bytes) -> str:
    for enc in ("utf-8", "iso-8859-1"):
        try:
            brut.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ErreurFEC("Encodage FEC non reconnu (UTF-8 / ISO-8859-1 attendus).")


def _detecter_separateur(ligne: str) -> str:
    """Détecte le séparateur sur la ligne d'entête FEC."""
    for sep in SEPARATEURS:
        if sep in ligne:
            return sep
    raise ErreurFEC("Séparateur FEC non reconnu (tab, ';' ou '|' attendus).")


def _parse_date(v: str) -> date:
    v = v.strip()
    if len(v) == 8 and v.isdigit():
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    raise ErreurFEC("Date FEC invalide : %r" % (v,))


def _trouver_entete(lignes):
    """Retourne (index_entete, liste_champs) en ignorant le préambule (<=14 lignes)."""
    for i, ligne in enumerate(lignes):
        if "JournalCode" in ligne and "EcritureNum" in ligne:
            return i, [c.strip() for c in ligne.replace("\t", ";").replace("|", ";").split(";")]
        if i >= MAX_PREAMBULE:
            break
    raise ErreurFEC("Ligne d'en-tête FEC (JournalCode/EcritureNum) introuvable.")


def parse_fec(source) -> Canonique:
    """Parse un FEC (chemin de fichier, bytes ou str) en journal canonique."""
    if isinstance(source, (bytes, bytearray)):
        brut = bytes(source)
    elif isinstance(source, str) and "\n" not in source and len(source) < 300:
        with open(source, "rb") as f:
            brut = f.read()
    elif isinstance(source, str):
        brut = source.encode("utf-8", errors="replace")
    else:
        raise ErreurFEC("Source FEC non supportée.")

    enc = _detecter_encodage(brut)
    texte = brut.decode(enc)
    lignes = [l for l in texte.splitlines() if l.strip()]
    idx, _ = _trouver_entete(lignes)
    sep = _detecter_separateur(lignes[idx])
    champs = [c.strip().strip('"') for c in lignes[idx].split(sep)]
    manquants = CHAMPS_REQUIS - set(champs)
    if manquants:
        raise ErreurFEC("Champs FEC manquants : %s" % ", ".join(sorted(manquants)))

    canon = Canonique()
    idxs = {c: champs.index(c) for c in champs}
    for ligne in lignes[idx + 1:]:
        vals = [v.strip().strip('"') for v in ligne.split(sep)]
        if len(vals) < len(champs):
            continue
        debit = vers_centimes(vals[idxs["Debit"]] or "0")
        credit = vers_centimes(vals[idxs["Credit"]] or "0")
        canon.ajouter(LigneEcriture(
            journal_code=vals[idxs["JournalCode"]],
            ecriture_num=vals[idxs["EcritureNum"]],
            date_ecriture=_parse_date(vals[idxs["EcritureDate"]]),
            compte=vals[idxs["CompteNum"]],
            libelle=vals[idxs["EcritureLib"]],
            debit=debit,
            credit=credit,
            piece=vals[idxs["PieceRef"]] if "PieceRef" in idxs else "",
        ))
    return canon
