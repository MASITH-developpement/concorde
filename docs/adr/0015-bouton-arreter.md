# ADR-0015 — Bouton « Arrêter » sur une tâche en cours

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 09/11/2026
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

### 2. Arrêter, c'est aussi défaire ce que la tâche a écrit (arbitrage 1)
Après l'arrêt au point sûr, CONCORDE **efface ce que cette tâche a écrit**, et seulement
cela :
- **SIRET et facture électronique** : les fiches écrites par la tâche reprennent leurs
  anciennes valeurs (trace propre à la tâche) ; une fiche modifiée entre-temps par
  quelqu'un d'autre n'est pas touchée.
- **Transfert et feu vert** : les écritures créées par la tâche (repérées par leur
  référence `CONCORDE/<transfert>/…`) sont repassées en brouillon puis supprimées par
  l'API d'Odoo ; un FEC produit est effacé. **Limite légale** : une écriture validée dans
  un journal protégé contre la modification (inaltérabilité, art. 286 du CGI) ou dans une
  période verrouillée ne peut pas être supprimée ; Odoo refuse, et CONCORDE la **nomme**
  dans le résultat au lieu de la forcer. Un logiciel qui ne sait pas supprimer (API sans
  suppression) est nommé de même.
- **Montée de version** : la copie de travail de la montée (bases, journaux) est effacée ;
  la base du client n'a jamais été touchée.
- **Analyse, téléchargement, propositions, vérification** : rien n'a été écrit, rien à
  défaire.
Le résultat de l'effacement (défait, laissé et pourquoi) figure dans la tâche arrêtée.

### 3. Montée de version : arrêt du saut en cours
- Le bouton dépose un **fichier d'arrêt** pour la montée ; le service le lit toutes les
  10 secondes : il arrête le conteneur du saut en cours, efface la copie de travail, et
  la montée passe au statut « arrêtée ».

### 4. Arrêt d'urgence (arbitrage 4)
- Pas de « tout arrêter » au point sûr (chaque tâche a son bouton). En revanche, un
  bouton **Arrêt d'urgence**, toujours visible, arrête **tout, tout de suite, dans l'état
  où c'est** : l'interface s'arrête et redémarre (systemd), les tâches en cours sont
  coupées net et marquées « interrompues » ; le service de montée arrête tous ses
  conteneurs.
- Confirmation renforcée : message de **danger** (« une écriture en cours peut rester à
  moitié faite dans la base ; le logiciel redémarre ; rien n'est défait
  automatiquement »), et mot `ARRÊT` à retaper.
- Après un arrêt d'urgence, chaque tâche interrompue garde sa trace : les annulations
  (SIRET, facture électronique) et la reprise des transferts restent possibles à la main.

### 5. Traces
Tout arrêt (tâche ou urgence) est inscrit dans le journal de la tâche, dans le journal de
l'interface et dans l'audit (qui, quand, quelle tâche, à quelle étape, ce qui a été
défait).

## Arbitrages (Stéphane Moreau, 09/11/2026)
1. Arrêt au prochain point sûr ; **si une écriture a été faite, elle est effacée** (le
   travail fait sur la base par la tâche).
2. Bouton aussi pendant une écriture en production : oui.
3. Confirmation avant d'arrêter : oui.
4. Pas de « tout arrêter » (un bouton par tâche), mais un **arrêt d'urgence** qui arrête
   tout dans l'état où c'est, avec confirmation et avertissement du danger pour la base
   et le logiciel.

## Options écartées
- **Couper le fil d'exécution brutalement** : Python ne le permet pas proprement, et une
  coupure au milieu d'un appel à Odoo laisserait une écriture dans un état inconnu.
- **Arrêter le service** : coupe tout le site et toutes les autres tâches.
