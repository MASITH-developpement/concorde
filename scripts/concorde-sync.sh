#!/bin/bash
# CONCORDE - synchronisation auto depuis GitHub (branche main)
cd /opt/concorde || exit 1
git fetch origin main || exit 0
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  git reset --hard origin/main >> /var/log/concorde-sync.log 2>&1
  if [ -f /opt/concorde/deploy/docker-compose.yml ]; then
    cd /opt/concorde/deploy && docker compose up -d --force-recreate >> /var/log/concorde-sync.log 2>&1
  fi
  echo "$(date) - sync vers $REMOTE" >> /var/log/concorde-sync.log
fi
