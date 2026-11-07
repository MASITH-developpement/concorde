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

RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def champ_bouchon(*_arguments, **_options):
    """Remplace un constructeur de champ Odoo (fields.Char, fields.Binary...).

    Rôle : accepter la déclaration d'un champ sans serveur Odoo.
    Paramètres : _arguments et _options du champ, ignorés.
    Retour : None.
    Erreurs : aucune.
    Usages : installer_bouchons_odoo().
    """
    return None


def creer_module_bouchon(nom_module, chemins_paquet=None):
    """Crée un module vide et l'enregistre dans sys.modules.

    Rôle : simuler un module ou un paquet odoo.
    Paramètres : nom_module (nom pointé), chemins_paquet (liste de dossiers
    si le module est un paquet, None sinon).
    Retour : le module créé.
    Erreurs : aucune.
    Usages : installer_bouchons_odoo().
    """
    module_bouchon = types.ModuleType(nom_module)
    if chemins_paquet is not None:
        module_bouchon.__path__ = chemins_paquet
    sys.modules[nom_module] = module_bouchon
    return module_bouchon


def installer_bouchons_odoo():
    """Installe dans sys.modules les bouchons odoo nécessaires à l'assistant.

    Rôle : permettre d'importer l'assistant sans serveur Odoo.
    Paramètres : aucun.
    Retour : aucun (modifie sys.modules).
    Erreurs : aucune.
    Usages : charger_assistant_import().
    """
    module_odoo = creer_module_bouchon("odoo", [])
    module_odoo._ = str
    module_odoo.api = types.SimpleNamespace(model=lambda methode: methode)
    module_odoo.fields = types.SimpleNamespace(
        **{type_champ: champ_bouchon for type_champ in TYPES_CHAMPS_ODOO}
    )
    modeles_odoo = types.SimpleNamespace(TransientModel=object, Model=object)
    module_odoo.models = modeles_odoo
    module_exceptions = creer_module_bouchon("odoo.exceptions")
    module_exceptions.UserError = ErreurUtilisateurBouchon
    creer_module_bouchon("odoo.tools").html_escape = html.escape
    module_release = creer_module_bouchon("odoo.release")
    module_release.version_info = (17, 0, 0, "final", 0, "")
    module_release.version = "17.0"
    creer_module_bouchon("odoo.addons", [])
    creer_module_bouchon("odoo.addons.concorde", [DOSSIER_MODULE])
    creer_module_bouchon(
        "odoo.addons.concorde.engine", [os.path.join(RACINE_DEPOT, "core")]
    )


def charger_assistant_import():
    """Charge le fichier de l'assistant d'import et rend son module.

    Rôle : importer wizard/concorde_import_wizard.py hors d'Odoo.
    Paramètres : aucun.
    Retour : le module chargé.
    Erreurs : ImportError si une dépendance manque.
    Usages : TestLireBinaire.
    """
    installer_bouchons_odoo()
    chemin_assistant = os.path.join(
        DOSSIER_MODULE, "wizard", "concorde_import_wizard.py"
    )
    spec_assistant = importlib.util.spec_from_file_location(
        "concorde_import_wizard_test", chemin_assistant
    )
    module_assistant = importlib.util.module_from_spec(spec_assistant)
    spec_assistant.loader.exec_module(module_assistant)
    return module_assistant


class TestLireBinaire(unittest.TestCase):
    """_lire_binaire : contenu brut d'un champ Binary, toutes versions."""

    @classmethod
    def setUpClass(cls):
        cls.assistant = charger_assistant_import().ConcordeImportWizard()

    def test_valeur_inattendue_leve_erreur_utilisateur(self):
        """Un type inattendu doit donner le message prévu, pas un plantage."""
        with self.assertRaises(ErreurUtilisateurBouchon) as erreur_levee:
            self.assistant._lire_binaire(object())
        self.assertIn("Type de fichier inattendu", str(erreur_levee.exception))

    def test_base64_simple_decode(self):
        """Une chaîne base64 (Odoo <= 19) rend les octets du fichier."""
        contenu_lu = self.assistant._lire_binaire("UEsDBA==")
        self.assertEqual(contenu_lu, OCTETS_DEBUT_ZIP)

    def test_double_encodage_deballe(self):
        """Un contenu encodé deux fois en base64 rend les octets réels."""
        contenu_lu = self.assistant._lire_binaire("VUVzREJBPT0=")
        self.assertEqual(contenu_lu, OCTETS_DEBUT_ZIP)


if __name__ == "__main__":
    unittest.main()
