# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Connecteur FEC : fichier déposé dans CONCORDE, ou FEC produit.

Lecture : le FEC que le client a déposé (Sage 100, Sage 50, Quadra, Loop
et tout logiciel français sans API, ADR-0008). Paramètre `chemin`.
Écriture : un FEC DGFiP contrôlé, un dossier par référence de transfert.
Paramètre `dossier`. Une référence déjà écrite n'est jamais réécrite.

Les écritures hors période sont gardées dans `lot.retirees` (rien ne
disparaît sans trace).
"""

import os
import re
from typing import ClassVar

from ..journal import Journal, nombre_texte
from ..migration.connecteur_fec import ErreurConnecteur, lire_fec
from ..migration.export import ecrire_fec_lot
from ..migration.lot import Lot
from ..telecharger import ErreurFec
from .base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    PerimetreLecture,
    ResultatEcriture,
)

NOM_FEC = "FEC.txt"
DOSSIER_ESSAIS = "essais"
_SIREN_DANS_NOM = re.compile(r"^(\d{9})FEC\d{8}", re.IGNORECASE)


def dossier_reference(dossier: str, reference: str) -> str:
    """Dossier où une référence de transfert est écrite.

    Rôle : nommer le dossier sans caractère dangereux (« / » compris).
    Paramètres : dossier — dossier de la connexion ; reference — ex.
    « CONCORDE/T20261108-1a2b ».
    Retour : chemin du sous-dossier.
    Erreurs : ErreurConnexion si la référence est vide une fois nettoyée.
    Usages : ConnecteurFec.ecrire, ConnecteurFec.relire.
    """
    nom = re.sub(r"[^A-Za-z0-9_-]+", "_", reference).strip("_")
    if not nom:
        raise ErreurConnexion("Référence de transfert vide.")
    return os.path.join(dossier, nom)


def retirer_hors_periode(lot: Lot, perimetre: PerimetreLecture) -> int:
    """Retire du lot les écritures hors de la période demandée.

    Rôle : appliquer le périmètre d'un transfert à un fichier qui contient
    plus que la période.
    Paramètres : lot — modifié sur place ; perimetre — bornes comprises.
    Retour : nombre de lignes retirées (gardées dans lot.retirees avec le
    motif « hors période »).
    Erreurs : aucune.
    Usages : ConnecteurFec.lire.
    """
    du, au = perimetre["du"], perimetre["au"]
    gardees = []
    for ligne in lot.lignes:
        if (du and ligne["date"] < du) or (au and ligne["date"] > au):
            lot.retirees.append((ligne, "hors période"))
        else:
            gardees.append(ligne)
    retirees = len(lot.lignes) - len(gardees)
    lot.lignes = gardees
    return retirees


class ConnecteurFec(Connecteur):
    """FEC déposé (lecture) ou FEC produit dans un dossier (écriture)."""

    logiciel = "fec"
    libelle = "FEC (fichier)"
    capacites: ClassVar[CapacitesConnecteur] = {
        "lecture": "fichier",
        "ecriture": "fichier",
    }

    def tester(self, journal: Journal) -> InfoConnexion:
        """Vérifie que le fichier se lit, ou que le dossier s'écrit."""
        chemin = self.parametres.get("chemin")
        dossier = self.parametres.get("dossier")
        if chemin:
            if not os.path.isfile(chemin) or not os.access(chemin, os.R_OK):
                raise ErreurConnexion(
                    "FEC introuvable ou illisible : %s" % chemin
                )
            trouve = _SIREN_DANS_NOM.match(os.path.basename(chemin))
            siren = trouve.group(1) if trouve else ""
        elif dossier:
            os.makedirs(dossier, exist_ok=True)
            if not os.access(dossier, os.W_OK):
                raise ErreurConnexion(
                    "Dossier non inscriptible : %s" % dossier
                )
            siren = ""
        else:
            raise ErreurConnexion(
                "FEC (fichier) : il manque le paramètre chemin ou dossier."
            )
        journal.dire("FEC : %s accessible" % (chemin or dossier), "ok")
        return {
            "logiciel": self.logiciel,
            "societe": "",
            "siren": siren,
            "devise": "EUR",
            "version": "FEC DGFiP (article A47 A-1 du LPF)",
        }

    def lire(self, perimetre: PerimetreLecture, journal: Journal) -> Lot:
        """Lit le FEC déposé, puis retire ce qui sort de la période."""
        chemin = self.parametres.get("chemin")
        if not chemin:
            raise ErreurConnexion("FEC (fichier) : aucun fichier déposé.")
        try:
            with open(chemin, "rb") as fichier:
                brut = fichier.read()
            lot = lire_fec(brut, os.path.basename(chemin), journal=journal)
        except (OSError, ErreurConnecteur) as exc:
            raise ErreurConnexion("FEC illisible : %s" % exc) from exc
        retirees = retirer_hors_periode(lot, perimetre)
        if retirees:
            journal.dire(
                "%s ligne(s) hors période gardées à part"
                % nombre_texte(retirees),
                "detail",
            )
        return lot

    def _chemin_fec(self, reference: str) -> str:
        """Chemin du FEC écrit sous une référence."""
        dossier = self.parametres.get("dossier")
        if not dossier:
            raise ErreurConnexion("FEC (fichier) : aucun dossier d'écriture.")
        return os.path.join(dossier_reference(dossier, reference), NOM_FEC)

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Écrit le FEC de la référence (sauf essai, ou déjà écrit)."""
        chemin = self._chemin_fec(reference)
        ecritures = len(lot.ecritures())
        if os.path.exists(chemin):
            journal.dire(
                "Référence %s déjà écrite : rien n'est réécrit" % reference,
                "alerte",
            )
            return {
                "essai": essai,
                "ecritures_a_creer": 0,
                "ecritures_deja_presentes": ecritures,
                "erreurs": [],
                "fichiers": {"fec": chemin},
            }
        resultat: ResultatEcriture = {
            "essai": essai,
            "ecritures_a_creer": ecritures,
            "ecritures_deja_presentes": 0,
            "erreurs": [],
            "fichiers": {},
        }
        if essai:
            return resultat
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        try:
            ecrire_fec_lot(lot, chemin)
        except (OSError, ErreurFec) as exc:
            resultat["erreurs"].append(str(exc))
            return resultat
        resultat["fichiers"]["fec"] = chemin
        journal.dire(
            "FEC écrit : %s écriture(s) dans %s"
            % (nombre_texte(ecritures), chemin),
            "ok",
        )
        return resultat

    def relire(self, reference: str, journal: Journal) -> Lot:
        """Relit le FEC écrit sous la référence."""
        chemin = self._chemin_fec(reference)
        try:
            with open(chemin, "rb") as fichier:
                return lire_fec(fichier.read(), NOM_FEC, journal=journal)
        except (OSError, ErreurConnecteur) as exc:
            raise ErreurConnexion("FEC écrit illisible : %s" % exc) from exc

    def environnement_test(self) -> Connecteur | None:
        """Sous-dossier « essais » du dossier d'écriture."""
        dossier = self.parametres.get("dossier")
        if not dossier:
            return None
        return ConnecteurFec(
            {"dossier": os.path.join(dossier, DOSSIER_ESSAIS)}
        )
