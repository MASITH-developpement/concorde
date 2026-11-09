#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Service de montée de version (ADR-0012), lancé par systemd en root.

  python3 -m scripts.concorde_montee_service

Ouvre le volume chiffré, donne à l'interface ses deux dossiers (dépôts et
demandes) et le dossier des livraisons, puis traite la file de demandes
toutes les 5 secondes, une à la fois. Une fois par jour : effacement des
montées de plus de 30 jours. Variables : CONCORDE_UI_UTILISATEUR (compte
de l'interface, « ubuntu » par défaut), CONCORDE_MONTEE_ETATS (résumés
lisibles par l'interface), et celles de core/montee_version/volume.py.
"""

import os
import pwd
import signal
import sys
import time
from types import FrameType

from core.journal import Journal
from core.montee_version.commandes import ErreurCommande
from core.montee_version.demandes import Service
from core.montee_version.volume import (
    ErreurVolume,
    fermer_volume,
    ouvrir_volume,
)
from scripts.outils_cli import afficher_evenement

PAUSE_FILE_S = 5.0
PURGE_S = 24 * 3600.0
CHEMIN_ETATS = os.environ.get(
    "CONCORDE_MONTEE_ETATS", "/var/lib/concorde-montee/etats"
)
DOSSIERS_INTERFACE = ("depots", "demandes", "livraisons")


def preparer_dossiers(donnees: str, utilisateur: str) -> tuple[int, int]:
    """Dossiers de l'interface dans le volume : à elle seule, en 700.

    Rend (uid, gid) du compte de l'interface.
    """
    compte = pwd.getpwnam(utilisateur)
    for nom in DOSSIERS_INTERFACE:
        dossier = os.path.join(donnees, nom)
        os.makedirs(dossier, mode=0o700, exist_ok=True)
        os.chown(dossier, compte.pw_uid, compte.pw_gid)
    os.makedirs(CHEMIN_ETATS, mode=0o755, exist_ok=True)
    return compte.pw_uid, compte.pw_gid


def main() -> int:
    """Boucle du service ; rend le code de sortie."""
    journal = Journal(ecouteur=afficher_evenement)
    try:
        donnees = ouvrir_volume()
    except (ErreurVolume, ErreurCommande, OSError) as exc:
        print("Volume chiffré indisponible : %s" % exc, file=sys.stderr)
        return 1
    proprietaire = preparer_dossiers(
        donnees, os.environ.get("CONCORDE_UI_UTILISATEUR", "ubuntu")
    )
    service = Service(donnees, CHEMIN_ETATS, proprietaire=proprietaire)
    continuer = [True]

    def arreter(signal_recu: int, cadre: FrameType | None) -> None:
        """Fin demandée par systemd : sortie après la demande en cours."""
        continuer[0] = False

    signal.signal(signal.SIGTERM, arreter)
    derniere_purge = 0.0
    journal.dire("Service de montée prêt (%s)" % donnees, "ok")
    while continuer[0]:
        if time.monotonic() - derniere_purge > PURGE_S or not derniere_purge:
            for ident in service.purger():
                journal.dire("Montée %s effacée (30 jours)" % ident, "info")
            derniere_purge = time.monotonic()
        service.traiter_file(journal)
        time.sleep(PAUSE_FILE_S)
    fermer_volume(donnees)
    return 0


if __name__ == "__main__":
    sys.exit(main())
