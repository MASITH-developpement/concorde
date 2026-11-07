# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Doublures partagées par les tests (fausses connexions Odoo et PostgreSQL).

Chaque doublure utilisée par au moins deux fichiers de test vit ici, une
seule fois, pour ne jamais être recopiée.
"""

import os
from types import TracebackType
from typing import Any, Literal, TypeVar

# Dossier racine du dépôt (parent du dossier tests/).
RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Enregistrement Odoo tel que le rend XML-RPC (valeurs hétérogènes : texte,
# nombre, booléen, paire [id, nom]…), ou ligne de données de test.
Enregistrement = dict[str, Any]


class FauxCommun:
    """Point d'entrée XML-RPC « common » d'un Odoo 17 simulé.

    Rôle : remplace ``xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common")``
    pour l'identification, sans réseau.
    Usages : ``tests/test_injection.py``, ``tests/test_odoo_donnees.py``,
    ``tests/test_interface.py``.
    """

    def version(self) -> dict[str, str]:
        """Rend la version du serveur simulé.

        Paramètres : aucun.
        Retour : ``{"server_version": "17.0"}``.
        Erreurs : aucune.
        Usages : détection de version par les sources et l'injection.
        """
        return {"server_version": "17.0"}

    def authenticate(self, *_identifiants: object) -> int:
        """Accepte toute identification et rend l'utilisateur n° 2.

        Paramètres : ``_identifiants`` (base, identifiant, clé, contexte),
        ignorés.
        Retour : l'identifiant d'utilisateur Odoo ``2``.
        Erreurs : aucune.
        Usages : ouverture de session des sources et de l'injection simulées.
        """
        return 2


CurseurAvecContexte = TypeVar("CurseurAvecContexte", bound="CurseurSimule")


class CurseurSimule:
    """Base des faux curseurs PostgreSQL utilisables avec ``with``.

    Rôle : fournit le protocole de gestionnaire de contexte d'un curseur
    psycopg (``with connexion.cursor() as curseur``) ; chaque doublure en
    hérite et n'écrit que ``execute`` / ``fetch*``.
    Usages : ``tests/test_bases_locales.py``, ``tests/test_injection.py``.
    """

    def __enter__(self: CurseurAvecContexte) -> CurseurAvecContexte:
        """Ouvre le bloc ``with``.

        Paramètres : aucun.
        Retour : le curseur lui-même.
        Erreurs : aucune.
        Usages : ``with connexion.cursor() as curseur``.
        """
        return self

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> Literal[False]:
        """Ferme le bloc ``with`` sans masquer d'exception.

        Paramètres : ``type_exception``, ``exception``, ``trace`` — exception
        levée dans le bloc (``None`` s'il n'y en a pas).
        Retour : ``False`` : toute exception est propagée.
        Erreurs : aucune.
        Usages : fin du bloc ``with connexion.cursor() as curseur``.
        """
        return False
