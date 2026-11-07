# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""INJECTEUR ODOO 18 COMMUNITY — XML-RPC, mode dry-run par défaut.

Cible : Odoo 18 Community (account.move / account.move.line via XML-RPC v2).
Compatible : le même payload fonctionne en Odoo 17 (schéma account.move
identique entre 17 et 18) ; la logique commune est dans
injectors/socle_odoo.py.

Sécurités CONCORDE respectées :
- Montants en centimes int jusqu'à la frontière Odoo (jamais de float)
- Idempotence : ref = "CONCORDE/<journal>/<ecriture>" ; jamais de doublon
- Equilibre tolérance 0,00 EUR vérifié AVANT toute injection
- Mode dry-run par défaut : rien n'est écrit dans Odoo sans dry_run=False
- Guardian : l'injecteur refuse de tourner sans self-check OK
"""

from injectors.socle_odoo import ErreurInjecteur, InjecteurOdoo

__all__ = ["ErreurInjecteur", "InjecteurOdoo18"]


class InjecteurOdoo18(InjecteurOdoo):
    """Injecte le journal canonique CONCORDE dans Odoo 18 Community."""

    VERSION_CIBLE = "18"
    CODE_TRACE = "odoo18"
