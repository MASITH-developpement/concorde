# CONCORDE v1.0 — MARQUÉ DÉPOSÉ ™

**La passerelle de liaison comptable universelle** — (c) MASITH / Stéphane Moreau. Tous droits réservés.

> Migration comptable **Quadra → Odoo 17 Community (chaîne de conversion 14→19 disponible)**, avec un noyau FEC pivot universel.

## Principes fondateurs

| Principe | Règle |
|---|---|
| Montants | **Toujours en centimes (int)** — jamais de float |
| Arrondi silencieux | **Interdit** — plus de 2 décimales = refus à l'import |
| Tolérance Concordance | **0,00 €** — débit = crédit, sinon blocage |
| Idempotence | Journal + Écriture + compte + montants + libellé = doublon ignoré |
| Mapping comptes | Compte Quadra absent du mapping = **blocage** (aucun compte deviné) |
| Souveraineté | LLM **Mistral uniquement** (100 % français) |
| Guardian | 100 % code déterministe, **zéro LLM**, self-check bloquant au démarrage |

## Architecture

```
FEC (Quadra, ISO-8859-1) ─► importer_fec ─► verifier_equilibre ─► mapper_comptes ─► lettrer ─► rapport ─► injecteur Odoo 17 (natif)
        │                        │                 │                   │            │
        Guardian (audit SHA-256 chaîné, rate limiting invisible, self-check bloquant)
        Marceau (explication conversationnelle : API Mistral ou moteur à règles — jamais muet)
```

- **Guardian** (`core/guardian.py`) — surveillance invisible : self-check bloquant, chaque étape
  enveloppée (`envelopper_etape`), audit chaîné SHA-256 (toute altération casse la chaîne),
  rate limiting invisible.
- **Marceau** (`core/marceau.py`) — noyau conversationnel : API Mistral si `MISTRAL_API_KEY`,
  sinon repli autonome sur un moteur à règles. **Jamais muet.**
- **Mapping** (`core/mapping.py`) — correspondance Quadra → Odoo (362 comptes réels client) ;
  compte inconnu = blocage avec le numéro fautif nommé.
- **No-code** (`concorde.yaml`) — pipeline 100 % YAML, parseur maison zéro dépendance (`core/yaml_min.py`).
- **Injecteur Odoo 17 natif** (`injectors/odoo17.py`) — XML-RPC, dry-run par défaut, idempotent. L'injecteur Odoo 18 (`injectors/odoo18.py`) reste fourni : le payload est identique entre 17 et 18.
- **Chaîne de conversion Odoo 14→19** (`injectors/odoo_conversion.py`) — convertit
  les écritures d'une version Odoo à la suivante (14→15→16→17→18→19), un saut à la
  fois, via le canonique en centimes. Équilibre 0,00 € et idempotence vérifiés à
  **chaque saut** ; dry-run par défaut, aucune donnée réelle importée.
- **Module AZALPLUS** (`azalplus_module.yaml`) — manifeste du module indépendant.

## Utilisation

Toutes les commandes se lancent depuis la racine du dépôt (`cd /opt/concorde`) :
les scripts sont des modules (`python3 -m scripts.<nom>`).

```bash
python3 -m unittest tests.test_moteur tests.test_demat tests.test_odoo_donnees tests.test_interface tests.test_surveillance tests.test_migration tests.test_bases_locales tests.test_injection tests.test_comparaison tests.test_rapport_jour   # tests complets
python3 samples/generateur_fec_test.py fec_test.txt  # FEC synthétique type Quadra
```

```python
from core.moteur import MoteurConcorde
from core.fec_parser import parse_fec
from core.yaml_min import charger_yaml
from injectors.odoo17 import InjecteurOdoo17

moteur = MoteurConcorde(config=charger_yaml("concorde.yaml"))
contexte = moteur.executer(open("FEC.txt", "rb").read())
# chaque résultat porte son explication Marceau : r["marceau"]

canon = contexte["resultats"][1]["resultat"]["canon"]
rapport = InjecteurOdoo17().injecter(canon)          # dry-run : rien n'est écrit
# injection réelle (après validation du dry-run) :
# InjecteurOdoo17(url="http://serveur:8069", db="odoo",
#                 utilisateur="admin", mot_de_passe="...",
#                 dry_run=False).injecter(canon)
```

## Contrôle de la dématérialisation des factures

Moteur `core/demat.py` (100 % déterministe, zéro LLM, **lecture seule**) qui vérifie
qu'un Odoo (14 à 20) émet et reçoit correctement ses factures électroniques :

| Volet | Contrôles |
|---|---|
| Configuration | modules Factur-X / UBL / CII, connecteurs Peppol / proxy (mode test = alerte), **SIREN et TVA de la société** (clés de contrôle) |
| Émission | factures validées : erreurs EDI et Peppol, envois en attente, XML structuré présent (pièce jointe, `ubl_cii_xml_id` ou **Factur-X embarqué dans le PDF**), SIREN / TVA des clients B2B français |
| Réception | part des factures fournisseurs reçues en XML, **doublons probables** (fournisseur + référence + montant en centimes), brouillons de plus de 15 jours |

Niveaux : **BLOQUANT** / **ALERTE** / INFO. Rapport horodaté par empreinte SHA-256.
Jamais muet : une analyse tronquée (plafond de factures) est signalée.

- **Dans Odoo** : menu *CONCORDE > Contrôle dématérialisation* > Nouveau > *Lancer le contrôle*.
- **En ligne de commande** (Odoo distant, clé API) :

```bash
export ODOO_API_KEY="..."     # jamais en argument (visible dans ps / l'historique)
python3 -m scripts.check_dematerialisation --url https://mon-odoo.fr --db mabase \
    --user contact@masith.fr --days 30 [--json rapport.json] [--sans-pdf]
# code retour : 0 conforme, 1 erreur de connexion, 2 anomalies
```

Le client XML-RPC refuse toute méthode autre que `search_read` / `fields_get` / `search_count`.

## Passerelle de données Odoo 17 (télécharger, analyser)

Commande `scripts/concorde_odoo.py` — ADR-0001. Deux sources de **lecture**, mêmes résultats :

| Source | Quand | Accès |
|---|---|---|
| `--source sql` | Volumes importants (150 000 lignes ≈ 6 s, ~90 Mo) | PostgreSQL en **lecture seule** ; variables `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` ; `psycopg2` (optionnel, chargé seulement ici) |
| `--source xmlrpc` | Partout, Odoo Online compris | Clé API dans `ODOO_API_KEY` ; seules `search_read` / `read` / `fields_get` sont autorisées |

```bash
# Télécharger : FEC DGFiP, classeur xlsx (une feuille par objet), CSV d'import Odoo
python3 -m scripts.concorde_odoo --source sql --base testalbhade \
    telecharger --format fec xlsx csv --du 2025-01-01 --au 2025-12-31 -o sorties/

# Analyser : équilibre au centime, dates futures, doublons, tiers sans SIREN/TVA…
python3 -m scripts.concorde_odoo --source sql --base testalbhade analyser --json analyse.json
# code retour : 0 conforme, 1 erreur, 2 anomalies
```

- **FEC** : écritures validées uniquement, 18 colonnes, `|`, ISO-8859-15, nom `<SIREN>FEC<AAAAMMJJ>.txt`.
  Refusé (aucun fichier produit) si une écriture est déséquilibrée, si un brouillon est présent
  ou si la société n'est pas en euros. Caractère non représentable : remplacé par `?` et compté.
- **xlsx** : feuilles Ecritures, Comptes, Journaux, Tiers, Factures. Les colonnes `id_*` et
  `modifie_le` servent à la réintégration (phase 3) : ne pas les modifier.
- **CSV** : ordre d'import `1_journaux`, `2_comptes`, `3_tiers`, `4_ecritures` (noms techniques Odoo).
- **Écriture dans Odoo** : jamais en SQL, toujours par l'ORM (phases 2 et 3, à venir).

## Migration ERP → Odoo 17 (ADR-0004) — étapes 1 à 5

```bash
# --table : table arbitrée par le comptable (ou --comptes-identiques, choix explicite)
python3 -m scripts.concorde_migrer FEC_CLIENT.txt -o lots/client_2025 \
    --table table_comptes.xlsx \
    --filtre '{"nom": "À-nouveaux janvier", "journaux": ["AN"], "du": "2025-01-01", "au": "2025-01-31"}' \
    --filtre '{"nom": "Lignes nulles", "portee": "lignes_nulles"}'
# 0 = lot prêt (ou testé avec --tester), 2 = bloqué (voir problemes.xlsx, a_arbitrer.xlsx)
```

**Étape 6** (`--tester`, avec `--reinitialiser-test` pour repartir d'une base vierge) : envoi dans
la base de test du serveur `concorde_test` par l'API d'Odoo — comptes, journaux et tiers manquants
créés, écritures en brouillon puis validées, lettrage refait et vérifié — puis relecture SQL
comparée au lot au centime. Identifiants : `CONCORDE_TEST_*` dans `/etc/concorde/interface.env`.

Étapes : 1 lecture stricte (rien n'est sauté ni dédoublonné en silence), 2 filtres, 3 contrôles,
4 correspondance (jamais de compte deviné), 5 export et conformité (le FEC produit est relu
et comparé au centime). Les filtres retirent des écritures entières ; un filtre qui couperait une
écriture en deux est refusé. Les étapes 7 et 8 (une écriture chez le client, envoi complet)
viennent ensuite.

## Rapport du jour

Écran **Rapport du jour** : CONCORDE rassemble la journée (sécurité, alertes, changements dans Odoo, travaux) et propose ses conclusions, de la plus grave à la plus rassurante. Chaque conclusion peut être décochée (elle disparaît aussi du détail), réécrite ou commentée ; on peut ajouter ses propres conclusions et un commentaire général. Les choix sont gardés par jour : régénérer le rapport ajoute les nouveautés sans écraser les corrections. « Télécharger » produit une page HTML imprimable (impression en PDF depuis le navigateur), avec seulement ce qui a été retenu.

## Comparer deux bases (lecture seule)

Écran **Comparer** de l'interface, ou :

```bash
python3 -m scripts.concorde_comparer --a testalbhade --b testalbhade_cmp \
    --du 2025-11-01 --au 2025-11-30 [--brouillons] [--date-copie 2026-10-14T18:01:57] -o dossier
```

Chaque base est vérifiée et analysée, puis comparée : totaux, soldes par compte, journal et tiers, écritures (identiques, différentes avec le détail, « analytique seule », présentes d'un seul côté), analytique (comptes disparus). Avec la date de copie, chaque différence indique le côté modifié après la copie, et les conflits sont signalés (base de l'alignement prod / test, ADR-0006). Détail complet dans un fichier Excel.

## Interface web

https://concorde.57-129-168-243.sslip.io : Alertes, Comptes, Analyser, Télécharger, Journal, Historique, Bases (ADR-0002, ADR-0003).
Surveillance automatique toutes les 15 min (`CONCORDE_UI_SURVEILLANCE`) : anomalies par compte, contrôles techniques, changements dans Odoo. Chaque alerte est expliquée par Marceau (catalogue local, aucune donnée envoyée à une IA externe).
Un seul utilisateur. Service `concorde-interface` (127.0.0.1:18090, Caddy fait le HTTPS).

```bash
sudo python3 -m scripts.concorde_interface_mdp     # changer le mot de passe (saisie masquée)
sudo systemctl restart concorde-interface
journalctl -u concorde-interface -f                # journal
```

**Bases** : une base Odoo 17 de ce serveur peut être supprimée (« Supprimer… ») ou, si elle a un
modèle vierge, réinitialisée (« Réinitialiser… »). Une copie de base client est sauvegardée avant (sauvegarde
vérifiée, gardée 7 jours) ; une base de test ne l'est pas. Une base client distante ne peut **jamais** être supprimée depuis CONCORDE
(ADR-0005) : « Retirer de CONCORDE » l'enlève seulement de la liste.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `MISTRAL_API_KEY` | Active Marceau via API Mistral (sinon moteur à règles) |
| `MARCEAU_MODEL` | Modèle Mistral (défaut : `mistral-small-latest`) |
| `ODOO_API_KEY` | Clé API Odoo (sources XML-RPC, contrôle démat) |
| `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` | Accès PostgreSQL de `--source sql` (lecture seule) |

## Déploiement serveur

Voir `deploy/INSTALL.md` — Docker : **odoo:17 + postgres:16**.

## Déploiement automatique (webhook GitHub)

Chaque `git push` sur `main` redéploie CONCORDE automatiquement sur le serveur :

1. Sur le VPS : générer un secret (`openssl rand -hex 32`), le mettre dans
   `deploy/concorde-webhook.service` (`CONCORDE_WEBHOOK_SECRET=`), puis :
   `cp deploy/concorde-webhook.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now concorde-webhook`
2. Ouvrir le port 9000 (`ufw allow 9000/tcp`).
3. Sur GitHub : dépôt → Settings → Webhooks → Add webhook :
   - Payload URL : `http://<IP_VPS>:9000/webhook`
   - Content type : `application/json`
   - Secret : le même que dans le service
   - Events : *Just the push event*

Le récepteur (`deploy/webhook.py`, Python stdlib) vérifie la signature
HMAC-SHA256 de chaque requête, ignore tout ce qui n'est pas `main`, et
exécute `git pull` + `docker compose up -d --build`. Journal local dans
`deploy/log/webhook.log`. Toute requête non signée est refusée en 403.

## Roadmap

1. ~~Injecteur Odoo~~ ✅ (`injectors/odoo17.py` natif, `odoo18.py` compat, dry-run)
2. ~~Serveur + docker-compose~~ ✅ (`deploy/`)
3. ~~Chaîne conversion Odoo 14→19~~ ✅ (`injectors/odoo_conversion.py`, 5 sauts, dry-run)
4. FEC réel du client (validation février 2026)
5. Dépôt INPI — classes 9 et 42

---
*CONCORDE est une marque de MASITH — MARQUÉ DÉPOSÉ ™*
