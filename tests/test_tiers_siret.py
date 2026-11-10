# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de « Compléter SIRET et TVA » (ADR-0013).

Annuaire de l'État et Odoo simulés : aucune requête ne sort du test.
"""

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from typing import Any
from unittest import mock

from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.secrets import ecrire_variable, nom_variable
from core.tiers_odoo import CibleTiers, annuler
from core.tiers_siret import (
    INTROUVABLE,
    SURE,
    ErreurSiret,
    controler,
    ecrire,
    identifiants_constat,
    lire_tiers,
    proposer,
)
from core.xml_sur import FauteXmlRpc
from interface import auth
from core.migration.injection import CibleOdoo
from core.odoo_source import ErreurSource
from interface.serveur import Application, Bases, creer_serveur
from interface.transferts import ErreurEcran
from tests.test_interface import MDP, FaussesBases, entete_obligatoire

# Société d'exemple : SIREN, SIRET et TVA fictifs (clés de contrôle valides).
SOCIETE_EXEMPLE = {
    "siren": "222222226",
    "nom_complet": "EXEMPLE SA (EXEMPLE)",
    "nom_raison_sociale": "EXEMPLE SA",
    "sigle": "EXEMPLE",
    "etat_administratif": "A",
    "tva": ["FR46222222226"],
    "siege": {
        "siret": "22222222600029",
        "code_postal": "75001",
        "adresse": "1 RUE DE L'EXEMPLE 75001 PARIS",
        "etat_administratif": "A",
    },
    "matching_etablissements": [
        {
            "siret": "22222222600128",
            "code_postal": "75001",
            "etat_administratif": "A",
            "adresse": "AUTRE SITE 75001 PARIS",
        }
    ],
}
FONDATION = {
    "siren": "444444442",
    "nom_complet": "FONDS DE DOTATION EXEMPLE",
    "nom_raison_sociale": "FONDS DE DOTATION EXEMPLE",
    "etat_administratif": "A",
    "tva": [],
    "siege": {"siret": "44444444200016", "code_postal": "75001"},
}
FERMEE = dict(SOCIETE_EXEMPLE, etat_administratif="C")


class FauxAnnuaire:
    """Annuaire simulé : réponses par nom cherché."""

    def __init__(self, reponses: dict[str, list[dict[str, Any]]]) -> None:
        """reponses : {nom: résultats}."""
        self.reponses = reponses
        self.appels: list[dict[str, Any]] = []

    def requete(
        self,
        methode: str,
        chemin: str,
        parametres: Any = None,
        corps: object = None,
    ) -> dict[str, Any]:
        """GET /search : résultats du nom (aucun si code postal inconnu)."""
        self.appels.append(dict(parametres))
        resultats = self.reponses.get(str(parametres["q"]), [])
        if parametres.get("code_postal") == "00000":
            resultats = []
        return {"results": resultats}


class FauxOdoo:
    """Odoo simulé : res.partner en mémoire, méthodes de CibleTiers."""

    def __init__(self, siret: bool = True) -> None:
        """Trois tiers sans identifiant, un déjà complété."""
        self.siret = siret
        self.fiches: dict[int, dict[str, Any]] = {
            8391: {"name": "EXEMPLE", "zip": "75001", "city": "Paris"},
            8390: {"name": "AUTRE SOCIETE", "zip": "", "city": ""},
            8159: {"name": "ABATTOIR ROMINOS", "zip": "00000", "city": ""},
            9000: {"name": "DEJA FAIT", "zip": "", "city": "", "vat": "FR1"},
        }
        for fiche in self.fiches.values():
            fiche.setdefault("vat", False)
            fiche.setdefault("company_registry", False)
            fiche.setdefault("siret", False)
        self.refuser: set[int] = set()

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Joue fields_get, read et write sur res.partner."""
        if methode not in CibleTiers.methodes_autorisees:
            raise PermissionError(methode)
        if methode == "fields_get":
            champs: dict[str, dict[str, Any]] = {
                "company_registry": {"type": "char"}
            }
            if self.siret:
                champs["siret"] = {"type": "char", "readonly": False}
            return champs
        if methode == "read":
            champs_demandes = (kwargs or {})["fields"]
            return [
                dict(
                    {cle: self.fiches[ident][cle] for cle in champs_demandes},
                    id=ident,
                )
                for ident in args[0]
                if ident in self.fiches
            ]
        ident = args[0][0]
        if ident in self.refuser:
            raise FauteXmlRpc(1, "ValidationError: numéro de TVA refusé")
        self.fiches[ident].update(args[1])
        return True


def annuaire_simule() -> FauxAnnuaire:
    """Annuaire des tests : EXEMPLE (2 réponses), AUTRE SOCIETE fermée."""
    return FauxAnnuaire(
        {"EXEMPLE": [SOCIETE_EXEMPLE, FONDATION], "AUTRE SOCIETE": [FERMEE]}
    )


class TestRegles(unittest.TestCase):
    """Contrôles, classement, écriture, annulation."""

    def test_controles_par_calcul(self) -> None:
        """Vérifie SIRET (Luhn, SIREN) et TVA (clé, SIREN)."""
        self.assertEqual(
            controler("22222222600029", "FR46222222226", "222222226"), []
        )
        self.assertIn(
            "SIRET invalide (clé de Luhn)",
            controler("22222222600020", "FR46222222226", "222222226"),
        )
        self.assertIn(
            "le SIRET n'appartient pas à ce SIREN",
            controler("44444444200016", "FR46222222226", "222222226"),
        )
        self.assertIn(
            "TVA fausse (clé ou SIREN)",
            controler("22222222600029", "FR47222222226", "222222226"),
        )
        self.assertEqual(
            controler("22222222600029", "", "222222226", False), []
        )
        self.assertEqual(
            identifiants_constat(
                ["A (id 3)", "B (id 3)", "sans", "C (id 12)"]
            ),
            [3, 12],
        )

    def test_propositions(self) -> None:
        """Vérifie sûre, à choisir, introuvable et la seconde recherche."""
        odoo = FauxOdoo()
        tiers = lire_tiers(odoo, [8391, 8390, 8159, 9000, 77])
        self.assertEqual(
            [un_tiers["id"] for un_tiers in tiers], [8391, 8390, 8159]
        )
        annuaire = annuaire_simule()
        propositions = proposer(tiers, annuaire, lambda duree: None)
        classes = [
            proposition_tiers["classe"] for proposition_tiers in propositions
        ]
        self.assertEqual(classes, [SURE, INTROUVABLE, INTROUVABLE])
        retenue = propositions[0]["candidates"][0]
        self.assertEqual(
            (retenue["siret"], retenue["tva"]),
            ("22222222600128", "FR46222222226"),
        )
        self.assertEqual(
            propositions[0]["candidates"][1]["controles"],
            ["TVA absente de l'annuaire"],
        )
        self.assertNotIn("code_postal", annuaire.appels[-1])
        with self.assertRaises(ErreurSiret):
            lire_tiers(odoo, [])

    def test_ecrire_puis_annuler(self) -> None:
        """Vérifie écriture tracée, fiches ignorées, refus et annulation."""
        odoo = FauxOdoo(siret=False)
        odoo.refuser.add(8390)
        with tempfile.TemporaryDirectory() as dossier:
            trace = os.path.join(dossier, "trace.jsonl")
            with self.assertRaises(ErreurSiret):
                ecrire(
                    odoo, [{"id": 8391, "siret": "1", "tva": ""}], "b", trace
                )
            bilan = ecrire(
                odoo,
                [
                    {
                        "id": 8391,
                        "siret": "22222222600029",
                        "tva": "FR46222222226",
                    },
                    {"id": 9000, "siret": "22222222600029", "tva": ""},
                    {"id": 8390, "siret": "22222222600029", "tva": ""},
                ],
                "base de test",
                trace,
            )
            self.assertEqual(bilan["ecrits"], [8391])
            self.assertEqual(bilan["ignores"], [9000])
            self.assertIn("TVA refusé", bilan["refus"][0]["cause"])
            self.assertEqual(
                odoo.fiches[8391]["company_registry"], "22222222600029"
            )
            odoo.fiches[8391]["vat"] = "FR46222222226"
            self.assertEqual(
                annuler(odoo, trace), {"remis": [8391], "ignores": []}
            )
            self.assertFalse(odoo.fiches[8391]["vat"])
            odoo.fiches[8391]["vat"] = "MODIFIE"
            self.assertEqual(annuler(odoo, trace)["ignores"], [8391])


class TestEcranSiret(unittest.TestCase):
    """Parcours complet par le serveur HTTP (Odoo et annuaire simulés)."""

    def setUp(self) -> None:
        """Interface, connexions Odoo (production et test), analyse simulée."""
        auth.N = 2**10
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        dossier = self._tmp.name
        secrets = os.path.join(dossier, "s", "connecteurs.env")
        self.app = Application(
            auth.hacher(MDP),
            os.path.join(dossier, "ui"),
            bases=FaussesBases(),
            fichier_secrets=secrets,
        )
        annuaire = self.app.transferts.annuaire
        parametres = {"url": "https://x", "base": "b", "utilisateur": "u"}
        self.test = annuaire.ajouter("odoo", "Client A test", parametres)["id"]
        self.prod = annuaire.ajouter(
            "odoo", "Client A production", parametres, self.test
        )["id"]
        self.sans_test = annuaire.ajouter("odoo", "Seule", parametres)["id"]
        self.couple = {
            "production": "connexion:" + self.prod,
            "test": "connexion:" + self.test,
        }
        for ident in (self.test, self.prod, self.sans_test):
            ecrire_variable(secrets, nom_variable(ident, "cle_api"), "k")
        self.odoo = {self.test: FauxOdoo(), self.prod: FauxOdoo()}

        def cible(connecteur: ConnecteurOdoo, classe: Any = None) -> FauxOdoo:
            """Odoo simulé de la connexion (repérée par son libellé)."""
            return self.odoo[
                self.prod if connecteur.parametres.get("prod") else self.test
            ]

        original = annuaire.ouvrir

        def ouvrir(ident: str) -> Any:
            """Connecteur réel, marqué production ou test."""
            connecteur = original(ident)
            connecteur.parametres["prod"] = "1" if ident == self.prod else ""
            return connecteur

        for remplacement in (
            mock.patch.object(ConnecteurOdoo, "cible", cible),
            mock.patch.object(annuaire, "ouvrir", ouvrir),
            mock.patch(
                "core.tiers_siret.ClientJson",
                lambda *arguments: annuaire_simule(),
            ),
        ):
            remplacement.start()
            self.addCleanup(remplacement.stop)
        self.analyse = "20261109-000000-abcdef"
        dossier_analyse = os.path.join(self.app.taches.dossier, self.analyse)
        os.makedirs(dossier_analyse)
        with open(
            os.path.join(dossier_analyse, "rapport.json"),
            "w",
            encoding="utf-8",
        ) as fichier:
            json.dump(
                {
                    "constats": [
                        {
                            "code": "TIERS_SANS_SIREN_TVA",
                            "elements": [
                                "EXEMPLE (id 8391)",
                                "AUTRE SOCIETE (id 8390)",
                            ],
                        }
                    ]
                },
                fichier,
            )
        self.app.taches._taches[self.analyse] = {
            "id": self.analyse,
            "action": "analyser",
            "statut": "terminee",
            "params": {},
            "fichiers": [],
        }
        self.serveur = creer_serveur(self.app, "127.0.0.1", 0)
        threading.Thread(
            target=self.serveur.serve_forever, daemon=True
        ).start()
        self.addCleanup(self.serveur.shutdown)
        reponse, _ = self.envoyer(
            "POST", "/api/connexion", {"mdp": MDP}, False
        )
        self.cookie = entete_obligatoire(reponse, "Set-Cookie").split(";")[0]

    def envoyer(
        self,
        methode: str,
        chemin: str,
        corps: Any = None,
        session: bool = True,
    ) -> tuple[http.client.HTTPResponse, Any]:
        """Requête JSON ; rend la réponse et le JSON reçu."""
        connexion = http.client.HTTPConnection(
            "127.0.0.1", self.serveur.server_address[1], timeout=10
        )
        entetes = {"X-Concorde": "1", "Content-Type": "application/json"}
        if session:
            entetes["Cookie"] = self.cookie
        connexion.request(
            methode,
            chemin,
            body=None if corps is None else json.dumps(corps).encode(),
            headers=entetes,
        )
        reponse = connexion.getresponse()
        contenu = reponse.read()
        connexion.close()
        return reponse, json.loads(contenu or b"{}")

    def tache(self, chemin: str, corps: Any) -> dict[str, Any]:
        """Lance une tâche et attend sa fin ; rend son état."""
        reponse, donnees = self.envoyer("POST", chemin, corps)
        self.assertEqual(reponse.status, 201, donnees)
        for _ in range(500):
            _, etat = self.envoyer("GET", "/api/taches/" + donnees["id"])
            if etat["statut"] not in ("en_attente", "en_cours"):
                fin: dict[str, Any] = etat
                return fin
            time.sleep(0.02)
        self.fail("tâche non terminée")

    def refus(self, chemin: str, corps: Any) -> str:
        """Requête refusée (400) ; rend la cause."""
        reponse, donnees = self.envoyer("POST", chemin, corps)
        self.assertEqual(reponse.status, 400, donnees)
        cause: str = donnees["erreur"]
        return cause

    def test_parcours(self) -> None:
        """Vérifie propositions, essai, feu vert, annulation, et les refus."""
        self.assertIn(
            "autre base",
            self.refus(
                "/api/siret",
                dict(
                    self.couple,
                    analyse=self.analyse,
                    test=self.couple["production"],
                ),
            ),
        )
        self.assertIn(
            "copie de test",
            self.refus(
                "/api/siret",
                {
                    "analyse": self.analyse,
                    "production": self.couple["production"],
                },
            ),
        )
        self.assertIn(
            "Analyse inconnue",
            self.refus("/api/siret", dict(self.couple, analyse="x")),
        )
        etat = self.tache(
            "/api/siret", dict(self.couple, analyse=self.analyse)
        )
        self.assertEqual(etat["statut"], "terminee", etat.get("erreur"))
        self.assertEqual(
            etat["resultat"]["classes"], {SURE: 1, INTROUVABLE: 1}
        )
        ident = etat["id"]
        _, donnees = self.envoyer("GET", "/api/siret/" + ident)
        self.assertEqual(donnees["connexion_test"], "Client A test")
        choix = [
            {"id": 8391, "siret": "22222222600128", "tva": "FR46222222226"}
        ]
        self.assertIn(
            "ne vient pas",
            self.refus(
                "/api/siret/%s/ecrire" % ident,
                {
                    "cible": "test",
                    "choix": [
                        {
                            "id": 8391,
                            "siret": "22222222600029",
                            "tva": "FR00000000000",
                        }
                    ],
                },
            ),
        )
        self.assertIn(
            "essai sur la copie",
            self.refus(
                "/api/siret/%s/ecrire" % ident,
                {
                    "cible": "production",
                    "choix": choix,
                    "confirmation": "Client A production",
                },
            ),
        )
        essai = self.tache(
            "/api/siret/%s/ecrire" % ident, {"cible": "test", "choix": choix}
        )
        self.assertEqual(essai["resultat"]["ecrits"], [8391])
        self.assertEqual(
            self.odoo[self.test].fiches[8391]["siret"], "22222222600128"
        )
        self.assertFalse(self.odoo[self.prod].fiches[8391]["siret"])
        self.assertIn(
            "mal retapé",
            self.refus(
                "/api/siret/%s/ecrire" % ident,
                {
                    "cible": "production",
                    "choix": choix,
                    "confirmation": "Client A",
                },
            ),
        )
        prod = self.tache(
            "/api/siret/%s/ecrire" % ident,
            {
                "cible": "production",
                "choix": choix,
                "confirmation": "Client A production",
            },
        )
        self.assertEqual(prod["resultat"]["ecrits"], [8391])
        self.assertEqual(
            self.odoo[self.prod].fiches[8391]["vat"], "FR46222222226"
        )
        annule = self.tache(
            "/api/siret/%s/annuler" % ident, {"cible": "production"}
        )
        self.assertEqual(annule["resultat"]["remis"], [8391])
        self.assertFalse(self.odoo[self.prod].fiches[8391]["vat"])
        self.assertIn(
            "Cible",
            self.refus("/api/siret/%s/annuler" % ident, {"cible": "autre"}),
        )
        reponse, _ = self.envoyer("GET", "/api/siret/" + ident, session=False)
        self.assertEqual(reponse.status, 401)

    def test_refus(self) -> None:
        """Vérifie les refus avant toute tâche : connexion, constat, choix."""
        fec = self.app.transferts.annuaire.ajouter(
            "fec", "Fichier", {"dossier": os.path.join(self._tmp.name, "f")}
        )["id"]
        self.assertIn(
            "base à compléter",
            self.refus(
                "/api/siret",
                dict(
                    self.couple,
                    analyse=self.analyse,
                    production="connexion:" + fec,
                ),
            ),
        )
        with self.assertRaises(ErreurEcran):
            self.app.siret.connecteur(fec)
        rapport = self.app.taches.rapport(self.analyse)
        if rapport is None:
            self.fail("rapport de l'analyse absent")
        with open(rapport, "w", encoding="utf-8") as fichier:
            json.dump({"constats": []}, fichier)
        self.assertIn(
            "aucun tiers",
            self.refus("/api/siret", dict(self.couple, analyse=self.analyse)),
        )
        self.assertIn(
            "pas encore prêts", self.refus("/api/siret/inconnue/ecrire", {})
        )
        ident = "propositions-simulees"
        self.app.taches._taches[ident] = {
            "id": ident,
            "action": "siret_proposer",
            "statut": "terminee",
            "params": dict(self.couple),
            "fichiers": [],
        }
        url = "/api/siret/%s/ecrire" % ident
        self.assertIn("Cible", self.refus(url, {"cible": "x", "choix": []}))
        self.assertIn(
            "Aucun tiers", self.refus(url, {"cible": "test", "choix": []})
        )
        self.assertIn(
            "mal formé", self.refus(url, {"cible": "test", "choix": ["x"]})
        )
        self.assertIn(
            "Rien à annuler",
            self.refus("/api/siret/%s/annuler" % ident, {"cible": "test"}),
        )
        reponse, _ = self.envoyer("POST", "/api/siret/x/inconnue", {})
        self.assertEqual(reponse.status, 404)


class CibleNotee(CibleOdoo):
    """Accès simulé (sans réseau) : garde les identifiants reçus."""

    def __init__(
        self, url: str, base: str, utilisateur: str, cle: str
    ) -> None:
        """Garde ce que Bases.acces_ecriture lui passe."""
        self.recu = (url, base, utilisateur, cle)


def identifiants_recus(acces: CibleOdoo) -> tuple[str, str, str, str]:
    """Identifiants gardés par un accès simulé."""
    if not isinstance(acces, CibleNotee):
        raise AssertionError("accès simulé attendu")
    return acces.recu


class TestBasesEcriture(unittest.TestCase):
    """Bases du sélecteur où CONCORDE peut écrire (ADR-0013, ADR-0014)."""

    def test_acces_ecriture(self) -> None:
        """Vérifie les bases du serveur et les Odoo distants."""
        bases = Bases()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONCORDE_TEST_BASE", None)
            with self.assertRaises(ErreurSource) as contexte:
                bases.acces_ecriture("sql:base_test", CibleNotee)
            self.assertIn("CONCORDE_TEST", str(contexte.exception))
        with mock.patch.dict(
            os.environ,
            {"CONCORDE_TEST_BASE": "base_test", "CONCORDE_TEST_MDP": "m"},
        ):
            acces = bases.acces_ecriture("sql:base_test", CibleNotee)
        self.assertEqual(
            identifiants_recus(acces)[1:], ("base_test", "admin", "m")
        )
        with self.assertRaises(ErreurSource) as contexte:
            bases.acces_ecriture("xmlrpc:inconnu", CibleNotee)
        self.assertIn("rebranchez", str(contexte.exception))
        bases._distants["xmlrpc:alb"] = {
            "id": "xmlrpc:alb",
            "nom": "base_production",
            "url": "https://client-a.example",
            "utilisateur": "u",
            "cle": "",
        }
        with self.assertRaises(ErreurSource):
            bases.acces_ecriture("xmlrpc:alb", CibleNotee)
        bases._distants["xmlrpc:alb"]["cle"] = "k"
        acces = bases.acces_ecriture("xmlrpc:alb", CibleNotee)
        self.assertEqual(
            identifiants_recus(acces),
            ("https://client-a.example", "base_production", "u", "k"),
        )


class TestBasesDuSelecteur(TestEcranSiret):
    """Une base du sélecteur (Odoo distant) choisie comme base à compléter."""

    def test_parcours(self) -> None:
        """Vérifie la liste des bases et des propositions sur une base."""
        bases = self.app.bases
        with mock.patch.object(
            type(bases),
            "lister",
            lambda instance, rafraichir=False: [
                {
                    "id": "xmlrpc:alb",
                    "nom": "base_production",
                    "libelle": "client a prod",
                    "ecriture_ok": True,
                },
                {
                    "id": "sql:autre",
                    "nom": "autre",
                    "libelle": "",
                    "ecriture_ok": False,
                },
            ],
        ), mock.patch.object(
            type(bases),
            "acces_ecriture",
            lambda instance, ident, classe=None: self.odoo[self.prod],
        ):
            _, sources = self.envoyer("GET", "/api/tiers/bases")
            self.assertEqual(
                sources[0],
                {"id": "base:xmlrpc:alb", "libelle": "client a prod"},
            )
            self.assertEqual(
                sorted(source["id"] for source in sources[1:]),
                sorted(
                    "connexion:" + ident
                    for ident in (self.test, self.prod, self.sans_test)
                ),
            )
            etat = self.tache(
                "/api/siret",
                {
                    "analyse": self.analyse,
                    "production": "base:xmlrpc:alb",
                    "test": "connexion:" + self.test,
                },
            )
            self.assertEqual(etat["statut"], "terminee", etat.get("erreur"))
            _, donnees = self.envoyer("GET", "/api/siret/" + etat["id"])
            self.assertEqual(
                (donnees["connexion"], donnees["connexion_test"]),
                ("client a prod", "Client A test"),
            )
        with self.assertRaises(ErreurEcran):
            self.app.siret.acces("autre:x")

    def test_refus(self) -> None:
        """Couverts par l'écran SIRET."""
