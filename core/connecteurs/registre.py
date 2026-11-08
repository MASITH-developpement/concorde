# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Logiciels branchés : nom court -> classe du connecteur (ADR-0008).

Brancher un nouveau logiciel = écrire son connecteur et l'ajouter ici.
"""

from .azalplus import ConnecteurAzalPlus
from .base import Connecteur, ErreurConnexion
from .fec import ConnecteurFec
from .odoo import ConnecteurOdoo

REGISTRE: dict[str, type[Connecteur]] = {
    ConnecteurAzalPlus.logiciel: ConnecteurAzalPlus,
    ConnecteurFec.logiciel: ConnecteurFec,
    ConnecteurOdoo.logiciel: ConnecteurOdoo,
}


def classe_connecteur(logiciel: str) -> type[Connecteur]:
    """Classe du connecteur d'un logiciel.

    Rôle : un seul endroit qui sait quels logiciels sont branchés.
    Paramètres : logiciel — nom court (ex. « fec »).
    Retour : la classe du connecteur.
    Erreurs : ErreurConnexion si le logiciel n'est pas branché (la liste
    des logiciels branchés est donnée).
    Usages : connexions.Annuaire.ajouter, connexions.Annuaire.ouvrir.
    """
    try:
        return REGISTRE[logiciel]
    except KeyError:
        raise ErreurConnexion(
            "Logiciel non branché : %r (branchés : %s)."
            % (logiciel, ", ".join(sorted(REGISTRE)))
        ) from None
