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
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any, NamedTuple

from .yaml_min import ValeurYaml, charger_yaml

CHEMIN_CONCORDE_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "concorde.yaml",
)
# Tables de rôles des clients : sur le serveur, hors git (jamais écrasées
# par la synchronisation de main, jamais publiées). CONCORDE_ROLES_CLIENTS
# désigne un autre fichier (tests ; analyse sans table : chemin absent).
CHEMIN_ROLES_CLIENTS = os.environ.get(
    "CONCORDE_ROLES_CLIENTS", "/etc/concorde/roles_clients.yaml"
)

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
SOURCE_CONFIGURATION = "configuration du logiciel"
SOURCE_COMPORTEMENT = "comportement des écritures"
SOURCE_LIBELLE = "libellé du compte"
SOURCE_TYPE = "account_type"
SOURCE_PREFIXE = "préfixe"

# Libellés de comptes (français, anglais) -> rôle, dans l'ordre d'essai.
_ROLES_LIBELLE = (
    (
        r"paiements?\b.*\b(en )?suspens|outstanding (receipts|payments)",
        "paiement_en_suspens",
    ),
    (r"\b(attente|suspense|suspens|à classer|a classer)\b", "attente"),
)
# Libellés propres à une famille de comptes : (préfixes, motif, rôle).
_ROLES_LIBELLE_FAMILLE = (
    (
        ("445",),
        r"intra[- ]?com|import|autoliquid|reverse charge",
        "tva_collectee_a_part",
    ),
    (("6",), r"provision", "charge_provision"),
)
# Autoliquidation : part minimale d'écritures compensées et nombre minimal.
PART_AUTOLIQUIDATION = 0.9
ECRITURES_AUTOLIQUIDATION = 3
# Compte de transit : part minimale de lignes lettrées et nombre minimal.
PART_LETTREE_TRANSIT = 0.5
LIGNES_TRANSIT = 10

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


class IndicesRoles(NamedTuple):
    """Rôles déduits automatiquement ({code: rôle}), par source.

    configuration : lue dans le logiciel par son connecteur ;
    comportement : observé dans les écritures (ObservateurRoles).
    """

    configuration: Mapping[str, str]
    comportement: Mapping[str, str]


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


def _role_libelle(code: str, libelle: str) -> str:
    """Rôle d'après le libellé du compte ('' : libellé non concluant)."""
    texte = libelle.casefold()
    for prefixes, motif, role in _ROLES_LIBELLE_FAMILLE:
        if code.startswith(prefixes) and re.search(motif, texte):
            return role
    if code[:1] in ("6", "7"):
        return ""  # « attente » n'a pas de sens pour une charge ou un produit
    for motif, role in _ROLES_LIBELLE:
        if re.search(motif, texte):
            return role
    return ""


def _role_prefixe_automatique(code: str) -> str:
    """Préfixe du plan comptable général, règles de l'ADR-0018.

    Par rapport à `_role_prefixe` : la TVA collectée 4457x forme un groupe,
    les acomptes 419 / 409 n'ont pas de règle de sens, les comptes 6412 /
    6413 (congés payés, primes, souvent repris en cours d'exercice) sont
    des provisions.
    """
    if code.startswith("4457"):
        return "tva_collectee"
    if code.startswith("419"):
        return "client_acompte"
    if code.startswith("409"):
        return "fournisseur_acompte"
    if code.startswith(("6412", "6413")):
        return "charge_provision"
    return _role_prefixe(code)


def _role_type_automatique(code: str, type_compte: str) -> str:
    """account_type d'Odoo, acomptes 419 / 409 reconnus par leur préfixe."""
    role = _role_type(code, type_compte)
    if role in ("client", "fournisseur") and code.startswith(("419", "409")):
        return role + "_acompte"
    return role


def role_compte(
    code: str,
    type_compte: str,
    table: TableRoles | None,
    libelle: str = "",
    indices: IndicesRoles | None = None,
) -> RoleCompte:
    """Rôle d'un compte pour les règles de solde, avec sa source.

    Rôle : avec `indices` (analyse, ADR-0018), essayer dans l'ordre la
    table client, la configuration du logiciel, le comportement des
    écritures, le libellé, l'account_type, puis le préfixe ; sans
    `indices` (écran Comptes, surveillance), règles de l'ADR-0017 : table
    client, account_type, préfixe, ou préfixe seul sans table.
    Paramètres : code du compte ; type_compte, account_type Odoo ('' si
    inconnu) ; table du client ou None ; libelle du compte ; indices
    déduits automatiquement ou None.
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
    if indices is not None:
        for source, roles in (
            (SOURCE_CONFIGURATION, indices.configuration),
            (SOURCE_COMPORTEMENT, indices.comportement),
        ):
            if code in roles:
                return RoleCompte(roles[code], source)
        for source, role in (
            (SOURCE_LIBELLE, _role_libelle(code, libelle)),
            (SOURCE_TYPE, _role_type_automatique(code, type_compte)),
            (SOURCE_PREFIXE, _role_prefixe_automatique(code)),
        ):
            if role:
                return RoleCompte(role, source)
        return RoleCompte("", SOURCE_PREFIXE)
    if table is not None:
        role = _role_type(code, type_compte)
        if role:
            return RoleCompte(role, SOURCE_TYPE)
    elif type_compte in ("asset_receivable", "liability_payable"):
        return RoleCompte(_ROLES_TYPE[type_compte], SOURCE_TYPE)
    return RoleCompte(_role_prefixe(code), SOURCE_PREFIXE)


def roles_du_plan(
    comptes: Sequence[Mapping[str, Any]],
    table: TableRoles | None,
    indices: IndicesRoles | None = None,
) -> dict[str, RoleCompte]:
    """Rôle de chaque compte du plan ({code: RoleCompte}).

    Paramètres : comptes — enregistrements portant 'code', 'type' et
    'libelle' ; table du client ou None ; indices déduits automatiquement
    (analyse) ou None.
    Usages : comptes.alertes_balance, passerelle.analyser_source.
    """
    return {
        compte["code"]: role_compte(
            compte["code"],
            compte.get("type") or "",
            table,
            compte.get("libelle") or "",
            indices,
        )
        for compte in comptes
    }


class ObservateurRoles:
    """Déduit des rôles du comportement des écritures (tout logiciel).

    Rôle : pendant la lecture des lignes, repérer
      - l'autoliquidation : compte de TVA collectée (445x hors 4456x) dont
        le crédit est compensé, dans la même écriture, par un débit de TVA
        déductible (4456x) du même montant, dans au moins
        PART_AUTOLIQUIDATION des écritures -> tva_collectee_a_part ;
      - le compte de transit : compte 512x / 58x dont au moins
        PART_LETTREE_TRANSIT des lignes sont lettrées (une vraie banque ne
        se lettre pas) -> paiement_en_suspens.
    Seules les lignes comptabilisées comptent.
    Usages : passerelle.analyser_source, tests.
    """

    def __init__(self) -> None:
        """Prépare des compteurs vides."""
        self._ecriture: Any = None
        self._credits_tva: list[tuple[str, int]] = []
        self._debits_deductibles: list[int] = []
        self._ecritures_tva: defaultdict[str, int] = defaultdict(int)
        self._compensees: defaultdict[str, int] = defaultdict(int)
        self._lignes_tresorerie: defaultdict[str, int] = defaultdict(int)
        self._lettrees: defaultdict[str, int] = defaultdict(int)

    def _clore_ecriture(self) -> None:
        """Compte l'écriture en cours pour chaque compte de TVA collectée."""
        for compte in {compte for compte, _ in self._credits_tva}:
            self._ecritures_tva[compte] += 1
            montants = [
                montant
                for compte_lu, montant in self._credits_tva
                if compte_lu == compte
            ]
            if all(
                montant in self._debits_deductibles for montant in montants
            ):
                self._compensees[compte] += 1
        self._credits_tva = []
        self._debits_deductibles = []

    def voir(self, ligne: Mapping[str, Any]) -> None:
        """Observe une ligne (lignes d'une même écriture consécutives)."""
        if ligne.get("etat", "posted") != "posted":
            return
        if ligne["ecriture_id"] != self._ecriture:
            self._clore_ecriture()
            self._ecriture = ligne["ecriture_id"]
        compte = ligne["compte"]
        if compte.startswith("4456") and ligne["debit"]:
            self._debits_deductibles.append(ligne["debit"])
        elif compte.startswith("445") and ligne["credit"]:
            self._credits_tva.append((compte, ligne["credit"]))
        if compte.startswith(("512", "58")):
            self._lignes_tresorerie[compte] += 1
            if ligne["lettrage"]:
                self._lettrees[compte] += 1

    def roles(self) -> dict[str, str]:
        """Rôles déduits ({code: rôle}) des lignes vues jusqu'ici."""
        self._clore_ecriture()
        res = {
            compte: "tva_collectee_a_part"
            for compte, nombre in self._ecritures_tva.items()
            if nombre >= ECRITURES_AUTOLIQUIDATION
            and self._compensees[compte] >= PART_AUTOLIQUIDATION * nombre
        }
        res.update(
            {
                compte: "paiement_en_suspens"
                for compte, nombre in self._lignes_tresorerie.items()
                if nombre >= LIGNES_TRANSIT
                and self._lettrees[compte] >= PART_LETTREE_TRANSIT * nombre
            }
        )
        return res

    def suivre(
        self, lignes: Iterable[Mapping[str, Any]]
    ) -> Iterator[Mapping[str, Any]]:
        """Rend les lignes telles quelles en les observant au passage."""
        for ligne in lignes:
            self.voir(ligne)
            yield ligne


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
