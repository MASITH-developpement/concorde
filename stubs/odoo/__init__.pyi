"""Stub de typage minimal du paquet odoo (Odoo 17), pour mypy.

Ne couvre que ce que le module CONCORDE utilise.
"""

from odoo import api as api
from odoo import fields as fields
from odoo import models as models

def _(source: str, *args: object, **kwargs: object) -> str:
    """Traduit un texte dans la langue de l'utilisateur."""
