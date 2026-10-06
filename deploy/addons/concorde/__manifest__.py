# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
{
    'name': 'CONCORDE',
    'version': '17.0.1.4.7',
    'category': 'Accounting/Accounting',
    'summary': "Passerelle de liaison comptable universelle — import FEC Quadra vers Odoo 17",
    'description': """
CONCORDE — La passerelle de liaison comptable universelle (MARQUÉ DÉPOSÉ)
=========================================================================

Import FEC Quadra dans Odoo 17 via le pipeline CONCORDE embarqué :
import FEC (idempotence, refus d'arrondi silencieux) -> équilibre
(tolérance 0,00 EUR) -> mapping Quadra/Odoo (compte inconnu = blocage)
-> lettrage -> rapport, sous surveillance Guardian (audit chaîné SHA-256,
zéro LLM) avec explication Marceau (jamais muet).

Montants en centimes (int) — jamais de float.
(c) MASITH / Stéphane Moreau. Tous droits réservés.
    """,
    'author': 'MASITH / Stéphane Moreau',
    'website': 'https://masith.fr',
    'license': 'OPL-1',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/concorde_views.xml',
    ],
    'application': True,
    'installable': True,
}
