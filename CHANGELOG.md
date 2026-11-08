# Journal des versions — CONCORDE

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions sémantiques.
Le module Odoo porte la même version au format `17.0.X.Y.Z` (`deploy/addons/concorde/__manifest__.py`).

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
- Envoi Odoo (`core/migration/injection.py`) : `CibleOdoo` (toute base,
  https exigé hors du serveur) ; `CibleTest` en devient un cas particulier,
  avec les mêmes verrous qu'avant. Préfixe de référence au choix du
  transfert ; recherche de l'existant (`rechercher_existants`, `manquants`)
  séparée de la création.
- Lecture XML-RPC d'Odoo : filtre `reference_prefixe`.
- `scripts/concorde_connexion.py` : lister, ajouter, tester, retirer une
  connexion ; saisie masquée d'un secret.
- Code `TRF_ECART_CONCORDANCE` expliqué par Marceau.
- 46 tests (`tests/test_connecteurs.py`) ; 399 → 445 tests.
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
