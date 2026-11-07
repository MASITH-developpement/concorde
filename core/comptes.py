# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Travail par compte comptable : balance, grand livre, alertes par compte.

Règles d'alerte (plan comptable général français, sur le solde = débit - crédit) :

  BLOQUANT  balance déséquilibrée ; caisse (53x) créditrice
  ALERTE    banque (512x) créditrice ; client créditeur (par tiers) ;
            fournisseur débiteur (par tiers) ; compte d'attente 47x / 58x non soldé ;
            charge (6x) créditrice, produit (7x) débiteur — sauf 6x9 / 7x9 (rabais)
            et 603 / 713 (variations de stocks), dont le sens est libre ;
            TVA déductible (4456x) créditrice ; TVA collectée (4457x) débitrice ;
            compte déprécié avec un solde.

Lecture seule. Montants en centimes.
"""
from .analyser import Rapport
from .journal import nombre_texte, ou_muet
from .xlsx_ecrire import euros_texte


def solde_texte(c):
    """Solde lisible : '1 234,56 D' / '12,00 C' / '0,00'."""
    s = c["debit"] - c["credit"]
    if not s:
        return "0,00"
    return "%s %s" % (euros_texte(abs(s), ","), "D" if s > 0 else "C")


def _sens_libre(code):
    """Comptes de gestion dont le solde peut normalement être dans les deux sens :
    6x9 / 7x9 (rabais, remises, ristournes), 603 (variation des stocks achetés),
    713 (variation de la production stockée)."""
    return (len(code) >= 3 and code[2] == "9") or code.startswith(("603", "713"))


REGLES = (
    # (code alerte, niveau, condition(compte, solde), message)
    ("CAISSE_CREDITRICE", "BLOQUANT",
     lambda c, s: c["code"].startswith("53") and s < 0, "Caisses créditrices"),
    ("BANQUE_CREDITRICE", "ALERTE",
     lambda c, s: c["code"].startswith("512") and s < 0, "Banques créditrices"),
    ("COMPTE_ATTENTE_NON_SOLDE", "ALERTE",
     lambda c, s: c["code"][:2] in ("47", "58") and s != 0, "Comptes d'attente non soldés"),
    ("CHARGE_CREDITRICE", "ALERTE",
     lambda c, s: c["code"].startswith("6") and not _sens_libre(c["code"]) and s < 0,
     "Comptes de charge créditeurs"),
    ("PRODUIT_DEBITEUR", "ALERTE",
     lambda c, s: c["code"].startswith("7") and not _sens_libre(c["code"]) and s > 0,
     "Comptes de produit débiteurs"),
    ("TVA_DEDUCTIBLE_CREDITRICE", "ALERTE",
     lambda c, s: c["code"].startswith("4456") and s < 0, "TVA déductible créditrice"),
    ("TVA_COLLECTEE_DEBITRICE", "ALERTE",
     lambda c, s: c["code"].startswith("4457") and s > 0, "TVA collectée débitrice"),
    ("COMPTE_DEPRECIE_SOLDE", "ALERTE",
     lambda c, s: c["deprecie"] and s != 0, "Comptes dépréciés avec un solde"),
)


def alertes_balance(balance, balance_tiers=(), journal=None):
    """Applique les règles. Retourne (Rapport, {code compte: [codes d'alerte]})."""
    j = ou_muet(journal)
    r = Rapport()
    par_compte = {}
    debit = sum(c["debit"] for c in balance)
    credit = sum(c["credit"] for c in balance)
    r.info("comptes", len(balance))
    r.info("comptes_mouvementes", sum(1 for c in balance if c["lignes"]))
    r.info("total_debit", euros_texte(debit, ","))
    r.info("total_credit", euros_texte(credit, ","))
    if debit != credit:
        r.constat("BLOQUANT", "BALANCE_DESEQUILIBREE", "Balance déséquilibrée",
                  ["D %s / C %s" % (euros_texte(debit, ","), euros_texte(credit, ","))])
        j.dire("Balance déséquilibrée : D %s / C %s"
               % (euros_texte(debit, ","), euros_texte(credit, ",")), "alerte")
    else:
        j.dire("Balance équilibrée au centime : %s €" % euros_texte(debit, ","), "ok")

    for code_alerte, niveau, condition, message in REGLES:
        touches = [c for c in balance if condition(c, c["debit"] - c["credit"])]
        for c in touches:
            par_compte.setdefault(c["code"], []).append(code_alerte)
        r.constat(niveau, code_alerte, message,
                  ["%s %s : %s" % (c["code"], c["libelle"], solde_texte(c)) for c in touches])
        if touches:
            j.dire("%s : %s (%s)" % (message, len(touches), ", ".join(
                c["code"] for c in touches[:5]) + ("…" if len(touches) > 5 else "")),
                "alerte")

    # Par tiers : clients créditeurs, fournisseurs débiteurs.
    types = {c["code"]: c["type"] for c in balance}
    clients, fournisseurs = [], []
    for t in balance_tiers:
        s = t["debit"] - t["credit"]
        if not t["tiers_id"]:
            continue                       # signalé par l'analyse (TIERS_MANQUANT)
        lib = "%s — %s (%s) : %s" % (t["compte"], t["tiers_nom"] or "?",
                                     t["tiers_ref"] or "id %s" % t["tiers_id"],
                                     solde_texte(t))
        if types.get(t["compte"]) == "asset_receivable" and s < 0:
            clients.append((s, lib, t["compte"]))
        elif types.get(t["compte"]) == "liability_payable" and s > 0:
            fournisseurs.append((-s, lib, t["compte"]))
    for code_alerte, message, liste in (("CLIENT_CREDITEUR", "Clients créditeurs", clients),
                                        ("FOURNISSEUR_DEBITEUR", "Fournisseurs débiteurs",
                                         fournisseurs)):
        liste.sort()                       # les plus gros soldes anormaux d'abord
        for _, _, compte in liste:
            if code_alerte not in par_compte.setdefault(compte, []):
                par_compte[compte].append(code_alerte)
        r.constat("ALERTE", code_alerte, message, [lib for _, lib, _ in liste])
        if liste:
            j.dire("%s : %s tiers" % (message, nombre_texte(len(liste))), "alerte")
    return r, par_compte


def grand_livre(lignes, offset=0, limite=500):
    """Lignes d'un compte avec solde cumulé. Retourne (page, totaux).

    `lignes` est trié par date (ordre des sources) ; le cumul est calculé sur
    tout le compte, puis la page demandée est découpée.
    """
    cumul = 0
    toutes = []
    debit = credit = 0
    for l in lignes:
        cumul += l["debit"] - l["credit"]
        debit += l["debit"]
        credit += l["credit"]
        toutes.append(dict(l, cumul=cumul))
    totaux = {"lignes": len(toutes), "debit": debit, "credit": credit,
              "solde": debit - credit}
    return toutes[offset:offset + limite], totaux
