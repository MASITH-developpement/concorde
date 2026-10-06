#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Export des écritures CONCORDE au format d'import standard d'Odoo Online.

Conçu pour Odoo 20 Online (SaaS), où aucun module ne peut être installé :
le pipeline CONCORDE (stdlib pur, tolérance 0, montants en centimes int,
jamais de LLM) tourne HORS d'Odoo et produit deux fichiers CSV que
l'assistant d'import natif d'Odoo ingère :

  1. comptes_odoo20.csv   — comptes à créer (importés d'abord)
  2. ecritures_odoo20.csv — écritures (importées ensuite)

Règles CONCORDE respectées : aucun compte ni intitulé deviné (intitulé lu
dans la colonne CompteLib, type par classe de compte explicite), erreurs
bloquantes explicites (équilibre, mapping), jamais muet.

Usage (depuis la racine du dépôt) :
  python3 scripts/export_odoo_online.py ECRITURES.fec|ECRITURES.xlsx \
      [-m mapping.xlsx] [-o dossier_sortie]
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fec_parser import parse_fec                     # noqa: E402
from core.mapping import (                                # noqa: E402
    ErreurMapping, charger_mapping, charger_mapping_xlsx)
from core.moteur import verifier_equilibre                # noqa: E402
from core.xlsx_vers_fec import xlsx_vers_fec              # noqa: E402

# Type de compte Odoo par classe du plan comptable français — règles
# explicites, jamais devinées en silence (tracées dans la sortie).
TYPES_PAR_CLASSE = {
    "1": "equity",
    "2": "asset_current",
    "3": "asset_current",
    "4": "liability_current",   # affiné ci-dessous : 40x/41x
    "03": "asset_receivable",   # comptes de tiers Quadra (030/035 clients)
    "5": "asset_cash",
    "6": "expense",
    "7": "income",
    "8": "off_balance",
    "9": "off_balance",
}
TYPE_FINAL_DEFAUT = "equity_unaffected"


def type_odoo(code):
    """Type de compte Odoo explicite déduit de la classe (1-9)."""
    c = (code or "").strip()
    if c.startswith("03"):
        return "asset_receivable"
    if c.startswith("40"):
        return "liability_payable"
    if c.startswith(("41", "416", "419")):
        return "asset_receivable"
    return TYPES_PAR_CLASSE.get(c[:1], TYPE_FINAL_DEFAUT)


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
        description="Export CONCORDE vers fichiers d'import Odoo Online")
    ap.add_argument("fichier", help="FEC (.fec/.txt) ou export (.xlsx)")
    ap.add_argument("-m", "--mapping", default=None,
                    help="Fichier de mapping (xlsx) ; sinon JSON embarqué")
    ap.add_argument("-o", "--sortie", default="export_odoo20",
                    help="Dossier de sortie (défaut : export_odoo20)")
    args = ap.parse_args()

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

    # Grouper par écriture : (journal, numéro, date)
    ecritures = {}
    for l in canon.lignes:
        ecritures.setdefault(
            (l.journal_code, l.ecriture_num, l.date_ecriture), []).append(l)

    os.makedirs(args.sortie, exist_ok=True)

    # ---- 1) comptes : TOUS les comptes utilisés, avec intitulé + type ----
    comptes = sorted({l.compte for l in canon.lignes})
    p_comptes = os.path.join(args.sortie, "comptes_odoo20.csv")
    with open(p_comptes, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Code", "Name", "Type"])
        for c in comptes:
            w.writerow([c, libelles.get(c) or c, type_odoo(c)])

    # ---- 2) écritures : une ligne CSV par ligne d'écriture, la 1re ligne
    # de chaque écriture porte les colonnes parent, les suivantes portent
    # uniquement les lignes d'écriture (format one2many Odoo). ----
    p_ecr = os.path.join(args.sortie, "ecritures_odoo20.csv")
    with open(p_ecr, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Journal", "Date", "Reference", "Journal Entry",
                    "Journal Items/Account Number", "Journal Items/Label",
                    "Journal Items/Debit", "Journal Items/Credit"])
        nb = 0
        for (jcode, enum, date), lignes in ecritures.items():
            ref = "FEC %s-%s" % (jcode, enum)
            premiere = True
            for l in lignes:
                if l.debit == 0 and l.credit == 0:
                    continue
                if premiere:
                    w.writerow([jcode, date.strftime("%d/%m/%Y"), ref,
                                (l.libelle or "CONCORDE")[:200],
                                l.compte, (l.libelle or "CONCORDE")[:200],
                                "%.2f" % (l.debit / 100.0),
                                "%.2f" % (l.credit / 100.0)])
                    premiere = False
                else:
                    w.writerow(["", "", "", "",
                                l.compte, (l.libelle or "CONCORDE")[:200],
                                "%.2f" % (l.debit / 100.0),
                                "%.2f" % (l.credit / 100.0)])
                nb += 1

    print("Export Odoo 20 Online : OK")
    print("  Écritures : %d pièces, %d lignes" % (len(ecritures), nb))
    print("  Comptes   : %d (tous exportés — retirez ceux qui existent "
          "déjà avant d'importer)" % len(comptes))
    if auto:
        print("  Correspondances identité ajoutées (absents du mapping) : "
              "%d : %s" % (len(auto), ", ".join(auto[:30])))
    print("  Fichiers  : %s" % p_comptes)
    print("             %s" % p_ecr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
