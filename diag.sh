#!/bin/bash
# CONCORDE - diagnostic : sorties que l'assistant demande pour corriger
echo "=== GIT ==="; cd /opt/concorde && git log --oneline -3 2>&1
echo "=== DOCKER ==="; docker ps --format "table {{.Names}}	{{.Status}}" 2>&1
echo "=== ODOO (10 dernieres lignes) ==="; docker logs concorde-odoo --tail 10 2>&1
echo "=== TEST PIPELINE (FEC synthetique) ==="
cd /opt/concorde
python3 samples/generateur_fec_test.py /tmp/fec_test.txt >/dev/null 2>&1
python3 -c "
from core.moteur import MoteurConcorde
from core.yaml_min import charger_yaml
try:
    moteur = MoteurConcorde(config=charger_yaml('concorde.yaml'))
    ctx = moteur.executer(open('/tmp/fec_test.txt','rb').read())
    for r in ctx['resultats']:
        print(r['nom'], '->', 'OK' if not r.get('erreur') else r['erreur'])
except Exception as e:
    print('ERREUR:', type(e).__name__, e)
" 2>&1
echo "=== FIN DIAG ==="
