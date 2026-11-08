# ADR-0012 — Montée de version : pilotage de la machine de travail et écran

- **Statut** : Proposée
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
L'ADR-0010 fixe **ce que** fait une montée de version Odoo : OpenUpgrade non modifié,
toujours sur une copie, circuit en 7 étapes, zéro écart au centime, machine de travail
louée (jamais le serveur CONCORDE). L'ADR-0011 décide un **écran à part**, où le client
ne voit jamais le nom d'OpenUpgrade.

Fait et mesuré (1.7.0) : la photo comptable de Odoo 14 à 18 (`core/montee_version/photo.py`),
la commande `concorde_montee photo | comparer`, et la montée 14 → 15 → 16 → 17 dans la
CI avec zéro écart.

Reste à décider **comment** CONCORDE conduit une vraie montée :
- comment la copie de la base du client arrive sur la machine de travail ;
- comment le serveur CONCORDE donne les ordres à cette machine et en reçoit les résultats ;
- comment la base montée est rendue au client.

Mesures du 08/11/2026 :
- OpenUpgrade publie, pour chaque saut, la liste des modules et leur état
  (`docsource/modules160-170.rst` pour 16 → 17, etc.) : « Done », « Nothing to do », ou
  vide (= non traité). Pour 16 → 17 : 83 « Done », 163 « Nothing to do », 187 vides.
- OpenUpgrade ne couvre que **Odoo Community**. Les modules Enterprise (comptabilité
  complète `account_accountant`, etc.) n'y sont pas.
- Odoo Online (hébergé par Odoo SA) n'accepte pas d'Odoo modifié : la montée y est faite
  par Odoo SA, pas par nous.

## Décision
### 1. La machine de travail fait tout le travail lourd ; CONCORDE pilote
- La machine louée reçoit Docker et une copie de CONCORDE à une version publiée (tag
  `vX.Y.Z`). Elle lance elle-même `concorde_montee` : copie, conteneurs, sauts, photos.
- Le serveur CONCORDE s'y connecte **en SSH, avec une clé dédiée**. Côté machine, cette
  clé ne peut lancer **que** `concorde_montee` (commande forcée dans `authorized_keys`),
  sans shell, sans redirection de port.
- Ce qui revient sur le serveur CONCORDE : l'inventaire, les photos (des totaux, pas les
  écritures), les journaux des sauts et le rapport. **Jamais la base du client.**
- Aucun port ouvert sur la machine de travail en dehors de SSH. PostgreSQL et Odoo y
  tournent sur un réseau Docker sans port publié.

### 2. La copie du client arrive par une sauvegarde Odoo déposée
- Le client (ou nous, avec son accord) fait une **sauvegarde Odoo standard** : fichier
  `.zip` avec la base et les pièces jointes (filestore), depuis le gestionnaire de bases
  d'Odoo ou par `pg_dump`.
- Elle est déposée **directement sur la machine de travail** (lien d'envoi à usage unique,
  ou copie SSH), jamais sur le serveur CONCORDE.
- Elle est relue tout de suite : version d'Odoo, taille, empreinte SHA-256 gardée dans le
  rapport.

### 3. Les copies sont chiffrées, la machine est effacée
- Toutes les données du client sont sur un **volume chiffré** (LUKS) de la machine de
  travail. La clé est dans le fichier de secrets de CONCORDE et n'est jamais écrite sur la
  machine.
- 30 jours après la livraison : le volume est effacé, puis la machine est rendue au
  loueur (arbitrage 3 de l'ADR-0010).

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

L'écran **Montée de version** appelle ces étapes par SSH et affiche leur état, saut par
saut. Il ne fait rien que la commande ne fasse déjà.

### 6. Ce que voit le client
- Écran et rapport : « montée de version Odoo réalisée par CONCORDE ». Le nom de l'outil
  sous-jacent n'apparaît pas (ADR-0011, arbitrage 5).
- Le rapport donne : versions de départ et d'arrivée, modules, durée de chaque saut,
  photo avant, photo après, **zéro écart** (ou la liste des écarts), empreintes.

### 7. Tests
- Chaque étape est testée dans la CI sur de vraies bases Odoo (comme le job
  `montee-odoo`) : inventaire, sauvegarde zip déposée, montée, comparaison, livraison.
- Le pilotage SSH est testé dans la CI avec une machine de travail simulée par un
  conteneur (même commande forcée).
- Premier cas réel : une copie d'une base de test, sur une machine louée, avant tout client.

## Conséquences
- Il faut louer une machine pour chaque montée réelle. Taille à prévoir : environ trois
  fois la base plus les pièces jointes, et au moins 8 Go de mémoire.
- Les clients sur **Odoo Enterprise** ou **Odoo Online** ne sont pas couverts par cette
  offre.
- La clé SSH de pilotage et la clé du volume chiffré entrent dans le fichier de secrets
  (ADR-0011) et dans la surveillance de sécurité (ADR-0007).

## Options écartées
- **Faire passer la base du client par le serveur CONCORDE** : disque trop petit
  (9,4 Go libres) et données du client sur un serveur exposé sur Internet.
- **Ouvrir un service web sur la machine de travail** : un port de plus à protéger,
  alors que SSH avec une commande forcée suffit.
- **Lire la couverture d'OpenUpgrade sur sa branche du moment** : la liste doit être
  celle du commit qui fera la montée, sinon l'inventaire peut mentir.
