# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 1 — connecteur FEC strict (migration).

Différences avec core/fec_parser.py (pipeline du module Odoo, inchangé) :
  - rien n'est sauté en silence : une ligne illisible (colonnes, date, montant)
    est gardée dans `lot.illisibles` avec son numéro et le motif ;
  - rien n'est dédoublonné : deux lignes identiques sont gardées (le contrôle
    des doublons les signale, c'est au comptable de trancher) ;
  - les 18 colonnes sont lues : tiers (CompAux), lettrage, devise.

Encodage : UTF-8 (avec ou sans BOM), sinon ISO-8859-15. Séparateur : | tab ;
Montants : virgule ou point, 2 décimales au plus (sinon ligne illisible).
"""

import hashlib
from datetime import date

from ..canonical import ErreurMontant, vers_centimes
from ..journal import nombre_texte, ou_muet
from .lot import Lot

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
    """Source illisible dans son ensemble (pas d'en-tête, encodage inconnu…)."""


def _decoder(brut):
    if brut.startswith(b"\xef\xbb\xbf"):
        return brut[3:].decode("utf-8"), "utf-8 (BOM)"
    try:
        return brut.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return brut.decode("iso-8859-15"), "iso-8859-15"


def _date(v):
    v = (v or "").strip()
    if not v:
        return None
    if len(v) == 8 and v.isdigit():
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    if len(v) == 10 and v[2] == "/" and v[5] == "/":  # JJ/MM/AAAA toléré
        return date(int(v[6:]), int(v[3:5]), int(v[:2]))
    raise ValueError("date invalide %r" % v)


def lire_fec(brut, nom="fichier.fec", journal=None):
    """Lit un FEC (bytes). Retourne un Lot. Lève ErreurConnecteur si illisible."""
    j = ou_muet(journal)
    empreinte = hashlib.sha256(brut).hexdigest()
    texte, encodage = _decoder(brut)
    lignes_txt = texte.splitlines()
    j.dire(
        "Lecture du FEC %s (%s octets, encodage %s, SHA-256 %s…)"
        % (nom, nombre_texte(len(brut)), encodage, empreinte[:12])
    )

    entete_i, sep = None, None
    for i, l in enumerate(lignes_txt[:PREAMBULE_MAX]):
        if "JournalCode" in l and "EcritureNum" in l:
            entete_i = i
            sep = next((s for s in ("|", "\t", ";") if s in l), None)
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
    idx = {c: i for i, c in enumerate(champs)}
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
        if c not in idx
    ]
    if absentes:
        j.dire(
            "Colonnes facultatives absentes (laissées vides) : %s"
            % ", ".join(absentes),
            "alerte",
        )

    def val(vals, nom_champ):
        i = idx.get(nom_champ)
        return (
            vals[i].strip().strip('"')
            if i is not None and i < len(vals)
            else ""
        )

    lignes, illisibles = [], []
    for n, brute in enumerate(lignes_txt[entete_i + 1 :], start=entete_i + 2):
        if not brute.strip():
            continue
        vals = brute.split(sep)
        if len(vals) != len(champs):
            illisibles.append(
                (
                    n,
                    brute[:200],
                    "%d colonnes au lieu de %d" % (len(vals), len(champs)),
                )
            )
            continue
        try:
            d = val(vals, "EcritureDate")
            l = {
                "n": n,
                "journal_code": val(vals, "JournalCode"),
                "journal_lib": val(vals, "JournalLib"),
                "ecriture": val(vals, "EcritureNum"),
                "date": _date(d),
                "compte": val(vals, "CompteNum"),
                "compte_lib": val(vals, "CompteLib"),
                "tiers_ref": val(vals, "CompAuxNum"),
                "tiers_nom": val(vals, "CompAuxLib"),
                "piece": val(vals, "PieceRef"),
                "piece_date": _date(val(vals, "PieceDate")),
                "libelle": val(vals, "EcritureLib"),
                "debit": vers_centimes(val(vals, "Debit") or "0"),
                "credit": vers_centimes(val(vals, "Credit") or "0"),
                "lettrage": val(vals, "EcritureLet"),
                "date_lettrage": _date(val(vals, "DateLet")),
                "valid_date": _date(val(vals, "ValidDate")),
                "montant_devise": (
                    vers_centimes(val(vals, "Montantdevise"))
                    if val(vals, "Montantdevise")
                    else None
                ),
                "devise": val(vals, "Idevise"),
                "analytique": "",  # absent de la norme FEC
                "compte_cible": None,
            }
            if l["date"] is None:
                raise ValueError("EcritureDate vide")
            if l["debit"] < 0 or l["credit"] < 0:
                raise ValueError(
                    "montant négatif (le FEC porte des montants positifs)"
                )
        except (ValueError, ErreurMontant) as exc:
            illisibles.append((n, brute[:200], str(exc)))
            continue
        lignes.append(l)

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
    t = lot.totaux()
    j.dire(
        "%s lignes lues, %s écritures, débit %s / crédit %s"
        % (
            nombre_texte(t["lignes"]),
            nombre_texte(t["ecritures"]),
            _euros(t["debit"]),
            _euros(t["credit"]),
        ),
        "ok",
    )
    if illisibles:
        j.dire(
            "%d ligne(s) illisible(s) — elles bloquent la migration (détail dans les "
            "problèmes)" % len(illisibles),
            "erreur",
        )
    return lot


def _euros(c):
    from ..xlsx_ecrire import euros_texte

    return euros_texte(c, ",") + " €"
