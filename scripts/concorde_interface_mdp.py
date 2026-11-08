#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Définit le mot de passe de l'interface web CONCORDE.

Écrit l'empreinte scrypt (jamais le mot de passe) dans le fichier
d'environnement du service, puis il faut redémarrer le service :

  sudo python3 -m scripts.concorde_interface_mdp            # saisie masquée
  sudo systemctl restart concorde-interface

Option --generer : tire un mot de passe aléatoire et l'affiche UNE fois.
"""

import argparse
import getpass
import secrets
import sys

from core.connecteurs.secrets import ecrire_variable
from interface.auth import hacher
from scripts.outils_cli import premiere_ligne

FICHIER = "/etc/concorde/interface.env"


def main() -> int:
    """Demande (ou tire) le mot de passe et écrit son empreinte."""
    ap = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    ap.add_argument("--fichier", default=FICHIER)
    ap.add_argument(
        "--generer", action="store_true", help="Mot de passe aléatoire"
    )
    args = ap.parse_args()
    if args.generer:
        mdp = secrets.token_urlsafe(15)
    else:
        mdp = getpass.getpass("Nouveau mot de passe : ")
        if len(mdp) < 12:
            print("Refusé : 12 caractères au minimum.", file=sys.stderr)
            return 1
        if getpass.getpass("Confirmez : ") != mdp:
            print("Les deux saisies diffèrent.", file=sys.stderr)
            return 1
    ecrire_variable(args.fichier, "CONCORDE_UI_MDP", hacher(mdp))
    print("Empreinte enregistrée dans %s." % args.fichier)
    if args.generer:
        print("Mot de passe (affiché une seule fois) : %s" % mdp)
    print("Redémarrez : sudo systemctl restart concorde-interface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
