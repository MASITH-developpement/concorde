# ADR-0015 — Bouton « Arrêter » sur une tâche en cours

- **Statut** : Proposée
- **Date** : 09/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Demande de Stéphane du 09/11/2026 : pouvoir **arrêter une action qui ne lui plaît
pas**, depuis l'écran, pendant qu'elle tourne (analyse, téléchargement, transfert, feu
vert, propositions et écritures SIRET ou facture électronique, montée de version).

Aujourd'hui, une tâche lancée va jusqu'au bout ; seul l'arrêt du service l'interrompt,
et l'arrêt du service coupe tout le site.

Ce qui existe (mesuré dans le code au 09/11/2026) :
- chaque tâche de l'interface tourne dans un fil et raconte chaque étape et chaque lot
  dans son **journal** (`Journal.dire`) ;
- les écritures sont faites pour être reprises : transferts idempotents (référence
  `CONCORDE/<transfert>/…`, ADR-0008), écritures SIRET et facture électronique tracées
  fiche par fiche et annulables (ADR-0013, 0014) ;
- la montée de version tourne dans un **service à part** (root, ADR-0012), qui traite une
  demande à la fois ; ses sauts sont des conteneurs Docker.

## Décision proposée
### 1. Arrêt au prochain point sûr, jamais au milieu d'une écriture
- Bouton **Arrêter** à côté de toute tâche en cours (écran qui l'a lancée et Historique),
  avec une confirmation (« Arrêter cette tâche ? Ce qui est déjà fait reste fait. »).
- L'arrêt est **demandé**, puis appliqué au prochain message du journal de la tâche :
  entre deux étapes, deux lots ou deux fiches, jamais pendant un appel à Odoo. La tâche
  passe au statut **« arrêtée »**, avec l'heure et l'étape où elle s'est arrêtée.
- Une tâche en attente de place (2 tâches à la fois) est arrêtée tout de suite.

### 2. Ce qui est fait reste fait, et se reprend
- Transfert ou feu vert arrêté : les écritures déjà faites restent dans la destination ;
  relancer le feu vert reprend sans doublon (idempotence ADR-0008).
- SIRET et facture électronique : les fiches déjà écrites restent, tracées ; le bouton
  « Annuler l'écriture » les remet si besoin.
- Analyse, téléchargement, propositions : rien n'est écrit ; il suffit de relancer.

### 3. Montée de version : arrêt du saut en cours
- Le bouton dépose un **fichier d'arrêt** pour la montée ; le service le lit toutes les
  10 secondes (même fil que le garde-fou du disque) : il arrête le conteneur du saut en
  cours, puis la montée passe au statut « arrêtée ». La copie de la base reste dans le
  volume chiffré : on peut relancer les vérifications, ou laisser l'effacement à
  30 jours s'en charger.
- Restauration de la sauvegarde ou photo en cours : arrêt à la fin de l'étape.

### 4. Traces
L'arrêt est inscrit dans le journal de la tâche, dans le journal de l'interface et dans
l'audit (qui, quand, quelle tâche, à quelle étape).

## Questions à trancher
1. Arrêt **au prochain point sûr** (quelques secondes au plus en général), jamais au
   milieu d'une écriture : d'accord ?
2. Le bouton est aussi proposé pendant une **écriture en production** (feu vert),
   en sachant que ce qui est déjà écrit reste écrit : d'accord ?
3. Une **confirmation** avant d'arrêter : d'accord ?
4. Un bouton « **tout arrêter** » en plus (toutes les tâches en cours) : oui ou non ?

## Options écartées
- **Couper le fil d'exécution brutalement** : Python ne le permet pas proprement, et une
  coupure au milieu d'un appel à Odoo laisserait une écriture dans un état inconnu.
- **Arrêter le service** : coupe tout le site et toutes les autres tâches.
