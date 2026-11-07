# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Routines communes aux scripts en ligne de commande CONCORDE."""

import json
import sys
from typing import Any

# Adresses où la clé API peut circuler : chiffrées, ou locales au serveur.
PREFIXES_SURS = ("https://", "http://localhost", "http://127.0.0.1")


def premiere_ligne(texte: str | None) -> str:
    """Première ligne d'un texte (vide si le texte est absent).

    Rôle : description argparse tirée de la docstring du module, qui
    vaut None quand Python tourne en mode -OO.
    Paramètres : texte — en général `__doc__`.
    Retour : la première ligne, ou "".
    Erreurs : aucune.
    Usages : scripts/concorde_comparer.py, scripts/concorde_interface_mdp.py.
    """
    return (texte or "").partition("\n")[0]


def avertir_si_non_chiffre(url: str) -> None:
    """Avertit (stderr) si la clé API va circuler en clair.

    Rôle : signaler une URL Odoo en http hors machine locale.
    Paramètres : url — adresse du serveur Odoo.
    Retour : None (message seulement, l'exécution continue).
    Erreurs : aucune.
    Usages : scripts/check_dematerialisation.py,
    scripts/concorde_odoo.py (ouvrir_source).
    """
    if not url.startswith(PREFIXES_SURS):
        print(
            "ATTENTION : connexion non chiffrée (http) — la clé API circule "
            "en clair.",
            file=sys.stderr,
        )


def ecrire_rapport_json(chemin: str, rapport: dict[str, Any]) -> None:
    """Écrit un rapport en JSON lisible (UTF-8, indenté).

    Rôle : sauvegarde du rapport complet demandé par l'option --json.
    Paramètres : chemin — fichier de sortie (écrasé) ; rapport — données
    du rapport (dictionnaire JSON dynamique ; valeurs non JSON converties
    en texte).
    Retour : None.
    Erreurs : OSError si le fichier ne peut pas être écrit.
    Usages : scripts/check_dematerialisation.py,
    scripts/concorde_odoo.py (cmd_analyser).
    """
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2, default=str)
