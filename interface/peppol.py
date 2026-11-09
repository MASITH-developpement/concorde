# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écran « Facture électronique des tiers » (ADR-0014).

Vérification (tâche « peppol_verifier ») : tous les clients et fournisseurs
d'une connexion Odoo, cherchés par SIREN dans le répertoire Peppol public ;
inscrit, non trouvé (à vérifier) ou sans SIREN ; liste en CSV. Puis le
circuit commun des écrans de tiers (interface/tiers.py) pour reprendre
l'adresse choisie dans l'ERP. Seule une adresse trouvée sur Peppol pour ce
tiers peut être écrite.
"""

import csv
import io
import json
from collections.abc import Mapping
from typing import Any

from core.guardian import Guardian
from core.journal import Journal
from core.tiers_odoo import AccesOdoo, CibleTiers
from core.tiers_peppol import (
    ErreurPeppol,
    Verification,
    ecrire_adresses,
    lire_tiers_facturation,
    verifier,
)
from interface.tiers import (
    ERREURS_TIERS,
    NOM_PROPOSITIONS,
    EcranTiers,
    ObjetJson,
    compter_classes,
)
from interface.transferts import ErreurEcran, texte_corps

# Refus de l'écran Facture électronique, rendus avec leur cause.
ERREURS_PEPPOL = (*ERREURS_TIERS, ErreurPeppol)
CLASSES_CSV = {
    "inscrit": "inscrit",
    "non_trouve": "non trouvé (à vérifier)",
    "sans_siren": "sans SIREN",
}


class EcranPeppol(EcranTiers):
    """Facture électronique des tiers : vérifier, puis reprendre l'adresse."""

    prefixe = "peppol"
    action_preparer = "peppol_verifier"
    titre = "facture électronique des tiers"

    def lancer_verification(self, corps: Mapping[str, Any]) -> str:
        """Lance la vérification de tous les tiers d'une connexion Odoo.

        Corps : connexion (Odoo, avec une connexion de test). Lève
        ErreurEcran.
        """
        fiche = self.connexion_avec_test(texte_corps(corps, "connexion"))
        return self.taches.lancer(
            self.action_preparer,
            None,
            "%s — %s" % (fiche["libelle"], self.titre),
            "",
            {"connexion": fiche["id"]},
        )

    def _travail_preparer(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « peppol_verifier » : tiers lus, répertoire Peppol."""
        cible = self.connecteur(tache["params"]["connexion"]).cible(CibleTiers)
        tiers = lire_tiers_facturation(cible)
        journal.dire(
            "%d clients et fournisseurs à vérifier" % len(tiers), "etape"
        )
        resultats = verifier(tiers)
        self.enregistrer(tache, list(resultats))
        comptes = compter_classes(list(resultats))
        guardian.tracer(self.prefixe, "verification", json.dumps(comptes))
        tache["resultat"] = {"tiers": len(tiers), "classes": comptes}

    def choix_valides(self, ident: str, recus: object) -> list[Any]:
        """Choix reçus, acceptés seulement s'ils viennent de Peppol."""
        resultats: list[Verification] = (
            self.lire(self.fichier(ident, NOM_PROPOSITIONS)) or []
        )
        par_tiers = {
            resultat_tiers["tiers"]["id"]: resultat_tiers
            for resultat_tiers in resultats
        }
        if not isinstance(recus, list) or not recus:
            raise ErreurEcran("Aucun tiers choisi.")
        choix: list[dict[str, Any]] = []
        for recu in recus:
            if not isinstance(recu, dict):
                raise ErreurEcran("Choix mal formé.")
            ident_tiers = recu.get("id")
            resultat_tiers = (
                par_tiers.get(ident_tiers)
                if isinstance(ident_tiers, int)
                else None
            )
            schema = str(recu.get("schema") or "")
            identifiant = str(recu.get("identifiant") or "")
            if resultat_tiers is None or not any(
                adresse["schema"] == schema
                and adresse["identifiant"] == identifiant
                for adresse in resultat_tiers["adresses"]
            ):
                raise ErreurEcran(
                    "Choix refusé pour le tiers %s : cette adresse n'a pas "
                    "été trouvée sur Peppol pour lui." % recu.get("id")
                )
            choix.append(
                {
                    "id": resultat_tiers["tiers"]["id"],
                    "schema": schema,
                    "identifiant": identifiant,
                }
            )
        return sorted(choix, key=lambda un_choix: un_choix["id"])

    def ecrire_choix(
        self, cible: AccesOdoo, choix: list[Any], base: str, trace: str
    ) -> dict[str, Any]:
        """Écrit l'adresse Peppol choisie ; rend le bilan."""
        return ecrire_adresses(cible, choix, base, trace)

    def export_csv(self, ident: str) -> bytes:
        """Résultat de la vérification en CSV (séparateur ;, UTF-8)."""
        self.tache_preparee(ident)
        resultats: list[Verification] = (
            self.lire(self.fichier(ident, NOM_PROPOSITIONS)) or []
        )
        tampon = io.StringIO()
        ecrivain = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
        ecrivain.writerow(
            [
                "Tiers",
                "Id Odoo",
                "SIREN",
                "Client",
                "Fournisseur",
                "Facture électronique",
                "Adresses Peppol",
                "Inscrit le",
                "Adresse dans Odoo",
            ]
        )
        for resultat_tiers in resultats:
            tiers = resultat_tiers["tiers"]
            adresses = resultat_tiers["adresses"]
            ecrivain.writerow(
                [
                    tiers["nom"],
                    tiers["id"],
                    tiers["siren"],
                    "oui" if tiers["client"] else "",
                    "oui" if tiers["fournisseur"] else "",
                    CLASSES_CSV.get(resultat_tiers["classe"], ""),
                    " | ".join(
                        "%s:%s" % (adresse["schema"], adresse["identifiant"])
                        for adresse in adresses
                    ),
                    min(
                        (adresse["inscrit_le"] for adresse in adresses),
                        default="",
                    ),
                    tiers["adresse_actuelle"],
                ]
            )
        return ("﻿" + tampon.getvalue()).encode("utf-8")
