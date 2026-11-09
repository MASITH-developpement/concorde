# ADR-0013 — Compléter le SIRET et la TVA des tiers depuis CONCORDE

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 09/11/2026
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
- l'annuaire donne aussi le **SIRET** de chaque établissement (avec son code postal et
  son état) et le **numéro de TVA** de l'entreprise (« BIOMERIEUX », Marcy-l'Étoile :
  SIRET du siège 673 620 399 00026, TVA FR69673620399) ;
- CONCORDE contrôle déjà la clé de Luhn d'un SIREN et d'un SIRET, et la clé d'une TVA
  française (`core/demat.py`).

## Décision
### 1. Proposer, jamais deviner
Les tiers traités sont ceux du constat `TIERS_SANS_SIREN_TVA` d'une analyse (leurs
identifiants Odoo), relus au moment de compléter : une fiche complétée entre-temps est
laissée telle quelle. Pour chacun, CONCORDE interroge l'annuaire avec le nom et le code
postal, puis classe :
- **sûre** : une seule entreprise active, dont le nom correspond, avec un établissement
  actif au code postal du tiers, et dont tous les contrôles du point 2 passent ;
- **à choisir** : plusieurs candidates (ou une seule, mais sans établissement au code
  postal du tiers), montrées avec leur adresse ;
- **introuvable** : aucune réponse.

### 2. SIRET et TVA, contrôlés par calcul (arbitrage 2)
- **SIRET** : celui de l'établissement actif au code postal du tiers, sinon celui du
  siège. Contrôlé : 14 chiffres, clé de Luhn (règle La Poste comprise), et ses 9
  premiers chiffres forment le SIREN de l'entreprise (lui aussi contrôlé par Luhn).
- **TVA** : celle donnée par l'annuaire, contrôlée par calcul : `FR` + clé + SIREN, avec
  clé = (12 + 3 × (SIREN mod 97)) mod 97, et le SIREN de la TVA doit être celui du
  SIRET. Une TVA absente ou fausse n'est pas écrite ; le SIRET seul peut l'être.
- Une candidate qui échoue à un contrôle n'est jamais proposée comme « sûre ».

### 3. Validation (arbitrage 3)
Les propositions « sûres » sont cochées d'office et se valident en un clic. Les « à
choisir » demandent de choisir la bonne candidate ; les « introuvables » restent à
compléter dans Odoo.

### 4. Écriture par l'API Odoo, copie de test d'abord (arbitrage 4)
- On choisit **la base à compléter** et **sa copie de test** parmi les bases où CONCORDE
  peut écrire : celles du sélecteur de l'interface (Odoo distant branché avec sa clé
  API, ou base du serveur dont les identifiants d'écriture sont configurés) et les
  connexions Odoo de l'écran Transferts. La copie de test (ex. `testalbhade`) reçoit
  d'abord les mêmes écritures ; puis **feu vert**, nom de la base retapé, pour la
  production. *Mis à jour le 09/11/2026 : au départ, seules les connexions de
  Transferts étaient proposées, ce qui obligeait à ressaisir une base déjà branchée.*
- Toujours par l'API d'Odoo (ADR-0001), jamais en SQL, et seulement trois champs de
  `res.partner` : le SIRET dans `siret` s'il existe (localisation française), sinon dans
  `company_registry`, et la TVA dans `vat` (Odoo refait son propre contrôle).
- Une fiche déjà complétée au moment d'écrire n'est jamais écrasée. Un refus d'Odoo sur
  une fiche n'arrête pas les autres ; il est nommé dans le résultat.
- Chaque écriture est tracée (tiers, champ, ancienne et nouvelle valeur, source, date,
  base) ; la trace permet de remettre les anciennes valeurs.

### 5. Écran
Dans le résultat d'une analyse, le constat « Sociétés françaises sans SIREN ni TVA »
gagne un bouton **Compléter** : choix de la connexion Odoo, liste des propositions
(tiers, adresse dans Odoo, entreprise trouvée, SIRET, TVA, classe), puis **Essayer sur
la copie de test** et **Feu vert pour la production**.

### 6. Limites
- L'annuaire est appelé au plus environ 7 fois par seconde (limite publiée par l'État) :
  quelques dizaines de secondes pour 182 tiers.
- Seuls le nom et le code postal du tiers partent vers l'annuaire.

## Arbitrages (Stéphane Moreau, 09/11/2026)
1. Annuaire public de l'État, propositions validées par Stéphane : oui.
2. **SIRET** (et non le seul SIREN), contrôlé par la clé de Luhn ; **TVA prise dans
   l'annuaire** et vérifiée par calcul.
3. Les propositions « sûres » se valident en un clic : oui.
4. Toujours la copie de test avant la production : oui.

## Options écartées
- **Recherche par un service payant** (Pappers, Societe.com) : abonnement, et données
  des clients envoyées à un tiers privé, alors que l'État fournit la même source.
- **Écrire sans validation** : un homonyme choisi à tort mettrait un mauvais SIREN sur
  des factures légales.
- **Écrire en SQL dans la base** : contourne les contrôles d'Odoo (ADR-0001).
