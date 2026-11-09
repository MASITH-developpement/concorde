# ADR-0013 — Compléter le SIREN et la TVA des tiers depuis CONCORDE

- **Statut** : Proposée
- **Date** : 09/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
L'analyse d'Albhades (base `alb_alpha`, 08/11/2026) signale **182 sociétés françaises
sans SIREN ni TVA** (constat `TIERS_SANS_SIREN_TVA`). Depuis la facture électronique,
le SIREN du client est une mention obligatoire : sans lui, la facture ne peut pas
passer par une plateforme agréée. Stéphane veut les compléter directement dans
CONCORDE (demande du 09/11/2026), au lieu de le faire fiche par fiche dans Odoo.

Mesures du 09/11/2026 :
- l'annuaire public des entreprises (`recherche-entreprises.api.gouv.fr`, État, gratuit,
  sans clé) répond depuis le serveur : nom, SIREN, siège (code postal, commune), état
  (active ou fermée) ;
- un même nom donne souvent plusieurs sociétés (« BIOMERIEUX » : 479 090 979 et
  673 620 399) : il faut rapprocher aussi l'adresse, et une personne doit valider ;
- CONCORDE lit déjà, pour chaque tiers, `company_registry` (SIREN), `vat`, l'adresse
  et le pays.

## Décision proposée
### 1. Proposer, jamais deviner
Pour chaque tiers du constat, CONCORDE interroge l'annuaire avec le nom, puis classe
les réponses :
- **sûre** : une seule société active dont le nom et le code postal du siège (ou d'un
  établissement) correspondent ;
- **à choisir** : plusieurs candidates, montrées avec leur adresse ;
- **introuvable** : aucune réponse (tiers étranger mal codé, nom abrégé…).

Le SIREN proposé est toujours contrôlé (clé de Luhn) et la société doit être active.
Rien n'est écrit sans une validation de Stéphane, ligne par ligne ou par lot de
propositions « sûres ».

### 2. La TVA est calculée à partir du SIREN, si demandé
Numéro de TVA français = `FR` + clé + SIREN (calcul officiel). Proposé seulement si
Stéphane le choisit : une société peut avoir un SIREN sans être assujettie à la TVA.

### 3. Écriture par l'API Odoo, d'abord sur la copie de test
- Toujours par l'API d'Odoo (ADR-0001), jamais en SQL : `company_registry` et, si
  choisi, `vat` (Odoo vérifie alors lui-même le format de la TVA).
- Même circuit que l'alignement (ADR-0006) : d'abord sur la copie de test
  (`testalbhade`), relecture, puis **feu vert** (nom de la base retapé) pour la
  production. Une fiche déjà complétée entre-temps n'est jamais écrasée.
- Chaque écriture est tracée (tiers, ancienne et nouvelle valeur, source annuaire,
  date) et réversible : le fichier de trace permet de remettre les anciennes valeurs.

### 4. Écran
Dans le résultat de l'analyse, le constat « Sociétés françaises sans SIREN ni TVA »
gagne un bouton **Compléter**. Il ouvre la liste : tiers, adresse dans Odoo,
proposition de l'annuaire (nom officiel, SIREN, adresse du siège), classe (sûre, à
choisir, introuvable), case à cocher. Puis : **Essayer sur la copie de test**,
**Feu vert pour la production**.

### 5. Limites
- L'annuaire est appelé au plus 7 fois par seconde (limite publiée par l'État) : environ
  30 secondes pour 182 tiers.
- Seuls le nom et le code postal partent vers l'annuaire, jamais d'autre donnée du
  client.

## Questions à trancher
1. Proposition par l'annuaire public de l'État, validée par vous : d'accord ?
2. Écrire aussi la TVA calculée à partir du SIREN, ou seulement le SIREN ?
3. Valider en un clic les propositions « sûres », ou une validation ligne par ligne
   pour toutes ?
4. Toujours passer par la copie de test avant la production : d'accord ?

## Options écartées
- **Recherche par un service payant** (Pappers, Societe.com) : abonnement, et données
  des clients envoyées à un tiers privé, alors que l'État fournit la même source.
- **Écrire sans validation** : un homonyme choisi à tort mettrait un mauvais SIREN sur
  des factures légales.
- **Écrire en SQL dans la base** : contourne les contrôles d'Odoo (ADR-0001).
