#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Montée de version Odoo (ADR-0010, ADR-0012), étape par étape.

  python3 -m scripts.concorde_montee creer <sauvegarde.zip> <version visée>
  python3 -m scripts.concorde_montee circuit <montée>     # étapes 1 à 4
  python3 -m scripts.concorde_montee feu-vert <montée> <nom de la base>
  python3 -m scripts.concorde_montee nouvel-essai <montée> <sauvegarde.zip>
  python3 -m scripts.concorde_montee livrer <montée>
  python3 -m scripts.concorde_montee etat <montée>
  python3 -m scripts.concorde_montee photo <base> <photo.json>
  python3 -m scripts.concorde_montee comparer <avant.json> <apres.json>

Les montées lancent Docker et donnent les pièces jointes au compte odoo
des conteneurs : à lancer en root (service de montée). `--racine` et
`--openupgrade` changent les dossiers de travail.
`photo` lit une base en lecture seule (identifiants : variables PG*).
`comparer` affiche chaque écart (ligne « ÉCART »).
Codes de sortie : 0 = rien à signaler, 1 = écarts ou montée bloquée,
2 = refus ou erreur.
"""

import argparse
import sys

from core.canonical import ErreurMontant
from core.fichier_json import ecrire_json_atomique
from core.montee_version import montee
from core.montee_version.commandes import ErreurCommande
from core.montee_version.openupgrade import ErreurOpenUpgrade
from core.montee_version.photo import (
    ErreurPhoto,
    charger_photo,
    comparer_photos,
    prendre_photo,
)
from core.journal import Journal
from core.montee_version.sauvegarde import ErreurSauvegarde
from core.odoo_source import ErreurSource, connexion_lecture_seule
from scripts.outils_cli import afficher_evenement, premiere_ligne


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


def _afficher_etat(etat: montee.EtatMontee) -> int:
    """Affiche l'état d'une montée ; 1 si elle est bloquée."""
    print(
        "Montée %s : %s (Odoo %d -> %d), statut %s"
        % (
            etat["id"],
            etat["base_client"],
            etat["depart"],
            etat["arrivee"],
            etat["statut"],
        )
    )
    for nom, etape in etat["etapes"].items():
        print(
            "  %-13s %-17s %s"
            % (nom, etape.get("statut", ""), etape.get("erreur", ""))
        )
    return 1 if etat["statut"] == montee.BLOQUEE else 0


def _montee(args: argparse.Namespace) -> int:
    """Sous-commandes de conduite d'une montée."""
    journal = Journal(ecouteur=afficher_evenement)
    if args.commande == "creer":
        etat = montee.creer(
            args.racine, args.sauvegarde, args.arrivee, journal
        )
        print(etat["id"])
        return 0
    if args.commande == "nouvel-essai":
        montee.nouvel_essai(
            args.racine,
            args.ident,
            args.sauvegarde,
            args.openupgrade,
            journal=journal,
        )
        return _afficher_etat(montee.charger(args.racine, args.ident))
    conduite = montee.Montee(
        args.racine, args.ident, args.openupgrade, journal=journal
    )
    if args.commande == "circuit":
        conduite.circuit()
    elif args.commande == "feu-vert":
        conduite.donner_feu_vert(args.confirmation, "ligne de commande")
    elif args.commande == "livrer":
        print(conduite.livrer())
    return _afficher_etat(montee.charger(args.racine, args.ident))


def main() -> int:
    """Lit la ligne de commande et lance la sous-commande."""
    analyseur = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    analyseur.add_argument("--racine", default=montee.CHEMIN_MONTEES)
    analyseur.add_argument("--openupgrade", default=montee.CHEMIN_OPENUPGRADE)
    sous = analyseur.add_subparsers(dest="commande", required=True)
    creer = sous.add_parser("creer")
    creer.add_argument("sauvegarde")
    creer.add_argument("arrivee", type=int)
    for nom in ("circuit", "livrer", "etat"):
        sous.add_parser(nom).add_argument("ident")
    feu_vert = sous.add_parser("feu-vert")
    feu_vert.add_argument("ident")
    feu_vert.add_argument("confirmation")
    essai = sous.add_parser("nouvel-essai")
    essai.add_argument("ident")
    essai.add_argument("sauvegarde")
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
        if args.commande == "comparer":
            return _comparer(args.avant, args.apres)
        if args.commande == "etat":
            return _afficher_etat(montee.charger(args.racine, args.ident))
        return _montee(args)
    except (
        montee.ErreurMontee,
        ErreurCommande,
        ErreurOpenUpgrade,
        ErreurSauvegarde,
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
