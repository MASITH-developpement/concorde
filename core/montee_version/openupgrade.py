# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Ce que CONCORDE sait d'OpenUpgrade (OCA, AGPL-3), sans jamais l'importer.

OpenUpgrade est lancé tel quel, comme programme séparé, à un commit figé
par version visée (ADR-0010). Ce module ne contient que des références :
les commits, la bibliothèque à installer dans l'image Odoo, et la lecture
de la table de couverture que publie OpenUpgrade pour chaque saut
(`docsource/modulesXX0-YY0.rst`).
"""

import os
import re

from .commandes import executer

DEPOT_OPENUPGRADE = "https://github.com/OCA/OpenUpgrade"
# Version visée -> commit figé de la branche OCA (relu à chaque changement).
COMMITS_OPENUPGRADE = {
    15: "913e7d32c7dafb1ec7131e74929053af7f7a23a6",
    16: "afa31b1df1a4dd1f5f5c8cc47d938685fa255d1d",
    17: "61daab09ab6c0d21234b96374d9291d3e02ee9e4",
    18: "9229e2cc4192631eeb91697022b81f96684b4c90",
}
OPENUPGRADELIB = "openupgradelib==3.13.7"
VERSION_MIN = 14
VERSION_MAX = max(COMMITS_OPENUPGRADE)
# États de la table qui valent « couvert » (casse ignorée).
ETATS_COUVERTS = ("done", "nothing to do")

# Ligne d'un module : « | |new| nom   | État  | Remarque |» (marque
# |new| ou |del| facultative ; la colonne État peut finir par « + »).
_LIGNE_MODULE = re.compile(
    r"^\|\s*(?:\|(?:new|del)\|\s*)?(?P<module>[A-Za-z0-9_.]+)\s*"
    r"\|(?P<etat>[^|+]*)[|+]"
)


class ErreurOpenUpgrade(ValueError):
    """Saut impossible ou table de couverture illisible."""


def version_majeure(version: str) -> int:
    """Numéro majeur d'une version d'Odoo (« 14.0.1.3 » -> 14).

    Rôle : un seul endroit qui lit la version d'une base ou d'un fichier.
    Paramètres : version — texte de la version.
    Retour : le numéro majeur.
    Erreurs : ErreurOpenUpgrade si le texte n'est pas une version.
    Usages : sauts, inventaire, sauvegarde.
    """
    debut = version.strip().split(".", 1)[0]
    if not debut.isdigit():
        raise ErreurOpenUpgrade("Version d'Odoo illisible : %r" % version)
    return int(debut)


def sauts(depart: int, arrivee: int) -> list[int]:
    """Versions visées, une à une, de `depart` à `arrivee`.

    Rôle : la montée se fait toujours une version à la fois (ADR-0010).
    Paramètres : depart — version de la base ; arrivee — version voulue.
    Retour : [depart + 1, …, arrivee].
    Erreurs : ErreurOpenUpgrade si une version est hors de 14 à 18, ou si
    l'arrivée n'est pas après le départ.
    Usages : inventaire, montee.
    """
    if not VERSION_MIN <= depart < arrivee <= VERSION_MAX:
        raise ErreurOpenUpgrade(
            "Montée impossible de %s vers %s : versions prises en charge "
            "%d à %d, arrivée après le départ."
            % (depart, arrivee, VERSION_MIN, VERSION_MAX)
        )
    return list(range(depart + 1, arrivee + 1))


def fichier_couverture(dossier: str, cible: int) -> str:
    """Chemin de la table de couverture du saut vers `cible`.

    Paramètres : dossier — copie d'OpenUpgrade au commit figé de `cible` ;
    cible — version visée.
    Retour : <dossier>/docsource/modules<cible-1>0-<cible>0.rst.
    Erreurs : aucune.
    Usages : inventaire.couverture_saut.
    """
    return os.path.join(
        dossier, "docsource", "modules%d0-%d0.rst" % (cible - 1, cible)
    )


def lire_couverture(texte: str) -> dict[str, str]:
    """Table de couverture d'OpenUpgrade -> {module: état}.

    Rôle : savoir, pour un saut, si chaque module est traité.
    Paramètres : texte — contenu du fichier modulesXX0-YY0.rst.
    Retour : {module: état tel qu'écrit, sans espaces ; « » si vide}.
    Erreurs : ErreurOpenUpgrade si aucune ligne de module n'est trouvée
    (fichier qui n'est pas une table de couverture).
    Usages : inventaire.couverture_saut, tests.
    """
    etats: dict[str, str] = {}
    for ligne in texte.splitlines():
        trouve = _LIGNE_MODULE.match(ligne)
        if trouve and trouve.group("module") != "Module":
            etats[trouve.group("module")] = trouve.group("etat").strip()
    if not etats:
        raise ErreurOpenUpgrade(
            "Table de couverture d'OpenUpgrade illisible : aucun module."
        )
    return etats


def etat_couvert(etat: str) -> bool:
    """Vrai si l'état de la table veut dire « module traité » en entier."""
    return etat.strip().lower() in ETATS_COUVERTS


def recuperer(racine: str, cible: int) -> str:
    """Copie d'OpenUpgrade au commit figé du saut vers `cible`.

    Rôle : toujours le même code OpenUpgrade pour un saut, non modifié,
    et la même table de couverture pour l'inventaire.
    Paramètres : racine — dossier des copies (une par version visée) ;
    cible — version visée.
    Retour : <racine>/<cible>, au commit COMMITS_OPENUPGRADE[cible]
    (copie déjà présente et au bon commit : reprise telle quelle).
    Erreurs : ErreurOpenUpgrade (version sans commit figé, commit obtenu
    différent) ; ErreurCommande (git en échec) ; OSError.
    Usages : scripts/concorde_montee, montee.
    """
    commit = COMMITS_OPENUPGRADE.get(cible)
    if commit is None:
        raise ErreurOpenUpgrade("Aucun commit figé pour Odoo %s." % cible)
    dossier = os.path.join(racine, str(cible))
    if not os.path.isdir(os.path.join(dossier, ".git")):
        os.makedirs(dossier, exist_ok=True)
        executer(["git", "init", "-q", dossier])
        executer(
            [
                "git",
                "-C",
                dossier,
                "fetch",
                "-q",
                "--depth",
                "1",
                DEPOT_OPENUPGRADE,
                commit,
            ]
        )
        executer(["git", "-C", dossier, "checkout", "-q", "FETCH_HEAD"])
    obtenu = executer(["git", "-C", dossier, "rev-parse", "HEAD"]).strip()
    if obtenu != commit:
        raise ErreurOpenUpgrade(
            "OpenUpgrade %s : commit %s au lieu de %s."
            % (cible, obtenu, commit)
        )
    return dossier
