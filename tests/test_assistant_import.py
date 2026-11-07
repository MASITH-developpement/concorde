# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de l'assistant d'import Odoo (wizard/concorde_import_wizard.py).

Odoo n'est pas installé sur le poste de test : installer_bouchons_odoo()
remplace les modules odoo utilisés à l'import par des bouchons minimaux,
et le moteur embarqué est chargé depuis core/ (sa source : install_module.sh
le copie dans deploy/addons/concorde/engine).
"""

import html
import importlib.util
import os
import sys
import types
import unittest
from collections.abc import Mapping
from typing import Protocol

from tests.outils import RACINE_DEPOT

DOSSIER_MODULE = os.path.join(RACINE_DEPOT, "deploy", "addons", "concorde")
OCTETS_DEBUT_ZIP = b"PK\x03\x04"
TYPES_CHAMPS_ODOO = (
    "Binary",
    "Boolean",
    "Char",
    "Html",
    "Integer",
    "Many2one",
    "Selection",
    "Text",
)


class ErreurUtilisateurBouchon(Exception):
    """Remplace odoo.exceptions.UserError pendant les tests."""


def champ_bouchon(*_arguments: object, **_options: object) -> None:
    """Remplace un constructeur de champ Odoo (fields.Char, fields.Binary...).

    Rôle : accepter la déclaration d'un champ sans serveur Odoo.
    Paramètres : _arguments et _options du champ, ignorés.
    Retour : None.
    Erreurs : aucune.
    Usages : installer_bouchons_odoo().
    """
    return None


def creer_module_bouchon(
    nom_module: str,
    chemins_paquet: list[str] | None = None,
    attributs: Mapping[str, object] | None = None,
) -> types.ModuleType:
    """Crée un module et l'enregistre dans sys.modules.

    Rôle : simuler un module ou un paquet odoo.
    Paramètres : nom_module (nom pointé), chemins_paquet (liste de dossiers
    si le module est un paquet, None sinon), attributs (noms et valeurs
    exposés par le module, None pour un module vide).
    Retour : le module créé.
    Erreurs : aucune.
    Usages : installer_bouchons_odoo().
    """
    module_bouchon = types.ModuleType(nom_module)
    if chemins_paquet is not None:
        module_bouchon.__path__ = chemins_paquet
    if attributs is not None:
        vars(module_bouchon).update(attributs)
    sys.modules[nom_module] = module_bouchon
    return module_bouchon


def installer_bouchons_odoo() -> None:
    """Installe dans sys.modules les bouchons odoo nécessaires à l'assistant.

    Rôle : permettre d'importer l'assistant sans serveur Odoo.
    Paramètres : aucun.
    Retour : aucun (modifie sys.modules).
    Erreurs : aucune.
    Usages : charger_assistant_import().
    """
    modeles_odoo = types.SimpleNamespace(TransientModel=object, Model=object)
    creer_module_bouchon(
        "odoo",
        [],
        {
            "_": str,
            "api": types.SimpleNamespace(model=lambda methode: methode),
            "fields": types.SimpleNamespace(
                **{
                    type_champ: champ_bouchon
                    for type_champ in TYPES_CHAMPS_ODOO
                }
            ),
            "models": modeles_odoo,
        },
    )
    creer_module_bouchon(
        "odoo.exceptions", attributs={"UserError": ErreurUtilisateurBouchon}
    )
    creer_module_bouchon("odoo.tools", attributs={"html_escape": html.escape})
    creer_module_bouchon(
        "odoo.release",
        attributs={
            "version_info": (17, 0, 0, "final", 0, ""),
            "version": "17.0",
        },
    )
    creer_module_bouchon("odoo.addons", [])
    creer_module_bouchon("odoo.addons.concorde", [DOSSIER_MODULE])
    creer_module_bouchon(
        "odoo.addons.concorde.engine", [os.path.join(RACINE_DEPOT, "core")]
    )


def charger_assistant_import() -> types.ModuleType:
    """Charge le fichier de l'assistant d'import et rend son module.

    Rôle : importer wizard/concorde_import_wizard.py hors d'Odoo.
    Paramètres : aucun.
    Retour : le module chargé.
    Erreurs : ImportError si le fichier est introuvable ou si une
    dépendance manque.
    Usages : TestLireBinaire.
    """
    installer_bouchons_odoo()
    chemin_assistant = os.path.join(
        DOSSIER_MODULE, "wizard", "concorde_import_wizard.py"
    )
    spec_assistant = importlib.util.spec_from_file_location(
        "concorde_import_wizard_test", chemin_assistant
    )
    if spec_assistant is None or spec_assistant.loader is None:
        raise ImportError("Assistant d'import illisible : " + chemin_assistant)
    module_assistant = importlib.util.module_from_spec(spec_assistant)
    spec_assistant.loader.exec_module(module_assistant)
    return module_assistant


class AssistantImport(Protocol):
    """Partie de l'assistant d'import Odoo vérifiée par ces tests."""

    def _lire_binaire(self, valeur: object) -> bytes:
        """Rend le contenu brut (octets) d'un champ Binary."""


class TestLireBinaire(unittest.TestCase):
    """_lire_binaire : contenu brut d'un champ Binary, toutes versions."""

    assistant: AssistantImport

    @classmethod
    def setUpClass(cls) -> None:
        """Charge une seule fois l'assistant d'import hors d'Odoo."""
        cls.assistant = charger_assistant_import().ConcordeImportWizard()

    def test_valeur_inattendue_leve_erreur_utilisateur(self) -> None:
        """Un type inattendu doit donner le message prévu, pas un plantage."""
        with self.assertRaises(ErreurUtilisateurBouchon) as erreur_levee:
            self.assistant._lire_binaire(object())
        self.assertIn("Type de fichier inattendu", str(erreur_levee.exception))

    def test_base64_simple_decode(self) -> None:
        """Une chaîne base64 (Odoo <= 19) rend les octets du fichier."""
        contenu_lu = self.assistant._lire_binaire("UEsDBA==")
        self.assertEqual(contenu_lu, OCTETS_DEBUT_ZIP)

    def test_double_encodage_deballe(self) -> None:
        """Un contenu encodé deux fois en base64 rend les octets réels."""
        contenu_lu = self.assistant._lire_binaire("VUVzREJBPT0=")
        self.assertEqual(contenu_lu, OCTETS_DEBUT_ZIP)


if __name__ == "__main__":
    unittest.main()
