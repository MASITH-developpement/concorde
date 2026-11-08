# ADR-0012 — Montée de version : pilotage sur le serveur CONCORDE et écran

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 08/11/2026
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
L'ADR-0010 fixe **ce que** fait une montée de version Odoo : OpenUpgrade non modifié,
toujours sur une copie, circuit en 7 étapes, zéro écart au centime, machine de travail
louée (jamais le serveur CONCORDE). L'ADR-0011 décide un **écran à part**, où le client
ne voit jamais le nom d'OpenUpgrade.

**Changement d'arbitrage (08/11/2026)** : Stéphane choisit de faire tourner les montées
**sur le serveur CONCORDE**, sans machine louée. Cela remplace l'arbitrage 2 de
l'ADR-0010. Le risque nommé par l'ADR-0010 (disque et mémoire trop justes, site arrêté si
le disque se remplit) est traité par les garde-fous du point 1.

Fait et mesuré (1.7.0) : la photo comptable de Odoo 14 à 18 (`core/montee_version/photo.py`),
la commande `concorde_montee photo | comparer`, et la montée 14 → 15 → 16 → 17 dans la
CI avec zéro écart.

Reste à décider **comment** CONCORDE conduit une vraie montée :
- comment la copie de la base du client arrive ;
- qui lance les conteneurs, alors que l'interface web n'a pas accès à Docker ;
- comment la base montée est rendue au client.

Mesures du serveur CONCORDE (08/11/2026) : 38 Go de disque dont **9,4 Go libres**,
**3,7 Go de mémoire** (2,4 Go disponibles), 2 processeurs. Le compte de l'interface
(`ubuntu`) n'a pas accès à Docker, et ne doit pas l'avoir : l'accès à Docker vaut un
accès root, et l'interface est ouverte sur Internet.

Mesures du 08/11/2026 :
- OpenUpgrade publie, pour chaque saut, la liste des modules et leur état
  (`docsource/modules160-170.rst` pour 16 → 17, etc.) : « Done », « Nothing to do », ou
  vide (= non traité). Pour 16 → 17 : 83 « Done », 163 « Nothing to do », 187 vides.
- OpenUpgrade ne couvre que **Odoo Community**. Les modules Enterprise (comptabilité
  complète `account_accountant`, etc.) n'y sont pas.
- Odoo Online (hébergé par Odoo SA) n'accepte pas d'Odoo modifié : la montée y est faite
  par Odoo SA, pas par nous.

## Décision
### 1. Un service à part lance les montées, avec des garde-fous
- Nouveau service `concorde-montee`, sous un compte système dédié `concorde-montee`,
  seul compte (avec root) à avoir accès à Docker pour les montées. **L'interface n'a
  jamais accès à Docker.**
- L'interface dépose une **demande** (fichier JSON) dans une file
  (`/var/lib/concorde-montee/demandes/`). Le service la relit, la vérifie (étape connue,
  montée connue, valeurs attendues) et lance `concorde_montee`. C'est l'équivalent local
  d'une « commande forcée » : rien d'autre ne peut être demandé.
- Le service écrit l'état de chaque montée (`montee.json`, journaux, rapport) là où
  l'interface peut le lire. **La base du client n'est jamais lisible par l'interface.**
- Conteneurs PostgreSQL et Odoo sur un réseau Docker **interne**, sans aucun port publié
  (incident du 01/11/2026).
- **Garde-fous, pour que le site ne tombe pas :**
  - avant de commencer : refus si l'espace libre est inférieur à **3 fois la taille de la
    base décompressée, plus 3 Go** (images Odoo comprises) ; la cause et les chiffres
    sont affichés ;
  - pendant la montée : arrêt propre si l'espace libre passe sous **2 Go** ;
  - conteneurs bridés : **1,5 Go de mémoire et 1 processeur** au plus, priorité basse
    (`nice`, `ionice`) ;
  - **une seule montée à la fois** ;
  - les images Odoo d'une version sont effacées après leur saut ; elles sont
    retéléchargées à la montée suivante.
- Conséquence : une base trop grosse pour le serveur est **refusée avant de commencer**,
  jamais coupée en route. Pour l'accepter, il faut agrandir le disque du serveur.

### 2. La copie du client arrive par une sauvegarde Odoo (.zip) déposée
- Sauvegarde Odoo standard : `.zip` avec `dump.sql` et les pièces jointes (filestore),
  faite depuis le gestionnaire de bases d'Odoo par le client, ou par nous avec son accord.
- Elle est déposée dans l'écran Montée de version et écrite **directement** dans le
  volume chiffré (point 3), sans copie en clair. Le plafond de taille est réglable, comme
  pour le dépôt de FEC (ADR-0011).
- Elle est relue tout de suite : présence de `dump.sql`, version d'Odoo, taille,
  empreinte SHA-256 gardée dans le rapport.

### 3. Les copies sont chiffrées et effacées à 30 jours
- Toutes les données du client (sauvegarde déposée, bases PostgreSQL des conteneurs,
  base montée) sont dans un **volume chiffré** (LUKS, conteneur fichier) monté pour la
  durée d'une montée.
- La clé est dans un fichier lisible **par le seul service de montée**
  (`/etc/concorde/montee/cle`, 600), pas dans le fichier de secrets de l'interface.
- 30 jours après la livraison, le volume de la montée est effacé (arbitrage 3 de
  l'ADR-0010).

### 4. Inventaire avant toute montée
- Lecture de la version et des modules installés de la copie.
- Pour chaque saut, l'état de chaque module est lu dans la table d'OpenUpgrade **du même
  commit figé** que celui qui fera la montée.
- Couvert = « Done » ou « Nothing to do ». Vide, inconnu ou module Enterprise = **non
  couvert : bloque**, avec la liste nommée par saut. Le client choisit : migrer par son
  développeur, ou désinstaller avant (arbitrage 5 de l'ADR-0010).

### 5. Le circuit de l'ADR-0010, piloté par la commande puis par l'écran
`concorde_montee` gagne les étapes manquantes, chacune refaisable et enregistrée dans
un dossier de montée (`montee.json`, comme `transfert.json`) :
- `inventaire` → `photo-avant` → `monter` (saut par saut) → `photo-apres` + `comparer`
  → `rapport` ;
- `feu-vert` (nom de la base retapé), puis `nouvel-essai` sur une copie fraîche, et
  `livrer` (sauvegarde Odoo de la base montée, avec son empreinte).

L'écran **Montée de version** dépose les demandes de ces étapes (point 1) et affiche leur
état, saut par saut. Il ne fait rien que la commande ne fasse déjà.

### 6. Ce que voit le client
- Écran et rapport : « montée de version Odoo réalisée par CONCORDE ». Le nom de l'outil
  sous-jacent n'apparaît pas (ADR-0011, arbitrage 5).
- Le rapport donne : versions de départ et d'arrivée, modules, durée de chaque saut,
  photo avant, photo après, **zéro écart** (ou la liste des écarts), empreintes.

### 7. Tests
- Chaque étape est testée dans la CI sur de vraies bases Odoo (comme le job
  `montee-odoo`) : inventaire, sauvegarde zip déposée, montée, comparaison, livraison.
- La file de demandes est testée : une demande inconnue ou mal formée est refusée.
- Les garde-fous sont testés : disque insuffisant, disque qui se remplit en route.
- Premier cas réel : une copie d'une base de test, sur le serveur CONCORDE, avant tout
  client (arbitrage 5).

## Conséquences
- **Taille des bases acceptées** : avec 9,4 Go libres, une base d'environ 2 Go
  décompressés au plus. Une base comme celle d'Albhades (170 133 lignes d'écritures,
  pièces jointes comprises) risque d'être refusée par le garde-fou : à mesurer sur sa
  sauvegarde. Si elle l'est, il faut agrandir le disque du serveur avant la montée.
- **Mémoire** : un saut bridé à 1,5 Go peut échouer sur une grosse base. Il s'arrête
  alors avec la cause nommée ; la production du client n'est jamais touchée.
- **Mise en place par root** (Stéphane) : compte `concorde-montee`, accès à Docker,
  service systemd, fichier de clé du volume chiffré. Commandes fournies avec le code.
- Les clients sur **Odoo Enterprise** ou **Odoo Online** ne sont pas couverts.
- Le service de montée et sa clé entrent dans la surveillance de sécurité (ADR-0007).

## Arbitrages (Stéphane Moreau, 08/11/2026)
1. La copie du client arrive par une **sauvegarde Odoo (.zip)**.
2. Pilotage **en local, sur le serveur CONCORDE** (remplace l'arbitrage 2 de
   l'ADR-0010), avec les garde-fous du point 1.
3. Données du client sur un **volume chiffré**, effacé à 30 jours.
4. **Pas de machine louée.**
5. **Premier essai réel** sur une base de test, avant tout client.

## Options écartées
- **Machine de travail louée** : proposée, écartée par Stéphane (arbitrages 2 et 4).
- **Donner l'accès à Docker au compte de l'interface** : l'interface, ouverte sur
  Internet, aurait alors l'équivalent d'un accès root.
- **Lire la couverture d'OpenUpgrade sur sa branche du moment** : la liste doit être
  celle du commit qui fera la montée, sinon l'inventaire peut mentir.
