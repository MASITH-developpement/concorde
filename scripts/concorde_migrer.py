#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Migration ERP -> Odoo 17 (ADR-0004).

Sans option : portes 1 à 5, rien n'est écrit dans une base.
--tester : porte 6 en plus — envoi dans la base de TEST du serveur
           (CONCORDE_TEST_*), relecture et comparaison au centime.
           --reinitialiser-test la remet vierge avant.

  python3 -m scripts.concorde_migrer FICHIER.fec -o lots/client_2025 \\
      [--table table_comptes.xlsx | --comptes-identiques] \\
      [--filtres filtres.json] \\
      [--filtre '{"nom": "AN janvier", "journaux": ["AN"],
                  "du": "2025-01-01", "au": "2025-01-31"}']

Filtres (JSON, une liste) — voir core/migration/filtres.py. Exemples :
  [{"nom": "À-nouveaux 2025", "journaux": ["AN"],
    "du": "2025-01-01", "au": "2025-01-31"},
   {"nom": "Comptes 640", "comptes": ["640"]},
   {"nom": "Lignes nulles", "portee": "lignes_nulles"}]

Codes retour : 0 = lot prêt (ou testé avec --tester), 2 = lot bloqué,
1 = erreur.
"""

import argparse
import json
import os
import sys
from typing import Any

from core.journal import Evenement, Journal
from core.migration.circuit import PORTES, executer
from core.migration.correspondance import ErreurTable, charger_table

COULEURS = {
    "etape": "\033[1m",
    "ok": "\033[32m",
    "alerte": "\033[33m",
    "erreur": "\033[31m",
    "detail": "\033[2m",
    "info": "",
}


def afficher(ev: Evenement) -> None:
    """Affiche un événement du journal, en couleur sur un terminal."""
    c = COULEURS.get(ev["niveau"], "") if sys.stdout.isatty() else ""
    fin = "\033[0m" if c else ""
    print("%s  %s%s%s" % (ev["t"][11:19], c, ev["message"], fin), flush=True)


def main(argv: list[str] | None = None) -> int:
    """Prépare le lot de migration ; rend le code retour (0, 1 ou 2)."""
    ap = argparse.ArgumentParser(
        description="CONCORDE — migration ERP -> Odoo, portes 1 à 5"
    )
    ap.add_argument("fichier", help="FEC de l'ERP source")
    ap.add_argument("-o", "--dossier", required=True, help="Dossier du lot")
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--table", help="Table de correspondance des comptes (xlsx, json, csv)"
    )
    g.add_argument(
        "--comptes-identiques",
        action="store_true",
        help="Garder les numéros de comptes (choix explicite du comptable)",
    )
    ap.add_argument("--filtres", help="Fichier JSON : liste de filtres")
    ap.add_argument(
        "--filtre",
        action="append",
        default=[],
        help="Un filtre en JSON (répétable)",
    )
    ap.add_argument(
        "--tester",
        action="store_true",
        help="Porte 6 : envoyer dans la base de test du serveur et relire",
    )
    ap.add_argument(
        "--reinitialiser-test",
        action="store_true",
        help="Remettre la base de test vierge avant l'envoi (sans sauvegarde)",
    )
    args = ap.parse_args(argv)

    try:
        # Filtres JSON fournis par l'utilisateur : structure dynamique.
        regles: list[Any] = []
        if args.filtres:
            with open(args.filtres, encoding="utf-8") as f:
                regles += json.load(f)
        regles += [json.loads(x) for x in args.filtre]
        table = None
        if args.table:
            with open(args.table, "rb") as f:
                table = charger_table(f.read(), args.table)
        with open(args.fichier, "rb") as f:
            brut = f.read()
    except (OSError, ValueError, ErreurTable) as exc:
        print("ERREUR : %s" % exc, file=sys.stderr)
        return 1

    journal = Journal(ecouteur=afficher)
    if args.reinitialiser_test:
        from core import bases_locales

        base = os.environ.get("CONCORDE_TEST_BASE", "")
        modeles = bases_locales.lister_modeles()
        bases_locales.reinitialiser(
            base, base, [base], modeles, "", journal=journal
        )
    r = executer(
        brut,
        os.path.basename(args.fichier),
        args.dossier,
        regles,
        table,
        args.comptes_identiques,
        journal=journal,
        tester=args.tester,
    )
    print()
    for p in PORTES:
        print("  %-15s %s" % (p, r["portes"][p]["statut"].replace("_", " ")))
    print("\nDossier du lot : %s" % os.path.abspath(args.dossier))
    return 0 if r["statut"] in ("pret", "teste") else 2


if __name__ == "__main__":
    sys.exit(main())
