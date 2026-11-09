# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écran « Compléter SIRET et TVA » (ADR-0013).

Depuis le constat « Sociétés françaises sans SIREN ni TVA » d'une analyse,
propositions de l'annuaire public de l'État (tâche « siret_proposer »),
puis le circuit commun des écrans de tiers (interface/tiers.py). Seuls un
SIRET et une TVA proposés par l'annuaire peuvent être écrits : rien n'est
saisi à la main.
"""

import json
from collections.abc import Mapping
from typing import Any

from core.guardian import Guardian
from core.journal import Journal
from core.tiers_odoo import AccesOdoo
from core.tiers_siret import (
    Choix,
    ErreurSiret,
    Proposition,
    ecrire,
    identifiants_constat,
    lire_tiers,
    proposer,
)
from interface.tiers import (
    ERREURS_TIERS,
    NOM_PROPOSITIONS,
    EcranTiers,
    ObjetJson,
    compter_classes,
)
from interface.transferts import ErreurEcran, texte_corps

CONSTAT_TIERS = "TIERS_SANS_SIREN_TVA"
# Refus de l'écran SIRET, rendus au navigateur avec leur cause.
ERREURS_SIRET = (*ERREURS_TIERS, ErreurSiret)


class EcranSiret(EcranTiers):
    """Compléter SIRET et TVA : propositions, essai, feu vert, annulation."""

    prefixe = "siret"
    action_preparer = "siret_proposer"
    titre = "SIRET et TVA"

    def lancer_propositions(self, corps: Mapping[str, Any]) -> str:
        """Lance les propositions pour le constat d'une analyse.

        Corps : analyse (tâche d'analyse terminée), production (base à
        compléter) et test (sa copie de test). Lève ErreurEcran.
        """
        analyse = texte_corps(corps, "analyse")
        rapport = self.taches.rapport(analyse)
        if rapport is None:
            raise ErreurEcran("Analyse inconnue ou pas terminée.")
        with open(rapport, encoding="utf-8") as fichier:
            constats = json.load(fichier)["constats"]
        constat = next(
            (
                un_constat
                for un_constat in constats
                if un_constat["code"] == CONSTAT_TIERS
            ),
            None,
        )
        if constat is None:
            raise ErreurEcran(
                "Cette analyse ne signale aucun tiers à compléter."
            )
        production, test = self.couple(corps)
        return self.taches.lancer(
            self.action_preparer,
            None,
            "%s — %s" % (self.libelle_source(production), self.titre),
            "",
            {
                "analyse": analyse,
                "production": production,
                "test": test,
                "identifiants": identifiants_constat(constat["elements"]),
            },
        )

    def _travail_preparer(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « siret_proposer » : tiers relus, annuaire, contrôles."""
        parametres = tache["params"]
        tiers = lire_tiers(
            self.acces(parametres["production"]), parametres["identifiants"]
        )
        journal.dire(
            "%d tiers à compléter sur %d signalés (les autres le sont déjà)"
            % (len(tiers), len(parametres["identifiants"])),
            "etape",
        )
        propositions = proposer(tiers)
        self.enregistrer(tache, list(propositions))
        comptes = compter_classes(list(propositions))
        guardian.tracer(self.prefixe, "propositions", json.dumps(comptes))
        tache["resultat"] = {"tiers": len(tiers), "classes": comptes}

    def choix_valides(self, ident: str, recus: object) -> list[Any]:
        """Choix reçus, acceptés seulement s'ils viennent des propositions."""
        propositions: list[Proposition] = (
            self.lire(self.fichier(ident, NOM_PROPOSITIONS)) or []
        )
        par_tiers = {
            proposition_tiers["tiers"]["id"]: proposition_tiers
            for proposition_tiers in propositions
        }
        if not isinstance(recus, list) or not recus:
            raise ErreurEcran("Aucun tiers choisi.")
        choix: list[Choix] = []
        for recu in recus:
            if not isinstance(recu, dict):
                raise ErreurEcran("Choix mal formé.")
            ident_tiers = recu.get("id")
            proposition_tiers = (
                par_tiers.get(ident_tiers)
                if isinstance(ident_tiers, int)
                else None
            )
            siret = str(recu.get("siret") or "")
            tva = str(recu.get("tva") or "")
            if proposition_tiers is None or not any(
                possible["siret"] == siret and tva in ("", possible["tva"])
                for possible in proposition_tiers["candidates"]
            ):
                raise ErreurEcran(
                    "Choix refusé pour le tiers %s : il ne vient pas des "
                    "propositions de l'annuaire." % recu.get("id")
                )
            choix.append(
                {
                    "id": proposition_tiers["tiers"]["id"],
                    "siret": siret,
                    "tva": tva,
                }
            )
        return sorted(choix, key=lambda un_choix: un_choix["id"])

    def ecrire_choix(
        self, cible: AccesOdoo, choix: list[Any], base: str, trace: str
    ) -> dict[str, Any]:
        """Écrit SIRET et TVA (contrôles refaits) ; rend le bilan."""
        return ecrire(cible, choix, base, trace)

    def propositions(self, ident: str) -> ObjetJson:
        """Propositions, connexions et essai sur la copie de test."""
        return self.resultats(ident)
