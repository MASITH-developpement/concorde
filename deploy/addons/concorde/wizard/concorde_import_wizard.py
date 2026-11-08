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

from __future__ import annotations

import base64
import binascii
import io
import os
import re
import zipfile
from collections import OrderedDict
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from odoo.addons.concorde.engine.moteur import MoteurConcorde
from odoo.addons.concorde.engine.mapping import (
    charger_mapping,
    charger_mapping_xlsx,
)
from odoo.addons.concorde.engine.plan_comptable import (
    charger_plan_xlsx,
    dictionnaire_plan,
)
from odoo.addons.concorde.engine.export_odoo import (
    TYPE_COMPTE_DEFAUT,
    generer_csv_comptes,
    generer_csv_ecritures,
    generer_csv_journaux,
    type_compte,
)
from odoo.addons.concorde.engine.xlsx_vers_fec import xlsx_vers_fec
from odoo.release import version as version_texte_odoo
from odoo.release import version_info

if TYPE_CHECKING:
    from typing import Literal, SupportsBytes, TypedDict

    from odoo.addons.concorde.engine.canonical import (
        Canonique,
        LigneEcriture,
    )
    from odoo.addons.concorde.engine.moteur import ContexteExecution

    # Configuration du mapping passée au moteur : mapping en mémoire
    # (« dict ») ou fichier JSON (« fichier »), plus ce que l'assistant
    # ajoute pour le rapport.
    ConfigMapping = TypedDict(
        "ConfigMapping",
        {
            "dict": dict[str, str],
            "fichier": str,
            "libelle": str,
            "correspondances_plan": list[str],
            "correspondances_auto": list[str],
            "libelles": dict[str, str],
        },
        total=False,
    )
    # Données du rapport HTML : bilan du moteur et ajouts de l'assistant.
    ContexteRapport = TypedDict(
        "ContexteRapport",
        {
            "audit_valide": bool,
            "empreinte_guardian": str,
            "mapping_libelle": str | None,
            "plan_libelle": str,
            "correspondances_plan": list[str],
            "correspondances_auto": list[str],
            "libelles_comptes": dict[str, str],
            "comptes_a_creer": list[str],
            "comptes_crees_plan": list[str],
            "comptes_crees_auto": list[str],
            "comptes_sans_type": list[str],
        },
        total=False,
    )
    # Plan comptable uploadé : {code: (intitulé, type Odoo ou None)}.
    PlanComptes = dict[str, tuple[str, str | None]]
    # Valeur lue dans un champ Binary : str base64 (Odoo <= 19), bytes,
    # BinaryValue (Odoo 20, supporte bytes()) ou False si vide.
    ValeurBinaire = str | bytes | SupportsBytes | Literal[False] | None
    # Action Odoo rendue au client web (fenêtre ou URL).
    ActionOdoo = dict[str, object]

# Nombre maximal de codes de comptes cités dans un rapport ou un message.
LIMITE_CODES_AFFICHES = 30

# Notice jointe au zip d'export : %s = version majeure d'Odoo (4 fois),
# puis nombre d'écritures et nombre de lignes.
MODELE_LISEZMOI = (
    "CONCORDE — Import de vos ecritures dans Odoo %s\n"
    "================================================\n"
    "\n"
    "Trois fichiers, trois imports, TOUJOURS dans cet ordre.\n"
    "Chaque import suit exactement la meme procedure (voir plus bas).\n"
    "\n"
    "ETAPE 1 — Creer les journaux\n"
    "  Fichier : journaux_odoo%s.csv\n"
    "  Menu    : Comptabilite > Configuration > Journaux\n"
    "             > liste ouverte > menu engrenage (ou les 3 points)\n"
    "             > Importer des enregistrements\n"
    "\n"
    "ETAPE 2 — Creer les comptes\n"
    "  Fichier : comptes_odoo%s.csv\n"
    "  Menu    : Comptabilite > Configuration > Plan comptable\n"
    "             > menu engrenage > Importer des enregistrements\n"
    "\n"
    "ETAPE 3 — Importer les ecritures\n"
    "  Fichier : ecritures_odoo%s.csv\n"
    "  Menu    : Comptabilite > Configuration > Journaux\n"
    "             > ouvrir N'IMPORTE QUEL journal > bouton intelligent\n"
    "             'Ecritures' > menu engrenage > Importer des\n"
    "             enregistrements\n"
    "  (le filtre journal de la liste n'a aucune importance : chaque\n"
    "   ligne du CSV porte le nom exact de son journal)\n"
    "\n"
    "PROCEDURE POUR CHAQUE IMPORT (identique sur Odoo 17, 18, 19, 20,\n"
    "Online ou on-premise) :\n"
    "  1. Glissez le fichier CSV dans la zone d'import.\n"
    "  2. REGLAGE OBLIGATOIRE : Separateur decimal = POINT\n"
    "     (par defaut Odoo propose Virgule : les montants seraient\n"
    "     mal interprettes. Les autres reglages — utf-8, virgule,\n"
    "     date JJ/MM/AAAA — sont corrects par defaut.)\n"
    "  3. 'Suivre les modifications dans le chatter' : Non.\n"
    "  4. Cliquez TESTER : Od affiche un apercu et le mapping des\n"
    "     colonnes. Toutes les colonnes sont reconnues automatiquement\n"
    "     (Journal par nom de journal, Compte par code = nom).\n"
    "  5. Si le test est vert : IMPORTER. Sinon : le message d'erreur\n"
    "     indique la ligne en cause — corrigez ou contactez le support\n"
    "     CONCORDE avec ce message.\n"
    "\n"
    "Contenu : %d ecritures, %d lignes.\n"
    "Verifications apres import : Grand livre equilibre ; total\n"
    "debit = total credit.\n"
    "Le lettrage n'est pas transmis par l'import natif Odoo : les\n"
    "rapprochements clients/fournisseurs se font dans Odoo ensuite.\n"
)


class EchecPipeline(Exception):
    """Échec du pipeline, avec le libellé du mapping connu à cet instant.

    Levée par ConcordeImportWizard._executer_pipeline ; erreur_origine
    garde l'exception d'origine pour le rapport d'erreur.
    """

    def __init__(
        self, erreur_origine: Exception, libelle_mapping: str
    ) -> None:
        """Mémorise l'erreur d'origine et le libellé du mapping."""
        super().__init__(str(erreur_origine))
        self.erreur_origine = erreur_origine
        self.libelle_mapping = libelle_mapping


def _version_majeure_odoo() -> int:
    """Numéro de version majeure d'Odoo, robuste toutes versions.

    Rôle : lire la version majeure d'Odoo. Odoo <= 19 : version_info est
    un namedtuple -> .major et [0] marchent. Odoo 20 : version_info est un
    simple TUPLE (odoo/release.py : version_info = (20, 0, 0, FINAL, 0,
    '')) -> .major n'existe PAS et getattr(..., 'major', 17) retombait
    TOUJOURS sur 17, meme sur une instance 20 : mauvais nom de zip, CSV au
    format de la mauvaise version et mauvais choix raw/datas. [0] marche
    pour les deux formes ; repli sur .major puis sur le texte de version.
    Paramètres : aucun.
    Retour : la version majeure (int).
    Erreurs : UserError si la version est illisible (jamais muet).
    Usages : action_exporter (nom des fichiers, choix raw/datas).
    """
    try:
        return int(version_info[0])
    except (TypeError, ValueError, IndexError):
        majeur = getattr(version_info, "major", None)
        if majeur is not None:
            return int(majeur)
        correspondance_version = re.match(r"(\d+)\.", version_texte_odoo or "")
        if correspondance_version:
            return int(correspondance_version.group(1))
        raise UserError(
            _("Version d'Odoo illisible (%r) — contactez le support CONCORDE.")
            % (version_info,)
        )


def _chemin_engine() -> str:
    """Rend le chemin du dossier engine/ embarqué dans le module."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"
    )


def _codes_html(codes: Sequence[str], marquer_coupure: bool = True) -> str:
    """Liste de codes de comptes échappée pour le rapport HTML.

    Rôle : citer au plus LIMITE_CODES_AFFICHES codes, séparés par des
    virgules, échappés pour le HTML.
    Paramètres : codes (codes de comptes) ; marquer_coupure (ajoute « … »
    quand la liste est coupée).
    Retour : le texte HTML échappé.
    Erreurs : aucune.
    Usages : ConcordeImportWizard._html_rapport (5 listes de comptes).
    """
    codes_affiches = html_escape(", ".join(codes[:LIMITE_CODES_AFFICHES]))
    if marquer_coupure and len(codes) > LIMITE_CODES_AFFICHES:
        codes_affiches += "…"
    return codes_affiches


def _comptes_des_lignes(
    lignes: Sequence[str], idx_num: int
) -> Iterator[tuple[str, list[str]]]:
    """Parcourt les lignes FEC qui portent un numéro de compte.

    Rôle : découper chaque ligne (tabulations) et ignorer les lignes trop
    courtes, sans compte, ou l'en-tête (« CompteNum »).
    Paramètres : lignes (lignes du FEC texte) ; idx_num (indice de la
    colonne CompteNum).
    Retour : itérateur de (compte, colonnes de la ligne).
    Erreurs : aucune.
    Usages : ConcordeImportWizard._completer_mapping (correspondances
    identité puis intitulés).
    """
    for ligne in lignes:
        parties = ligne.split("\t")
        if len(parties) <= idx_num:
            continue
        compte = parties[idx_num].strip()
        if not compte or compte.lower() == "comptenum":
            continue
        yield compte, parties


def _bilan_etape(
    contexte: ContexteExecution, rang_etape: int
) -> dict[str, Any]:
    """Résultat d'une étape du pipeline de l'assistant.

    Rôle : lire le dict produit par une étape (le moteur type ce résultat
    « object » : chaque étape rend sa propre structure).
    Paramètres : contexte (bilan du moteur) ; rang_etape (2 = mapping des
    comptes, 4 = rapport, cf. _config_moteur).
    Retour : le dict produit par l'étape (contenu propre à l'étape).
    Erreurs : TypeError si l'étape n'a pas produit un dict.
    Usages : action_exporter (canon), action_importer (canon, stats).
    """
    bilan = contexte["resultats"][rang_etape]["resultat"]
    if not isinstance(bilan, dict):
        raise TypeError(
            "Étape %d du pipeline : dict attendu, %s obtenu."
            % (rang_etape, type(bilan).__name__)
        )
    return bilan


class ConcordeImportWizard(models.TransientModel):
    """Assistant d'import ou d'export d'un FEC via le pipeline CONCORDE."""

    _name = "concorde.import.wizard"
    _description = "Assistant d'import FEC CONCORDE"

    fec_file = fields.Binary(
        string="Fichier FEC (Quadra) ou export Excel (.xlsx)", required=True
    )
    fec_filename = fields.Char(string="Nom du fichier")
    dry_run = fields.Boolean(
        string="Mode simulation (dry-run)",
        default=True,
        help="Analyse complete du FEC sans creer d'ecritures dans Odoo. "
        "CONCORDE est idempotent : meme hors dry-run, un import deja "
        "effectue n'est jamais duplique.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal Odoo par defaut",
        domain=[("type", "=", "general")],
    )
    plan_file = fields.Binary(
        string="Plan comptable Odoo (.xlsx) — création des comptes manquants",
        required=False,
        help="Nouveau plan comptable : les comptes requis par l'import mais "
        "absents d'Odoo y sont lus (code + intitulé, colonne « Type » "
        "optionnelle) et CRÉÉS automatiquement. Un compte requis mais "
        "absent de ce fichier reste bloquant (aucun compte deviné). "
        "En dry-run aucun compte n'est créé : le rapport liste ce qui "
        "serait créé.",
    )
    plan_filename = fields.Char(string="Nom du fichier du plan comptable")
    mapping_file = fields.Binary(
        string="Fichier de mapping (Mapping Quadra Odoo .xlsx)",
        required=False,
        help="Correspondances des comptes Quadra -> Odoo. Colonnes "
        "attendues : « Numéro » (compte Quadra) et « Odoo Acct » (compte "
        "Odoo cible). Prioritaire sur le mapping JSON embarqué. Un compte "
        "absent du mapping reste bloquant (aucun compte deviné).",
    )
    mapping_filename = fields.Char(string="Nom du fichier de mapping")

    @api.model
    def _default_journal(self) -> models.BaseModel:
        """Journal par défaut : code CONCORDE, sinon un journal général."""
        journal = self.env["account.journal"].search(
            [("code", "=", "CONCORDE")], limit=1
        )
        if not journal:
            journal = self.env["account.journal"].search(
                [("type", "=", "general")], limit=1
            )
        return journal

    @api.model
    def default_get(self, fields_list: list[str]) -> dict[str, Any]:
        """Valeurs par défaut, complétées du journal par défaut.

        Les valeurs dépendent du type de chaque champ : dynamiques.
        """
        vals = super().default_get(fields_list)
        if "journal_id" in fields_list and not vals.get("journal_id"):
            journal = self._default_journal()
            vals["journal_id"] = journal.id if journal else False
        return vals

    def _config_moteur(
        self, mapping_cfg: ConfigMapping | None = None
    ) -> dict[str, object]:
        """Configuration du moteur : Guardian, étapes du pipeline, mapping."""
        return {
            "noyau": {"guardian": {"journal": "/var/concorde/guardian"}},
            "pipeline": [
                {
                    "nom": "importer_fec",
                    "module": "odoo.addons.concorde.engine.fec_parser",
                    "fonction": "parse_fec",
                },
                {
                    "nom": "verifier_equilibre",
                    "fonction": "verifier_equilibre",
                },
                {"nom": "mapper_comptes", "fonction": "mapper_comptes"},
                {
                    "nom": "lettrer",
                    "module": "odoo.addons.concorde.engine.lettrage",
                    "fonction": "lettrer",
                },
                {"nom": "rapport", "fonction": "rapport"},
            ],
            "mapping": mapping_cfg or self._config_mapping(),
        }

    def _lire_binaire(self, valeur: ValeurBinaire) -> bytes:
        """Rend le contenu brut (bytes) d'un champ Binary, tous Odoo.

        Rôle : Odoo <= 19 : la lecture rend du base64, en str ou en bytes
        (Odoo 17 rend des bytes base64, mesuré le 08/11/2026) -> décoder ;
        des bytes qui ne sont pas du base64 sont déjà le fichier.
        Odoo 20 : la lecture rend un BinaryValue (BinaryBytes ou
        BinaryValueAttachment, cf. odoo/tools/binary.py et
        odoo/orm/fields_binary.py) — un proxy paresseux dont .content
        donne les octets et qui supporte bytes(). (Preuve du bug 20 :
        base64.b64decode() sur la valeur avec validate=False jette
        silencieusement les octets hors alphabet et produit des déchets
        déterministes par fichier — les « 3c a4 83 16 » etc. — alors que
        le filestore contenait les fichiers intacts.)
        Paramètres : valeur (valeur lue dans un champ Binary).
        Retour : les octets du fichier (b"" si le champ est vide).
        Erreurs : UserError, avec le type, si la valeur est inattendue, ou
        si une str n'est pas du base64 valide (jamais muet).
        Usages : _config_mapping, _executer_pipeline, _b64_pour_stockage,
        action_exporter, action_importer.
        """
        if not valeur:
            return b""
        if isinstance(valeur, (str, bytes)):
            # validate=True : un caractère hors alphabet base64 (tabulation,
            # fin de ligne d'un FEC brut) est refusé, jamais jeté en silence.
            try:
                octets_fichier = base64.b64decode(valeur, validate=True)
            except binascii.Error:
                if isinstance(valeur, str):
                    raise UserError(
                        _(
                            "Fichier illisible : contenu base64 invalide — "
                            "contactez le support CONCORDE."
                        )
                    )
                octets_fichier = valeur
        else:
            # Odoo 20 : BinaryValue / BinaryValueAttachment (Buffer)
            contenu = getattr(valeur, "content", None)
            if isinstance(contenu, bytes):
                octets_fichier = contenu
            else:
                try:
                    octets_fichier = bytes(valeur)  # BinaryValue.__bytes__
                except Exception:
                    raise UserError(
                        _(
                            "Type de fichier inattendu (%r, attributs: %s) — "
                            "contactez le support CONCORDE."
                        )
                        % (type(valeur).__name__, sorted(dir(valeur))[:20])
                    )
        # Anti-double-encodage : un .xlsx encodé une fois de trop commence
        # par 'UEsDB' (base64 de l'en-tête zip 'PK\x03\x04'). Un vrai
        # fichier ne commence jamais ainsi : on déballe les couches
        # superflues (max 3) pour rendre les octets réels du fichier.
        for _couche_superflue in range(3):
            if octets_fichier[:5] != b"UEsDB":
                break
            octets_fichier = base64.b64decode(octets_fichier)
        return octets_fichier

    def _b64_pour_stockage(
        self, valeur: ValeurBinaire
    ) -> str | Literal[False] | None:
        """Valeur stockable dans un champ Binary (str base64), tous Odoo.

        Rôle : Odoo <= 19 rend une str base64 ; Odoo 20 rend un
        BinaryValue (proxy). On repart du contenu brut et on l'encode en
        base64 — utilisable pour les create()/write() de Binary sur toutes
        les versions.
        Paramètres : valeur (valeur lue dans un champ Binary).
        Retour : la str base64, ou la valeur vide (None / False) inchangée.
        Erreurs : UserError de _lire_binaire si la valeur est inattendue.
        Usages : _valeurs_fichier_fec.
        """
        if isinstance(valeur, str) or valeur is None or valeur is False:
            return valeur
        return base64.b64encode(self._lire_binaire(valeur)).decode()

    def _config_mapping(self) -> ConfigMapping:
        """Mapping du pipeline : fichier uploadé (prioritaire) ou JSON.

        Le fichier client « Mapping Quadra Odoo.xlsx » est lu par le moteur
        (engine.mapping.charger_mapping_xlsx, stdlib uniquement). Toute
        erreur de lecture est explicite (Marceau : jamais muet).
        """
        if self.mapping_file:
            brut = self._lire_binaire(self.mapping_file)
            mapping = charger_mapping_xlsx(
                brut, nom_fichier=self.mapping_filename or ""
            )
            return {
                "dict": mapping,
                "libelle": "%s (%d correspondances)"
                % (self.mapping_filename or "mapping.xlsx", len(mapping)),
            }
        return {
            "fichier": os.path.join(
                _chemin_engine(), "mapping_quadra_odoo.json"
            ),
            "libelle": "mapping_quadra_odoo.json (embarqué)",
        }

    def _grouper_ecritures(
        self, canon: Canonique
    ) -> OrderedDict[tuple[str, str], list[LigneEcriture]]:
        """Regroupe les lignes par écriture (journal, numéro), dans l'ordre."""
        ecritures: OrderedDict[tuple[str, str], list[LigneEcriture]] = (
            OrderedDict()
        )
        for ligne_ecriture in canon.lignes:
            cle = (ligne_ecriture.journal_code, ligne_ecriture.ecriture_num)
            ecritures.setdefault(cle, []).append(ligne_ecriture)
        return ecritures

    def _html_erreur(self, exc: Exception) -> str:
        """Rapport HTML d'un échec du pipeline (aucun import effectué)."""
        detail = html_escape("%s: %s" % (type(exc).__name__, exc))
        return (
            "<p><b>Echec du pipeline CONCORDE - aucun import effectue.</b></p>"
            "<p>Erreur : %s</p>" % detail
        )

    def _html_rapport(
        self,
        resultats: Sequence[Mapping[str, object]],
        contexte: ContexteRapport,
    ) -> str:
        """Rapport HTML du pipeline : audit, mapping, comptes, étapes."""
        if contexte.get("audit_valide"):
            etat = "audit valide"
        else:
            etat = "ALERTE : chaine d'audit invalide"
        lignes = ["<p><b>Pipeline CONCORDE</b> - Guardian : %s</p>" % etat]
        if contexte.get("mapping_libelle"):
            lignes.append(
                "<p>Mapping des comptes : %s</p>"
                % html_escape(contexte["mapping_libelle"])
            )
        if contexte.get("plan_libelle"):
            lignes.append(
                "<p>Plan comptable : %s</p>"
                % html_escape(contexte["plan_libelle"])
            )
        if contexte.get("correspondances_plan"):
            ajoutes = contexte["correspondances_plan"]
            lignes.append(
                "<p>Correspondances ajoutées depuis le plan comptable "
                "(Quadra -> compte Odoo de même code, défini par le plan, "
                "aucun compte deviné) : %d (%s)</p>"
                % (len(ajoutes), _codes_html(ajoutes))
            )
        if contexte.get("correspondances_auto"):
            ajoutes = contexte["correspondances_auto"]
            lignes.append(
                "<p>Correspondances identité ajoutées (comptes absents du "
                "mapping et du plan — compte Odoo de même code créé "
                "automatiquement, décision client, aucun compte deviné) : "
                "%d (%s)</p>" % (len(ajoutes), _codes_html(ajoutes))
            )
        if contexte.get("comptes_a_creer"):
            lignes.append(
                "<p>Dry-run : %d compte(s) seraient créés dans Odoo "
                "(depuis le plan comptable ou automatiquement) : %s</p>"
                % (
                    len(contexte["comptes_a_creer"]),
                    _codes_html(contexte["comptes_a_creer"]),
                )
            )
        if contexte.get("comptes_crees_plan"):
            crees = contexte["comptes_crees_plan"]
            lignes.append(
                "<p>Comptes créés depuis le plan comptable : %d (%s)</p>"
                % (len(crees), _codes_html(crees))
            )
        if contexte.get("comptes_crees_auto"):
            crees = contexte["comptes_crees_auto"]
            lignes.append(
                '<p style="color:#B06A2E;">Comptes créés automatiquement '
                "(absents du plan comptable — intitulé lu dans le fichier "
                "d'écritures, type par défaut « %s », aucun compte "
                "deviné) : %d (%s)</p>"
                % (TYPE_COMPTE_DEFAUT, len(crees), _codes_html(crees))
            )
        if contexte.get("comptes_sans_type"):
            lignes.append(
                '<p style="color:#B06A2E;">Comptes créés sans type explicite '
                "(type par défaut « %s » appliqué, aucun type deviné) : %s</p>"
                % (
                    TYPE_COMPTE_DEFAUT,
                    _codes_html(
                        contexte["comptes_sans_type"], marquer_coupure=False
                    ),
                )
            )
        lignes.append("<ul>")
        for resultat_etape in resultats:
            nom = html_escape(resultat_etape.get("etape", "?"))
            marceau = html_escape(resultat_etape.get("marceau", ""))
            lignes.append("<li><b>%s</b> - %s</li>" % (nom, marceau))
        lignes.append("</ul>")
        empreinte = html_escape(contexte.get("empreinte_guardian", ""))
        lignes.append(
            '<p style="color:#888;">Empreinte Guardian : %s</p>' % empreinte
        )
        return "".join(lignes)

    def _retour_fiche(self, record: models.BaseModel) -> ActionOdoo:
        """Action Odoo ouvrant la fiche d'import donnée.

        Rôle : afficher la fiche concorde.import créée par l'assistant.
        Paramètres : record (fiche concorde.import).
        Retour : l'action fenêtre (dict) pour le client web.
        Erreurs : aucune.
        Usages : _creer_fiche_erreur, action_importer.
        """
        return {
            "type": "ir.actions.act_window",
            "res_model": "concorde.import",
            "res_id": record.id,
            "view_mode": "form",
            "target": "current",
        }

    def _valeurs_fichier_fec(self) -> dict[str, object]:
        """Valeurs communes de la fiche d'import : nom et fichier FEC.

        Rôle : décrire le fichier importé de la même façon sur toutes les
        fiches concorde.import créées par l'assistant.
        Paramètres : aucun (lit l'assistant courant).
        Retour : dict name / fec_filename / fec_file.
        Erreurs : UserError de _b64_pour_stockage si le fichier est d'un
        type inattendu.
        Usages : _creer_fiche_erreur, action_importer.
        """
        return {
            "name": self.fec_filename or "FEC",
            "fec_filename": self.fec_filename,
            "fec_file": self._b64_pour_stockage(self.fec_file),
        }

    def _creer_fiche_erreur(self, echec_pipeline: EchecPipeline) -> ActionOdoo:
        """Crée la fiche d'import en erreur et rend l'action qui l'ouvre.

        Rôle : tracer un échec du pipeline (aucun import effectué).
        Paramètres : echec_pipeline (erreur d'origine et libellé du
        mapping connu au moment de l'échec).
        Retour : l'action fenêtre ouvrant la fiche créée.
        Erreurs : UserError de _valeurs_fichier_fec.
        Usages : action_exporter, action_importer.
        """
        record = self.env["concorde.import"].create(
            {
                **self._valeurs_fichier_fec(),
                "mapping_source": echec_pipeline.libelle_mapping,
                "plan_source": self.plan_filename or "",
                "state": "erreur",
                "rapport_html": self._html_erreur(
                    echec_pipeline.erreur_origine
                ),
            }
        )
        return self._retour_fiche(record)

    def _executer_pipeline(
        self, brut: bytes
    ) -> tuple[ContexteExecution, ConfigMapping, PlanComptes | None]:
        """Prépare le mapping et le plan, puis exécute le pipeline CONCORDE.

        Rôle : lire le plan comptable uploadé (optionnel), convertir un
        export Excel (.xlsx) en FEC standard (erreur explicite si le
        classeur est illisible ou incomplet), rattacher les comptes absents
        du mapping (identité, définis par le plan ou créés avec l'intitulé
        du FEC), puis exécuter le moteur.
        Paramètres : brut (octets du fichier d'écritures uploadé).
        Retour : (bilan du moteur, configuration du mapping complétée,
        plan comptable {code: (nom, type)} ou None).
        Erreurs : EchecPipeline pour toute erreur, avec le libellé du
        mapping connu à cet instant (Marceau : jamais muet).
        Usages : action_exporter, action_importer.
        """
        mapping_cfg: ConfigMapping | None = None
        try:
            mapping_cfg = self._config_mapping()
            plan_comptes: PlanComptes | None = None
            if self.plan_file:
                plan_comptes = dictionnaire_plan(
                    charger_plan_xlsx(
                        self._lire_binaire(self.plan_file),
                        nom_fichier=self.plan_filename or "",
                    )
                )
            if (self.fec_filename or "").lower().endswith((".xlsx", ".xls")):
                brut = xlsx_vers_fec(brut, nom_fichier=self.fec_filename or "")
            mapping_cfg = self._completer_mapping(
                brut, mapping_cfg, plan_comptes
            )
            moteur = MoteurConcorde(config=self._config_moteur(mapping_cfg))
            contexte = moteur.executer(brut)
        except Exception as exc:
            raise EchecPipeline(
                exc, mapping_cfg.get("libelle", "") if mapping_cfg else ""
            ) from exc
        return contexte, mapping_cfg, plan_comptes

    def _completer_mapping(
        self,
        brut: bytes,
        mapping_cfg: ConfigMapping,
        plan_comptes: PlanComptes | None,
    ) -> ConfigMapping:
        """Correspondances identité pour les comptes absents du mapping.

        Règle CONCORDE (décision client explicite) : tout compte du fichier
        d'écritures absent du mapping est rattaché au compte Odoo de même
        code. Le compte est ensuite créé dans Odoo soit depuis le plan
        comptable uploadé (code + intitulé + type lus dans le plan), soit
        automatiquement avec l'intitulé lu dans le fichier d'écritures
        (colonne CompteLib) et le type par défaut explicite. Aucun compte
        ni intitulé n'est jamais deviné, et chaque ajout est tracé dans le
        rapport (Marceau : jamais muet).
        """
        try:
            texte = brut.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UserError(
                _(
                    "Fichier d'écritures illisible (encodage UTF-8 "
                    "attendu) : %s"
                )
                % exc
            )
        mapping: dict[str, str]
        if "dict" in mapping_cfg:
            mapping = dict(mapping_cfg["dict"])
        else:
            mapping = charger_mapping(mapping_cfg["fichier"])
        lignes = texte.splitlines()
        # Indices des colonnes CompteNum/CompteLib depuis l'en-tête FEC
        # (standard : 4 et 5) ; fallback explicite si l'en-tête manque.
        idx_num, idx_lib = 4, 5
        for ligne in lignes:
            champs = [
                champ_entete.strip().lower()
                for champ_entete in ligne.split("\t")
            ]
            if "comptenum" in champs:
                idx_num = champs.index("comptenum")
                if "comptelib" in champs:
                    idx_lib = champs.index("comptelib")
                break
        depuis_plan: list[str] = []
        hors_plan: list[str] = []
        libelles: dict[str, str] = {}
        for compte, _parties in _comptes_des_lignes(lignes, idx_num):
            if compte in mapping:
                continue
            mapping[compte] = compte
            if plan_comptes is not None and compte in plan_comptes:
                if compte not in depuis_plan:
                    depuis_plan.append(compte)
            elif compte not in hors_plan:
                hors_plan.append(compte)
        # Intitulés lus dans le FEC (colonne CompteLib), indexés par le
        # compte Odoo CIBLE : l'intitulé du compte Quadra décrit le compte
        # Odoo qui lui est rattaché (identité ou correspondance du mapping).
        for compte, parties in _comptes_des_lignes(lignes, idx_num):
            cible = mapping.get(compte)
            if cible and len(parties) > idx_lib:
                lib = parties[idx_lib].strip()
                if lib and lib.lower() != "comptelib":
                    libelles.setdefault(cible, lib)
        libelle = mapping_cfg.get("libelle", "mapping")
        nb = len(depuis_plan) + len(hors_plan)
        if nb:
            libelle += (
                _(
                    " + %d correspondances identité (comptes absents du "
                    "mapping : définis par le plan comptable ou créés "
                    "automatiquement)"
                )
                % nb
            )
        return {
            "dict": mapping,
            "libelle": libelle,
            "correspondances_plan": depuis_plan,
            "correspondances_auto": hors_plan,
            "libelles": libelles,
        }

    def action_exporter(self) -> ActionOdoo:
        """Exporte les écritures au format d'import standard d'Odoo.

        Chaque instance CONCORDE exporte pour SA version d'Odoo (déduite
        de odoo.release) : trois CSV (journaux, comptes puis écritures) et
        un LISEZMOI, zippés, que l'assistant d'import natif d'Odoo ingère —
        utile pour Odoo Online où aucun module ne peut être installé.
        Aucun compte ni écriture n'est créé : l'export est un dry-run
        intégral (jamais muet, le rapport d'erreur s'affiche en cas de
        problème de pipeline).
        """
        self.ensure_one()
        version = str(_version_majeure_odoo())
        brut = self._lire_binaire(self.fec_file)
        try:
            contexte, mapping_cfg, _plan = self._executer_pipeline(brut)
        except EchecPipeline as echec_pipeline:
            return self._creer_fiche_erreur(echec_pipeline)
        canon: Canonique = _bilan_etape(contexte, 2)["canon"]
        # Intitulés lus dans le FEC (colonne CompteLib) par
        # _completer_mapping, indexés par compte Odoo cible.
        libelles = mapping_cfg.get("libelles", {})
        csv_comptes = generer_csv_comptes(canon.lignes, libelles, version)
        csv_ecritures = generer_csv_ecritures(canon.lignes, version)
        csv_journaux = generer_csv_journaux(canon.lignes, version)
        nb_ecritures = len(
            {
                (
                    ligne_ecriture.journal_code,
                    ligne_ecriture.ecriture_num,
                    ligne_ecriture.date_ecriture,
                )
                for ligne_ecriture in canon.lignes
            }
        )
        lisezmoi = (
            MODELE_LISEZMOI
            % (
                version,
                version,
                version,
                version,
                nb_ecritures,
                len(canon.lignes),
            )
        ).encode("utf-8")
        tampon_zip = io.BytesIO()
        with zipfile.ZipFile(tampon_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("journaux_odoo%s.csv" % version, csv_journaux)
            archive.writestr("comptes_odoo%s.csv" % version, csv_comptes)
            archive.writestr("ecritures_odoo%s.csv" % version, csv_ecritures)
            archive.writestr("LISEZMOI.txt", lisezmoi)
        nom = "concorde_export_odoo%s.zip" % version
        # Odoo 20 : 'datas' est IGNORE (ir_attachment._check_contents :
        # "Use raw, datas has beeen removed" + values.pop('datas')) — il
        # faut ecrire 'raw' (bytes : exception explicite du champ raw, les
        # octets sont bruts). Odoo <= 19 : 'datas' en str base64 fonctionne.
        majeur = _version_majeure_odoo()
        attachment_vals: dict[str, object] = {
            "name": nom,
            "mimetype": "application/zip",
        }
        if majeur >= 20:
            attachment_vals["raw"] = tampon_zip.getvalue()
        else:
            attachment_vals["datas"] = base64.b64encode(
                tampon_zip.getvalue()
            ).decode()
        attachment = self.env["ir.attachment"].create(attachment_vals)
        # Marceau : jamais muet — verifier que le zip reellement stocke
        # n'est PAS vide (un export vide doit echouer explicitement, pas
        # livrer un fichier de 0 octet). Les champs raw / datas
        # d'ir.attachment sont lus par leur nom (modèle hors module).
        taille_stockee = 0
        try:
            taille_stockee = (
                attachment["raw"].size
                if hasattr(attachment["raw"], "size")
                else len(attachment["raw"] or b"")
            )
        except Exception:
            taille_stockee = len(base64.b64decode(attachment["datas"] or ""))
        if taille_stockee != len(tampon_zip.getvalue()):
            raise UserError(
                _(
                    "Export zip incomplet : %d octets stockés sur %d attendus "
                    "— contactez le support CONCORDE."
                )
                % (taille_stockee, len(tampon_zip.getvalue()))
            )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_importer(self) -> ActionOdoo:
        """Analyse le FEC et, hors dry-run, crée comptes et écritures.

        Le pipeline CONCORDE est exécuté, la fiche concorde.import reçoit
        le rapport ; hors dry-run, les comptes manquants sont créés puis
        les écritures non encore importées (idempotence par référence
        « FEC journal-écriture »). Retour : l'action ouvrant la fiche.
        Erreurs : UserError sans journal hors dry-run ou si des comptes
        manquent encore.
        """
        self.ensure_one()
        brut = self._lire_binaire(self.fec_file)
        try:
            contexte, mapping_cfg, plan_comptes = self._executer_pipeline(brut)
        except EchecPipeline as echec_pipeline:
            return self._creer_fiche_erreur(echec_pipeline)
        contexte_rapport: ContexteRapport = {
            "audit_valide": contexte["audit_valide"],
            "empreinte_guardian": contexte["empreinte_guardian"],
            "mapping_libelle": mapping_cfg.get("libelle"),
            "correspondances_plan": mapping_cfg.get(
                "correspondances_plan", []
            ),
            "correspondances_auto": mapping_cfg.get(
                "correspondances_auto", []
            ),
            "libelles_comptes": mapping_cfg.get("libelles", {}),
        }

        resultats = contexte["resultats"]
        stats: dict[str, Any] = {}
        if len(resultats) > 4:
            stats = _bilan_etape(contexte, 4).get("stats", {})
        canon: Canonique = _bilan_etape(contexte, 2)["canon"]

        # --- comptes requis, comptes manquants, creation depuis le plan ---
        # Tout est calculé AVANT la fiche : le rapport rendu doit refléter
        # exactement ce que CONCORDE a fait (jamais muet).
        ecritures = self._grouper_ecritures(canon)
        comptes = sorted(
            {
                ligne_ecriture.compte
                for lignes in ecritures.values()
                for ligne_ecriture in lignes
            }
        )
        Account = self.env["account.account"]
        par_code: dict[str, models.BaseModel] = {}
        manquants: list[str] = []
        for code in comptes:
            acct = Account.search(
                [
                    ("code", "=", code),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
            if acct:
                par_code[code] = acct
            else:
                manquants.append(code)

        # Création des comptes manquants dans Odoo :
        # - depuis le plan comptable uploadé si le compte y est défini
        #   (code + intitulé + type lus dans le plan, jamais devinés) ;
        # - sinon automatiquement (décision client explicite) avec
        #   l'intitulé lu dans le fichier d'écritures (colonne CompteLib)
        #   et le type par défaut explicite — tout est tracé.
        # En dry-run aucune création : le rapport liste ce qui serait créé.
        libelles = contexte_rapport.get("libelles_comptes", {})
        comptes_crees_plan: list[str] = []
        comptes_crees_auto: list[str] = []
        comptes_a_creer: list[str] = []
        sans_type: list[str] = []
        for code in manquants:
            if self.dry_run:
                comptes_a_creer.append(code)
                continue
            typ: str | None
            if plan_comptes is not None and code in plan_comptes:
                nom, typ = plan_comptes[code]
                origine = "plan"
            else:
                nom = libelles.get(code) or code
                typ = None
                origine = "auto"
            vals = {"code": code, "name": nom}
            if typ:
                vals["account_type"] = typ
            else:
                # type non déterminé dans le plan : type Odoo explicite
                # déduit de la classe du compte, tracé dans le rapport.
                vals["account_type"] = type_compte(code)
                sans_type.append(code)
            acct = Account.create(vals)
            par_code[code] = acct
            if origine == "plan":
                comptes_crees_plan.append(code)
            else:
                comptes_crees_auto.append(code)
        manquants = []

        plan_libelle = ""
        if plan_comptes is not None:
            plan_libelle = "%s (%d comptes)" % (
                self.plan_filename or "plan.xlsx",
                len(plan_comptes),
            )
        contexte_rapport["plan_libelle"] = plan_libelle
        if comptes_a_creer:
            contexte_rapport["comptes_a_creer"] = comptes_a_creer
        if comptes_crees_plan:
            contexte_rapport["comptes_crees_plan"] = comptes_crees_plan
        if comptes_crees_auto:
            contexte_rapport["comptes_crees_auto"] = comptes_crees_auto
        if sans_type:
            contexte_rapport["comptes_sans_type"] = sans_type
        tous_crees = comptes_crees_plan + comptes_crees_auto

        record = self.env["concorde.import"].create(
            {
                **self._valeurs_fichier_fec(),
                "journal_id": self.journal_id.id,
                "state": "analyse_ok",
                "nb_lignes": stats.get("nb_lignes", 0),
                "nb_paires": stats.get("nb_paires", 0),
                "nb_anomalies": stats.get("nb_anomalies", 0),
                "total_debit": stats.get("total_debit", 0) / 100.0,
                "total_credit": stats.get("total_credit", 0) / 100.0,
                "empreinte_guardian": contexte_rapport.get(
                    "empreinte_guardian", ""
                ),
                "mapping_source": contexte_rapport.get("mapping_libelle", ""),
                "plan_source": contexte_rapport.get("plan_libelle", ""),
                "nb_comptes_crees": len(tous_crees),
                "comptes_crees": ", ".join(tous_crees),
                "comptes_manquants": ", ".join(manquants),
                "nb_ecritures": len(ecritures),
                "rapport_html": self._html_rapport(
                    resultats, contexte_rapport
                ),
            }
        )

        if not self.dry_run and not self.journal_id:
            raise UserError(
                _(
                    "Choisissez un journal Odoo pour un import reel "
                    "(ou activez le dry-run)."
                )
            )
        if manquants and not self.dry_run:
            raise UserError(
                _(
                    "Comptes Odoo absents (et absents du plan comptable "
                    "uploadé) - CONCORDE ne devine jamais un compte : %s"
                )
                % ", ".join(manquants[:LIMITE_CODES_AFFICHES])
            )

        nb_creees = 0
        if not self.dry_run:
            Move = self.env["account.move"]
            Journal = self.env["account.journal"]
            for (jcode, enum), lignes in ecritures.items():
                journal = (
                    Journal.search([("code", "=", jcode)], limit=1)
                    or self.journal_id
                )
                ref = "FEC %s-%s" % (jcode, enum)
                if Move.search_count(
                    [("ref", "=", ref), ("journal_id", "=", journal.id)]
                ):
                    continue  # idempotence : deja importee
                vals_lines: list[tuple[int, int, dict[str, object]]] = []
                for ligne in lignes:
                    if ligne.debit == 0 and ligne.credit == 0:
                        continue
                    libelle_ligne = (ligne.libelle or "CONCORDE")[:200]
                    vals_lines.append(
                        (
                            0,
                            0,
                            {
                                "name": libelle_ligne,
                                "account_id": par_code[ligne.compte].id,
                                "debit": ligne.debit / 100.0,
                                "credit": ligne.credit / 100.0,
                            },
                        )
                    )
                if vals_lines:
                    date_ecr = lignes[0].date_ecriture
                    Move.create(
                        {
                            "journal_id": journal.id,
                            "date": date_ecr,
                            "ref": ref,
                            "concorde_import_id": record.id,
                            "line_ids": vals_lines,
                        }
                    )
                    nb_creees += 1
            record.write({"state": "importe", "nb_ecritures": nb_creees})
        return self._retour_fiche(record)
