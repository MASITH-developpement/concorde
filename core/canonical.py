# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Modèle canonique CONCORDE.

Règle d'or : les montants sont TOUJOURS en centimes (int).
Jamais de float, jamais d'arrondi silencieux.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Union


class ErreurMontant(ValueError):
    """Montant invalide ou arrondi silencieux tenté."""


def vers_centimes(texte: object) -> int:
    """Convertit un montant texte en centimes (int).

    Rôle : '123,45', '123.45', '123', '-12,50' -> 12345, 12345, 12300,
    -1250. L'arrondi silencieux est interdit.
    Paramètres : texte, montant (converti par str() avant lecture).
    Retour : le montant en centimes (0 pour un texte vide).
    Erreurs : ErreurMontant si plus de 2 décimales ou montant invalide.
    Usages : fec_parser, guardian (self-check), xlsx_vers_fec, migration.
    """
    s = str(texte).strip().replace(" ", "").replace(" ", "")
    if not s:
        return 0
    s = s.replace(".", ",")
    negatif = s.startswith("-")
    if negatif:
        s = s[1:]
    if "," in s:
        ent, dec = s.split(",", 1)
        if len(dec) > 2:
            raise ErreurMontant(
                "Arrondi silencieux interdit (plus de 2 decimales) : %r"
                % (texte,)
            )
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
    debit: int = 0  # centimes
    credit: int = 0  # centimes
    lettrage: str = ""
    piece: str = ""
    version_source: str = ""  # version Odoo d'origine (conversion 14->19)

    def cle_idempotence(self) -> str:
        """Clé d'idempotence : lignes identiques = doublon, non réimporté."""
        return "|".join(
            [
                self.journal_code,
                self.ecriture_num,
                self.compte,
                str(self.debit),
                str(self.credit),
                self.libelle,
            ]
        )

    @property
    def montant(self) -> int:
        """Montant signé de la ligne en centimes (débit - crédit)."""
        return self.debit - self.credit


class Canonique:
    """Journal canonique CONCORDE : ensemble idempotent de lignes."""

    def __init__(self) -> None:
        """Crée un journal vide."""
        self.lignes: list[LigneEcriture] = []
        self._cles: set[str] = set()
        self.doublons_ignores: int = 0

    def ajouter(self, ligne: LigneEcriture) -> bool:
        """Ajoute une ligne sauf doublon (idempotence). True si ajoutée."""
        cle = ligne.cle_idempotence()
        if cle in self._cles:
            self.doublons_ignores += 1
            return False
        self._cles.add(cle)
        self.lignes.append(ligne)
        return True

    @property
    def total_debit(self) -> int:
        """Somme des débits du journal, en centimes."""
        return sum(ligne.debit for ligne in self.lignes)

    @property
    def total_credit(self) -> int:
        """Somme des crédits du journal, en centimes."""
        return sum(ligne.credit for ligne in self.lignes)

    def est_equilibre(self, tolerance: int = 0) -> bool:
        """Tolerance Concordance = 0,00 EUR (0 centime)."""
        return abs(self.total_debit - self.total_credit) <= tolerance

    def __len__(self) -> int:
        """Nombre de lignes du journal."""
        return len(self.lignes)


def extraire_canon(
    donnees: Union[Canonique, dict[str, Any]],
) -> Optional[Canonique]:
    """Journal canonique porté par une donnée du pipeline.

    Rôle : une étape reçoit soit le Canonique, soit le dict produit par
    l'étape précédente (clé 'canon', ou 'resultat' -> 'canon').
    Paramètres : donnees, Canonique ou dict de pipeline (contenu
    dynamique, d'où Any).
    Retour : le Canonique trouvé, ou None si le dict n'en porte pas.
    Erreurs : aucune.
    Usages : lettrage.lettrer, mapping.mapper_comptes.
    """
    if not isinstance(donnees, dict):
        return donnees
    # Test « is None » et non de vérité : un Canonique vide est présent.
    canon_trouve: Optional[Canonique] = donnees.get("canon")
    if canon_trouve is None:
        canon_trouve = donnees.get("resultat", {}).get("canon")
    return canon_trouve
