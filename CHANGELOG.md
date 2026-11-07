# Journal des versions — CONCORDE

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions sémantiques.
Le module Odoo porte la même version au format `17.0.X.Y.Z` (`deploy/addons/concorde/__manifest__.py`).

## [1.4.10] — 2026-11-07
### Corrigé
- Assistant d'import : un fichier de type inattendu affichait une erreur Python
  (`UnboundLocalError`) au lieu du message « Type de fichier inattendu ».
  Cause : la boucle anti-double-encodage utilisait `_` comme variable et masquait
  la fonction de traduction dans toute la méthode `_lire_binaire`.
### Sécurité
- Ajout d'un `.gitignore` : les fichiers `.env` (mots de passe) ne peuvent plus être commités.

## [1.4.9] et antérieures
Voir l'historique git (`git log`).
