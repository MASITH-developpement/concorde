# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 1 — connecteur FEC strict (migration).

Différences avec core/fec_parser.py (pipeline du module Odoo, inchangé) :
  - rien n'est sauté en silence : une ligne illisible (colonnes, date,
    montant) est gardée dans `lot.illisibles` avec son numéro et le motif ;
  - rien n'est dédoublonné : deux lignes identiques sont gardées (le contrôle
    des doublons les signale, c'est au comptable de trancher) ;
  - les 18 colonnes sont lues : tiers (CompAux), lettrage, devise.

Encodage : UTF-8 (avec ou sans BOM), sinon ISO-8859-15. Séparateur : | tab ;
Montants : virgule ou point, 2 décimales au plus (sinon ligne illisible).
"""

import hashlib
from datetime import date

from ..canonical import ErreurMontant, vers_centimes
from ..journal import Journal, nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from .lot import LigneIllisible, LigneLot, Lot

CHAMPS_REQUIS = (
    "JournalCode",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "Debit",
    "Credit",
)
PREAMBULE_MAX = 15


class ErreurConnecteur(ValueError):
    """Source illisible dans son ensemble (pas d'en-tête, encodage…)."""


def _decoder(brut: bytes) -> tuple[str, str]:
    """Décode le fichier : (texte, nom de l'encodage reconnu)."""
    if brut.startswith(b"\xef\xbb\xbf"):
        return brut[3:].decode("utf-8"), "utf-8 (BOM)"
    try:
        return brut.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return brut.decode("iso-8859-15"), "iso-8859-15"


def _date(texte: str | None) -> date | None:
    """Date FEC (AAAAMMJJ, ou JJ/MM/AAAA toléré) ; None si vide.

    Lève ValueError si la date est invalide.
    """
    texte = (texte or "").strip()
    if not texte:
        return None
    if len(texte) == 8 and texte.isdigit():
        return date(int(texte[:4]), int(texte[4:6]), int(texte[6:8]))
    if len(texte) == 10 and texte[2] == "/" and texte[5] == "/":
        return date(int(texte[6:]), int(texte[3:5]), int(texte[:2]))
    raise ValueError("date invalide %r" % texte)


def lire_fec(
    brut: bytes, nom: str = "fichier.fec", journal: Journal | None = None
) -> Lot:
    """Lit un FEC (bytes). Retourne un Lot.

    Lève ErreurConnecteur si le fichier est illisible dans son ensemble.
    """
    j = ou_muet(journal)
    empreinte = hashlib.sha256(brut).hexdigest()
    texte, encodage = _decoder(brut)
    lignes_txt = texte.splitlines()
    j.dire(
        "Lecture du FEC %s (%s octets, encodage %s, SHA-256 %s…)"
        % (nom, nombre_texte(len(brut)), encodage, empreinte[:12])
    )

    entete_i: int | None = None
    sep: str | None = None
    for i, ligne_texte in enumerate(lignes_txt[:PREAMBULE_MAX]):
        if "JournalCode" in ligne_texte and "EcritureNum" in ligne_texte:
            entete_i = i
            sep = next((s for s in ("|", "\t", ";") if s in ligne_texte), None)
            break
    if entete_i is None or sep is None:
        raise ErreurConnecteur(
            "En-tête FEC (JournalCode, EcritureNum…) introuvable "
            "dans les %d premières lignes." % PREAMBULE_MAX
        )
    champs = [
        c.strip().strip('"').lstrip("﻿")
        for c in lignes_txt[entete_i].split(sep)
    ]
    manquants = [c for c in CHAMPS_REQUIS if c not in champs]
    if manquants:
        raise ErreurConnecteur(
            "Colonnes FEC obligatoires absentes : %s" % ", ".join(manquants)
        )
    index_champs = {c: i for i, c in enumerate(champs)}
    j.dire(
        "En-tête trouvée ligne %d : %d colonnes, séparateur %s"
        % (
            entete_i + 1,
            len(champs),
            {"|": "« | »", "\t": "tabulation", ";": "« ; »"}[sep],
        ),
        "detail",
    )
    absentes = [
        c
        for c in (
            "CompAuxNum",
            "CompAuxLib",
            "EcritureLet",
            "DateLet",
            "PieceRef",
            "EcritureLib",
            "CompteLib",
            "JournalLib",
        )
        if c not in index_champs
    ]
    if absentes:
        j.dire(
            "Colonnes facultatives absentes (laissées vides) : %s"
            % ", ".join(absentes),
            "alerte",
        )

    def valeur_champ(valeurs: list[str], nom_champ: str) -> str:
        """Valeur nettoyée d'une colonne de la ligne ; vide si absente."""
        i = index_champs.get(nom_champ)
        return (
            valeurs[i].strip().strip('"')
            if i is not None and i < len(valeurs)
            else ""
        )

    lignes: list[LigneLot] = []
    illisibles: list[LigneIllisible] = []
    debut_donnees = entete_i + 1
    for n, brute in enumerate(
        lignes_txt[debut_donnees:], start=debut_donnees + 1
    ):
        if not brute.strip():
            continue
        valeurs = brute.split(sep)
        if len(valeurs) != len(champs):
            illisibles.append(
                (
                    n,
                    brute[:200],
                    "%d colonnes au lieu de %d" % (len(valeurs), len(champs)),
                )
            )
            continue
        try:
            date_ecriture = _date(valeur_champ(valeurs, "EcritureDate"))
            date_piece = _date(valeur_champ(valeurs, "PieceDate"))
            debit = vers_centimes(valeur_champ(valeurs, "Debit") or "0")
            credit = vers_centimes(valeur_champ(valeurs, "Credit") or "0")
            date_lettrage = _date(valeur_champ(valeurs, "DateLet"))
            date_validation = _date(valeur_champ(valeurs, "ValidDate"))
            montant_devise = (
                vers_centimes(valeur_champ(valeurs, "Montantdevise"))
                if valeur_champ(valeurs, "Montantdevise")
                else None
            )
            if date_ecriture is None:
                raise ValueError("EcritureDate vide")
            if debit < 0 or credit < 0:
                raise ValueError(
                    "montant négatif (le FEC porte des montants positifs)"
                )
        except (ValueError, ErreurMontant) as exc:
            illisibles.append((n, brute[:200], str(exc)))
            continue
        lignes.append(
            {
                "n": n,
                "journal_code": valeur_champ(valeurs, "JournalCode"),
                "journal_lib": valeur_champ(valeurs, "JournalLib"),
                "ecriture": valeur_champ(valeurs, "EcritureNum"),
                "date": date_ecriture,
                "compte": valeur_champ(valeurs, "CompteNum"),
                "compte_lib": valeur_champ(valeurs, "CompteLib"),
                "tiers_ref": valeur_champ(valeurs, "CompAuxNum"),
                "tiers_nom": valeur_champ(valeurs, "CompAuxLib"),
                "piece": valeur_champ(valeurs, "PieceRef"),
                "piece_date": date_piece,
                "libelle": valeur_champ(valeurs, "EcritureLib"),
                "debit": debit,
                "credit": credit,
                "lettrage": valeur_champ(valeurs, "EcritureLet"),
                "date_lettrage": date_lettrage,
                "valid_date": date_validation,
                "montant_devise": montant_devise,
                "devise": valeur_champ(valeurs, "Idevise"),
                "analytique": "",  # absent de la norme FEC
                "compte_cible": None,
            }
        )

    lot = Lot(
        {
            "type": "fec",
            "nom": nom,
            "empreinte": empreinte,
            "encodage": encodage,
            "separateur": sep,
            "lignes_fichier": len(lignes_txt),
        },
        lignes,
    )
    lot.illisibles = illisibles
    totaux = lot.totaux()
    j.dire(
        "%s lignes lues, %s écritures, débit %s / crédit %s"
        % (
            nombre_texte(totaux["lignes"]),
            nombre_texte(totaux["ecritures"]),
            _euros(totaux["debit"]),
            _euros(totaux["credit"]),
        ),
        "ok",
    )
    if illisibles:
        j.dire(
            "%d ligne(s) illisible(s) — elles bloquent la migration "
            "(détail dans les problèmes)" % len(illisibles),
            "erreur",
        )
    return lot


def _euros(centimes: int) -> str:
    """Montant en centimes -> « 1234,56 € »."""
    return euros_texte(centimes, ",") + " €"
