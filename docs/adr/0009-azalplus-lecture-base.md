# ADR-0009 — AzalPlus : lire la base en lecture seule maintenant, écrire par l'API v2 une fois terminée

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 08/11/2026
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
L'ADR-0008 prévoyait un connecteur AzalPlus par l'API REST v2 (`/api/v2/comptabilite`,
jeton Bearer). Mesure du 08/11/2026 sur le code `/opt/azalplus-v2` : cette API n'est pas
utilisable.
- Le jeton n'est jamais vérifié ; l'entreprise et la société viennent de paramètres
  d'adresse ou de valeurs écrites en dur.
- Aucune base derrière : les listes rendent des données de démonstration, une écriture
  envoyée n'est pas enregistrée, et sa création échoue (erreur 500).
- Le module comptable n'est pas lancé (le serveur fait tourner une version minimale), et
  la passerelle ne transmet pas les envois POST.
- Une écriture n'a qu'un compte (pas de lignes) et aucun champ ne garantit l'idempotence.

La vraie base AzalPlus (`azals`, PostgreSQL 15, schéma `azalplus`) existe, sur un autre
serveur. Mesures du 08/11/2026 (lecture seule) : 1 869 lignes d'écritures, 913 écritures,
toutes équilibrées, aucune à plus de 2 décimales ; une ligne par ligne d'écriture
(`comptabilite_ecritures` : compte, débit, crédit, journal, pièce, lettrage, tiers,
analytique, devise) ; statuts « VALIDEE » (1 867 lignes) et « VALIDE » (2 lignes) ;
3 sociétés dont 680 lignes **sans société** ; le tiers est porté par son **nom** (82
noms : 41 désignent un seul client ou fournisseur actif avec code, 28 un client sans
code, 13 sont introuvables).

## Décision
1. **A — maintenant** : AzalPlus est branché comme **source**, par lecture directe de sa
   base PostgreSQL, en **lecture seule** (`core/connecteurs/azalplus.py`).
   - Rôle PostgreSQL **dédié à CONCORDE**, en lecture seule, sur les seules tables lues
     (`comptabilite_ecritures`, `comptabilite_journaux`, `clients`, `fournisseurs`).
   - Session ouverte en lecture seule ; TLS demandé (`sslmode=require` par défaut).
   - Base joignable par un **réseau privé entre serveurs**, jamais par Internet (incident
     du 01/11/2026 : PostgreSQL ouvert sur Internet, vidé puis détourné).
   - Chaque requête filtre l'entreprise (`tenant_id`, en UUID) et la société ; lignes
     supprimées (`deleted_at`) et archivées exclues.
   - Statuts « VALIDEE » et « VALIDE » lus comme validés ; tout autre statut est exclu et
     compté.
   - Lignes **sans société** : jamais lues ; comptées et signalées au test de connexion et
     à chaque lecture, à rattacher dans AzalPlus.
   - **Tiers** : un nom qui désigne un seul client ou fournisseur actif ayant un code
     donne ce code, et chaque tiers trouvé ainsi est **signalé** (alerte
     `MIG_SIGNALEMENT_SOURCE`) ; introuvable, sans code ou porté par plusieurs : ligne
     illisible, **bloquante**, motif nommé.
   - **Aucune écriture dans AzalPlus par la base** (ADR-0008, options écartées).
2. **B — ensuite** : terminer l'API v2 dans le projet AzalPlus (vraie vérification du
   jeton, entreprise tirée du jeton, persistance, écritures à plusieurs lignes,
   équilibre contrôlé, référence externe unique pour l'idempotence). Le connecteur
   AzalPlus saura alors écrire par cette API. Chantier mené dans le dépôt AzalPlus,
   avec ses propres règles (skill `dev-azal-odoo`, section AzalPlus).
3. **C — après** : connecteur Pennylane.

## Conséquences
- AzalPlus peut alimenter Odoo, un FEC ou tout autre destination dès que la base est
  joignable ; aucun transfert ne peut aller **vers** AzalPlus avant B.
- Il faut, côté serveur AzalPlus : le réseau privé, le rôle en lecture seule et son mot de
  passe (saisi par Stéphane dans le fichier de secrets, ADR-0008).
- Les 680 lignes sans société, les 2 lignes « VALIDE » et les tiers sans code sont à
  corriger dans AzalPlus ; tant qu'ils restent, ils sont signalés à chaque lecture.
- La lecture dépend du schéma de la base AzalPlus : un changement de colonne y fait
  échouer la lecture (erreur nommée), jamais une lecture partielle silencieuse.

## Options écartées
- **Coder contre l'API v2 actuelle** : rien ne serait réellement lu ni écrit.
- **Écrire dans AzalPlus par la base** : contourne les contrôles d'AzalPlus et sa
  numérotation ; écarté par l'ADR-0008.
- **Ouvrir le port PostgreSQL d'AzalPlus sur Internet** : cause de l'incident du
  01/11/2026.
- **Rattacher les lignes sans société à la société principale** : supposition, refusée.
- **Prendre le nom du tiers comme référence** : deux tiers au même nom seraient confondus.
