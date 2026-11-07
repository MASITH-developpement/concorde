# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 5 — export et conformité.

Produit, à partir du lot filtré et traduit :
  - un FEC de contrôle (comptes Odoo), au format DGFiP ;
  - le CSV d'import Odoo (écritures), pour mémoire et contrôle croisé ;
  - le fichier des lignes retirées par les filtres (rien ne disparaît sans trace).
Puis RELIT le FEC produit avec le connecteur FEC et compare au lot :
nombre de lignes et d'écritures, totaux, équilibre de chaque écriture,
solde de chaque compte Odoo, nombre de lignes par tiers. Un centime d'écart = BLOQUANT.
"""
import os

from ..analyser import Rapport
from ..journal import nombre_texte, ou_muet
from ..telecharger import csv_ecritures, generer_fec
from ..xlsx_ecrire import Centimes, ecrire_xlsx, euros_texte
from .connecteur_fec import lire_fec
from .lot import cle_ecriture


def _vers_format_sortie(lot):
    """Lignes du lot -> format attendu par core/telecharger (FEC et CSV)."""
    ids = {}
    for l in lot.lignes:
        eid = ids.setdefault(cle_ecriture(l), len(ids) + 1)
        yield {
            "etat": "posted", "ecriture_id": eid, "ecriture": l["ecriture"],
            "journal_code": l["journal_code"], "journal_lib": l["journal_lib"],
            "date": l["date"], "piece_date": l["piece_date"], "reference": l["piece"],
            "compte": l["compte_cible"] or l["compte"], "compte_lib": l["compte_lib"],
            # le compte auxiliaire suit le tiers, quel que soit le compte cible
            "compte_type": "asset_receivable" if l["tiers_ref"] else "",
            "tiers_id": l["tiers_ref"] or None, "tiers_ref": l["tiers_ref"],
            "tiers_nom": l["tiers_nom"], "libelle": l["libelle"],
            "debit": l["debit"], "credit": l["credit"], "lettrage": l["lettrage"],
            "date_lettrage": l["date_lettrage"], "montant_devise": l["montant_devise"],
            "devise": l["devise"],
        }


def exporter(lot, dossier, journal=None):
    """Écrit les fichiers et contrôle la conformité. Retourne (Rapport, fichiers)."""
    j = ou_muet(journal)
    os.makedirs(dossier, exist_ok=True)
    fichiers = {}
    fec = os.path.join(dossier, "controle_FEC_comptes_odoo.txt")
    with j.etape("Export du FEC de contrôle (comptes Odoo)") as e:
        r_fec = generer_fec(_vers_format_sortie(lot), fec, encodage="utf-8")
        e.conclure("%s lignes" % nombre_texte(r_fec["lignes"]))
    fichiers["fec"] = fec
    chemin_csv = os.path.join(dossier, "import_odoo_ecritures.csv")
    with open(chemin_csv, "w", encoding="utf-8", newline="") as f:
        f.write(csv_ecritures(list(_vers_format_sortie(lot))))
    fichiers["csv"] = chemin_csv
    if lot.retirees:
        chemin = os.path.join(dossier, "lignes_retirees.xlsx")
        ecrire_xlsx(chemin, [("Retirees", ("Filtre", "Ligne source", "Journal", "Écriture",
                                           "Date", "Compte", "Tiers", "Libellé", "Débit",
                                           "Crédit"),
                              ([motif, l["n"], l["journal_code"], l["ecriture"], l["date"],
                                l["compte"], l["tiers_ref"], l["libelle"],
                                Centimes(l["debit"]), Centimes(l["credit"])]
                               for l, motif in lot.retirees))])
        fichiers["retirees"] = chemin
        j.dire("%s ligne(s) retirée(s) gardées dans %s" % (
            nombre_texte(len(lot.retirees)), os.path.basename(chemin)), "detail")

    with j.etape("Conformité : relecture du FEC produit et comparaison au centime") as e:
        with open(fec, "rb") as f:
            relu = lire_fec(f.read(), os.path.basename(fec))
        r = comparer(lot, relu)
        e.conclure("conforme" if not r.constats else "%d écart(s)" % len(r.constats))
    for c in r.constats:
        j.dire("%s : %s" % (c["message"], nombre_texte(c["nombre"])), "erreur")
    return r, fichiers


def comparer(lot, relu):
    """Compare le lot (comptes cibles) au FEC relu. Rapport des écarts (BLOQUANT)."""
    r = Rapport()
    a, b = lot.totaux(), relu.totaux()
    r.info("entree", a)
    r.info("sortie", b)
    for k, nom in (("lignes", "lignes"), ("ecritures", "écritures"), ("debit", "débit"),
                   ("credit", "crédit")):
        if a[k] != b[k]:
            r.constat("BLOQUANT", "MIG_ECART_SORTIE", "Écart entrée / sortie",
                      ["%s : entrée %s, sortie %s" % (nom, a[k], b[k])])
    r.constat("BLOQUANT", "MIG_ILLISIBLE_SORTIE", "Lignes illisibles dans le FEC produit",
              ["ligne %d : %s" % (n, m) for n, _, m in relu.illisibles])
    soldes_a = lot.balance_par_compte(cible=True)
    soldes_b = relu.balance_par_compte()
    r.constat("BLOQUANT", "MIG_ECART_COMPTE", "Soldes de comptes différents entrée / sortie",
              ["%s : entrée %s, sortie %s" % (k, euros_texte(soldes_a.get(k, 0), ","),
                                              euros_texte(soldes_b.get(k, 0), ","))
               for k in sorted(set(soldes_a) | set(soldes_b), key=str)
               if soldes_a.get(k, 0) != soldes_b.get(k, 0)])
    desequ = [k for k, ls in relu.ecritures().items()
              if sum(l["debit"] - l["credit"] for l in ls)]
    r.constat("BLOQUANT", "MIG_ECRITURE_DESEQUILIBREE", "Écritures déséquilibrées en sortie",
              ["%s/%s" % k for k in desequ])

    def par_tiers(lignes):
        d = {}
        for l in lignes:
            if l["tiers_ref"]:
                d[l["tiers_ref"]] = d.get(l["tiers_ref"], 0) + 1
        return d
    ta, tb = par_tiers(lot.lignes), par_tiers(relu.lignes)
    r.constat("BLOQUANT", "MIG_ECART_TIERS", "Lignes de tiers différentes entrée / sortie",
              ["%s : entrée %d, sortie %d" % (k, ta.get(k, 0), tb.get(k, 0))
               for k in sorted(set(ta) | set(tb)) if ta.get(k, 0) != tb.get(k, 0)])
    return r
