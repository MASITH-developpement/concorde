# CONCORDE — Module Odoo 17

Application CONCORDE pour Odoo 17 Community. (c) MASITH / Stéphane Moreau. Tous droits réservés.

## Contenu

- **Menu CONCORDE** : > Importer un FEC (assistant), > Historique des imports.
- **Assistant** : dépôt du fichier FEC Quadra, journal par défaut, dry-run activé
  par défaut. Le pipeline embarqué tourne entièrement dans Odoo :
  import FEC -> équilibre (tolérance 0,00 EUR) -> mapping 362 comptes ->
  lettrage -> rapport, sous Guardian (audit chaîné SHA-256) et Marceau
  (explication, jamais muet).
- **Import Odoo** : hors dry-run, création des account.move idempotents
  (réf. « FEC <journal>-<écriture> » ; déjà importée = ignorée). Compte Odoo
  absent = blocage avec la liste exacte (aucun compte deviné).
- **Sécurité** : accès réservé au groupe Comptabilité/Administrateur.

## Moteur embarqué

Le dossier engine/ est une copie fidèle de /opt/concorde/core, réalisée par
scripts/install_module.sh. Ne pas éditer dans le module : corriger dans core/.

## Marceau / Mistral

Exporter MISTRAL_API_KEY dans l'environnement du conteneur odoo active le mode
Mistral ; sinon repli automatique sur le moteur de règles (jamais muet).
