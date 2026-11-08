# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du socle des transferts entre logiciels (ADR-0008)."""

import http.client
import io
import json
import os
import re
import ssl
import stat
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar
from unittest import mock
from urllib.parse import parse_qsl

from core.connecteurs import http_json as module_http_json
from core.connecteurs import odoo as module_odoo
from core.connecteurs import registre, transfert
from core.migration import export as module_export
from core.migration import filtres as module_filtres
from core.migration import injection
from core.migration.correspondance import appliquer as appliquer_correspondance
from core.connecteurs.base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    ResultatEcriture,
)
from core.connecteurs.connexions import Annuaire, ErreurAnnuaire
from core.connecteurs.azalplus import ConnecteurAzalPlus
from core.connecteurs.http_json import ClientJson, connexion_https
from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.pennylane import ConnecteurPennylane, Element
from core.connecteurs.fec import (
    ConnecteurFec,
    dossier_reference,
    retirer_hors_periode,
)
from core.connecteurs.secrets import (
    ErreurSecrets,
    ecrire_variable,
    effacer_secrets_connexion,
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
from core.odoo_source import ErreurSource, SourceXmlRpcOdoo17
from scripts import concorde_connexion
from tests.outils import (
    BASE,
    RACINE_DEPOT,
    FauxCommun,
    FauxObjet,
    FauxOdoo,
    fec,
    ligne_fec,
)

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
        with self.assertRaises(ErreurSecrets):
            ecrire_variable(self.secrets, "A", "")

    def test_ecriture_atomique_dans_un_dossier_neuf(self) -> None:
        """Vérifie le dossier créé en 700 et l'absence de fichier temporaire."""
        chemin = os.path.join(self.dossier, "connecteurs", "connecteurs.env")
        ecrire_variable(chemin, "A", "1")
        ecrire_variable(chemin, "B", "2")
        dossier_secrets = os.path.dirname(chemin)
        self.assertEqual(stat.S_IMODE(os.stat(dossier_secrets).st_mode), 0o700)
        self.assertEqual(os.listdir(dossier_secrets), ["connecteurs.env"])
        self.assertEqual(lire_secrets(chemin), {"A": "1", "B": "2"})

    def test_coupure_pendant_l_ecriture(self) -> None:
        """Vérifie qu'un échec d'écriture laisse l'ancien fichier intact."""
        ecrire_variable(self.secrets, "A", "garde")
        with mock.patch("os.replace", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                ecrire_variable(self.secrets, "B", "perdu")
        self.assertEqual(lire_secrets(self.secrets), {"A": "garde"})

    def test_effacer_les_secrets_d_une_connexion(self) -> None:
        """Vérifie que seuls les secrets de la connexion sont effacés."""
        effacer_secrets_connexion(self.secrets, "a", ("jeton",))
        self.assertFalse(os.path.exists(self.secrets))
        ecrire_variable(self.secrets, nom_variable("a", "jeton"), "1")
        ecrire_variable(self.secrets, nom_variable("b", "jeton"), "2")
        effacer_secrets_connexion(self.secrets, "a", ("jeton", "cle"))
        self.assertEqual(
            lire_secrets(self.secrets), {nom_variable("b", "jeton"): "2"}
        )


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

    def test_etat_puis_effacement_des_secrets(self) -> None:
        """Vérifie « renseigné / manquant » sans valeur, puis l'effacement."""
        fiche = self.annuaire_connexions.ajouter("faux", "Cabinet", {})
        self.assertEqual(
            self.annuaire_connexions.secrets_renseignes(fiche["id"]),
            {"jeton": False},
        )
        ecrire_variable(
            self.secrets, nom_variable(fiche["id"], "jeton"), "jeton-prive"
        )
        etat = self.annuaire_connexions.secrets_renseignes(fiche["id"])
        self.assertEqual(etat, {"jeton": True})
        self.assertNotIn("jeton-prive", json.dumps(etat))
        self.annuaire_connexions.retirer(fiche["id"])
        self.assertEqual(lire_secrets(self.secrets), {})

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


class TestConnecteurOdoo(Bac):
    """Connecteur Odoo 17 sur des Odoo simulés (lecture et écriture)."""

    def setUp(self) -> None:
        """Prépare les deux Odoo simulés et branche le connecteur dessus."""
        super().setUp()
        self.lecture = FauxObjet()
        self.ecriture = FauxOdoo()
        cible_reelle = injection.CibleOdoo
        lecture, ecriture = self.lecture, self.ecriture

        def source(
            url: str,
            base: str,
            utilisateur: str,
            cle: str,
            journal: Journal | None = None,
        ) -> SourceXmlRpcOdoo17:
            """Source XML-RPC sur l'Odoo de lecture simulé."""
            return SourceXmlRpcOdoo17(
                url,
                base,
                utilisateur,
                cle,
                proxy_commun=FauxCommun(),
                proxy_objet=lecture,
                journal=journal,
            )

        def cible(
            url: str, base: str, utilisateur: str, mot_de_passe: str
        ) -> injection.CibleOdoo:
            """Cible d'écriture sur l'Odoo d'écriture simulé."""
            return cible_reelle(
                url,
                base,
                utilisateur,
                mot_de_passe,
                proxy_commun=FauxCommun(),
                proxy_objet=ecriture,
            )

        for correctif in (
            mock.patch.object(module_odoo, "SourceXmlRpcOdoo17", source),
            mock.patch.object(injection, "CibleOdoo", cible),
        ):
            correctif.start()
            self.addCleanup(correctif.stop)

    def odoo(self, **options: str) -> ConnecteurOdoo:
        """Connecteur vers « client » (options : creer_manquants…)."""
        parametres = {
            "url": "https://client.odoo.com",
            "base": "client",
            "utilisateur": "admin",
        }
        parametres.update(options)
        return ConnecteurOdoo(parametres, {"cle_api": "cle"})

    def lot_pret(self) -> Lot:
        """FEC de référence, comptes repris à l'identique."""
        lot = lire_fec(fec(*BASE))
        appliquer_correspondance(lot, identique=True)
        return lot

    def test_parametres_requis(self) -> None:
        """Vérifie que l'adresse, la base, le login et la clé sont exigés."""
        with self.assertRaises(ErreurConnexion) as contexte:
            ConnecteurOdoo({"url": "https://x"}, {})
        for manque in ("base", "utilisateur", "secret cle_api"):
            self.assertIn(manque, str(contexte.exception))

    def test_tester_et_lire(self) -> None:
        """Vérifie la société lue et les lignes au format commun."""
        info = self.odoo().tester(Journal())
        self.assertEqual(
            (info["societe"], info["siren"], info["version"]),
            ("Soc", "384684957", "17.0"),
        )
        lot = self.odoo().lire({"du": None, "au": None}, Journal())
        self.assertEqual(lot.source["type"], "odoo")
        self.assertEqual(
            lot.totaux(),
            {"lignes": 2, "ecritures": 1, "debit": 10010, "credit": 10010},
        )
        client = lot.lignes[1]
        self.assertEqual(
            (client["compte"], client["tiers_ref"], client["piece"]),
            ("411000", "C7", "VEN/1"),  # sans référence : nom de la pièce
        )

    def test_relire_par_reference(self) -> None:
        """Vérifie que seules les écritures de la référence sont relues."""
        self.lecture.donnees["account.move"][0]["ref"] = "CONCORDE/T1/VEN/1"
        self.assertEqual(
            self.odoo().relire("CONCORDE/T1", Journal()).totaux()["lignes"], 2
        )
        self.assertEqual(
            self.odoo().relire("CONCORDE/T2", Journal()).totaux()["lignes"], 0
        )

    def test_vraie_destination_incomplete_bloquee(self) -> None:
        """Vérifie qu'un compte, journal ou tiers absent bloque l'écriture."""
        essai = self.odoo().ecrire(
            self.lot_pret(), "CONCORDE/T1", True, Journal()
        )
        self.assertEqual(essai["ecritures_a_creer"], 4)
        self.assertEqual(len(essai["erreurs"]), 3)  # comptes, journaux, tiers
        self.assertIn("101000", " ".join(essai["erreurs"]))
        reel = self.odoo().ecrire(
            self.lot_pret(), "CONCORDE/T1", False, Journal()
        )
        self.assertEqual(reel["erreurs"], essai["erreurs"])
        self.assertEqual(self.ecriture.donnees["account.move"], [])

    def test_base_de_test_ecriture_puis_reprise(self) -> None:
        """Vérifie l'envoi dans une base de test, puis l'absence de doublon."""
        test = self.odoo(creer_manquants="oui")
        essai = test.ecrire(
            self.lot_pret(), "CONCORDE/T1/test1", True, Journal()
        )
        self.assertEqual(essai["erreurs"], [])
        self.assertEqual(self.ecriture.donnees["account.move"], [])
        ecrit = test.ecrire(
            self.lot_pret(), "CONCORDE/T1/test1", False, Journal()
        )
        self.assertEqual(ecrit["erreurs"], [])
        refs = sorted(
            ecriture_odoo["ref"]
            for ecriture_odoo in self.ecriture.donnees["account.move"]
        )
        self.assertEqual(refs[0], "CONCORDE/T1/test1/AN/1")
        self.assertEqual(len(refs), 4)
        encore = test.ecrire(
            self.lot_pret(), "CONCORDE/T1/test1", True, Journal()
        )
        self.assertEqual(
            (encore["ecritures_a_creer"], encore["ecritures_deja_presentes"]),
            (0, 4),
        )

    def test_refus_d_odoo_rapportes(self) -> None:
        """Vérifie que les refus d'Odoo deviennent des erreurs nommées."""
        self.ecriture.refuser_compte = 1  # 512000 refusé à la création
        ecrit = self.odoo(creer_manquants="oui").ecrire(
            self.lot_pret(), "CONCORDE/T1", False, Journal()
        )
        self.assertTrue(ecrit["erreurs"])
        self.assertIn("compte refusé", " ".join(ecrit["erreurs"]))
        devise = self.lot_pret()
        devise.lignes[0]["devise"] = "USD"
        ecrit = self.odoo(creer_manquants="oui").ecrire(
            devise, "CONCORDE/T2", False, Journal()
        )
        self.assertIn("devise", " ".join(ecrit["erreurs"]))

    def test_erreurs_de_connexion(self) -> None:
        """Vérifie que chaque échec d'Odoo devient une ErreurConnexion."""
        with mock.patch.object(
            module_odoo,
            "SourceXmlRpcOdoo17",
            side_effect=ErreurSource("refusée"),
        ):
            for action in (
                lambda: self.odoo().tester(Journal()),
                lambda: self.odoo().lire({"du": None, "au": None}, Journal()),
                lambda: self.odoo().relire("R", Journal()),
            ):
                with self.assertRaises(ErreurConnexion):
                    action()
        with mock.patch.object(
            SourceXmlRpcOdoo17, "societe_info", side_effect=OSError("coupé")
        ):
            with self.assertRaises(ErreurConnexion):
                self.odoo().tester(Journal())
        with mock.patch.object(
            SourceXmlRpcOdoo17, "lignes", side_effect=OSError("coupé")
        ):
            for action in (
                lambda: self.odoo().lire({"du": None, "au": None}, Journal()),
                lambda: self.odoo().relire("R", Journal()),
            ):
                with self.assertRaises(ErreurConnexion):
                    action()
        with mock.patch.object(
            injection,
            "CibleOdoo",
            side_effect=injection.ErreurInjection("refusée"),
        ):
            with self.assertRaises(ErreurConnexion):
                self.odoo().ecrire(self.lot_pret(), "R", True, Journal())
        with mock.patch.object(
            injection, "rechercher_existants", side_effect=OSError("coupé")
        ):
            with self.assertRaises(ErreurConnexion):
                self.odoo().ecrire(self.lot_pret(), "R", True, Journal())


class TestEnvoiOdoo(unittest.TestCase):
    """Envoi vers une base Odoo quelconque (injection, ADR-0008)."""

    def test_adresse_non_chiffree_refusee(self) -> None:
        """Vérifie le refus d'une adresse http hors de ce serveur."""
        with self.assertRaises(injection.ErreurInjection):
            injection.CibleOdoo("http://client.example", "b", "u", "m")

    def test_rien_cree_sans_permission(self) -> None:
        """Vérifie qu'un élément absent bloque l'envoi sans création."""
        odoo = FauxOdoo()
        cible = injection.CibleOdoo(
            "https://client.odoo.com",
            "client",
            "u",
            "m",
            proxy_commun=FauxCommun(),
            proxy_objet=odoo,
        )
        lot = lire_fec(fec(*BASE))
        appliquer_correspondance(lot, identique=True)
        with self.assertRaises(injection.ErreurInjection) as contexte:
            injection.envoyer(cible, lot, None, "CONCORDE/T1", False)
        self.assertIn("101000", str(contexte.exception))
        self.assertEqual(
            [
                ecriture_odoo
                for ecriture_odoo, methode in odoo.appels
                if methode == "create"
            ],
            [],
        )
        self.assertEqual(
            injection.manquants(injection.rechercher_existants(cible, lot))[
                "journaux"
            ],
            ["AN", "VE", "BQ", "OD"],
        )

    def test_identification_refusee_et_journal_trop_long(self) -> None:
        """Vérifie le refus d'identification et d'un code journal > 5."""
        with mock.patch.object(FauxCommun, "authenticate", return_value=0):
            with self.assertRaises(injection.ErreurInjection) as contexte:
                injection.CibleOdoo(
                    "https://client.odoo.com",
                    "client",
                    "u",
                    "m",
                    proxy_commun=FauxCommun(),
                    proxy_objet=FauxOdoo(),
                )
        self.assertIn("Authentification refusée", str(contexte.exception))
        cible = injection.CibleOdoo(
            "https://client.odoo.com",
            "client",
            "u",
            "m",
            proxy_commun=FauxCommun(),
            proxy_objet=FauxOdoo(),
        )
        lot = lire_fec(fec(ligne_fec("TROPLONG", "1", "20250101", "512000")))
        appliquer_correspondance(lot, identique=True)
        with self.assertRaises(injection.ErreurInjection) as contexte:
            injection.preparer(cible, lot, Journal(), creer_manquants=True)
        self.assertIn("trop long", str(contexte.exception))


TENANT_TEST = "11111111-1111-1111-1111-111111111111"
SOCIETE_TEST = "22222222-2222-2222-2222-222222222222"


class FauxCurseurPg:
    """Curseur PostgreSQL simulé : rend les lignes selon la requête."""

    def __init__(self, base: "FauxPg") -> None:
        """Garde la base simulée et la dernière requête."""
        self.base = base
        self.requete = ""

    def __enter__(self) -> "FauxCurseurPg":
        """Ouvre le bloc with."""
        return self

    def __exit__(self, *details: object) -> None:
        """Ferme le bloc with."""

    def execute(self, requete: str, parametres: Mapping[str, object]) -> None:
        """Enregistre la requête ; lève l'erreur prévue par le test."""
        if self.base.erreur is not None:
            raise self.base.erreur
        self.base.requetes.append((requete, dict(parametres)))
        self.requete = requete

    def fetchall(self) -> list[tuple[object, ...]]:
        """Lignes simulées de la requête exécutée."""
        if "count(*) FILTER" in self.requete:
            return [self.base.comptes]
        if "UNION ALL" in self.requete:
            return self.base.tiers
        return self.base.lignes


class FauxPg:
    """Base AzalPlus simulée (connexion DB-API)."""

    def __init__(self) -> None:
        """Deux écritures équilibrées ; tiers clients et fournisseurs."""
        jour = date(2026, 10, 3)
        self.lignes: list[tuple[object, ...]] = [
            (
                jour,
                "VT",
                "Ventes",
                "VT-1",
                "",
                "411000",
                "Clients",
                "ACME",
                "Facture",
                Decimal("120.00"),
                Decimal("0"),
                "A",
                "",
                None,
                "",
            ),
            (
                jour,
                "VT",
                None,
                "VT-1",
                "",
                "706000",
                "Ventes",
                "",
                "Facture",
                Decimal("0"),
                Decimal("120.00"),
                "",
                "",
                None,
                "",
            ),
            (
                jour,
                "BQ",
                "Banque",
                "BQ-1",
                "REL-9",
                "512000",
                "Banque",
                "",
                "Règlement",
                Decimal("120.00"),
                Decimal("0"),
                "",
                "EUR",
                None,
                "AXE1",
            ),
            (
                jour,
                "BQ",
                "Banque",
                "BQ-1",
                "REL-9",
                "411000",
                "Clients",
                "ACME",
                "Règlement",
                Decimal("0"),
                Decimal("120.00"),
                "A",
                "",
                None,
                "",
            ),
        ]
        self.tiers: list[tuple[object, ...]] = [
            ("ACME", "C001"),
            ("DOUBLON", "C002"),
            ("DOUBLON", "F001"),
            ("SANSCODE", None),
        ]
        self.comptes: tuple[object, ...] = (4, 680, 0)
        self.requetes: list[tuple[str, dict[str, object]]] = []
        self.session: dict[str, bool] = {}
        self.fermee = 0
        self.erreur: Exception | None = None

    def cursor(self, name: str | None = None) -> FauxCurseurPg:
        """Ouvre un curseur simulé."""
        return FauxCurseurPg(self)

    def set_session(self, *, readonly: bool, autocommit: bool) -> None:
        """Garde le mode demandé (lecture seule attendue)."""
        self.session = {"readonly": readonly, "autocommit": autocommit}

    def close(self) -> None:
        """Compte les fermetures."""
        self.fermee += 1


class TestConnecteurAzalPlus(Bac):
    """Connecteur AzalPlus en lecture seule (ADR-0009)."""

    PARAMETRES = {
        "hote": "10.0.0.2",
        "port": "5432",
        "base": "azals",
        "utilisateur": "concorde_ro",
        "tenant_id": TENANT_TEST,
        "societe_id": SOCIETE_TEST,
    }

    def setUp(self) -> None:
        """Branche psycopg2.connect sur la base simulée."""
        super().setUp()
        self.base_pg = FauxPg()
        self.connexions: list[dict[str, object]] = []

        def connecter(**options: object) -> FauxPg:
            """Garde les options de connexion, rend la base simulée."""
            self.connexions.append(options)
            return self.base_pg

        correctif = mock.patch("psycopg2.connect", connecter)
        correctif.start()
        self.addCleanup(correctif.stop)

    def azalplus(self, **options: str) -> ConnecteurAzalPlus:
        """Connecteur vers la société simulée."""
        parametres = dict(self.PARAMETRES)
        parametres.update(options)
        return ConnecteurAzalPlus(parametres, {"mot_de_passe": "secret"})

    def test_parametres(self) -> None:
        """Vérifie les paramètres exigés et les identifiants en UUID."""
        with self.assertRaises(ErreurConnexion) as contexte:
            ConnecteurAzalPlus({}, {})
        self.assertIn("tenant_id", str(contexte.exception))
        with self.assertRaises(ErreurConnexion):
            self.azalplus(tenant_id="pas-un-uuid")
        self.assertEqual(self.azalplus().tenant, uuid.UUID(TENANT_TEST))

    def test_tester_compte_et_signale(self) -> None:
        """Vérifie le comptage, l'alerte sans société, la lecture seule."""
        journal = Journal()
        info = self.azalplus().tester(journal)
        self.assertEqual(info["societe"], SOCIETE_TEST)
        messages = " ".join(
            evenement["message"] for evenement in journal.tout()
        )
        self.assertIn("680 ligne(s) d'écritures sans société", messages)
        self.base_pg.comptes = (4, 0, 3)
        journal = Journal()
        self.azalplus().tester(journal)
        self.assertIn(
            "ni « VALIDEE » ni « VALIDE »",
            " ".join(evenement["message"] for evenement in journal.tout()),
        )
        self.assertEqual(
            self.base_pg.session, {"readonly": True, "autocommit": False}
        )
        self.assertEqual(self.connexions[0]["sslmode"], "require")
        self.assertEqual(self.connexions[0]["password"], "secret")
        for requete, parametres in self.base_pg.requetes:
            self.assertIn("tenant_id = %(tenant)s", requete)
            self.assertEqual(parametres["tenant"], TENANT_TEST)
        self.assertEqual(self.base_pg.fermee, len(self.base_pg.requetes))

    def test_lire(self) -> None:
        """Vérifie les lignes, les tiers trouvés par leur nom, la période."""
        lot = self.azalplus().lire(
            {"du": date(2026, 10, 1), "au": None}, Journal()
        )
        self.assertEqual(lot.source["type"], "azalplus")
        self.assertEqual(
            lot.totaux(),
            {"lignes": 4, "ecritures": 2, "debit": 24000, "credit": 24000},
        )
        self.assertEqual(lot.illisibles, [])
        premiere, banque = lot.lignes[0], lot.lignes[2]
        self.assertEqual(
            (premiere["tiers_ref"], premiere["tiers_nom"]), ("C001", "ACME")
        )
        self.assertEqual(lot.lignes[1]["journal_lib"], "")
        self.assertEqual(
            (banque["piece"], banque["ecriture"], banque["analytique"]),
            ("REL-9", "BQ-1", "AXE1"),
        )
        self.assertEqual(
            lot.signalements,
            ["tiers « ACME » retrouvé par son nom : code C001"],
        )
        requete, parametres = self.base_pg.requetes[1]
        self.assertEqual(parametres["du"], date(2026, 10, 1))
        self.assertEqual(parametres["statuts"], ["VALIDEE", "VALIDE"])
        self.assertIn("deleted_at IS NULL AND NOT e.archived", requete)

    def test_tiers_et_montants_bloquants(self) -> None:
        """Vérifie : tiers introuvable, en double, sans code ; 3 décimales."""
        jour = date(2026, 10, 3)
        modele = list(self.base_pg.lignes[0])

        def ligne(tiers: str, debit: Decimal) -> tuple[object, ...]:
            """Ligne simulée avec un tiers et un débit donnés."""
            copie = list(modele)
            copie[7], copie[9], copie[0] = tiers, debit, jour
            return tuple(copie)

        self.base_pg.lignes = [
            ligne("INCONNU", Decimal("1")),
            ligne("DOUBLON", Decimal("1")),
            ligne("SANSCODE", Decimal("1")),
            ligne("", Decimal("1.234")),
        ]
        lot = self.azalplus().lire({"du": None, "au": None}, Journal())
        motifs = [motif for _, _, motif in lot.illisibles]
        self.assertEqual(len(motifs), 4)
        self.assertIn("introuvable", motifs[0])
        self.assertIn("2 clients ou fournisseurs", motifs[1])
        self.assertIn("sans code", motifs[2])
        self.assertIn("centime", motifs[3])
        self.assertEqual(lot.lignes[3]["debit"], 0)

    def test_devise(self) -> None:
        """Vérifie qu'une ligne en devise garde son montant en devise."""
        en_dollars = list(self.base_pg.lignes[0])
        en_dollars[12], en_dollars[13] = "USD", Decimal("130.50")
        self.base_pg.lignes = [tuple(en_dollars)]
        ligne_lue = self.azalplus().lire({"du": None, "au": None}, Journal())
        self.assertEqual(
            (
                ligne_lue.lignes[0]["devise"],
                ligne_lue.lignes[0]["montant_devise"],
            ),
            ("USD", 13050),
        )

    def test_erreurs(self) -> None:
        """Vérifie : base injoignable, requête refusée, psycopg2 absent."""
        import psycopg2

        with mock.patch(
            "psycopg2.connect",
            side_effect=psycopg2.OperationalError("injoignable"),
        ):
            with self.assertRaises(ErreurConnexion) as contexte:
                self.azalplus().tester(Journal())
        self.assertIn("injoignable", str(contexte.exception))
        self.assertNotIn("secret", str(contexte.exception))
        self.base_pg.erreur = psycopg2.Error("droit refusé")
        with self.assertRaises(ErreurConnexion):
            self.azalplus().lire({"du": None, "au": None}, Journal())
        self.assertEqual(self.base_pg.fermee, 1)  # fermée malgré l'erreur
        with self.assertRaises(ErreurConnexion):
            self.azalplus(port="cinq").tester(Journal())
        with mock.patch.dict(sys.modules, {"psycopg2": None}):
            with self.assertRaises(ErreurConnexion) as contexte:
                self.azalplus().tester(Journal())
        self.assertIn("psycopg2", str(contexte.exception))

    def test_transfert_azalplus_vers_fec(self) -> None:
        """Vérifie un transfert complet AzalPlus -> FEC, jamais l'inverse."""
        source = self.annuaire_connexions.ajouter(
            "azalplus", "AzalPlus société A", self.PARAMETRES
        )["id"]
        ecrire_variable(
            self.secrets, nom_variable(source, "mot_de_passe"), "secret"
        )
        destination = self.annuaire_connexions.ajouter(
            "fec", "Sortie", {"dossier": os.path.join(self.dossier, "s")}
        )["id"]
        etat = transfert.creer(
            self.annuaire_connexions,
            self.demande(source, destination),
            self.transferts,
            AUJ,
            Journal(),
            self.guardian,
        )
        dest = etat["destinations"][destination]
        self.assertEqual(dest["statut"], ATTENTE)
        constats = [
            constat_lu["code"]
            for constat_lu in dest["etapes"]["donnees"]["constats"]
        ]
        self.assertEqual(constats, ["MIG_SIGNALEMENT_SOURCE"])
        with self.assertRaises(ErreurTransfert):
            transfert.creer(
                self.annuaire_connexions,
                self.demande(destination, source),
                self.transferts,
                AUJ,
                Journal(),
                self.guardian,
            )


class FausseReponse:
    """Réponse HTTP simulée."""

    def __init__(
        self, status: int, corps: bytes, entetes: dict[str, str]
    ) -> None:
        """Garde le statut, le corps et les en-têtes."""
        self.status, self._corps, self._entetes = status, corps, entetes

    def read(self) -> bytes:
        """Corps de la réponse."""
        return self._corps

    def getheader(self, name: str) -> str | None:
        """Valeur d'un en-tête."""
        return self._entetes.get(name)


class FauxPennylane:
    """API v2 de Pennylane simulée (journaux, comptes, écritures, lignes).

    `forcees` : réponses imposées, servies avant le fonctionnement normal.
    """

    RACINE = "/api/external/v2"

    def __init__(self) -> None:
        """Deux journaux, comptes du PCG (512000 deux fois : deux TVA)."""
        self.journaux: list[Element] = [
            {"id": 1, "code": "AN", "label": "À nouveaux", "type": "x"},
            {"id": 2, "code": "VE", "label": "Ventes", "type": "x"},
        ]
        self.comptes: list[Element] = [
            {"id": 10 + rang, "number": numero, "enabled": True}
            for rang, numero in enumerate(
                ("512000", "101000", "706000", "445710", "411000", "512000")
            )
        ]
        self.comptes[5]["enabled"] = False  # doublon désactivé : ignoré
        self.ecritures: list[Element] = []
        self.lignes: list[Element] = []
        self.forcees: list[tuple[int, bytes, dict[str, str]]] = []
        self.requetes: list[tuple[str, str, dict[str, str]]] = []
        self.suivant = 1000

    def ouvrir(
        self, hote: str, port: int | None, delai: float
    ) -> "FauxPennylane":
        """Fabrique de connexion : la base simulée sert de connexion."""
        return self

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] = {},
    ) -> None:
        """Garde la requête pour getresponse."""
        self._requete = (method, url, body)
        self.requetes.append((method, url, dict(headers)))

    def close(self) -> None:
        """Rien à fermer."""

    def getresponse(self) -> FausseReponse:
        """Répond comme l'API v2 (filtres, curseur, création)."""
        if self.forcees:
            return FausseReponse(*self.forcees.pop(0))
        methode, url, corps = self._requete
        chemin, _, requete = url.partition("?")
        chemin = chemin.removeprefix(self.RACINE)
        parametres = dict(parse_qsl(requete))
        if methode == "POST":
            return self._creer(json.loads(corps or b"{}"))
        sources = {
            "/journals": self.journaux,
            "/ledger_accounts": self.comptes,
            "/ledger_entries": self.ecritures,
            "/ledger_entry_lines": self.lignes,
        }
        elements = [
            element_api
            for element_api in sources[chemin]
            if all(
                self._garde(element_api, filtre_api)
                for filtre_api in json.loads(parametres.get("filter", "[]"))
            )
        ]
        debut = int(parametres.get("cursor") or 0)
        limite = int(parametres.get("limit") or 20)
        fin = debut + limite
        page = elements[debut:fin]
        suite = debut + limite < len(elements)
        return self._json(
            200,
            {
                "items": page,
                "has_more": suite,
                "next_cursor": str(debut + limite) if suite else None,
            },
        )

    @staticmethod
    def _garde(element: Element, filtre: dict[str, Any]) -> bool:
        """Vrai si l'élément passe le filtre Pennylane."""
        champ, operateur, valeur = (
            filtre["field"],
            filtre["operator"],
            filtre["value"],
        )
        if champ == "ledger_entry_id":
            present = element["ledger_entry"]["id"]
        else:
            present = element.get(champ)
        if operateur == "in":
            return present in valeur
        if operateur == "eq":
            return bool(present == valeur)
        if operateur == "gteq":
            return str(present) >= str(valeur)
        return str(present) <= str(valeur)  # lteq

    def _json(self, statut: int, valeur: object) -> FausseReponse:
        """Réponse JSON."""
        return FausseReponse(statut, json.dumps(valeur).encode(), {})

    def _creer(self, corps: dict[str, Any]) -> FausseReponse:
        """Crée une écriture et ses lignes (422 si déséquilibrée)."""
        lignes = corps["ledger_entry_lines"]
        if sum(
            Decimal(ligne_api["debit"]) - Decimal(ligne_api["credit"])
            for ligne_api in lignes
        ):
            return self._json(422, {"message": "Entry lines are not balanced"})
        self.suivant += 1
        ident = self.suivant
        self.ecritures.append(
            {
                "id": ident,
                "label": corps["label"],
                "piece_number": corps["piece_number"],
                "date": corps["date"],
                "journal": {"id": corps["journal_id"]},
                "status": "entry",
            }
        )
        numeros = {
            compte_api["id"]: compte_api["number"]
            for compte_api in self.comptes
        }
        for ligne in lignes:
            self.suivant += 1
            self.lignes.append(
                {
                    "id": self.suivant,
                    "debit": ligne["debit"],
                    "credit": ligne["credit"],
                    "label": ligne["label"],
                    "date": corps["date"],
                    "journal": {"id": corps["journal_id"]},
                    "ledger_entry": {"id": ident},
                    "ledger_account": {
                        "id": ligne["ledger_account_id"],
                        "number": numeros[ligne["ledger_account_id"]],
                    },
                    "lettered_ledger_entry_lines": {"ids": []},
                }
            )
        return self._json(201, {"id": ident})


# FEC sans tiers ni lettrage (Pennylane ne les porte pas sur la ligne).
FEC_SIMPLE = (
    ligne_fec("AN", "1", "20250101", "512000", "1000,00"),
    ligne_fec("AN", "1", "20250101", "101000", credit="1000,00"),
    ligne_fec("VE", "2", "20250115", "411000", "120,00"),
    ligne_fec("VE", "2", "20250115", "706000", credit="100,00"),
    ligne_fec("VE", "2", "20250115", "445710", credit="20,00"),
)


class TestClientJson(unittest.TestCase):
    """Client REST JSON commun (https, 429, erreurs sans jeton)."""

    def client(self, faux: FauxPennylane, **options: Any) -> ClientJson:
        """Client vers l'API simulée."""
        return ClientJson(
            "https://app.pennylane.com/api/external/v2",
            "jeton-secret",
            ouvrir=faux.ouvrir,
            **options,
        )

    def test_https_exige(self) -> None:
        """Vérifie le refus d'une adresse http."""
        with self.assertRaises(ErreurConnexion):
            ClientJson("http://app.pennylane.com/api", "j")

    def test_limite_d_appels_puis_reprise(self) -> None:
        """Vérifie l'attente sur 429 puis la reprise, et l'abandon nommé."""
        faux = FauxPennylane()
        attentes: list[float] = []
        faux.forcees = [(429, b"", {"Retry-After": "3"}), (429, b"", {})]
        page = self.client(faux, attendre=attentes.append).requete(
            "GET", "/journals"
        )
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(attentes, [3.0, 2.0])
        faux.forcees = [(429, b"", {"Retry-After": "x"})] * 2
        with self.assertRaises(ErreurConnexion) as contexte:
            self.client(faux, essais=2, attendre=attentes.append).requete(
                "GET", "/journals"
            )
        self.assertIn("limite d'appels", str(contexte.exception))
        self.assertEqual(attentes[-1], 2.0)

    def test_erreurs_sans_jeton(self) -> None:
        """Vérifie 401, message de l'éditeur, réponse illisible, réseau."""
        faux = FauxPennylane()
        cas: tuple[tuple[tuple[int, bytes, dict[str, str]], str], ...] = (
            ((401, b"{}", {}), "jeton invalide"),
            ((500, b'{"error": "panne"}', {}), "panne"),
            ((502, b"", {}), "sans détail"),
            ((200, b"<html>", {}), "illisible"),
        )
        for forcee, attendu in cas:
            faux.forcees = [forcee]
            with self.assertRaises(ErreurConnexion) as contexte:
                self.client(faux).requete("GET", "/journals")
            self.assertIn(attendu, str(contexte.exception))
            self.assertNotIn("jeton-secret", str(contexte.exception))
        with mock.patch.object(faux, "request", side_effect=OSError("coupé")):
            with self.assertRaises(ErreurConnexion) as contexte:
                self.client(faux).requete("GET", "/journals")
        self.assertIn("injoignable", str(contexte.exception))
        self.assertEqual(
            faux.requetes[0][2]["Authorization"], "Bearer jeton-secret"
        )

    def test_pagination_par_curseur(self) -> None:
        """Vérifie que toutes les pages d'une liste sont lues."""
        faux = FauxPennylane()
        faux.comptes = [
            {"id": rang, "number": str(rang), "enabled": True}
            for rang in range(250)
        ]
        self.assertEqual(
            len(self.client(faux).tout_lire("/ledger_accounts")), 250
        )
        curseurs = [url for _, url, _ in faux.requetes if "cursor=" in url]
        self.assertEqual(len(curseurs), 2)

    def test_connexion_https_verifie_le_certificat(self) -> None:
        """Vérifie que la connexion par défaut vérifie le certificat."""
        connexion = connexion_https("app.pennylane.com", None, 5)
        self.assertIsInstance(connexion, http.client.HTTPSConnection)
        contexte = getattr(connexion, "_context")
        self.assertEqual(contexte.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(contexte.check_hostname)


class TestConnecteurPennylane(Bac):
    """Connecteur Pennylane sur l'API simulée."""

    def setUp(self) -> None:
        """Branche le client HTTP sur l'API simulée."""
        super().setUp()
        self.faux = FauxPennylane()
        correctif = mock.patch.object(
            module_http_json, "connexion_https", self.faux.ouvrir
        )
        correctif.start()
        self.addCleanup(correctif.stop)

    def pennylane(self, **options: str) -> ConnecteurPennylane:
        """Connecteur vers l'API simulée."""
        return ConnecteurPennylane(options, {"jeton": "jeton-secret"})

    def lot(self, *lignes: str) -> Lot:
        """Lot lu dans un FEC, comptes à l'identique."""
        lot = lire_fec(fec(*lignes))
        appliquer_correspondance(lot, identique=True)
        return lot

    def test_tester(self) -> None:
        """Vérifie le test et l'en-tête de société (jeton de cabinet)."""
        info = self.pennylane(societe_id="42").tester(Journal())
        self.assertEqual(info["societe"], "42")
        self.assertEqual(self.faux.requetes[0][2]["X-Company-Id"], "42")

    def test_refus_nommes(self) -> None:
        """Vérifie : tiers, lettrage, journal et compte absents."""
        essai = self.pennylane().ecrire(
            self.lot(*BASE), "CONCORDE/T1", True, Journal()
        )
        texte = " ".join(essai["erreurs"])
        for attendu in ("avec tiers", "lettrée", "BQ, OD", "421000, 640000"):
            self.assertIn(attendu, texte)
        devise = self.lot(*FEC_SIMPLE)
        devise.lignes[0]["devise"] = "USD"
        self.assertIn(
            "en devise",
            " ".join(
                self.pennylane().ecrire(devise, "R", True, Journal())[
                    "erreurs"
                ]
            ),
        )
        self.faux.comptes[5]["enabled"] = True  # 512000 sous deux TVA
        self.assertIn(
            "plusieurs identifiants",
            " ".join(
                self.pennylane().ecrire(
                    self.lot(*FEC_SIMPLE), "R", False, Journal()
                )["erreurs"]
            ),
        )
        self.assertEqual(self.faux.ecritures, [])

    def test_ecrire_relire_reprise(self) -> None:
        """Vérifie l'écriture, la relecture au centime, sans doublon."""
        connecteur = self.pennylane()
        lot = self.lot(*FEC_SIMPLE)
        essai = connecteur.ecrire(lot, "CONCORDE/T1", True, Journal())
        self.assertEqual(
            (essai["erreurs"], essai["ecritures_a_creer"]), ([], 2)
        )
        ecrit = connecteur.ecrire(lot, "CONCORDE/T1", False, Journal())
        self.assertEqual(ecrit["erreurs"], [])
        self.assertEqual(
            sorted(
                element_api["piece_number"]
                for element_api in self.faux.ecritures
            ),
            ["CONCORDE/T1/AN/1", "CONCORDE/T1/VE/2"],
        )
        self.assertEqual(self.faux.lignes[0]["debit"], "1000.00")
        relu = connecteur.relire("CONCORDE/T1", Journal())
        self.assertEqual(module_export.comparer(lot, relu).constats, [])
        encore = self.pennylane()
        reprise = encore.ecrire(lot, "CONCORDE/T1", False, Journal())
        self.assertEqual(
            (
                reprise["ecritures_a_creer"],
                reprise["ecritures_deja_presentes"],
            ),
            (0, 2),
        )
        self.assertEqual(len(self.faux.ecritures), 2)
        self.assertEqual(
            encore.relire("CONCORDE/T1", Journal()).totaux(), lot.totaux()
        )
        with self.assertRaises(ErreurConnexion):
            self.pennylane().relire("CONCORDE/T1", Journal())

    def test_refus_d_une_ecriture(self) -> None:
        """Vérifie qu'un refus de Pennylane est gardé avec sa référence."""
        refus = self.faux._json(
            422, {"message": "Entry lines are not balanced"}
        )
        with mock.patch.object(self.faux, "_creer", return_value=refus):
            ecrit = self.pennylane().ecrire(
                self.lot(*FEC_SIMPLE), "CONCORDE/T2", False, Journal()
            )
        self.assertEqual(len(ecrit["erreurs"]), 2)
        self.assertIn("CONCORDE/T2/AN/1", ecrit["erreurs"][0])
        self.assertIn("not balanced", ecrit["erreurs"][0])

    def test_lire(self) -> None:
        """Vérifie la lecture : statuts exigés, période, lettrage."""
        connecteur = self.pennylane(statuts_lus="entry, complete")
        connecteur.ecrire(
            self.lot(*FEC_SIMPLE), "CONCORDE/T1", False, Journal()
        )
        self.faux.ecritures[1]["status"] = "draft"
        self.faux.lignes[0]["lettered_ledger_entry_lines"]["ids"] = [9999]
        lot = connecteur.lire({"du": date(2025, 1, 1), "au": None}, Journal())
        self.assertEqual(lot.totaux()["ecritures"], 1)  # brouillon exclu
        self.assertEqual(lot.lignes[0]["lettrage"], "P1002")
        self.assertEqual(lot.lignes[0]["journal_code"], "AN")
        vide = connecteur.lire(
            {"du": None, "au": date(2024, 12, 31)}, Journal()
        )
        self.assertEqual(vide.lignes, [])
        with self.assertRaises(ErreurConnexion):
            self.pennylane().lire({"du": None, "au": None}, Journal())

    def test_donnees_illisibles(self) -> None:
        """Vérifie le refus d'un montant à 3 décimales ou d'une date."""
        connecteur = self.pennylane(statuts_lus="entry")
        connecteur.ecrire(self.lot(*FEC_SIMPLE), "R", False, Journal())
        self.faux.lignes[0]["debit"] = "1.234"
        with self.assertRaises(ErreurConnexion):
            connecteur.relire("R", Journal())
        self.faux.lignes[0]["debit"] = "1000.00"
        self.faux.lignes[0]["date"] = "05/01/2025"
        with self.assertRaises(ErreurConnexion):
            connecteur.relire("R", Journal())

    def test_transfert_fec_vers_pennylane(self) -> None:
        """Vérifie le parcours complet vers Pennylane (bac à sable en test)."""
        source = self.annuaire_connexions.ajouter(
            "fec", "FEC", {"chemin": self.deposer(*FEC_SIMPLE)}
        )["id"]
        test = self.annuaire_connexions.ajouter(
            "pennylane", "Pennylane bac à sable", {}
        )["id"]
        vraie = self.annuaire_connexions.ajouter(
            "pennylane", "Pennylane cabinet", {}, test
        )["id"]
        for ident in (test, vraie):
            ecrire_variable(self.secrets, nom_variable(ident, "jeton"), "j")
        etat = transfert.creer(
            self.annuaire_connexions,
            self.demande(source, vraie),
            self.transferts,
            AUJ,
            Journal(),
            self.guardian,
        )
        self.assertEqual(etat["destinations"][vraie]["statut"], ATTENTE)
        fin = transfert.donner_feu_vert(
            self.annuaire_connexions,
            etat["id"],
            vraie,
            "Pennylane cabinet",
            AUJ,
            "Stéphane Moreau",
            self.transferts,
            AUJ,
            Journal(),
            self.guardian,
        )
        self.assertEqual(fin["statut"], TRANSFEREE)
        references = sorted(
            element_api["piece_number"] for element_api in self.faux.ecritures
        )
        self.assertEqual(len(references), 6)  # test1, test2, transfert
        self.assertTrue(references[0].endswith("/AN/1"))
