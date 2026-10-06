# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Génération des fichiers d'import standard Odoo (comptes + écritures).

Chaque version d'Odoo reçoit un export dans SON format : les types de
comptes sont validés explicitement contre la liste de valeurs de la
version cible (règle CONCORDE : jamais muet, jamais deviné en silence).

Valeurs account_type par version (documentation officielle Odoo) :
- 17/18 : asset_receivable, asset_cash, asset_current, asset_non_current,
  asset_prepayments, asset_fixed, liability_payable, liability_credit_card,
  liability_current, liability_non_current, equity, equity_unaffected,
  income, income_other, expense, expense_depreciation,
  expense_direct_cost, off_balance
- 19/20 : identique + expense_other
"""
import csv
import io

from .canonical import LigneEcriture  # noqa: F401  (typage documentation)

TYPES_PAR_VERSION = {
    "17": {
        "asset_receivable", "asset_cash", "asset_current",
        "asset_non_current", "asset_prepayments", "asset_fixed",
        "liability_payable", "liability_credit_card", "liability_current",
        "liability_non_current", "equity", "equity_unaffected", "income",
        "income_other", "expense", "expense_depreciation",
        "expense_direct_cost", "off_balance",
    },
    "18": {
        "asset_receivable", "asset_cash", "asset_current",
        "asset_non_current", "asset_prepayments", "asset_fixed",
        "liability_payable", "liability_credit_card", "liability_current",
        "liability_non_current", "equity", "equity_unaffected", "income",
        "income_other", "expense", "expense_depreciation",
        "expense_direct_cost", "off_balance",
    },
    "19": {
        "asset_receivable", "asset_cash", "asset_current",
        "asset_non_current", "asset_prepayments", "asset_fixed",
        "liability_payable", "liability_credit_card", "liability_current",
        "liability_non_current", "equity", "equity_unaffected", "income",
        "income_other", "expense", "expense_other", "expense_depreciation",
        "expense_direct_cost", "off_balance",
    },
    "20": {
        "asset_receivable", "asset_cash", "asset_current",
        "asset_non_current", "asset_prepayments", "asset_fixed",
        "liability_payable", "liability_credit_card", "liability_current",
        "liability_non_current", "equity", "equity_unaffected", "income",
        "income_other", "expense", "expense_other", "expense_depreciation",
        "expense_direct_cost", "off_balance",
    },
}

# Type de compte Odoo par classe du plan comptable français — règles
# explicites, identiques pour toutes les versions supportées.
TYPES_PAR_CLASSE = {
    "1": "equity",
    "2": "asset_current",
    "3": "asset_current",
    "4": "liability_current",   # affiné ci-dessous : 40x/41x/03x
    "03": "asset_receivable",   # comptes de tiers Quadra (030/035 clients)
    "5": "asset_cash",
    "6": "expense",
    "7": "income",
    "8": "off_balance",
    "9": "off_balance",
}
TYPE_COMPTE_DEFAUT = "equity_unaffected"


class ErreurExport(RuntimeError):
    """Erreur explicite de l'export (version inconnue, type invalide)."""


def type_compte(code):
    """Type de compte Odoo explicite déduit de la classe (1-9)."""
    c = (code or "").strip()
    if c.startswith("03"):
        return "asset_receivable"
    if c.startswith("40"):
        return "liability_payable"
    if c.startswith(("41", "416", "419")):
        return "asset_receivable"
    return TYPES_PAR_CLASSE.get(c[:1], TYPE_COMPTE_DEFAUT)


def _verifier_type(code, version):
    typ = type_compte(code)
    if typ not in TYPES_PAR_VERSION.get(version, set()):
        raise ErreurExport(
            "Version Odoo %s inconnue ou type %r non supporté par Odoo %s "
            "(compte %s) — CONCORDE ne devine jamais un type."
            % (version, typ, version, code))
    return typ


def generer_csv_comptes(lignes, libelles, version):
    """CSV des comptes au format d'import Odoo <version>.

    lignes : itérable de LigneEcriture (déjà mappées sur les comptes Odoo).
    libelles : {compte cible: intitulé} lus dans le FEC.
    Retourne une str CSV (UTF-8, BOM pour Excel).
    """
    if version not in TYPES_PAR_VERSION:
        raise ErreurExport(
            "Version Odoo %r non supportée (attendues : %s)."
            % (version, ", ".join(sorted(TYPES_PAR_VERSION))))
    comptes = sorted({l.compte for l in lignes})
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Code", "Name", "Type"])
    for c in comptes:
        w.writerow([c, libelles.get(c) or c, _verifier_type(c, version)])
    return "\ufeff" + buf.getvalue()


# Type de journal Odoo par code journal français — règles explicites.
# Valeurs account.journal.type : sale, purchase, bank, cash, general.
# Codes de banque (5x) -> bank, caisse 53 -> cash, achats 6x ->
# purchase, ventes 7x -> sale, tout le reste (OD, SAL, TVA, 41...) ->
# general. Règles PCG, documentées, identiques toutes versions.
JOURNAUX_PAR_DEFAUT = {
    "OD": ("Opérations diverses", "general"),
    "SAL": ("Paie", "general"),
    "TVA": ("Déclarations TVA", "general"),
    "CB": ("Carte bancaire", "bank"),
}


def type_journal(code):
    """(nom, type Odoo) d'un code journal — règles PCG explicites."""
    code = (code or "").strip().upper()
    if code in JOURNAUX_PAR_DEFAUT:
        return JOURNAUX_PAR_DEFAUT[code]
    if code.startswith("53"):
        return ("Caisse %s" % code, "cash")
    if code.startswith("5"):
        return ("Banque %s" % code, "bank")
    if code.startswith("6"):
        return ("Achats %s" % code, "purchase")
    if code.startswith("7"):
        return ("Ventes %s" % code, "sale")
    return ("Journal %s" % code, "general")


def generer_csv_journaux(lignes, version):
    """CSV des journaux au format d'import Odoo <version>.

    Un journal par code présent dans les lignes, avec le type Odoo
    déduit des règles PCG (type_journal). L'import des écritures
    échoue si les journaux n'existent pas : ce fichier rend l'export
    autosuffisant (journaux -> comptes -> écritures).
    """
    if version not in TYPES_PAR_VERSION:
        raise ErreurExport(
            "Version Odoo %r non supportée (attendues : %s)."
            % (version, ", ".join(sorted(TYPES_PAR_VERSION))))
    codes = sorted({l.journal_code for l in lignes if l.journal_code})
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Name", "Code", "Type"])
    for c in codes:
        nom, jtype = type_journal(c)
        w.writerow([nom, c, jtype])
    return "\ufeff" + buf.getvalue()


def generer_csv_ecritures(lignes, version):
    """CSV des écritures au format d'import Odoo <version> (one2many).

    lignes : itérable de LigneEcriture (déjà mappées). La première ligne
    de chaque écriture porte les colonnes parent (journal, date, ref),
    les suivantes uniquement les lignes d'écriture.
    """
    if version not in TYPES_PAR_VERSION:
        raise ErreurExport(
            "Version Odoo %r non supportée (attendues : %s)."
            % (version, ", ".join(sorted(TYPES_PAR_VERSION))))
    ecritures = {}
    for l in lignes:
        ecritures.setdefault(
            (l.journal_code, l.ecriture_num, l.date_ecriture), []).append(l)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Journal", "Date", "Reference", "Journal Entry",
                "Journal Items/Account Number", "Journal Items/Label",
                "Journal Items/Debit", "Journal Items/Credit"])
    for (jcode, enum, date), lignes_e in ecritures.items():
        ref = "FEC %s-%s" % (jcode, enum)
        premiere = True
        for l in lignes_e:
            if l.debit == 0 and l.credit == 0:
                continue
            parent = [jcode, date.strftime("%d/%m/%Y"), ref,
                      (l.libelle or "CONCORDE")[:200]] if premiere else [""] * 4
            w.writerow(parent + [
                l.compte, (l.libelle or "CONCORDE")[:200],
                "%.2f" % (l.debit / 100.0),
                "%.2f" % (l.credit / 100.0)])
            premiere = False
    return "\ufeff" + buf.getvalue()
