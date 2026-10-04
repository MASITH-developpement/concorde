#!/bin/bash
# CONCORDE - synchronisation auto depuis GitHub (v2 - securisee)
# - ne JAMAIS ecraser .env (arrete si .env absent : deploiement manuel requis)
# - ne redemarrer les conteneurs QUE si le dossier deploy/ a change
cd /opt/concorde || exit 1
[ -f deploy/.env ] || { echo "$(date) - .env ABSENT : synchro stoppee (protection)" >> /var/log/concorde-sync.log; exit 1; }
git fetch origin main || exit 0
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  # fichiers du dossier deploy/ modifies par ce push ?
  DEPLOY_CHANGE=$(git diff --name-only "$LOCAL" "$REMOTE" -- deploy/ | wc -l)
  git reset --hard origin/main >> /var/log/concorde-sync.log 2>&1
  if [ "$DEPLOY_CHANGE" -gt 0 ]; then
    cd /opt/concorde/deploy && docker compose up -d >> /var/log/concorde-sync.log 2>&1
    echo "$(date) - sync + restart deploy (deploy/ modifie) -> $REMOTE" >> /var/log/concorde-sync.log
  else
    echo "$(date) - sync code seul (pas de restart) -> $REMOTE" >> /var/log/concorde-sync.log
  fi
fi
