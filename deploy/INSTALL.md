# Déploiement serveur CONCORDE — Odoo 17 Community + PostgreSQL 16

Guide de déploiement Docker sur serveur Ubuntu 22.04/24.04 LTS.

## 1. Prérequis serveur

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # reconnexion ensuite
```

## 2. Récupérer le déploiement CONCORDE

```bash
git clone https://github.com/MASITH-developpement/concorde.git
cd concorde/deploy
```

## 3. Configurer les secrets

Créer un fichier `.env` à côté du `docker-compose.yml` :

```
POSTGRES_DB=odoo
POSTGRES_USER=odoo
POSTGRES_PASSWORD=<mot de passe base fort>
ADMIN_PASSWD=<mot de passe gestionnaire Odoo fort>
```

Mettre aussi les mêmes valeurs dans `config/odoo.conf` (`db_password` et `admin_passwd`).

```bash
chmod 600 .env config/odoo.conf
```

## 4. Démarrer

```bash
docker compose up -d
docker compose ps          # les 2 services doivent être "healthy/up"
```

Odoo est accessible sur `http://<IP_SERVEUR>:8069`.
Créer la base au premier accès (le gestionnaire de bases demande `ADMIN_PASSWD`).

## 5. Activer la comptabilité (module `account`)

Interface Odoo → Applications → rechercher **Comptabilité** (Accounting) → Installer.

## 6. Brancher l'injecteur CONCORDE

Sur la machine qui exécute CONCORDE (le serveur ou un poste local) :

```bash
cd ..   # racine du dépôt concorde
python3 -m unittest tests.test_moteur    # 15/15 attendus

# Migration complète en 2 commandes :
python3 - <<'EOF'
from core.fec_parser import parse_fec
from injectors.odoo17 import InjecteurOdoo17

canon = parse_fec("FEC_QUADRA.txt")
rapport = InjecteurOdoo17().injecter(canon)   # dry-run : rien n'est écrit
print(rapport)
EOF

# Quand le dry-run est validé, injection réelle :
# InjecteurOdoo17(url="http://<IP_SERVEUR>:8069", db="odoo",
#                 utilisateur="admin", mot_de_passe="...",
#                 dry_run=False).injecter(canon)
```

### Sécurités actives
- **Dry-run par défaut** : aucune écriture Odoo sans `dry_run=False` explicite
- **Idempotence** : réf `CONCORDE/<journal>/<écriture>` — réexécuter ne duplique rien
- **Tolérance Concordance 0,00 €** : journal déséquilibré = injection refusée
- **Guardian** : self-check bloquant + audit chaîné SHA-256 de chaque création

## 7. Sauvegardes

```bash
# Sauvegarde base complète
docker exec concorde-postgres pg_dump -U odoo odoo | gzip > backup_$(date +%F).sql.gz

# restauration
gunzip -c backup_YYYY-MM-DD.sql.gz | docker exec -i concorde-postgres psql -U odoo odoo
```

## Journal Guardian

Sur le serveur, réserver l'emplacement du journal d'audit :

```bash
sudo mkdir -p /var/concorde/guardian
sudo chown $USER /var/concorde/guardian
```

## Notes

- Le dossier `addons/` permet de déposer des modules Odoo personnalisés (ex. module CONCORDE pour AZALPLUS).
- Marceau : définir `MISTRAL_API_KEY` sur la machine CONCORDE pour activer l'IA conversationnelle (sinon moteur à règles, jamais muet).
- (c) MASITH / Stéphane Moreau — CONCORDE, MARQUÉ DÉPOSÉ ™
