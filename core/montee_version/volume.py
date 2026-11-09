# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Volume chiffré des montées (ADR-0012, point 3).

Un conteneur LUKS dans un fichier creux : il ne prend sur le disque que
ce qui y est écrit. Il est ouvert et monté par le service de montée
(root) avec une clé lisible par lui seul ; l'interface n'en connaît que
deux sous-dossiers (dépôts et demandes). Sans clé, le fichier n'est
qu'une suite d'octets illisibles.
"""

import os
from collections.abc import Callable

from .commandes import executer

NOM_VOLUME = "concorde-montee"
CHEMIN_IMAGE = os.environ.get(
    "CONCORDE_MONTEE_IMAGE", "/var/lib/concorde-montee/volume.luks"
)
CHEMIN_MONTAGE = os.environ.get(
    "CONCORDE_MONTEE_DONNEES", "/var/lib/concorde-montee/donnees"
)
CHEMIN_CLE = os.environ.get("CONCORDE_MONTEE_CLE", "/etc/concorde/montee/cle")
TAILLE_VOLUME = os.environ.get("CONCORDE_MONTEE_VOLUME", "60G")


class ErreurVolume(RuntimeError):
    """Volume chiffré impossible à ouvrir ou clé mal protégée."""


def verifier_cle(chemin: str) -> None:
    """Refuse une clé absente ou lisible par d'autres que root.

    Rôle : la clé du volume ne doit jamais être lisible par l'interface.
    Paramètres : chemin — fichier de la clé.
    Retour : aucun.
    Erreurs : ErreurVolume (absente, droits trop ouverts, propriétaire
    autre que root).
    Usages : ouvrir_volume.
    """
    if not os.path.isfile(chemin):
        raise ErreurVolume(
            "Clé du volume absente : %s (deploy/installer_montee.sh)." % chemin
        )
    infos = os.stat(chemin)
    if infos.st_mode & 0o077 or infos.st_uid != 0:
        raise ErreurVolume(
            "Clé du volume mal protégée (%s) : root seul, droits 600." % chemin
        )


def ouvrir_volume(
    image: str = CHEMIN_IMAGE,
    montage: str = CHEMIN_MONTAGE,
    cle: str = CHEMIN_CLE,
    taille: str = TAILLE_VOLUME,
    lanceur: Callable[[list[str]], str] = executer,
) -> str:
    """Crée au besoin, ouvre et monte le volume chiffré ; rend le montage.

    Rôle : toutes les données des clients sont écrites chiffrées.
    Paramètres : image — fichier du conteneur LUKS (créé creux à la
    première ouverture) ; montage — dossier où le monter ; cle — fichier
    de la clé ; taille — taille maximale (ex. « 60G ») ; lanceur.
    Retour : le dossier monté.
    Erreurs : ErreurVolume (clé) ; ErreurCommande (cryptsetup, mkfs,
    mount en échec).
    Usages : scripts/concorde_montee_service.py.
    """
    verifier_cle(cle)
    peripherique = "/dev/mapper/" + NOM_VOLUME
    neuf = not os.path.isfile(image)
    if neuf:
        os.makedirs(os.path.dirname(image), mode=0o700, exist_ok=True)
        lanceur(["truncate", "-s", taille, image])
        lanceur(
            [
                "cryptsetup",
                "luksFormat",
                "--batch-mode",
                "--key-file",
                cle,
                image,
            ]
        )
    if not os.path.exists(peripherique):
        lanceur(["cryptsetup", "open", "--key-file", cle, image, NOM_VOLUME])
    if neuf:
        lanceur(["mkfs.ext4", "-q", "-L", NOM_VOLUME, peripherique])
    os.makedirs(montage, mode=0o700, exist_ok=True)
    if not os.path.ismount(montage):
        lanceur(["mount", peripherique, montage])
    return montage


def fermer_volume(
    montage: str = CHEMIN_MONTAGE,
    lanceur: Callable[[list[str]], str] = executer,
) -> None:
    """Démonte et referme le volume (arrêt du service)."""
    if os.path.ismount(montage):
        lanceur(["umount", montage])
    if os.path.exists("/dev/mapper/" + NOM_VOLUME):
        lanceur(["cryptsetup", "close", NOM_VOLUME])
