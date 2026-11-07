# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de l'interface web : authentification, sécurité HTTP, parcours complet."""

import http.client
import json
import tempfile
import threading
import time
import unittest

from core.odoo_source import SourceXmlRpcOdoo17
from interface import auth
from interface.serveur import Application, creer_serveur
from tests.test_odoo_donnees import FauxCommun, FauxObjet

MDP = "mot-de-passe-de-test"


class TestAuth(unittest.TestCase):
    def test_hachage(self):
        e = auth.hacher(MDP)
        self.assertTrue(e.startswith("scrypt$"))
        self.assertNotIn(MDP, e)
        self.assertTrue(auth.verifier(MDP, e))
        self.assertFalse(auth.verifier("autre", e))
        self.assertFalse(auth.verifier(MDP, ""))
        self.assertFalse(auth.verifier(MDP, "n'importe$quoi"))
        self.assertNotEqual(e, auth.hacher(MDP))  # sel aléatoire

    def test_expiration_inactivite(self):
        t = [0.0]
        s = auth.Sessions(horloge=lambda: t[0])
        j = s.ouvrir("1.2.3.4")
        self.assertTrue(s.valide(j))
        t[0] += auth.INACTIVITE_MAX + 1
        self.assertFalse(s.valide(j))

    def test_duree_max(self):
        t = [0.0]
        s = auth.Sessions(horloge=lambda: t[0])
        j = s.ouvrir("ip")
        for _ in range(12):  # activité toutes les 59 min
            t[0] += 59 * 60
            s.valide(j)
        self.assertFalse(s.valide(j))

    def test_force_brute(self):
        t = [0.0]
        s = auth.Sessions(horloge=lambda: t[0])
        for _ in range(auth.ECHECS_MAX):
            self.assertFalse(s.bloquee("ip"))
            s.echec("ip")
        self.assertTrue(s.bloquee("ip"))
        self.assertFalse(s.bloquee("autre-ip"))
        t[0] += auth.FENETRE_ECHECS + 1
        self.assertFalse(s.bloquee("ip"))


class FaussesBases:
    """Annuaire réduit à une base XML-RPC simulée."""

    def lister(self, rafraichir=False):
        return [
            {
                "id": "xmlrpc:test",
                "nom": "test",
                "source": "xmlrpc",
                "version": "17.0",
                "societe": "Soc",
                "devise": "EUR",
                "siren": "384684957",
                "url": "http://x",
            }
        ]

    def ouvrir(self, ident, journal=None):
        return SourceXmlRpcOdoo17(
            "http://x",
            "b",
            "u",
            "c",
            proxy_commun=FauxCommun(),
            proxy_objet=FauxObjet(),
            journal=journal,
        )

    def nom(self, ident):
        return "test"


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        auth.N = 2**10  # tests rapides
        cls.app = Application(
            auth.hacher(MDP), tempfile.mkdtemp(), bases=FaussesBases()
        )
        cls.serveur = creer_serveur(cls.app, "127.0.0.1", 0)
        cls.port = cls.serveur.server_address[1]
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        auth.N = 2**15

    def requete(self, methode, chemin, corps=None, cookie=None, csrf=True):
        cx = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        entetes = {}
        if csrf:
            entetes["X-Concorde"] = "1"
        if cookie:
            entetes["Cookie"] = cookie
        donnees = json.dumps(corps).encode() if corps is not None else None
        if donnees:
            entetes["Content-Type"] = "application/json"
        cx.request(methode, chemin, body=donnees, headers=entetes)
        r = cx.getresponse()
        brut = r.read()
        cx.close()
        return r, brut

    def connecter(self):
        r, _ = self.requete("POST", "/api/connexion", {"mdp": MDP})
        self.assertEqual(r.status, 200)
        cookie = r.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        return cookie.split(";")[0]

    def attendre(self, cookie, ident):
        for _ in range(100):
            _, b = self.requete("GET", "/api/taches/" + ident, cookie=cookie)
            t = json.loads(b)
            if t["statut"] not in ("en_attente", "en_cours"):
                return t
            time.sleep(0.05)
        self.fail("tâche non terminée")

    def test_page_et_entetes_securite(self):
        r, b = self.requete("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn(b"CONCORDE", b)
        self.assertIn(
            "default-src 'self'", r.getheader("Content-Security-Policy")
        )
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")

    def test_api_protegee(self):
        r, _ = self.requete("GET", "/api/bases")
        self.assertEqual(r.status, 401)
        r, _ = self.requete(
            "GET", "/api/bases", cookie="concorde_session=faux"
        )
        self.assertEqual(r.status, 401)

    def test_csrf(self):
        cookie = self.connecter()
        r, _ = self.requete(
            "POST",
            "/api/taches",
            {"action": "analyser", "base_id": "xmlrpc:test"},
            cookie=cookie,
            csrf=False,
        )
        self.assertEqual(r.status, 403)

    def test_mauvais_mot_de_passe(self):
        r, _ = self.requete("POST", "/api/connexion", {"mdp": "faux"})
        self.assertEqual(r.status, 401)
        self.assertIsNone(r.getheader("Set-Cookie"))

    def test_traversee_refusee(self):
        for chemin in (
            "/../serveur.py",
            "/%2e%2e/serveur.py",
            "/../../etc/passwd",
        ):
            r, _ = self.requete("GET", chemin)
            self.assertEqual(r.status, 404, chemin)

    def test_parametres_invalides(self):
        cookie = self.connecter()
        for corps in (
            {"action": "supprimer", "base_id": "xmlrpc:test"},
            {"action": "analyser", "base_id": "inconnue"},
            {
                "action": "analyser",
                "base_id": "xmlrpc:test",
                "du": "31/12/2025",
            },
            {
                "action": "analyser",
                "base_id": "xmlrpc:test",
                "du": "2026-01-01",
                "au": "2025-01-01",
            },
            {
                "action": "telecharger",
                "base_id": "xmlrpc:test",
                "formats": [],
                "objets": ["ecritures"],
            },
        ):
            r, _ = self.requete("POST", "/api/taches", corps, cookie=cookie)
            self.assertEqual(r.status, 400, corps)

    def test_parcours_analyse(self):
        cookie = self.connecter()
        r, b = self.requete(
            "POST",
            "/api/taches",
            {"action": "analyser", "base_id": "xmlrpc:test"},
            cookie=cookie,
        )
        self.assertEqual(r.status, 201)
        t = self.attendre(cookie, json.loads(b)["id"])
        self.assertEqual(t["statut"], "terminee", t.get("erreur"))
        self.assertEqual(t["resultat"]["infos"]["total_debit"], "100,10")
        r, b = self.requete(
            "GET", "/api/taches/%s/rapport.json" % t["id"], cookie=cookie
        )
        self.assertEqual(r.status, 200)
        self.assertIn("empreinte", json.loads(b))

    def test_parcours_telechargement(self):
        cookie = self.connecter()
        r, b = self.requete(
            "POST",
            "/api/taches",
            {
                "action": "telecharger",
                "base_id": "xmlrpc:test",
                "formats": ["fec", "xlsx"],
                "objets": ["ecritures", "comptes"],
            },
            cookie=cookie,
        )
        t = self.attendre(cookie, json.loads(b)["id"])
        self.assertEqual(t["statut"], "terminee", t.get("erreur"))
        self.assertEqual([f["format"] for f in t["fichiers"]], ["fec", "xlsx"])
        self.assertNotIn(
            "chemin", t["fichiers"][0]
        )  # chemin serveur jamais exposé
        r, b = self.requete(
            "GET", "/api/taches/%s/fichiers/0" % t["id"], cookie=cookie
        )
        self.assertEqual(r.status, 200)
        self.assertTrue(b.startswith(b"JournalCode|"))
        r, _ = self.requete(
            "GET", "/api/taches/%s/fichiers/9" % t["id"], cookie=cookie
        )
        self.assertEqual(r.status, 404)
        r, b = self.requete(
            "GET", "/api/taches/%s/zip" % t["id"], cookie=cookie
        )
        self.assertEqual(r.status, 200)
        self.assertTrue(b.startswith(b"PK"))

    def test_journal_de_tache(self):
        cookie = self.connecter()
        r, b = self.requete(
            "POST",
            "/api/taches",
            {"action": "analyser", "base_id": "xmlrpc:test"},
            cookie=cookie,
        )
        t = self.attendre(cookie, json.loads(b)["id"])
        messages = [e["message"] for e in t["journal"]]
        self.assertTrue(any("Connexion" in m for m in messages))
        self.assertTrue(any(m.startswith("Bilan :") for m in messages))
        self.assertTrue(any(m.startswith("Terminé en") for m in messages))
        # lecture incrémentale
        _, b = self.requete(
            "GET",
            "/api/taches/%s?depuis=%d" % (t["id"], len(messages)),
            cookie=cookie,
        )
        self.assertEqual(json.loads(b)["journal"], [])
        # chaque constat porte l'explication de Marceau
        for c in t["resultat"]["constats"]:
            self.assertTrue(c["explication"]["pourquoi"])

    def test_comptes_grand_livre_ecriture(self):
        cookie = self.connecter()
        r, b = self.requete(
            "GET", "/api/comptes?base=xmlrpc:test", cookie=cookie
        )
        self.assertEqual(r.status, 200, b)
        d = json.loads(b)
        c411 = next(c for c in d["comptes"] if c["code"] == "411000")
        self.assertEqual((c411["debit"], c411["lignes"]), (10010, 1))
        self.assertEqual(d["infos"]["total_debit"], "100,10")
        r, b = self.requete(
            "GET",
            "/api/comptes/411000/grand-livre?base=xmlrpc:test",
            cookie=cookie,
        )
        g = json.loads(b)
        self.assertEqual(g["totaux"]["solde"], 10010)
        self.assertEqual(g["lignes"][0]["cumul"], 10010)
        r, b = self.requete(
            "GET", "/api/ecritures/5?base=xmlrpc:test", cookie=cookie
        )
        self.assertEqual(len(json.loads(b)["lignes"]), 2)
        r, _ = self.requete("GET", "/api/comptes?base=inconnue", cookie=cookie)
        self.assertEqual(r.status, 400)
        r, _ = self.requete("GET", "/api/comptes?base=xmlrpc:test")
        self.assertEqual(r.status, 401)

    def test_alertes_et_journal(self):
        cookie = self.connecter()
        self.app.centre.synchroniser(
            "balance",
            "test",
            [
                {
                    "code": "CAISSE_CREDITRICE",
                    "niveau": "BLOQUANT",
                    "message": "Caisses créditrices",
                    "nombre": 1,
                    "exemples": ["530000"],
                }
            ],
        )
        _, b = self.requete("GET", "/api/alertes/resume", cookie=cookie)
        self.assertEqual(json.loads(b)["bloquantes"], 1)
        _, b = self.requete("GET", "/api/alertes", cookie=cookie)
        a = json.loads(b)["alertes"][0]
        self.assertEqual(a["explication"]["titre"], "Caisse créditrice")
        r, _ = self.requete(
            "POST",
            "/api/alertes/vue",
            {"id": a["id"]},
            cookie=cookie,
            csrf=False,
        )
        self.assertEqual(r.status, 403)
        _, b = self.requete(
            "POST", "/api/alertes/vue", {"id": a["id"]}, cookie=cookie
        )
        self.assertEqual(json.loads(b)["non_vues"], 0)
        _, b = self.requete("GET", "/api/journal?depuis=0", cookie=cookie)
        self.assertTrue(
            any(
                "Connexion réussie" in e["message"]
                for e in json.loads(b)["journal"]
            )
        )

    def test_suppression_base_distante_interdite(self):
        cookie = self.connecter()
        for action in ("supprimer_base", "reinitialiser_base"):
            r, b = self.requete(
                "POST",
                "/api/taches",
                {
                    "action": action,
                    "base_id": "xmlrpc:test",
                    "confirmation": "test",
                },
                cookie=cookie,
            )
            self.assertEqual(r.status, 400)
            self.assertIn("ne se supprime jamais", json.loads(b)["erreur"])

    def test_rapport_du_jour(self):
        cookie = self.connecter()
        r, b = self.requete(
            "GET", "/api/rapport?jour=2026-11-07", cookie=cookie
        )
        self.assertEqual(r.status, 200)
        d = json.loads(b)
        self.assertTrue(d["conclusions"])
        premiere = d["conclusions"][0]["id"]
        r, b = self.requete(
            "POST",
            "/api/rapport",
            {
                "jour": "2026-11-07",
                "conclusions": [
                    {"id": premiere, "visible": False, "commentaire": "vu"}
                ],
                "ajouts": [{"id": "a", "texte": "Point ajouté"}],
                "commentaire": "RAS",
            },
            cookie=cookie,
        )
        d = json.loads(b)
        self.assertFalse(
            next(c for c in d["conclusions"] if c["id"] == premiere)["visible"]
        )
        self.assertEqual(d["commentaire"], "RAS")
        r, b = self.requete(
            "GET", "/api/rapport/export?jour=2026-11-07", cookie=cookie
        )
        self.assertEqual(r.status, 200)
        self.assertIn("attachment", r.getheader("Content-Disposition"))
        self.assertIn("Point ajouté", b.decode())
        r, _ = self.requete(
            "GET", "/api/rapport?jour=07/11/2026", cookie=cookie
        )
        self.assertEqual(r.status, 400)
        r, _ = self.requete(
            "POST",
            "/api/rapport",
            {"jour": "2026-11-07"},
            cookie=cookie,
            csrf=False,
        )
        self.assertEqual(r.status, 403)

    def test_echec_affiche(self):
        """FEC + brouillons : la tâche échoue avec un message clair (jamais muet)."""
        cookie = self.connecter()
        r, b = self.requete(
            "POST",
            "/api/taches",
            {
                "action": "telecharger",
                "base_id": "xmlrpc:test",
                "formats": ["fec"],
                "objets": ["ecritures"],
                "brouillons": True,
            },
            cookie=cookie,
        )
        t = self.attendre(cookie, json.loads(b)["id"])
        self.assertEqual(t["statut"], "echec")
        self.assertIn("brouillons", t["erreur"])


if __name__ == "__main__":
    unittest.main()
