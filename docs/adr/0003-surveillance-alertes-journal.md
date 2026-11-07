# ADR-0003 — Comptes, alertes et journal : CONCORDE surveille et raconte

- **Statut** : Acceptée — arbitrages de Stéphane Moreau en séance du 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Stéphane veut travailler par compte comptable, être alerté de lui-même quand un
problème se présente, et que CONCORDE dise ce qu'il fait (« bavard »).

## Décision
1. **Comptes** : la balance (tous les comptes du plan), le grand livre d'un compte (solde
   cumulé, 500 lignes par page) et le détail d'une écriture, en lecture seule.
   Les corrections viendront en phase 3, quand on aura l'accès en écriture (ADR-0001).
2. **Alertes, trois familles**, rassemblées dans un centre d'alertes (`core/surveillance.py`,
   fichier `alertes.json`) :
   - *comptables* : les règles du plan comptable sur la balance (`core/comptes.py`) et les
     constats de l'analyse ;
   - *techniques* : PostgreSQL, Odoo, disque, tâches en échec, mots de passe refusés ;
   - *changements dans Odoo* : une photo de la base à chaque passage, comparée à la
     précédente (écritures créées, supprimées, remises en brouillon, comptes, verrous).
   Une alerte d'état qui ne se reproduit plus passe « résolue » toute seule ; une alerte
   qui s'aggrave est remontrée. Les changements sont des événements (vus, jamais résolus).
3. **Surveillance automatique** toutes les 15 minutes (`CONCORDE_UI_SURVEILLANCE`), sur
   les bases du serveur (SQL), et à la demande depuis l'écran Alertes.
4. **Journal** (`core/journal.py`) : chaque tâche raconte ses étapes en direct (durées,
   volumes, contrôles, alertes) ; un journal système raconte la surveillance et les
   connexions.
5. **Explications** : chaque alerte porte un « pourquoi » et un « que faire » rédigés par
   Marceau à partir d'un **catalogue local** (`core/explications.py`). Aucune donnée
   comptable n'est envoyée à Mistral, même si la clé est configurée.

## Conséquences
- La surveillance lit chaque base toutes les 15 minutes (≈ 1,5 s pour 154 000 lignes).
- La photo d'une base (≈ 46 000 écritures) pèse quelques Mo dans `/var/lib/concorde-interface`.
- Les Odoo distants (API) ne sont pas surveillés automatiquement, pour ne pas solliciter
  leur API ; on les analyse à la demande.

## Options écartées
- **Explications par Mistral** : écarté, car des données comptables sortiraient du serveur.
- **Notifications par e-mail** : pas demandé pour l'instant, mais facile à ajouter sur
  le centre d'alertes.
