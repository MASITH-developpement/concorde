# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de l'écran Transferts (ADR-0011), par le vrai serveur HTTP."""

import http.client
import io
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from typing import Any

from core.connecteurs.secrets import lire_secrets
from interface import auth
from interface.serveur import Application, creer_serveur
from interface.transferts import (
    ErreurEcran,
    chemin_dans,
    recevoir_fichier,
    taille_depot_max,
)
from tests.outils import fec, ligne_fec
from tests.test_interface import MDP, FaussesBases, entete_obligatoire

FEC_VENTES = (
    ligne_fec("AN", "1", "20250101", "512000", "1000,00"),
    ligne_fec("AN", "1", "20250101", "101000", credit="1000,00"),
    ligne_fec("VE", "2", "20250115", "411000", "120,00"),
    ligne_fec("VE", "2", "20250115", "706000", credit="100,00"),
    ligne_fec("VE", "2", "20250115", "445710", credit="20,00"),
)
SAISIE_PENNYLANE = "jeton-pennylane-tres-prive"


class TestEcranTransferts(unittest.TestCase):
    """Connexions, dépôts, transferts et feu vert depuis l'écran."""

    app: Application
    serveur: ThreadingHTTPServer
    port: int
    dossier: str
    secrets: str
    cookie: str

    @classmethod
    def setUpClass(cls) -> None:
        """Démarre l'interface sur un dossier et des secrets neufs."""
        auth.N = 2**10
        cls.dossier = tempfile.mkdtemp()
        cls.secrets = os.path.join(
            cls.dossier, "connecteurs", "connecteurs.env"
        )
        cls.app = Application(
            auth.hacher(MDP),
            cls.dossier,
            bases=FaussesBases(),
            fichier_secrets=cls.secrets,
        )
        cls.serveur = creer_serveur(cls.app, "127.0.0.1", 0)
        cls.port = cls.serveur.server_address[1]
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        """Arrête le serveur et rétablit le coût de hachage."""
        cls.serveur.shutdown()
        auth.N = 2**15

    def setUp(self) -> None:
        """Ouvre une session."""
        reponse, _ = self.envoyer("POST", "/api/connexion", {"mdp": MDP})
        self.assertEqual(reponse.status, 200)
        self.cookie = entete_obligatoire(reponse, "Set-Cookie").split(";")[0]

    def envoyer(
        self,
        methode: str,
        chemin: str,
        corps: dict[str, Any] | None = None,
        brut: bytes | None = None,
        session: bool = True,
    ) -> tuple[http.client.HTTPResponse, bytes]:
        """Envoie une requête (JSON ou fichier brut) ; rend réponse, corps."""
        connexion = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=10
        )
        entetes = {"X-Concorde": "1"}
        if session and getattr(self, "cookie", None):
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

    def json_ok(
        self, methode: str, chemin: str, corps: dict[str, Any] | None = None
    ) -> Any:
        """Requête qui doit réussir ; rend le JSON reçu."""
        reponse, contenu = self.envoyer(methode, chemin, corps)
        self.assertLess(reponse.status, 300, contenu.decode())
        return json.loads(contenu)

    def refus(
        self,
        methode: str,
        chemin: str,
        corps: dict[str, Any] | None = None,
        brut: bytes | None = None,
    ) -> str:
        """Requête qui doit être refusée (400) ; rend la cause."""
        reponse, contenu = self.envoyer(methode, chemin, corps, brut)
        self.assertEqual(reponse.status, 400, contenu.decode())
        cause: str = json.loads(contenu)["erreur"]
        return cause

    def attendre(self, ident: str) -> dict[str, Any]:
        """Attend la fin d'une tâche ; rend son état."""
        for _ in range(200):
            tache: dict[str, Any] = self.json_ok("GET", "/api/taches/" + ident)
            if tache["statut"] not in ("en_attente", "en_cours"):
                return tache
            time.sleep(0.05)
        self.fail("tâche non terminée")

    def connexion_fec(self, libelle: str, usage: str) -> dict[str, Any]:
        """Ajoute une connexion FEC (source ou destination)."""
        fiche: dict[str, Any] = self.json_ok(
            "POST",
            "/api/connexions",
            {"logiciel": "fec", "libelle": libelle, "usage": usage},
        )
        return fiche

    def deposer(self, ident: str, contenu: bytes) -> dict[str, Any]:
        """Dépose un FEC ; rend la fiche du dépôt."""
        reponse, corps = self.envoyer(
            "POST",
            "/api/connexions/%s/depot?nom=384684957FEC20251231.txt" % ident,
            brut=contenu,
        )
        self.assertEqual(reponse.status, 201, corps.decode())
        depot: dict[str, Any] = json.loads(corps)
        return depot

    def test_session_exigee(self) -> None:
        """Vérifie que chaque route de l'écran exige une session."""
        for methode, chemin in (
            ("GET", "/api/logiciels"),
            ("GET", "/api/connexions"),
            ("GET", "/api/transferts"),
            ("POST", "/api/connexions"),
            ("POST", "/api/tables"),
            ("POST", "/api/connexions/fec_000000/depot"),
            ("DELETE", "/api/connexions/fec_000000"),
        ):
            brut = b"x" if chemin.endswith(("tables", "depot")) else None
            corps: dict[str, Any] | None = (
                None if brut or methode != "POST" else {}
            )
            reponse, _ = self.envoyer(
                methode, chemin, corps, brut, session=False
            )
            self.assertEqual(reponse.status, 401, chemin)

    def test_logiciels_decrits_par_les_connecteurs(self) -> None:
        """Vérifie le formulaire construit depuis les connecteurs."""
        reponse = self.json_ok("GET", "/api/logiciels")
        par_nom = {
            logiciel["logiciel"]: logiciel for logiciel in reponse["logiciels"]
        }
        self.assertEqual(reponse["depot_max"], 200 * 1024 * 1024)
        self.assertEqual(
            par_nom["odoo"]["parametres"], ["url", "base", "utilisateur"]
        )
        self.assertEqual(par_nom["odoo"]["secrets"], ["cle_api"])
        self.assertEqual(par_nom["fec"]["parametres"], [])
        self.assertTrue(par_nom["fec"]["fichier"])
        self.assertIsNone(par_nom["azalplus"]["ecriture"])

    def test_secret_jamais_renvoye(self) -> None:
        """Vérifie qu'un secret saisi n'apparaît dans aucune réponse."""
        fiche = self.json_ok(
            "POST",
            "/api/connexions",
            {"logiciel": "pennylane", "libelle": "Pennylane cabinet"},
        )
        self.assertEqual(fiche["secrets"], {"jeton": False})
        reponse = self.json_ok(
            "POST",
            "/api/connexions/%s/secret" % fiche["id"],
            {"champ": "jeton", "valeur": SAISIE_PENNYLANE},
        )
        self.assertEqual(reponse, {"secrets": {"jeton": True}})
        dossier_secrets = os.path.dirname(self.secrets)
        self.assertEqual(stat.S_IMODE(os.stat(dossier_secrets).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.secrets).st_mode), 0o600)
        for chemin in ("/api/connexions", "/api/journal", "/api/taches"):
            _, contenu = self.envoyer("GET", chemin)
            self.assertNotIn(SAISIE_PENNYLANE.encode(), contenu, chemin)
        self.assertIn(
            "Secret inconnu",
            self.refus(
                "POST",
                "/api/connexions/%s/secret" % fiche["id"],
                {"champ": "mot_de_passe", "valeur": "x"},
            ),
        )
        self.assertIn(
            "vide",
            self.refus(
                "POST",
                "/api/connexions/%s/secret" % fiche["id"],
                {"champ": "jeton", "valeur": ""},
            ),
        )
        self.json_ok("DELETE", "/api/connexions/" + fiche["id"])
        self.assertEqual(lire_secrets(self.secrets), {})

    def test_refus_a_l_ajout(self) -> None:
        """Vérifie les refus : chemin FEC imposé, paramètre inconnu, usage."""
        self.assertIn(
            "aucun chemin",
            self.refus(
                "POST",
                "/api/connexions",
                {
                    "logiciel": "fec",
                    "libelle": "Pirate",
                    "usage": "source",
                    "parametres": {"chemin": "/home/ubuntu/.ssh/id_ed25519"},
                },
            ),
        )
        self.assertIn(
            "source",
            self.refus(
                "POST", "/api/connexions", {"logiciel": "fec", "libelle": "X"}
            ),
        )
        self.assertIn(
            "inconnu",
            self.refus(
                "POST",
                "/api/connexions",
                {
                    "logiciel": "odoo",
                    "libelle": "Odoo",
                    "parametres": {"url": "https://x", "hote": "y"},
                },
            ),
        )
        self.assertIn(
            "refusé",
            self.refus(
                "POST",
                "/api/connexions",
                {
                    "logiciel": "odoo",
                    "libelle": "Odoo",
                    "parametres": {"cle_api": "abc"},
                },
            ),
        )
        self.assertIn(
            "texte",
            self.refus(
                "POST",
                "/api/connexions",
                {
                    "logiciel": "odoo",
                    "libelle": "Odoo",
                    "parametres": {"url": 3},
                },
            ),
        )

    def test_depot_refuse_puis_accepte(self) -> None:
        """Vérifie qu'un FEC refusé n'est pas gardé et qu'un bon FEC l'est."""
        source = self.connexion_fec("Sage 100 client A", "source")
        self.assertEqual(source["usage"], "source")
        self.assertIsNone(source["depot"])
        cause = self.refus(
            "POST",
            "/api/connexions/%s/depot?nom=faux.txt" % source["id"],
            brut=b"ceci n'est pas un FEC",
        )
        self.assertIn("FEC", cause)
        depots = os.path.join(self.dossier, "depots")
        self.assertEqual(
            [nom for _, _, noms in os.walk(depots) for nom in noms], []
        )
        depot = self.deposer(source["id"], fec(*FEC_VENTES))
        self.assertEqual(
            (depot["lignes"], depot["ecritures"], depot["debit"]),
            (5, 2, 112000),
        )
        self.assertEqual(depot["nom"], "384684957FEC20251231.txt")
        connexions = self.json_ok("GET", "/api/connexions")
        relue = next(cx for cx in connexions if cx["id"] == source["id"])
        self.assertEqual(relue["depot"]["lignes"], 5)
        self.assertNotIn("chemin", relue["parametres"])
        destination = self.connexion_fec("Sortie", "destination")
        self.assertIn(
            "ne reçoit pas",
            self.refus(
                "POST",
                "/api/connexions/%s/depot?nom=a.txt" % destination["id"],
                brut=fec(*FEC_VENTES),
            ),
        )
        self.json_ok("DELETE", "/api/connexions/" + source["id"])
        self.assertEqual(os.listdir(depots), [])

    def test_transfert_complet_avec_feu_vert(self) -> None:
        """Vérifie le parcours FEC -> FEC : rapport, feu vert, transfert."""
        source = self.connexion_fec("Quadra client B", "source")
        self.deposer(source["id"], fec(*FEC_VENTES))
        destination = self.connexion_fec("Export client B", "destination")
        self.assertIn(
            "source",
            self.refus(
                "POST",
                "/api/transferts",
                {"source": source["id"], "destinations": [source["id"]]},
            ),
        )
        tache = self.attendre(
            self.json_ok(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "identique": {destination["id"]: True},
                },
            )["id"]
        )
        self.assertEqual(tache["statut"], "terminee", tache["erreur"])
        ident = tache["resultat"]["transfert"]
        self.assertEqual(
            tache["resultat"]["destinations"],
            {destination["id"]: "attente_feu_vert"},
        )
        resumes = self.json_ok("GET", "/api/transferts")
        self.assertIn(ident, [resume["id"] for resume in resumes])
        detail = self.json_ok("GET", "/api/transferts/" + ident)
        self.assertEqual(
            detail["libelles"][destination["id"]], "Export client B"
        )
        self.assertIn("source/FEC_source.txt", detail["fichiers"])
        reponse, contenu = self.envoyer(
            "GET",
            "/api/transferts/%s/fichier?chemin=source/FEC_source.txt" % ident,
        )
        self.assertEqual(reponse.status, 200)
        self.assertIn(b"JournalCode", contenu)
        for chemin in ("../../connexions.json", "/etc/passwd", ""):
            reponse, _ = self.envoyer(
                "GET", "/api/transferts/%s/fichier?chemin=%s" % (ident, chemin)
            )
            self.assertEqual(reponse.status, 404, chemin)
        url_feu_vert = "/api/transferts/%s/feu-vert" % ident
        self.assertIn(
            "retapé",
            self.refus(
                "POST",
                url_feu_vert,
                {
                    "destination": destination["id"],
                    "confirmation": "Export client C",
                    "sauvegarde_du": "2026-11-08",
                },
            ),
        )
        self.assertIn(
            "sauvegarde",
            self.refus(
                "POST",
                url_feu_vert,
                {
                    "destination": destination["id"],
                    "confirmation": "Export client B",
                },
            ),
        )
        fin = self.attendre(
            self.json_ok(
                "POST",
                url_feu_vert,
                {
                    "destination": destination["id"],
                    "confirmation": "Export client B",
                    "sauvegarde_du": "2026-11-08",
                },
            )["id"]
        )
        self.assertEqual(fin["statut"], "terminee", fin["erreur"])
        self.assertEqual(fin["resultat"]["statut"], "transferee")
        detail = self.json_ok("GET", "/api/transferts/" + ident)
        feu_vert = detail["destinations"][destination["id"]]["etapes"][
            "feu_vert"
        ]
        self.assertIn("127.0.0.1", feu_vert["infos"]["par"])
        self.assertIn(
            "n'attend pas",
            self.refus(
                "POST",
                url_feu_vert,
                {
                    "destination": destination["id"],
                    "confirmation": "Export client B",
                    "sauvegarde_du": "2026-11-08",
                },
            ),
        )

    def test_table_de_correspondance(self) -> None:
        """Vérifie la table reçue, puis son usage par jeton."""
        reponse, contenu = self.envoyer(
            "POST",
            "/api/tables?nom=table.csv",
            brut="Compte source;Compte cible\n512000;512100\n".encode(),
        )
        self.assertEqual(reponse.status, 201, contenu.decode())
        self.assertEqual(json.loads(contenu)["comptes"], 1)
        self.assertIn(
            "non reconnu",
            self.refus("POST", "/api/tables?nom=table.pdf", brut=b"%PDF"),
        )
        self.assertIn(
            "vide",
            self.refus(
                "POST", "/api/tables?nom=table.csv", brut=b"Compte;Cible\n"
            ),
        )
        source = self.connexion_fec("Source table", "source")
        self.deposer(source["id"], fec(*FEC_VENTES))
        destination = self.connexion_fec("Destination table", "destination")
        self.assertIn(
            "inconnue",
            self.refus(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "tables": {destination["id"]: "../../connexions"},
                },
            ),
        )
        tache = self.attendre(
            self.json_ok(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "tables": {
                        destination["id"]: json.loads(contenu)["jeton"]
                    },
                },
            )["id"]
        )
        # Table incomplète : la concordance bloque, les comptes manquants
        # partent dans le fichier à arbitrer.
        etat = tache["resultat"]["destinations"][destination["id"]]
        self.assertEqual(etat, "bloquee")
        detail = self.json_ok(
            "GET", "/api/transferts/" + tache["resultat"]["transfert"]
        )
        self.assertIn(
            "%s/a_arbitrer.xlsx" % destination["id"], detail["fichiers"]
        )

    def test_demande_mal_formee(self) -> None:
        """Vérifie les refus avant toute lecture."""
        self.assertIn(
            "mal formée",
            self.refus(
                "POST", "/api/transferts", {"source": "x", "destinations": "y"}
            ),
        )
        self.assertIn(
            "Aucune destination",
            self.refus(
                "POST", "/api/transferts", {"source": "x", "destinations": []}
            ),
        )
        self.assertIn(
            "inconnu",
            self.refus("POST", "/api/transferts/T-absent/feu-vert", {}),
        )
        reponse, _ = self.envoyer(
            "GET", "/api/transferts/T20261108000000-abcd"
        )
        self.assertEqual(reponse.status, 400)
        reponse, _ = self.envoyer("GET", "/api/transferts/x/inconnu")
        self.assertEqual(reponse.status, 404)
        reponse, _ = self.envoyer("POST", "/api/transferts/x/inconnu", {})
        self.assertEqual(reponse.status, 404)

    def test_tester_puis_retirer_une_source_deja_servie(self) -> None:
        """Vérifie le test d'une connexion et le libellé d'une retirée."""
        source = self.connexion_fec("Source à retirer", "source")
        self.deposer(source["id"], fec(*FEC_VENTES))
        destination = self.connexion_fec("Sortie à tester", "destination")
        relue = self.json_ok(
            "POST", "/api/connexions/%s/tester" % destination["id"], {}
        )
        self.assertIsNotNone(relue["dernier_test"])
        self.assertIn(
            "date de début",
            self.refus(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "du": "2025-12-31",
                    "au": "2025-01-01",
                },
            ),
        )
        self.assertIn(
            "inconnue",
            self.refus(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "tables": {destination["id"]: "0" * 32},
                },
            ),
        )
        tache = self.attendre(
            self.json_ok(
                "POST",
                "/api/transferts",
                {
                    "source": source["id"],
                    "destinations": [destination["id"]],
                    "identique": {destination["id"]: True},
                },
            )["id"]
        )
        self.json_ok("DELETE", "/api/connexions/" + source["id"])
        resume = next(
            resume
            for resume in self.json_ok("GET", "/api/transferts")
            if resume["id"] == tache["resultat"]["transfert"]
        )
        self.assertEqual(resume["source"], "(retirée) %s" % source["id"])
        os.makedirs(os.path.join(self.dossier, "transferts", "autre"))
        self.assertNotIn(
            "autre",
            [
                resume["id"]
                for resume in self.json_ok("GET", "/api/transferts")
            ],
        )

    def test_fichier_de_secrets_trop_ouvert(self) -> None:
        """Vérifie que l'écran nomme un fichier de secrets mal protégé."""
        fiche = self.json_ok(
            "POST",
            "/api/connexions",
            {"logiciel": "pennylane", "libelle": "Pennylane droits"},
        )
        self.json_ok(
            "POST",
            "/api/connexions/%s/secret" % fiche["id"],
            {"champ": "jeton", "valeur": "x"},
        )
        os.chmod(self.secrets, 0o644)
        try:
            relue = next(
                cx
                for cx in self.json_ok("GET", "/api/connexions")
                if cx["id"] == fiche["id"]
            )
        finally:
            os.chmod(self.secrets, 0o600)
        self.assertIn("chmod 600", relue["secrets_erreur"])
        self.json_ok("DELETE", "/api/connexions/" + fiche["id"])


class TestOutilsEcran(unittest.TestCase):
    """Routines de l'écran : plafond, réception, chemins."""

    def test_aucun_transfert_au_depart(self) -> None:
        """Vérifie la liste vide quand aucun transfert n'a été créé."""
        with tempfile.TemporaryDirectory() as dossier:
            app = Application(
                "scrypt$x",
                dossier,
                bases=FaussesBases(),
                fichier_secrets=os.path.join(dossier, "s.env"),
            )
            self.assertEqual(app.transferts.lister_transferts(), [])

    def test_taille_depot_max(self) -> None:
        """Vérifie le plafond par défaut, réglé, et les valeurs refusées."""
        self.assertEqual(taille_depot_max({}), 200 * 1024 * 1024)
        self.assertEqual(
            taille_depot_max({"CONCORDE_DEPOT_MAX_MO": "500"}),
            500 * 1024 * 1024,
        )
        for mauvaise in ("0", "-3", "1,5", "beaucoup"):
            with self.assertRaises(ValueError):
                taille_depot_max({"CONCORDE_DEPOT_MAX_MO": mauvaise})

    def test_recevoir_fichier(self) -> None:
        """Vérifie la réception, le plafond et l'envoi interrompu."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "sous", "f.bin")
            recevoir_fichier(io.BytesIO(b"abc" * 30000), 90000, chemin, 10**6)
            with open(chemin, "rb") as fichier:
                self.assertEqual(len(fichier.read()), 90000)
            with self.assertRaises(ErreurEcran):
                recevoir_fichier(io.BytesIO(b"abc"), 3, chemin, 2)
            with self.assertRaises(ErreurEcran):
                recevoir_fichier(io.BytesIO(b""), 0, chemin, 2)
            with self.assertRaises(ErreurEcran):
                recevoir_fichier(io.BytesIO(b"ab"), 10, chemin, 100)
            self.assertFalse(os.path.exists(chemin))

    def test_chemin_dans(self) -> None:
        """Vérifie le refus des sorties de dossier."""
        self.assertTrue(chemin_dans("/srv/a", "/srv/a/b/c"))
        self.assertFalse(chemin_dans("/srv/a", "/srv/a/../b"))
        self.assertFalse(chemin_dans("/srv/a", "/srv/a"))
        self.assertFalse(chemin_dans("/srv/a", "/srv/ab"))


if __name__ == "__main__":
    unittest.main()
