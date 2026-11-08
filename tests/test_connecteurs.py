# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du socle des transferts entre logiciels (ADR-0008)."""

import io
import os
import re
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar
from unittest import mock

from core.connecteurs import registre, transfert
from core.migration import filtres as module_filtres
from core.connecteurs.base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    ResultatEcriture,
)
from core.connecteurs.connexions import Annuaire, ErreurAnnuaire
from core.connecteurs.fec import (
    ConnecteurFec,
    dossier_reference,
    retirer_hors_periode,
)
from core.connecteurs.secrets import (
    ErreurSecrets,
    ecrire_variable,
    lire_secrets,
    nom_variable,
    secrets_connexion,
)
from core.connecteurs.transfert import (
    ATTENTE,
    BLOQUEE,
    SANS_TEST,
    TRANSFEREE,
    DemandeTransfert,
    ErreurTransfert,
)
from core.explications import CATALOGUE
from core.guardian import Guardian
from core.journal import Journal
from core.migration.connecteur_fec import lire_fec
from core.migration.filtres import ResultatFiltres
from core.migration.lot import Lot
from scripts import concorde_connexion
from tests.outils import BASE, RACINE_DEPOT, fec, ligne_fec

AUJ = date(2026, 11, 8)


class ConnecteurFaux(Connecteur):
    """Logiciel à API simulé : écrit en mémoire, sans environnement de test.

    Paramètre `refuser` : l'écriture rend une erreur (refus du logiciel).
    """

    logiciel = "faux"
    libelle = "Logiciel simulé"
    capacites: ClassVar[CapacitesConnecteur] = {
        "lecture": None,
        "ecriture": "api",
    }
    secrets_requis = ("jeton",)
    ecrits: ClassVar[dict[str, Lot]] = {}

    def tester(self, journal: Journal) -> InfoConnexion:
        """Rend une société fictive."""
        return {
            "logiciel": self.logiciel,
            "societe": "Société simulée",
            "siren": "123456789",
            "devise": "EUR",
            "version": "v1",
        }

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Garde le lot en mémoire, ou refuse si `refuser`."""
        erreurs = (
            ["refusé par le logiciel"]
            if self.parametres.get("refuser")
            else []
        )
        if not essai and not erreurs:
            self.ecrits[reference] = lot
        return {
            "essai": essai,
            "ecritures_a_creer": len(lot.ecritures()),
            "ecritures_deja_presentes": 0,
            "erreurs": erreurs,
            "fichiers": {},
        }

    def relire(self, reference: str, journal: Journal) -> Lot:
        """Rend le lot écrit sous la référence."""
        return self.ecrits[reference]


class ConnecteurRefusFinal(ConnecteurFaux):
    """Logiciel simulé qui accepte l'essai et le test, refuse le transfert.

    Avec `refuser`, seule l'écriture réelle sous la référence finale
    (sans « /test ») est refusée.
    """

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Refuse seulement l'écriture réelle finale si `refuser`."""
        final = not essai and "/test" not in reference
        if final and self.parametres.get("refuser"):
            return {
                "essai": essai,
                "ecritures_a_creer": len(lot.ecritures()),
                "ecritures_deja_presentes": 0,
                "erreurs": ["refusé par le logiciel"],
                "fichiers": {},
            }
        if not essai:
            self.ecrits[reference] = lot
        return {
            "essai": essai,
            "ecritures_a_creer": len(lot.ecritures()),
            "ecritures_deja_presentes": 0,
            "erreurs": [],
            "fichiers": {},
        }


class Bac(unittest.TestCase):
    """Dossier temporaire, annuaire et secrets propres à chaque test."""

    def setUp(self) -> None:
        """Crée le dossier, l'annuaire, et branche le logiciel simulé."""
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = self._tmp.name
        self.secrets = os.path.join(self.dossier, "connecteurs.env")
        self.annuaire_connexions = Annuaire(
            os.path.join(self.dossier, "connexions.json"), self.secrets
        )
        self.transferts = os.path.join(self.dossier, "transferts")
        self.guardian = Guardian(os.path.join(self.dossier, "guardian"))
        registre.REGISTRE["faux"] = ConnecteurFaux
        ConnecteurFaux.ecrits = {}

    def tearDown(self) -> None:
        """Débranche le logiciel simulé et efface le dossier."""
        registre.REGISTRE.pop("faux", None)
        self._tmp.cleanup()

    def deposer(self, *lignes: str, nom: str = "FEC.txt") -> str:
        """Dépose un FEC dans le dossier ; rend son chemin."""
        chemin = os.path.join(self.dossier, nom)
        with open(chemin, "wb") as fichier:
            fichier.write(fec(*lignes))
        return chemin

    def demande(
        self,
        source: str,
        *destinations: str,
        du: str | None = None,
        au: str | None = None,
        filtres: list[dict[str, Any]] | None = None,
        identique: dict[str, bool] | None = None,
    ) -> DemandeTransfert:
        """Demande de transfert, comptes repris à l'identique par défaut."""
        return {
            "source": source,
            "destinations": list(destinations),
            "du": du,
            "au": au,
            "filtres": filtres or [],
            "tables": {},
            "identique": (
                {ident_destination: True for ident_destination in destinations}
                if identique is None
                else identique
            ),
        }


class TestSecrets(Bac):
    """Fichier de secrets : droits, format, écriture."""

    def test_ecriture_puis_lecture(self) -> None:
        """Vérifie l'écriture en 600, le remplacement et la lecture."""
        ecrire_variable(self.secrets, "CONCORDE_CNX_A_JETON", "un")
        ecrire_variable(self.secrets, "CONCORDE_CNX_A_JETON", "deux")
        ecrire_variable(self.secrets, "AUTRE", "x")
        self.assertEqual(stat.S_IMODE(os.stat(self.secrets).st_mode), 0o600)
        self.assertEqual(
            lire_secrets(self.secrets),
            {"CONCORDE_CNX_A_JETON": "deux", "AUTRE": "x"},
        )
        self.assertEqual(
            secrets_connexion(
                "a", ("jeton", "cle"), lire_secrets(self.secrets)
            ),
            {"jeton": "deux"},
        )

    def test_absent_vide(self) -> None:
        """Vérifie qu'un fichier absent ne contient aucun secret."""
        self.assertEqual(lire_secrets(self.secrets), {})

    def test_refus_droits_ouverts(self) -> None:
        """Vérifie le refus d'un fichier lisible par d'autres comptes."""
        ecrire_variable(self.secrets, "A", "secret-tres-prive")
        os.chmod(self.secrets, 0o644)
        with self.assertRaises(ErreurSecrets) as contexte:
            lire_secrets(self.secrets)
        self.assertIn("chmod 600", str(contexte.exception))
        self.assertNotIn("secret-tres-prive", str(contexte.exception))

    def test_ligne_invalide_sans_valeur_dans_le_message(self) -> None:
        """Vérifie que l'erreur donne la ligne, jamais son contenu."""
        with open(self.secrets, "w", encoding="utf-8") as fichier:
            fichier.write("# commentaire\n\nA=1\nvaleur-secrete-sans-nom\n")
        os.chmod(self.secrets, 0o600)
        with self.assertRaises(ErreurSecrets) as contexte:
            lire_secrets(self.secrets)
        self.assertIn("ligne 4", str(contexte.exception))
        self.assertNotIn("valeur-secrete", str(contexte.exception))

    def test_noms_et_valeurs_refuses(self) -> None:
        """Vérifie le refus d'un nom invalide ou d'un retour à la ligne."""
        self.assertEqual(
            nom_variable("pennylane_3f2a9c", "jeton"),
            "CONCORDE_CNX_PENNYLANE_3F2A9C_JETON",
        )
        with self.assertRaises(ErreurSecrets):
            nom_variable("a-b", "jeton")
        with self.assertRaises(ErreurSecrets):
            ecrire_variable(self.secrets, "minuscule", "x")
        with self.assertRaises(ErreurSecrets):
            ecrire_variable(self.secrets, "A", "x\nB=y")


class TestAnnuaire(Bac):
    """Annuaire des connexions : jamais de secret, plusieurs connexions."""

    def test_ajout_relecture_retrait(self) -> None:
        """Vérifie l'ajout, la persistance, le test et le retrait."""
        test = self.annuaire_connexions.ajouter(
            "fec", "Essais", {"dossier": self.dossier + "/e"}
        )
        vraie = self.annuaire_connexions.ajouter(
            "fec", "Client A", {"dossier": self.dossier + "/a"}, test["id"]
        )
        self.assertTrue(re.match(r"^fec_[0-9a-f]{6}$", vraie["id"]))
        relu = Annuaire(self.annuaire_connexions.chemin, self.secrets)
        self.assertEqual(
            [fichier["libelle"] for fichier in relu.lister()],
            ["Client A", "Essais"],
        )
        with self.assertRaises(ErreurAnnuaire):
            relu.retirer(test["id"])  # sert de test à « Client A »
        relu.retirer(vraie["id"])
        relu.retirer(test["id"])
        self.assertEqual(relu.lister(), [])
        with self.assertRaises(ErreurAnnuaire):
            relu.retirer(test["id"])
        with self.assertRaises(ErreurAnnuaire):
            relu.obtenir(test["id"])

    def test_copies_independantes(self) -> None:
        """Vérifie qu'une fiche rendue ne modifie pas l'annuaire."""
        fiche = self.annuaire_connexions.ajouter(
            "fec", "A", {"dossier": self.dossier + "/a"}
        )
        fiche["parametres"]["dossier"] = "/ailleurs"
        self.annuaire_connexions.lister()[0]["libelle"] = "B"
        self.assertEqual(
            self.annuaire_connexions.obtenir(fiche["id"])["parametres"],
            {"dossier": self.dossier + "/a"},
        )
        self.assertEqual(self.annuaire_connexions.lister()[0]["libelle"], "A")

    def test_refus(self) -> None:
        """Vérifie les refus : secret en paramètre, logiciel, libellé, test."""
        with self.assertRaises(ErreurAnnuaire) as contexte:
            self.annuaire_connexions.ajouter(
                "faux", "X", {"api_key": "abc", "url": "u"}
            )
        self.assertIn("api_key", str(contexte.exception))
        self.assertNotIn("abc", str(contexte.exception))
        for nom in ("jeton", "Mot_De_Passe", "client_secret", "clé"):
            with self.assertRaises(ErreurAnnuaire):
                self.annuaire_connexions.ajouter("faux", "X", {nom: "v"})
        with self.assertRaises(ErreurConnexion):
            self.annuaire_connexions.ajouter("inconnu", "X", {})
        with self.assertRaises(ErreurAnnuaire):
            self.annuaire_connexions.ajouter("fec", "  ", {})
        faux = self.annuaire_connexions.ajouter("faux", "F", {})
        with self.assertRaises(ErreurAnnuaire):
            self.annuaire_connexions.ajouter("fec", "A", {}, faux["id"])
        with self.assertRaises(ErreurAnnuaire):
            self.annuaire_connexions.ajouter("fec", "A", {}, "fec_absent")

    def test_ouvrir_avec_ses_seuls_secrets(self) -> None:
        """Vérifie que chaque connecteur ne reçoit que son secret."""
        connexion_a = self.annuaire_connexions.ajouter("faux", "A", {})
        connexion_b = self.annuaire_connexions.ajouter("faux", "B", {})
        with self.assertRaises(ErreurConnexion) as contexte:
            self.annuaire_connexions.ouvrir(connexion_a["id"])
        self.assertIn("secret jeton", str(contexte.exception))
        ecrire_variable(
            self.secrets, nom_variable(connexion_a["id"], "jeton"), "ja"
        )
        ecrire_variable(
            self.secrets, nom_variable(connexion_b["id"], "jeton"), "jb"
        )
        ouvert = self.annuaire_connexions.ouvrir(connexion_a["id"])
        self.assertEqual(ouvert._secrets, {"jeton": "ja"})
        info = self.annuaire_connexions.tester(connexion_a["id"], Journal())
        self.assertEqual(info["siren"], "123456789")
        fiche = self.annuaire_connexions.obtenir(connexion_a["id"])
        self.assertEqual(fiche["derniere_info"], info)
        self.assertIsNotNone(fiche["dernier_test"])
        with open(
            self.annuaire_connexions.chemin, encoding="utf-8"
        ) as fichier:
            self.assertNotIn("ja", fichier.read().replace("jamais", ""))


class TestConnecteurFec(Bac):
    """Connecteur FEC : fichier déposé, FEC produit, idempotence."""

    def test_tester(self) -> None:
        """Vérifie le test du fichier, du dossier, et les refus."""
        chemin = self.deposer(*BASE, nom="123456789FEC20251231.txt")
        info = ConnecteurFec({"chemin": chemin}).tester(Journal())
        self.assertEqual(info["siren"], "123456789")
        info = ConnecteurFec({"dossier": self.dossier + "/d"}).tester(
            Journal()
        )
        self.assertEqual(info["siren"], "")
        for parametres in ({"chemin": self.dossier + "/absent"}, {}):
            with self.assertRaises(ErreurConnexion):
                ConnecteurFec(parametres).tester(Journal())
        with mock.patch("os.access", return_value=False):
            with self.assertRaises(ErreurConnexion):
                ConnecteurFec({"dossier": self.dossier}).tester(Journal())

    def test_lire_periode(self) -> None:
        """Vérifie que les écritures hors période sont gardées à part."""
        instance_fec = ConnecteurFec({"chemin": self.deposer(*BASE)})
        lot = instance_fec.lire(
            {"du": date(2025, 1, 10), "au": date(2025, 1, 20)}, Journal()
        )
        self.assertEqual(lot.totaux()["ecritures"], 2)  # VE/2 et BQ/3
        self.assertEqual(len(lot.retirees), 4)
        self.assertEqual(
            {motif for _, motif in lot.retirees}, {"hors période"}
        )
        tout = instance_fec.lire({"du": None, "au": None}, Journal())
        self.assertEqual(
            retirer_hors_periode(tout, {"du": None, "au": None}), 0
        )

    def test_lire_refus(self) -> None:
        """Vérifie les refus : pas de fichier, fichier absent ou vide."""
        with self.assertRaises(ErreurConnexion):
            ConnecteurFec({}).lire({"du": None, "au": None}, Journal())
        with self.assertRaises(ErreurConnexion):
            ConnecteurFec({"chemin": self.dossier + "/absent"}).lire(
                {"du": None, "au": None}, Journal()
            )
        vide = os.path.join(self.dossier, "vide.txt")
        open(vide, "wb").close()
        with self.assertRaises(ErreurConnexion):
            ConnecteurFec({"chemin": vide}).lire(
                {"du": None, "au": None}, Journal()
            )

    def test_ecrire_essai_idempotence_relire(self) -> None:
        """Vérifie l'essai, l'écriture, la non-réécriture et la relecture."""
        lot = lire_fec(fec(*BASE))
        sortie = ConnecteurFec({"dossier": os.path.join(self.dossier, "s")})
        essai = sortie.ecrire(lot, "CONCORDE/T1", True, Journal())
        self.assertEqual(essai["ecritures_a_creer"], 4)
        self.assertFalse(os.path.exists(os.path.join(self.dossier, "s")))
        ecrit = sortie.ecrire(lot, "CONCORDE/T1", False, Journal())
        self.assertEqual(ecrit["erreurs"], [])
        self.assertTrue(
            ecrit["fichiers"]["fec"].endswith("CONCORDE_T1/FEC.txt")
        )
        encore = sortie.ecrire(lot, "CONCORDE/T1", False, Journal())
        self.assertEqual(
            (encore["ecritures_a_creer"], encore["ecritures_deja_presentes"]),
            (0, 4),
        )
        self.assertEqual(
            sortie.relire("CONCORDE/T1", Journal()).totaux(), lot.totaux()
        )
        with self.assertRaises(ErreurConnexion):
            sortie.relire("CONCORDE/T2", Journal())

    def test_ecrire_refus(self) -> None:
        """Vérifie : pas de dossier, référence vide, lot déséquilibré."""
        lot = lire_fec(fec(*BASE))
        with self.assertRaises(ErreurConnexion):
            ConnecteurFec({}).ecrire(lot, "R", False, Journal())
        with self.assertRaises(ErreurConnexion):
            dossier_reference(self.dossier, "///")
        desequilibre = lire_fec(fec(BASE[0]))
        sortie = ConnecteurFec({"dossier": self.dossier})
        ecrit = sortie.ecrire(desequilibre, "R", False, Journal())
        self.assertTrue(ecrit["erreurs"])
        self.assertNotIn("fec", ecrit["fichiers"])

    def test_environnement_test_et_capacites(self) -> None:
        """Vérifie le dossier d'essais et les opérations non prévues."""
        test = ConnecteurFec({"dossier": self.dossier}).environnement_test()
        if test is None:
            self.fail("environnement de test attendu")
        self.assertEqual(
            test.parametres["dossier"], os.path.join(self.dossier, "essais")
        )
        self.assertIsNone(ConnecteurFec({"chemin": "x"}).environnement_test())
        faux = ConnecteurFaux({}, {"jeton": "j"})
        self.assertIsNone(faux.environnement_test())
        with self.assertRaises(ErreurConnexion):
            faux.lire({"du": None, "au": None}, Journal())
        with self.assertRaises(ErreurConnexion):
            Connecteur.ecrire(faux, lire_fec(fec(*BASE)), "R", True, Journal())
        with self.assertRaises(ErreurConnexion):
            Connecteur.relire(faux, "R", Journal())


class TestTransfert(Bac):
    """Procédure en 7 étapes, destinations indépendantes."""

    def connexions(self, *lignes: str) -> tuple[str, str]:
        """Source FEC déposée et destination FEC ; rend leurs identifiants."""
        source = self.annuaire_connexions.ajouter(
            "fec", "Sage 100 client A", {"chemin": self.deposer(*lignes)}
        )
        destination = self.annuaire_connexions.ajouter(
            "fec",
            "Sortie client A",
            {"dossier": os.path.join(self.dossier, "sortie")},
        )
        return source["id"], destination["id"]

    def creer(self, demande: DemandeTransfert) -> transfert.EtatTransfert:
        """Crée le transfert dans le dossier du test."""
        return transfert.creer(
            self.annuaire_connexions,
            demande,
            self.transferts,
            AUJ,
            Journal(),
            self.guardian,
        )

    def feu_vert(
        self, ident: str, destination: str, confirmation: str
    ) -> transfert.EtatDestination:
        """Donne le feu vert (sauvegarde du jour)."""
        return transfert.donner_feu_vert(
            self.annuaire_connexions,
            ident,
            destination,
            confirmation,
            AUJ,
            "Stéphane Moreau",
            self.transferts,
            AUJ,
            Journal(),
            self.guardian,
        )

    def test_parcours_complet(self) -> None:
        """Vérifie rapport, attente, feu vert, nouveau test, transfert."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(self.demande(source, destination))
        dest = etat["destinations"][destination]
        self.assertEqual(dest["statut"], ATTENTE)
        self.assertEqual(
            [
                dest["etapes"][nom_etape]["statut"]
                for nom_etape in transfert.ETAPES
            ],
            ["verte"] * 4 + ["non_jouee"] * 3,
        )
        self.assertTrue(os.path.isfile(str(etat["photo_source"])))
        sortie = os.path.join(self.dossier, "sortie")
        self.assertEqual(os.listdir(sortie), ["essais"])  # rien de vrai écrit
        self.assertEqual(
            transfert.charger(etat["id"], self.transferts)["destinations"],
            etat["destinations"],
        )
        fin = self.feu_vert(etat["id"], destination, " Sortie client A ")
        self.assertEqual(fin["statut"], TRANSFEREE)
        self.assertEqual(
            fin["etapes"]["feu_vert"]["infos"]["par"], "Stéphane Moreau"
        )
        relu = ConnecteurFec({"dossier": sortie}).relire(
            dest["reference"], Journal()
        )
        self.assertEqual(relu.totaux(), lire_fec(fec(*BASE)).totaux())
        self.assertEqual(
            sorted(os.listdir(os.path.join(sortie, "essais"))),
            [
                "CONCORDE_%s_test1" % etat["id"],
                "CONCORDE_%s_test2" % etat["id"],
            ],
        )
        with self.assertRaises(ErreurTransfert):  # déjà transférée
            self.feu_vert(etat["id"], destination, "Sortie client A")

    def test_feu_vert_refuse(self) -> None:
        """Vérifie les refus du feu vert : rien n'est écrit."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(self.demande(source, destination))
        with self.assertRaises(ErreurTransfert):
            self.feu_vert(etat["id"], destination, "Sortie client B")
        with self.assertRaises(ErreurTransfert):
            self.feu_vert(etat["id"], "fec_absent", "x")
        with self.assertRaises(ErreurTransfert):
            self.feu_vert("T-absent", destination, "x")
        with self.assertRaises(ErreurTransfert):
            transfert.donner_feu_vert(
                self.annuaire_connexions,
                etat["id"],
                destination,
                "Sortie client A",
                date(2026, 11, 9),
                "Stéphane Moreau",
                self.transferts,
                AUJ,
            )
        self.assertEqual(
            os.listdir(os.path.join(self.dossier, "sortie")), ["essais"]
        )

    def test_source_changee_avant_le_feu_vert(self) -> None:
        """Vérifie le blocage si la source a changé depuis le rapport."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(self.demande(source, destination))
        self.deposer(*BASE[:7])  # écriture OD/4 retirée de la source
        fin = self.feu_vert(etat["id"], destination, "Sortie client A")
        self.assertEqual(fin["statut"], BLOQUEE)
        self.assertIn("a changé", fin["etapes"]["nouveau_test"]["erreur"])
        self.assertEqual(
            os.listdir(os.path.join(self.dossier, "sortie")), ["essais"]
        )

    def test_nouveau_test_bloque(self) -> None:
        """Vérifie le blocage si la source ne passe plus les contrôles."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(self.demande(source, destination))
        self.deposer(*BASE, ligne_fec("OD", "5", "20250131", "0", "1,00"))
        fin = self.feu_vert(etat["id"], destination, "Sortie client A")
        self.assertEqual(fin["statut"], BLOQUEE)
        self.assertIn("ne passe plus", fin["etapes"]["nouveau_test"]["erreur"])

    def test_source_disparue_avant_le_feu_vert(self) -> None:
        """Vérifie le blocage si la source ne se lit plus."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(self.demande(source, destination))
        os.remove(
            self.annuaire_connexions.obtenir(source)["parametres"]["chemin"]
        )
        fin = self.feu_vert(etat["id"], destination, "Sortie client A")
        self.assertIn(
            "Source illisible", fin["etapes"]["nouveau_test"]["erreur"]
        )

    def test_destinations_independantes(self) -> None:
        """Vérifie qu'un refus pour une destination n'arrête pas l'autre."""
        source, bonne = self.connexions(*BASE)
        sans_table = self.annuaire_connexions.ajouter(
            "fec", "Sans table", {"dossier": self.dossier + "/sans_table"}
        )["id"]
        etat = self.creer(
            self.demande(source, bonne, sans_table, identique={bonne: True})
        )
        self.assertEqual(etat["destinations"][bonne]["statut"], ATTENTE)
        destination_bloquee = etat["destinations"][sans_table]
        self.assertEqual(destination_bloquee["statut"], BLOQUEE)
        self.assertEqual(
            destination_bloquee["etapes"]["concordance"]["statut"], BLOQUEE
        )
        self.assertTrue(
            os.path.isfile(
                destination_bloquee["etapes"]["concordance"]["fichiers"][
                    "a_arbitrer"
                ]
            )
        )
        self.assertEqual(
            destination_bloquee["etapes"]["simulation"]["statut"], "non_jouee"
        )

    def test_sans_environnement_de_test(self) -> None:
        """Vérifie l'arrêt après la simulation sans environnement de test."""
        source, _ = self.connexions(*BASE)
        faux = self.annuaire_connexions.ajouter(
            "faux", "Pennylane simulé", {}
        )["id"]
        ecrire_variable(self.secrets, nom_variable(faux, "jeton"), "j")
        etat = self.creer(self.demande(source, faux))
        dest = etat["destinations"][faux]
        self.assertEqual(dest["statut"], SANS_TEST)
        self.assertEqual(dest["etapes"]["simulation"]["statut"], "verte")
        self.assertEqual(ConnecteurFaux.ecrits, {})
        with self.assertRaises(ErreurTransfert):
            self.feu_vert(etat["id"], faux, "Pennylane simulé")

    def test_connexion_de_test_de_l_annuaire(self) -> None:
        """Vérifie le test dans la connexion de test, puis le refus final."""
        source, _ = self.connexions(*BASE)
        test = self.annuaire_connexions.ajouter("faux", "Test", {})["id"]
        vraie = self.annuaire_connexions.ajouter(
            "faux", "Vraie", {"refuser": "1"}, test
        )
        for ident in (test, vraie["id"]):
            ecrire_variable(self.secrets, nom_variable(ident, "jeton"), "j")
        etat = self.creer(self.demande(source, vraie["id"]))
        dest = etat["destinations"][vraie["id"]]
        self.assertEqual(dest["statut"], BLOQUEE)  # simulation refusée
        self.assertIn("refusé", dest["etapes"]["simulation"]["erreur"])
        self.assertEqual(ConnecteurFaux.ecrits, {})

    def test_test_et_transfert_refuses(self) -> None:
        """Vérifie le blocage quand le test ou le transfert est refusé."""
        source, _ = self.connexions(*BASE)
        test = self.annuaire_connexions.ajouter(
            "faux", "Test", {"refuser": "1"}
        )["id"]
        vraie = self.annuaire_connexions.ajouter("faux", "Vraie", {}, test)[
            "id"
        ]
        for ident in (test, vraie):
            ecrire_variable(self.secrets, nom_variable(ident, "jeton"), "j")
        etat = self.creer(self.demande(source, vraie))
        self.assertIn(
            "refusé", etat["destinations"][vraie]["etapes"]["test"]["erreur"]
        )
        registre.REGISTRE["faux"] = ConnecteurRefusFinal
        bon_test = self.annuaire_connexions.ajouter("faux", "Test bon", {})[
            "id"
        ]
        refus = self.annuaire_connexions.ajouter(
            "faux", "Refus final", {"refuser": "1"}, bon_test
        )["id"]
        for ident in (bon_test, refus):
            ecrire_variable(self.secrets, nom_variable(ident, "jeton"), "j")
        etat = self.creer(self.demande(source, refus))
        self.assertEqual(etat["destinations"][refus]["statut"], ATTENTE)
        fin = self.feu_vert(etat["id"], refus, "Refus final")
        self.assertEqual(fin["statut"], BLOQUEE)
        self.assertIn("refusé", fin["etapes"]["transfert"]["erreur"])

    def test_ecart_au_test(self) -> None:
        """Vérifie le blocage si la relecture du test diffère du lot."""
        source, _ = self.connexions(*BASE)
        test = self.annuaire_connexions.ajouter("faux", "Test", {})["id"]
        vraie = self.annuaire_connexions.ajouter("faux", "Vraie", {}, test)[
            "id"
        ]
        for ident in (test, vraie):
            ecrire_variable(self.secrets, nom_variable(ident, "jeton"), "j")
        with mock.patch.object(
            ConnecteurFaux,
            "relire",
            lambda self, reference, journal_lu: lire_fec(fec(*BASE[:2])),
        ):
            etat = self.creer(self.demande(source, vraie))
        test_etape = etat["destinations"][vraie]["etapes"]["test"]
        self.assertEqual(test_etape["statut"], BLOQUEE)
        self.assertIn(
            "MIG_ECART_SORTIE",
            [constat_lu["code"] for constat_lu in test_etape["constats"]],
        )

    def test_erreurs_de_connexion_rapportees(self) -> None:
        """Vérifie qu'une connexion qui échoue bloque son étape, nommée."""
        source, destination = self.connexions(*BASE)
        with mock.patch.object(
            ConnecteurFec,
            "environnement_test",
            side_effect=ErreurConnexion("x"),
        ):
            etat = self.creer(self.demande(source, destination))
        self.assertEqual(
            etat["destinations"][destination]["etapes"]["test"]["erreur"], "x"
        )
        with mock.patch.object(
            ConnecteurFec, "ecrire", side_effect=ErreurConnexion("injoignable")
        ):
            etat = self.creer(self.demande(source, destination))
        self.assertEqual(
            etat["destinations"][destination]["etapes"]["simulation"][
                "erreur"
            ],
            "injoignable",
        )
        etat = self.creer(self.demande(source, destination))
        relire = ConnecteurFec.relire

        def coupe_au_transfert(
            instance_fec: ConnecteurFec, reference: str, journal: Journal
        ) -> Lot:
            """Relecture normale des tests ; coupure au vrai transfert."""
            if "/test" in reference:
                return relire(instance_fec, reference, journal)
            raise ErreurConnexion("coupé")

        with mock.patch.object(ConnecteurFec, "relire", coupe_au_transfert):
            fin = transfert.donner_feu_vert(
                self.annuaire_connexions,
                etat["id"],
                destination,
                "Sortie client A",
                AUJ,
                "Stéphane Moreau",
                self.transferts,
                AUJ,
                Journal(),
                self.guardian,
            )
        self.assertEqual(fin["statut"], BLOQUEE)
        self.assertEqual(fin["etapes"]["nouveau_test"]["statut"], "verte")
        self.assertEqual(fin["etapes"]["transfert"]["erreur"], "coupé")

    def test_source_illisible_et_filtre_invalide(self) -> None:
        """Vérifie le blocage de toutes les destinations, ou d'une seule."""
        source, destination = self.connexions(*BASE)
        os.remove(
            self.annuaire_connexions.obtenir(source)["parametres"]["chemin"]
        )
        etat = self.creer(self.demande(source, destination))
        self.assertIn(
            "Source illisible",
            etat["destinations"][destination]["etapes"]["donnees"]["erreur"],
        )
        source, destination = self.connexions(*BASE)
        etat = self.creer(
            self.demande(
                source, destination, filtres=[{"nom": "f", "portee": "x"}]
            )
        )
        self.assertEqual(
            etat["destinations"][destination]["etapes"]["donnees"]["statut"],
            BLOQUEE,
        )

    def test_controles_bloquants(self) -> None:
        """Vérifie qu'un compte « 0 » bloque l'étape 1."""
        source, destination = self.connexions(
            *BASE, ligne_fec("OD", "5", "20250131", "0", "1,00")
        )
        etat = self.creer(self.demande(source, destination))
        self.assertEqual(
            etat["destinations"][destination]["etapes"]["donnees"]["statut"],
            BLOQUEE,
        )

    def test_ecart_de_concordance(self) -> None:
        """Vérifie qu'une ligne perdue par les filtres bloque l'étape 2."""
        source, destination = self.connexions(*BASE)
        appliquer = module_filtres.appliquer

        def perdre_une_ligne(
            lot: Lot,
            regles: Iterable[Mapping[str, Any]],
            journal: Journal | None = None,
        ) -> ResultatFiltres:
            """Applique les filtres puis perd l'écriture OD/4 sans trace."""
            resultat = appliquer(lot, regles, journal=journal)
            lot.lignes = lot.lignes[:-2]
            return resultat

        with mock.patch.object(module_filtres, "appliquer", perdre_une_ligne):
            etat = self.creer(self.demande(source, destination))
        concordance = etat["destinations"][destination]["etapes"][
            "concordance"
        ]
        self.assertEqual(concordance["statut"], BLOQUEE)
        self.assertEqual(
            concordance["constats"][0]["code"], "TRF_ECART_CONCORDANCE"
        )

    def test_demandes_refusees(self) -> None:
        """Vérifie les demandes impossibles, refusées avant toute lecture."""
        source, destination = self.connexions(*BASE)
        faux = self.annuaire_connexions.ajouter("faux", "F", {})["id"]
        ecrire_variable(self.secrets, nom_variable(faux, "jeton"), "j")
        for demande in (
            self.demande(source),
            self.demande(source, destination, destination),
            self.demande(source, source),
            self.demande(faux, destination),  # ne sait pas lire
            self.demande("fec_absent", destination),
        ):
            with self.assertRaises(ErreurTransfert):
                self.creer(demande)
        with self.assertRaises(ValueError):
            self.creer(self.demande(source, destination, du="31/01/2025"))
        self.assertFalse(os.path.exists(self.transferts))

    def test_destination_qui_ne_sait_pas_ecrire(self) -> None:
        """Vérifie le refus d'une destination en lecture seule."""
        source, destination = self.connexions(*BASE)
        with mock.patch.dict(ConnecteurFec.capacites, {"ecriture": None}):
            with self.assertRaises(ErreurTransfert) as contexte:
                self.creer(self.demande(source, destination))
        self.assertIn("écrire", str(contexte.exception))

    def test_periode(self) -> None:
        """Vérifie que la période limite le transfert, sans écart."""
        source, destination = self.connexions(*BASE)
        etat = self.creer(
            self.demande(source, destination, du="2025-01-10", au="2025-01-20")
        )
        dest = etat["destinations"][destination]
        self.assertEqual(dest["statut"], ATTENTE)
        self.assertEqual(dest["totaux"]["ecritures"], 2)

    def test_verrou_par_connexion(self) -> None:
        """Vérifie qu'une connexion n'est écrite que par un fil à la fois."""
        ordre: list[str] = []

        def ecrire(nom: str) -> None:
            """Tient le verrou de la connexion « c » pendant l'écriture."""
            with transfert.verrou_connexion("c"):
                ordre.append(nom + " début")
                ordre.append(nom + " fin")

        with transfert.verrou_connexion("c"):
            fil = threading.Thread(target=ecrire, args=("b",))
            fil.start()
            ordre.append("a")
        fil.join()
        self.assertEqual(ordre, ["a", "b début", "b fin"])


class TestCatalogue(unittest.TestCase):
    """Chaque code de transfert a son explication (Marceau)."""

    def test_codes_expliques(self) -> None:
        """Vérifie que chaque code TRF_ du paquet est au catalogue."""
        codes: set[str] = set()
        dossier = os.path.join(RACINE_DEPOT, "core", "connecteurs")
        for nom in os.listdir(dossier):
            if nom.endswith(".py"):
                with open(
                    os.path.join(dossier, nom), encoding="utf-8"
                ) as fichier:
                    codes |= set(
                        re.findall(r'"(TRF_[A-Z_]+)"', fichier.read())
                    )
        self.assertTrue(codes)
        self.assertEqual(sorted(codes - set(CATALOGUE)), [])


class TestCommande(Bac):
    """Commande scripts/concorde_connexion.py."""

    def lancer(self, *arguments: str) -> tuple[int, str, str]:
        """Lance la commande ; rend (code, sortie, erreurs)."""
        sortie, erreurs = io.StringIO(), io.StringIO()
        argv = ["concorde_connexion", "--fichier", self.secrets, *arguments]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            concorde_connexion,
            "Annuaire",
            lambda fichier_secrets: Annuaire(
                self.annuaire_connexions.chemin, fichier_secrets
            ),
        ), redirect_stdout(sortie), redirect_stderr(erreurs):
            code = concorde_connexion.main()
        return code, sortie.getvalue(), erreurs.getvalue()

    def test_parcours(self) -> None:
        """Vérifie ajouter, secret, tester, lister, retirer."""
        code, sortie, _ = self.lancer("ajouter", "faux", "Pennylane cabinet")
        self.assertEqual(code, 0)
        ident = re.search(r"Connexion ajoutée : (\S+)", sortie)
        if ident is None:
            self.fail("identifiant de connexion attendu")
        self.assertIn("secret %s jeton" % ident.group(1), sortie)
        with mock.patch("getpass.getpass", return_value="jeton-secret"):
            code, sortie, _ = self.lancer("secret", ident.group(1), "jeton")
        self.assertEqual(code, 0)
        self.assertNotIn("jeton-secret", sortie)
        self.assertEqual(
            lire_secrets(self.secrets),
            {nom_variable(ident.group(1), "jeton"): "jeton-secret"},
        )
        code, sortie, _ = self.lancer("tester", ident.group(1))
        self.assertIn("OK", sortie)
        code, sortie, _ = self.lancer("lister")
        self.assertIn("Pennylane cabinet", sortie)
        self.assertIn("Logiciels branchés", sortie)
        code, sortie, _ = self.lancer("retirer", ident.group(1))
        self.assertEqual((code, self.annuaire_connexions.lister()), (0, []))

    def test_refus(self) -> None:
        """Vérifie les refus : paramètre mal formé, saisie vide, inconnu."""
        code, _, erreurs = self.lancer("ajouter", "fec", "A", "--param", "x")
        self.assertEqual(code, 1)
        self.assertIn("nom=valeur", erreurs)
        code, sortie, _ = self.lancer(
            "ajouter", "fec", "A", "--param", "dossier=" + self.dossier
        )
        ident = sortie.split(": ")[1].strip()
        with mock.patch("getpass.getpass", return_value=""):
            code, _, erreurs = self.lancer("secret", ident, "jeton")
        self.assertEqual(code, 1)
        code, _, erreurs = self.lancer("tester", "fec_absent")
        self.assertEqual(code, 1)
        self.assertIn("Refusé", erreurs)


if __name__ == "__main__":
    unittest.main()
