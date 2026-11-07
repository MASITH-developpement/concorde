# ADR-0001 — Passerelle de données Odoo 17 : lire en SQL ou en XML-RPC, écrire par l'ORM

- **Statut** : Acceptée — arbitrages de Stéphane Moreau en séance du 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
CONCORDE doit pouvoir **uploader, analyser, modifier et télécharger** les données
comptables d'un Odoo 17 : écritures, plan comptable, journaux, tiers, factures.
Volume de référence : base `testalbhade`, 170 133 lignes d'écritures (153 765 hors
sections et notes), 45 673 écritures, 5 570 tiers. Le travail se fait **hors d'Odoo**,
en ligne de commande.

## Décision
1. **Lecture : deux sources interchangeables**, qui rendent les mêmes enregistrements
   (`core/odoo_source.py`) :
   - `sql` : PostgreSQL direct, transaction en lecture seule, curseur côté serveur.
     `psycopg2` est une dépendance **optionnelle**, chargée seulement pour cette source.
   - `xmlrpc` : API Odoo avec clé API ; seules `search_read`, `read`, `fields_get`
     et `search_count` sont autorisées.
2. **Écriture : uniquement par l'ORM d'Odoo** (XML-RPC), jamais en SQL. Odoo recalcule
   lui-même les soldes, restes dus, lignes de TVA, numérotations et lettrages, et
   applique les dates de verrouillage et l'inaltérabilité.
3. **Modification d'une écriture validée** : remise en brouillon, correction, puis
   revalidation. Refus si la période est verrouillée ou le journal sécurisé.
   **Factures validées** ou transmises en facture électronique : jamais modifiées,
   on passe par un avoir.
4. **Base d'écriture en développement : `concorde` uniquement.** `testalbhade` sert
   à tester la lecture du gros volume.
5. Formats de sortie : FEC DGFiP, xlsx (bibliothèque standard), CSV d'import Odoo.
6. Montants en centimes (int) de bout en bout ; un montant Odoo non exact au centime
   est refusé, jamais arrondi.
7. Identifiants : variables d'environnement (`PG*`, `ODOO_API_KEY`), jamais en argument.

## Conséquences
- Lecture de 150 000 lignes en environ 6 s en SQL. Écriture plus lente (par paquets,
  avec reprise) : à mesurer en phase 2.
- Les clients sur Odoo Online ou Odoo.sh restent servis par la source `xmlrpc`.
- Un rôle PostgreSQL dédié en lecture seule est recommandé pour la source `sql`
  (aujourd'hui, c'est l'utilisateur `odoo` du conteneur qui est utilisé).

## Options écartées
- **Tout en SQL, écriture comprise** : contourne l'ORM. On risque des soldes, des
  lignes de TVA ou des lettrages incohérents, et on passe outre les verrouillages.
  Inacceptable en comptabilité.
- **Tout en XML-RPC** : lecture trop lente sur gros volume.
- **Contre-passation pour les écritures validées** : écartée par Stéphane au profit
  de la remise en brouillon.
