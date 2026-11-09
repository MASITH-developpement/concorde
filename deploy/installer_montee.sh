#!/bin/bash
# CONCORDE — mise en place du service de montée (ADR-0012). À lancer en root :
#   sudo bash /opt/concorde/deploy/installer_montee.sh
# Refait sans risque : rien n'est écrasé (la clé du volume n'est créée
# qu'une fois ; la perdre rend les montées en cours illisibles).
set -euo pipefail

DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-psycopg2 cryptsetup >/dev/null

install -d -o root -g root -m 711 /var/lib/concorde-montee
install -d -o root -g root -m 755 /var/lib/concorde-montee/etats
install -d -o root -g root -m 700 /etc/concorde/montee
if [ ! -f /etc/concorde/montee/cle ]; then
  umask 077
  head -c 64 /dev/urandom > /etc/concorde/montee/cle
  echo "Clé du volume chiffré créée : /etc/concorde/montee/cle (à sauvegarder hors du serveur)."
fi
chmod 600 /etc/concorde/montee/cle

install -o root -g root -m 644 /opt/concorde/deploy/concorde-montee.service \
  /etc/systemd/system/concorde-montee.service
install -o root -g root -m 644 /opt/concorde/deploy/concorde-interface.service \
  /etc/systemd/system/concorde-interface.service
systemctl daemon-reload
systemctl enable --now concorde-montee
# La première ouverture crée le volume (clé dérivée lentement, exprès) :
# attendre qu'il soit monté, 5 minutes au plus.
for essai in $(seq 1 100); do
  if mountpoint -q /var/lib/concorde-montee/donnees; then
    break
  fi
  sleep 3
done
if ! mountpoint -q /var/lib/concorde-montee/donnees; then
  echo "Volume chiffré non monté : journalctl -u concorde-montee" >&2
  exit 1
fi
# Le dossier monté doit être traversable par l'interface (sans pouvoir le lister).
chmod 711 /var/lib/concorde-montee/donnees
systemctl restart concorde-interface
systemctl --no-pager --lines=5 status concorde-montee
