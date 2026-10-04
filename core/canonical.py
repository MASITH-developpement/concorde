# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Modèle canonique CONCORDE.

Règle d'or : les montants sont TOUJOURS en centimes (int).
Jamais de float, jamais d'arrondi silencieux.
"""
from dataclasses import dataclass, field
from datetime import date


class ErreurMontant(ValueError):
    """Montant invalide ou arrondi silencieux tenté."""


def vers_centimes(texte) -> int:
    """Convertit un montant texte ('123,45', '123.45', '123', '-12,50') en centimes int.

    Refuse strictement plus de 2 décimales : l'arrondi silencieux est interdit.
    """
    s = str(texte).strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return 0
    s = s.replace(".", ",")
    negatif = s.startswith("-")
    if negatif:
        s = s[1:]
    if "," in s:
        ent, dec = s.split(",", 1)
        if len(dec) > 2:
            raise ErreurMontant("Arrondi silencieux interdit (plus de 2 decimales) : %r" % (texte,))
        dec = (dec + "00")[:2]
    else:
        ent, dec = s, "00"
    if not ent.isdigit() or not dec.isdigit():
        raise ErreurMontant("Montant invalide : %r" % (texte,))
    val = int(ent) * 100 + int(dec)
    return -val if negatif else val


@dataclass
class LigneEcriture:
    """Une ligne d'écriture canonique. Montants en centimes int."""
    journal_code: str
    ecriture_num: str
    date_ecriture: date
    compte: str
    libelle: str
    debit: int = 0   # centimes
    credit: int = 0  # centimes
    lettrage: str = ""
    piece: str = ""

    def cle_idempotence(self) -> str:
        """Clé d'idempotence : deux lignes identiques = doublon, jamais réimportées."""
        return "|".join([
            self.journal_code, self.ecriture_num, self.compte,
            str(self.debit), str(self.credit), self.libelle,
        ])

    @property
    def montant(self) -> int:
        return self.debit - self.credit


class Canonique:
    """Journal canonique CONCORDE : ensemble idempotent de lignes, en centimes."""

    def __init__(self):
        self.lignes: list = []
        self._cles: set = set()
        self.doublons_ignores: int = 0

    def ajouter(self, ligne: LigneEcriture) -> bool:
        """Ajoute une ligne sauf doublon (idempotence). Retourne True si ajoutée."""
        cle = ligne.cle_idempotence()
        if cle in self._cles:
            self.doublons_ignores += 1
            return False
        self._cles.add(cle)
        self.lignes.append(ligne)
        return True

    @property
    def total_debit(self) -> int:
        return sum(l.debit for l in self.lignes)

    @property
    def total_credit(self) -> int:
        return sum(l.credit for l in self.lignes)

    def est_equilibre(self, tolerance: int = 0) -> bool:
        """Tolerance Concordance = 0,00 EUR (0 centime)."""
        return abs(self.total_debit - self.total_credit) <= tolerance

    def __len__(self):
        return len(self.lignes)
