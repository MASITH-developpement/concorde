# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Travail par compte comptable : balance, grand livre, alertes par compte.

Règles d'alerte (plan comptable général français, sur le solde
= débit - crédit) :

  BLOQUANT  balance déséquilibrée ; caisse (53x) créditrice
  ALERTE    banque (512x) créditrice ; client créditeur (par tiers) ;
            fournisseur débiteur (par tiers) ;
            compte d'attente 47x / 58x non soldé ;
            charge (6x) créditrice, produit (7x) débiteur — sauf 6x9 / 7x9
            (rabais) et 603 / 713 (variations de stocks), dont le sens est
            libre ;
            TVA déductible (4456x) créditrice ;
            TVA collectée (4457x) débitrice ;
            compte déprécié avec un solde.

Lecture seule. Montants en centimes.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .analyser import Rapport
from .journal import Journal, nombre_texte, ou_muet
from .xlsx_ecrire import euros_texte

# Compte, ligne ou solde par tiers : dictionnaire produit par la source
# (lignes SQL / XML-RPC Odoo, fichiers) dont les valeurs sont hétérogènes
# (texte, centimes, booléens, identifiants).
Enregistrement = Mapping[str, Any]

# (code alerte, niveau, condition(compte, solde), message)
Regle = tuple[str, str, Callable[[Enregistrement, int], bool], str]


def solde_texte(c: Enregistrement) -> str:
    """Rend le solde lisible d'un compte ou d'un tiers.

    Rôle : afficher débit - crédit avec son sens.
    Paramètres : c, enregistrement portant les clés 'debit' et 'credit'
    (centimes).
    Retour : '1234,56 D' (débiteur), '12,00 C' (créditeur) ou '0,00'.
    Erreurs : KeyError si 'debit' ou 'credit' manque.
    Usages : alertes_balance (comptes et tiers), comparaison.
    """
    s = c["debit"] - c["credit"]
    if not s:
        return "0,00"
    return "%s %s" % (euros_texte(abs(s), ","), "D" if s > 0 else "C")


def _sens_libre(code: str) -> bool:
    """Dit si un compte de gestion peut avoir un solde dans les deux sens.

    Rôle : exclure des alertes charge créditrice / produit débiteur les
    comptes 6x9 / 7x9 (rabais, remises, ristournes), 603 (variation des
    stocks achetés) et 713 (variation de la production stockée).
    Paramètres : code, numéro de compte.
    Retour : True si le sens du solde est libre.
    Erreurs : aucune.
    Usages : règles CHARGE_CREDITRICE et PRODUIT_DEBITEUR de REGLES.
    """
    return (len(code) >= 3 and code[2] == "9") or code.startswith(
        ("603", "713")
    )


REGLES: tuple[Regle, ...] = (
    (
        "CAISSE_CREDITRICE",
        "BLOQUANT",
        lambda c, s: c["code"].startswith("53") and s < 0,
        "Caisses créditrices",
    ),
    (
        "BANQUE_CREDITRICE",
        "ALERTE",
        lambda c, s: c["code"].startswith("512") and s < 0,
        "Banques créditrices",
    ),
    (
        "COMPTE_ATTENTE_NON_SOLDE",
        "ALERTE",
        lambda c, s: c["code"][:2] in ("47", "58") and s != 0,
        "Comptes d'attente non soldés",
    ),
    (
        "CHARGE_CREDITRICE",
        "ALERTE",
        lambda c, s: c["code"].startswith("6")
        and not _sens_libre(c["code"])
        and s < 0,
        "Comptes de charge créditeurs",
    ),
    (
        "PRODUIT_DEBITEUR",
        "ALERTE",
        lambda c, s: c["code"].startswith("7")
        and not _sens_libre(c["code"])
        and s > 0,
        "Comptes de produit débiteurs",
    ),
    (
        "TVA_DEDUCTIBLE_CREDITRICE",
        "ALERTE",
        lambda c, s: c["code"].startswith("4456") and s < 0,
        "TVA déductible créditrice",
    ),
    (
        "TVA_COLLECTEE_DEBITRICE",
        "ALERTE",
        lambda c, s: c["code"].startswith("4457") and s > 0,
        "TVA collectée débitrice",
    ),
    (
        "COMPTE_DEPRECIE_SOLDE",
        "ALERTE",
        lambda c, s: c["deprecie"] and s != 0,
        "Comptes dépréciés avec un solde",
    ),
)


def alertes_balance(
    balance: Sequence[Enregistrement],
    balance_tiers: Iterable[Enregistrement] = (),
    journal: Journal | None = None,
) -> tuple[Rapport, dict[str, list[str]]]:
    """Applique les règles d'alerte à une balance.

    Rôle : contrôler la balance générale et la balance par tiers.
    Paramètres : balance, comptes (clés code, libelle, type, debit, credit,
    lignes, deprecie) ; balance_tiers, soldes par (compte, tiers) (clés
    compte, tiers_id, tiers_nom, tiers_ref, debit, credit) ; journal,
    journal d'activité (muet si absent).
    Retour : (Rapport, {code compte: [codes d'alerte]}).
    Erreurs : KeyError si une clé attendue manque.
    Usages : passerelle, interface/serveur, tests.
    """
    j = ou_muet(journal)
    r = Rapport()
    par_compte: dict[str, list[str]] = {}
    debit: int = sum(c["debit"] for c in balance)
    credit: int = sum(c["credit"] for c in balance)
    r.info("comptes", len(balance))
    r.info("comptes_mouvementes", sum(1 for c in balance if c["lignes"]))
    r.info("total_debit", euros_texte(debit, ","))
    r.info("total_credit", euros_texte(credit, ","))
    if debit != credit:
        r.constat(
            "BLOQUANT",
            "BALANCE_DESEQUILIBREE",
            "Balance déséquilibrée",
            [
                "D %s / C %s"
                % (euros_texte(debit, ","), euros_texte(credit, ","))
            ],
        )
        j.dire(
            "Balance déséquilibrée : D %s / C %s"
            % (euros_texte(debit, ","), euros_texte(credit, ",")),
            "alerte",
        )
    else:
        j.dire(
            "Balance équilibrée au centime : %s €" % euros_texte(debit, ","),
            "ok",
        )

    for code_alerte, niveau, condition, message in REGLES:
        touches = [
            c for c in balance if condition(c, c["debit"] - c["credit"])
        ]
        for c in touches:
            par_compte.setdefault(c["code"], []).append(code_alerte)
        r.constat(
            niveau,
            code_alerte,
            message,
            [
                "%s %s : %s" % (c["code"], c["libelle"], solde_texte(c))
                for c in touches
            ],
        )
        if touches:
            j.dire(
                "%s : %s (%s)"
                % (
                    message,
                    len(touches),
                    ", ".join(c["code"] for c in touches[:5])
                    + ("…" if len(touches) > 5 else ""),
                ),
                "alerte",
            )

    # Par tiers : clients créditeurs, fournisseurs débiteurs.
    types = {c["code"]: c["type"] for c in balance}
    clients: list[tuple[int, str, str]] = []
    fournisseurs: list[tuple[int, str, str]] = []
    for t in balance_tiers:
        s = t["debit"] - t["credit"]
        if not t["tiers_id"]:
            continue  # signalé par l'analyse (TIERS_MANQUANT)
        lib = "%s — %s (%s) : %s" % (
            t["compte"],
            t["tiers_nom"] or "?",
            t["tiers_ref"] or "id %s" % t["tiers_id"],
            solde_texte(t),
        )
        if types.get(t["compte"]) == "asset_receivable" and s < 0:
            clients.append((s, lib, t["compte"]))
        elif types.get(t["compte"]) == "liability_payable" and s > 0:
            fournisseurs.append((-s, lib, t["compte"]))
    for code_alerte, message, liste in (
        ("CLIENT_CREDITEUR", "Clients créditeurs", clients),
        ("FOURNISSEUR_DEBITEUR", "Fournisseurs débiteurs", fournisseurs),
    ):
        liste.sort()  # les plus gros soldes anormaux d'abord
        for _, _, compte in liste:
            if code_alerte not in par_compte.setdefault(compte, []):
                par_compte[compte].append(code_alerte)
        r.constat("ALERTE", code_alerte, message, [lib for _, lib, _ in liste])
        if liste:
            j.dire(
                "%s : %s tiers" % (message, nombre_texte(len(liste))), "alerte"
            )
    return r, par_compte


def grand_livre(
    lignes: Iterable[Enregistrement], offset: int = 0, limite: int = 500
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Rend une page du grand livre d'un compte avec solde cumulé.

    Rôle : calculer le cumul sur tout le compte, puis découper la page.
    Paramètres : lignes, lignes du compte triées par date (ordre des
    sources), clés debit et credit en centimes ; offset, rang de la
    première ligne rendue ; limite, nombre maximal de lignes rendues.
    Retour : (page, totaux) — page = lignes enrichies de 'cumul', totaux =
    {lignes, debit, credit, solde}.
    Erreurs : KeyError si 'debit' ou 'credit' manque.
    Usages : interface/serveur, tests.
    """
    cumul = 0
    toutes: list[dict[str, Any]] = []
    debit = credit = 0
    for ligne in lignes:
        cumul += ligne["debit"] - ligne["credit"]
        debit += ligne["debit"]
        credit += ligne["credit"]
        toutes.append(dict(ligne, cumul=cumul))
    totaux = {
        "lignes": len(toutes),
        "debit": debit,
        "credit": credit,
        "solde": debit - credit,
    }
    fin_page = offset + limite
    return toutes[offset:fin_page], totaux
