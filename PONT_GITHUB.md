# Pont de deploiement CONCORDE (Vibe <-> VPS)

## Installation unique (sur le VPS, en root)

```bash
cd /opt/concorde
# 1. Recuperer les scripts
git pull origin main 2>/dev/null || true
cp scripts/concorde-sync.sh /usr/local/bin/ && chmod +x /usr/local/bin/concorde-sync.sh
cp scripts/diag.sh /opt/concorde/ && chmod +x /opt/concorde/diag.sh
# 2. Cron de synchro auto (toutes les minutes)
(crontab -l 2>/dev/null | grep -v concorde-sync; echo "* * * * * /usr/local/bin/concorde-sync.sh") | crontab -
echo "PONT INSTALLE"
```

## Usage

- **Synchro** : automatique, chaque push GitHub arrive en < 1 min.
- **Diagnostic** : quand l'assistant demande un diagnostic, taper `bash /opt/concorde/diag.sh`
  et coller la sortie complete dans la conversation.
- Le mapping reel (362 comptes) est dans `mapping_quadra_odoo.json` a la racine :
  le moteur le trouve automatiquement depuis /opt/concorde.
