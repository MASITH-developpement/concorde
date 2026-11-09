# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Sauvegarde et restauration Odoo (.zip) dans la CI, par le service officiel.

  python -m tests.integration.base_odoo sauvegarder <fichier.zip>
  python -m tests.integration.base_odoo restaurer <fichier.zip> <base>

Appelle `db.dump` et `db.restore` (même code que le gestionnaire de bases
d'Odoo) sur ODOO_URL ; base sauvegardée : ODOO_BASE ; mot de passe maître
ODOO_MAITRE (« admin » par défaut). Code 1, avec une annotation ::error::,
si Odoo refuse ou si le fichier n'est pas une sauvegarde .zip.
"""

import base64
import os
import sys
import zipfile

from core.odoo_source import transport_xmlrpc
from core.xml_sur import FauteXmlRpc, ProxyXmlRpc

DELAI_BASE_S = 900.0


def service_bases() -> ProxyXmlRpc:
    """Service XML-RPC « db » de l'Odoo de la CI."""
    url = os.environ["ODOO_URL"]
    return ProxyXmlRpc(
        url + "/xmlrpc/2/db",
        transport=transport_xmlrpc(url, DELAI_BASE_S),
        allow_none=True,
    )


def sauvegarder(chemin: str) -> None:
    """Écrit la sauvegarde .zip de ODOO_BASE dans `chemin`."""
    contenu = service_bases().dump(
        os.environ.get("ODOO_MAITRE", "admin"), os.environ["ODOO_BASE"], "zip"
    )
    with open(chemin, "wb") as fichier:
        fichier.write(base64.b64decode(str(contenu)))


def restaurer(chemin: str, base: str) -> None:
    """Restaure la sauvegarde `chemin` sous le nom `base` (copie)."""
    with open(chemin, "rb") as fichier:
        donnees = base64.b64encode(fichier.read()).decode()
    service_bases().restore(
        os.environ.get("ODOO_MAITRE", "admin"), base, donnees, True
    )


def main() -> int:
    """Lance l'action demandée ; rend le code de sortie."""
    action, chemin = sys.argv[1], sys.argv[2]
    if not (action == "sauvegarder" or zipfile.is_zipfile(chemin)):
        print("::error::%s n'est pas une sauvegarde .zip." % chemin)
        return 1
    try:
        if action == "sauvegarder":
            sauvegarder(chemin)
        else:
            restaurer(chemin, sys.argv[3])
    except FauteXmlRpc as exc:
        print("::error::Odoo refuse (%s) : %s" % (action, exc.faultString))
        return 1
    if not zipfile.is_zipfile(chemin):
        print("::error::Odoo n'a pas rendu une sauvegarde .zip.")
        return 1
    with zipfile.ZipFile(chemin) as archive:
        print(
            "%s %s : %d fichiers, %d octets."
            % (
                action,
                chemin,
                len(archive.namelist()),
                os.path.getsize(chemin),
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
