# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Travail par compte comptable : balance, grand livre, alertes par compte.

Les règles d'alerte portent sur le solde (débit - crédit) et dépendent du
rôle de chaque compte (core/roles_comptes.py : table client, account_type,
préfixe du plan comptable général) :

  BLOQUANT  balance déséquilibrée ; caisse créditrice
  ALERTE    banque créditrice ; paiements en suspens non soldés ;
            client créditeur, fournisseur débiteur (par tiers) ;
            compte d'attente non soldé ; charge créditrice, produit
            débiteur (sauf comptes au sens libre : 6x9 / 7x9, 603 / 713) ;
            TVA déductible créditrice ; TVA collectée débitrice (compte
            seul ou groupe), répartie sur plusieurs comptes, ou compte du
            groupe de sens contraire au groupe ; compte déprécié avec un
            solde
  INFO      provision (charge) créditrice

Avec un contexte (analyse, ADR-0017), les règles portent sur le solde
cumulé et chaque constat cite la période, le cumul, le rôle et sa source.
Sans contexte (écran Comptes, surveillance), elles portent sur la balance
reçue, rôles par préfixes, textes inchangés.

Lecture seule. Montants en centimes.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypedDict

from .analyser import Rapport
from .journal import Journal, nombre_texte, ou_muet
from .roles_comptes import (
    SEUIL_TVA_REPARTIE_EUROS_DEFAUT,
    RoleCompte,
    TableRoles,
    roles_du_plan,
)
from .soldes_cumules import SoldeTiers
from .xlsx_ecrire import euros_texte

# Compte, ligne ou solde par tiers : dictionnaire produit par la source
# (lignes SQL / XML-RPC Odoo, fichiers) dont les valeurs sont hétérogènes
# (texte, centimes, booléens, identifiants).
Enregistrement = Mapping[str, Any]

# (code alerte, niveau, rôles visés, condition(solde), message)
Regle = tuple[str, str, frozenset[str], Callable[[int], bool], str]

# Rôle d'un compte absent du plan (balance par tiers seulement).
SANS_ROLE = RoleCompte("", "")


class ContexteSoldes(TypedDict):
    """Données de l'analyse pour les règles sur solde cumulé (ADR-0017).

    cumul_comptes : solde cumulé par code de compte ; tiers : soldes par
    (compte, tiers), période et cumul ; table : rôles du client (ou None) ;
    suspens : lignes non lettrées par compte de paiements en suspens.
    """

    cumul_comptes: Mapping[str, int]
    tiers: Sequence[SoldeTiers]
    table: TableRoles | None
    suspens: Mapping[str, Sequence[Enregistrement]]


def sens_texte(solde: int) -> str:
    """Rend un solde lisible avec son sens.

    Paramètres : solde, débit - crédit en centimes.
    Retour : '1234,56 D' (débiteur), '12,00 C' (créditeur) ou '0,00'.
    Erreurs : aucune.
    Usages : solde_texte, alertes_balance (période et cumul).
    """
    if not solde:
        return "0,00"
    return "%s %s" % (euros_texte(abs(solde), ","), "D" if solde > 0 else "C")


def solde_texte(c: Enregistrement) -> str:
    """Rend le solde lisible d'un compte ou d'un tiers.

    Rôle : afficher débit - crédit avec son sens.
    Paramètres : c, enregistrement portant les clés 'debit' et 'credit'
    (centimes).
    Retour : comme `sens_texte`.
    Erreurs : KeyError si 'debit' ou 'credit' manque.
    Usages : alertes_balance (sans contexte), comparaison.
    """
    return sens_texte(c["debit"] - c["credit"])


REGLES: tuple[Regle, ...] = (
    (
        "CAISSE_CREDITRICE",
        "BLOQUANT",
        frozenset({"caisse"}),
        lambda solde: solde < 0,
        "Caisses créditrices",
    ),
    (
        "BANQUE_CREDITRICE",
        "ALERTE",
        frozenset({"banque"}),
        lambda solde: solde < 0,
        "Banques créditrices",
    ),
    (
        "COMPTE_ATTENTE_NON_SOLDE",
        "ALERTE",
        frozenset({"attente"}),
        lambda solde: solde != 0,
        "Comptes d'attente non soldés",
    ),
    (
        "CHARGE_CREDITRICE",
        "ALERTE",
        frozenset({"charge"}),
        lambda solde: solde < 0,
        "Comptes de charge créditeurs",
    ),
    (
        "CHARGE_PROVISION_CREDITRICE",
        "INFO",
        frozenset({"charge_provision"}),
        lambda solde: solde < 0,
        "Provisions créditrices en cours d'exercice (reprise possible)",
    ),
    (
        "PRODUIT_DEBITEUR",
        "ALERTE",
        frozenset({"produit"}),
        lambda solde: solde > 0,
        "Comptes de produit débiteurs",
    ),
    (
        "TVA_DEDUCTIBLE_CREDITRICE",
        "ALERTE",
        frozenset({"tva_deductible"}),
        lambda solde: solde < 0,
        "TVA déductible créditrice",
    ),
    (
        "TVA_COLLECTEE_DEBITRICE",
        "ALERTE",
        frozenset({"tva_collectee_a_part"}),
        lambda solde: solde > 0,
        "TVA collectée débitrice",
    ),
)


class _Balance:
    """Balance enrichie : période, cumul et rôle de chaque compte.

    Rôle : un seul endroit qui sait rédiger un élément de constat, avec ou
    sans contexte d'analyse.
    """

    def __init__(
        self,
        balance: Sequence[Enregistrement],
        contexte: ContexteSoldes | None,
    ) -> None:
        """Indexe la balance et les rôles du plan."""
        self.comptes = {compte_lu["code"]: compte_lu for compte_lu in balance}
        self.contexte = contexte
        self.roles = roles_du_plan(
            balance, contexte["table"] if contexte else None
        )

    def periode(self, code: str) -> int:
        """Solde des mouvements de la période (0 si compte inconnu)."""
        compte_lu = self.comptes.get(code)
        return compte_lu["debit"] - compte_lu["credit"] if compte_lu else 0

    def cumul(self, code: str) -> int:
        """Solde contrôlé : cumulé avec contexte, période sinon."""
        if self.contexte is None:
            return self.periode(code)
        return self.contexte["cumul_comptes"].get(code, 0)

    def role(self, code: str) -> RoleCompte:
        """Rôle retenu pour le compte."""
        return self.roles.get(code, SANS_ROLE)

    def valeurs(self, periode: int, cumul: int, role: RoleCompte) -> str:
        """Fin d'élément : solde, ou rôle + période + cumul (contexte)."""
        if self.contexte is None:
            return sens_texte(periode)
        return "[%s, %s] : période %s / cumul %s" % (
            role.role or "aucun rôle",
            role.source or "compte hors plan",
            sens_texte(periode),
            sens_texte(cumul),
        )

    def texte(self, code: str) -> str:
        """Élément de constat d'un compte."""
        libelle = self.comptes[code]["libelle"] if code in self.comptes else ""
        separateur = " : " if self.contexte is None else " "
        return "%s %s%s%s" % (
            code,
            libelle,
            separateur,
            self.valeurs(
                self.periode(code), self.cumul(code), self.role(code)
            ),
        )


def _marquer(
    par_compte: dict[str, list[str]], codes: Iterable[str], alerte: str
) -> None:
    """Ajoute le code d'alerte à chaque compte touché, sans doublon."""
    for code in codes:
        liste = par_compte.setdefault(code, [])
        if alerte not in liste:
            liste.append(alerte)


def alertes_balance(
    balance: Sequence[Enregistrement],
    balance_tiers: Iterable[Enregistrement] = (),
    journal: Journal | None = None,
    contexte: ContexteSoldes | None = None,
) -> tuple[Rapport, dict[str, list[str]]]:
    """Applique les règles d'alerte à une balance.

    Rôle : contrôler la balance générale et la balance par tiers.
    Paramètres : balance, comptes de la période (clés code, libelle, type,
    debit, credit, lignes, deprecie) ; balance_tiers, soldes par (compte,
    tiers) de la période (clés compte, tiers_id, tiers_nom, tiers_ref,
    debit, credit), ignorés avec un contexte (il porte les tiers) ;
    journal d'activité (muet si absent) ; contexte — soldes cumulés et
    rôles de l'analyse (ADR-0017), None pour la balance seule.
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

    balance_enrichie = _Balance(balance, contexte)

    def constater(
        niveau: str,
        code_alerte: str,
        message: str,
        elements: Sequence[str],
        touches: Sequence[str],
    ) -> None:
        """Enregistre un constat, marque les comptes, le dit au journal."""
        _marquer(par_compte, touches, code_alerte)
        r.constat(niveau, code_alerte, message, elements)
        if elements:
            j.dire(
                "%s : %s (%s)"
                % (
                    message,
                    len(elements),
                    ", ".join(touches[:5]) + ("…" if len(touches) > 5 else ""),
                ),
                "alerte",
            )

    for code_alerte, niveau, roles, condition, message in REGLES:
        touches = [
            code
            for code in balance_enrichie.comptes
            if balance_enrichie.role(code).role in roles
            and condition(balance_enrichie.cumul(code))
        ]
        constater(
            niveau,
            code_alerte,
            message,
            [balance_enrichie.texte(code) for code in touches],
            touches,
        )
    deprecies = [
        code
        for code, compte_lu in balance_enrichie.comptes.items()
        if compte_lu["deprecie"] and balance_enrichie.cumul(code) != 0
    ]
    constater(
        "ALERTE",
        "COMPTE_DEPRECIE_SOLDE",
        "Comptes dépréciés avec un solde",
        [balance_enrichie.texte(code) for code in deprecies],
        deprecies,
    )
    _alertes_tva_groupe(balance_enrichie, constater, contexte)
    _alertes_suspens(balance_enrichie, constater, contexte)
    _alertes_tiers(balance_enrichie, balance_tiers, par_compte, r, j)
    if contexte is not None:
        r.info(
            "roles_comptes",
            {
                code: {
                    "role": balance_enrichie.role(code).role,
                    "source": balance_enrichie.role(code).source,
                }
                for code in sorted(par_compte)
            },
        )
    return r, par_compte


# Signature de la fonction `constater` d'alertes_balance.
FonctionConstat = Callable[[str, str, str, Sequence[str], Sequence[str]], None]


def _alertes_tva_groupe(
    balance_enrichie: _Balance,
    constater: FonctionConstat,
    contexte: ContexteSoldes | None,
) -> None:
    """Contrôles du groupe de comptes de TVA collectée (rôle tva_collectee).

    Rôle : solde du groupe débiteur (TVA_COLLECTEE_DEBITRICE) ; au moins
    deux comptes au-delà du seuil (TVA_COLLECTEE_REPARTIE) ; compte de sens
    contraire au groupe (TVA_COLLECTEE_SENS_CONTRAIRE).
    Paramètres : balance enrichie ; constater ; contexte (seuil du client).
    Usages : alertes_balance.
    """
    membres = [
        code
        for code in balance_enrichie.comptes
        if balance_enrichie.role(code).role == "tva_collectee"
    ]
    if not membres:
        return
    table = contexte["table"] if contexte else None
    seuil = (
        table.seuil_tva_repartie
        if table
        else SEUIL_TVA_REPARTIE_EUROS_DEFAUT * 100
    )
    total = sum(balance_enrichie.cumul(code) for code in membres)
    sources = sorted({balance_enrichie.role(code).source for code in membres})
    groupe = "Groupe TVA collectée (%s) %s" % (
        ", ".join(membres),
        balance_enrichie.valeurs(
            sum(balance_enrichie.periode(code) for code in membres),
            total,
            RoleCompte("tva_collectee", " + ".join(sources)),
        ),
    )
    constater(
        "ALERTE",
        "TVA_COLLECTEE_DEBITRICE",
        "TVA collectée débitrice",
        [groupe] if total > 0 else [],
        membres if total > 0 else [],
    )
    portes = [code for code in membres if balance_enrichie.cumul(code)]
    significatifs = [
        code for code in membres if abs(balance_enrichie.cumul(code)) >= seuil
    ]
    repartie = len(significatifs) >= 2
    constater(
        "ALERTE",
        "TVA_COLLECTEE_REPARTIE",
        "TVA collectée répartie sur plusieurs comptes (seuil %s €)"
        % euros_texte(seuil, ","),
        (
            [groupe] + [balance_enrichie.texte(code) for code in portes]
            if repartie
            else []
        ),
        portes if repartie else [],
    )
    contraires = [
        code
        for code in portes
        if total and (balance_enrichie.cumul(code) > 0) != (total > 0)
    ]
    constater(
        "ALERTE",
        "TVA_COLLECTEE_SENS_CONTRAIRE",
        "Comptes de TVA collectée de sens contraire à leur groupe",
        [
            "%s — groupe : %s"
            % (balance_enrichie.texte(code), sens_texte(total))
            for code in contraires
        ],
        contraires,
    )


def _alertes_suspens(
    balance_enrichie: _Balance,
    constater: FonctionConstat,
    contexte: ContexteSoldes | None,
) -> None:
    """Paiements en suspens non soldés : lignes non lettrées, plus anciennes
    d'abord (rôle paiement_en_suspens, cumul non nul).

    Usages : alertes_balance.
    """
    touches = [
        code
        for code in balance_enrichie.comptes
        if balance_enrichie.role(code).role == "paiement_en_suspens"
        and balance_enrichie.cumul(code)
    ]
    elements: list[str] = []
    for code in touches:
        lignes = sorted(
            (contexte["suspens"] if contexte else {}).get(code, ()),
            key=lambda ligne: (ligne["date"], ligne["ligne_id"]),
        )
        if not lignes:
            elements.append(
                "%s — aucune ligne non lettrée (lettrages partiels)"
                % balance_enrichie.texte(code)
            )
        for ligne in lignes:
            elements.append(
                "%s — %s %s %s : %s"
                % (
                    balance_enrichie.texte(code),
                    ligne["date"].strftime("%d/%m/%Y"),
                    ligne["ecriture"],
                    ligne["tiers_nom"] or ligne["libelle"],
                    sens_texte(ligne["debit"] - ligne["credit"]),
                )
            )
    constater(
        "ALERTE",
        "PAIEMENT_EN_SUSPENS_NON_SOLDE",
        "Paiements en suspens non soldés (lignes non lettrées, plus "
        "anciennes d'abord)",
        elements,
        touches,
    )


def _alertes_tiers(
    balance_enrichie: _Balance,
    balance_tiers: Iterable[Enregistrement],
    par_compte: dict[str, list[str]],
    r: Rapport,
    j: Journal,
) -> None:
    """Clients créditeurs et fournisseurs débiteurs, par tiers.

    Rôle : avec contexte, solde cumulé par (compte, tiers) ; sans
    contexte, solde de `balance_tiers`. Rôles client / fournisseur.
    Usages : alertes_balance.
    """
    if balance_enrichie.contexte is not None:
        soldes: list[tuple[Enregistrement, int, int]] = [
            (solde_tiers, solde_tiers["periode"], solde_tiers["cumul"])
            for solde_tiers in balance_enrichie.contexte["tiers"]
        ]
    else:
        soldes = [
            (
                solde_tiers,
                solde_tiers["debit"] - solde_tiers["credit"],
                solde_tiers["debit"] - solde_tiers["credit"],
            )
            for solde_tiers in balance_tiers
        ]
    clients: list[tuple[int, str, str]] = []
    fournisseurs: list[tuple[int, str, str]] = []
    for solde_tiers, periode, cumul in soldes:
        if not solde_tiers["tiers_id"]:
            continue  # signalé par l'analyse (TIERS_MANQUANT)
        role = balance_enrichie.role(solde_tiers["compte"])
        lib = "%s — %s (%s)%s%s" % (
            solde_tiers["compte"],
            solde_tiers["tiers_nom"] or "?",
            solde_tiers["tiers_ref"] or "id %s" % solde_tiers["tiers_id"],
            " : " if balance_enrichie.contexte is None else " ",
            balance_enrichie.valeurs(periode, cumul, role),
        )
        if role.role == "client" and cumul < 0:
            clients.append((cumul, lib, solde_tiers["compte"]))
        elif role.role == "fournisseur" and cumul > 0:
            fournisseurs.append((-cumul, lib, solde_tiers["compte"]))
    for code_alerte, message, liste in (
        ("CLIENT_CREDITEUR", "Clients créditeurs", clients),
        ("FOURNISSEUR_DEBITEUR", "Fournisseurs débiteurs", fournisseurs),
    ):
        liste.sort()  # les plus gros soldes anormaux d'abord
        _marquer(par_compte, [compte for _, _, compte in liste], code_alerte)
        r.constat("ALERTE", code_alerte, message, [lib for _, lib, _ in liste])
        if liste:
            j.dire(
                "%s : %s tiers" % (message, nombre_texte(len(liste))), "alerte"
            )


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
