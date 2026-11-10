# ADR-0017 — Analyse : soldes cumulés et rôles de comptes par client

- **Statut** : Acceptée (plan validé par Stéphane le 10/11/2026)
- **Date** : 10/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Analyse d'un dossier client réel (Odoo 17 Enterprise, plan comptable à
8 chiffres repris d'un autre logiciel, mêlé de comptes Odoo standard). Les
montants sont exacts, mais la plupart des alertes de sens des soldes sont
des faux positifs :

- la balance ne prenait que les mouvements de la période. L'historique de
  l'exercice précédent (écritures comptabilisées) était ignoré, et
  l'à-nouveaux est volontairement en brouillon : une caisse ou un client
  créditeur sur la période ne l'est plus en cumul ;
- les règles reposaient sur les préfixes du plan comptable général. Un plan
  repris d'un autre logiciel les trompe : les comptes Odoo de paiements en
  suspens (sous 512) ne sont pas des banques ; la TVA collectée est répartie
  entre le compte standard d'Odoo, le compte de l'ancien logiciel et un
  compte de transition ;
- le journal de TVA sur encaissements (CABA) crée une écriture par règlement
  partiel : la grande majorité des doublons probables et des lignes à
  montant nul en viennent.

Le dépôt est public : aucune donnée client ne doit y entrer.

## Décision
1. **Solde cumulé à la date de fin** pour toutes les règles de sens des soldes :
   écritures comptabilisées (`parent_state = 'posted'`) datées au plus tard
   à la date de fin. Les brouillons restent exclus.
   - Comptes de bilan : depuis l'origine, ou depuis la dernière écriture
     d'à-nouveaux **comptabilisée** (les lignes antérieures sont alors écartées :
     l'ouverture n'est jamais comptée deux fois).
   - Comptes de gestion (charges et produits) : depuis le début de l'exercice
     qui contient la date de fin, lu dans la société Odoo
     (`fiscalyear_last_month`, `fiscalyear_last_day`).
   - Écriture d'à-nouveaux : l'ouverture déclarée dans la société Odoo
     (`account_opening_move_id`) et les écritures des journaux listés dans
     `concorde.yaml` (`analyse.journaux_a_nouveaux`, par défaut AN et RAN).
   - Le rapport affiche les deux valeurs (période et cumul) ; l'alerte ne se
     déclenche que sur le cumul. `infos.calcul_soldes` dit le mode retenu et
     le nombre de lignes antérieures prises en compte.
   - Constat INFO `OUVERTURE_DOUBLE_POSSIBLE` quand une écriture d'à-nouveaux
     et un historique antérieur coexistent, avec le choix fait.
2. **Rôles de comptes par client**, dans `/etc/concorde/roles_clients.yaml`,
   **hors git** (modèle fictif `roles_clients.exemple.yaml` dans le dépôt ;
   une section `clients` dans `concorde.yaml` est refusée). Le client est
   reconnu par le nom de la base, puis par le nom de la société Odoo.
   - Avec une table : rôle lu dans la table (code exact, puis préfixe le plus
     long), sinon d'après l'`account_type` d'Odoo, sinon d'après le préfixe du
     plan comptable général.
   - Sans table (ou sans fichier) : préfixes seuls (et `account_type` pour les
     tiers), comme avant.
   - Chaque constat cite le rôle retenu et sa source (table client,
     account_type, préfixe).
3. **Nouveaux contrôles** : `PAIEMENT_EN_SUSPENS_NON_SOLDE` (lignes non
   lettrées les plus anciennes), `TVA_COLLECTEE_REPARTIE` (au moins deux comptes
   du groupe TVA collectée au-delà d'un seuil, 1 000 € par défaut, réglable par
   client), `TVA_COLLECTEE_SENS_CONTRAIRE` (compte du groupe de sens contraire
   au groupe), `CHARGE_PROVISION_CREDITRICE` (INFO, provisions dont la reprise
   peut rendre le solde créditeur).
4. **Journal de TVA sur encaissements** (`tax_cash_basis_journal_id` de la
   société) : un doublon exige le même `tax_cash_basis_rec_id` quand il est
   renseigné, et les paires écriture + extourne (`reversed_entry_id`) sont
   écartées. Ses lignes à montant nul ne sont plus signalées ; les autres sont
   ventilées par journal.
5. Lecture seule inchangée : seules `search_read`, `read`, `fields_get` et
   `search_count` sont appelées par l'API.

## Conséquences
- Lecture supplémentaire des lignes comptabilisées antérieures à la période
  (compte, tiers, montants seulement). Par l'API, c'est plus long sur un gros
  historique.
- L'écran Comptes et la surveillance gardent leur calcul (hors périmètre de
  cette décision) : leurs alertes peuvent différer de celles de l'analyse.
- Les tables des clients s'installent sur le serveur par root, hors git : la
  synchronisation de `main` ne les écrase pas ; elles sont à sauvegarder avec
  `/etc/concorde`.

## Options écartées
- **Ajouter l'historique aux mouvements de la période sans détecter
  l'ouverture** : compte deux fois l'ouverture dès que l'à-nouveaux est
  comptabilisé.
- **Cumuler les comptes de gestion depuis l'origine** : additionne les charges
  et produits de plusieurs exercices non clôturés dans Odoo.
- **Tables des clients dans `concorde.yaml`** : le dépôt est public, et le
  serveur est remis sur `main` chaque minute.
- **`read_group` d'Odoo pour les cumuls** : méthode hors de la liste de lecture
  seule de la source.
- **Reconnaître le journal CABA par son code** : le code est libre ; la
  société Odoo dit lequel sert à la TVA sur encaissements.
