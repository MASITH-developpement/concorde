# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la montée pilotée (ADR-0012), avec un Docker simulé.

La vraie montée (Docker, OpenUpgrade, Odoo 14 -> 17, restauration de la
base livrée) est jouée par la CI (job montee-pilotee).
"""

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
import zipfile
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from unittest import mock

from core.montee_version import (
    commandes,
    inventaire,
    montee,
    openupgrade,
    photo,
)
from core.montee_version.commandes import ErreurCommande, executer
from core.montee_version.inventaire import classer_module, inventorier
from core.montee_version.openupgrade import (
    ErreurOpenUpgrade,
    lire_couverture,
    sauts,
    version_majeure,
)
from core.montee_version.sauvegarde import (
    ErreurSauvegarde,
    ecrire_sauvegarde,
    examiner_sauvegarde,
    extraire_sauvegarde,
    version_postgres,
)
from scripts import concorde_montee
from tests.test_montee_version import BasePhoto, reponses_odoo

COMPTES_MONTEE = [
    (10, "411000", None),
    (20, "706000", None),
    (30, "512000", None),
]
MODULES_CLIENT = ["account", "base", "l10n_fr"]


def table_couverture(*lignes: tuple[str, str]) -> str:
    """Table de couverture au format d'OpenUpgrade."""
    sortie = [
        "Module coverage",
        "+-----------+--------+---------+",
        "| Module    | Status + Extra   |",
        "+===========+========+=========+",
    ]
    for module, etat in lignes:
        sortie.append("| %s | %s | |" % (module, etat))
        sortie.append("+-----------+--------+---------+")
    return "\n".join(sortie)


def sauvegarde_zip(
    chemin: str, version: str | None = "14.0", base: str = "client_a"
) -> str:
    """Écrit une petite sauvegarde Odoo (.zip) ; rend son chemin."""
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.writestr("dump.sql", "SELECT 1;\n")
        archive.writestr("filestore/ab/abcdef", b"piece jointe")
        if version is not None:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {"version": version, "db_name": base, "pg_version": "13.4"}
                ),
            )
    return chemin


class FauxDocker:
    """Lanceur simulé : répond comme Docker, garde chaque commande."""

    def __init__(self) -> None:
        """Aucun conteneur au départ."""
        self.commandes: list[list[str]] = []
        self.existants: set[str] = set()
        self.saut_en_echec: int | None = None
        self.duree_saut = 0.0

    def __call__(
        self,
        arguments: Sequence[str],
        journal: str | None = None,
        entree: Any = None,
    ) -> str:
        """Joue une commande docker."""
        argv = list(arguments)
        self.commandes.append(argv)
        if hasattr(entree, "read"):
            entree.read()
        action = argv[1:3]
        if action[:2] in (["ps", "-aq"], ["network", "ls"]):
            nom = argv[-1].split("^")[-1].rstrip("$")
            return nom + "\n" if nom in self.existants else ""
        if action == ["network", "create"]:
            self.existants.add(argv[-1])
        elif argv[1:3] == ["run", "-d"]:
            self.existants.add(argv[argv.index("--name") + 1])
        elif argv[1] == "rm":
            self.existants.discard(argv[-1])
        elif action == ["network", "rm"]:
            self.existants.discard(argv[-1])
        elif argv[1] == "inspect":
            return "10.9.0.2\n"
        elif "--entrypoint" in argv:
            return "%d\n" % os.getuid()
        elif argv[1] == "run" and "--rm" in argv:
            cible = int(argv[argv.index("--name") + 1].rsplit("odoo", 1)[1])
            time.sleep(self.duree_saut)
            if journal:
                with open(journal, "a", encoding="utf-8") as fichier:
                    fichier.write(
                        "2026 INFO saut %d\n2026 1 ERROR x\n" % cible
                    )
            if cible == self.saut_en_echec:
                raise ErreurCommande("docker run : code 1. Traceback")
        elif "pg_dump" in argv:
            dossier = self.donnees_pg
            with open(os.path.join(dossier, "livraison.sql"), "w") as dump:
                dump.write("-- base montée\n")
        return ""

    donnees_pg = ""


class Atelier(unittest.TestCase):
    """Dossiers de montée, OpenUpgrade et base simulés."""

    def setUp(self) -> None:
        """Dossiers neufs, couvertures et photos simulées."""
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = os.path.join(self._tmp.name, "montees")
        self.openupgrade = os.path.join(self._tmp.name, "openupgrade")
        os.makedirs(self.racine)
        self.couvertures = {
            cible: [("account", "Done"), ("base", "Nothing to do")]
            for cible in (15, 16, 17, 18)
        }
        self.docker = FauxDocker()
        self.reponses_avant = reponses_odoo(COMPTES_MONTEE)
        self.reponses_avant[photo._SQL_VERSION_PHOTO] = [("14.0.1.3",)]
        self.reponses_apres = reponses_odoo(COMPTES_MONTEE)
        self.photos = 0
        for cible_patch in (
            mock.patch.object(montee, "recuperer", self.recuperer),
            mock.patch.object(
                montee, "connexion_lecture_seule", self.connexion
            ),
            mock.patch.object(montee, "place_libre", self.place_libre),
        ):
            cible_patch.start()
            self.addCleanup(cible_patch.stop)

    def tearDown(self) -> None:
        """Efface les dossiers."""
        self._tmp.cleanup()

    libre = 100 * montee.GO

    def place_libre(self, chemin: str) -> int:
        """Place disque simulée (100 Go par défaut)."""
        return self.libre

    def recuperer(self, racine: str, cible: int) -> str:
        """Copie d'OpenUpgrade simulée : la table de couverture seule."""
        dossier = os.path.join(racine, str(cible), "docsource")
        os.makedirs(dossier, exist_ok=True)
        with open(
            os.path.join(dossier, "modules%d0-%d0.rst" % (cible - 1, cible)),
            "w",
            encoding="utf-8",
        ) as fichier:
            fichier.write(table_couverture(*self.couvertures[cible]))
        racine_copie = os.path.dirname(dossier)
        os.makedirs(
            os.path.join(racine_copie, "openupgrade_scripts"), exist_ok=True
        )
        with open(
            os.path.join(racine_copie, "openupgrade_scripts", "apriori.py"),
            "w",
            encoding="utf-8",
        ) as fichier:
            fichier.write("renamed_modules = {}\nmerged_modules = {}\n")
        return racine_copie

    def connexion(self, base: str, acces: dict[str, str]) -> BasePhoto:
        """Base restaurée simulée : avant puis après la montée."""
        self.assertEqual(acces["host"], "10.9.0.2")
        reponses = dict(
            self.reponses_avant if self.photos < 2 else self.reponses_apres
        )
        self.photos += 1
        reponses[inventaire._SQL_MODULES_INSTALLES] = [
            (module,) for module in MODULES_CLIENT
        ]
        return BasePhoto(reponses)

    def nouvelle(self, arrivee: int = 17, **options: Any) -> montee.Montee:
        """Montée créée depuis une sauvegarde neuve."""
        zip_client = sauvegarde_zip(
            os.path.join(self._tmp.name, "client_%d.zip" % time.time_ns()),
            **options,
        )
        etat = montee.creer(self.racine, zip_client, arrivee)
        conduite = montee.Montee(
            self.racine, etat["id"], self.openupgrade, self.docker
        )
        self.docker.donnees_pg = os.path.join(conduite.donnees, "pgdata")
        return conduite


class TestCircuit(Atelier):
    """Étapes 1 à 4 : inventaire, photos, sauts, comparaison."""

    def test_circuit_sans_ecart(self) -> None:
        """Vérifie le circuit complet et les garde-fous des conteneurs."""
        conduite = self.nouvelle()
        self.assertEqual(conduite.circuit(), montee.ATTENTE)
        etat = montee.charger(self.racine, conduite.etat["id"])
        self.assertEqual(
            [
                etat["etapes"][nom]["statut"]
                for nom in montee.ETAPES_MONTEE[:5]
            ],
            ["verte"] * 5,
        )
        self.assertEqual(
            sorted(etat["etapes"]["sauts"]["infos"]), ["15", "16", "17"]
        )
        self.assertEqual(
            etat["etapes"]["sauts"]["infos"]["15"]["lignes_erreur"], 1
        )
        commandes_texte = [" ".join(argv) for argv in self.docker.commandes]
        self.assertTrue(
            any(
                "network create --internal" in texte
                for texte in commandes_texte
            )
        )
        lancements = [
            argv for argv in self.docker.commandes if argv[1] == "run"
        ]
        self.assertIn("postgres:13", lancements[0])
        for argv in lancements:
            self.assertNotIn("-p", argv)
            self.assertNotIn("--publish", argv)
        for argv in lancements[:1] + [
            argv
            for argv in lancements
            if "--rm" in argv and "--entrypoint" not in argv
        ]:
            self.assertIn("--memory", argv)
            self.assertIn("--env-file", argv)
        acces = conduite._fichier_acces()
        self.assertEqual(stat.S_IMODE(os.stat(acces).st_mode), 0o600)
        mot = conduite._acces()["POSTGRES_PASSWORD"]
        self.assertFalse(any(mot in texte for texte in commandes_texte))
        self.assertNotIn(mot, json.dumps(etat))
        self.assertTrue(
            any(argv[1:3] == ["image", "rm"] for argv in self.docker.commandes)
        )
        self.assertFalse(self.docker.existants)

    def test_inventaire_bloquant(self) -> None:
        """Vérifie qu'un module non couvert arrête avant toute montée."""
        self.couvertures[16] = [("account", "Done"), ("autre", "Done")]
        MODULES_CLIENT.append("perso")
        self.addCleanup(MODULES_CLIENT.remove, "perso")
        conduite = self.nouvelle()
        self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        etape = montee.charger(self.racine, conduite.etat["id"])["etapes"][
            "inventaire"
        ]
        self.assertIn("Odoo 15 : perso", etape["erreur"])
        self.assertFalse(
            any(
                "--rm" in argv and "--name" in argv
                for argv in self.docker.commandes
            )
        )

    def test_saut_en_echec(self) -> None:
        """Vérifie l'arrêt au saut en échec, saut et cause nommés."""
        self.docker.saut_en_echec = 16
        conduite = self.nouvelle()
        self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        etat = montee.charger(self.racine, conduite.etat["id"])
        self.assertIn("Odoo 16", etat["etapes"]["sauts"]["erreur"])
        self.assertIn("Saut vers Odoo 16", etat["etapes"]["arret"]["erreur"])
        self.assertEqual(
            etat["etapes"]["sauts"]["infos"]["15"]["statut"], "verte"
        )

    def test_disque_qui_se_remplit(self) -> None:
        """Vérifie que le saut est arrêté si le disque se remplit."""
        self.docker.saut_en_echec = 15
        self.docker.duree_saut = 0.3
        conduite = self.nouvelle()
        libres = iter([100 * montee.GO] + [montee.GO] * 100)
        with mock.patch.object(
            montee, "SURVEILLANCE_S", 0.05
        ), mock.patch.object(
            montee, "place_libre", lambda chemin: next(libres)
        ):
            self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        etat = montee.charger(self.racine, conduite.etat["id"])
        self.assertIn(
            "disque presque plein", etat["etapes"]["sauts"]["erreur"]
        )
        self.assertTrue(
            any(argv[1] == "kill" for argv in self.docker.commandes)
        )

    def test_ecart_bloque(self) -> None:
        """Vérifie qu'un centime d'écart bloque la montée."""
        lignes = list(self.reponses_apres[montee_photo_sql()])
        lignes[0] = lignes[0][:4] + (Decimal("120.01"),) + lignes[0][5:]
        self.reponses_apres[montee_photo_sql()] = lignes
        conduite = self.nouvelle()
        self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        etape = montee.charger(self.racine, conduite.etat["id"])["etapes"][
            "comparaison"
        ]
        self.assertGreater(etape["infos"]["ecarts"], 0)

    def test_place_insuffisante(self) -> None:
        """Vérifie le refus avant de commencer, chiffres donnés."""
        with self.assertRaises(montee.ErreurMontee) as contexte:
            with mock.patch.object(montee, "place_libre", lambda chemin: 1):
                montee.verifier_place(self.racine, montee.GO)
        self.assertIn("Agrandir le disque", str(contexte.exception))
        conduite = self.nouvelle()
        with mock.patch.object(montee, "place_libre", lambda chemin: 1):
            self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        self.assertFalse(
            [argv for argv in self.docker.commandes if argv[1] == "run"]
        )


def montee_photo_sql() -> str:
    """Requête des lignes de la photo (pour fabriquer un écart)."""
    return photo._SQL_LIGNES_PHOTO


class TestCasLimites(Atelier):
    """Pannes nommées : PostgreSQL muet, base incohérente, image."""

    def test_postgres_muet(self) -> None:
        """Vérifie l'abandon après les essais, cause nommée."""
        conduite = self.nouvelle()

        def muet(arguments: Sequence[str], *autres: Any) -> str:
            """pg_isready échoue toujours."""
            if "pg_isready" in arguments:
                raise ErreurCommande("pg_isready : code 2.")
            return self.docker(arguments, *autres)

        conduite.lancer = muet
        with mock.patch("time.sleep", lambda duree: None):
            with self.assertRaises(montee.ErreurMontee) as contexte:
                conduite._attendre_postgres(essais=2)
        self.assertIn("pas prêt", str(contexte.exception))

    def test_base_differente_de_la_sauvegarde(self) -> None:
        """Vérifie l'arrêt si la base restaurée n'a pas la version annoncée."""
        self.reponses_avant[photo._SQL_VERSION_PHOTO] = [("15.0.1",)]
        conduite = self.nouvelle()
        self.assertEqual(conduite.circuit(), montee.BLOQUEE)
        etat = montee.charger(self.racine, conduite.etat["id"])
        self.assertIn("incohérente", etat["etapes"]["arret"]["erreur"])

    def test_compte_odoo_illisible_et_image_gardee(self) -> None:
        """Vérifie le refus d'un uid illisible et l'image Odoo gardée."""
        conduite = self.nouvelle()

        def bavard(arguments: Sequence[str], *autres: Any) -> str:
            """id rend du texte ; l'image Odoo refuse d'être effacée."""
            if "--entrypoint" in arguments:
                return "odoo\n"
            if (
                list(arguments[1:3]) == ["image", "rm"]
                and "-f" not in arguments
            ):
                raise ErreurCommande("docker image rm : code 1. en service")
            return self.docker(arguments, *autres)

        conduite.lancer = bavard
        with self.assertRaises(montee.ErreurMontee):
            conduite._proprietaire_odoo("image")
        conduite._effacer_image("concorde-openupgrade:15", 15)

    def test_reprise_apres_restauration(self) -> None:
        """Vérifie qu'une reprise ne restaure pas deux fois."""
        conduite = self.nouvelle()
        with conduite.conteneurs():
            pass
        os.makedirs(
            os.path.join(
                conduite.donnees, "odoo", "filestore", montee.NOM_BASE
            ),
            exist_ok=True,
        )
        avant = len(self.docker.commandes)
        with conduite.conteneurs():
            pass
        self.assertFalse(
            any("psql" in argv for argv in self.docker.commandes[avant:])
        )


class TestFeuVertEtLivraison(Atelier):
    """Étapes 5 à 7 : feu vert, nouvel essai, livraison."""

    def test_parcours_complet(self) -> None:
        """Vérifie feu vert, nouvel essai et sauvegarde livrée."""
        conduite = self.nouvelle()
        conduite.circuit()
        with self.assertRaises(montee.ErreurMontee):
            conduite.livrer()
        with self.assertRaises(montee.ErreurMontee):
            conduite.donner_feu_vert("autre_base", "test")
        conduite.donner_feu_vert("client_a", "test")
        with self.assertRaises(montee.ErreurMontee):
            conduite.donner_feu_vert("client_a", "test")
        fraiche = sauvegarde_zip(os.path.join(self._tmp.name, "fraiche.zip"))
        self.photos = 0
        essai_lanceur = self.docker

        statut = montee.nouvel_essai(
            self.racine,
            conduite.etat["id"],
            fraiche,
            self.openupgrade,
            essai_lanceur,
        )
        self.assertEqual(statut, montee.ATTENTE)
        conduite = montee.Montee(
            self.racine, conduite.etat["id"], self.openupgrade, self.docker
        )
        essai = conduite.etat["etapes"]["nouvel_essai"]["infos"]["montee"]
        self.docker.donnees_pg = os.path.join(
            self.racine, essai, "donnees", "pgdata"
        )
        sauvegarde_livree = conduite.livrer()
        info = examiner_sauvegarde(sauvegarde_livree)
        self.assertEqual((info["version"], info["base"]), ("17.0", "client_a"))
        self.assertEqual(info["pieces_jointes"], 1)
        etat = montee.charger(self.racine, conduite.etat["id"])
        self.assertEqual(etat["statut"], montee.LIVREE)
        self.assertEqual(
            etat["etapes"]["livraison"]["infos"]["sha256"], info["sha256"]
        )

    def test_nouvel_essai_refuse(self) -> None:
        """Vérifie les refus : sans feu vert, ou avec une autre base."""
        conduite = self.nouvelle()
        conduite.circuit()
        fraiche = sauvegarde_zip(
            os.path.join(self._tmp.name, "autre.zip"), base="client_b"
        )
        with self.assertRaises(montee.ErreurMontee):
            montee.nouvel_essai(
                self.racine,
                conduite.etat["id"],
                fraiche,
                self.openupgrade,
                self.docker,
            )
        conduite.donner_feu_vert("client_a", "test")
        with self.assertRaises(montee.ErreurMontee) as contexte:
            montee.nouvel_essai(
                self.racine,
                conduite.etat["id"],
                sauvegarde_zip(
                    os.path.join(self._tmp.name, "autre2.zip"), base="client_b"
                ),
                self.openupgrade,
                self.docker,
            )
        self.assertIn("même base", str(contexte.exception))


class TestCreation(Atelier):
    """Création d'une montée et identifiants."""

    def test_refus_a_la_creation(self) -> None:
        """Vérifie les refus : sans version, saut impossible, pas un zip."""
        with self.assertRaises(montee.ErreurMontee):
            self.nouvelle(version=None)
        with self.assertRaises(ErreurOpenUpgrade):
            self.nouvelle(arrivee=14)
        pas_zip = os.path.join(self._tmp.name, "faux.zip")
        with open(pas_zip, "w", encoding="utf-8") as fichier:
            fichier.write("pas un zip")
        with self.assertRaises(ErreurSauvegarde):
            montee.creer(self.racine, pas_zip, 17)
        for ident in ("../x", "X1", "M1/2"):
            with self.assertRaises(montee.ErreurMontee):
                montee.charger(self.racine, ident)
        with self.assertRaises(montee.ErreurMontee):
            montee.charger(self.racine, "M20260101000000-abcd")


class TestSauvegarde(unittest.TestCase):
    """Sauvegarde Odoo : lecture, extraction, écriture."""

    def test_aller_retour(self) -> None:
        """Vérifie l'examen, l'extraction et l'écriture d'une sauvegarde."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = sauvegarde_zip(os.path.join(dossier, "s.zip"))
            info = examiner_sauvegarde(chemin)
            self.assertEqual(info["version"], "14.0")
            self.assertEqual(info["pieces_jointes"], 1)
            dump, pieces = extraire_sauvegarde(
                chemin, os.path.join(dossier, "x")
            )
            self.assertTrue(
                os.path.isfile(os.path.join(pieces, "ab", "abcdef"))
            )
            sortie = os.path.join(dossier, "l.zip")
            empreinte = ecrire_sauvegarde(
                sortie, dump, pieces, {"version": "17.0"}
            )
            self.assertEqual(examiner_sauvegarde(sortie)["sha256"], empreinte)

    def test_version_postgres(self) -> None:
        """Vérifie la version de PostgreSQL du client, et ses refus."""
        self.assertEqual(version_postgres(None), 13)
        self.assertEqual(version_postgres("16.2"), 16)
        for mauvaise_version in ("9.6", "18", "abc"):
            with self.assertRaises(ErreurSauvegarde):
                version_postgres(mauvaise_version)

    def test_refus(self) -> None:
        """Vérifie les refus : chemin dangereux, sans dump, manifeste faux."""
        with tempfile.TemporaryDirectory() as dossier:
            for nom, contenu in (
                ("../evasion", "x"),
                ("/absolu", "x"),
                ("autre.txt", "x"),
            ):
                chemin = os.path.join(dossier, "z.zip")
                with zipfile.ZipFile(chemin, "w") as archive:
                    archive.writestr(nom, contenu)
                with self.assertRaises(ErreurSauvegarde):
                    examiner_sauvegarde(chemin)
                with self.assertRaises(ErreurSauvegarde):
                    extraire_sauvegarde(chemin, os.path.join(dossier, "e"))
            with zipfile.ZipFile(chemin, "w") as archive:
                archive.writestr("dump.sql", "x")
                archive.writestr("manifest.json", "{pas du json")
            with self.assertRaises(ErreurSauvegarde):
                examiner_sauvegarde(chemin)


class TestOpenUpgradeEtInventaire(unittest.TestCase):
    """Références d'OpenUpgrade et règle de l'inventaire."""

    def test_lire_couverture(self) -> None:
        """Vérifie la lecture des marques |new| et |del|, des notes, des « + »."""
        texte = "\n".join(
            [
                "| Module | Status               + Extra |",
                "| account | Done | |",
                "| |new| account_lock |                      | |",
                "| |del| association | |Merged into membership.|",
                "| sale | Nothing To Do + |",
            ]
        )
        table = lire_couverture(texte)
        self.assertEqual(
            table["account"], {"etat": "Done", "note": "", "retire": False}
        )
        self.assertEqual(table["account_lock"]["etat"], "")
        self.assertTrue(table["association"]["retire"])
        self.assertEqual(
            openupgrade.fusion_notee(table["association"]["note"]),
            "membership",
        )
        self.assertEqual(table["sale"]["etat"], "Nothing To Do")
        with self.assertRaises(ErreurOpenUpgrade):
            lire_couverture("pas une table")

    def test_lire_apriori(self) -> None:
        """Vérifie la lecture des fusions, sans rien exécuter."""
        self.assertEqual(
            openupgrade.lire_apriori(
                "import os\nrenamed_modules = {'note': 'project_todo'}\n"
                "merged_modules = {'l10n_generic_coa': 'account'}\n"
                "autre = {'x': 'y'}\n"
            ),
            {"note": "project_todo", "l10n_generic_coa": "account"},
        )
        with self.assertRaises(ErreurOpenUpgrade):
            openupgrade.lire_apriori("merged_modules = dict(os.environ)\n")

    def test_sauts_et_versions(self) -> None:
        """Vérifie les sauts possibles et la lecture des versions."""
        self.assertEqual(sauts(14, 18), [15, 16, 17, 18])
        for depart, arrivee in ((13, 15), (16, 16), (17, 19), (16, 15)):
            with self.assertRaises(ErreurOpenUpgrade):
                sauts(depart, arrivee)
        self.assertEqual(version_majeure("16.0.1.3"), 16)
        with self.assertRaises(ErreurOpenUpgrade):
            version_majeure("saas~17")

    def test_classer_module(self) -> None:
        """Vérifie les trois classes et leurs causes."""

        def entree(
            etat: str = "", note: str = "", retire: bool = False
        ) -> Any:
            """Ligne de table de couverture."""
            return {"etat": etat, "note": note, "retire": retire}

        self.assertEqual(
            classer_module("account", entree("Done"), None), ("couvert", "")
        )
        self.assertEqual(
            classer_module("x", entree("nothing to do"), None)[0], "couvert"
        )
        self.assertEqual(
            classer_module(
                "snailmail_account", entree(note="No DB layout changes."), None
            )[0],
            "couvert",
        )
        self.assertIn("payment", classer_module("p", None, "payment")[1])
        self.assertEqual(
            classer_module("base", entree("Done (partial)"), None)[0],
            "a_verifier",
        )
        self.assertIn(
            "retiré", classer_module("x", entree(retire=True), None)[1]
        )
        self.assertEqual(
            classer_module("l10n_fr", entree(), None)[0], "a_verifier"
        )
        self.assertIn("non listée", classer_module("l10n_fr", None, None)[1])
        self.assertIn(
            "Enterprise", classer_module("account_accountant", None, None)[1]
        )
        self.assertIn(
            "non annoté", classer_module("sale_x", entree(), None)[1]
        )

    def test_inventorier(self) -> None:
        """Vérifie le suivi des fusions et retraits, et la table manquante."""

        def ligne(
            etat: str = "Done", note: str = "", retire: bool = False
        ) -> Any:
            """Ligne de table de couverture."""
            return {"etat": etat, "note": note, "retire": retire}

        resultat = inventorier(
            "b",
            "15.0.1",
            ["account", "perso", "patch", "vieux"],
            17,
            {
                16: {
                    "modules": {
                        "account": ligne(),
                        "patch": ligne("", "Merged into payment.", True),
                        "vieux": ligne("", "", True),
                    },
                    "fusions": {},
                },
                17: {
                    "modules": {"account": ligne(), "payment": ligne()},
                    "fusions": {"perso": "account"},
                },
            },
        )
        self.assertTrue(resultat["bloque"])
        premier, second = resultat["sauts"]
        self.assertEqual(
            [m["module"] for m in premier["bloquants"]], ["perso"]
        )
        self.assertEqual(
            [m["module"] for m in premier["a_verifier"]], ["vieux"]
        )
        self.assertEqual((second["couverts"], second["bloquants"]), (3, []))
        with self.assertRaises(ErreurOpenUpgrade):
            inventorier(
                "b",
                "15.0",
                ["account"],
                17,
                {16: {"modules": {}, "fusions": {}}},
            )

    def test_recuperer(self) -> None:
        """Vérifie la reprise d'une copie et le refus d'un autre commit."""
        with tempfile.TemporaryDirectory() as racine:
            with self.assertRaises(ErreurOpenUpgrade):
                openupgrade.recuperer(racine, 19)
            os.makedirs(os.path.join(racine, "17", ".git"))
            reponses = iter(
                [openupgrade.COMMITS_OPENUPGRADE[17] + "\n", "autre\n"]
            )
            with mock.patch.object(
                openupgrade, "executer", lambda arguments: next(reponses)
            ):
                self.assertEqual(
                    openupgrade.recuperer(racine, 17),
                    os.path.join(racine, "17"),
                )
                with self.assertRaises(ErreurOpenUpgrade):
                    openupgrade.recuperer(racine, 17)
            appels: list[list[str]] = []

            def git(arguments: list[str]) -> str:
                """git simulé : copie neuve au bon commit."""
                appels.append(arguments)
                return openupgrade.COMMITS_OPENUPGRADE[16]

            with mock.patch.object(openupgrade, "executer", git):
                openupgrade.recuperer(racine, 16)
            self.assertIn("fetch", appels[1])


class TestCommandes(unittest.TestCase):
    """Lancement des programmes."""

    def test_executer(self) -> None:
        """Vérifie sortie, entrée, journal, échec et délai."""
        self.assertEqual(executer([sys.executable, "-c", "print(1)"]), "1\n")
        self.assertEqual(
            executer(
                [sys.executable, "-c", "import sys;print(sys.stdin.read())"],
                entree=b"abc",
            ),
            "abc\n",
        )
        with tempfile.TemporaryDirectory() as dossier:
            journal = os.path.join(dossier, "j.log")
            with self.assertRaises(ErreurCommande) as contexte:
                executer(
                    [
                        sys.executable,
                        "-c",
                        "print('cause');raise SystemExit(3)",
                    ],
                    journal=journal,
                )
            self.assertIn("code 3", str(contexte.exception))
            self.assertIn("cause", str(contexte.exception))
        with self.assertRaises(ErreurCommande) as contexte:
            executer(
                [sys.executable, "-c", "import time;time.sleep(5)"], delai=0.2
            )
        self.assertIn("arrêté", str(contexte.exception))
        self.assertIn(
            "illisible", commandes.fin_de_sortie("", "/inexistant/journal.log")
        )
        self.assertIn(
            "illisible", montee.fin_de_journal("/inexistant/journal.log")
        )


class TestCommandeMonteePilotee(Atelier):
    """Sous-commandes de conduite (Docker simulé)."""

    def lancer(self, *arguments: str) -> tuple[int, str]:
        """Lance concorde_montee ; rend le code et la sortie."""
        sortie = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            [
                "concorde_montee",
                "--racine",
                self.racine,
                "--openupgrade",
                self.openupgrade,
                *arguments,
            ],
        ), contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(
            sortie
        ), mock.patch.object(
            montee, "executer", self.docker
        ):
            code = concorde_montee.main()
        return code, sortie.getvalue()

    def test_parcours_en_ligne_de_commande(self) -> None:
        """Vérifie creer, circuit, feu-vert, etat et les refus."""
        zip_client = sauvegarde_zip(os.path.join(self._tmp.name, "c.zip"))
        code, sortie = self.lancer("creer", zip_client, "17")
        self.assertEqual(code, 0, sortie)
        ident = sortie.strip().splitlines()[-1]
        code, sortie = self.lancer("circuit", ident)
        self.assertEqual(code, 0, sortie)
        self.assertIn("attente_feu_vert", sortie)
        code, sortie = self.lancer("feu-vert", ident, "client_a")
        self.assertEqual(code, 0, sortie)
        code, sortie = self.lancer("livrer", ident)
        self.assertEqual(code, 2)
        self.assertIn("nouvel_essai", sortie)
        code, sortie = self.lancer("etat", "M-inconnue")
        self.assertEqual(code, 2)
        fraiche = sauvegarde_zip(os.path.join(self._tmp.name, "f.zip"))
        self.photos = 0
        code, sortie = self.lancer("nouvel-essai", ident, fraiche)
        self.assertEqual(code, 0, sortie)


if __name__ == "__main__":
    unittest.main()
