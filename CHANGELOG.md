# Journal des versions — CONCORDE

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions sémantiques.
Le module Odoo porte la même version au format `17.0.X.Y.Z` (`deploy/addons/concorde/__manifest__.py`).

## [Non publiée]
### Ajouté
- **Compléter SIRET et TVA des tiers** (ADR-0013, acceptée le 09/11/2026) :
  bouton « Compléter SIRET et TVA… » sur le constat « Sociétés françaises
  sans SIREN ni TVA » d'une analyse. Annuaire public des entreprises de
  l'État (nom et code postal seulement) ; SIRET de l'établissement au code
  postal du tiers (sinon le siège), contrôlé par la clé de Luhn et le
  SIREN ; TVA de l'annuaire, contrôlée par calcul. Propositions « sûres »
  (même nom, même code postal, contrôles bons) cochées d'office, « à
  choisir », « introuvables ». Écriture par l'API Odoo d'une connexion
  (champs `siret` ou `company_registry`, et `vat` seulement), d'abord sur
  sa connexion de test, puis feu vert (nom retapé, mêmes choix) ; fiche
  complétée entre-temps jamais écrasée ; trace et annulation.
  `core/tiers_siret.py`, `interface/siret.py`, `interface/static/siret.js`.
- Montée de version conduite par CONCORDE (ADR-0012, acceptée le 08/11/2026),
  sur le serveur CONCORDE : `concorde_montee creer | circuit | feu-vert |
  nouvel-essai | livrer | etat`. Sauvegarde Odoo (.zip) déposée, inventaire
  des modules saut par saut (table de couverture d'OpenUpgrade au commit
  figé : couvert, à vérifier, bloquant), PostgreSQL et Odoo dans des
  conteneurs sur un réseau Docker interne sans port publié, OpenUpgrade non
  modifié une version à la fois, photo avant / après au centime, feu vert
  (nom de la base retapé, une seule fois), nouvel essai sur une copie
  fraîche, livraison d'une sauvegarde Odoo standard avec son empreinte.
- Garde-fous : place disque (3 fois la base + 3 Go au départ, arrêt sous
  2 Go pendant un saut), conteneurs bridés (1,5 Go, 1 processeur, priorité
  basse), mot de passe du PostgreSQL jetable dans un fichier 600, jamais en
  argument ; base restaurée d'une autre version que la sauvegarde : refus.
- CI : job `montee-pilotee` (remplace `montee-odoo`) : base Odoo 14 →
  sauvegarde .zip → montée 14 → 17 par la commande → nouvel essai →
  livraison → restauration de la base livrée dans un vrai Odoo 17 → zéro
  écart. Commits d'OpenUpgrade figés dans `core/montee_version/openupgrade.py`.
- Service de montée (`scripts/concorde_montee_service.py`, root) : file de
  demandes vérifiées champ par champ (`core/montee_version/demandes.py`),
  volume chiffré LUKS (`core/montee_version/volume.py`, clé root 600),
  résumés publiés pour l'écran pendant la montée, effacement à 30 jours.
  Installation : `sudo bash deploy/installer_montee.sh`.
- Écran **Montée de version** (`interface/montees.py`,
  `interface/static/montees.js`) : dépôt de la sauvegarde (.zip, 4 Go par
  défaut, `CONCORDE_MONTEE_DEPOT_MAX_MO`), vérifications, suivi saut par
  saut, inventaire, écarts, feu vert, nouvel essai, livraison et
  téléchargement. L'outil de migration n'y est jamais nommé.
- PostgreSQL jetable à la version du client (`pg_version` de la sauvegarde).
- Inventaire v2 : notes, retraits et fusions d'OpenUpgrade (`apriori.py`)
  suivis saut par saut ; un module standard non annoté est « à vérifier »,
  seul un module absent de la liste bloque.
### Modifié
- `ClientJson` accepte une API publique sans jeton ; `CibleOdoo` a une
  liste de méthodes autorisées par classe (`methodes_autorisees`) ;
  `ConnecteurOdoo.cible` (accès en écriture d'une connexion, classe au
  choix) ; `analyser.normaliser_nom` devient une routine partagée.
- Routines partagées : `commandes.executer` (seul lancement de programme de
  la montée, sans shell), `photo.requete_lecture` et `photo.version_odoo`,
  `outils_cli.afficher_evenement` (repris par `concorde_comparer`),
  `odoo_source.connexion_lecture_seule` (accès d'un PostgreSQL jetable),
  `tests/integration/attendre_odoo` (attente d'Odoo dans la CI).

## [1.8.0] — 2026-11-08
### Modifié
- Secrets des connexions (ADR-0011, acceptée le 08/11/2026) : nouveau chemin
  `/etc/concorde/connecteurs/connecteurs.env`, dans un dossier 700 du compte
  du service, seul endroit de `/etc` où l'interface peut écrire
  (`ReadWritePaths` du service). Écriture atomique : une coupure ne perd plus
  les secrets déjà enregistrés. Une valeur vide est refusée.
- Retirer une connexion efface aussi ses secrets.
### Ajouté
- Écran **Transferts** dans l'interface (ADR-0011) : connexions (ajouter,
  tester, saisir un secret en masqué, retirer), dépôt d'un FEC depuis le
  navigateur (relu aussitôt, refusé sans être gardé s'il est faux), nouveau
  transfert (source, destinations, période, plan identique ou table de
  correspondance), suivi des 7 étapes par destination, fichiers du rapport,
  feu vert (libellé retapé, date de sauvegarde, adresse IP dans l'audit).
  Module `interface/transferts.py` et page `interface/static/transferts.js`.
- Plafond d'un FEC déposé : 200 Mo, réglable par `CONCORDE_DEPOT_MAX_MO`.
- `Annuaire.secrets_renseignes` : pour chaque secret attendu, renseigné ou
  non, jamais la valeur.
- Connecteurs : `parametres_facultatifs` ; l'annuaire refuse un paramètre
  inconnu du connecteur.
- Routines partagées : `Taches.lancer` (toute tâche de fond),
  `transfert.valider_demande` et `transfert.controler_feu_vert` (mêmes règles
  pour l'écran et le moteur).

## [1.7.0] — 2026-11-08
### Ajouté
- Montée de version Odoo (ADR-0010, acceptée le 08/11/2026) : photo comptable
  d'une base Odoo 14 à 18, en lecture seule (`core/montee_version/photo.py`).
  Balance, balance tiers, journaux, lettrage, analytique et dates de
  verrouillage, en centimes, avec empreinte ; `comparer_photos` liste chaque
  écart (tolérance zéro). Les différences de schéma entre versions sont lues
  dans la base, jamais déduites du numéro de version.
- Commande `scripts/concorde_montee.py` : `photo` (photo d'une base, en JSON
  avec empreinte) et `comparer` (chaque écart affiché, code 1 s'il y en a un ;
  une photo retouchée à la main est refusée).
- CI : job `montee-odoo`, montée 14 -> 15 -> 16 -> 17 par OpenUpgrade (OCA),
  lancé tel quel à un commit figé, photo avant / après, zéro écart exigé.
- CI : job `photo-odoo`, sur un vrai Odoo 14, 15, 16, 17 et 18 (base jetable).
  Il crée des écritures connues, prend la photo en SQL, la recalcule par l'ORM
  d'Odoo et exige zéro écart (`tests/integration/verifier_photo.py`).
### Modifié
- Routines partagées : `odoo_source.connexion_lecture_seule` (seule ouverture
  SQL vers Odoo) et `odoo_source.proxys_xmlrpc` (accès XML-RPC, auparavant
  recopié dans `demat`).

## [1.6.0] — 2026-11-08
### Ajouté
- Transferts entre logiciels (ADR-0008, acceptée le 08/11/2026) : socle
  `core/connecteurs/`. Un pivot (le `Lot` en centimes), un connecteur par
  logiciel (tester, lire, écrire, relire ; essai à blanc par défaut),
  plusieurs connexions enregistrées à la fois.
  - `connexions` : annuaire `connexions.json` sans aucun secret (un paramètre
    au nom de secret est refusé) ; connexion d'environnement de test par
    connexion.
  - `secrets` : `/etc/concorde/connecteurs.env`, lu seulement en droits 600 ;
    aucune valeur dans un message, un journal ou un rapport.
  - `transfert` : procédure en 7 étapes par destination (données,
    concordance, simulation, test, feu vert, nouveau test, transfert) ;
    destinations indépendantes ; arrêt après la simulation sans environnement
    de test ; feu vert avec nom de la destination retapé et date de
    sauvegarde ; source relue et comparée à celle du rapport ; une seule
    écriture à la fois par connexion.
  - `fec` : premier connecteur — FEC déposé dans CONCORDE (Sage 100, Sage 50,
    Quadra, Loop…) ou FEC produit ; une référence n'est jamais réécrite.
  - `odoo` : connecteur Odoo 17 par l'API XML-RPC (lecture, écriture,
    relecture par référence, sur Odoo Online comme sur site). Sur une vraie
    destination, un compte, un journal ou un tiers absent bloque l'écriture
    (rien n'est créé sans arbitrage) ; option `creer_manquants=oui` pour une
    base de test vierge.
  - `azalplus` : AzalPlus comme source, lecture seule de sa base PostgreSQL
    (ADR-0009) : entreprise et société filtrées, statuts VALIDEE / VALIDE,
    lignes sans société comptées et signalées, tiers retrouvés par leur nom
    (signalés) ou bloquants (introuvable, sans code, en double).
  - `pennylane` : connecteur Pennylane par l'API v2 (lecture, écriture,
    relecture). L'API n'empêchant pas les doublons, chaque écriture porte sa
    référence CONCORDE dans `piece_number`, cherchée avant l'envoi. Refus
    nommés : journal ou compte absent, compte sous plusieurs identifiants
    (TVA), ligne en devise, avec tiers ou lettrage (non portés par
    Pennylane sur la ligne, règle à arbitrer). Lecture : `statuts_lus`
    exigé. Jeton d'entreprise = bac à sable ; OAuth 2.0 à brancher.
  - `http_json` : client REST JSON commun (Python standard, certificat
    vérifié, reprise après une limite d'appels 429, jeton jamais affiché).
- `Lot.signalements` et alerte `MIG_SIGNALEMENT_SOURCE` dans les contrôles.
- ADR-0009 (AzalPlus : lecture de la base maintenant, écriture par l'API v2
  une fois terminée).
- Envoi Odoo (`core/migration/injection.py`) : `CibleOdoo` (toute base,
  https exigé hors du serveur) ; `CibleTest` en devient un cas particulier,
  avec les mêmes verrous qu'avant. Préfixe de référence au choix du
  transfert ; recherche de l'existant (`rechercher_existants`, `manquants`)
  séparée de la création.
- Lecture XML-RPC d'Odoo : filtre `reference_prefixe`.
- `scripts/concorde_connexion.py` : lister, ajouter, tester, retirer une
  connexion ; saisie masquée d'un secret.
- Code `TRF_ECART_CONCORDANCE` expliqué par Marceau.
- 65 tests (`tests/test_connecteurs.py`) ; 399 → 464 tests.
### Modifié
- Routines partagées au lieu de copies : `core/fichier_json.ecrire_json_atomique`
  (ex-`_ecrire_json_atomique` de l'interface, repris par `surveillance`),
  `connecteurs.secrets.ecrire_variable` (repris par
  `concorde_interface_mdp`), `migration.export.ecrire_fec_lot` et
  `lignes_sortie`, `migration.circuit.statut_constats` et
  `constats_expliques`. Fabriques de FEC et Odoo simulés de test dans `tests/outils.py`.

## [1.5.2] — 2026-11-08
### Ajouté
- Tests : `xlsx_vers_fec` (30 % → 99 %), `mapping` (25 % → 100 %),
  `plan_comptable` (17 % → 100 %), `yaml_min` (0 % → 100 %). Couverture de
  `core` + `interface` : 72 % → 83 % ; 178 → 399 tests.
- CI : couverture mesurée (`coverage`), plancher 83 % (`pyproject.toml`) ;
  `pragma: no cover` ajouté aux motifs interdits.
- `tests/classeurs_xlsx.py` : fabrication commune des classeurs .xlsx de test.
### Corrigé
- Plan comptable : les types de compte produits sont tous des types Odoo valides
  (17 à 20, mesurés dans les images) — « Banque »/« Caisse » donnaient `bank`/
  `cash`, refusés par Odoo à la création du compte ; un type Odoo écrit tel quel
  (`asset_fixed`, `liability_non_current`…) n'est plus remplacé par un type plus
  général ; la correspondance la plus spécifique l'emporte ; un libellé ambigu
  n'est plus deviné ; en-têtes « Numéro/Type de compte » reconnus ; un doublon
  identique n'est rendu qu'une fois et un conflit de types est nommé.
- Dates JJ/MM/AAAA dont le jour vaut 19 ou 20 (ex. 20/12/2020) : refusées à
  tort, lues désormais selon la position des séparateurs. Les formats mal
  construits lus par hasard (`05/0124`) sont refusés.
- Mapping : toute entrée illisible (JSON invalide ou objet, fichier absent,
  paire incomplète, cellule `#N/A` ou nombre illisible, XML invalide) donne une
  ErreurMapping explicite au lieu d'une erreur Python ; le journal n'est plus
  laissé à moitié renommé en cas d'erreur ; la feuille désignée par un chemin
  absolu est la bonne ; un en-tête en double ou réparti sur deux lignes est
  refusé ; un journal canonique vide fourni est reconnu.
- Lecteur YAML : listes `[a, b]`, commentaires de fin de ligne, listes et tables
  imbriquées dans une liste ; un retrait incohérent ou une construction non
  gérée lève `ErreurYaml` (ligne citée) au lieu de perdre des données.
### Modifié
- `xlsx_vers_fec` : retrait du seul `pragma: no cover` ; le repli sans
  openpyxl est maintenant testé.
- Lecture des cellules (mapping et plan comptable) : une cellule en erreur Excel
  ou illisible arrête la lecture avec la cellule citée, même dans une colonne
  non utilisée.
- `lettres_colonne` (`core/xlsx_ecrire.py`) : une seule routine pour les lettres
  de colonne Excel (trois copies auparavant).

## [1.5.1] — 2026-11-08
### Corrigé
- Assistant d'import (Odoo 17) : un FEC texte (.txt) échouait toujours
  (« Ligne d'en-tête FEC introuvable ») et était conservé encodé deux fois.
  Cause : Odoo 17 rend le champ fichier en octets base64, que `_lire_binaire`
  prenait pour le fichier brut ; seuls les .xlsx passaient. Le base64 est
  désormais décodé (str ou octets, caractères hors alphabet refusés) ; une
  chaîne qui n'est pas du base64 donne un message clair.

## [1.5.0] — 2026-11-07
### Ajouté
- Contrôle de la dématérialisation des factures (menu CONCORDE > Contrôle
  dématérialisation) : Factur-X / UBL / CII, erreurs EDI et Peppol, SIREN / TVA,
  doublons — lecture seule.
### Corrigé
- Export vers Odoo (`action_exporter`) : le CSV des comptes portait le numéro
  de compte au lieu de son intitulé. Il reprend désormais l'intitulé lu dans le
  FEC (colonne CompteLib), comme l'import.
- Moteur : le dossier du journal Guardian était cherché sous `guardian` alors
  que la configuration (`concorde.yaml`, assistant) le range sous
  `noyau.guardian` ; le réglage était ignoré au profit du dossier par défaut.
- Lecture .xlsx sans openpyxl : un classeur contenant des styles nommés
  (`cellStyleXfs`) décalait les styles de cellules ; une date était alors lue
  comme un nombre (« Date invalide : 45296 »).
- Assistant d'import : un fichier de type inattendu affichait une erreur Python
  (`UnboundLocalError`) au lieu du message « Type de fichier inattendu ».
  Cause : la boucle anti-double-encodage utilisait `_` comme variable et masquait
  la fonction de traduction dans toute la méthode `_lire_binaire`.
- Bases locales : le nom du modèle vierge n'était pas vérifié avant d'être inséré
  dans `CREATE DATABASE … TEMPLATE` ; il l'est désormais AVANT la suppression
  (routine `_identifiant_sql`).
- Odoo : une traduction vide (jsonb) donne un texte vide, jamais « None ».
- `core/migration` : `NotRequired` / `Required` (Python 3.11+) remplacés par des
  TypedDict compatibles Python 3.10 (Python d'Odoo 17) — l'import plantait en 3.10.
- Un test était sauté faute de fichier client : il tourne avec un mapping synthétique.
### Modifié
- Lancement en modules depuis la racine : `python3 -m interface.serveur`,
  `python3 -m securite.concorde_securite`, `python3 -m scripts.<nom>`
  (services systemd mis à jour : WorkingDirectory + ExecStart).
- Qualité mesurée : flake8 (règles par défaut), black (79), mypy --strict
  (Python 3.10 et 3.14), docstrings complètes, aucun `noqa` / `type: ignore`.
- Code dupliqué factorisé (injecteurs Odoo 17/18, transports XML-RPC, lecture
  xlsx, curseurs, tests…).
- Nouvelle CI bloquante `.github/workflows/qualite.yml`.
- `scripts/install_module.sh` : plus de `|| true` (erreur SQL explicite).
### Sécurité
- Odoo n'est plus joignable depuis Internet : les ports 8017 et 8021 n'écoutent que
  sur `127.0.0.1` (Docker contournait le pare-feu ufw). Seul Concorde, sur le
  serveur, l'utilisait (journaux des 7 derniers jours).
- `deploy/config/odoo.conf` contenait les mots de passe en clair et était publié :
  il devient le modèle `odoo.conf.exemple` ; la configuration réelle
  `odoo.local.conf` reste sur le serveur, hors git. Mots de passe changés.
- Ajout d'un `.gitignore` : les fichiers `.env` (mots de passe) ne peuvent plus être commités.
- Lecture XML (.xlsx clients) et XML-RPC protégées par **defusedxml** (`core/xml_sur.py`) :
  bombe d'entités, entités externes et DTD refusées. Nouvelle dépendance :
  `defusedxml` (paquet Ubuntu `python3-defusedxml`) ; le conteneur Odoo l'a déjà
  (image odoo:17, defusedxml 0.7.1).
- bandit : 66 alertes → 16, revues une à une et figées dans
  `bandit_reference.json` (la CI échoue sur toute nouvelle alerte) :
  - B404 / B603 (8) : `subprocess` lance pg_dump, pg_restore, clamscan, git et
    docker par chemin absolu, arguments en liste, sans shell ;
  - B411 (1) : `core/xml_sur.py` importe `xmlrpc.client` pour le protéger
    (`defusedxml.xmlrpc.monkey_patch`) ;
  - B104 (3) : le webhook écoute sur toutes les interfaces pour recevoir GitHub
    (requêtes signées HMAC) ; deux faux positifs comparent l'adresse `0.0.0.0`
    lue dans Docker ;
  - B108 (3) : `/tmp`, `/var/tmp`, `/dev/shm` sont des dossiers surveillés par
    l'antivirus, rien n'y est écrit ;
  - B311 (1) : `random` à graine fixe pour les données de test.

## [1.4.9] et antérieures
Voir l'historique git (`git log`).
