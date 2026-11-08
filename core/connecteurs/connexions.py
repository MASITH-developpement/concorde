# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Annuaire des connexions : plusieurs logiciels branchés à la fois.

Une connexion = un logiciel + un compte précis (« Sage du client A »,
« Pennylane du cabinet »…). L'annuaire (connexions.json) ne contient
AUCUN secret : un paramètre dont le nom ressemble à un secret est refusé.
Les secrets sont lus dans le fichier de secrets au moment d'ouvrir la
connexion (core/connecteurs/secrets.py).

`connexion_test` : identifiant de la connexion qui sert d'environnement
de test à celle-ci (ex. la société de test Pennylane du même cabinet).
"""

import copy
import json
import os
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import TypedDict

from ..fichier_json import ecrire_json_atomique
from ..journal import Journal
from .base import Connecteur, InfoConnexion
from .registre import classe_connecteur
from .secrets import (
    CHEMIN_SECRETS,
    effacer_secrets_connexion,
    etat_secrets,
    lire_secrets,
    secrets_connexion,
)

CHEMIN_CONNEXIONS = os.environ.get(
    "CONCORDE_CONNEXIONS", "/var/lib/concorde-interface/connexions.json"
)
# Fragments qui signalent un secret dans un nom de paramètre.
MOTS_SECRETS = (
    "cle",
    "clé",
    "jeton",
    "token",
    "secret",
    "mot_de_passe",
    "password",
    "mdp",
    "api_key",
)


class ErreurAnnuaire(ValueError):
    """Connexion inconnue, paramètre refusé, ou retrait impossible."""


class FicheConnexion(TypedDict):
    """Une connexion de l'annuaire (jamais de secret)."""

    id: str
    logiciel: str
    libelle: str
    parametres: dict[str, str]
    connexion_test: str | None
    cree_le: str
    dernier_test: str | None
    derniere_info: InfoConnexion | None


class Annuaire:
    """Connexions enregistrées, partagées entre les fils de l'interface."""

    def __init__(
        self,
        chemin: str = CHEMIN_CONNEXIONS,
        fichier_secrets: str = CHEMIN_SECRETS,
    ) -> None:
        """Charge l'annuaire (vide s'il n'existe pas encore)."""
        self.chemin = chemin
        self.fichier_secrets = fichier_secrets
        self._verrou = threading.Lock()
        self._fiches: dict[str, FicheConnexion] = {}
        if os.path.isfile(chemin):
            with open(chemin, encoding="utf-8") as fichier:
                self._fiches = {
                    fiche_lue["id"]: fiche_lue
                    for fiche_lue in json.load(fichier)
                }

    def _sauver(self) -> None:
        """Écrit l'annuaire (appelé sous le verrou)."""
        dossier = os.path.dirname(self.chemin)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        ecrire_json_atomique(
            self.chemin,
            list(self._fiches.values()),
            ascii_seul=False,
            retrait=1,
        )

    def lister(self) -> list[FicheConnexion]:
        """Toutes les connexions, par libellé."""
        with self._verrou:
            return [
                copy.deepcopy(fiche_lue)
                for fiche_lue in sorted(
                    self._fiches.values(),
                    key=lambda fiche_lue: fiche_lue["libelle"].lower(),
                )
            ]

    def obtenir(self, ident: str) -> FicheConnexion:
        """Fiche d'une connexion. Lève ErreurAnnuaire si inconnue."""
        with self._verrou:
            fiche = self._fiches.get(ident)
            if fiche is None:
                raise ErreurAnnuaire("Connexion inconnue : %s" % ident)
            return copy.deepcopy(fiche)

    def ajouter(
        self,
        logiciel: str,
        libelle: str,
        parametres: Mapping[str, str],
        connexion_test: str | None = None,
    ) -> FicheConnexion:
        """Enregistre une connexion ; rend sa fiche.

        Lève ErreurAnnuaire (paramètre au nom de secret ou inconnu du
        connecteur, libellé vide, connexion de test inconnue ou d'un autre
        logiciel) ou
        ErreurConnexion (logiciel non branché).
        """
        classe = classe_connecteur(logiciel)
        libelle = (libelle or "").strip()
        if not libelle:
            raise ErreurAnnuaire("Libellé de connexion vide.")
        refuses = [
            nom
            for nom in parametres
            if any(mot in nom.lower() for mot in MOTS_SECRETS)
        ]
        if refuses:
            raise ErreurAnnuaire(
                "Paramètre(s) refusé(s) : %s. Un secret va dans le fichier "
                "de secrets, jamais dans l'annuaire." % ", ".join(refuses)
            )
        attendus = classe.parametres_requis + classe.parametres_facultatifs
        inconnus = sorted(set(parametres) - set(attendus))
        if inconnus:
            raise ErreurAnnuaire(
                "Paramètre(s) inconnu(s) pour %s : %s (attendus : %s)."
                % (
                    classe.libelle,
                    ", ".join(inconnus),
                    ", ".join(attendus) or "aucun",
                )
            )
        ident = "%s_%s" % (logiciel, uuid.uuid4().hex[:6])
        with self._verrou:
            if connexion_test is not None:
                test = self._fiches.get(connexion_test)
                if test is None or test["logiciel"] != logiciel:
                    raise ErreurAnnuaire(
                        "Connexion de test inconnue ou d'un autre logiciel : "
                        "%s" % connexion_test
                    )
            fiche: FicheConnexion = {
                "id": ident,
                "logiciel": logiciel,
                "libelle": libelle,
                "parametres": {
                    nom_parametre: str(valeur_parametre)
                    for nom_parametre, valeur_parametre in parametres.items()
                },
                "connexion_test": connexion_test,
                "cree_le": datetime.now().isoformat(timespec="seconds"),
                "dernier_test": None,
                "derniere_info": None,
            }
            self._fiches[ident] = fiche
            self._sauver()
        return copy.deepcopy(fiche)

    def retirer(self, ident: str) -> None:
        """Retire une connexion et efface ses secrets.

        Rien ne change dans le logiciel lui-même. Lève ErreurAnnuaire si
        elle est inconnue, ou si elle sert d'environnement de test à une
        autre connexion ; ErreurSecrets ou OSError si ses secrets ne
        peuvent pas être effacés (la connexion reste alors dans
        l'annuaire).
        """
        with self._verrou:
            if ident not in self._fiches:
                raise ErreurAnnuaire("Connexion inconnue : %s" % ident)
            utilisateurs = sorted(
                fiche_lue["id"]
                for fiche_lue in self._fiches.values()
                if fiche_lue["connexion_test"] == ident
            )
            if utilisateurs:
                raise ErreurAnnuaire(
                    "%s sert d'environnement de test à %s : retrait refusé."
                    % (ident, ", ".join(utilisateurs))
                )
            effacer_secrets_connexion(
                self.fichier_secrets,
                ident,
                classe_connecteur(
                    self._fiches[ident]["logiciel"]
                ).secrets_requis,
            )
            del self._fiches[ident]
            self._sauver()

    def secrets_renseignes(self, ident: str) -> dict[str, bool]:
        """Secrets attendus par la connexion : renseignés ou non.

        Jamais de valeur. Lève ErreurAnnuaire, ErreurSecrets ou
        ErreurConnexion.
        """
        fiche = self.obtenir(ident)
        return etat_secrets(
            ident,
            classe_connecteur(fiche["logiciel"]).secrets_requis,
            lire_secrets(self.fichier_secrets),
        )

    def ouvrir(self, ident: str) -> Connecteur:
        """Connecteur prêt à servir, avec ses seuls secrets.

        Lève ErreurAnnuaire, ErreurSecrets ou ErreurConnexion.
        """
        fiche = self.obtenir(ident)
        classe = classe_connecteur(fiche["logiciel"])
        secrets = secrets_connexion(
            ident, classe.secrets_requis, lire_secrets(self.fichier_secrets)
        )
        return classe(fiche["parametres"], secrets)

    def tester(self, ident: str, journal: Journal) -> InfoConnexion:
        """Teste la connexion et garde la date et ce qui a été lu."""
        info = self.ouvrir(ident).tester(journal)
        with self._verrou:
            fiche = self._fiches[ident]
            fiche["dernier_test"] = datetime.now().isoformat(
                timespec="seconds"
            )
            fiche["derniere_info"] = info
            self._sauver()
        return info
