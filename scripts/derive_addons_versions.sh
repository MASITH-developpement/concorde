#!/bin/bash
# CONCORDE — derivation des addons par version Odoo (18/19/20) depuis la source 17
# La source de verite reste deploy/addons/concorde (genere par install_module.sh)
set -e
cd /opt/concorde/deploy
SRC=addons/concorde
[ -d "$SRC" ] || { echo "ERREUR : $SRC absent ; lancez d'abord scripts/install_module.sh"; exit 1; }
python3 - <<'PYEOF'
import re, shutil, os
SRC = 'addons/concorde'
for ver in ('18', '19', '20'):
    dst = 'addons%s/concorde' % ver
    if os.path.isdir('addons' + ver):
        shutil.rmtree('addons' + ver)
    shutil.copytree(SRC, dst)
    mp = os.path.join(dst, '__manifest__.py')
    txt = open(mp, encoding='utf-8').read()
    txt = re.sub(r"""(['"]version['"]?\s*[:=]\s*['"])17\.0\.""",
                 lambda m: m.group(1) + ver + '.0.', txt)
    # Libelles de version : chaque module derive vise SA version d'Odoo
    txt = txt.replace('vers Odoo 17', 'vers Odoo %s' % ver)
    txt = txt.replace('pour Odoo 17', 'pour Odoo %s' % ver)
    for q in ("'", '"'):
        for old in ('17.0.1.0', '17.0.1.0.0'):
            txt = txt.replace(q + old + q, q + ver + '.0.1.0' + q)
    # --- vues : Odoo 18+ : <tree> devient <list> ; sous-liste move_ids -> vue par defaut
    vp = os.path.join(dst, 'views', 'concorde_views.xml')
    if os.path.isfile(vp):
        v = open(vp, encoding='utf-8').read()
        v = re.sub(r'<field name="move_ids">.*?</field>', '<field name="move_ids"/>', v, flags=re.S)
        v = v.replace('<tree>', '<list>').replace('</tree>', '</list>')
        open(vp, 'w', encoding='utf-8').write(v)
    wp = os.path.join(dst, 'wizard', 'concorde_import_wizard.py')
    if os.path.isfile(wp):
        w = open(wp, encoding='utf-8').read()
        w = w.replace('pour Odoo 17', 'pour Odoo %s' % ver)
        open(wp, 'w', encoding='utf-8').write(w)
    # --- Odoo 20 : ir.model.access devient ir.access ; operation 'crud' = r+u+c+d
    if ver == '20':
        sp = os.path.join(dst, 'security', 'ir.model.access.csv')
        if os.path.isfile(sp):
            raw = open(sp, encoding='utf-8').read().splitlines()
            header = raw[0].split(',')
            i_id = header.index('id')
            i_name = header.index('name')
            i_model = header.index('model_id:id')
            i_group = header.index('group_id:id') if 'group_id:id' in header else None
            out = ['id,name,model_id:id,group_id:id,operation']
            for line in raw[1:]:
                if not line.strip():
                    continue
                parts = line.split(',')
                aid, name, model = parts[i_id], parts[i_name], parts[i_model]
                group = parts[i_group] if i_group is not None else ''
                out.append('%s,%s,%s,%s,crud' % (aid, name, model, group))
            c = '\n'.join(out) + '\n'
            open(os.path.join(dst, 'security', 'ir.access.csv'), 'w', encoding='utf-8').write(c)
            os.remove(sp)
        txt = txt.replace('security/ir.model.access.csv', 'security/ir.access.csv')
    open(mp, 'w', encoding='utf-8').write(txt)
    ok = (ver + '.0.1.') in txt
    print('OK addons%s/concorde (manifest %s.0.1.x : %s)' % (ver, ver, ok))
PYEOF
echo "=== ADDONS PAR VERSION GENERES ==="
