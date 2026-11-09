# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écran Montée de version (ADR-0011 point 7, ADR-0012).

L'interface n'a pas accès à Docker ni aux bases des clients. Elle :
- reçoit la sauvegarde Odoo (.zip) dans le dossier des dépôts du volume
  chiffré, et la relit tout de suite (version, base, taille) ;
- dépose des demandes vérifiées dans la file du service de montée ;
- lit les résumés publiés par ce service, et les sauvegardes livrées.
Le client ne voit jamais le nom de l'outil de migration (ADR-0011).
"""

import json
import os
import re
import uuid
from collections.abc import Mapping
from typing import Any

from core.journal import Journal
from core.montee_version.demandes import ErreurDemande, deposer_demande
from core.montee_version.openupgrade import VERSION_MAX, VERSION_MIN
from core.montee_version.sauvegarde import (
    ErreurSauvegarde,
    examiner_sauvegarde,
)
from interface.transferts import (
    ErreurEcran,
    FluxEntrant,
    chemin_dans,
    recevoir_fichier,
    taille_depot_max,
    texte_corps,
)

# Objet JSON échangé avec le navigateur (comme dans interface/serveur.py).
ObjetJson = dict[str, Any]

DONNEES_MONTEE = os.environ.get(
    "CONCORDE_MONTEE_DONNEES", "/var/lib/concorde-montee/donnees"
)
ETATS_MONTEE = os.environ.get(
    "CONCORDE_MONTEE_ETATS", "/var/lib/concorde-montee/etats"
)
SAUVEGARDE_MAX_MO_DEFAUT = 4096
_MONTEE = re.compile(r"^M\d{14}-[0-9a-f]{4}$")
_JETON_DEPOT = re.compile(r"^[0-9a-f]{32}\.zip$")
_IDENT_DEMANDE = re.compile(r"^[0-9a-f]{32}$")
# Refus de l'écran Montée, rendus au navigateur avec leur cause.
ERREURS_MONTEE_ECRAN = (
    ErreurEcran,
    ErreurDemande,
    ErreurSauvegarde,
    ValueError,
)


class EcranMontees:
    """Ce que fait l'écran Montée de version, par la file de demandes."""

    def __init__(
        self,
        journal: Journal,
        donnees: str = DONNEES_MONTEE,
        etats: str = ETATS_MONTEE,
        environnement: Mapping[str, str] | None = None,
    ) -> None:
        """Dossiers du service de montée ; plafond des sauvegardes.

        Lève ValueError si CONCORDE_MONTEE_DEPOT_MAX_MO est invalide.
        """
        self.journal = journal
        self.depots = os.path.join(donnees, "depots")
        self.demandes = os.path.join(donnees, "demandes")
        self.livraisons = os.path.join(donnees, "livraisons")
        self.etats = etats
        self.depot_max = taille_depot_max(
            os.environ if environnement is None else environnement,
            "CONCORDE_MONTEE_DEPOT_MAX_MO",
            SAUVEGARDE_MAX_MO_DEFAUT,
        )

    def _pret(self) -> None:
        """Refuse si le service de montée n'a pas ouvert son volume."""
        if not os.path.isdir(self.demandes) or not os.access(
            self.demandes, os.W_OK
        ):
            raise ErreurEcran(
                "Le service de montée n'est pas prêt (volume chiffré fermé "
                "ou service non installé : deploy/installer_montee.sh)."
            )

    def etat(self) -> ObjetJson:
        """Service prêt ou non, plafond, versions, montées et demandes."""
        try:
            self._pret()
            pret, cause = True, ""
        except ErreurEcran as exc:
            pret, cause = False, str(exc)
        return {
            "pret": pret,
            "cause": cause,
            "depot_max": self.depot_max,
            "versions": list(range(VERSION_MIN + 1, VERSION_MAX + 1)),
            "montees": self.lister(),
            "en_attente": (
                sorted(
                    nom[:-5]
                    for nom in os.listdir(self.demandes)
                    if nom.endswith(".json")
                )
                if pret
                else []
            ),
        }

    def lister(self) -> list[ObjetJson]:
        """Résumés publiés des montées, plus récente d'abord."""
        if not os.path.isdir(self.etats):
            return []
        montees = []
        for nom in sorted(os.listdir(self.etats), reverse=True):
            if _MONTEE.match(nom[:-5]) and nom.endswith(".json"):
                with open(
                    os.path.join(self.etats, nom), encoding="utf-8"
                ) as fichier:
                    montees.append(json.load(fichier))
        return montees

    def resultat_demande(self, ident: str) -> ObjetJson:
        """Résultat d'une demande : fait, refus (cause) ou en attente."""
        if not _IDENT_DEMANDE.match(ident):
            raise ErreurEcran("Demande inconnue.")
        chemin = os.path.join(self.etats, "demande-%s.json" % ident)
        if not os.path.isfile(chemin):
            return {"id": ident, "statut": "en_attente"}
        with open(chemin, encoding="utf-8") as fichier:
            resultat: ObjetJson = json.load(fichier)
        return resultat

    def deposer(self, nom: str, flux: FluxEntrant, taille: int) -> ObjetJson:
        """Reçoit une sauvegarde Odoo (.zip) et la relit ; rend son résumé.

        Un fichier refusé n'est pas gardé.
        Lève ErreurEcran, ErreurSauvegarde ou OSError.
        """
        self._pret()
        jeton = uuid.uuid4().hex + ".zip"
        chemin = os.path.join(self.depots, jeton)
        recevoir_fichier(flux, taille, chemin, self.depot_max)
        try:
            info = examiner_sauvegarde(chemin)
            if info["version"] is None:
                raise ErreurSauvegarde(
                    "Version d'Odoo absente (manifest.json) : faire la "
                    "sauvegarde depuis le gestionnaire de bases d'Odoo."
                )
        except ErreurSauvegarde:
            os.remove(chemin)
            raise
        self.journal.dire(
            "Sauvegarde Odoo déposée : %s (Odoo %s)"
            % (os.path.basename(nom)[:120], info["version"]),
            "info",
        )
        return {
            "jeton": jeton,
            "nom": os.path.basename(nom)[:200],
            "version": info["version"],
            "base": info["base"],
            "octets": info["octets"],
            "octets_decompresses": info["octets_decompresses"],
            "pieces_jointes": info["pieces_jointes"],
        }

    def demander(
        self, action: str, corps: Mapping[str, Any], ident: str | None, ip: str
    ) -> ObjetJson:
        """Dépose une demande au service ; rend son identifiant.

        Actions : creer (depot, arrivee), circuit, feu_vert (confirmation),
        nouvel_essai (depot), livrer.
        Lève ErreurEcran ou ErreurDemande (rien n'est déposé).
        """
        self._pret()
        valeurs: dict[str, Any] = {}
        if ident is not None:
            valeurs["montee"] = ident
        if action in ("creer", "nouvel_essai"):
            depot = texte_corps(corps, "depot")
            if not _JETON_DEPOT.match(depot) or not os.path.isfile(
                os.path.join(self.depots, depot)
            ):
                raise ErreurEcran("Sauvegarde déposée inconnue : déposez-la.")
            valeurs["depot"] = depot
        if action == "creer":
            arrivee = corps.get("arrivee")
            valeurs["arrivee"] = arrivee if isinstance(arrivee, int) else 0
        if action == "feu_vert":
            valeurs["confirmation"] = texte_corps(corps, "confirmation")
            valeurs["par"] = "session de l'interface depuis %s" % ip
        demande = deposer_demande(self.demandes, action, **valeurs)
        self.journal.dire(
            "Montée de version : demande %s%s"
            % (action, " " + ident if ident else ""),
            "alerte" if action in ("feu_vert", "livrer") else "info",
        )
        return {"demande": demande}

    def livraison(self, ident: str) -> str:
        """Chemin de la sauvegarde livrée d'une montée. Lève ErreurEcran."""
        resume = next(
            (montee for montee in self.lister() if montee["id"] == ident), None
        )
        infos = (
            (resume or {}).get("etapes", {}).get("livraison", {}).get("infos")
        )
        if not infos:
            raise ErreurEcran("Aucune sauvegarde livrée pour cette montée.")
        chemin = os.path.join(self.livraisons, str(infos["fichier"]))
        if not chemin_dans(self.livraisons, chemin) or not os.path.isfile(
            chemin
        ):
            raise ErreurEcran("Sauvegarde livrée introuvable.")
        return chemin
