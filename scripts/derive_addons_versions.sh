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
    txt = re.sub("(['\"]version['\"]?\\s*[:=]\\s*['\"])[0-9]+\\.0\\.[0-9.]+",
                 lambda m: m.group(1) + ver + '.0.1.0', txt)
    for q in ("'", '"'):
        for old in ('17.0.1.0', '17.0.1.0.0'):
            txt = txt.replace(q + old + q, q + ver + '.0.1.0' + q)
    # --- Odoo 18+ : validation stricte des sous-listes imbriquees -> vue par defaut pour move_ids
    vp = os.path.join(dst, 'views', 'concorde_views.xml')
    v = open(vp, encoding='utf-8').read()
    v = re.sub(r'<field name="move_ids">.*?</field>', '<field name="move_ids"/>', v, flags=re.S)
    # --- Odoo 19+ : <tree> devient <list>
    if int(ver) >= 19:
        v = v.replace('<tree>', '<list>').replace('</tree>', '</list>')
    open(vp, 'w', encoding='utf-8').write(v)
    # --- Odoo 20 : ir.model.access devient ir.access (fichier ET manifest)
    if ver == '20':
        sp = os.path.join(dst, 'security', 'ir.model.access.csv')
        if os.path.isfile(sp):
            c = open(sp, encoding='utf-8').read().replace('ir.model.access', 'ir.access')
            open(os.path.join(dst, 'security', 'ir.access.csv'), 'w', encoding='utf-8').write(c)
            os.remove(sp)
        txt = txt.replace('security/ir.model.access.csv', 'security/ir.access.csv')
    open(mp, 'w', encoding='utf-8').write(txt)
    ok = (ver + '.0.1.0') in txt
    print('OK addons%s/concorde (manifest %s.0.1.0 : %s)' % (ver, ver, ok))
PYEOF
echo "=== ADDONS PAR VERSION GENERES ==="
