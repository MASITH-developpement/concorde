# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Rôle de chaque compte pour les règles de solde (ADR-0017).

Le rôle d'un compte (banque, caisse, TVA collectée…) décide des règles de
sens qui lui sont appliquées. Il est lu, dans l'ordre :

  1. dans la table du client (`/etc/concorde/roles_clients.yaml`, hors
     git : aucune donnée client dans le dépôt ; modèle fictif
     `roles_clients.exemple.yaml`) : code exact, puis préfixe le plus long ;
  2. d'après l'`account_type` d'Odoo ;
  3. d'après le préfixe du plan comptable général.

Sans table client, seuls les préfixes servent (et l'`account_type` pour
les comptes de tiers), comme avant l'ADR-0017. Chaque rôle est rendu avec
sa source, citée dans les constats.
"""

import os
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from .yaml_min import ValeurYaml, charger_yaml

CHEMIN_CONCORDE_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "concorde.yaml",
)
# Tables de rôles des clients : sur le serveur, hors git (jamais écrasées
# par la synchronisation de main, jamais publiées).
CHEMIN_ROLES_CLIENTS = "/etc/concorde/roles_clients.yaml"

# Rôles reconnus dans une table client, et ce qu'ils déclenchent.
ROLES_CONNUS = {
    "caisse": "CAISSE_CREDITRICE",
    "banque": "BANQUE_CREDITRICE",
    "paiement_en_suspens": "PAIEMENT_EN_SUSPENS_NON_SOLDE",
    "attente": "COMPTE_ATTENTE_NON_SOLDE",
    "depreciation": "aucune règle de sens",
    "client": "CLIENT_CREDITEUR (par tiers)",
    "client_acompte": "aucune règle de sens",
    "fournisseur": "FOURNISSEUR_DEBITEUR (par tiers)",
    "fournisseur_acompte": "aucune règle de sens",
    "charge": "CHARGE_CREDITRICE",
    "charge_provision": "CHARGE_PROVISION_CREDITRICE (INFO)",
    "charge_sens_libre": "aucune règle de sens",
    "produit": "PRODUIT_DEBITEUR",
    "produit_sens_libre": "aucune règle de sens",
    "tva_deductible": "TVA_DEDUCTIBLE_CREDITRICE",
    "tva_collectee": "groupe : TVA_COLLECTEE_DEBITRICE, _REPARTIE, "
    "_SENS_CONTRAIRE",
    "tva_collectee_a_part": "TVA_COLLECTEE_DEBITRICE (compte seul)",
}

SOURCE_TABLE = "table client"
SOURCE_TYPE = "account_type"
SOURCE_PREFIXE = "préfixe"

JOURNAUX_A_NOUVEAUX_DEFAUT = ("AN", "RAN")
SEUIL_TVA_REPARTIE_EUROS_DEFAUT = 1000

# account_type Odoo 17 -> rôle (la trésorerie est départagée par préfixe).
_ROLES_TYPE = {
    "asset_receivable": "client",
    "liability_payable": "fournisseur",
    "expense": "charge",
    "expense_depreciation": "charge",
    "expense_direct_cost": "charge",
    "income": "produit",
    "income_other": "produit",
}


class ErreurRoles(ValueError):
    """Configuration de l'analyse invalide (jamais ignorée)."""


class TableRoles(NamedTuple):
    """Table de rôles d'un client, lue dans `roles_clients.yaml`."""

    client: str
    bases: tuple[str, ...]
    societes: tuple[str, ...]
    comptes: Mapping[str, str]
    prefixes: Mapping[str, str]
    seuil_tva_repartie: int  # centimes


class ConfigAnalyse(NamedTuple):
    """Réglages de l'analyse (`concorde.yaml`) et tables des clients."""

    journaux_a_nouveaux: tuple[str, ...]
    tables: tuple[TableRoles, ...]


class RoleCompte(NamedTuple):
    """Rôle retenu pour un compte et d'où il vient."""

    role: str  # '' : aucun rôle
    source: str


def sens_libre(code: str) -> bool:
    """Dit si un compte de gestion peut avoir un solde dans les deux sens.

    Rôle : exclure des alertes charge créditrice / produit débiteur les
    comptes 6x9 / 7x9 (rabais, remises, ristournes), 603 (variation des
    stocks achetés) et 713 (variation de la production stockée).
    Paramètres : code, numéro de compte.
    Retour : True si le sens du solde est libre.
    Erreurs : aucune.
    Usages : `_role_gestion`.
    """
    return (len(code) >= 3 and code[2] == "9") or code.startswith(
        ("603", "713")
    )


def _role_gestion(code: str, role: str) -> str:
    """Rend `role` (charge ou produit), ou sa variante « sens libre »."""
    return role + "_sens_libre" if sens_libre(code) else role


def _role_prefixe(code: str) -> str:
    """Rôle d'après le préfixe du plan comptable général ('' : aucun)."""
    if code.startswith("53"):
        return "caisse"
    if code.startswith("512"):
        return "banque"
    if code[:2] in ("47", "58"):
        return "attente"
    if code.startswith("6"):
        return _role_gestion(code, "charge")
    if code.startswith("7"):
        return _role_gestion(code, "produit")
    if code.startswith("4456"):
        return "tva_deductible"
    if code.startswith("4457"):
        return "tva_collectee_a_part"
    return ""


def _role_type(code: str, type_compte: str) -> str:
    """Rôle d'après l'account_type d'Odoo ('' : type non concluant)."""
    if type_compte == "asset_cash":
        return "caisse" if code.startswith("53") else "banque"
    role = _ROLES_TYPE.get(type_compte, "")
    if role in ("charge", "produit"):
        return _role_gestion(code, role)
    return role


def role_compte(
    code: str, type_compte: str, table: TableRoles | None
) -> RoleCompte:
    """Rôle d'un compte pour les règles de solde, avec sa source.

    Rôle : appliquer l'ordre table client, account_type, préfixe ; sans
    table, préfixe seul (account_type pour les comptes de tiers).
    Paramètres : code du compte ; type_compte, account_type Odoo ('' si
    inconnu) ; table du client ou None.
    Retour : RoleCompte(role, source) ; role '' si aucune règle ne s'applique.
    Erreurs : aucune.
    Usages : `roles_du_plan`, tests.
    """
    if table is not None:
        if code in table.comptes:
            return RoleCompte(table.comptes[code], SOURCE_TABLE)
        prefixes = [
            prefixe for prefixe in table.prefixes if code.startswith(prefixe)
        ]
        if prefixes:
            return RoleCompte(
                table.prefixes[max(prefixes, key=len)], SOURCE_TABLE
            )
        role = _role_type(code, type_compte)
        if role:
            return RoleCompte(role, SOURCE_TYPE)
    elif type_compte in ("asset_receivable", "liability_payable"):
        return RoleCompte(_ROLES_TYPE[type_compte], SOURCE_TYPE)
    return RoleCompte(_role_prefixe(code), SOURCE_PREFIXE)


def roles_du_plan(
    comptes: Sequence[Mapping[str, Any]], table: TableRoles | None
) -> dict[str, RoleCompte]:
    """Rôle de chaque compte du plan ({code: RoleCompte}).

    Paramètres : comptes — enregistrements portant 'code' et 'type' ;
    table du client ou None.
    Usages : comptes.alertes_balance, passerelle.analyser_source.
    """
    return {
        compte["code"]: role_compte(
            compte["code"], compte.get("type") or "", table
        )
        for compte in comptes
    }


def _texte_liste(valeur: ValeurYaml, cle: str, origine: str) -> list[str]:
    """Liste de textes `cle` de la section `origine` ; ErreurRoles sinon."""
    if not isinstance(valeur, list) or not all(
        isinstance(element, str) for element in valeur
    ):
        raise ErreurRoles(
            "%s : « %s » doit être une liste de textes." % (origine, cle)
        )
    return [str(element) for element in valeur]


def _table_codes(valeur: ValeurYaml, cle: str, client: str) -> dict[str, str]:
    """Table {code ou préfixe: rôle} d'une entrée client, rôles vérifiés."""
    if not isinstance(valeur, dict):
        raise ErreurRoles(
            "roles_clients.yaml, client %s : « %s » doit être une table."
            % (client, cle)
        )
    res: dict[str, str] = {}
    for code, role in valeur.items():
        if not isinstance(role, str) or role not in ROLES_CONNUS:
            raise ErreurRoles(
                "roles_clients.yaml, client %s, %s %s : rôle inconnu %r "
                "(rôles possibles : %s)."
                % (client, cle, code, role, ", ".join(sorted(ROLES_CONNUS)))
            )
        res[str(code)] = role
    return res


def _seuil_centimes(valeur: ValeurYaml, origine: str) -> int:
    """Seuil en euros entiers (YAML) converti en centimes."""
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 0:
        raise ErreurRoles(
            "%s : seuil_tva_repartie_euros doit être un "
            "entier positif." % origine
        )
    return valeur * 100


def _table_client(entree: ValeurYaml, seuil_defaut: int) -> TableRoles:
    """Construit la table de rôles d'une entrée de `clients`."""
    if not isinstance(entree, dict) or not isinstance(entree.get("nom"), str):
        raise ErreurRoles(
            "roles_clients.yaml : chaque client doit avoir un « nom »."
        )
    nom = str(entree["nom"])
    seuil = entree.get("seuil_tva_repartie_euros")
    return TableRoles(
        client=nom,
        bases=tuple(
            _texte_liste(
                entree.get("bases", []),
                "bases",
                "roles_clients.yaml, client " + nom,
            )
        ),
        societes=tuple(
            _texte_liste(
                entree.get("societes", []),
                "societes",
                "roles_clients.yaml, client " + nom,
            )
        ),
        comptes=_table_codes(entree.get("comptes", {}), "comptes", nom),
        prefixes=_table_codes(entree.get("prefixes", {}), "prefixes", nom),
        seuil_tva_repartie=(
            seuil_defaut
            if seuil is None
            else _seuil_centimes(seuil, "roles_clients.yaml, client %s" % nom)
        ),
    )


def _lire_racine(chemin: str) -> dict[str, ValeurYaml]:
    """Table racine d'un fichier YAML ({} si le fichier est absent)."""
    if not os.path.exists(chemin):
        return {}
    contenu = charger_yaml(chemin)
    if not isinstance(contenu, dict):
        raise ErreurRoles("%s : table attendue à la racine." % chemin)
    return contenu


def lire_configuration(
    chemin_reglages: str = CHEMIN_CONCORDE_YAML,
    chemin_roles: str = CHEMIN_ROLES_CLIENTS,
) -> ConfigAnalyse:
    """Lit les réglages de l'analyse et les tables de rôles des clients.

    Rôle : charger la section `analyse` de `concorde.yaml` (réglages
    communs, dans git) et la section `clients` de `roles_clients.yaml`
    (données des clients, hors git).
    Paramètres : chemin_reglages ; chemin_roles. Un fichier absent donne ses
    valeurs par défaut : sans `roles_clients.yaml`, aucune table client
    (préfixes seuls) ; sans `concorde.yaml` (moteur embarqué dans le module
    Odoo), journaux AN / RAN et seuil de 1 000 €.
    Retour : ConfigAnalyse(journaux_a_nouveaux, tables).
    Erreurs : ErreurYaml (syntaxe) ; ErreurRoles (section invalide, ou
    section `clients` dans `concorde.yaml` : les données des clients n'ont
    pas leur place dans le dépôt public).
    Usages : passerelle.analyser_source, tests.
    """
    config = _lire_racine(chemin_reglages)
    if "clients" in config:
        raise ErreurRoles(
            "concorde.yaml : section « clients » interdite (dépôt public) ; "
            "les tables des clients vont dans %s." % CHEMIN_ROLES_CLIENTS
        )
    analyse = config.get("analyse", {})
    if not isinstance(analyse, dict):
        raise ErreurRoles("concorde.yaml : « analyse » doit être une table.")
    seuil = analyse.get("seuil_tva_repartie_euros")
    seuil_defaut = (
        SEUIL_TVA_REPARTIE_EUROS_DEFAUT * 100
        if seuil is None
        else _seuil_centimes(seuil, "concorde.yaml, analyse")
    )
    journaux = analyse.get("journaux_a_nouveaux")
    clients = _lire_racine(chemin_roles).get("clients", [])
    if not isinstance(clients, list):
        raise ErreurRoles(
            "roles_clients.yaml : « clients » doit être une liste."
        )
    return ConfigAnalyse(
        (
            JOURNAUX_A_NOUVEAUX_DEFAUT
            if journaux is None
            else tuple(
                _texte_liste(
                    journaux, "journaux_a_nouveaux", "concorde.yaml, analyse"
                )
            )
        ),
        tuple(
            _table_client(entree_client, seuil_defaut)
            for entree_client in clients
        ),
    )


def table_du_client(
    config: ConfigAnalyse, base: str, societe: str
) -> TableRoles | None:
    """Table de rôles du client d'une base, ou None.

    Rôle : reconnaître le client par le nom de la base, puis, en secours
    (copies de préproduction renommées), par le nom de la société Odoo
    (casse ignorée).
    Paramètres : config lue ; base ; societe, nom de la société Odoo.
    Retour : la table du client, ou None si aucun client ne correspond.
    Erreurs : aucune.
    Usages : passerelle.analyser_source, tests.
    """
    for table in config.tables:
        if base in table.bases:
            return table
    nom = societe.casefold()
    for table in config.tables:
        if nom in (nom_societe.casefold() for nom_societe in table.societes):
            return table
    return None
