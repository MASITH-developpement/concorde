# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du bouton « Arrêter » et de l'arrêt d'urgence (ADR-0015)."""

import os
import tempfile
import threading
import time
import unittest
from typing import Any
from unittest import mock

from core.connecteurs import transfert
from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.pennylane import ConnecteurPennylane
from core.journal import Journal, TacheArretee
from core.montee_version import demandes, montee
from core.xml_sur import FauteXmlRpc
from interface import auth
from interface.montees import EcranMontees
from interface.serveur import Application, Taches
from tests import test_connecteurs, test_tiers_siret
from tests.test_connecteurs import FEC_SIMPLE
from tests.test_interface import MDP, FaussesBases
from tests.test_montee_pilotee import Atelier, sauvegarde_zip


class TestJournalArret(unittest.TestCase):
    """Le journal lève l'arrêt à son prochain message."""

    def test_arret_au_prochain_message(self) -> None:
        """Vérifie la levée, le message noté et le désarmement."""
        journal = Journal()
        journal.dire("avant")
        journal.demander_arret()
        self.assertTrue(journal.arret_demande)
        with self.assertRaises(TacheArretee) as contexte:
            journal.dire("étape 2")
        self.assertEqual(str(contexte.exception), "étape 2")
        self.assertEqual(journal.tout()[-1]["message"], "étape 2")
        journal.desarmer()
        journal.dire("après")
        self.assertFalse(issubclass(TacheArretee, Exception))


class TestTachesArretees(unittest.TestCase):
    """Taches : arrêt au point sûr, effacement, arrêt avant le départ."""

    def setUp(self) -> None:
        """Gestionnaire de tâches sur un dossier neuf."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.taches = Taches(self._tmp.name, FaussesBases())
        self.depart = threading.Event()
        self.liberer = threading.Event()
        self.defaites: list[str] = []

        def longue(tache: Any, journal: Journal, guardian: Any) -> None:
            """Tâche qui écrit, puis raconte jusqu'à ce qu'on la libère."""
            tache["ecrit"] = True
            self.depart.set()
            while not self.liberer.wait(0.01):
                journal.dire("lot suivant", "detail")

        def defaire(tache: Any, journal: Journal) -> dict[str, Any]:
            """Annulation simulée : note la tâche défaite."""
            self.defaites.append(tache["id"])
            journal.dire("effacé", "info")
            return {"remis": [1]}

        self.taches.travaux["transfert"] = longue
        self.taches.annulations["transfert"] = defaire

    def attendre(self, ident: str) -> dict[str, Any]:
        """Attend la fin d'une tâche ; rend son état."""
        for _ in range(500):
            tache = self.taches.obtenir(ident)
            if tache and tache["statut"] not in ("en_attente", "en_cours"):
                return tache
            time.sleep(0.01)
        self.fail("tâche non terminée")

    def test_arret_puis_effacement(self) -> None:
        """Vérifie le statut « arrêtée » et l'effacement de son travail."""
        ident = self.taches.lancer("transfert", None, "essai", "", {})
        self.assertTrue(self.depart.wait(5))
        self.taches.arreter(ident, "test")
        fin = self.attendre(ident)
        self.assertEqual(fin["statut"], "arretee")
        self.assertIn("lot suivant", fin["erreur"])
        self.assertEqual(fin["annulation"], {"remis": [1]})
        self.assertEqual(self.defaites, [ident])
        self.assertEqual(fin["arret_demande"]["par"], "test")
        with self.assertRaises(ValueError):
            self.taches.arreter(ident, "test")
        with self.assertRaises(ValueError):
            self.taches.arreter("inconnue", "test")

    def test_arret_avant_le_depart(self) -> None:
        """Vérifie qu'une tâche en attente de place ne démarre pas."""
        self.taches.travaux["feu_vert"] = self.taches.travaux["transfert"]
        premieres = [
            self.taches.lancer("transfert", None, "a", "", {}),
            self.taches.lancer("transfert", None, "b", "", {}),
        ]
        self.assertTrue(self.depart.wait(5))
        troisieme = self.taches.lancer("feu_vert", None, "c", "", {})
        self.taches.arreter(troisieme, "test")
        self.liberer.set()
        for ident in premieres:
            self.assertEqual(self.attendre(ident)["statut"], "terminee")
        fin = self.attendre(troisieme)
        self.assertEqual(fin["statut"], "arretee")
        self.assertNotIn("annulation", fin)

    def test_effacement_en_echec(self) -> None:
        """Vérifie qu'un effacement impossible est rendu, jamais muet."""

        def casse(tache: Any, journal: Journal) -> dict[str, Any]:
            """Annulation qui échoue."""
            raise OSError("disque en lecture seule")

        self.taches.annulations["transfert"] = casse
        ident = self.taches.lancer("transfert", None, "essai", "", {})
        self.assertTrue(self.depart.wait(5))
        self.taches.arreter(ident, "test")
        fin = self.attendre(ident)
        self.assertIn("lecture seule", fin["annulation"]["erreur"])
        del self.taches.annulations["transfert"]
        self.depart.clear()
        ident = self.taches.lancer("transfert", None, "essai", "", {})
        self.assertTrue(self.depart.wait(5))
        self.taches.arreter(ident, "test")
        self.assertIn("rien", self.attendre(ident)["annulation"])


class TestUrgence(unittest.TestCase):
    """Arrêt d'urgence : mot retapé, montée prévenue, fin du processus."""

    def test_arret_urgence(self) -> None:
        """Vérifie le dépôt du fichier d'urgence et l'arrêt du processus."""
        auth.N = 2**10
        with tempfile.TemporaryDirectory() as dossier:
            for nom in ("depots", "demandes"):
                os.makedirs(os.path.join(dossier, "volume", nom))
            ecran = EcranMontees(
                Journal(),
                os.path.join(dossier, "volume"),
                os.path.join(dossier, "etats"),
                {},
            )
            app = Application(
                auth.hacher(MDP),
                os.path.join(dossier, "ui"),
                bases=FaussesBases(),
                fichier_secrets=os.path.join(dossier, "s.env"),
                montees=ecran,
            )
            fin = threading.Event()
            codes: list[int] = []

            def quitter(code: int) -> None:
                """Fin du processus simulée."""
                codes.append(code)
                fin.set()

            app.quitter = quitter
            vrai_minuteur = threading.Timer
            with mock.patch("interface.serveur.threading.Timer") as minuterie:
                minuterie.side_effect = lambda delai, fonction, arguments: (
                    vrai_minuteur(0.01, fonction, arguments)
                )
                reponse = app.declencher_urgence("test")
            self.assertTrue(fin.wait(5))
            self.assertEqual(codes, [1])
            self.assertTrue(reponse["montee"])
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        dossier, "volume", "demandes", montee.ARRET_URGENCE
                    )
                )
            )
            ecran.arreter("M20261109000000-abcd")
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        dossier,
                        "volume",
                        "demandes",
                        "arret-M20261109000000-abcd",
                    )
                )
            )
            with self.assertRaises(ValueError):
                ecran.arreter("../etc")
            sans_service = EcranMontees(
                Journal(), os.path.join(dossier, "absent"), dossier, {}
            )
            self.assertFalse(sans_service.prevenir_urgence())


class TestDefaireTransfert(test_connecteurs.TestTransfert):
    """Transfert FEC -> FEC défait : essai, puis feu vert."""

    def test_defaire(self) -> None:
        """Vérifie l'effacement des FEC et la destination remise en attente."""
        source, destination = self.connexions(*FEC_SIMPLE)
        etat = self.creer(self.demande(source, destination))
        sortie = os.path.join(self.dossier, "sortie")
        essais = os.path.join(sortie, "essais")
        self.assertTrue(os.listdir(essais))
        bilan = transfert.defaire(
            self.annuaire_connexions,
            etat["id"],
            [destination],
            False,
            self.transferts,
            Journal(),
        )
        self.assertEqual(bilan[destination]["test"][0]["laissees"], [])
        self.assertEqual(os.listdir(essais), [])
        etat = self.creer(self.demande(source, destination))
        fin = self.feu_vert(etat["id"], destination, "Sortie client A")
        self.assertEqual(fin["statut"], transfert.TRANSFEREE)
        bilan = transfert.defaire(
            self.annuaire_connexions,
            etat["id"],
            [destination],
            True,
            self.transferts,
            Journal(),
        )
        self.assertGreater(bilan[destination]["production"]["supprimees"], 0)
        self.assertEqual(
            [nom for nom in os.listdir(sortie) if nom != "essais"], []
        )
        relu = transfert.charger(etat["id"], self.transferts)
        self.assertEqual(
            relu["destinations"][destination]["statut"], transfert.ATTENTE
        )


class FauxOdooSuppression:
    """Odoo simulé : écritures d'un transfert, dont une protégée."""

    def __init__(self) -> None:
        """Deux écritures validées, une en brouillon."""
        self.ecritures = {
            1: {"ref": "CONCORDE/T1/VE/1", "state": "posted"},
            2: {"ref": "CONCORDE/T1/VE/2", "state": "posted"},
            3: {"ref": "CONCORDE/T1/OD/1", "state": "draft"},
        }
        self.protegees = {2}

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """search_read, button_draft, unlink sur account.move."""
        if methode == "search_read":
            return [
                dict(valeurs, id=ident)
                for ident, valeurs in self.ecritures.items()
            ]
        ident = args[0][0]
        if ident in self.protegees:
            raise FauteXmlRpc(1, "UserError: journal protégé (inaltérabilité)")
        if methode == "button_draft":
            self.ecritures[ident]["state"] = "draft"
        else:
            del self.ecritures[ident]
        return True


class TestSupprimer(unittest.TestCase):
    """Effacement par les connecteurs."""

    def test_odoo(self) -> None:
        """Vérifie brouillon, suppression, et écriture protégée nommée."""
        faux = FauxOdooSuppression()
        connecteur = ConnecteurOdoo(
            {"url": "https://x", "base": "b", "utilisateur": "u"},
            {"cle_api": "k"},
        )
        with mock.patch.object(
            ConnecteurOdoo, "cible", lambda instance, classe=None: faux
        ):
            bilan = connecteur.supprimer("CONCORDE/T1", Journal())
        self.assertEqual(bilan["supprimees"], 2)
        self.assertEqual(len(bilan["laissees"]), 1)
        self.assertIn("inaltérabilité", bilan["laissees"][0])
        self.assertEqual(list(faux.ecritures), [2])

    def test_logiciel_sans_effacement(self) -> None:
        """Vérifie qu'un logiciel qui ne sait pas effacer est nommé."""
        bilan = ConnecteurPennylane({}, {"jeton": "j"}).supprimer(
            "CONCORDE/T1", Journal()
        )
        self.assertEqual(bilan["supprimees"], 0)
        self.assertIn("à la main", bilan["laissees"][0])


class TestMonteeArretee(Atelier):
    """Montée arrêtée : saut coupé, copie effacée ; urgence."""

    def service(self) -> demandes.ServiceMontee:
        """Service de montée sur un volume simulé."""
        donnees = os.path.join(self._tmp.name, "volume")
        for nom in ("depots", "demandes", "livraisons"):
            os.makedirs(os.path.join(donnees, nom), exist_ok=True)
        service = demandes.ServiceMontee(
            donnees,
            os.path.join(self._tmp.name, "etats"),
            self.openupgrade,
            self.docker,
            (os.getuid(), os.getgid()),
        )
        self.racine = service.racine
        return service

    def test_arret_pendant_un_saut(self) -> None:
        """Vérifie le saut coupé, le statut et la copie effacée."""
        service = self.service()
        nom = "a" * 32 + ".zip"
        sauvegarde_zip(os.path.join(service.depots, nom))
        demandes.deposer_demande(
            service.demandes, "creer", depot=nom, arrivee=17
        )
        service.traiter_file()
        ident = os.listdir(service.racine)[0]
        self.docker.duree_saut = 0.3
        demandes.deposer_demande(service.demandes, "circuit", montee=ident)
        arret = os.path.join(service.demandes, montee.PREFIXE_ARRET + ident)

        def demander_arret() -> None:
            """Dépose le fichier d'arrêt pendant le premier saut."""
            time.sleep(0.15)
            with open(arret, "w", encoding="utf-8") as fichier:
                fichier.write(ident)

        threading.Thread(target=demander_arret).start()
        with mock.patch.object(montee, "SURVEILLANCE_S", 0.05):
            service.traiter_file()
        etat = montee.charger(service.racine, ident)
        self.assertEqual(etat["statut"], montee.ARRETEE)
        self.assertTrue(
            any(argv[1] == "kill" for argv in self.docker.commandes)
        )
        self.assertFalse(
            os.path.exists(os.path.join(service.racine, ident, "donnees"))
        )
        self.assertFalse(os.path.exists(arret))

    def test_arret_entre_deux_etapes_et_urgence(self) -> None:
        """Vérifie l'arrêt avant la photo, puis l'urgence qui vide la file."""
        conduite = self.nouvelle()
        conduite.arrets = os.path.join(self._tmp.name, "arrets")
        os.makedirs(conduite.arrets)
        with open(
            os.path.join(conduite.arrets, montee.ARRET_URGENCE),
            "w",
            encoding="utf-8",
        ) as fichier:
            fichier.write("urgence")
        self.assertEqual(conduite.arret_demande(), "urgence")
        self.assertEqual(conduite.circuit(), montee.ARRETEE)
        service = self.service()
        demandes.deposer_demande(
            service.demandes, "circuit", montee=conduite.etat["id"]
        )
        with open(
            os.path.join(service.demandes, montee.ARRET_URGENCE),
            "w",
            encoding="utf-8",
        ) as fichier:
            fichier.write("urgence")
        self.assertEqual(service.traiter_file(), 0)
        self.assertEqual(os.listdir(service.demandes), [])
        self.assertIsNone(
            montee.Montee(conduite.racine, conduite.etat["id"]).arret_demande()
        )


class TestRoutesEtTiers(test_tiers_siret.TestEcranSiret):
    """Routes d'arrêt par HTTP, et écriture SIRET défaite."""

    def test_parcours(self) -> None:
        """Vérifie l'essai SIRET défait par l'annulation de la tâche."""
        etat = self.tache(
            "/api/siret", dict(self.couple, analyse=self.analyse)
        )
        choix = [
            {"id": 8391, "siret": "67362039900125", "tva": "FR69673620399"}
        ]
        essai = self.tache(
            "/api/siret/%s/ecrire" % etat["id"],
            {"cible": "test", "choix": choix},
        )
        self.assertEqual(
            self.odoo[self.test].fiches[8391]["siret"], "67362039900125"
        )
        bilan = self.app.siret._defaire_ecriture(essai, Journal())
        self.assertEqual(bilan["remis"], [8391])
        self.assertFalse(self.odoo[self.test].fiches[8391]["siret"])
        essai["id"] = "jamais-ecrite"
        self.assertEqual(
            self.app.siret._defaire_ecriture(essai, Journal())["remis"], []
        )

    def test_refus(self) -> None:
        """Vérifie les routes : tâche finie, mot d'urgence faux puis juste."""
        self.assertIn(
            "pas en cours", self.refus("/api/taches/inconnue/arreter", {})
        )
        self.assertIn(
            "ARRÊT", self.refus("/api/urgence", {"confirmation": "x"})
        )
        appels: list[int] = []
        self.app.quitter = appels.append
        # Jamais les dossiers réels du service de montée du serveur.
        self.app.montees = EcranMontees(
            Journal(),
            os.path.join(self._tmp.name, "volume-essai"),
            os.path.join(self._tmp.name, "etats-essai"),
            {},
        )
        with mock.patch("interface.serveur.threading.Timer") as minuterie:
            reponse, donnees = self.envoyer(
                "POST", "/api/urgence", {"confirmation": "ARRÊT"}
            )
        self.assertEqual(reponse.status, 202)
        self.assertTrue(donnees["redemarrage"])
        minuterie.assert_called_once_with(2.0, appels.append, (1,))
