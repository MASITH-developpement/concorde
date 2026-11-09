# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de l'écran Montée de version (ADR-0012), par le vrai serveur HTTP.

Le service de montée est joué dans le test (Docker et base simulés, comme
tests/test_montee_pilotee.py) : l'écran ne fait que déposer des demandes
et lire les résumés publiés.
"""

import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer
from typing import Any

from core.journal import Journal
from core.montee_version import demandes, montee
from interface import auth
from interface.montees import EcranMontees
from interface.serveur import Application, creer_serveur
from tests.test_interface import MDP, FaussesBases, entete_obligatoire
from tests.test_montee_pilotee import Atelier, sauvegarde_zip


class TestEcranMontees(Atelier):
    """Dépôt, demandes, suivi, feu vert, livraison, depuis l'écran."""

    serveur: ThreadingHTTPServer

    def setUp(self) -> None:
        """Service de montée simulé et interface sur un port libre."""
        super().setUp()
        auth.N = 2**10
        donnees = os.path.join(self._tmp.name, "volume")
        for nom in ("depots", "demandes", "livraisons"):
            os.makedirs(os.path.join(donnees, nom))
        etats = os.path.join(self._tmp.name, "etats")
        self.service = demandes.ServiceMontee(
            donnees,
            etats,
            self.openupgrade,
            self.docker,
            (os.getuid(), os.getgid()),
        )
        self.racine = self.service.racine
        self.ecran = EcranMontees(Journal(), donnees, etats, {})
        app = Application(
            auth.hacher(MDP),
            os.path.join(self._tmp.name, "interface"),
            bases=FaussesBases(),
            fichier_secrets=os.path.join(self._tmp.name, "s.env"),
            montees=self.ecran,
        )
        self.serveur = creer_serveur(app, "127.0.0.1", 0)
        threading.Thread(
            target=self.serveur.serve_forever, daemon=True
        ).start()
        self.addCleanup(self.serveur.shutdown)
        reponse, _ = self.envoyer(
            "POST", "/api/connexion", {"mdp": MDP}, session=False
        )
        self.cookie = entete_obligatoire(reponse, "Set-Cookie").split(";")[0]

    def envoyer(
        self,
        methode: str,
        chemin: str,
        corps: dict[str, Any] | None = None,
        brut: bytes | None = None,
        session: bool = True,
    ) -> tuple[http.client.HTTPResponse, bytes]:
        """Requête JSON ou fichier brut ; rend réponse et corps."""
        connexion = http.client.HTTPConnection(
            "127.0.0.1", self.serveur.server_address[1], timeout=10
        )
        entetes = {"X-Concorde": "1"}
        if session:
            entetes["Cookie"] = self.cookie
        donnees = brut
        if corps is not None:
            donnees = json.dumps(corps).encode()
            entetes["Content-Type"] = "application/json"
        connexion.request(methode, chemin, body=donnees, headers=entetes)
        reponse = connexion.getresponse()
        contenu = reponse.read()
        connexion.close()
        return reponse, contenu

    def ok(
        self, methode: str, chemin: str, corps: dict[str, Any] | None = None
    ) -> Any:
        """Requête qui doit réussir ; rend le JSON reçu."""
        reponse, contenu = self.envoyer(methode, chemin, corps)
        self.assertLess(reponse.status, 300, contenu.decode())
        return json.loads(contenu)

    def refus(
        self, methode: str, chemin: str, corps: dict[str, Any] | None = None
    ) -> str:
        """Requête refusée (400) ; rend la cause."""
        reponse, contenu = self.envoyer(methode, chemin, corps)
        self.assertEqual(reponse.status, 400, contenu.decode())
        cause: str = json.loads(contenu)["erreur"]
        return cause

    def deposer(self, base: str = "client_a") -> str:
        """Dépose une sauvegarde par l'écran ; rend son jeton."""
        chemin = sauvegarde_zip(
            os.path.join(self._tmp.name, "envoi.zip"), base=base
        )
        with open(chemin, "rb") as fichier:
            contenu_zip = fichier.read()
        reponse, contenu = self.envoyer(
            "POST", "/api/montees/depot?nom=client.zip", brut=contenu_zip
        )
        self.assertEqual(reponse.status, 201, contenu.decode())
        resume = json.loads(contenu)
        self.assertEqual((resume["version"], resume["base"]), ("14.0", base))
        jeton: str = resume["jeton"]
        return jeton

    def faire(self, chemin: str, corps: dict[str, Any] | None = None) -> Any:
        """Demande par l'écran, traitée par le service ; rend le résultat."""
        ident = self.ok("POST", chemin, corps or {})["demande"]
        self.assertEqual(
            self.ok("GET", "/api/montees/demandes/" + ident)["statut"],
            "en_attente",
        )
        self.service.traiter_file()
        return self.ok("GET", "/api/montees/demandes/" + ident)

    def test_parcours_complet(self) -> None:
        """Vérifie dépôt, vérifications, feu vert, nouvel essai, livraison."""
        etat = self.ok("GET", "/api/montees")
        self.assertTrue(etat["pret"])
        self.assertEqual(etat["versions"], [15, 16, 17, 18])
        resultat = self.faire(
            "/api/montees", {"depot": self.deposer(), "arrivee": 17}
        )
        ident = resultat["montee"]
        self.assertEqual(
            self.faire("/api/montees/%s/circuit" % ident)["statut"], "fait"
        )
        resume = self.ok("GET", "/api/montees")["montees"][0]
        self.assertEqual(resume["statut"], montee.ATTENTE)
        self.assertNotIn(
            "openupgrade",
            json.dumps(resume).lower().replace("openupgrade_", ""),
        )
        refus = self.faire(
            "/api/montees/%s/feu-vert" % ident, {"confirmation": "autre"}
        )
        self.assertIn("mal retapé", refus["message"])
        self.assertEqual(
            self.faire(
                "/api/montees/%s/feu-vert" % ident,
                {"confirmation": "client_a"},
            )["statut"],
            "fait",
        )
        self.photos = 0
        self.faire(
            "/api/montees/%s/nouvel-essai" % ident, {"depot": self.deposer()}
        )
        essai = montee.charger(self.racine, ident)["etapes"]["nouvel_essai"]
        self.docker.donnees_pg = os.path.join(
            self.racine, essai["infos"]["montee"], "donnees", "pgdata"
        )
        reponse, _ = self.envoyer("GET", "/api/montees/%s/livraison" % ident)
        self.assertEqual(reponse.status, 404)
        self.assertEqual(
            self.faire("/api/montees/%s/livrer" % ident)["statut"], "fait"
        )
        reponse, contenu = self.envoyer(
            "GET", "/api/montees/%s/livraison" % ident
        )
        self.assertEqual(reponse.status, 200)
        self.assertEqual(contenu[:2], b"PK")
        self.assertIn(
            "client_a_odoo17.zip",
            entete_obligatoire(reponse, "Content-Disposition"),
        )

    def test_refus(self) -> None:
        """Vérifie les refus de l'écran, avant toute demande."""
        reponse, contenu = self.envoyer(
            "POST", "/api/montees/depot?nom=faux.zip", brut=b"pas un zip"
        )
        self.assertEqual(reponse.status, 400)
        self.assertIn("zip", json.loads(contenu)["erreur"])
        self.assertEqual(os.listdir(self.ecran.depots), [])
        self.assertIn(
            "inconnue",
            self.refus(
                "POST", "/api/montees", {"depot": "../x.zip", "arrivee": 17}
            ),
        )
        self.assertIn(
            "arrivee",
            self.refus(
                "POST",
                "/api/montees",
                {"depot": self.deposer(), "arrivee": "17"},
            ),
        )
        self.assertIn(
            "montee",
            self.refus("POST", "/api/montees/M-x/circuit", {}),
        )
        reponse, _ = self.envoyer(
            "POST", "/api/montees/M20260101000000-abcd/effacer", {}
        )
        self.assertEqual(reponse.status, 404)
        reponse, _ = self.envoyer("GET", "/api/montees/inconnue")
        self.assertEqual(reponse.status, 404)
        self.assertIn(
            "inconnue", self.refus("GET", "/api/montees/demandes/abc")
        )
        reponse, _ = self.envoyer("GET", "/api/montees", session=False)
        self.assertEqual(reponse.status, 401)
        reponse, _ = self.envoyer(
            "POST", "/api/montees/depot", brut=b"x", session=False
        )
        self.assertEqual(reponse.status, 401)
        self.assertEqual(os.listdir(self.service.demandes), [])

    def test_service_absent(self) -> None:
        """Vérifie l'écran quand le volume chiffré n'est pas ouvert."""
        ecran = EcranMontees(
            Journal(),
            os.path.join(self._tmp.name, "absent"),
            os.path.join(self._tmp.name, "absent-etats"),
            {"CONCORDE_MONTEE_DEPOT_MAX_MO": "10"},
        )
        etat = ecran.etat()
        self.assertFalse(etat["pret"])
        self.assertIn("installer_montee", etat["cause"])
        self.assertEqual(
            (etat["montees"], etat["depot_max"]), ([], 10 * 1024 * 1024)
        )
