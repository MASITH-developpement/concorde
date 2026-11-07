# ADR-0006 — Aligner la production sur la base de test, sur une période (comparer, puis appliquer)

- **Statut** : Acceptée — validée par Stéphane Moreau le 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Le travail de correction se fait dans une **base de test**, une copie de la production du
client restaurée sur notre serveur (exemple : `testalbhade`, copie de `alb_alpha` du
14/10/2026 à 18 h 01 UTC). Une fois le travail validé, la **production** du client doit
devenir identique à la base de test **sur une période**. Cela vaut pour les écritures, mais
aussi pour **l'analytique**, à vérifier et à réinjecter.

Ordre de grandeur chez Albhades : 170 133 lignes d'écritures, dont 97 425 (57 %) avec une
répartition analytique ; 6 plans analytiques, 194 comptes analytiques, 12 règles
d'obligation, 45 451 lignes analytiques.

Choix de Stéphane : **comparer, puis appliquer seulement les différences**. C'est plus sûr
que vider la période en production et tout réinjecter.

## Décision
### 1. Comparatif (lecture seule, rien n'est écrit)
Sur la période choisie, CONCORDE lit la base de test (SQL) et la production (API) et classe
chaque écriture :

| Classe | Sens | Action proposée en production |
|---|---|---|
| identique | même contenu des deux côtés | aucune |
| à créer | n'existe qu'en test | création |
| à modifier | compte, montant, tiers, libellé, date, référence ou lettrage différents | modification |
| **analytique seule** | seule la répartition analytique diffère | réécriture de la répartition |
| à retirer | n'existe plus en test | suppression |
| **conflit** | modifiée ou créée **en production** après la date de la copie | **rien** : à trancher par Stéphane |

**Qui a raison ?** Un comparatif seul ne le sait pas. CONCORDE s'appuie sur la **date de la
copie** (enregistrée avec la base de test) et sur les dates de modification d'Odoo :
- une écriture modifiée en test après la copie, et intacte en production : on l'applique ;
- une écriture créée ou modifiée en production après la copie : c'est un conflit, jamais
  appliqué automatiquement.

**Rapprochement des écritures.** Les écritures qui existaient au moment de la copie portent
le même identifiant dans les deux bases. Celles qui ont été créées **après** la copie peuvent
avoir le même identifiant d'un côté et de l'autre sans être les mêmes. Elles sont donc
rapprochées par leur contenu (journal, date, référence, montants), jamais par leur
identifiant.

**Analytique.** CONCORDE compare la répartition de chaque ligne en traduisant les comptes
analytiques par leur code et leur nom, pas par leur identifiant. Il vérifie aussi :
- les lignes sans analytique là où une règle d'obligation l'exige ;
- les répartitions dont un plan ne fait pas 100 % ;
- les comptes analytiques archivés encore utilisés ;
- l'écart entre une répartition et les lignes analytiques qu'Odoo en a tirées.

Les plans et comptes analytiques créés en test sont créés en production. Ils ne sont
**jamais supprimés** en production.

Le comparatif s'affiche à l'écran, avec le détail en xlsx. Stéphane peut **écarter** des
lignes avant d'appliquer.

### 2. Application (écriture en production, par l'API d'Odoo uniquement)
- Ordre : comptes et plans analytiques manquants, puis créations, modifications, analytique,
  et enfin retraits.
- Écriture validée à modifier ou à retirer : remise en brouillon, correction ou suppression,
  puis revalidation (ADR-0001). Refusé si la période est verrouillée ou le journal sécurisé :
  **CONCORDE ne déverrouille jamais une période**. Une facture validée se corrige par un avoir.
- **Analytique seule** : on réécrit la répartition de la ligne, et Odoo régénère les lignes
  analytiques. Il ne faut donc pas de remise en brouillon si Odoo l'accepte sur une écriture
  validée, ce qui sera vérifié d'abord sur `concorde_test`.
- Étapes : **une** écriture appliquée, relue et comparée ; puis le reste, par paquets, avec
  reprise en cas de coupure. Rien ne part sans **confirmation explicite** (nom de la base
  retapé) ni sans **sauvegarde de la production déclarée**.
- Chaque action est journalisée (avant, après, identifiant Odoo) et scellée par Guardian.

### 3. Contrôle final
Un nouveau comparatif sur la même période doit trouver **0 différence**, hors conflits
écartés. Sinon, CONCORDE affiche les écarts restants.

## Conséquences
- Il faut garder, pour chaque base de test, sa **date de copie** (saisie à la restauration).
- Il faut le **login et la clé API** de la production du client (écran Bases).
- La base de test doit exister pendant toute l'opération. `testalbhade` a été supprimée le
  06/11/2026 à 07 h 24 ; elle peut être restaurée depuis sa sauvegarde
  `testalbhade_20261106-072455.dump` (gardée jusqu'au 13/11) ou depuis
  `alb_alpha_14Oct26_bf.dump`.

## Options écartées
- **Vider la période en production et tout réinjecter** : cela supprime et recrée des
  milliers d'écritures justes, casse le lettrage et l'historique, et prend plus de risque.
- **Rapprocher les écritures par leur seul identifiant** : faux pour celles créées après la copie.
- **La base de test gagne toujours** : cela effacerait le travail fait en production depuis
  la copie.
