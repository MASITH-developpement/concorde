# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Ce que tout connecteur sait faire (ADR-0008, point 2).

Un connecteur traduit entre un logiciel et le `Lot` en centimes, rien de
plus : contrôles, correspondance des comptes, rapports et feu vert sont
communs (core/connecteurs/transfert.py).

  tester()                  connexion, société lue, droits
  lire(perimetre)           données du logiciel -> Lot
  ecrire(lot, ref, essai)   Lot -> logiciel ; essai=True n'écrit rien
  relire(ref)               ce qui a été écrit sous `ref` -> Lot
  environnement_test()      connecteur vers la copie de test, s'il en existe

Un connecteur qui ne sait pas lire (ou écrire) le déclare dans `capacites`
et lève ErreurConnexion si on le lui demande quand même.
"""

import datetime
import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Optional, TypedDict

from ..journal import Journal
from ..migration.lot import LigneLot, Lot


def nouveau_lot(logiciel: str, nom: str, lignes: list[LigneLot]) -> Lot:
    """Lot au format commun à partir de lignes lues par une API.

    Rôle : décrire la source d'un lot lu par API comme celle d'un fichier
    (type, nom, empreinte), pour la photo et l'audit.
    Paramètres : logiciel — nom court (« odoo »…) ; nom — base ou
    société lue ; lignes — lignes au format LigneLot (centimes).
    Retour : Lot ; empreinte SHA-256 des lignes.
    Erreurs : aucune.
    Usages : connecteurs.odoo, connecteurs.azalplus.
    """
    texte = json.dumps(lignes, sort_keys=True, default=str)
    return Lot(
        {
            "type": logiciel,
            "nom": nom,
            "empreinte": hashlib.sha256(texte.encode("utf-8")).hexdigest(),
            "encodage": "",
            "separateur": "",
            "lignes_fichier": len(lignes),
        },
        lignes,
    )


class ErreurConnexion(RuntimeError):
    """Le logiciel ne répond pas comme attendu.

    Authentification refusée, serveur injoignable, réponse illisible,
    opération que le connecteur ne sait pas faire. Le message ne contient
    jamais de secret.
    """


class CapacitesConnecteur(TypedDict):
    """Ce que le connecteur sait faire : « api », « fichier », « base »

    (lecture seule directe de la base du logiciel) ou None.
    """

    lecture: str | None
    ecriture: str | None


class InfoConnexion(TypedDict):
    """Ce que le test de connexion a lu chez le logiciel."""

    logiciel: str
    societe: str
    siren: str
    devise: str
    version: str


class PerimetreLecture(TypedDict):
    """Données à lire : période (bornes comprises, None = sans borne)."""

    du: datetime.date | None
    au: datetime.date | None


class ResultatEcriture(TypedDict):
    """Bilan d'une écriture (ou d'un essai à blanc) dans un logiciel."""

    essai: bool
    ecritures_a_creer: int
    ecritures_deja_presentes: int
    erreurs: list[str]
    fichiers: dict[str, str]


class ResultatSuppression(TypedDict):
    """Bilan de l'effacement de ce qu'une référence a écrit (ADR-0015)."""

    supprimees: int
    laissees: list[str]


class Connecteur(ABC):
    """Prise vers un logiciel : un compte précis de ce logiciel.

    `parametres` (adresse, base, dossier…) vient de l'annuaire des
    connexions ; `secrets` (jeton, clé…) du fichier de secrets. Le
    connecteur ne garde les secrets qu'en mémoire.
    """

    logiciel: ClassVar[str]
    libelle: ClassVar[str]
    capacites: ClassVar[CapacitesConnecteur]
    # Noms des paramètres et des secrets attendus : l'annuaire les vérifie
    # et refuse tout autre paramètre ; l'écran construit son formulaire.
    parametres_requis: ClassVar[tuple[str, ...]] = ()
    parametres_facultatifs: ClassVar[tuple[str, ...]] = ()
    secrets_requis: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        parametres: Mapping[str, str],
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        """Garde les paramètres et les secrets ; vérifie qu'ils sont là.

        Lève ErreurConnexion en nommant le paramètre ou le secret absent
        (jamais sa valeur).
        """
        self.parametres = dict(parametres)
        self._secrets = dict(secrets or {})
        absents = [
            nom_parametre
            for nom_parametre in self.parametres_requis
            if not parametres.get(nom_parametre)
        ]
        absents += [
            "secret " + nom_secret
            for nom_secret in self.secrets_requis
            if not self._secrets.get(nom_secret)
        ]
        if absents:
            raise ErreurConnexion(
                "%s : il manque %s." % (self.libelle, ", ".join(absents))
            )

    @abstractmethod
    def tester(self, journal: Journal) -> InfoConnexion:
        """Essaie la connexion et lit la société. Lève ErreurConnexion."""

    def lire(self, perimetre: PerimetreLecture, journal: Journal) -> Lot:
        """Lit les données du périmètre vers un Lot. Lève ErreurConnexion."""
        raise ErreurConnexion("%s ne sait pas lire." % self.libelle)

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Écrit le lot sous la référence `reference`.

        Avec `essai`, rien n'est écrit : le résultat dit ce qui serait
        créé. Une écriture déjà présente sous cette référence n'est jamais
        recréée. Lève ErreurConnexion.
        """
        raise ErreurConnexion("%s ne sait pas écrire." % self.libelle)

    def relire(self, reference: str, journal: Journal) -> Lot:
        """Relit ce qui a été écrit sous `reference`. Lève ErreurConnexion."""
        raise ErreurConnexion("%s ne sait pas relire." % self.libelle)

    def supprimer(
        self, reference: str, journal: Journal
    ) -> ResultatSuppression:
        """Efface ce qui a été écrit sous `reference` (tâche arrêtée).

        Par défaut le logiciel ne sait pas : rien n'est effacé, et la
        cause est nommée pour un effacement à la main (ADR-0015).
        """
        return {
            "supprimees": 0,
            "laissees": [
                "%s : %s ne sait pas effacer, à faire à la main dans le "
                "logiciel" % (reference, self.libelle)
            ],
        }

    def environnement_test(self) -> Optional["Connecteur"]:
        """Connecteur vers l'environnement de test propre au logiciel.

        Par défaut aucun : la connexion de test vient alors de l'annuaire
        (champ `connexion_test`), ou le transfert s'arrête après la
        simulation (ADR-0008, point 4).
        """
        return None
