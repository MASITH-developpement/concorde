# ADR-0010 — Montée de version Odoo : OpenUpgrade fait la migration, CONCORDE certifie la comptabilité

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 08/11/2026
- **Date** : 08/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Un client sur un Odoo ancien (14, 15, 16) veut passer à une version récente (17, 18).
La montée de version touche toute la base : modules, comptabilité, stocks, ventes,
utilisateurs. La crainte du client porte d'abord sur la comptabilité : est-elle
identique, à l'euro près, après la montée ?

**OpenUpgrade** (OCA, https://github.com/OCA/OpenUpgrade) fait cette montée pour Odoo
Community :
- une version à la fois (14 → 15 → 16 → 17 → 18), sur une copie de la base ;
- l'Odoo de la version suivante est lancé sur l'ancienne base, avec deux modules :
  `openupgrade_framework` (empêche Odoo de détruire les anciennes tables et colonnes
  pendant la migration) et `openupgrade_scripts` (un script par module Odoo et par
  version, qui déplace les données vers le nouveau format) ;
- les modules sur mesure du client ne sont pas couverts.

**Licence : AGPL-3.** Copier ou adapter son code dans CONCORDE ferait de CONCORDE une
œuvre dérivée, à publier sous AGPL-3, y compris pour un service en ligne. CONCORDE est
« Tous droits réservés ».

Ce que CONCORDE sait déjà faire (mesuré dans le code au 08/11/2026) :
- photo d'une base (`odoo_source.instantane`) et comparaison de deux photos
  (`surveillance.comparer_instantanes`) ; balance générale et balance tiers
  (`odoo_source.balance`, `balance_tiers`), grand livre (`comptes.grand_livre`) ;
- circuit de transfert en 7 étapes avec feu vert (ADR-0008) ;
- chaîne de conversion d'écritures 14 → 19 (`injectors/odoo_conversion.py`), qui ne
  déplace que des écritures, pas une base ;
- limite : `SourceSqlOdoo17` et `SourceXmlRpcOdoo17` ne lisent **que Odoo 17** et
  refusent toute autre version.

Serveur CONCORDE (mesure du 08/11/2026) : 38 Go de disque dont 9,4 Go libres, environ
4 Go de mémoire. Une base comme celle d'Albhades (170 133 lignes d'écritures) montée sur
plusieurs versions n'y tient pas.

## Décision
1. **OpenUpgrade est utilisé tel quel, jamais copié.**
   - Programme séparé : branches officielles OCA, version figée par numéro de commit, sans
     aucune modification, avec sa licence.
   - CONCORDE ne l'importe jamais. Il le lance dans des conteneurs temporaires (PostgreSQL
     et Odoo de la version visée, plus les deux modules OpenUpgrade), sur un réseau Docker
     isolé, sans aucun port ouvert (incident du 01/11/2026).
   - Toute correction d'un script OpenUpgrade est proposée à l'OCA, jamais gardée chez
     nous.
2. **Toujours sur une copie, jamais en production.** La base du client n'est lue qu'une
   fois, pour en faire une copie (sauvegarde). La production reste intacte jusqu'à la
   bascule, décidée avec le client.
3. **Circuit, calqué sur l'ADR-0008 :**
   1. **Inventaire.** Lire la version et les modules installés, puis classer chaque module
      : couvert par OpenUpgrade à chaque saut, ou non couvert (sur mesure, OCA non migré).
      Un module non couvert bloque, avec une liste nommée. Le client choisit : le migrer
      (par son développeur) ou le désinstaller avant.
   2. **Photo comptable avant**, en lecture seule, sur la copie. Elle couvre :
      - balance générale et balance tiers par exercice ;
      - nombre d'écritures validées et totaux débit/crédit par journal ;
      - lignes lettrées et soldes ouverts par compte de tiers ;
      - totaux analytiques par compte analytique ;
      - dates de verrouillage.
      Le tout reçoit une empreinte.
   3. **Montée pas à pas** sur la copie, une version à la fois. Un saut en erreur arrête
      tout, avec le saut et l'erreur nommés.
   4. **Photo après et comparaison au centime.** Tolérance zéro : un seul écart bloque
      (statut BLOQUEE) et donne la liste des écarts.
   5. **Rapport** (inventaire, sauts, comparaison), puis **attente du feu vert** : le nom
      de la base est à retaper, comme à l'ADR-0008.
   6. **Nouvel essai** : la base du client a continué de vivre depuis la copie. Juste avant
      la bascule, on refait une copie fraîche, on remonte, on recompare. Il faut zéro écart
      pour continuer.
   7. **Livraison** : la base montée et le rapport signé. La bascule en production (date,
      gel des saisies) se fait avec le client.
4. **Photo multi-version.** La photo lit la copie directement en SQL, en lecture seule. Un
   adaptateur par version couvre ce qui change d'une version à l'autre. Exemples à
   confirmer sur une vraie base de chaque version :
   - l'analytique est une ligne par compte en 14 et 15, une répartition JSON à partir de
     16 ;
   - le code de compte dépend de la société en 18.
   Chaque adaptateur est testé sur une vraie base de sa version avant d'être utilisé chez
   un client.
5. **Code** : nouveau dossier `core/montee_version/` (inventaire, photo multi-version,
   pilotage des conteneurs, rapport) et une commande `scripts/concorde_montee.py`. L'écran
   viendra après le premier cas réel.
6. **Données du client** : copies chiffrées sur disque, droits 600, supprimées 30 jours après
   la livraison. Mots de passe dans le fichier de secrets (ADR-0008).

## Arbitrages (Stéphane Moreau, 08/11/2026)
1. **Versions** : de 14 à 18 ; 19 dès que la branche OCA est publiée et testée.
2. **Machine** : un serveur de travail dédié, loué le temps d'une montée ; jamais le
   serveur CONCORDE.
3. **Copies du client** : supprimées 30 jours après la livraison.
4. **Tolérance** : zéro écart au centime, sans exception.
5. **Modules sur mesure** : hors périmètre ; migrés par le développeur du client ou
   désinstallés avant la montée.
6. **Juriste** : le montage « OpenUpgrade non modifié, lancé comme programme séparé »
   est validé par un juriste avant la première vente.

## Conséquences
- **Ce qu'on vend** : une montée de version Odoo avec une comptabilité **certifiée
  identique**. OpenUpgrade fait la migration ; CONCORDE prouve qu'elle n'a rien cassé.
- **Code** : le code de CONCORDE reste privé.
- **Dépendances** : Docker et les images officielles PostgreSQL et Odoo sur la machine de
  travail. Aucune nouvelle dépendance Python sans accord.
- **Délai** : il dépend d'OpenUpgrade. Si une version ou un module n'est pas couvert, la
  montée est bloquée ; CONCORDE le dit, il ne contourne pas.
- **À surveiller** : la durée d'un saut sur une grosse base (à mesurer sur une copie de
  `alb_alpha` ou d'une base de même taille) et la place disque nécessaire (environ trois
  copies de la base au pire moment).

## Options écartées
- **Copier ou adapter le code d'OpenUpgrade dans CONCORDE** : CONCORDE passerait sous
  AGPL-3.
- **Réécrire une montée de version « maison »** : des milliers de scripts, par module et
  par version, entretenus par une communauté ; des années de travail.
- **Ne déplacer que les écritures** (`injectors/odoo_conversion.py`) : laisse de côté
  stocks, ventes et utilisateurs. Ce n'est pas une montée de version. Cette chaîne reste
  utile pour un simple transfert de comptabilité entre deux Odoo.
- **Monter directement la base de production** : aucun retour arrière possible ; contraire
  à la règle « rien en production sans accord ».
- **Faire tourner les montées sur le serveur CONCORDE** : pas assez de disque ni
  de mémoire ; une montée qui sature le disque arrêterait aussi le site.
