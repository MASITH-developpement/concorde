#!/bin/bash
# CONCORDE — installation du module Odoo 17 (a executer en root apres un git pull)
set -e
cd /opt/concorde
MODULE_DIR=deploy/addons/concorde

# Copie fidele du moteur depuis le depot local (jamais de transcription manuelle)
mkdir -p "$MODULE_DIR/engine"
cp core/*.py "$MODULE_DIR/engine/"
cp mapping_quadra_odoo.json "$MODULE_DIR/engine/"

# Installation du module dans la base concorde
cd deploy
docker compose run --rm odoo -i concorde -d concorde --without-demo=all --stop-after-init
docker compose up -d
echo "=== MODULE CONCORDE INSTALLE ==="
