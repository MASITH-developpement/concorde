#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Gère les connexions aux logiciels (ADR-0008) : lister, ajouter, tester.

  python3 -m scripts.concorde_connexion lister
  python3 -m scripts.concorde_connexion ajouter fec "FEC client A" \\
      --param chemin=/srv/depots/clientA/FEC.txt
  python3 -m scripts.concorde_connexion secret <id> jeton   # saisie masquée
  python3 -m scripts.concorde_connexion tester <id>
  python3 -m scripts.concorde_connexion retirer <id>

Un secret n'est jamais passé en argument ni affiché : il est saisi en
masqué et écrit dans le fichier de secrets (droits 600).
"""

import argparse
import getpass
import sys

from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import Annuaire, ErreurAnnuaire
from core.connecteurs.registre import REGISTRE
from core.connecteurs.secrets import (
    CHEMIN_SECRETS,
    ErreurSecrets,
    ecrire_variable,
    nom_variable,
)
from core.journal import Journal
from scripts.outils_cli import premiere_ligne


def _lire_parametres(paires: list[str]) -> dict[str, str]:
    """« nom=valeur » répétés -> dictionnaire. Lève ValueError."""
    parametres: dict[str, str] = {}
    for paire in paires:
        nom, egal, valeur = paire.partition("=")
        if not egal or not nom:
            raise ValueError("Paramètre attendu sous la forme nom=valeur.")
        parametres[nom] = valeur
    return parametres


def _executer(args: argparse.Namespace, annuaire_connexions: Annuaire) -> int:
    """Exécute la sous-commande demandée ; rend le code de sortie."""
    if args.commande == "lister":
        for fiche in annuaire_connexions.lister():
            print(
                "%s | %s | %s | test : %s | dernier essai : %s"
                % (
                    fiche["id"],
                    fiche["logiciel"],
                    fiche["libelle"],
                    fiche["connexion_test"] or "aucun",
                    fiche["dernier_test"] or "jamais",
                )
            )
        print("Logiciels branchés : %s" % ", ".join(sorted(REGISTRE)))
        return 0
    if args.commande == "ajouter":
        fiche = annuaire_connexions.ajouter(
            args.logiciel,
            args.libelle,
            _lire_parametres(args.param),
            args.test,
        )
        attendus = REGISTRE[args.logiciel].secrets_requis
        print("Connexion ajoutée : %s" % fiche["id"])
        for champ in attendus:
            print(
                "Secret à saisir : python3 -m scripts.concorde_connexion "
                "secret %s %s" % (fiche["id"], champ)
            )
        return 0
    if args.commande == "secret":
        fiche = annuaire_connexions.obtenir(args.ident)
        valeur = getpass.getpass("%s (%s) : " % (args.champ, fiche["libelle"]))
        if not valeur:
            print("Rien saisi : rien n'est écrit.", file=sys.stderr)
            return 1
        ecrire_variable(
            args.fichier, nom_variable(args.ident, args.champ), valeur
        )
        print("Secret enregistré dans %s." % args.fichier)
        return 0
    if args.commande == "tester":
        info = annuaire_connexions.tester(args.ident, Journal())
        print("Connexion %s : OK — %s" % (args.ident, info))
        return 0
    annuaire_connexions.retirer(args.ident)
    print("Connexion retirée : %s" % args.ident)
    return 0


def main() -> int:
    """Lit la ligne de commande et lance la sous-commande."""
    analyseur = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    analyseur.add_argument("--fichier", default=CHEMIN_SECRETS)
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("lister")
    ajouter = sous.add_parser("ajouter")
    ajouter.add_argument("logiciel", choices=sorted(REGISTRE))
    ajouter.add_argument("libelle")
    ajouter.add_argument("--param", action="append", default=[])
    ajouter.add_argument("--test", help="connexion d'environnement de test")
    secret = sous.add_parser("secret")
    secret.add_argument("ident")
    secret.add_argument("champ")
    for nom in ("tester", "retirer"):
        sous.add_parser(nom).add_argument("ident")
    args = analyseur.parse_args()
    try:
        return _executer(args, Annuaire(fichier_secrets=args.fichier))
    except (
        ErreurAnnuaire,
        ErreurConnexion,
        ErreurSecrets,
        ValueError,
        OSError,
    ) as exc:
        print("Refusé : %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
