# Sommaire des variables — CONCORDE

Toute nouvelle variable est déclarée ici dans la même modification (protocole CONCORDE, § E).
Avant d'en créer une, vérifier (casse ignorée) qu'elle n'existe pas déjà.

> Sommaire commencé le 07/11/2026 (version 1.4.10) : il ne liste que les variables
> créées depuis. Les variables plus anciennes restent à y reporter.

| Variable | Fichier | Rôle |
|---|---|---|
| `_couche_superflue` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Compteur (non utilisé) des couches base64 en trop retirées par `_lire_binaire`, 3 au maximum |
| `RACINE_DEPOT` | `tests/test_assistant_import.py` | Dossier racine du dépôt |
| `DOSSIER_MODULE` | `tests/test_assistant_import.py` | Dossier du module Odoo `deploy/addons/concorde` |
| `TYPES_CHAMPS_ODOO` | `tests/test_assistant_import.py` | Types de champs Odoo simulés par `champ_bouchon` |
| `ErreurUtilisateurBouchon` | `tests/test_assistant_import.py` | Remplace `odoo.exceptions.UserError` |
| `champ_bouchon` | `tests/test_assistant_import.py` | Remplace un constructeur de champ Odoo |
| `creer_module_bouchon` | `tests/test_assistant_import.py` | Crée et enregistre un module odoo simulé |
| `installer_bouchons_odoo` | `tests/test_assistant_import.py` | Installe tous les modules odoo simulés |
| `charger_assistant_import` | `tests/test_assistant_import.py` | Charge l'assistant d'import hors d'Odoo |
| `_arguments`, `_options` | `tests/test_assistant_import.py` | Paramètres ignorés de `champ_bouchon` |
| `nom_module` | `tests/test_assistant_import.py` | Paramètre : nom pointé du module simulé |
| `chemins_paquet` | `tests/test_assistant_import.py` | Paramètre : dossiers d'un paquet simulé |
| `module_bouchon` | `tests/test_assistant_import.py` | Module simulé en cours de création |
| `module_odoo` | `tests/test_assistant_import.py` | Paquet `odoo` simulé |
| `module_release` | `tests/test_assistant_import.py` | Module `odoo.release` simulé |
| `type_champ` | `tests/test_assistant_import.py` | Élément de `TYPES_CHAMPS_ODOO` |
| `chemin_assistant` | `tests/test_assistant_import.py` | Chemin du fichier de l'assistant |
| `spec_assistant` | `tests/test_assistant_import.py` | Spécification d'import de l'assistant |
| `module_assistant` | `tests/test_assistant_import.py` | Module de l'assistant chargé |
| `erreur_levee` | `tests/test_assistant_import.py` | Erreur capturée par le test |
