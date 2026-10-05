#!/bin/bash
# CONCORDE — derivation des addons par version Odoo (18/19/20) a partir de la source 17
# La source de verite reste deploy/addons/concorde (genere par install_module.sh)
set -e
cd /opt/concorde/deploy
SRC=addons/concorde
[ -d "$SRC" ] || { echo "ERREUR : $SRC absent ; lancez d'abord scripts/install_module.sh"; exit 1; }
derive() {
  VER=$1   # ex. 19
  DST=addons$VER/concorde
  rm -rf "$DST"
  mkdir -p addons$VER
  cp -r "$SRC" "$DST"
  # 1) version du manifest pour la serie cible
  sed -i "s/'version': *'17\.0\.[0-9.]*/'version': '$VER.0.1.0'/" "$DST/__manifest__.py"
  sed -i "s/\"version\": *\"17\.0\.[0-9.]*/\"version\": \"$VER.0.1.0\/" "$DST/__manifest__.py"
  # 2) vues : <tree> devient <list> a partir d'Odoo 19
  if [ "$VER" -ge 19 ]; then
    sed -i 's/<tree>/<list>/g; s<\/tree><</list><g' "$DST/views/concorde_views.xml" 2>/dev/null || true
    sed -i 's#</tree>#</list>#g' "$DST/views/concorde_views.xml" 2>/dev/null || true
  fi
  echo "OK addons$VER/concorde (version $VER.0.1.0)"
}
derive 18
derive 19
derive 20
echo "=== ADDONS PAR VERSION GENERES ==="
