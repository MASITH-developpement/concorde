# Journal des versions — CONCORDE

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions sémantiques.
Le module Odoo porte la même version au format `17.0.X.Y.Z` (`deploy/addons/concorde/__manifest__.py`).

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
