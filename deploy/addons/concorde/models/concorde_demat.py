# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Contrôle de la dématérialisation des factures — application Odoo.

Le moteur (engine/demat.py, copie fidèle de core/demat.py) est le même que
celui du script scripts/check_dematerialisation.py. Lecture seule : le
contrôle n'écrit que son propre rapport (concorde.demat.controle).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.concorde.engine.demat import ControleDemat, rendu_html

if TYPE_CHECKING:
    from odoo.api import Environment


class SourceEnv:
    """Source « interne » du moteur demat : l'ORM, droits de l'utilisateur."""

    def __init__(self, env: Environment) -> None:
        """Mémorise l'environnement Odoo de l'utilisateur courant."""
        self.env = env

    def champs(self, modele: str) -> dict[str, dict[str, Any]]:
        """Rend la description des champs d'un modèle ({} si inaccessible).

        Les attributs d'un champ dépendent de son type : valeurs dynamiques.
        """
        if modele not in self.env:
            return {}
        try:
            return self.env[modele].fields_get(attributes=["type"])
        except AccessError:
            return {}

    def lire(
        self,
        modele: str,
        domaine: Sequence[Sequence[object]],
        champs: Iterable[str],
        offset: int = 0,
        limit: int | None = None,
        ordre: str = "id",
    ) -> list[dict[str, Any]]:
        """Lit les enregistrements du domaine (search_read, lecture seule).

        Les valeurs lues dépendent du type de chaque champ : dynamiques.
        """
        return self.env[modele].search_read(
            domaine, list(champs), offset=offset, limit=limit, order=ordre
        )

    def modules_installes(self, noms: Iterable[str]) -> set[str] | None:
        """Rend les modules installés parmi noms (None si droits absents)."""
        try:
            modules_lus = self.env["ir.module.module"].search_read(
                [("name", "in", list(noms)), ("state", "=", "installed")],
                ["name"],
            )
        except AccessError:
            return None
        return {module_lu["name"] for module_lu in modules_lus}


class ConcordeDematControle(models.Model):
    """Rapport d'un contrôle de la dématérialisation des factures."""

    _name = "concorde.demat.controle"
    _description = "Contrôle de la dématérialisation des factures"
    _order = "id desc"

    name = fields.Char(
        string="Contrôle",
        required=True,
        default=lambda self: _("Contrôle du %s") % fields.Date.today(),
    )
    date_controle = fields.Datetime(string="Exécuté le", readonly=True)
    jours = fields.Integer(string="Fenêtre (jours)", default=30, required=True)
    inspecter_pdf = fields.Boolean(
        string="Inspecter les PDF (Factur-X embarqué)",
        default=True,
        help="Ouvre les PDF des factures sans XML séparé pour y chercher le "
        "Factur-X embarqué. Plus lent, mais évite de sous-estimer le taux.",
    )
    state = fields.Selection(
        [
            ("draft", "Non exécuté"),
            ("conforme", "Conforme"),
            ("a_verifier", "À vérifier"),
            ("non_conforme", "Non conforme"),
        ],
        string="Résultat",
        default="draft",
        readonly=True,
    )
    nb_bloquants = fields.Integer(string="Bloquants", readonly=True)
    nb_alertes = fields.Integer(string="Alertes", readonly=True)
    nb_infos = fields.Integer(string="Informations", readonly=True)
    emission_total = fields.Integer(string="Factures émises", readonly=True)
    emission_avec_xml = fields.Integer(string="Émises avec XML", readonly=True)
    reception_total = fields.Integer(string="Factures reçues", readonly=True)
    reception_avec_xml = fields.Integer(
        string="Reçues avec XML", readonly=True
    )
    taux_reception = fields.Char(
        string="Taux de réception électronique", readonly=True
    )
    empreinte = fields.Char(string="Empreinte SHA-256", readonly=True)
    rapport_html = fields.Html(string="Rapport", sanitize=False, readonly=True)
    rapport_json = fields.Text(string="Rapport (JSON)", readonly=True)

    def action_lancer(self) -> bool:
        """Exécute le contrôle et enregistre son rapport dans la fiche.

        Erreurs : UserError si la fenêtre est inférieure à 1 jour ou si le
        moteur échoue (RuntimeError).
        """
        for rec in self:
            if rec.jours < 1:
                raise UserError(
                    _("La fenêtre d'analyse doit être d'au moins 1 jour.")
                )
            try:
                rapport_controle = (
                    ControleDemat(
                        SourceEnv(self.env),
                        jours=rec.jours,
                        inspecter_pdf=rec.inspecter_pdf,
                    )
                    .executer()
                    .en_dict()
                )
            except RuntimeError as exc:
                raise UserError(str(exc))
            infos = rapport_controle["infos"]
            rec.write(
                {
                    "date_controle": fields.Datetime.now(),
                    "state": rapport_controle["statut"],
                    "nb_bloquants": rapport_controle["bloquants"],
                    "nb_alertes": rapport_controle["alertes"],
                    "nb_infos": rapport_controle["infos_anomalies"],
                    "emission_total": infos.get("emission_total", 0),
                    "emission_avec_xml": infos.get("emission_avec_xml", 0),
                    "reception_total": infos.get("reception_total", 0),
                    "reception_avec_xml": infos.get("reception_avec_xml", 0),
                    "taux_reception": infos.get(
                        "reception_taux_electronique", ""
                    ),
                    "empreinte": rapport_controle["empreinte"],
                    "rapport_html": rendu_html(rapport_controle),
                    "rapport_json": json.dumps(
                        rapport_controle,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                }
            )
        return True
