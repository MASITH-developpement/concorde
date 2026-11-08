# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écriture sûre des fichiers de données JSON de CONCORDE."""

import json
import os
from collections.abc import Callable


def ecrire_json_atomique(
    chemin: str,
    donnees: object,
    ascii_seul: bool = True,
    retrait: int | None = None,
    conversion: Callable[[object], str] | None = None,
) -> None:
    """Écrit un fichier JSON d'un seul coup (fichier .tmp puis renommage).

    Rôle : qu'un fichier de données ne soit jamais lu à moitié écrit.
    Paramètres : chemin, le fichier final ; donnees, la valeur à écrire ;
    ascii_seul, retrait et conversion sont passés à json.dump
    (ensure_ascii, indent, default).
    Retour : aucun.
    Erreurs : OSError si l'écriture échoue, TypeError si une valeur n'est
    pas convertible en JSON.
    Usages : interface/serveur.py (Bases.renommer, Taches._sauver,
    Surveillance._surveiller_base, /api/rapport), core/surveillance.py
    (CentreAlertes._sauver), core/connecteurs (annuaire des connexions,
    état des transferts).
    """
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(
            donnees,
            fichier,
            ensure_ascii=ascii_seul,
            indent=retrait,
            default=conversion,
        )
    os.replace(temporaire, chemin)
