#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Montée de version Odoo (ADR-0010) : photo comptable et comparaison.

  python3 -m scripts.concorde_montee photo <base> <photo.json>
  python3 -m scripts.concorde_montee comparer <avant.json> <apres.json>

`photo` lit la base en lecture seule (identifiants : variables PG*).
`comparer` affiche chaque écart (ligne « ÉCART ») et sort en code 1 s'il
y en a un seul : la tolérance est zéro.
Codes de sortie : 0 = rien à signaler, 1 = écarts, 2 = refus ou erreur.
"""

import argparse
import sys

from core.canonical import ErreurMontant
from core.fichier_json import ecrire_json_atomique
from core.montee_version.photo import (
    ErreurPhoto,
    charger_photo,
    comparer_photos,
    prendre_photo,
)
from core.odoo_source import ErreurSource, connexion_lecture_seule
from scripts.outils_cli import premiere_ligne


def _photo(base: str, chemin: str) -> int:
    """Prend la photo de `base` et l'écrit dans `chemin`."""
    connexion = connexion_lecture_seule(base)
    try:
        photo = prendre_photo(connexion, base)
    finally:
        connexion.close()
    ecrire_json_atomique(chemin, photo, ascii_seul=False, retrait=1)
    print(
        "Photo de %s (Odoo %s) : %s, empreinte %s"
        % (
            base,
            photo["version"],
            ", ".join(
                "%s %d" % (section, len(valeurs))
                for section, valeurs in photo["sections"].items()
            ),
            photo["empreinte"][:12],
        )
    )
    return 0


def _comparer(chemin_avant: str, chemin_apres: str) -> int:
    """Compare deux photos ; 1 s'il y a un écart."""
    avant, apres = charger_photo(chemin_avant), charger_photo(chemin_apres)
    ecarts = comparer_photos(avant, apres)
    for ecart in ecarts:
        print(
            "ÉCART %s %s : avant=%r après=%r"
            % (ecart["section"], ecart["cle"], ecart["avant"], ecart["apres"])
        )
    print(
        "%s (Odoo %s) -> %s (Odoo %s) : %d écart(s)."
        % (
            avant["base"],
            avant["version"],
            apres["base"],
            apres["version"],
            len(ecarts),
        )
    )
    return 1 if ecarts else 0


def main() -> int:
    """Lit la ligne de commande et lance la sous-commande."""
    analyseur = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    sous = analyseur.add_subparsers(dest="commande", required=True)
    photo = sous.add_parser("photo")
    photo.add_argument("base")
    photo.add_argument("fichier")
    comparer = sous.add_parser("comparer")
    comparer.add_argument("avant")
    comparer.add_argument("apres")
    args = analyseur.parse_args()
    try:
        if args.commande == "photo":
            return _photo(args.base, args.fichier)
        return _comparer(args.avant, args.apres)
    except (
        ErreurPhoto,
        ErreurSource,
        ErreurMontant,
        ValueError,
        OSError,
    ) as exc:
        print("Refusé : %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
