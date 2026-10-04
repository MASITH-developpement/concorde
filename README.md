# CONCORDE v1.0 — MARQUÉ DÉPOSÉ ™

**La passerelle de liaison comptable universelle** — (c) MASITH / Stéphane Moreau. Tous droits réservés.

> Migration comptable **Quadra → Odoo 18 Community**, avec un noyau FEC pivot universel.

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
FEC (Quadra, ISO-8859-1) ─► importer_fec ─► verifier_equilibre ─► mapper_comptes ─► lettrer ─► rapport ─► injecteur Odoo 18
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
- **Injecteur Odoo 18** (`injectors/odoo18.py`) — XML-RPC, dry-run par défaut, idempotent.
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
from injectors.odoo18 import InjecteurOdoo18

moteur = MoteurConcorde(config=charger_yaml("concorde.yaml"))
contexte = moteur.executer(open("FEC.txt", "rb").read())
# chaque résultat porte son explication Marceau : r["marceau"]

canon = contexte["resultats"][1]["resultat"]["canon"]
rapport = InjecteurOdoo18().injecter(canon)          # dry-run : rien n'est écrit
# injection réelle (après validation du dry-run) :
# InjecteurOdoo18(url="http://serveur:8069", db="odoo",
#                 utilisateur="admin", mot_de_passe="...",
#                 dry_run=False).injecter(canon)
```

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `MISTRAL_API_KEY` | Active Marceau via API Mistral (sinon moteur à règles) |
| `MARCEAU_MODEL` | Modèle Mistral (défaut : `mistral-small-latest`) |

## Déploiement serveur

Voir `deploy/INSTALL.md` — Docker : **odoo:18 + postgres:16**.

## Roadmap

1. ~~Injecteur Odoo~~ ✅ (`injectors/odoo18.py`, dry-run)
2. ~~Serveur + docker-compose~~ ✅ (`deploy/`)
3. FEC réel du client (validation février 2026)
4. Dépôt INPI — classes 9 et 42

---
*CONCORDE est une marque de MASITH — MARQUÉ DÉPOSÉ ™*
