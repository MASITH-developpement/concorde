# ADR-0008 — Transferts entre logiciels comptables : un pivot, un connecteur par logiciel, plusieurs connexions à la fois

- **Statut** : Proposée — à valider par Stéphane Moreau
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Demande de Stéphane du 08/11/2026 : CONCORDE sert à **transférer des données entre
logiciels**, et pas seulement à migrer vers Odoo. Plusieurs logiciels doivent être
branchés **en même temps** : Sage vers Pennylane, AzalPlus vers Odoo, Quadra vers Sage…
CONCORDE est un logiciel indépendant : Odoo n'est qu'un logiciel branché parmi d'autres.

Logiciels à brancher en premier, d'après les clients :
- **Sage** : Sage 100, Sage 50 (installés) et Sage Business Cloud (en ligne) ;
- **Cegid** : Quadra installé, Cegid Loop, offre Cegid en ligne (accès développeur) ;
- **Pennylane** et **AzalPlus** : jetons API disponibles pour les tests ;
- **Odoo** : déjà branché (ADR-0001, ADR-0004).

Ce qui existe : le format commun en centimes (`core/migration/lot.py`, classe `Lot`), le
circuit à huit portes de l'ADR-0004 (lecture, conversion, problèmes, correspondance,
export, test sur base vierge, test d'une écriture, envoi complet), la lecture FEC stricte
(`core/migration/connecteur_fec.py`), la lecture et l'envoi Odoo.

Il n'existe **pas d'API commune** à ces logiciels : chaque éditeur a la sienne (adresse,
authentification, format), et Sage 100, Sage 50, Quadra et Loop installés n'ont pas
d'API web publique. Le seul format commun est le **FEC**, que tout logiciel comptable
français doit savoir exporter (article A47 A-1 du LPF).

## Décision
### 1. Un pivot central, jamais de liaison directe entre deux logiciels
Tout transfert passe par le format commun de CONCORDE (le `Lot`, en centimes) :
écritures, comptes, journaux, tiers, lettrage. Avec N logiciels, il y a **N connecteurs**,
et non N × (N − 1) liaisons. Un nouveau logiciel = un connecteur, aussitôt utilisable
avec tous les autres, comme source et comme destination.

### 2. Un connecteur = lire, écrire, tester
Chaque connecteur (dossier `connecteurs/`, un fichier par logiciel) offre trois fonctions :
- **tester** la connexion : authentification, société lue (nom, SIREN, devise), droits ;
- **lire** une période vers un `Lot` (porte 1 de l'ADR-0004) ;
- **écrire** un `Lot` dans le logiciel, **en essai à blanc par défaut**.

Chaque connecteur déclare ce qu'il sait faire, et l'interface n'offre que ça :

| Logiciel | Lecture | Écriture | Accès |
|---|---|---|---|
| Odoo 17 | API XML-RPC (existant) | API XML-RPC (existant) | clé API |
| AzalPlus | API REST v2 (`/api/v2/comptabilite`) | API REST v2 (à confirmer sur le compte de test) | jeton Bearer |
| Pennylane | API REST publique | API REST publique (à confirmer sur le compte de test) | jeton API |
| Sage Business Cloud | API REST | API REST | OAuth2 (application développeur Sage) |
| Cegid en ligne | API, selon l'offre | API, selon l'offre | accès développeur Cegid |
| Sage 100 / Sage 50 | export FEC du client | **fichier d'import Sage** produit par CONCORDE | aucun |
| Quadra / Cegid Loop | export FEC du client | **fichier d'import Quadra** produit par CONCORDE | aucun |
| Tout autre logiciel français | export FEC | FEC | aucun |

**Lecture directe** : pour un logiciel à API, CONCORDE se connecte au serveur du logiciel
et lit les données en direct ; personne n'a rien à exporter ni à télécharger. La photo
de ce qui a été lu (règle de l'ADR-0004) est une trace gardée sur le serveur CONCORDE,
pas un fichier à manipuler.

Pour un logiciel installé sans API, le transfert s'arrête à un fichier prêt à importer,
contrôlé au centime. L'import dans le logiciel est fait par une personne chez le client.

Le connecteur ne fait que traduire entre le logiciel et le `Lot`. Les contrôles,
la correspondance des comptes, l'idempotence, les journaux et les rapports sont
**communs** et ne sont jamais refaits dans un connecteur.

### 3. Plusieurs connexions en même temps
Une **connexion** = un connecteur + un compte précis (ex. « Sage du client A »,
« Pennylane du cabinet », « Odoo de test »). On peut en enregistrer autant qu'il faut,
y compris plusieurs pour le même logiciel.
- Annuaire des connexions : `/var/lib/concorde-interface/connexions.json`, **sans aucun
  secret** (logiciel, adresse, société, libellé, date du dernier test).
- Secrets (jetons, clés, identifiants OAuth2 et jetons de renouvellement) :
  `/etc/concorde/connecteurs.env`, hors git, droits 600, propriétaire le compte du
  service. Jamais dans un journal, un rapport, une réponse de l'API ou un message d'erreur.
- Une connexion se teste à l'enregistrement et avant chaque transfert.

### 4. Un transfert = une source, une ou plusieurs destinations
Un **transfert** = une connexion source + une ou plusieurs connexions destination +
un périmètre (période, journaux, données : écritures, plan, tiers, lettrage).
- **La source n'est jamais écrite** (règle de l'ADR-0004, inchangée). Un logiciel peut
  être source dans un transfert et destination dans un autre, jamais les deux dans le
  même. Source = destination : refusé.
- La source est lue **une seule fois**. Sa photo (FEC + xlsx) est gardée dans le dossier
  du transfert, puis chaque destination suit son propre circuit, indépendant des autres :
  un refus pour Pennylane ne bloque pas Odoo, et chaque destination a son rapport.
- Chaque destination suit **la même procédure**, dans cet ordre (demande de Stéphane
  du 08/11/2026). Chaque étape ne s'ouvre que si la précédente est bonne :
  1. **vérifier les données** à transférer : lecture, conversion et batterie de
     contrôles (portes 1 à 3 de l'ADR-0004) ;
  2. **vérifier la concordance** : correspondance des comptes et des tiers, équilibre et
     totaux identiques au centime entre la source et le lot (portes 4 et 5) ;
  3. **simuler le résultat** : essai à blanc dans la destination, qui montre ce qui serait
     créé, sans rien écrire ;
  4. s'il n'y a **rien à signaler** : **test de transfert** dans l'environnement de test de
     la destination, relu et comparé au centime ;
  5. si le test est bon : **rapport** (données, contrôles, simulation, test), puis
     **attente du feu vert** de Stéphane. Sans feu vert, rien ne part ;
  6. au feu vert : **nouveau test de transfert**, car la source ou la destination ont pu
     changer depuis le rapport ;
  7. si ce nouveau test est bon : **transfert complet**, après sauvegarde déclarée de la
     destination, puis relecture de la destination et comparaison au centime.
- Tout écart, à n'importe quelle étape, arrête la destination concernée et figure dans
  son rapport, avec la cause nommée.
- Environnement de test, selon la destination :
  - Odoo : base vierge du serveur (inchangé) ;
  - logiciel à API : environnement ou société **de test** de l'éditeur. S'il n'y en a pas,
    le transfert s'arrête après la simulation (étape 3), sauf accord écrit de Stéphane
    pour ce client ;
  - destination fichier : le fichier produit est relu par CONCORDE et comparé au `Lot`
    au centime.

### 5. Correspondance des comptes et des tiers par couple source → destination
La table arbitrée de l'ADR-0004 (porte 4) est rangée **par couple** connexion source →
connexion destination, et réutilisée d'un transfert à l'autre. Un compte absent →
fichier « à arbitrer », jamais deviné, même quand les deux logiciels suivent le PCG.

### 6. Idempotence et reprise, pour toutes les destinations
Chaque écriture envoyée porte `CONCORDE/<transfert>/<journal>/<n°>` dans le champ de
référence de la destination ; chaque connecteur indique ce champ. Une écriture déjà
présente n'est jamais renvoyée, et un envoi coupé reprend là où il s'était arrêté.

### 7. Plusieurs transferts à la fois, sans se marcher dessus
- Plusieurs transferts peuvent tourner en même temps.
- **Une seule écriture à la fois par connexion destination** (verrou par connexion) :
  deux transferts vers le même Pennylane passent l'un après l'autre.
- Chaque connecteur respecte les limites d'appels de son éditeur (attente et reprise,
  jamais d'abandon silencieux).

### 8. Technique
- Python standard (`urllib`, `json`, `ssl`), comme le reste de CONCORDE : **aucune
  nouvelle dépendance**. TLS vérifié, jamais désactivé.
- Chaque connecteur est testé sur des réponses enregistrées (sans réseau, dans la suite
  `pytest`), puis vérifié en réel avec un compte de test avant d'être déclaré prêt.
- Nouvel écran **Transferts** dans l'interface : connexions (ajouter, tester, retirer),
  nouveau transfert, suivi en direct par destination.

### 9. Ce que l'ADR-0008 change dans l'ADR-0004
L'ADR-0004 reste en vigueur pour les contrôles. L'ADR-0008 la remplace sur trois points :
- **la destination n'est plus forcément Odoo** : tout connecteur qui sait écrire ;
- **les étapes 6 à 8** (test sur base vierge, test d'une écriture, envoi complet) sont
  remplacées par la procédure du point 4 (simulation, test, rapport, feu vert, nouveau
  test, transfert) ;
- **les secrets** : l'ADR-0004 les voulait en mémoire seulement. Des connexions
  enregistrées et des jetons OAuth2 renouvelés (le jeton de renouvellement change à
  chaque usage) ne peuvent pas rester en mémoire : ils vont dans
  `/etc/concorde/connecteurs.env` (point 3). Les clés des Odoo distants saisies dans
  l'écran Bases restent en mémoire, comme aujourd'hui.

## Conséquences
- Le module `connecteurs/` devient le seul endroit qui connaît chaque logiciel.
  `core/migration/connecteur_fec.py` et `injectors/odoo17.py` y sont rattachés, sans
  changer leur comportement, avant tout nouveau connecteur.
- Il faut un compte de test chez chaque éditeur à API (Pennylane, AzalPlus, Sage Business
  Cloud, Cegid) pour passer les portes 6 et 7.
- Il faut les spécifications des formats d'import de Sage 100, Sage 50 et Quadra
  (fichiers d'écritures), et un fichier importé chez un vrai client pour valider chacun.
- Le fichier de secrets est sensible : il entre dans la surveillance de sécurité
  (ADR-0007) et dans les sauvegardes chiffrées, jamais dans git.
- Les API des éditeurs changent : chaque connecteur indique la version d'API utilisée,
  et une erreur de format est bloquante et nommée, jamais ignorée.

## Ordre de construction proposé
1. Socle : interface connecteur, annuaire des connexions, secrets, moteur de transfert
   qui reprend le circuit de l'ADR-0004, sur une seule branche.
2. **FEC** et **Odoo** rattachés au socle (ils existent) : premier transfert FEC → Odoo
   par le nouveau moteur, résultat identique à aujourd'hui au centime.
3. **Pennylane** et **AzalPlus** (lecture puis écriture), vérifiés avec les jetons de test.
4. **Sage** : Business Cloud par API, puis fichiers d'import Sage 100 / Sage 50.
5. **Cegid** : fichiers d'import Quadra / Loop, puis API en ligne avec l'accès développeur.
6. Écran **Transferts**.

## Arbitrages
Tranchés par Stéphane le 08/11/2026 :
- lecture directe par l'API, sans export ni téléchargement, pour les logiciels à API ;
- destination à API sans environnement de test : arrêt après la simulation ;
- plusieurs connexions en même temps ; une seule écriture à la fois par destination ;
- procédure de transfert du point 4 ;
- connexion directe au serveur de chaque logiciel par l'API de son éditeur.

Encore ouverts :
1. Secrets en fichier `/etc/concorde/connecteurs.env` (point 9) : d'accord ?
2. Plusieurs destinations : indépendantes (un refus n'arrête pas les autres) ou
   tout-ou-rien ?
3. Le nouveau test de transfert après le feu vert (étape 6) se fait-il dans
   l'environnement de test, ou par une écriture dans la vraie destination, aussitôt
   relue puis supprimée (porte 7 de l'ADR-0004) ?
4. Logiciels installés sans API (Sage 100, Sage 50, Quadra, Loop) : export FEC par le
   client, ou petit programme CONCORDE installé chez le client qui lit et envoie ?

## Options écartées
- **Une liaison par couple de logiciels** (Sage → Pennylane, Sage → Odoo…) : 20 liaisons
  pour 5 logiciels, 30 pour 6, chacune avec ses propres contrôles. Ingérable et contraire
  à la règle « une action répétée devient une routine commune ».
- **Passer par un intermédiaire payant** (agrégateurs d'API comptables européens ou
  américains) au lieu de se connecter soi-même à chaque serveur : un seul branchement,
  mais abonnement par connexion, données des clients qui transitent chez un tiers
  (contraire au principe de souveraineté de CONCORDE), contrôles au centime impossibles
  à garantir de bout en bout, et dépendance à un tiers pour le cœur du produit.
  Retenu à la place : chaque connecteur se connecte **directement au serveur du
  logiciel** (Odoo, Pennylane, AzalPlus, Sage, Cegid…) par l'API de son éditeur.
- **FEC seulement, sans API** : marche partout pour lire, mais aucun envoi automatique,
  et pas de tiers ni de lettrage complets selon les logiciels. Gardé comme solution de
  repli pour tout logiciel sans connecteur.
- **Écrire directement dans la base de données d'un logiciel** (SQL) : contourne les
  contrôles de l'éditeur, casse sa garantie, interdit par l'ADR-0001 pour Odoo et
  impossible sur les offres en ligne.
