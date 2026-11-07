#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Définit le mot de passe de l'interface web CONCORDE.

Écrit l'empreinte scrypt (jamais le mot de passe) dans le fichier
d'environnement du service, puis il faut redémarrer le service :

  sudo python3 scripts/concorde_interface_mdp.py            # saisie masquée
  sudo systemctl restart concorde-interface

Option --generer : tire un mot de passe aléatoire et l'affiche UNE fois.
"""
import argparse
import getpass
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interface.auth import hacher  # noqa: E402

FICHIER = "/etc/concorde/interface.env"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fichier", default=FICHIER)
    ap.add_argument("--generer", action="store_true", help="Mot de passe aléatoire")
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
    lignes = []
    if os.path.exists(args.fichier):
        with open(args.fichier, encoding="utf-8") as f:
            lignes = [l for l in f if not l.startswith("CONCORDE_UI_MDP=")]
    lignes.append("CONCORDE_UI_MDP=%s\n" % hacher(mdp))
    os.makedirs(os.path.dirname(args.fichier), exist_ok=True)
    ancien = os.umask(0o077)
    try:
        with open(args.fichier, "w", encoding="utf-8") as f:
            f.writelines(lignes)
    finally:
        os.umask(ancien)
    os.chmod(args.fichier, 0o600)
    print("Empreinte enregistrée dans %s." % args.fichier)
    if args.generer:
        print("Mot de passe (affiché une seule fois) : %s" % mdp)
    print("Redémarrez : sudo systemctl restart concorde-interface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
