# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Assistant d'import FEC CONCORDE pour Odoo 17.

Pipeline complet embarqué : FEC -> équilibre -> mapping -> lettrage -> rapport.
Guardian : self-check bloquant, audit chaîné SHA-256. Marceau : jamais muet.
Idempotence : une écriture FEC déjà importée (réf. FEC journal-écriture)
n'est jamais réimportée. Compte Odoo absent = blocage (aucun compte deviné).
"""
import base64
import os
from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from odoo.addons.concorde.engine.moteur import MoteurConcorde


def _chemin_engine():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine')


class ConcordeImportWizard(models.TransientModel):
    _name = 'concorde.import.wizard'
    _description = "Assistant d'import FEC CONCORDE"

    fec_file = fields.Binary(string="Fichier FEC (Quadra)", required=True)
    fec_filename = fields.Char(string="Nom du fichier")
    dry_run = fields.Boolean(
        string="Mode simulation (dry-run)",
        default=True,
        help="Analyse complète du FEC sans créer d'écritures dans Odoo. "
             "CONCORDE est idempotent : même hors dry-run, un import déjà "
             "effectué n'est jamais dupliqué.")
    journal_id = fields.Many2one(
        'account.journal', string="Journal Odoo par défaut", required=True,
        domain=[('type', '=', 'general')])

    def _default_journal(self):
        journal = self.env['account.journal'].search([('code', '=', 'CONCORDE')], limit=1)
        if not journal:
            journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        return journal

    _defaults = {}

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'journal_id' in fields_list and not vals.get('journal_id'):
            vals['journal_id'] = self._default_journal().id
        return vals

    def _config_moteur(self):
        return {
            'noyau': {'guardian': {'journal': '/var/concorde/guardian'}},
            'pipeline': [
                {'nom': 'importer_fec',
                 'module': 'odoo.addons.concorde.engine.fec_parser',
                 'fonction': 'parse_fec'},
                {'nom': 'verifier_equilibre', 'fonction': 'verifier_equilibre'},
                {'nom': 'mapper_comptes', 'fonction': 'mapper_comptes'},
                {'nom': 'lettrer',
                 'module': 'odoo.addons.concorde.engine.lettrage',
                 'fonction': 'lettrer'},
                {'nom': 'rapport', 'fonction': 'rapport'},
            ],
            'mapping': {'fichier': os.path.join(_chemin_engine(), 'mapping_quadra_odoo.json')},
        }

    def _grouper_ecritures(self, canon):
        ecritures = OrderedDict()
        for l in canon.lignes:
            cle = (l.journal_code, l.ecriture_num)
            ecritures.setdefault(cle, []).append(l)
        return ecritures

    def _html_erreur(self, exc):
        return ('<p><b>Échec du pipeline CONCORDE — aucun import effectué.</b></p>'
                '<p>Erreur : %s</p>' % html_escape('%s: %s' % (type(exc).__name__, exc)))

    def _html_rapport(self, resultats, contexte):
        lignes = ['<p><b>Pipeline CONCORDE</b> — Guardian : %s</p>' % (
            'audit validé' if contexte.get('audit_valide') else 'ALERTE : chaîne d'audit invalide')]
        lignes.append('<ul>')
        for r in resultats:
            nom = html_escape(r.get('etape', '?'))
            marceau = html_escape(r.get('marceau', ''))
            lignes.append('<li><b>%s</b> — %s</li>' % (nom, marceau))
        lignes.append('</ul>')
        empreinte = contexte.get('empreinte_guardian', '')
        lignes.append('<p style="color:#888;">Empreinte Guardian : %s</p>' % html_escape(empreinte))
        return ''.join(lignes)

    def _retour_fiche(self, record):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'concorde.import',
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_importer(self):
        self.ensure_one()
        brut = base64.b64decode(self.fec_file)
        moteur = MoteurConcorde(config=self._config_moteur())
        try:
            contexte = moteur.executer(brut)
        except Exception as exc:
            record = self.env['concorde.import'].create({
                'name': self.fec_filename or 'FEC',
                'fec_filename': self.fec_filename,
                'fec_file': self.fec_file,
                'state': 'erreur',
                'rapport_html': self._html_erreur(exc),
            })
            return self._retour_fiche(record)

        resultats = contexte['resultats']
        stats = resultats[4]['resultat'].get('stats', {}) if resultats else {}
        canon = resultats[2]['resultat']['canon']
        record = self.env['concorde.import'].create({
            'name': self.fec_filename or 'FEC',
            'fec_filename': self.fec_filename,
            'fec_file': self.fec_file,
            'journal_id': self.journal_id.id,
            'state': 'analyse_ok',
            'nb_lignes': stats.get('nb_lignes', 0),
            'nb_paires': stats.get('nb_paires', 0),
            'nb_anomalies': stats.get('nb_anomalies', 0),
            'total_debit': stats.get('total_debit', 0) / 100.0,
            'total_credit': stats.get('total_credit', 0) / 100.0,
            'empreinte_guardian': contexte.get('empreinte_guardian', ''),
            'rapport_html': self._html_rapport(resultats, contexte),
        })

        ecritures = self._grouper_ecritures(canon)
        comptes = sorted({l.compte for lignes in ecritures.values() for l in lignes})
        Account = self.env['account.account']
        par_code = {}
        manquants = []
        for code in comptes:
            acct = Account.search([
                ('code', '=', code),
                ('company_id', '=', self.env.company.id)], limit=1)
            if acct:
                par_code[code] = acct
            else:
                manquants.append(code)
        if manquants:
            record.comptes_manquants = ', '.join(manquants)
        record.nb_ecritures = len(ecritures)

        if manquants and not self.dry_run:
            raise UserError(_(
                "Comptes Odoo absents — CONCORDE ne devine jamais un compte : %s") %
                ', '.join(manquants[:30]))

        nb_creees = 0
        if not self.dry_run:
            Move = self.env['account.move']
            Journal = self.env['account.journal']
            for (jcode, enum), lignes in ecritures.items():
                journal = Journal.search([('code', '=', jcode)], limit=1) or self.journal_id
                ref = 'FEC %s-%s' % (jcode, enum)
                if Move.search_count([('ref', '=', ref), ('journal_id', '=', journal.id)]):
                    continue  # idempotence : déjà importée
                vals_lines = []
                for l in lignes:
                    if l.debit == 0 and l.credit == 0:
                        continue
                    vals_lines.append((0, 0, {
                        'name': (l.libelle or 'CONCORDE')[:200],
                        'account_id': par_code[l.compte].id,
                        'debit': l.debit / 100.0,
                        'credit': l.credit / 100.0,
                    }))
                if vals_lines:
                    Move.create({
                        'journal_id': journal.id,
                        'date': l.date_ecriture,
                        'ref': ref,
                        'concorde_import_id': record.id,
                        'line_ids': vals_lines,
                    })
                    nb_creees += 1
            record.write({'state': 'importe', 'nb_ecritures': nb_creees})
        return self._retour_fiche(record)
