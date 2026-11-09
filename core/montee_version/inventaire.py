# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Inventaire avant une montée de version (ADR-0010 étape 1, ADR-0012 point 4).

Pour chaque saut, chaque module installé est cherché dans la table de
couverture d'OpenUpgrade du commit figé qui fera ce saut :
- couvert : « Done » ou « Nothing to do » ;
- à vérifier (ne bloque pas seul, figure au rapport) : traitement partiel,
  ou module de localisation `l10n_*` (données du plan comptable, dont
  l'effet est contrôlé par la photo comptable au centime) ;
- bloquant : pas encore traité, ou absent de la liste (module sur mesure,
  module OCA, module Enterprise).
"""

from typing import TypedDict

from ..odoo_source import ConnexionSql
from .openupgrade import (
    ErreurOpenUpgrade,
    etat_couvert,
    fichier_couverture,
    lire_couverture,
    sauts,
    version_majeure,
)
from .photo import requete_lecture, version_odoo

PREFIXE_LOCALISATION = "l10n_"
_SQL_MODULES_INSTALLES = (
    "SELECT name FROM ir_module_module WHERE state = 'installed' "
    "ORDER BY name"
)


class ModuleBloquant(TypedDict):
    """Module qui empêche un saut, et pourquoi."""

    module: str
    cause: str


class SautInventaire(TypedDict):
    """Un saut : version visée, modules couverts, à vérifier, bloquants."""

    vers: int
    couverts: int
    a_verifier: list[ModuleBloquant]
    bloquants: list[ModuleBloquant]


class Inventaire(TypedDict):
    """Résultat de l'inventaire d'une base."""

    base: str
    version: str
    arrivee: int
    modules: list[str]
    sauts: list[SautInventaire]
    bloque: bool


def lire_modules(connexion: ConnexionSql, base: str) -> tuple[str, list[str]]:
    """Version et modules installés d'une base (lecture seule).

    Rôle : la première lecture de l'inventaire.
    Paramètres : connexion — session SQL en lecture seule ; base — nom.
    Retour : (version d'Odoo, noms des modules installés, triés).
    Erreurs : ErreurPhoto (pas une base Odoo) ; psycopg2.Error.
    Usages : scripts/concorde_montee (inventaire).
    """
    version = version_odoo(connexion, base)
    modules = [
        str(ligne[0])
        for ligne in requete_lecture(connexion, _SQL_MODULES_INSTALLES)
    ]
    connexion.rollback()
    return version, modules


def couverture_saut(dossier_openupgrade: str, cible: int) -> dict[str, str]:
    """Table de couverture du saut vers `cible`, lue sur le disque.

    Paramètres : dossier_openupgrade — copie au commit figé de `cible`.
    Retour : {module: état}.
    Erreurs : OSError (fichier absent) ; ErreurOpenUpgrade.
    Usages : scripts/concorde_montee (inventaire), montee.
    """
    with open(
        fichier_couverture(dossier_openupgrade, cible), encoding="utf-8"
    ) as fichier:
        return lire_couverture(fichier.read())


def classer_module(module: str, etat: str | None) -> tuple[str, str]:
    """Classe un module pour un saut : couvert, à vérifier ou bloquant.

    Rôle : la règle de l'inventaire, en un seul endroit.
    Paramètres : module — nom ; etat — état dans la table du saut, None
    si le module n'y figure pas.
    Retour : (« couvert » | « a_verifier » | « bloquant », cause).
    Erreurs : aucune.
    Usages : inventorier, tests.
    """
    if etat is not None and etat_couvert(etat):
        return "couvert", ""
    if etat:
        return "a_verifier", "traitement incomplet (%s)" % etat
    if module.startswith(PREFIXE_LOCALISATION):
        return (
            "a_verifier",
            "localisation (plan comptable) %s : contrôlée par la photo "
            "comptable" % ("non listée" if etat is None else "non marquée"),
        )
    if etat is None:
        return (
            "bloquant",
            "absent de la liste du saut (module sur mesure, OCA ou "
            "Enterprise)",
        )
    return "bloquant", "pas encore traité pour ce saut"


def inventorier(
    base: str,
    version: str,
    modules: list[str],
    arrivee: int,
    couvertures: dict[int, dict[str, str]],
) -> Inventaire:
    """Classe chaque module installé, saut par saut.

    Rôle : dire avant toute montée ce qui la bloquerait (ADR-0010).
    Paramètres : base ; version — version de la base ; modules —
    installés ; arrivee — version voulue ; couvertures — {version visée:
    table de couverture de ce saut}.
    Retour : Inventaire ; `bloque` vrai si un seul module bloque un saut.
    Erreurs : ErreurOpenUpgrade (saut impossible, table manquante).
    Usages : scripts/concorde_montee (inventaire), tests.
    """
    liste_sauts: list[SautInventaire] = []
    for cible in sauts(version_majeure(version), arrivee):
        table = couvertures.get(cible)
        if table is None:
            raise ErreurOpenUpgrade(
                "Table de couverture manquante pour le saut vers Odoo %d."
                % cible
            )
        classes: dict[str, list[ModuleBloquant]] = {
            "couvert": [],
            "a_verifier": [],
            "bloquant": [],
        }
        for module in modules:
            classe, cause = classer_module(module, table.get(module))
            classes[classe].append({"module": module, "cause": cause})
        liste_sauts.append(
            {
                "vers": cible,
                "couverts": len(classes["couvert"]),
                "a_verifier": classes["a_verifier"],
                "bloquants": classes["bloquant"],
            }
        )
    return {
        "base": base,
        "version": version,
        "arrivee": arrivee,
        "modules": modules,
        "sauts": liste_sauts,
        "bloque": any(saut["bloquants"] for saut in liste_sauts),
    }
