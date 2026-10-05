# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
from odoo import fields, models


class ConcordeImport(models.Model):
    _name = 'concorde.import'
    _description = "Import FEC CONCORDE"
    _order = 'id desc'

    name = fields.Char(string="Import", required=True)
    fec_filename = fields.Char(string="Nom du fichier FEC")
    fec_file = fields.Binary(string="Fichier FEC", attachment=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('analyse_ok', 'Analysé'),
        ('importe', 'Importé dans Odoo'),
        ('erreur', 'Erreur'),
    ], string="État", default='draft')
    journal_id = fields.Many2one('account.journal', string="Journal par défaut")
    nb_lignes = fields.Integer(string="Lignes importées")
    nb_ecritures = fields.Integer(string="Écritures")
    nb_paires = fields.Integer(string="Paires lettrées")
    nb_anomalies = fields.Integer(string="Anomalies de lettrage")
    total_debit = fields.Float(string="Total débit")
    total_credit = fields.Float(string="Total crédit")
    empreinte_guardian = fields.Char(string="Empreinte Guardian (SHA-256)")
    mapping_source = fields.Char(string="Mapping des comptes (source)")
    comptes_manquants = fields.Text(string="Comptes Odoo manquants")
    rapport_html = fields.Html(string="Rapport pipeline", sanitize=False)
    move_ids = fields.One2many('account.move', 'concorde_import_id', string="Écritures créées")


class AccountMove(models.Model):
    _inherit = 'account.move'

    concorde_import_id = fields.Many2one('concorde.import', string="Import CONCORDE", index=True, copy=False)
