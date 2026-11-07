# ADR-0004 — Migration d'un ERP vers Odoo 17 : convertir, contrôler, tester, puis envoyer

- **Statut** : Acceptée — validée par Stéphane Moreau le 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Stéphane veut reprendre les données d'un autre ERP, depuis **un fichier** (Excel, CSV,
FEC…) ou **directement par l'API de l'ERP** (AzalPlus, Sage, Quadra…). CONCORDE les convertit, sort les
problèmes, crée l'export, le contrôle et teste sa conformité. Il l'importe ensuite dans
une base Odoo 17 vierge du serveur (0 erreur exigée), puis envoie **une** ligne dans la
base du client, et enfin **tout**, si tout est bon.

Arbitrages du 06/11/2026 :
- entrées : fichiers (FEC, Excel/CSV d'ERP, balance + tiers + plan pour une reprise
  d'ouverture) **et API d'ERP** (précision du 06/11/2026 : la source n'est pas forcément
  Odoo, ni forcément un fichier) ;
- données : écritures, plan comptable et journaux, tiers, lettrage ;
- test complet sur une base Odoo 17 **vierge** du serveur ;
- base client : Odoo Online, Odoo.sh ou sur site, selon le client (envoi toujours par l'API).

## Décision
### Connecteurs source : une prise par origine, un seul circuit ensuite
Chaque origine a son **connecteur** (`connecteurs/`). Tous rendent le même lot dans le
format commun de CONCORDE, en centimes : écritures, comptes, journaux, tiers, lettrage.
Le reste du circuit ne sait pas d'où viennent les données.

| Connecteur | Mode | Ce qu'il lit |
|---|---|---|
| FEC | fichier | tout ERP français (format légal, déjà lu par CONCORDE) |
| Excel / CSV | fichier | exports d'ERP ; **profil de colonnes en YAML par ERP** (no-code, comme `concorde.yaml`) : une nouvelle source = un nouveau profil, sans code |
| Balance + tiers + plan | fichier | reprise d'ouverture : soldes de début d'exercice, fichiers clients et fournisseurs, plan comptable |
| **AzalPlus** | **API** REST v2, jeton Bearer | `/api/v2/comptabilite` : comptes, écritures, FEC, balance ; tiers par le module clients |
| Odoo (toutes versions) | API XML-RPC | source déjà écrite (ADR-0001) : migration Odoo → Odoo |
| Sage | API **selon le produit** | Sage Business Cloud Comptabilité : API REST (OAuth2). Sage 50 / Sage 100 : pas d'API web standard, donc export fichier, ou connecteur sur le poste du client (à étudier) |
| Quadra (Cegid) | API **selon l'offre** | Quadra installé : pas d'API publique, donc export FEC ou ASCII. Offres Cegid en ligne : API à étudier, client par client |
| Autres (Pennylane, EBP…) | API ou fichier | un connecteur de plus, au besoin |

Règles communes à tous les connecteurs :
- **lecture seule sur la source** : CONCORDE n'écrit jamais dans l'ERP d'origine ;
- identifiants (jetons, clés, OAuth) en variables d'environnement ou en mémoire, jamais
  dans un fichier ni dans un journal ;
- chaque connecteur raconte ce qu'il lit (journal) et signale ce qu'il ne sait pas lire,
  au lieu de l'ignorer ;
- un connecteur par API produit aussi une **photo fichier** de ce qu'il a lu (FEC et
  xlsx), gardée dans le dossier du lot : on sait toujours d'où partait la migration.

### Le circuit : huit portes, chacune bloquante
| # | Porte | Ce qui bloque |
|---|---|---|
| 1 | **Lecture** par le connecteur source (fichier ou API) | fichier ou API illisible, authentification refusée, colonne ou champ obligatoire absent, montant à plus de 2 décimales |
| 2 | **Conversion** vers le format commun en centimes, tiers et lettrage compris | — |
| 3 | **Problèmes** : la batterie de contrôles de migration | écriture déséquilibrée, montant nul, écriture d'une seule ligne, compte « 0 », écriture à cheval sur deux journaux ou deux mois, doublon entre fichiers, date future non tranchée |
| 4 | **Correspondance** des comptes (table arbitrée par le comptable) et des tiers | compte absent de la table → fichier « à arbitrer », jamais deviné ; tiers retrouvé par son seul nom → signalé |
| 5 | **Export et conformité** : CSV Odoo, FEC de contrôle, mêmes totaux au centime que l'entrée | un centime d'écart entre l'entrée et la sortie |
| 6 | **Test complet sur la base vierge** du serveur, en commençant par le plus petit fichier, puis relecture et comparaison | toute erreur d'import, tout écart de balance |
| 7 | **Test d'une écriture** sur la base client, relecture, comparaison, puis **suppression** de cette écriture de test | écart, refus d'Odoo, droits insuffisants |
| 8 | **Envoi complet** sur la base client, sur **confirmation explicite** de Stéphane, après sauvegarde du client | sans confirmation ou sans sauvegarde déclarée, rien ne part |

### Règles d'envoi
- Toujours par l'API (ORM), jamais en SQL (ADR-0001). L'injecteur `injectors/odoo17.py`
  est d'abord **corrigé** : montants convertis des centimes en euros, et identifiants
  Odoo (compte, journal, tiers) résolus au lieu des codes.
- **Idempotence** : chaque écriture porte `ref = CONCORDE/<lot>/<journal>/<n°>` ; une
  écriture déjà présente n'est jamais renvoyée. Si l'envoi est coupé, la reprise
  repart là où il s'était arrêté.
- Envoi par **paquets**, chaque paquet journalisé. À la fin, la balance est relue et
  comparée à l'entrée, au centime.
- Le **lettrage** est refait par l'API après l'envoi des écritures (l'import natif
  d'Odoo ne le reprend pas).
- Écritures envoyées **en brouillon** puis validées en fin de lot, une fois la relecture
  conforme. Un lot raté reste en brouillon et peut être supprimé proprement.
- Chaque lot a un **dossier de lot** : fichier d'entrée, problèmes, table appliquée,
  exports, rapports de chaque porte, journal complet et empreinte Guardian.

### Interface
Un nouvel écran **Migrer** : un assistant en 8 étapes, une par porte, qui montre le journal
en direct et les problèmes (expliqués par Marceau). Chaque étape ne s'ouvre que si la
précédente est verte. Pour l'envoi final, il faut retaper le nom de la base client.

## Conséquences
- Il faut une base Odoo 17 vierge sur le serveur (`concorde_test`, plan comptable
  français), recréée avant chaque test complet.
- Il faut un login et une clé API par base client, saisis dans l'écran Bases (gardés
  en mémoire seulement).
- La sauvegarde du client est déclarée (case à cocher avec la date). Concorde ne peut pas
  la faire lui-même sur Odoo Online.

## Ordre de construction proposé
1. Le cœur du circuit (portes 2 à 8) avec le connecteur **FEC**, qui existe déjà.
2. Connecteur **Excel / CSV à profils** YAML.
3. Connecteur **AzalPlus** par API (MASITH maîtrise l'API).
4. Connecteur **balance + tiers + plan**.
5. Connecteurs **Sage** et **Quadra** selon les produits réels des clients.

## Options écartées
- **Import natif d'Odoo** (CSV dans l'interface d'Odoo) : pas de reprise, pas de lettrage,
  et des erreurs ligne par ligne difficiles à suivre. Le CSV reste produit comme export
  de contrôle.
- **Envoi direct sans base de test** : contraire à la règle « test avant production ».
