# Journal des versions — CONCORDE

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions sémantiques.
Le module Odoo porte la même version au format `17.0.X.Y.Z` (`deploy/addons/concorde/__manifest__.py`).

## [1.5.0] — 2026-11-07
### Ajouté
- Contrôle de la dématérialisation des factures (menu CONCORDE > Contrôle
  dématérialisation) : Factur-X / UBL / CII, erreurs EDI et Peppol, SIREN / TVA,
  doublons — lecture seule.
### Corrigé
- Assistant d'import : un fichier de type inattendu affichait une erreur Python
  (`UnboundLocalError`) au lieu du message « Type de fichier inattendu ».
  Cause : la boucle anti-double-encodage utilisait `_` comme variable et masquait
  la fonction de traduction dans toute la méthode `_lire_binaire`.
- Bases locales : le nom du modèle vierge n'était pas vérifié avant d'être inséré
  dans `CREATE DATABASE … TEMPLATE` ; il l'est désormais AVANT la suppression
  (routine `_identifiant_sql`).
- Odoo : une traduction vide (jsonb) donne un texte vide, jamais « None ».
- `core/migration` : `NotRequired` / `Required` (Python 3.11+) remplacés par des
  TypedDict compatibles Python 3.10 (Python d'Odoo 17) — l'import plantait en 3.10.
- Un test était sauté faute de fichier client : il tourne avec un mapping synthétique.
### Modifié
- Lancement en modules depuis la racine : `python3 -m interface.serveur`,
  `python3 -m securite.concorde_securite`, `python3 -m scripts.<nom>`
  (services systemd mis à jour : WorkingDirectory + ExecStart).
- Qualité mesurée : flake8 (règles par défaut), black (79), mypy --strict
  (Python 3.10 et 3.14), docstrings complètes, aucun `noqa` / `type: ignore`.
- Code dupliqué factorisé (injecteurs Odoo 17/18, transports XML-RPC, lecture
  xlsx, curseurs, tests…).
- Nouvelle CI bloquante `.github/workflows/qualite.yml`.
- `scripts/install_module.sh` : plus de `|| true` (erreur SQL explicite).
### Sécurité
- Ajout d'un `.gitignore` : les fichiers `.env` (mots de passe) ne peuvent plus être commités.
- Lecture XML (.xlsx clients) et XML-RPC protégées par **defusedxml** (`core/xml_sur.py`) :
  bombe d'entités, entités externes et DTD refusées. Nouvelle dépendance :
  `defusedxml` (paquet Ubuntu `python3-defusedxml`), à installer aussi dans le
  conteneur Odoo (moteur embarqué).

## [1.4.9] et antérieures
Voir l'historique git (`git log`).
