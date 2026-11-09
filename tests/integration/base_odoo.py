# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Sauvegardes Odoo (.zip) dans la CI : fabriquer, restaurer.

  python -m tests.integration.base_odoo emballer <dossier> <fichier.zip> \
      <version Odoo> <version PostgreSQL>
  python -m tests.integration.base_odoo restaurer <fichier.zip> <base>

`emballer` fait la sauvegarde du « client » au format d'Odoo (dump_db :
dump.sql de `pg_dump --no-owner`, filestore/, manifest.json) à partir de
<dossier>/dump.sql et <dossier>/filestore. Le service db.dump de l'image
Odoo 14 échoue dans la CI (son pg_dump interne rend « error 1 » alors que
le même pg_dump lancé à la main réussit) : la CI fabrique donc le fichier
elle-même, au même format.
`restaurer` appelle `db.restore` (même code que le gestionnaire de bases)
sur ODOO_URL, mot de passe maître ODOO_MAITRE (« admin » par défaut).
Code 1, avec une annotation ::error::, si Odoo refuse.
"""

import base64
import os
import sys
import zipfile

from core.montee_version.sauvegarde import ecrire_sauvegarde
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


def emballer(dossier: str, chemin: str, version: str, pg_version: str) -> None:
    """Sauvegarde .zip au format d'Odoo (dump et pièces jointes)."""
    ecrire_sauvegarde(
        chemin,
        os.path.join(dossier, "dump.sql"),
        os.path.join(dossier, "filestore"),
        {
            "odoo_dump": "1",
            "db_name": os.environ["ODOO_BASE"],
            "version": version,
            "major_version": version,
            "pg_version": pg_version,
        },
    )


def restaurer(chemin: str, base: str) -> None:
    """Restaure la sauvegarde `chemin` sous le nom `base` (copie)."""
    with open(chemin, "rb") as fichier:
        donnees = base64.b64encode(fichier.read()).decode()
    service_bases().restore(
        os.environ.get("ODOO_MAITRE", "admin"), base, donnees, True
    )


def main() -> int:
    """Lance l'action demandée ; rend le code de sortie."""
    action = sys.argv[1]
    if action == "emballer":
        emballer(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        chemin = sys.argv[3]
    else:
        chemin = sys.argv[2]
        if not zipfile.is_zipfile(chemin):
            print("::error::%s n'est pas une sauvegarde .zip." % chemin)
            return 1
    try:
        if action == "restaurer":
            restaurer(chemin, sys.argv[3])
    except FauteXmlRpc as exc:
        cause = [ligne for ligne in str(exc.faultString).splitlines() if ligne]
        for ligne in cause[-4:]:
            print("::error::Odoo refuse (%s) : %s" % (action, ligne))
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
