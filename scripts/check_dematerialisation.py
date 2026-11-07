#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Contrôle de la dématérialisation des factures d'un Odoo distant.

Accès par XML-RPC avec une clé API.

LECTURE SEULE : seules search_read et fields_get sont appelées (verrou dans
le client). Le moteur est core/demat.py, le même que celui du menu
CONCORDE > Contrôle dématérialisation dans Odoo.

Utilisation (depuis la racine du dépôt) :
  export ODOO_API_KEY="votre-cle-api"   # jamais en argument de commande
  python3 -m scripts.check_dematerialisation \\
      --url https://mon-odoo.example.com --db mabase \\
      --user contact@masith.fr --days 30 [--json rapport.json] [--sans-pdf]

Codes retour : 0 = conforme, 1 = connexion / erreur,
2 = anomalies (bloquantes ou alertes).
"""

import argparse
import os
import sys

from core.demat import (
    MAX_FACTURES_DEFAUT,
    MAX_PDF_INSPECTES_DEFAUT,
    ControleDemat,
    SourceXmlRpc,
    rendu_texte,
)
from scripts.outils_cli import avertir_si_non_chiffre, ecrire_rapport_json


def main(argv: list[str] | None = None) -> int:
    """Lance le contrôle ; rend le code retour (0, 1 ou 2)."""
    ap = argparse.ArgumentParser(
        description="CONCORDE — contrôle de la dématérialisation des "
        "factures Odoo"
    )
    ap.add_argument(
        "--url", required=True, help="URL Odoo, ex. https://mon-odoo.fr"
    )
    ap.add_argument("--db", required=True, help="Nom de la base")
    ap.add_argument("--user", required=True, help="Login Odoo")
    ap.add_argument(
        "--days",
        type=int,
        default=30,
        help="Fenêtre d'analyse en jours (défaut : 30)",
    )
    ap.add_argument(
        "--max-factures",
        type=int,
        default=MAX_FACTURES_DEFAUT,
        help="Plafond de factures lues par sens (défaut : %(default)s)",
    )
    ap.add_argument(
        "--max-pdf",
        type=int,
        default=MAX_PDF_INSPECTES_DEFAUT,
        help="Plafond de PDF inspectés pour le Factur-X embarqué "
        "(défaut : %(default)s)",
    )
    ap.add_argument(
        "--sans-pdf",
        action="store_true",
        help="Ne pas télécharger les PDF (plus rapide, taux XML sous-estimé)",
    )
    ap.add_argument(
        "--json",
        metavar="FICHIER",
        help="Écrit aussi le rapport complet en JSON",
    )
    ap.add_argument(
        "--timeout", type=int, default=60, help="Timeout réseau (s)"
    )
    args = ap.parse_args(argv)

    cle = os.environ.get("ODOO_API_KEY")
    if not cle:
        print(
            "ERREUR : clé API manquante — définissez la variable "
            "ODOO_API_KEY.",
            file=sys.stderr,
        )
        return 1
    if args.days < 1:
        print("ERREUR : --days doit valoir au moins 1.", file=sys.stderr)
        return 1
    avertir_si_non_chiffre(args.url)

    try:
        source = SourceXmlRpc(
            args.url, args.db, args.user, cle, timeout=args.timeout
        )
    except Exception as exc:  # réseau, SSL, authentification
        print("ERREUR de connexion : %s" % exc, file=sys.stderr)
        return 1

    print(
        "Connecté à %s (base %s, Odoo %s)\n"
        % (args.url, args.db, source.version_serveur)
    )
    try:
        rapport = (
            ControleDemat(
                source,
                jours=args.days,
                max_factures=args.max_factures,
                inspecter_pdf=not args.sans_pdf,
                max_pdf=args.max_pdf,
            )
            .executer()
            .en_dict()
        )
    except Exception as exc:
        print(
            "ERREUR pendant l'analyse : %s: %s" % (type(exc).__name__, exc),
            file=sys.stderr,
        )
        return 1

    print(rendu_texte(rapport))
    if args.json:
        ecrire_rapport_json(args.json, rapport)
        print("\nRapport JSON : %s" % args.json)
    return 0 if rapport["statut"] == "conforme" else 2


if __name__ == "__main__":
    sys.exit(main())
