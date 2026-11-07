#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Vérifier, analyser et comparer deux bases Odoo 17 — lecture seule.

  python3 -m scripts.concorde_comparer --a testalbhade --b testalbhade_cmp \\
      --du 2025-11-01 --au 2025-11-30 [--brouillons] \\
      [--date-copie 2026-10-14T18:01:57] [-o dossier]

Bases du serveur en SQL (PGHOST, PGUSER, PGPASSWORD).
Codes retour : 0 = identiques, 2 = différences ou anomalies, 1 = erreur.
"""

import argparse
import sys
from datetime import date

from core.comparaison import comparer_bases
from core.journal import Evenement, Journal
from core.odoo_source import SourceSqlOdoo17
from scripts.outils_cli import premiere_ligne


def afficher(ev: Evenement) -> None:
    """Affiche un événement du journal : heure puis message."""
    print("%s  %s" % (ev["t"][11:19], ev["message"]), flush=True)


def main(argv: list[str] | None = None) -> int:
    """Compare les bases --a et --b ; rend le code retour (0, 1 ou 2)."""
    ap = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    ap.add_argument("--a", required=True, help="Base A (référence)")
    ap.add_argument("--b", required=True, help="Base B (comparée)")
    ap.add_argument("--du", type=date.fromisoformat)
    ap.add_argument("--au", type=date.fromisoformat)
    ap.add_argument(
        "--brouillons", action="store_true", help="Inclure les brouillons"
    )
    ap.add_argument(
        "--date-copie", help="B est une copie de A faite à cette date (UTC)"
    )
    ap.add_argument("-o", "--dossier", default="comparaisons")
    args = ap.parse_args(argv)
    j = Journal(ecouteur=afficher)
    try:
        a, b = SourceSqlOdoo17(args.a), SourceSqlOdoo17(args.b)
    except Exception as exc:
        print("ERREUR : %s" % exc, file=sys.stderr)
        return 1
    etats = ("posted", "draft") if args.brouillons else ("posted",)
    r = comparer_bases(
        a, b, args.du, args.au, etats, args.date_copie, args.dossier, j
    )
    print()
    for c in r["comparaison"]["constats"]:
        print("[%s] %s — %d" % (c["niveau"], c["message"], c["nombre"]))
        for e in c["exemples"][:5]:
            print("    · %s" % e)
    return 0 if r["comparaison"]["statut"] == "conforme" else 2


if __name__ == "__main__":
    sys.exit(main())
