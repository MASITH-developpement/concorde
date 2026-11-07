# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Contrôle de la dématérialisation des factures — application Odoo.

Le moteur (engine/demat.py, copie fidèle de core/demat.py) est le même que
celui du script scripts/check_dematerialisation.py. Lecture seule : le
contrôle n'écrit que son propre rapport (concorde.demat.controle).
"""
import json

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.concorde.engine.demat import ControleDemat, rendu_html


class SourceEnv:
    """Source « interne » du moteur demat : l'ORM, avec les droits de l'utilisateur."""

    def __init__(self, env):
        self.env = env

    def champs(self, modele):
        if modele not in self.env:
            return {}
        try:
            return self.env[modele].fields_get(attributes=['type'])
        except AccessError:
            return {}

    def lire(self, modele, domaine, champs, offset=0, limit=None, ordre='id'):
        return self.env[modele].search_read(
            domaine, list(champs), offset=offset, limit=limit, order=ordre)

    def modules_installes(self, noms):
        try:
            mods = self.env['ir.module.module'].search_read(
                [('name', 'in', list(noms)), ('state', '=', 'installed')], ['name'])
        except AccessError:
            return None
        return {m['name'] for m in mods}


class ConcordeDematControle(models.Model):
    _name = 'concorde.demat.controle'
    _description = "Contrôle de la dématérialisation des factures"
    _order = 'id desc'

    name = fields.Char(string="Contrôle", required=True,
                       default=lambda self: _("Contrôle du %s") % fields.Date.today())
    date_controle = fields.Datetime(string="Exécuté le", readonly=True)
    jours = fields.Integer(string="Fenêtre (jours)", default=30, required=True)
    inspecter_pdf = fields.Boolean(
        string="Inspecter les PDF (Factur-X embarqué)", default=True,
        help="Ouvre les PDF des factures sans XML séparé pour y chercher le "
             "Factur-X embarqué. Plus lent, mais évite de sous-estimer le taux.")
    state = fields.Selection([
        ('draft', 'Non exécuté'),
        ('conforme', 'Conforme'),
        ('a_verifier', 'À vérifier'),
        ('non_conforme', 'Non conforme'),
    ], string="Résultat", default='draft', readonly=True)
    nb_bloquants = fields.Integer(string="Bloquants", readonly=True)
    nb_alertes = fields.Integer(string="Alertes", readonly=True)
    nb_infos = fields.Integer(string="Informations", readonly=True)
    emission_total = fields.Integer(string="Factures émises", readonly=True)
    emission_avec_xml = fields.Integer(string="Émises avec XML", readonly=True)
    reception_total = fields.Integer(string="Factures reçues", readonly=True)
    reception_avec_xml = fields.Integer(string="Reçues avec XML", readonly=True)
    taux_reception = fields.Char(string="Taux de réception électronique", readonly=True)
    empreinte = fields.Char(string="Empreinte SHA-256", readonly=True)
    rapport_html = fields.Html(string="Rapport", sanitize=False, readonly=True)
    rapport_json = fields.Text(string="Rapport (JSON)", readonly=True)

    def action_lancer(self):
        for rec in self:
            if rec.jours < 1:
                raise UserError(_("La fenêtre d'analyse doit être d'au moins 1 jour."))
            try:
                d = ControleDemat(SourceEnv(self.env), jours=rec.jours,
                                  inspecter_pdf=rec.inspecter_pdf).executer().en_dict()
            except RuntimeError as exc:
                raise UserError(str(exc))
            infos = d['infos']
            rec.write({
                'date_controle': fields.Datetime.now(),
                'state': d['statut'],
                'nb_bloquants': d['bloquants'],
                'nb_alertes': d['alertes'],
                'nb_infos': d['infos_anomalies'],
                'emission_total': infos.get('emission_total', 0),
                'emission_avec_xml': infos.get('emission_avec_xml', 0),
                'reception_total': infos.get('reception_total', 0),
                'reception_avec_xml': infos.get('reception_avec_xml', 0),
                'taux_reception': infos.get('reception_taux_electronique', ''),
                'empreinte': d['empreinte'],
                'rapport_html': rendu_html(d),
                'rapport_json': json.dumps(d, ensure_ascii=False, indent=2, default=str),
            })
        return True
