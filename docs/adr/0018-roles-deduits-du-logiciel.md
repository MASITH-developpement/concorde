# ADR-0018 — Rôles des comptes déduits du logiciel, pour tous les clients

- **Statut** : Acceptée (plan validé par Stéphane le 10/11/2026 : « commence par odoo puis azalplus »)
- **Date** : 10/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
L'ADR-0017 corrige le calcul (soldes cumulés), mais le rôle de chaque compte
(banque, paiements en suspens, TVA collectée…) ne vient que d'une table écrite
à la main pour un client, ou des préfixes du plan comptable général. Pour tout
autre client, les faux positifs reviennent : comptes Odoo de paiements en
suspens pris pour des banques, TVA collectée contrôlée compte par compte,
comptes d'attente non reconnus. Le rapport doit être juste pour tous les
clients, quel que soit leur logiciel (Odoo, AzalPlus, Cegid, Sage…).

## Décision
1. Le rôle d'un compte est **déduit automatiquement**, sources essayées dans
   cet ordre ; chaque constat cite celle qui a servi :
   1. **table client** (facultative, hors git, ADR-0017) : correction d'un cas ;
   2. **configuration du logiciel**, lue par son connecteur en lecture seule.
      Odoo : comptes des journaux de banque et de caisse, comptes de paiements
      en suspens (société et moyens de paiement), comptes d'attente (journaux,
      société, virements internes), comptes des taxes de vente (TVA collectée,
      transition comprise), d'achat (TVA déductible) et d'autoliquidation
      (lignes négatives des taxes d'achat : TVA à suivre à part) ;
   3. **comportement des écritures** (tout logiciel) : compte de TVA collectée
      toujours compensé dans la même écriture par une TVA déductible du même
      montant = autoliquidation ; compte 512 / 58 dont les lignes sont lettrées
      = compte de transit (paiements en suspens) ;
   4. **libellé du compte** (français et anglais) : « attente », « suspense »,
      « paiements … en suspens », « outstanding », « intracommunautaire »,
      « import », « provision » ;
   5. **type de compte du logiciel** (Odoo : `account_type`) ;
   6. **préfixe du plan comptable général** : la TVA collectée 4457x forme un
      groupe ; acomptes 419 / 409 sans alerte de sens ; 6412 / 6413 (congés
      payés, primes) en INFO.
2. Sans table client, l'analyse doit donner sur un dossier réel le même
   résultat qu'avec la table : c'est le test de référence (préproduction
   du client qui a motivé l'ADR-0017).
3. Ordre des logiciels : **Odoo** d'abord, puis **AzalPlus**, puis les autres
   connecteurs (Cegid Loop, Sage Business Cloud par API ; FEC pour les
   logiciels sans API).
4. L'écran Comptes et la surveillance gardent leur calcul actuel (hors
   périmètre, comme pour l'ADR-0017).

## Conséquences
- Une lecture de plus par analyse : configuration du logiciel (quelques
  centaines d'enregistrements), en lecture seule.
- Les règles de libellé et de comportement sont des indices : leur source est
  toujours affichée, et la table client permet de les corriger.
- Chaque connecteur pourra fournir sa configuration ; sans elle, les sources
  3 à 6 s'appliquent.

## Options écartées
- **Une table écrite à la main pour chaque client** : ne passe pas à l'échelle
  et laisse les nouveaux clients avec des faux positifs.
- **Le préfixe seul** : trompé par les plans repris d'un autre logiciel.
- **Le libellé avant la configuration** : un libellé est libre ; la
  configuration du logiciel dit à quoi sert vraiment le compte.
