# CONCORDE v1.0 — MARQUÉ DÉPOSÉ ™

**La passerelle de liaison comptable universelle** — (c) MASITH / Stéphane Moreau. Tous droits réservés.

> Migration comptable **Quadra → Odoo 17 Community**, avec un noyau FEC pivot universel.

## Principes fondateurs

| Principe | Règle |
|---|---|
| Montants | **Toujours en centimes (int)** — jamais de float |
| Arrondi silencieux | **Interdit** — plus de 2 décimales = refus à l'import |
| Tolérance Concordance | **0,00 €** — débit = crédit, sinon blocage |
| Idempotence | Journal + Écriture + compte + montants + libellé = doublon ignoré |
| Souveraineté | LLM **Mistral uniquement** (100 % français) |
| Guardian | 100 % code déterministe, **zéro LLM**, self-check bloquant au démarrage |

## Architecture

```
FEC (Quadra, ISO-8859-1) ──► importer_fec ──► verifier_equilibre ──► lettrer ──► rapport
        │                         │                │                │           │
        Guardian (audit SHA-256 chaîné, rate limiting invisible, self-check bloquant)
        Marceau (explication conversationnelle : API Mistral ou moteur à règles — jamais muet)
```

- **Guardian** (`core/guardian.py`) — surveillance invisible : self-check bloquant, chaque étape
  enveloppée (`envelopper_etape`), audit chaîné SHA-256 (toute altération casse la chaîne),
  rate limiting invisible.
- **Marceau** (`core/marceau.py`) — noyau conversationnel : API Mistral si `MISTRAL_API_KEY`,
  sinon repli autonome sur un moteur à règles. **Jamais muet.**
- **No-code** (`concorde.yaml`) — pipeline 100 % YAML, parseur maison zéro dépendance (`core/yaml_min.py`).
- **Module AZALPLUS** (`azalplus_module.yaml`) — manifeste du module indépendant.

## Utilisation

```bash
python3 -m unittest tests.test_moteur   # tests complets
python3 samples/generateur_fec_test.py fec_test.txt  # FEC synthétique type Quadra
```

```python
from core.moteur import MoteurConcorde
from core.yaml_min import charger_yaml

moteur = MoteurConcorde(config=charger_yaml("concorde.yaml"))
contexte = moteur.executer(open("FEC.txt", "rb").read())
# chaque résultat porte son explication Marceau : r["marceau"]
```

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `MISTRAL_API_KEY` | Active Marceau via API Mistral (sinon moteur à règles) |
| `MARCEAU_MODEL` | Modèle Mistral (défaut : `mistral-small-latest`) |

## Journal Guardian (production)

`/var/concorde/guardian` — audit chaîné SHA-256, vérifiable par `guardian.verifier_chaine()`.

## Roadmap

1. Injecteur **Odoo 17** (XML-RPC, mode dry-run)
2. Serveur Ubuntu + `docker-compose` (odoo:17 + postgres:16)
3. FEC réel du client
4. Dépôt INPI — classes 9 et 42

---
*CONCORDE est une marque de MASITH — MARQUÉ DÉPOSÉ ™*
