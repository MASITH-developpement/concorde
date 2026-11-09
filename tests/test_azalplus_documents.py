# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Devis et rapport dans AzalPlus (ADR-0015) : ce qui part, ce qui ne part
pas, et ce qui est refusé en le nommant."""

import json
import os
import tempfile
import unittest
from datetime import date
from typing import Any
from urllib.parse import parse_qsl

from core.azalplus_documents import (
    CLIENT_ABSENT_CREER,
    EmetteurAzalPlus,
    ErreurAzalPlusDocuments,
    MissionAzalPlus,
    emettre_sans_bloquer,
    reglages_azalplus,
    siren_normalise,
)
from core.connecteurs.base import ErreurConnexion

CLIENT_TEST = {
    "id": "c1",
    "name": "DUPONT SARL",
    "registration_number": "123456789",
}
PRODUIT_TEST = {
    "id": "p1",
    "code": "PRD-00007",
    "name": "Reprise comptable CONCORDE",
    "unit": "forfait",
    "sale_price": "900.00",
    "tax_rate": "20.00",
}
PRODUIT_ECRITURE = {
    "id": "p2",
    "code": "PRD-00099",
    "name": "Écriture reprise",
    "unit": "écriture",
    "sale_price": "0.12",
    "tax_rate": "20.00",
}


def mission_test(
    genre: str = "transfert",
    siren: str = "123 456 789",
    mesures: dict[str, int] | None = None,
    fichiers: list[str] | None = None,
) -> MissionAzalPlus:
    """Une mission terminée, telle que CONCORDE la décrit."""
    return MissionAzalPlus(
        genre=genre,
        reference="CONCORDE/T-2026-001",
        siren=siren,
        societe="DUPONT SARL",
        intitule="Reprise Quadra vers Odoo 17",
        resume="1 869 lignes, 913 écritures, équilibre 0,00 €.",
        mesures=(
            {"ecritures": 913, "journaux": 4} if mesures is None else mesures
        ),
        fichiers=[] if fichiers is None else fichiers,
    )


class FauxAzalPlus:
    """AzalPlus de bureau : répond comme /api/v1 et note ce qu'on demande."""

    def __init__(
        self,
        clients: list[dict[str, Any]] | None = None,
        produits: list[dict[str, Any]] | None = None,
    ) -> None:
        self.base_clients = [dict(CLIENT_TEST)] if clients is None else clients
        self.base_produits = (
            [dict(PRODUIT_TEST), dict(PRODUIT_ECRITURE)]
            if produits is None
            else produits
        )
        self.appels: list[tuple[str, str, dict[str, str]]] = []
        self.entetes: list[dict[str, str]] = []
        self.corps: list[Any] = []
        self.status = 200
        self._brut = b"{}"

    def ouvrir(
        self, hote: str, port: int | None, delai: float
    ) -> "FauxAzalPlus":
        """Fabrique de connexion passée à ClientJson."""
        self.hote, self.port = hote, port
        return self

    def request(
        self,
        methode: str,
        url: str,
        body: bytes | None = None,
        headers: Any = None,
    ) -> None:
        """Enregistre l'appel et prépare la réponse."""
        chemin, _separateur, requete = url.partition("?")
        self.appels.append((methode, chemin, dict(parse_qsl(requete))))
        self.entetes.append(dict(headers or {}))
        self.corps.append(
            json.loads(body.decode("utf-8"))
            if body
            and not str(self.entetes[-1].get("Content-Type", "")).startswith(
                "multipart"
            )
            else body
        )
        self.status, self._brut = self._repondre(methode, chemin)

    def _repondre(self, methode: str, chemin: str) -> tuple[int, bytes]:
        """La réponse d'AzalPlus pour cet appel."""
        reponses: dict[tuple[str, str], tuple[int, object]] = {
            ("GET", "/api/v1/clients"): (200, {"data": self.base_clients}),
            ("GET", "/api/v1/produits"): (200, {"data": self.base_produits}),
            ("POST", "/api/v1/clients"): (
                201,
                {"data": {"id": "cneuf", "name": "NOUVEAU"}},
            ),
            ("POST", "/api/v1/devis"): (
                201,
                {"data": {"id": "d1", "number": "DEV-00042"}},
            ),
            ("POST", "/api/v1/ged"): (201, {"data": {"id": "g1"}}),
            ("POST", "/api/v1/ged/upload"): (201, {"data": {"id": "g2"}}),
        }
        statut, valeur = reponses.get((methode, chemin), (404, {}))
        return statut, json.dumps(valeur).encode("utf-8")

    def getresponse(self) -> "FauxAzalPlus":
        """La réponse (le faux sert de connexion et de réponse)."""
        return self

    def read(self) -> bytes:
        """Corps de la réponse."""
        return self._brut

    def getheader(self, name: str) -> str | None:
        """Aucun en-tête de réponse."""
        return None

    def close(self) -> None:
        """Rien à fermer."""

    def demandes(self, methode: str, chemin: str) -> int:
        """Combien de fois cet appel a été fait."""
        return sum(
            1
            for vu_methode, vu_chemin, _parametres in self.appels
            if (vu_methode, vu_chemin) == (methode, chemin)
        )


def reglages_test(**autres: Any) -> dict[str, Any]:
    """Réglages d'émission, tous verrous ouverts sauf mention contraire."""
    reglages: dict[str, Any] = {
        "actif": True,
        "essai_a_blanc": False,
        "adresse": "https://azalplus.test",
        "societe_emettrice": "",
        "client_absent": "refus",
        "rapport": "ged",
        "type_rapport": "RAPPORT",
        "statut_devis": "BROUILLON",
        "declencheurs": {
            "transfert": True,
            "montee_version": False,
            "controle_demat": False,
        },
        "prestations": {
            "transfert": [
                {"produit": "PRD-00007", "quantite": "forfait"},
            ],
            "montee_version": [],
            "controle_demat": [],
        },
    }
    reglages.update(autres)
    return reglages


class TestEmissionAzalPlus(unittest.TestCase):
    """Les verrous, les refus nommés et l'émission réelle."""

    def setUp(self) -> None:
        """Un faux AzalPlus et un registre jetable par test."""
        self.faux = FauxAzalPlus()
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.registre = os.path.join(self.dossier.name, "emissions.json")

    def emetteur(self, **autres: Any) -> EmetteurAzalPlus:
        """L'émetteur branché sur le faux AzalPlus."""
        return EmetteurAzalPlus(
            reglages_test(**autres),
            "azlmcp_essai",
            registre=self.registre,
            ouvrir=self.faux.ouvrir,
            aujourd_hui=date(2026, 11, 9),
        )

    def test_verrou_general_ferme_ne_parle_pas_a_azalplus(self) -> None:
        """actif: false — aucun appel, motif lisible."""
        emission = self.emetteur(actif=False).emettre(mission_test())
        self.assertIn("AzalPlus fermé", emission["refus"])
        self.assertEqual(self.faux.appels, [])

    def test_declencheur_ferme_ne_parle_pas_a_azalplus(self) -> None:
        """Le genre de mission n'est pas déclencheur : rien ne part."""
        emission = self.emetteur().emettre(
            mission_test(genre="montee_version")
        )
        self.assertIn("montee_version", emission["refus"])
        self.assertEqual(self.faux.appels, [])

    def test_essai_a_blanc_lit_mais_ne_cree_rien(self) -> None:
        """L'essai à blanc prépare les lignes sans rien créer."""
        emission = self.emetteur(essai_a_blanc=True).emettre(mission_test())
        self.assertTrue(emission["essai"])
        self.assertEqual(emission["devis"], "")
        self.assertEqual(len(emission["lignes"]), 1)
        self.assertEqual(self.faux.demandes("POST", "/api/v1/devis"), 0)
        self.assertFalse(os.path.exists(self.registre))

    def test_prix_et_tva_viennent_du_catalogue_azalplus(self) -> None:
        """CONCORDE ne fixe aucun prix : il lit celui d'AzalPlus."""
        lignes = self.emetteur(essai_a_blanc=True).emettre(mission_test())[
            "lignes"
        ]
        self.assertEqual(lignes[0]["prix_unitaire"], "900.00")
        self.assertEqual(lignes[0]["tva"], "20.00")
        self.assertEqual(lignes[0]["produit_id"], "p1")
        self.assertEqual(lignes[0]["quantite"], 1)

    def test_quantite_prise_sur_une_mesure_de_la_mission(self) -> None:
        """quantite: ecritures — la quantité est la mesure, pas un 1."""
        reglages = {
            "prestations": {
                "transfert": [
                    {"produit": "PRD-00099", "quantite": "ecritures"}
                ]
            }
        }
        lignes = self.emetteur(essai_a_blanc=True, **reglages).emettre(
            mission_test()
        )["lignes"]
        self.assertEqual(lignes[0]["quantite"], 913)

    def test_mesure_absente_est_un_refus_nomme(self) -> None:
        """Une mesure qui manque ne devient jamais un 1 deviné."""
        reglages = {
            "prestations": {
                "transfert": [{"produit": "PRD-00007", "quantite": "comptes"}]
            }
        }
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur(**reglages).emettre(mission_test())
        self.assertIn("comptes", str(leve.exception))

    def test_aucune_prestation_reglee_est_un_refus_nomme(self) -> None:
        """Sans code produit réglé, aucun devis n'est inventé."""
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur(prestations={"transfert": []}).emettre(
                mission_test()
            )
        self.assertIn("Aucune prestation", str(leve.exception))

    def test_prestation_absente_du_catalogue_est_un_refus_nomme(
        self,
    ) -> None:
        """Un code inconnu d'AzalPlus bloque, en nommant le code."""
        reglages = {
            "prestations": {
                "transfert": [{"produit": "PRD-INCONNU"}],
            }
        }
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur(**reglages).emettre(mission_test())
        self.assertIn("PRD-INCONNU", str(leve.exception))

    def test_siren_introuvable_est_un_refus_nomme(self) -> None:
        """Aucun client ne porte ce SIREN : rien n'est créé."""
        self.faux.base_clients = []
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur().emettre(mission_test())
        self.assertIn("123456789", str(leve.exception))
        self.assertEqual(self.faux.demandes("POST", "/api/v1/devis"), 0)

    def test_siren_illisible_est_un_refus_nomme(self) -> None:
        """Moins de neuf chiffres : on ne complète pas au hasard."""
        with self.assertRaises(ErreurAzalPlusDocuments):
            self.emetteur().emettre(mission_test(siren="1234"))

    def test_siren_en_double_est_un_refus_nomme(self) -> None:
        """Deux clients au même SIREN : à démêler, pas à choisir."""
        self.faux.base_clients = [dict(CLIENT_TEST), dict(CLIENT_TEST)]
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur().emettre(mission_test())
        self.assertIn("désigne 2 clients", str(leve.exception))

    def test_client_cree_seulement_si_le_reglage_le_dit(self) -> None:
        """client_absent: creer — le client est créé avec son SIREN."""
        self.faux.base_clients = []
        emission = self.emetteur(client_absent=CLIENT_ABSENT_CREER).emettre(
            mission_test()
        )
        self.assertEqual(self.faux.demandes("POST", "/api/v1/clients"), 1)
        self.assertEqual(emission["devis"], "DEV-00042")

    def test_emission_reelle_cree_le_devis_puis_le_rapport(self) -> None:
        """Le devis, le rapport, et le registre inscrit une seule fois."""
        emission = self.emetteur().emettre(mission_test())
        self.assertEqual(emission["devis"], "DEV-00042")
        self.assertEqual(emission["rapport"], "g1")
        self.assertEqual(emission["refus"], "")
        self.assertEqual(self.faux.demandes("POST", "/api/v1/devis"), 1)
        with open(self.registre, "r", encoding="utf-8") as fichier:
            inscrit = json.load(fichier)
        self.assertEqual(inscrit["CONCORDE/T-2026-001"]["devis"], "DEV-00042")

    def test_le_devis_demande_ne_porte_ni_numero_ni_total(self) -> None:
        """AzalPlus garde la numérotation et les totaux (AZAP-AUTORITE)."""
        self.emetteur().emettre(mission_test())
        demande = self.faux.corps[
            self.faux.appels.index(("POST", "/api/v1/devis", {}))
        ]
        self.assertNotIn("number", demande)
        self.assertNotIn("total", demande)
        self.assertNotIn("subtotal", demande)
        self.assertNotIn("tax_amount", demande)
        self.assertEqual(demande["reference"], "CONCORDE/T-2026-001")
        self.assertEqual(demande["status"], "BROUILLON")

    def test_mission_deja_emise_ne_cree_pas_un_second_devis(self) -> None:
        """Rejouer une mission ne redonne pas un devis."""
        emetteur = self.emetteur()
        emetteur.emettre(mission_test())
        emission = emetteur.emettre(mission_test())
        self.assertIn("déjà émise", emission["refus"])
        self.assertEqual(self.faux.demandes("POST", "/api/v1/devis"), 1)

    def test_societe_emettrice_passe_par_l_entete(self) -> None:
        """AzalPlus ignore le societe_id du corps : c'est l'en-tête."""
        self.emetteur(societe_emettrice="c273a4d6").emettre(mission_test())
        self.assertEqual(self.faux.entetes[0].get("X-Societe-ID"), "c273a4d6")

    def test_rapport_ecarte_si_le_reglage_le_dit(self) -> None:
        """rapport: aucun — le devis part seul."""
        emission = self.emetteur(rapport="aucun").emettre(mission_test())
        self.assertEqual(emission["rapport"], "")
        self.assertEqual(self.faux.demandes("POST", "/api/v1/ged"), 0)

    def test_rapport_avec_fichier_passe_par_le_depot_ged(self) -> None:
        """Une pièce présente est déposée en formulaire, pas en JSON."""
        piece = os.path.join(self.dossier.name, "rapport.xlsx")
        with open(piece, "wb") as fichier:
            fichier.write(b"xlsx")
        emission = self.emetteur().emettre(
            mission_test(fichiers=[piece, "/absent/rien.xlsx"])
        )
        self.assertEqual(emission["rapport"], "g2")
        self.assertEqual(self.faux.demandes("POST", "/api/v1/ged/upload"), 1)

    def test_adresse_en_clair_refusee(self) -> None:
        """Une adresse http:// ne sort jamais du serveur."""
        with self.assertRaises(ErreurConnexion):
            self.emetteur(adresse="http://azalplus.test").emettre(
                mission_test()
            )

    def test_adresse_absente_est_un_refus_nomme(self) -> None:
        """Sans adresse réglée, le motif le dit."""
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            self.emetteur(adresse="").emettre(mission_test())
        self.assertIn("Adresse", str(leve.exception))

    def test_cle_absente_est_un_refus_nomme(self) -> None:
        """Sans clé d'API, le motif nomme la variable à renseigner."""
        emetteur = EmetteurAzalPlus(
            reglages_test(), "", registre=self.registre
        )
        with self.assertRaises(ErreurAzalPlusDocuments) as leve:
            emetteur.emettre(mission_test())
        self.assertIn("CONCORDE_AZALPLUS_CLE_API", str(leve.exception))

    def test_refus_d_azalplus_ne_casse_pas_la_mission(self) -> None:
        """Le refus est DIT, jamais avalé, et la mission reste réussie."""
        self.faux.base_clients = []
        emission = emettre_sans_bloquer(mission_test(), None, self.emetteur())
        self.assertIn("123456789", emission["refus"])
        self.assertEqual(emission["devis"], "")


class TestReglagesAzalPlus(unittest.TestCase):
    """Les réglages livrés et la lecture d'un SIREN."""

    def test_reglages_livres_tous_verrous_fermes(self) -> None:
        """Le fichier livré ne crée rien tant qu'on ne l'ouvre pas."""
        reglages = reglages_azalplus()
        self.assertFalse(reglages["actif"])
        self.assertTrue(reglages["essai_a_blanc"])
        self.assertEqual(set(reglages["declencheurs"].values()), {False})

    def test_reglages_absents_est_un_refus_nomme(self) -> None:
        """Un fichier manquant se dit, il ne s'invente pas."""
        with self.assertRaises(ErreurAzalPlusDocuments):
            reglages_azalplus("/absent/azalplus_documents.yaml")

    def test_siren_lu_quelle_que_soit_sa_presentation(self) -> None:
        """Espaces, points et les cinq chiffres d'un SIRET."""
        self.assertEqual(siren_normalise("123 456 789"), "123456789")
        self.assertEqual(siren_normalise("12345678900017"), "123456789")
        self.assertEqual(siren_normalise("1234"), "")
        self.assertEqual(siren_normalise(""), "")


if __name__ == "__main__":
    unittest.main()
