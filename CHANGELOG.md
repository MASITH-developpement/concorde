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
### Sécurité
- Ajout d'un `.gitignore` : les fichiers `.env` (mots de passe) ne peuvent plus être commités.

## [1.4.9] et antérieures
Voir l'historique git (`git log`).
