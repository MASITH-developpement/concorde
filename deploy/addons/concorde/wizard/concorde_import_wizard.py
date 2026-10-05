# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Assistant d'import FEC CONCORDE pour Odoo 17.

Accepte un FEC texte Quadra OU un export d'ecritures Excel (.xlsx),
converti en FEC standard par engine.xlsx_vers_fec avant le pipeline.

Mapping des comptes : le fichier client « Mapping Quadra Odoo.xlsx » peut
etre uploadé dans l'assistant (prioritaire sur le JSON embarqué). Colonnes
attendues « Numero » et « Odoo Acct » ; erreurs explicites sinon.

Pipeline complet embarque : FEC -> equilibre -> mapping -> lettrage -> rapport.
Guardian : self-check bloquant, audit chaine SHA-256. Marceau : jamais muet.
Idempotence : une ecriture FEC deja importee (ref. FEC journal-ecriture)
n'est jamais reimportee. Compte Odoo absent = blocage (aucun compte devine).
"""
import base64
import os
from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from odoo.addons.concorde.engine.moteur import MoteurConcorde
from odoo.addons.concorde.engine.mapping import charger_mapping, charger_mapping_xlsx
from odoo.addons.concorde.engine.plan_comptable import (
    charger_plan_xlsx,
    dictionnaire_plan,
)
from odoo.addons.concorde.engine.xlsx_vers_fec import xlsx_vers_fec

# Type de compte Odoo appliqué aux comptes créés depuis le plan uploadé
# quand aucune colonne « Type » exploitable n'existe. Choix explicite et
# tracé dans le rapport (Marceau : jamais muet, jamais deviné).
TYPE_COMPTE_DEFAUT = "unaffected"

def _chemin_engine():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine')

class ConcordeImportWizard(models.TransientModel):
    _name = 'concorde.import.wizard'
    _description = "Assistant d'import FEC CONCORDE"

    fec_file = fields.Binary(
        string="Fichier FEC (Quadra) ou export Excel (.xlsx)",
        required=True)
    fec_filename = fields.Char(string="Nom du fichier")
    dry_run = fields.Boolean(
        string="Mode simulation (dry-run)",
        default=True,
        help="Analyse complete du FEC sans creer d'ecritures dans Odoo. "
             "CONCORDE est idempotent : meme hors dry-run, un import deja "
             "effectue n'est jamais duplique.")
    journal_id = fields.Many2one(
        'account.journal', string="Journal Odoo par defaut",
        domain=[('type', '=', 'general')])
    plan_file = fields.Binary(
        string="Plan comptable Odoo (.xlsx) — création des comptes manquants",
        required=False,
        help="Nouveau plan comptable : les comptes requis par l'import mais "
             "absents d'Odoo y sont lus (code + intitulé, colonne « Type » "
             "optionnelle) et CRÉÉS automatiquement. Un compte requis mais "
             "absent de ce fichier reste bloquant (aucun compte deviné). "
             "En dry-run aucun compte n'est créé : le rapport liste ce qui "
             "serait créé.")
    plan_filename = fields.Char(string="Nom du fichier du plan comptable")
    mapping_file = fields.Binary(
        string="Fichier de mapping (Mapping Quadra Odoo .xlsx)",
        required=False,
        help="Correspondances des comptes Quadra -> Odoo. Colonnes attendues : "
             "« Numéro » (compte Quadra) et « Odoo Acct » (compte Odoo cible). "
             "Prioritaire sur le mapping JSON embarqué. Un compte absent du "
             "mapping reste bloquant (aucun compte deviné).")
    mapping_filename = fields.Char(string="Nom du fichier de mapping")

    @api.model
    def _default_journal(self):
        journal = self.env['account.journal'].search(
            [('code', '=', 'CONCORDE')], limit=1)
        if not journal:
            journal = self.env['account.journal'].search(
                [('type', '=', 'general')], limit=1)
        return journal

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'journal_id' in fields_list and not vals.get('journal_id'):
            journal = self._default_journal()
            vals['journal_id'] = journal.id if journal else False
        return vals

    def _config_moteur(self, mapping_cfg=None):
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
            'mapping': mapping_cfg or self._config_mapping(),
        }

    def _config_mapping(self):
        """Mapping du pipeline : fichier uploadé (prioritaire) ou JSON embarqué.

        Le fichier client « Mapping Quadra Odoo.xlsx » est lu par le moteur
        (engine.mapping.charger_mapping_xlsx, stdlib uniquement). Toute erreur
        de lecture est explicite (Marceau : jamais muet).
        """
        if self.mapping_file:
            brut = base64.b64decode(self.mapping_file)
            mapping = charger_mapping_xlsx(
                brut, nom_fichier=self.mapping_filename or '')
            return {
                'dict': mapping,
                'libelle': "%s (%d correspondances)" % (
                    self.mapping_filename or 'mapping.xlsx', len(mapping)),
            }
        return {
            'fichier': os.path.join(
                _chemin_engine(), 'mapping_quadra_odoo.json'),
            'libelle': 'mapping_quadra_odoo.json (embarqué)',
        }

    def _grouper_ecritures(self, canon):
        ecritures = OrderedDict()
        for l in canon.lignes:
            cle = (l.journal_code, l.ecriture_num)
            ecritures.setdefault(cle, []).append(l)
        return ecritures

    def _html_erreur(self, exc):
        detail = html_escape('%s: %s' % (type(exc).__name__, exc))
        return ('<p><b>Echec du pipeline CONCORDE - aucun import effectue.</b></p>'
                '<p>Erreur : %s</p>' % detail)

    def _html_rapport(self, resultats, contexte):
        if contexte.get('audit_valide'):
            etat = 'audit valide'
        else:
            etat = "ALERTE : chaine d'audit invalide"
        lignes = ['<p><b>Pipeline CONCORDE</b> - Guardian : %s</p>' % etat]
        if contexte.get('mapping_libelle'):
            lignes.append(
                '<p>Mapping des comptes : %s</p>'
                % html_escape(contexte['mapping_libelle']))
        if contexte.get('plan_libelle'):
            lignes.append(
                '<p>Plan comptable : %s</p>'
                % html_escape(contexte['plan_libelle']))
        if contexte.get('correspondances_plan'):
            ajoutes = contexte['correspondances_plan']
            lignes.append(
                '<p>Correspondances ajoutées depuis le plan comptable '
                '(Quadra -> compte Odoo de même code, défini par le plan, '
                'aucun compte deviné) : %d (%s)</p>'
                % (len(ajoutes),
                   html_escape(', '.join(ajoutes[:30]))
                   + ('…' if len(ajoutes) > 30 else '')))
        if contexte.get('comptes_a_creer'):
            lignes.append(
                '<p>Dry-run : %d compte(s) seraient créés depuis le plan '
                'comptable : %s</p>'
                % (len(contexte['comptes_a_creer']),
                   html_escape(', '.join(contexte['comptes_a_creer'][:30]))
                   + ('…' if len(contexte['comptes_a_creer']) > 30 else '')))
        if contexte.get('comptes_crees'):
            lignes.append(
                '<p>Comptes créés depuis le plan comptable : %d (%s)</p>'
                % (len(contexte['comptes_crees']),
                   html_escape(', '.join(contexte['comptes_crees'][:30]))
                   + ('…' if len(contexte['comptes_crees']) > 30 else '')))
        if contexte.get('comptes_sans_type'):
            lignes.append(
                '<p style="color:#B06A2E;">Comptes créés sans type explicite '
                '(type par défaut « %s » appliqué, aucun type deviné) : %s</p>'
                % (TYPE_COMPTE_DEFAUT,
                   html_escape(', '.join(contexte['comptes_sans_type'][:30]))))
        lignes.append('<ul>')
        for r in resultats:
            nom = html_escape(r.get('etape', '?'))
            marceau = html_escape(r.get('marceau', ''))
            lignes.append('<li><b>%s</b> - %s</li>' % (nom, marceau))
        lignes.append('</ul>')
        empreinte = html_escape(contexte.get('empreinte_guardian', ''))
        lignes.append('<p style="color:#888;">Empreinte Guardian : %s</p>' % empreinte)
        return ''.join(lignes)

    def _retour_fiche(self, record):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'concorde.import',
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _completer_mapping_par_plan(self, brut, mapping_cfg, plan_comptes):
        """Correspondances explicites ajoutées depuis le plan uploadé.

        Pour chaque compte du fichier d'écritures absent du mapping mais
        présent dans le plan comptable uploadé, la correspondance
        Quadra -> compte Odoo de même code est ajoutée : le plan définit
        ce compte (code + intitulé lus dans le fichier), rien n'est deviné.
        Chaque ajout est tracé dans le rapport (Marceau : jamais muet).
        Les comptes absents du mapping ET du plan restent en erreur
        explicite côté moteur.
        """
        try:
            texte = brut.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise UserError(_(
                "Fichier d'écritures illisible (encodage UTF-8 attendu) : %s")
                % exc)
        if 'dict' in mapping_cfg:
            mapping = dict(mapping_cfg['dict'])
        else:
            mapping = charger_mapping(mapping_cfg['fichier'])
        ajoutes = []
        for ligne in texte.splitlines():
            parties = ligne.split('\t')
            if len(parties) < 5:
                continue
            compte = parties[4].strip()
            if not compte:
                continue
            if compte not in mapping and compte in plan_comptes:
                mapping[compte] = compte
                if compte not in ajoutes:
                    ajoutes.append(compte)
        libelle = mapping_cfg.get('libelle', 'mapping')
        if ajoutes:
            libelle += _(" + %d correspondances ajoutées depuis le plan "
                         "comptable (code identique)") % len(ajoutes)
        return {'dict': mapping, 'libelle': libelle,
                'correspondances_plan': ajoutes}

    def action_importer(self):
        self.ensure_one()
        brut = base64.b64decode(self.fec_file)
        mapping_cfg = None
        try:
            mapping_cfg = self._config_mapping()
            # Plan comptable uploadé (optionnel) : comptes {code: (nom, type)}.
            plan_comptes = None
            if self.plan_file:
                plan_brut = base64.b64decode(self.plan_file)
                plan_comptes = dictionnaire_plan(charger_plan_xlsx(
                    plan_brut, nom_fichier=self.plan_filename or ''))
            # Convertisseur Excel -> FEC : les exports d'ecritures .xlsx
            # (Quadra et assimiles) sont convertis en FEC standard avant
            # le pipeline. Erreur explicite si le classeur est illisible
            # ou incomplet (Marceau : jamais muet).
            if (self.fec_filename or '').lower().endswith(('.xlsx', '.xls')):
                brut = xlsx_vers_fec(brut, nom_fichier=self.fec_filename)
            # Plan uploadé : correspondances explicites pour les comptes
            # absents du mapping (code identique, défini par le plan).
            if plan_comptes is not None:
                mapping_cfg = self._completer_mapping_par_plan(
                    brut, mapping_cfg, plan_comptes)
            moteur = MoteurConcorde(config=self._config_moteur(mapping_cfg))
            contexte = moteur.executer(brut)
            contexte['mapping_libelle'] = mapping_cfg.get('libelle')
            contexte['correspondances_plan'] = mapping_cfg.get(
                'correspondances_plan', [])
        except Exception as exc:
            record = self.env['concorde.import'].create({
                'name': self.fec_filename or 'FEC',
                'fec_filename': self.fec_filename,
                'fec_file': self.fec_file,
                'mapping_source': (mapping_cfg or {}).get('libelle', ''),
                'plan_source': self.plan_filename or '',
                'state': 'erreur',
                'rapport_html': self._html_erreur(exc),
            })
            return self._retour_fiche(record)

        resultats = contexte['resultats']
        stats = {}
        if len(resultats) > 4:
            stats = resultats[4]['resultat'].get('stats', {})
        canon = resultats[2]['resultat']['canon']

        # --- comptes requis, comptes manquants, creation depuis le plan ---
        # Tout est calculé AVANT la fiche : le rapport rendu doit refléter
        # exactement ce que CONCORDE a fait (jamais muet).
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

        # Plan comptable uploadé : création automatique des comptes
        # manquants (code + intitulé lus dans le fichier, jamais devinés).
        # En dry-run aucune création : le rapport liste ce qui serait créé.
        comptes_crees = []
        comptes_a_creer = []
        sans_type = []
        if plan_comptes is not None:
            non_couverts = []
            for code in manquants:
                if code in plan_comptes:
                    if self.dry_run:
                        comptes_a_creer.append(code)
                    else:
                        nom, typ = plan_comptes[code]
                        vals = {'code': code, 'name': nom}
                        if typ:
                            vals['account_type'] = typ
                        else:
                            # type non déterminé dans le fichier : type Odoo
                            # par défaut explicite, tracé dans le rapport.
                            vals['account_type'] = TYPE_COMPTE_DEFAUT
                            sans_type.append(code)
                        acct = Account.create(vals)
                        par_code[code] = acct
                        comptes_crees.append(code)
                else:
                    non_couverts.append(code)
            manquants = non_couverts

        plan_libelle = ''
        if plan_comptes is not None:
            plan_libelle = "%s (%d comptes)" % (
                self.plan_filename or 'plan.xlsx', len(plan_comptes))
        contexte['plan_libelle'] = plan_libelle
        if comptes_a_creer:
            contexte['comptes_a_creer'] = comptes_a_creer
        if comptes_crees:
            contexte['comptes_crees'] = comptes_crees
        if sans_type:
            contexte['comptes_sans_type'] = sans_type

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
            'mapping_source': contexte.get('mapping_libelle', ''),
            'plan_source': contexte.get('plan_libelle', ''),
            'nb_comptes_crees': len(comptes_crees),
            'comptes_crees': ', '.join(comptes_crees),
            'comptes_manquants': ', '.join(manquants),
            'nb_ecritures': len(ecritures),
            'rapport_html': self._html_rapport(resultats, contexte),
        })

        if not self.dry_run and not self.journal_id:
            raise UserError(_("Choisissez un journal Odoo pour un import reel (ou activez le dry-run)."))
        if manquants and not self.dry_run:
            raise UserError(_(
                "Comptes Odoo absents (et absents du plan comptable uploadé) - "
                "CONCORDE ne devine jamais un compte : %s")
                % ', '.join(manquants[:30]))

        nb_creees = 0
        if not self.dry_run:
            Move = self.env['account.move']
            Journal = self.env['account.journal']
            for (jcode, enum), lignes in ecritures.items():
                journal = Journal.search(
                    [('code', '=', jcode)], limit=1) or self.journal_id
                ref = 'FEC %s-%s' % (jcode, enum)
                if Move.search_count([
                        ('ref', '=', ref), ('journal_id', '=', journal.id)]):
                    continue  # idempotence : deja importee
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
                    date_ecr = lignes[0].date_ecriture
                    Move.create({
                        'journal_id': journal.id,
                        'date': date_ecr,
                        'ref': ref,
                        'concorde_import_id': record.id,
                        'line_ids': vals_lines,
                    })
                    nb_creees += 1
            record.write({'state': 'importe', 'nb_ecritures': nb_creees})
        return self._retour_fiche(record)
