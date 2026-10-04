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

```bash
python3 -m unittest tests.test_moteur   # tests complets
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

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `MISTRAL_API_KEY` | Active Marceau via API Mistral (sinon moteur à règles) |
| `MARCEAU_MODEL` | Modèle Mistral (défaut : `mistral-small-latest`) |

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
