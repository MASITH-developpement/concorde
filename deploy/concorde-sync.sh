#!/bin/bash
# CONCORDE - synchronisation auto depuis GitHub (branche main), lancée par cron (root).
# Installation (root) : install -m 755 deploy/concorde-sync.sh /usr/local/bin/concorde-sync.sh
# Chemins réglables par variables d'environnement (tests) ; valeurs du serveur par défaut.
# Aucun échec n'est muet : chaque passage écrit son état dans
# /var/lib/concorde-sync/etat.json (lu par l'interface), et un échec part aussi
# dans le journal système (journalctl -t concorde-sync) et dans le log.
set -u
DEPOT=${CONCORDE_DEPOT:-/opt/concorde}
JOURNAL=${CONCORDE_SYNCHRO_JOURNAL:-/var/log/concorde-sync.log}
DOSSIER_ETAT=${CONCORDE_SYNCHRO_DOSSIER:-/var/lib/concorde-sync}
ETAT="$DOSSIER_ETAT/etat.json"

ecrire_etat() {  # $1 statut (ok|echec), $2 étape, $3 message
    mkdir -p "$DOSSIER_ETAT" && chmod 755 "$DOSSIER_ETAT"
    local tmp
    tmp=$(mktemp "$DOSSIER_ETAT/.etat.XXXXXX") || return 1
    python3 - "$1" "$2" "$3" "$(git -C "$DEPOT" rev-parse HEAD 2>/dev/null)" > "$tmp" <<'PY'
import json, sys
from datetime import datetime
statut, etape, message, head = sys.argv[1:5]
print(json.dumps({"date": datetime.now().isoformat(timespec="seconds"),
                  "statut": statut, "etape": etape, "message": message[-500:],
                  "head": head}, ensure_ascii=False))
PY
    chmod 644 "$tmp" && mv -f "$tmp" "$ETAT"
}

echec() {  # $1 étape, $2 message
    echo "$(date) - ECHEC $1 : $2" >> "$JOURNAL"
    logger -p user.err -t concorde-sync "ECHEC $1 : $2"
    ecrire_etat echec "$1" "$2"
    exit 1
}

cd "$DEPOT" || echec depot "dépôt $DEPOT introuvable"
sortie=$(git fetch origin main 2>&1) || echec fetch "$sortie"
LOCAL=$(git rev-parse HEAD) || echec rev-parse "HEAD illisible"
REMOTE=$(git rev-parse origin/main) || echec rev-parse "origin/main illisible"
if [ "$LOCAL" != "$REMOTE" ]; then
    sortie=$(git reset --hard origin/main 2>&1) || echec reset "$sortie"
    echo "$sortie" >> "$JOURNAL"
    if [ -f "$DEPOT/deploy/docker-compose.yml" ]; then
        sortie=$(cd "$DEPOT/deploy" && docker compose up -d --force-recreate 2>&1) \
            || echec docker "$sortie"
        echo "$sortie" >> "$JOURNAL"
    fi
    echo "$(date) - sync vers $REMOTE" >> "$JOURNAL"
fi
ecrire_etat ok synchro "à jour sur $REMOTE" || {
    logger -p user.err -t concorde-sync "ECHEC etat : $ETAT non écrit"
    echo "$(date) - ECHEC etat : $ETAT non écrit" >> "$JOURNAL"
    exit 1
}
