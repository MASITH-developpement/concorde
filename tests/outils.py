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


# --- FEC de test (tests/test_migration.py, tests/test_connecteurs.py) ---
ENTETE = (
    "JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|"
    "CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|"
    "EcritureLet|DateLet|ValidDate|Montantdevise|Idevise"
)


def ligne_fec(
    j: str,
    num: str,
    d: str,
    compte: str,
    debit: str = "0,00",
    credit: str = "0,00",
    aux: str = "",
    lib: str = "lib",
    let: str = "",
) -> str:
    """Construit une ligne FEC (séparateur « | ») avec les 18 colonnes."""
    return "|".join(
        [
            j,
            j + " lib",
            num,
            d,
            compte,
            "Compte " + compte,
            aux,
            ("Tiers " + aux) if aux else "",
            "P" + num,
            d,
            lib,
            debit,
            credit,
            let,
            d if let else "",
            d,
            "",
            "",
        ]
    )


def fec(*lignes: str, entete: str = ENTETE) -> bytes:
    """Assemble un fichier FEC complet (en-tête + lignes) en ISO-8859-15."""
    return ("\n".join([entete] + list(lignes)) + "\n").encode("iso-8859-15")


BASE = [
    ligne_fec("AN", "1", "20250101", "512000", "1000,00"),
    ligne_fec("AN", "1", "20250101", "101000", credit="1000,00"),
    ligne_fec("VE", "2", "20250115", "411000", "120,00", aux="C1", let="A"),
    ligne_fec("VE", "2", "20250115", "706000", credit="100,00"),
    ligne_fec("VE", "2", "20250115", "445710", credit="20,00"),
    ligne_fec("BQ", "3", "20250120", "512000", "120,00"),
    ligne_fec(
        "BQ", "3", "20250120", "411000", credit="120,00", aux="C1", let="A"
    ),
    ligne_fec("OD", "4", "20250131", "640000", "500,00"),
    ligne_fec("OD", "4", "20250131", "421000", credit="500,00"),
]
