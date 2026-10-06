#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Export des écritures CONCORDE au format d'import standard d'Odoo.

Chaque version d'Odoo reçoit SON export : comptes + écritures au format
d'import natif de la version cible (17, 18, 19 ou 20), types de comptes
validés explicitement contre la liste de la version. Le pipeline CONCORDE
(stdlib pur, tolérance 0, montants en centimes int, jamais de LLM) tourne
hors d'Odoo.

Usage (depuis la racine du dépôt) :
  python3 scripts/export_odoo_online.py ECRITURES.fec|ECRITURES.xlsx \
      [-m mapping.xlsx] [-v 17|18|19|20] [-o dossier_sortie]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.export_odoo import (                                # noqa: E402
    TYPES_PAR_VERSION, generer_csv_comptes, generer_csv_ecritures)
from core.fec_parser import parse_fec                        # noqa: E402
from core.mapping import charger_mapping, charger_mapping_xlsx  # noqa: E402
from core.moteur import verifier_equilibre                   # noqa: E402
from core.xlsx_vers_fec import xlsx_vers_fec                 # noqa: E402


def lire_compte_libs(brut_fec, mapping):
    """Intitulés des comptes lus dans le FEC (colonne CompteLib),
    indexés par le compte Odoo CIBLE du mapping."""
    texte = brut_fec.decode("utf-8")
    idx_num, idx_lib = 4, 5
    for ligne in texte.splitlines():
        champs = [c.strip().lower() for c in ligne.split("\t")]
        if "comptenum" in champs:
            idx_num = champs.index("comptenum")
            if "comptelib" in champs:
                idx_lib = champs.index("comptelib")
            break
    libelles = {}
    for ligne in texte.splitlines():
        parties = ligne.split("\t")
        if len(parties) <= idx_num:
            continue
        compte = parties[idx_num].strip()
        if not compte or compte.lower() == "comptenum":
            continue
        if len(parties) > idx_lib:
            lib = parties[idx_lib].strip()
            if lib and lib.lower() != "comptelib":
                libelles.setdefault(mapping.get(compte) or compte, lib)
    return libelles


def main():
    ap = argparse.ArgumentParser(
        description="Export CONCORDE vers fichiers d'import Odoo "
                    "(17, 18, 19 ou 20)")
    ap.add_argument("fichier", help="FEC (.fec/.txt) ou export (.xlsx)")
    ap.add_argument("-m", "--mapping", default=None,
                    help="Fichier de mapping (xlsx) ; sinon JSON embarqué")
    ap.add_argument("-v", "--version", default="17",
                    choices=sorted(TYPES_PAR_VERSION),
                    help="Version d'Odoo cible (défaut : 17)")
    ap.add_argument("-o", "--sortie", default=None,
                    help="Dossier de sortie (défaut : export_odoo%s)")
    args = ap.parse_args()

    sortie = args.sortie or ("export_odoo%s" % args.version)
    brut = open(args.fichier, "rb").read()
    if args.fichier.lower().endswith((".xlsx", ".xls")):
        brut = xlsx_vers_fec(brut, nom_fichier=args.fichier)

    canon = parse_fec(brut)
    equi = verifier_equilibre(canon)
    if not equi["equilibre"]:
        print("ERREUR : écritures non équilibrées (tolérance 0) — "
              "débit %d / crédit %d (centimes), aucun export effectué."
              % (equi["total_debit"], equi["total_credit"]))
        return 2

    if args.mapping:
        mapping = charger_mapping_xlsx(
            open(args.mapping, "rb").read(),
            nom_fichier=os.path.basename(args.mapping))
    else:
        mapping = charger_mapping(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "mapping_quadra_odoo.json"))

    # Correspondance identité pour les comptes absents du mapping (décision
    # client explicite) : compte Odoo de même code, créé depuis l'export.
    auto = []
    for l in canon.lignes:
        if l.compte not in mapping:
            mapping[l.compte] = l.compte
            auto.append(l.compte)

    # Intitulés lus dans le FEC, indexés par le compte cible.
    libelles = lire_compte_libs(brut, mapping)

    # Application du mapping sur toutes les lignes.
    for l in canon.lignes:
        l.compte = mapping[l.compte]

    os.makedirs(sortie, exist_ok=True)
    p_comptes = os.path.join(sortie, "comptes_odoo%s.csv" % args.version)
    p_ecr = os.path.join(sortie, "ecritures_odoo%s.csv" % args.version)
    with open(p_comptes, "w", encoding="utf-8") as f:
        f.write(generer_csv_comptes(canon.lignes, libelles, args.version))
    with open(p_ecr, "w", encoding="utf-8") as f:
        f.write(generer_csv_ecritures(canon.lignes, args.version))

    nb_ecritures = len({(l.journal_code, l.ecriture_num, l.date_ecriture)
                        for l in canon.lignes})
    nb_lignes = sum(1 for l in canon.lignes if l.debit or l.credit)
    print("Export Odoo %s : OK" % args.version)
    print("  Écritures : %d pièces, %d lignes" % (nb_ecritures, nb_lignes))
    print("  Comptes   : %d (tous exportés — retirez ceux qui existent "
          "déjà avant d'importer)"
          % len({l.compte for l in canon.lignes}))
    if auto:
        print("  Correspondances identité ajoutées (absents du mapping) : "
              "%d : %s" % (len(auto), ", ".join(auto[:30])))
    print("  Fichiers  : %s" % p_comptes)
    print("             %s" % p_ecr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
