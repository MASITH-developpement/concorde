# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""File de demandes entre l'interface et le service de montée (ADR-0012).

L'interface n'a pas accès à Docker. Elle dépose une demande (fichier
JSON) ; le service de montée (root) la relit, la vérifie (action connue,
champs attendus, valeurs bien formées) et l'exécute. Rien d'autre ne
peut être demandé. Le service publie ensuite, hors du volume chiffré, un
résumé de chaque montée lisible par l'interface : jamais la base.
"""

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Any, TypedDict

from ..fichier_json import ecrire_json_atomique
from ..journal import Journal
from . import montee
from .commandes import ErreurCommande
from .openupgrade import VERSION_MAX, VERSION_MIN, ErreurOpenUpgrade
from .sauvegarde import ErreurSauvegarde

# Action -> champs attendus (et rien d'autre).
ACTIONS_MONTEE: dict[str, tuple[str, ...]] = {
    "creer": ("depot", "arrivee"),
    "circuit": ("montee",),
    "feu_vert": ("montee", "confirmation", "par"),
    "nouvel_essai": ("montee", "depot"),
    "livrer": ("montee",),
}
_DEPOT = re.compile(r"^[0-9a-f]{32}\.zip$")
_MONTEE = re.compile(r"^M\d{14}-[0-9a-f]{4}$")
_DEMANDE = re.compile(r"^[0-9a-f]{32}\.json$")
TEXTE_MAX = 200
JOURS_CONSERVATION = 30
# Erreurs d'une montée, rendues comme refus nommés.
ERREURS_MONTEE = (
    montee.ErreurMontee,
    ErreurCommande,
    ErreurOpenUpgrade,
    ErreurSauvegarde,
    ValueError,
    OSError,
)


class ErreurDemande(ValueError):
    """Demande mal formée : refusée sans rien exécuter."""


class Demande(TypedDict):
    """Une demande vérifiée."""

    id: str
    action: str
    valeurs: dict[str, Any]


def verifier_demande(contenu: Any) -> Demande:
    """Vérifie une demande, champ par champ.

    Rôle : seul passage entre l'interface et root ; rien d'imprévu
    n'est accepté.
    Paramètres : contenu — JSON relu ({id, action, valeurs}).
    Retour : Demande.
    Erreurs : ErreurDemande (action inconnue, champ manquant ou en trop,
    valeur mal formée).
    Usages : deposer_demande, lire_demande.
    """
    if not isinstance(contenu, dict) or set(contenu) != {
        "id",
        "action",
        "valeurs",
    }:
        raise ErreurDemande("Demande mal formée.")
    action = contenu["action"]
    valeurs = contenu["valeurs"]
    if action not in ACTIONS_MONTEE or not isinstance(valeurs, dict):
        raise ErreurDemande("Action inconnue : %r" % action)
    if not isinstance(contenu["id"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", contenu["id"]
    ):
        raise ErreurDemande("Identifiant de demande mal formé.")
    if set(valeurs) != set(ACTIONS_MONTEE[action]):
        raise ErreurDemande(
            "Champs attendus pour %s : %s."
            % (action, ", ".join(ACTIONS_MONTEE[action]))
        )
    for champ, valeur in valeurs.items():
        _verifier_valeur(champ, valeur)
    return {"id": contenu["id"], "action": action, "valeurs": valeurs}


def _verifier_valeur(champ: str, valeur: Any) -> None:
    """Refuse une valeur mal formée (ErreurDemande)."""
    if champ == "arrivee":
        bonne = isinstance(valeur, int) and VERSION_MIN < valeur <= VERSION_MAX
    elif champ == "depot":
        bonne = isinstance(valeur, str) and bool(_DEPOT.match(valeur))
    elif champ == "montee":
        bonne = isinstance(valeur, str) and bool(_MONTEE.match(valeur))
    else:
        bonne = isinstance(valeur, str) and 0 < len(valeur) <= TEXTE_MAX
    if not bonne:
        raise ErreurDemande("Valeur refusée pour %s." % champ)


def deposer_demande(dossier: str, action: str, **valeurs: Any) -> str:
    """Dépose une demande pour le service ; rend son identifiant.

    Rôle : point d'entrée de l'interface (écran Montée de version).
    Paramètres : dossier — file des demandes ; action ; valeurs.
    Retour : identifiant de la demande (nom du fichier sans .json).
    Erreurs : ErreurDemande (rien n'est déposé) ; OSError.
    Usages : interface/montees.py.
    """
    ident = uuid.uuid4().hex
    demande = verifier_demande(
        {"id": ident, "action": action, "valeurs": valeurs}
    )
    os.makedirs(dossier, exist_ok=True)
    ecrire_json_atomique(os.path.join(dossier, ident + ".json"), demande)
    return ident


def lire_demande(chemin: str) -> Demande:
    """Relit et vérifie une demande déposée. Lève ErreurDemande."""
    if not _DEMANDE.match(os.path.basename(chemin)):
        raise ErreurDemande("Fichier de demande inattendu.")
    try:
        with open(chemin, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
    except ValueError as exc:
        raise ErreurDemande("Demande illisible.") from exc
    return verifier_demande(contenu)


class Service:
    """Ce que fait le service de montée, pas à pas."""

    def __init__(
        self,
        donnees: str,
        etats: str,
        openupgrade: str = montee.CHEMIN_OPENUPGRADE,
        lanceur: montee.LanceurProgramme | None = None,
        proprietaire: tuple[int, int] | None = None,
    ) -> None:
        """Dossiers du volume chiffré (donnees) et des résumés (etats).

        `proprietaire` (uid, gid) : compte de l'interface, qui reçoit les
        sauvegardes livrées pour pouvoir les télécharger.
        """
        self.racine = os.path.join(donnees, "montees")
        self.demandes = os.path.join(donnees, "demandes")
        self.depots = os.path.join(donnees, "depots")
        self.livraisons = os.path.join(donnees, "livraisons")
        self.etats = etats
        self.openupgrade = openupgrade
        self.lanceur = lanceur
        self.proprietaire = proprietaire
        for dossier in (self.racine, self.etats):
            os.makedirs(dossier, mode=0o700, exist_ok=True)

    def traiter_file(self, journal: Journal | None = None) -> int:
        """Traite les demandes en attente, une à la fois ; rend leur nombre."""
        if not os.path.isdir(self.demandes):
            return 0
        noms = sorted(
            (
                nom
                for nom in os.listdir(self.demandes)
                if nom.endswith(".json")
            ),
            key=lambda nom: os.path.getmtime(os.path.join(self.demandes, nom)),
        )
        for nom in noms:
            self.traiter(os.path.join(self.demandes, nom), journal)
        return len(noms)

    def traiter(self, chemin: str, journal: Journal | None = None) -> None:
        """Exécute une demande et publie son résultat (fait ou refus)."""
        ident = os.path.splitext(os.path.basename(chemin))[0]
        resultat: dict[str, Any] = {"id": ident, "le": _maintenant()}
        try:
            demande = lire_demande(chemin)
            resultat["action"] = demande["action"]
            resultat["montee"] = self._executer(demande, journal)
            resultat["statut"] = "fait"
        except (ErreurDemande, *ERREURS_MONTEE) as exc:
            resultat["statut"] = "refus"
            resultat["message"] = str(exc)
        finally:
            os.remove(chemin)
        ecrire_json_atomique(
            os.path.join(self.etats, "demande-%s.json" % ident),
            resultat,
            ascii_seul=False,
        )
        if resultat.get("montee"):
            self.publier(str(resultat["montee"]))

    def _depot(self, nom: str) -> str:
        """Chemin d'une sauvegarde déposée par l'interface."""
        chemin = os.path.join(self.depots, nom)
        if not os.path.isfile(chemin):
            raise ErreurDemande("Sauvegarde déposée introuvable.")
        return chemin

    def _executer(self, demande: Demande, journal: Journal | None) -> str:
        """Lance l'action ; rend l'identifiant de la montée concernée."""
        valeurs = demande["valeurs"]
        action = demande["action"]
        if action == "creer":
            etat = montee.creer(
                self.racine,
                self._depot(valeurs["depot"]),
                valeurs["arrivee"],
                journal,
            )
            return etat["id"]
        ident = str(valeurs["montee"])
        if action == "nouvel_essai":
            montee.nouvel_essai(
                self.racine,
                ident,
                self._depot(valeurs["depot"]),
                self.openupgrade,
                self.lanceur,
                journal,
            )
            return ident
        conduite = montee.Montee(
            self.racine, ident, self.openupgrade, self.lanceur, journal
        )
        if action == "circuit":
            conduite.circuit()
        elif action == "feu_vert":
            conduite.donner_feu_vert(valeurs["confirmation"], valeurs["par"])
        else:
            livree = conduite.livrer()
            os.makedirs(self.livraisons, exist_ok=True)
            copie = os.path.join(self.livraisons, os.path.basename(livree))
            shutil.copy2(livree, copie)
            if self.proprietaire is not None:
                os.chown(copie, *self.proprietaire)
        return ident

    def publier(self, ident: str) -> None:
        """Résumé d'une montée pour l'écran, sans la base du client."""
        etat: dict[str, Any] = dict(montee.charger(self.racine, ident))
        inventaire = os.path.join(self.racine, ident, "inventaire.json")
        if os.path.isfile(inventaire):
            with open(inventaire, encoding="utf-8") as fichier:
                etat["inventaire"] = json.load(fichier)
        ecrire_json_atomique(
            os.path.join(self.etats, "%s.json" % ident), etat, ascii_seul=False
        )

    def purger(self, maintenant: datetime | None = None) -> list[str]:
        """Efface les montées de plus de 30 jours ; rend leurs identifiants.

        Délai compté depuis la livraison, ou depuis le dernier changement
        pour une montée jamais livrée. Une montée en cours n'est jamais
        effacée.
        """
        limite = (maintenant or datetime.now()) - timedelta(
            days=JOURS_CONSERVATION
        )
        effacees = []
        for ident in sorted(os.listdir(self.racine)):
            dossier = os.path.join(self.racine, ident)
            etat = montee.charger(self.racine, ident)
            if etat["statut"] == montee.EN_COURS:
                continue
            livraison = etat["etapes"]["livraison"].get("infos", {}).get("le")
            repere = (
                datetime.fromisoformat(livraison)
                if livraison
                else datetime.fromtimestamp(
                    os.path.getmtime(os.path.join(dossier, "montee.json"))
                )
            )
            if repere < limite:
                montee.Montee(
                    self.racine, ident, lanceur=self.lanceur
                ).arreter()
                shutil.rmtree(dossier)
                for public in (
                    os.path.join(self.etats, ident + ".json"),
                    os.path.join(
                        self.livraisons,
                        "%s_odoo%d.zip"
                        % (etat["base_client"], etat["arrivee"]),
                    ),
                ):
                    if os.path.exists(public):
                        os.remove(public)
                effacees.append(ident)
        return effacees


def _maintenant() -> str:
    """Date et heure, à la seconde."""
    return datetime.now().isoformat(timespec="seconds")
