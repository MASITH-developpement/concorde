# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Module Odoo CONCORDE : charge les modèles et l'assistant d'import.

Les imports enregistrent les modèles auprès d'Odoo (effet de bord voulu) ;
__all__ les déclare comme l'interface publique du paquet.
"""

from . import models
from . import wizard

__all__ = ["models", "wizard"]
