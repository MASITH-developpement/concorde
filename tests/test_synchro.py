# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Synchronisation du serveur sur main : jamais d'échec muet.

Le script deploy/concorde-sync.sh est lancé sur un dépôt jetable (dépôt
distant nu + copie de travail), puis son état est relu par
core.surveillance.constats_synchro, comme le fait l'interface.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from core.montee_version.commandes import ErreurCommande, executer
from core.surveillance import AGE_MAX_SYNCHRO_S, constats_synchro
from tests.outils import RACINE_DEPOT

SCRIPT_SYNCHRO = os.path.join(RACINE_DEPOT, "deploy", "concorde-sync.sh")
IDENTITE_GIT = ["-c", "user.name=essai", "-c", "user.email=essai@exemple.fr"]


def codes(constats: list[dict[str, object]]) -> list[object]:
    """Codes des constats, dans l'ordre."""
    return [constat_lu["code"] for constat_lu in constats]


class TestConstatsSynchro(unittest.TestCase):
    """Lecture de l'état écrit par le script."""

    def ecrire(self, contenu: str) -> str:
        """Écrit un état dans un fichier temporaire et rend son chemin."""
        chemin = os.path.join(tempfile.mkdtemp(), "etat.json")
        with open(chemin, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
        return chemin

    def etat(self, statut: str, il_y_a: timedelta) -> str:
        """État JSON daté d'il y a `il_y_a`."""
        return self.ecrire(
            json.dumps(
                {
                    "date": (datetime.now() - il_y_a).isoformat(
                        timespec="seconds"
                    ),
                    "statut": statut,
                    "etape": "fetch",
                    "message": "accès refusé",
                    "head": "abc",
                }
            )
        )

    def test_etat_absent_ou_illisible(self) -> None:
        """Pas d'état, JSON cassé ou date absente : synchro arrêtée."""
        absent = os.path.join(tempfile.mkdtemp(), "etat.json")
        for chemin in (
            absent,
            self.ecrire("{pas du json"),
            self.ecrire('{"statut": "ok"}'),
            self.ecrire('{"date": 12, "statut": "ok"}'),
        ):
            with self.subTest(chemin=chemin):
                self.assertEqual(
                    codes(constats_synchro(chemin)), ["SYNCHRO_ARRETEE"]
                )

    def test_synchro_recente_et_reussie(self) -> None:
        """Passage réussi il y a une minute : aucune alerte."""
        chemin = self.etat("ok", timedelta(minutes=1))
        self.assertEqual(constats_synchro(chemin), [])

    def test_synchro_ancienne(self) -> None:
        """Plus de passage depuis 10 minutes (cron arrêté) : alerte."""
        chemin = self.etat("ok", timedelta(seconds=AGE_MAX_SYNCHRO_S + 60))
        self.assertEqual(codes(constats_synchro(chemin)), ["SYNCHRO_ARRETEE"])

    def test_synchro_en_echec(self) -> None:
        """Échec : alerte avec l'étape et le message du script."""
        constats = constats_synchro(self.etat("echec", timedelta(0)))
        self.assertEqual(codes(constats), ["SYNCHRO_ECHEC"])
        self.assertEqual(constats[0]["exemples"], ["fetch : accès refusé"])


class TestScriptSynchro(unittest.TestCase):
    """deploy/concorde-sync.sh sur un dépôt jetable."""

    def setUp(self) -> None:
        """Dépôt distant nu, une branche main et une copie synchronisée."""
        self.dossier = tempfile.mkdtemp()
        self.distant = os.path.join(self.dossier, "distant.git")
        self.copie_travail = os.path.join(self.dossier, "travail")
        self.depot = os.path.join(self.dossier, "depot")
        executer(["git", "init", "-q", "--bare", self.distant])
        executer(["git", "clone", "-q", self.distant, self.copie_travail])
        self.publier("premier")
        executer(
            ["git", "clone", "-q", "-b", "main", self.distant, self.depot]
        )
        self.etat = os.path.join(self.dossier, "etat", "etat.json")
        self.environnement = {
            "CONCORDE_DEPOT": self.depot,
            "CONCORDE_SYNCHRO_JOURNAL": os.path.join(self.dossier, "sync.log"),
            "CONCORDE_SYNCHRO_DOSSIER": os.path.join(self.dossier, "etat"),
        }

    def publier(self, message: str) -> None:
        """Pousse un commit vide sur main du dépôt distant."""
        executer(
            ["git", "-C", self.copie_travail]
            + IDENTITE_GIT
            + ["commit", "-q", "--allow-empty", "-m", message]
        )
        executer(
            [
                "git",
                "-C",
                self.copie_travail,
                "push",
                "-q",
                "origin",
                "HEAD:main",
            ]
        )

    def lancer(self) -> None:
        """Lance le script avec les chemins du dépôt jetable."""
        with mock.patch.dict(os.environ, self.environnement):
            executer(["bash", SCRIPT_SYNCHRO])

    def tete(self, depot: str) -> str:
        """Commit courant d'un dépôt."""
        return executer(["git", "-C", depot, "rev-parse", "HEAD"]).strip()

    def test_a_jour_puis_nouveau_commit(self) -> None:
        """Passages réussis : état « ok » relu sans alerte, copie à jour."""
        self.lancer()
        self.assertEqual(constats_synchro(self.etat), [])
        self.publier("second")
        self.lancer()
        self.assertEqual(self.tete(self.depot), self.tete(self.copie_travail))
        with open(self.etat, encoding="utf-8") as fichier:
            self.assertEqual(json.load(fichier)["statut"], "ok")

    def test_recuperation_impossible(self) -> None:
        """Dépôt distant injoignable : code retour non nul et alerte."""
        executer(
            [
                "git",
                "-C",
                self.depot,
                "remote",
                "set-url",
                "origin",
                os.path.join(self.dossier, "inexistant.git"),
            ]
        )
        with self.assertRaises(ErreurCommande):
            self.lancer()
        constats = constats_synchro(self.etat)
        self.assertEqual(codes(constats), ["SYNCHRO_ECHEC"])
        self.assertTrue(constats[0]["exemples"][0].startswith("fetch : "))


if __name__ == "__main__":
    unittest.main()
