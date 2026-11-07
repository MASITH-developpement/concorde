#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""CONCORDE ⇄ Odoo 17 — télécharger et analyser les données comptables.

Deux sources de lecture, mêmes résultats (ADR-0001) :
  --source sql      PostgreSQL direct, lecture seule — rapide (150 000 lignes ≈ 10 s).
                    Identifiants : PGHOST, PGPORT, PGUSER, PGPASSWORD (variables).
  --source xmlrpc   API Odoo — marche partout (Odoo Online compris).
                    Clé API : variable ODOO_API_KEY (jamais en argument).

Exemples (depuis la racine du dépôt) :
  python3 -m scripts.concorde_odoo --source sql --base testalbhade \\
      telecharger --format fec xlsx csv --du 2025-01-01 --au 2025-12-31 -o sorties/
  python3 -m scripts.concorde_odoo --source xmlrpc --url https://client.odoo.com \\
      --base client --user compta@client.fr analyser --json analyse.json

Codes retour : 0 = conforme / fait, 1 = erreur, 2 = anomalies relevées.
"""

import argparse
import json
import os
import sys
from datetime import date

from core.analyser import rendu_texte
from core.guardian import Guardian
from core.odoo_source import ErreurSource, SourceSqlOdoo17, SourceXmlRpcOdoo17
from core.passerelle import FORMATS, OBJETS, analyser_source, telecharger
from core.telecharger import ErreurFec


def _date(texte):
    return date.fromisoformat(texte)


def ouvrir_source(args):
    if args.source == "sql":
        return SourceSqlOdoo17(args.base, societe=args.societe)
    cle = os.environ.get("ODOO_API_KEY")
    if not cle:
        raise ErreurSource(
            "Clé API manquante : définissez la variable ODOO_API_KEY."
        )
    if not (args.url and args.user):
        raise ErreurSource("--url et --user sont requis avec --source xmlrpc.")
    if not args.url.startswith(
        ("https://", "http://localhost", "http://127.0.0.1")
    ):
        print(
            "ATTENTION : connexion non chiffrée (http) — la clé API circule en clair.",
            file=sys.stderr,
        )
    return SourceXmlRpcOdoo17(
        args.url, args.base, args.user, cle, societe=args.societe
    )


def cmd_telecharger(args, source, guardian):
    produits = telecharger(
        source,
        args.sortie,
        formats=args.format,
        objets=args.objets,
        du=args.du,
        au=args.au,
        brouillons=args.brouillons,
        separateur=args.separateur,
        encodage=args.encodage,
        guardian=guardian,
    )
    for p in produits:
        print(
            "%-5s %s — %s"
            % (
                p["format"].upper(),
                (
                    os.path.commonpath(p["fichiers"])
                    if len(p["fichiers"]) > 1
                    else p["fichiers"][0]
                ),
                p["resume"],
            )
        )
        for a in p["alertes"]:
            print("      ATTENTION : %s" % a)
    return 0


def cmd_analyser(args, source, guardian):
    d = analyser_source(source, args.du, args.au, args.validees, guardian)
    print(rendu_texte(d))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2, default=str)
        print("\nRapport complet (JSON) : %s" % args.json)
    return 0 if d["statut"] == "conforme" else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="CONCORDE ⇄ Odoo 17")
    ap.add_argument("--source", choices=("sql", "xmlrpc"), required=True)
    ap.add_argument("--base", required=True, help="Nom de la base Odoo")
    ap.add_argument("--url", help="URL Odoo (xmlrpc)")
    ap.add_argument("--user", help="Login Odoo (xmlrpc)")
    ap.add_argument(
        "--societe", type=int, help="id de la société (bases multi-sociétés)"
    )
    sous = ap.add_subparsers(dest="commande", required=True)

    t = sous.add_parser("telecharger", help="FEC, xlsx, CSV d'import Odoo")
    t.add_argument("--format", nargs="+", choices=FORMATS, default=["xlsx"])
    t.add_argument("--objets", nargs="+", choices=OBJETS, default=list(OBJETS))
    t.add_argument("--du", type=_date, help="Date de début AAAA-MM-JJ")
    t.add_argument(
        "--au", type=_date, help="Date de fin AAAA-MM-JJ (clôture du FEC)"
    )
    t.add_argument(
        "--brouillons",
        action="store_true",
        help="Inclure les brouillons (xlsx / csv seulement)",
    )
    t.add_argument("--separateur", choices=("|", "\t"), default="|")
    t.add_argument(
        "--encodage",
        default="iso-8859-15",
        help="Encodage du FEC (défaut iso-8859-15 ; utf-8 possible)",
    )
    t.add_argument(
        "-o", "--sortie", default="sorties", help="Dossier de sortie"
    )

    a = sous.add_parser("analyser", help="Contrôles comptables et tiers")
    a.add_argument("--du", type=_date)
    a.add_argument("--au", type=_date)
    a.add_argument(
        "--validees", action="store_true", help="Ignorer les brouillons"
    )
    a.add_argument("--json", metavar="FICHIER", help="Rapport complet en JSON")

    args = ap.parse_args(argv)
    guardian = Guardian()
    guardian.self_check()
    try:
        source = ouvrir_source(args)
    except Exception as exc:
        print("ERREUR de connexion : %s" % exc, file=sys.stderr)
        return 1
    try:
        print(
            "Connecté : base %s, Odoo %s, source %s\n"
            % (source.base, source.version_serveur, source.nature)
        )
        return {"telecharger": cmd_telecharger, "analyser": cmd_analyser}[
            args.commande
        ](args, source, guardian)
    except (ErreurFec, ErreurSource) as exc:
        print("REFUS : %s" % exc, file=sys.stderr)
        return 1
    finally:
        source.fermer()


if __name__ == "__main__":
    sys.exit(main())
