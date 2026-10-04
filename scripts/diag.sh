#!/bin/bash
# CONCORDE - diagnostic v2 : introspection adaptee a la structure reelle
echo "=== GIT ==="; cd /opt/concorde && git log --oneline -3 2>&1
echo "=== DOCKER ==="; docker ps --format "table {{.Names}}	{{.Status}}" 2>&1
echo "=== TEST PIPELINE (FEC synthetique) ==="
cd /opt/concorde
python3 samples/generateur_fec_test.py /tmp/fec_test.txt >/dev/null 2>&1
python3 -c "
import json
from core.moteur import MoteurConcorde
from core.yaml_min import charger_yaml
try:
    moteur = MoteurConcorde(config=charger_yaml('concorde.yaml'))
    ctx = moteur.executer(open('/tmp/fec_test.txt','rb').read())
    print('--- cles du contexte:', list(ctx.keys()))
    res = ctx.get('resultats', [])
    print('--- nb resultats:', len(res))
    for i, r in enumerate(res):
        if isinstance(r, dict):
            nom = r.get('nom') or r.get('etape') or r.get('module') or ('resultat_%d' % i)
            err = r.get('erreur')
            print('ETAPE:', nom, '| erreur:', repr(err) if err else 'OK')
        else:
            print('RESULTAT', i, ':', type(r).__name__, repr(r)[:200])
except Exception as e:
    import traceback; traceback.print_exc()
" 2>&1
echo "=== FIN DIAG ==="
