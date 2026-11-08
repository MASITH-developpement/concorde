# ADR-0011 — Écrans Connexions, Transferts et Montée de version dans l'interface web

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 08/11/2026
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Les transferts entre logiciels (ADR-0008, ADR-0009, version 1.6.0) et la montée de
version Odoo (ADR-0010, version 1.7.0) existent, mais ne s'utilisent qu'en ligne de
commande sur le serveur. Stéphane veut s'en servir depuis l'interface web (demande du
08/11/2026). Le point 8 de l'ADR-0008 prévoyait déjà un écran « Transferts ».

Ce qui existe déjà et ne change pas :
- `core/connecteurs/connexions.py` : l'annuaire des connexions (ajouter, tester,
  retirer), sans aucun secret ;
- `core/connecteurs/secrets.py` : le fichier de secrets, lu seulement s'il est en 600 ;
- `core/connecteurs/transfert.py` : le moteur des 7 étapes (`creer` joue les étapes 1
  à 4, `donner_feu_vert` les étapes 5 à 7, avec le nom de la destination retapé et la
  date de sauvegarde) ;
- l'interface (ADR-0002) : un seul utilisateur, tâches en arrière-plan (2 à la fois),
  suivi en direct, service systemd en système de fichiers **en lecture seule** sauf
  `/var/lib/concorde-interface`.

Le blocage : le service ne peut pas écrire dans `/etc/concorde`. Les secrets ne peuvent
donc pas être saisis depuis l'écran tant que rien ne change.

## Décision
### 1. Un nouvel écran « Transferts », avec deux parties
Une seule entrée dans le menu, **Transferts**, avec deux parties :
- **Connexions** : la liste (logiciel, libellé, environnement de test, dernier essai,
  et pour chaque secret « renseigné » ou « manquant »), et les boutons **Ajouter**,
  **Tester**, **Saisir un secret**, **Retirer** ;
- **Transferts** : **Nouveau transfert**, puis la liste des transferts avec, pour chaque
  destination, ses 7 étapes en couleur (verte, bloquée, en attente) et la cause de
  chaque blocage.

Le formulaire **Ajouter** est construit à partir de ce que chaque connecteur déclare
(paramètres requis, secrets requis, lecture et écriture). Aucun logiciel n'est écrit en
dur dans la page. Un logiciel ajouté plus tard (Sage, Cegid) apparaît donc tout seul.

### 2. Les secrets se saisissent dans l'écran, sans jamais revenir
- Champ masqué (`type=password`), envoyé une seule fois en HTTPS, écrit aussitôt dans
  le fichier de secrets et jamais conservé ailleurs.
- **Aucune** réponse de l'API ne contient de secret : l'écran ne reçoit que « renseigné »
  ou « manquant ». Changer un secret, c'est le retaper en entier.
- Jamais dans un journal, un rapport, un message d'erreur, l'historique ou l'audit.
- **Retirer** une connexion efface aussi ses secrets du fichier.

### 3. Le fichier de secrets change de place, pour que l'écran puisse l'écrire
- Nouveau chemin : `/etc/concorde/connecteurs/connecteurs.env`, dans un dossier
  `/etc/concorde/connecteurs` appartenant au compte du service (`ubuntu`), en 700, le
  fichier en 600.
- Le service a le droit d'écrire **dans ce seul dossier** (`ReadWritePaths`), et nulle
  part ailleurs dans `/etc`.
- L'écriture devient **atomique** (fichier temporaire, puis renommage) : une coupure en
  pleine écriture ne peut plus perdre les secrets déjà enregistrés. Aujourd'hui, le
  fichier est réécrit sur place.
- Mise en place : une seule commande `sudo`, lancée par Stéphane (création du dossier
  et mise à jour du service). Aucun fichier de secrets n'existe encore : il n'y a rien
  à déplacer.

### 4. Un FEC se dépose depuis l'écran
- Pour un logiciel sans API (Sage 100, Sage 50, Quadra, Loop), on ajoute une connexion
  « FEC (fichier) » et on **dépose** le fichier depuis le navigateur.
- Il est rangé dans `/var/lib/concorde-interface/depots/<connexion>/FEC.txt` (dossier
  700), à **200 Mo au plus par défaut**. Ce plafond se change sans toucher au code,
  par la variable `CONCORDE_DEPOT_MAX_MO` de `/etc/concorde/interface.env` (puis
  redémarrage du service). Le fichier est relu tout de suite par la lecture FEC stricte. Un
  fichier refusé n'est pas gardé, et la cause s'affiche.
- Un nouveau dépôt remplace l'ancien. Un transfert déjà créé garde sa photo de la source
  (ADR-0008) et n'est pas touché.

### 5. Un transfert se lance et se suit comme les autres tâches
- **Nouveau transfert** : une source (seules les connexions qui savent lire sont
  proposées), une ou plusieurs destinations (seules celles qui savent écrire, et jamais
  la source elle-même), la période, et pour chaque destination « plan comptable
  identique » ou un fichier de correspondance des comptes.
- Les étapes 1 à 4 tournent en tâche de fond, avec le même suivi en direct que les
  tâches actuelles. Elles comptent dans la limite de 2 tâches à la fois.
- Chaque destination affiche son rapport et peut se télécharger : constats, simulation,
  test, comptes à arbitrer.

### 6. Le feu vert, destination par destination
- Le bouton **Feu vert** n'apparaît que pour une destination « en attente du feu vert ».
- Il demande de **retaper le libellé de la destination** et la **date de la dernière
  sauvegarde** de la destination. Sans ces deux éléments, rien ne part (règle déjà dans
  `donner_feu_vert`).
- Le nouveau test puis le transfert complet (étapes 6 et 7) tournent en tâche de fond.
- Le feu vert est inscrit dans l'audit avec la date et l'adresse IP de la session.

### 7. Un écran à part : « Montée de version »
- Une entrée **Montée de version** dans le menu, distincte de Transferts.
- Le client voit **une montée de version Odoo faite par CONCORDE**. Le nom de l'outil
  utilisé en dessous (OpenUpgrade, ADR-0010) n'apparaît ni à l'écran ni dans le rapport
  remis au client. Il reste écrit dans la documentation interne et dans l'audit.
- L'écran suit le circuit de l'ADR-0010 :
  1. choisir la base Odoo (une connexion Odoo) et la version visée (15 à 18) ;
  2. inventaire des modules, avec ceux qui bloquent la montée ;
  3. photo comptable avant ;
  4. montée pas à pas sur une copie, avec l'avancement par version ;
  5. photo après et comparaison au centime, écart par écart ;
  6. rapport, puis feu vert (nom de la base retapé) ;
  7. nouvel essai sur une copie fraîche, puis livraison.
- Ce qui s'affiche vient seulement de ce qui a été mesuré : une étape non faite reste
  grise, jamais « verte » par défaut.

### 8. Ce qui reste hors de ces écrans
- **Plusieurs utilisateurs** : toujours un seul (ADR-0002).
- **Modifier une connexion** : on la retire et on la recrée. Ses secrets sont effacés
  avec elle.

### 9. Technique
- Aucune nouvelle dépendance : `http.server`, HTML, CSS et JavaScript sans framework,
  comme le reste de l'interface.
- Les nouvelles routes appellent l'annuaire et le moteur de transfert existants. Aucune
  règle de transfert n'est réécrite dans l'interface.
- Routes `/api/connexions…`, `/api/transferts…` et `/api/depots…`, avec la même
  protection que les autres : session, en-tête anti-CSRF, contrôle de l'origine.
- Tests : chaque route, y compris la preuve qu'aucune réponse ne contient de secret ;
  parcours complet dans le navigateur, sur le site en ligne, avec un transfert
  FEC → FEC.

### 10. Ordre de construction
1. Dossier des secrets et écriture atomique (point 3).
2. Écran Transferts : Connexions, dépôt de FEC, transferts, feu vert.
3. Pilotage de la montée de bout en bout par la commande `concorde_montee` (copie,
   conteneurs sur la machine louée, rapport, feu vert), puis l'écran Montée de version
   branché dessus. L'écran ne fait rien que la commande ne fasse déjà, mesuré en CI.

## Conséquences
- Le service peut écrire dans `/etc/concorde/connecteurs`. Une faille dans l'interface
  pourrait donc changer des secrets de connexion, mais pas le mot de passe de
  l'interface (`interface.env`), qui reste en lecture seule.
- Le dossier des secrets entre dans la surveillance de sécurité (ADR-0007) et dans les
  sauvegardes chiffrées.
- L'ADR-0008 (point 3) est modifiée sur le chemin du fichier de secrets.
- **Licence AGPL d'OpenUpgrade** : ne pas citer OpenUpgrade au client ne change rien
  aux obligations de la licence (ADR-0010, arbitrage 6). L'avocat doit confirmer, avant
  la première vente, que le contrat et le rapport client peuvent ne pas le nommer.

## Arbitrages (Stéphane Moreau, 08/11/2026)
1. Secrets dans `/etc/concorde/connecteurs/`, seul dossier inscriptible par le service : oui.
2. Dépôt de FEC : 200 Mo par défaut, **qu'on doit pouvoir augmenter si nécessaire**
   (variable `CONCORDE_DEPOT_MAX_MO`).
3. Correspondance des comptes : « plan identique » ou fichier déposé : oui.
4. Modifier une connexion = la retirer puis la recréer, ses secrets effacés : oui.
5. Montée de version : **un écran spécifique**. OpenUpgrade est utilisé, mais c'est
   **transparent pour le client**.

## Options écartées
- **Garder les secrets en ligne de commande seulement** : rien ne change côté sécurité,
  mais il faut une session SSH pour chaque connexion. C'est contraire à la demande.
- **Rendre `/etc/concorde` entier inscriptible** : le service pourrait alors changer
  son propre mot de passe (`interface.env`).
- **Secrets dans `/var/lib/concorde-interface`** : mélangés avec l'historique et les
  résultats, qui n'ont pas les mêmes règles de sauvegarde ni de surveillance.
- **Un écran par logiciel** : il faudrait toucher à la page à chaque nouveau logiciel,
  alors que les connecteurs déclarent déjà ce qu'ils demandent.
