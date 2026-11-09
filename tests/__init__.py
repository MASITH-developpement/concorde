# CONCORDE v1.0 — package (c) MASITH / Stéphane Moreau
"""Tests de CONCORDE.

Avant tout import des modules testés, les chemins de travail du serveur
(secrets, connexions, transferts, montées, volume chiffré) sont tournés
vers un dossier temporaire : un test ne doit jamais lire ni écrire les
fichiers réels du serveur, même lancé sur le serveur lui-même.
"""

import os
import tempfile

DOSSIER_TESTS_TEMPORAIRE = tempfile.mkdtemp(prefix="concorde-tests-")
for variable_chemin, chemin_relatif in (
    ("CONCORDE_SECRETS", "secrets/connecteurs.env"),
    ("CONCORDE_CONNEXIONS", "connexions.json"),
    ("CONCORDE_TRANSFERTS", "transferts"),
    ("CONCORDE_MONTEES", "montees"),
    ("CONCORDE_OPENUPGRADE", "openupgrade"),
    ("CONCORDE_MONTEE_DONNEES", "montee/donnees"),
    ("CONCORDE_MONTEE_ETATS", "montee/etats"),
    ("CONCORDE_MONTEE_IMAGE", "montee/volume.luks"),
    ("CONCORDE_MONTEE_CLE", "montee/cle"),
):
    os.environ[variable_chemin] = os.path.join(
        DOSSIER_TESTS_TEMPORAIRE, chemin_relatif
    )
