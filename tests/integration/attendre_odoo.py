# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Attend qu'un Odoo démarré par la CI réponde (variable ODOO_URL).

  python -m tests.integration.attendre_odoo

Code 0 dès que /web/login répond ; sinon code 1 après 60 essais (3 s),
avec une annotation ::error:: pour la CI.
"""

import http.client
import os
import sys
import time
from urllib.parse import urlsplit

ESSAIS_ODOO = 60
PAUSE_S = 3.0


def odoo_repond(url: str) -> bool:
    """Vrai si la page de connexion d'Odoo répond (code < 400).

    Seulement en http vers l'Odoo local de la CI (ODOO_URL).
    """
    adresse = urlsplit(url)
    connexion = http.client.HTTPConnection(
        adresse.hostname or "127.0.0.1", adresse.port or 80, timeout=5
    )
    try:
        connexion.request("GET", "/web/login")
        return connexion.getresponse().status < 400
    except OSError:
        return False
    finally:
        connexion.close()


def main() -> int:
    """Attend l'Odoo de ODOO_URL ; rend le code de sortie."""
    url = os.environ["ODOO_URL"]
    for essai in range(1, ESSAIS_ODOO + 1):
        if odoo_repond(url):
            print("Odoo prêt après %d essai(s)." % essai)
            return 0
        time.sleep(PAUSE_S)
    print("::error::Odoo ne répond pas sur %s." % url)
    return 1


if __name__ == "__main__":
    sys.exit(main())
