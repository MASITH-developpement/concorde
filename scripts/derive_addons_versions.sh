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
    # remplacer la valeur de version, quel que soit le style de quotes
    txt = re.sub("(version['\"]?\\s*[:=]\\s*['\"])[0-9]+\\.0\\.[0-9.]+",
                 lambda m: m.group(1) + ver + '.0.1.0', txt)
    # filet de securite : remplacement litteral des deux styles
    for q in ("'", '"'):
        for old in ('17.0.1.0', '17.0.1.0.0'):
            txt = txt.replace(q + old + q, q + ver + '.0.1.0' + q)
    open(mp, 'w', encoding='utf-8').write(txt)
    ok = (ver + '.0.1.0') in txt
    if ver == '20':
        # Odoo 20 : ir.model.access devient ir.access (modele + nom de fichier)
        sp = os.path.join(dst, 'security', 'ir.model.access.csv')
        if os.path.isfile(sp):
            c = open(sp, encoding='utf-8').read()
            c = c.replace('ir.model.access', 'ir.access')
            np2 = os.path.join(dst, 'security', 'ir.access.csv')
            open(np2, 'w', encoding='utf-8').write(c)
            os.remove(sp)
    if int(ver) >= 19:
        vp = os.path.join(dst, 'views', 'concorde_views.xml')
        if os.path.isfile(vp):
            v = open(vp, encoding='utf-8').read()
            v = v.replace('<tree>', '<list>').replace('</tree>', '</list>')
            open(vp, 'w', encoding='utf-8').write(v)
    print('OK addons%s/concorde (manifest %s.0.1.0 : %s)' % (ver, ver, ok))
PYEOF
echo "=== ADDONS PAR VERSION GENERES ==="
