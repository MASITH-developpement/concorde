# ADR-0015 — Devis et rapport dans AzalPlus : CONCORDE demande par l'API v1, AzalPlus décide

- **Statut** : Proposée — en attente de l'accord explicite de Stéphane Moreau
- **Date** : 09/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Demande de Stéphane du 09/11/2026 : brancher CONCORDE sur AzalPlus pour que la
**création des devis et des rapports soit automatique**. Arbitrages donnés le même
jour : créer **un devis ET un rapport**, et prendre les montants **au catalogue
d'AzalPlus**.

Mesures du 09/11/2026, depuis le serveur CONCORDE et sur le code d'AzalPlus :

- L'ADR-0009 branchait AzalPlus comme **source**, par lecture directe de sa base.
  Cette voie n'est **pas opérationnelle** : le port PostgreSQL d'AzalPlus n'est pas
  joignable depuis ce serveur (le réseau privé prévu n'existe pas). Et l'ADR-0009
  interdit de toute façon d'**écrire** dans AzalPlus par sa base — l'écriture
  contournerait sa numérotation et ses contrôles.
- L'API v2 d'AzalPlus reste inutilisable (mesure de l'ADR-0009, inchangée).
- En revanche, AzalPlus v1 répond en HTTPS (`/health` sain) et offre depuis le
  31/10/2026 une **clé d'API permanente** (`moteur/cle_api.py`) : présentée sur
  `/api/v1/`, elle est **traduite** en jeton interne au nom de son porteur, puis la
  requête poursuit son chemin normal. RBAC, contexte tenant et société, RLS,
  permissions de module, crochets métier et journal d'audit s'appliquent donc à
  l'identique. Portées `api:read` / `api:write` ; `DELETE` refusé à **toute** clé.
- Les créations réelles passent par la route générique `POST /api/v1/<module>`, et
  c'est **elle** qui appelle l'autorité serveur des totaux : numéro du devis,
  sous-total, remise, TVA ventilée, total. CONCORDE n'a aucun total à calculer.
- Le catalogue d'AzalPlus ne contient, ce jour, **aucune prestation CONCORDE**.
- **4 clients sur 340** portent un SIREN (`clients.registration_number`).
- AzalPlus **ignore volontairement** le `societe_id` d'un corps de requête (garde
  anti mass-assignment) : la société émettrice se choisit par l'en-tête
  `X-Societe-ID`.
- Accepter un devis dans AzalPlus (statut `ACCEPTE`) y déclenche la création
  automatique d'une commande **et** d'une intervention.

## Décision
### 1. CONCORDE demande, il n'écrit pas
Une mission terminée donne lieu à **deux demandes** à AzalPlus, par `/api/v1/` et
une clé d'API : un **devis** (`POST /api/v1/devis`) et un **rapport** rangé dans sa
GED (`POST /api/v1/ged`, ou `POST /api/v1/ged/upload` quand la mission a produit des
pièces). Jamais une écriture en base, jamais un calcul de total, jamais un numéro
fabriqué : c'est l'exigence d'AZAP-AUTORITE, et c'est aussi ce qui rend la liaison
insensible aux évolutions d'AzalPlus.

### 2. Les prix viennent du catalogue d'AzalPlus
Une prestation est désignée par le **code** d'un produit du catalogue
(`produits.code`). CONCORDE **lit** chez AzalPlus le prix et le taux de TVA de ce
code, et ne les fixe nulle part. Un code inconnu — ou porté par plusieurs produits
— est un **refus nommé** : aucun prix n'est deviné.

La quantité d'une ligne vaut `forfait` (1) ou le **nom d'une mesure de la mission**
(`lignes`, `ecritures`). Une mesure absente est un refus nommé, jamais un 1 par
défaut. Une quantité nulle écarte la ligne ; si toutes le sont, aucun devis ne part.

### 3. Trois verrous, fermés à la livraison
Rien ne part tant que les trois ne sont pas ouverts, dans `azalplus_documents.yaml` :
`actif`, le **déclencheur** du genre de mission, et `essai_a_blanc` mis à `false`.
En essai à blanc, CONCORDE ne fait que **lire** AzalPlus et dit ce qui partirait.
Aucun interrupteur ne figure dans ce fichier s'il ne fait rien.

### 4. Le client se reconnaît à son SIREN, jamais à son nom
Le SIREN est **lu dans le logiciel comptable du client** (il est l'identité que
CONCORDE a sous la main, et elle est sûre), normalisé à ses neuf chiffres, puis
comparé à `clients.registration_number`. Introuvable : refus nommé, ou création du
client si le réglage `client_absent` vaut `creer`. Porté par plusieurs clients :
refus — il y a quelque chose à démêler dans AzalPlus, pas un choix à faire ici.
**Jamais d'appariement par le nom** : deux clients homonymes seraient confondus.

### 5. Le devis naît en BROUILLON
Parce qu'`ACCEPTE` déclencherait dans AzalPlus la commande et l'intervention :
cette décision appartient à celui qui lit le devis, pas à CONCORDE.

### 6. Une mission ne donne qu'un devis
Un registre local (`/var/lib/concorde-interface/azalplus_documents.json`) retient
la mission émise et son numéro de devis. Rejouer une mission ne crée pas un second
devis ; la référence CONCORDE est en outre portée par le champ `reference` du devis,
de sorte qu'un humain retrouve la mission depuis AzalPlus.

### 7. Un refus d'AzalPlus ne casse jamais une mission réussie
Un transfert qui a abouti reste abouti. Le refus est **dit** au journal et rendu
dans la valeur de retour — jamais avalé. L'outil
`python3 -m scripts.concorde_azalplus emettre <transfert> <destination>` rejoue la
demande (AzalPlus était injoignable, le SIREN vient d'y être renseigné…).

### 8. Ce qui est branché aujourd'hui
La **fin d'un transfert** (ADR-0008, étape 7 : statut `transferee`), et l'outil en
ligne de commande (`verifier`, `emettre`).

## Conséquences
- Il faut, côté AzalPlus, **trois choses** qui n'existent pas encore :
  1. une clé d'API de portée `api:read,api:write`, créée par Stéphane
     (`python3 scripts/mcp_token.py creer --email <porteur> --nom "CONCORDE" --api
     --ecriture`), déposée dans `/etc/concorde/connecteurs/connecteurs.env` sous
     `CONCORDE_AZALPLUS_CLE_API` ;
  2. les **prestations CONCORDE au catalogue**, avec leurs prix — une décision de
     Stéphane, que CONCORDE ne prend pas ;
  3. le **SIREN des clients** concernés (4 sur 340 en portent un).
- Tant que ces trois manquent, la liaison refuse **en le nommant** ; elle ne crée
  jamais un devis approximatif.
- La liaison dépend de la forme de l'API v1 d'AzalPlus : un champ renommé y fait
  échouer la demande avec un motif, jamais une création partielle silencieuse.
- La clé est **révocable** à tout instant depuis AzalPlus
  (`scripts/mcp_token.py revoquer`), ce qui coupe la liaison sans toucher CONCORDE.

## Ce qui reste à faire
- Brancher la **fin d'une montée de version** (ADR-0012) : son point de fin vit
  dans le service root des montées, dont la modification demande une campagne de
  contrôle à part.
- Brancher le **contrôle de dématérialisation** (`core/demat.py`) : il produit déjà
  le SIREN de la société et ses comptages, mais son rapport n'est pas conservé sur
  le serveur ; il faut d'abord décider où il vit.
- Un bouton « Émettre vers AzalPlus » dans l'écran Transferts, quand la liaison aura
  tourné en vrai.
- L'ADR-0009 point B (terminer l'API v2 d'AzalPlus) reste valable pour les
  **écritures comptables** ; la présente ADR ne concerne que les documents
  commerciaux et les rapports.

## Options écartées
- **Écrire les devis dans la base d'AzalPlus** : contourne sa numérotation, ses
  totaux, son RBAC et son audit — écarté par l'ADR-0008 et par AZAP-AUTORITE.
- **Attendre l'API v2** : elle n'est pas utilisable et son chantier vit dans un
  autre dépôt ; la clé d'API v1 existe, traverse toute la pile et suffit.
- **Tenir une grille tarifaire dans CONCORDE** : deux sources de vérité pour un
  prix. Le catalogue d'AzalPlus fait foi.
- **Rapprocher les clients par leur nom** quand le SIREN manque : deux homonymes
  seraient confondus et le devis partirait au mauvais client.
- **Créer le devis en ACCEPTE** pour « gagner une étape » : cela fabriquerait une
  commande et une intervention sans que personne ait lu le devis.
- **Un déclencheur par genre de mission, déclaré même sans branchement** : un
  réglage qui ne fait rien se croit actif. Seuls les genres branchés figurent.
