# Décisions d'architecture (ADR) — CONCORDE

Modèle : `0000-modele.md`. Une ADR acceptée ne se modifie pas : on en écrit une nouvelle qui la remplace.

| N° | Titre | Statut |
|---|---|---|
| [0001](0001-passerelle-donnees-odoo17.md) | Passerelle de données Odoo 17 : lire en SQL ou en XML-RPC, écrire par l'ORM | Acceptée (06/11/2026) |
| [0002](0002-interface-web.md) | Interface web : Python standard, un utilisateur, derrière Caddy | Acceptée (06/11/2026) |
| [0003](0003-surveillance-alertes-journal.md) | Comptes, alertes et journal : CONCORDE surveille et raconte | Acceptée (06/11/2026) |
| [0004](0004-migration-erp-vers-odoo.md) | Migration d'un ERP vers Odoo 17 : convertir, contrôler, tester, puis envoyer | Acceptée (06/11/2026) |
| [0005](0005-suppression-bases.md) | Suppression de bases et de clés API : seulement en local, jamais chez un client | Acceptée (06/11/2026) |
| [0006](0006-alignement-prod-sur-test.md) | Aligner la production sur la base de test, sur une période (comparer, puis appliquer) | Acceptée (06/11/2026) |
| [0007](0007-securite-antivirus-mineur-rancongiciel.md) | Surveillance de sécurité : ClamAV de nuit, contrôle mineur / rançongiciel toutes les 15 min | Acceptée (07/11/2026) |
| [0008](0008-transferts-entre-logiciels.md) | Transferts entre logiciels comptables : un pivot, un connecteur par logiciel, plusieurs connexions à la fois | Acceptée (08/11/2026) |
| [0009](0009-azalplus-lecture-base.md) | AzalPlus : lire la base en lecture seule maintenant, écrire par l'API v2 une fois terminée | Acceptée (08/11/2026) |
| [0010](0010-montee-version-odoo.md) | Montée de version Odoo : OpenUpgrade fait la migration, CONCORDE certifie la comptabilité | Acceptée (08/11/2026) |
| [0011](0011-ecran-connexions-transferts.md) | Écrans Connexions, Transferts et Montée de version dans l'interface web | Acceptée (08/11/2026) |
| [0012](0012-pilotage-montee-version.md) | Montée de version : pilotage sur le serveur CONCORDE et écran | Acceptée (08/11/2026) |
| [0013](0013-completer-siren-tva.md) | Compléter le SIRET et la TVA des tiers depuis CONCORDE | Acceptée (09/11/2026) |
| [0014](0014-facture-electronique-tiers.md) | Facture électronique : vérifier l'inscription des tiers et reprendre leur adresse | Acceptée (09/11/2026) |
| [0015](0015-bouton-arreter.md) | Bouton « Arrêter » sur une tâche en cours | Proposée (09/11/2026) |
