# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de « Facture électronique des tiers » (ADR-0014).

Répertoire Peppol et Odoo simulés : aucune requête ne sort du test. Les
réponses du répertoire reprennent la forme mesurée le 09/11/2026.
"""

import http.client
import os
import tempfile
import unittest
from typing import Any
from unittest import mock

from core.tiers_peppol import (
    INSCRIT,
    NON_TROUVE,
    SANS_SIREN,
    ErreurPeppol,
    adresse_proposee,
    adresses_peppol,
    ecrire_adresses,
    lire_tiers_facturation,
    verifier,
)
from tests import test_tiers_siret
from tests.test_tiers_siret import FauxOdoo

FACTURE_UBL = (
    "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn"
)
AVOIR_UBL = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::X"
FACTURE_CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"


def participant(valeur: str, *documents: str) -> dict[str, Any]:
    """Une réponse du répertoire pour un participant."""
    return {
        "participantID": {"scheme": "iso6523-actorid-upis", "value": valeur},
        "docTypes": [{"value": document} for document in documents],
        "entities": [{"countryCode": "FR", "regDate": "2026-07-03"}],
    }


REPONSES = {
    "111111118": [
        participant("0002:111111118", FACTURE_UBL, AVOIR_UBL),
        participant("0225:111111118", FACTURE_UBL, FACTURE_CII),
        participant("0225:999999999", FACTURE_UBL),
    ],
    "222222226": [
        participant("0225:222222226_routage1", FACTURE_UBL),
        participant("0009:22222222600029", FACTURE_UBL),
        participant("0009:222222226abc", FACTURE_UBL),
        participant("9957:FR46222222226", FACTURE_UBL),
    ],
}


class FauxRepertoire:
    """Répertoire Peppol simulé : réponses par SIREN cherché."""

    def __init__(self) -> None:
        """Aucun appel au départ."""
        self.appels: list[str] = []

    def requete(
        self,
        methode: str,
        chemin: str,
        parametres: Any = None,
        corps: object = None,
    ) -> dict[str, Any]:
        """GET /search/1.0/json?q=<SIREN>."""
        self.appels.append(str(parametres["q"]))
        return {"matches": REPONSES.get(str(parametres["q"]), [])}


class FauxOdooFacturation(FauxOdoo):
    """Odoo simulé avec clients, fournisseurs et champs Peppol."""

    def __init__(self, peppol: bool = True) -> None:
        """Quatre tiers : inscrit, à routage, non trouvé, sans SIREN."""
        super().__init__()
        self.peppol = peppol
        self.fiches = {
            1: {"name": "TIERS UN", "company_registry": "111111118"},
            2: {"name": "EXEMPLE", "vat": "FR46222222226"},
            3: {"name": "TIERS TROIS", "siret": "33333333400048"},
            4: {"name": "SANS SIREN"},
            5: {
                "name": "DEJA",
                "company_registry": "111111118",
                "peppol_eas": "0225",
                "peppol_endpoint": "111111118",
            },
        }
        for fiche in self.fiches.values():
            for champ in (
                "vat",
                "company_registry",
                "siret",
                "peppol_eas",
                "peppol_endpoint",
            ):
                fiche.setdefault(champ, False)
            fiche["customer_rank"] = 1
            fiche["supplier_rank"] = 0

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Ajoute fields_get des champs Peppol et search_read paginé."""
        options = kwargs or {}
        if methode == "fields_get":
            champs: dict[str, Any] = {"siret": {"type": "char"}}
            if self.peppol:
                champs["peppol_eas"] = {
                    "type": "selection",
                    "selection": [["0002", "SIRENE"], ["0225", "SIREN FR"]],
                }
                champs["peppol_endpoint"] = {"type": "char"}
            return champs
        if methode == "search_read":
            debut = options["offset"]
            fin = debut + options["limit"]
            identifiants = sorted(self.fiches)[debut:fin]
            return [
                dict(
                    {
                        nom: self.fiches[ident][nom]
                        for nom in options["fields"]
                    },
                    id=ident,
                )
                for ident in identifiants
            ]
        return super().appel(modele, methode, args, kwargs)


class TestReglesPeppol(unittest.TestCase):
    """Lecture du répertoire, classement, écriture."""

    def test_adresses_et_proposition(self) -> None:
        """Vérifie le filtre par SIREN, les documents et l'adresse proposée."""
        adresses_tiers_un = adresses_peppol(
            {"matches": REPONSES["111111118"]}, "111111118"
        )
        self.assertEqual(
            [
                (adresse["schema"], adresse["identifiant"])
                for adresse in adresses_tiers_un
            ],
            [("0002", "111111118"), ("0225", "111111118")],
        )
        self.assertEqual(
            adresses_tiers_un[1]["documents"],
            ["facture UBL", "facture CII (Factur-X)"],
        )
        self.assertEqual(
            adresse_proposee(adresses_tiers_un), adresses_tiers_un[1]
        )
        adresses_exemple = adresses_peppol(
            {"matches": REPONSES["222222226"]}, "222222226"
        )
        self.assertEqual(
            [adresse["identifiant"] for adresse in adresses_exemple],
            ["22222222600029", "222222226_routage1"],
        )
        self.assertIsNone(adresse_proposee(adresses_exemple))

    def test_verifier_tous_les_tiers(self) -> None:
        """Vérifie les trois classes et un seul appel par SIREN."""
        with mock.patch("core.tiers_peppol.LOT_TIERS", 2):
            tiers = lire_tiers_facturation(FauxOdooFacturation())
        self.assertEqual(
            [un_tiers["siren"] for un_tiers in tiers],
            ["111111118", "222222226", "333333334", "", "111111118"],
        )
        self.assertEqual(tiers[4]["adresse_actuelle"], "0225:111111118")
        repertoire = FauxRepertoire()
        resultats = verifier(tiers, repertoire, lambda duree: None)
        self.assertEqual(
            [resultat["classe"] for resultat in resultats],
            [INSCRIT, INSCRIT, NON_TROUVE, SANS_SIREN, INSCRIT],
        )
        self.assertEqual(
            repertoire.appels, ["111111118", "222222226", "333333334"]
        )

    def test_ecrire_adresses(self) -> None:
        """Vérifie l'écriture, la fiche déjà renseignée et les refus."""
        choix = [
            {"id": 1, "schema": "0225", "identifiant": "111111118"},
            {"id": 5, "schema": "0225", "identifiant": "111111118"},
        ]
        with tempfile.TemporaryDirectory() as dossier:
            trace = os.path.join(dossier, "t.jsonl")
            with self.assertRaises(ErreurPeppol):
                ecrire_adresses(
                    FauxOdooFacturation(peppol=False), choix, "b", trace
                )
            with self.assertRaises(ErreurPeppol):
                ecrire_adresses(
                    FauxOdooFacturation(),
                    [
                        {
                            "id": 2,
                            "schema": "0009",
                            "identifiant": "22222222600029",
                        }
                    ],
                    "b",
                    trace,
                )
            odoo = FauxOdooFacturation()
            bilan = ecrire_adresses(odoo, choix, "base", trace)
        self.assertEqual((bilan["ecrits"], bilan["ignores"]), ([1], [5]))
        self.assertEqual(
            (odoo.fiches[1]["peppol_eas"], odoo.fiches[1]["peppol_endpoint"]),
            ("0225", "111111118"),
        )


class TestEcranPeppol(test_tiers_siret.TestEcranSiret):
    """Parcours HTTP : vérification, CSV, essai, feu vert, annulation."""

    def setUp(self) -> None:
        """Mêmes connexions que l'écran SIRET ; Odoo de facturation simulé."""
        super().setUp()
        self.odoo = {
            self.test: FauxOdooFacturation(),
            self.prod: FauxOdooFacturation(),
        }
        remplacement = mock.patch(
            "core.tiers_peppol.ClientJson", lambda *arguments: FauxRepertoire()
        )
        remplacement.start()
        self.addCleanup(remplacement.stop)

    def test_parcours(self) -> None:
        """Vérifie la vérification, le CSV, l'essai et le feu vert."""
        self.assertIn(
            "autre base",
            self.refus(
                "/api/peppol",
                dict(self.couple, test=self.couple["production"]),
            ),
        )
        etat = self.tache("/api/peppol", dict(self.couple))
        self.assertEqual(etat["statut"], "terminee", etat.get("erreur"))
        self.assertEqual(
            etat["resultat"]["classes"],
            {INSCRIT: 3, NON_TROUVE: 1, SANS_SIREN: 1},
        )
        ident = etat["id"]
        _, donnees = self.envoyer("GET", "/api/peppol/" + ident)
        self.assertEqual(len(donnees["propositions"]), 5)
        statut, disposition, contenu = self.telecharger(
            "/api/peppol/%s/csv" % ident
        )
        self.assertEqual(statut, 200)
        self.assertIn("facture_electronique", disposition)
        self.assertIn("non trouvé (à vérifier)", contenu)
        choix = [{"id": 1, "schema": "0225", "identifiant": "111111118"}]
        self.assertIn(
            "pas été trouvée",
            self.refus(
                "/api/peppol/%s/ecrire" % ident,
                {
                    "cible": "test",
                    "choix": [{"id": 1, "schema": "0225", "identifiant": "1"}],
                },
            ),
        )
        essai = self.tache(
            "/api/peppol/%s/ecrire" % ident, {"cible": "test", "choix": choix}
        )
        self.assertEqual(essai["resultat"]["ecrits"], [1])
        prod = self.tache(
            "/api/peppol/%s/ecrire" % ident,
            {
                "cible": "production",
                "choix": choix,
                "confirmation": "Client A production",
            },
        )
        self.assertEqual(prod["resultat"]["ecrits"], [1])
        self.assertEqual(
            self.odoo[self.prod].fiches[1]["peppol_endpoint"], "111111118"
        )
        annule = self.tache(
            "/api/peppol/%s/annuler" % ident, {"cible": "production"}
        )
        self.assertEqual(annule["resultat"]["remis"], [1])
        self.assertEqual(self.telecharger("/api/peppol/inconnue/csv")[0], 404)
        self.assertEqual(self.telecharger("/api/siret/x/csv")[0], 404)

    def telecharger(self, chemin: str) -> tuple[int, str, str]:
        """GET d'un fichier ; rend statut, Content-Disposition et texte."""
        connexion = http.client.HTTPConnection(
            "127.0.0.1", self.serveur.server_address[1], timeout=10
        )
        connexion.request("GET", chemin, headers={"Cookie": self.cookie})
        reponse = connexion.getresponse()
        contenu = reponse.read().decode("utf-8", "replace")
        connexion.close()
        return (
            reponse.status,
            str(reponse.getheader("Content-Disposition") or ""),
            contenu,
        )

    def test_refus(self) -> None:
        """Les refus communs sont déjà vérifiés par l'écran SIRET."""
        reponse, _ = self.envoyer("POST", "/api/peppol/x/inconnue", {})
        self.assertEqual(reponse.status, 404)
        self.assertIn("Aucun tiers", self.refus_choix_vide())

    def refus_choix_vide(self) -> str:
        """Choix vide sur adresse vérification simulée terminée."""
        ident = "verification-simulee"
        self.app.taches._taches[ident] = {
            "id": ident,
            "action": "peppol_verifier",
            "statut": "terminee",
            "params": dict(self.couple),
            "fichiers": [],
        }
        return self.refus(
            "/api/peppol/%s/ecrire" % ident, {"cible": "test", "choix": []}
        )
