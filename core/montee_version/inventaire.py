# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Inventaire avant une montée de version (ADR-0010 étape 1, ADR-0012 point 4).

Pour chaque saut, chaque module installé est cherché dans la table de
couverture d'OpenUpgrade du commit figé qui fera ce saut :
- couvert : « Done », « Nothing to do », « No DB layout changes », ou
  module repris par un autre à ce saut (apriori.py, « Merged into ») ;
- à vérifier (ne bloque pas seul, figure au rapport) : traitement partiel,
  module retiré par Odoo, module standard listé mais non annoté, ou
  localisation `l10n_*` (effet contrôlé par la photo comptable au centime) ;
- bloquant : absent de la liste (module sur mesure, OCA ou Enterprise).
Les modules suivent les fusions et retraits d'un saut à l'autre.
"""

from typing import TypedDict

from ..odoo_source import ConnexionSql
from .openupgrade import (
    EntreeCouverture,
    ErreurOpenUpgrade,
    etat_couvert,
    fichier_apriori,
    fichier_couverture,
    fusion_notee,
    lire_apriori,
    lire_couverture,
    sans_changement,
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


class CouvertureSaut(TypedDict):
    """Ce qu'OpenUpgrade dit d'un saut : table des modules et fusions."""

    modules: dict[str, EntreeCouverture]
    fusions: dict[str, str]


def couverture_saut(dossier_openupgrade: str, cible: int) -> CouvertureSaut:
    """Table de couverture et fusions du saut vers `cible`, lues sur disque.

    Paramètres : dossier_openupgrade — copie au commit figé de `cible`.
    Retour : CouvertureSaut.
    Erreurs : OSError (fichier absent) ; ErreurOpenUpgrade.
    Usages : montee.Montee.faire_inventaire.
    """
    with open(
        fichier_couverture(dossier_openupgrade, cible), encoding="utf-8"
    ) as fichier:
        modules = lire_couverture(fichier.read())
    with open(
        fichier_apriori(dossier_openupgrade), encoding="utf-8"
    ) as fichier:
        fusions = lire_apriori(fichier.read())
    return {"modules": modules, "fusions": fusions}


def classer_module(
    module: str, entree: EntreeCouverture | None, fusion: str | None
) -> tuple[str, str]:
    """Classe un module pour un saut : couvert, à vérifier ou bloquant.

    Rôle : la règle de l'inventaire, en un seul endroit.
    Paramètres : module — nom ; entree — sa ligne dans la table du saut
    (None s'il n'y figure pas) ; fusion — module qui le reprend à ce
    saut (apriori.py ou note « Merged into »), sinon None.
    Retour : (« couvert » | « a_verifier » | « bloquant », cause).
    Erreurs : aucune.
    Usages : inventorier, tests.
    """
    if fusion is not None:
        return "couvert", "repris par %s" % fusion
    if entree is None:
        if module.startswith(PREFIXE_LOCALISATION):
            return (
                "a_verifier",
                "localisation (plan comptable) non listée : contrôlée par la "
                "photo comptable",
            )
        return (
            "bloquant",
            "absent de la liste du saut (module sur mesure, OCA ou "
            "Enterprise)",
        )
    if etat_couvert(entree["etat"]) or sans_changement(entree["note"]):
        return "couvert", ""
    if entree["retire"]:
        return "a_verifier", "retiré par Odoo dans cette version"
    if entree["etat"]:
        return "a_verifier", "traitement incomplet (%s)" % entree["etat"]
    if module.startswith(PREFIXE_LOCALISATION):
        return (
            "a_verifier",
            "localisation (plan comptable) non marquée : contrôlée par la "
            "photo comptable",
        )
    return "a_verifier", "module standard non annoté par OpenUpgrade"


def inventorier(
    base: str,
    version: str,
    modules: list[str],
    arrivee: int,
    couvertures: dict[int, CouvertureSaut],
) -> Inventaire:
    """Classe chaque module installé, saut par saut.

    Rôle : dire avant toute montée ce qui la bloquerait (ADR-0010). Les
    modules suivent les fusions et retraits d'un saut à l'autre, comme
    pendant la vraie montée.
    Paramètres : base ; version — version de la base ; modules —
    installés ; arrivee — version voulue ; couvertures — {version visée:
    CouvertureSaut de ce saut}.
    Retour : Inventaire ; `bloque` vrai si un seul module bloque un saut.
    Erreurs : ErreurOpenUpgrade (saut impossible, table manquante).
    Usages : montee.Montee.faire_inventaire, tests.
    """
    liste_sauts: list[SautInventaire] = []
    presents = sorted(set(modules))
    for cible in sauts(version_majeure(version), arrivee):
        couverture = couvertures.get(cible)
        if couverture is None:
            raise ErreurOpenUpgrade(
                "Table de couverture manquante pour le saut vers Odoo %d."
                % cible
            )
        classes: dict[str, list[ModuleBloquant]] = {
            "couvert": [],
            "a_verifier": [],
            "bloquant": [],
        }
        suivants: set[str] = set()
        for module in presents:
            entree = couverture["modules"].get(module)
            fusion = couverture["fusions"].get(module) or (
                fusion_notee(entree["note"]) if entree else None
            )
            classe, cause = classer_module(module, entree, fusion)
            classes[classe].append({"module": module, "cause": cause})
            if fusion is not None:
                suivants.add(fusion)
            elif not (entree and entree["retire"]):
                suivants.add(module)
        liste_sauts.append(
            {
                "vers": cible,
                "couverts": len(classes["couvert"]),
                "a_verifier": classes["a_verifier"],
                "bloquants": classes["bloquant"],
            }
        )
        presents = sorted(suivants)
    return {
        "base": base,
        "version": version,
        "arrivee": arrivee,
        "modules": modules,
        "sauts": liste_sauts,
        "bloque": any(saut["bloquants"] for saut in liste_sauts),
    }
