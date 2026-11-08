# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""MOTEUR CONCORDE — orchestration du pipeline, no-code 100 % YAML.

- Refuse de démarrer sans Guardian self-checké (noyau obligatoire)
- Chaque étape du pipeline est enveloppée par Guardian (audit + rate limit)
- Chaque donnée produite est liée à son explication Marceau
"""

import importlib
from typing import Any, Callable, Optional, TypedDict, Union

from .canonical import Canonique
from .guardian import Guardian
from .mapping import BilanMapping, mapper_comptes
from .marceau import Marceau


class ErreurMoteur(RuntimeError):
    """Erreur d'orchestration du pipeline."""


class BilanEquilibre(TypedDict):
    """Résultat de l'étape verifier_equilibre (montants en centimes)."""

    nb_lignes: int
    equilibre: bool
    total_debit: int
    total_credit: int
    doublons_ignores: int
    canon: Canonique


class ResultatEtape(TypedDict):
    """Trace d'une étape exécutée : nom, résultat brut, explication."""

    etape: str
    resultat: object
    marceau: str


class ContexteExecution(TypedDict):
    """Bilan d'exécution du pipeline, avec la preuve d'audit Guardian."""

    config: dict[str, Any]
    resultats: list[ResultatEtape]
    empreinte_guardian: str
    audit_valide: bool


ETAPE_DEFAUT = [
    {
        "nom": "importer_fec",
        "module": "core.fec_parser",
        "fonction": "parse_fec",
    },
    {"nom": "verifier_equilibre", "fonction": "verifier_equilibre"},
    {"nom": "lettrer", "module": "core.lettrage", "fonction": "lettrer"},
    {"nom": "rapport", "fonction": "rapport"},
]


def verifier_equilibre(canon: Canonique) -> BilanEquilibre:
    """Étape pipeline : équilibre débit/crédit à 0 centime près.

    Rôle : contrôle de la tolérance Concordance (0,00 EUR).
    Paramètres : canon, journal canonique importé.
    Retour : BilanEquilibre (le journal est transmis sous la clé 'canon').
    Erreurs : aucune (un déséquilibre est signalé par equilibre=False).
    Usages : MoteurConcorde._verifier_equilibre,
    scripts/export_odoo_online.py.
    """
    equilibre = canon.est_equilibre(tolerance=0)
    return {
        "nb_lignes": len(canon),
        "equilibre": equilibre,
        "total_debit": canon.total_debit,
        "total_credit": canon.total_credit,
        "doublons_ignores": canon.doublons_ignores,
        "canon": canon,
    }


def rapport(contexte: object) -> dict[str, object]:
    """Étape pipeline : extrait les statistiques du résultat précédent.

    Accepte le tuple (paires, anomalies, stats) du lettrage ou un dict ;
    retourne {'stats': ...} ({} si rien d'exploitable).
    """
    if isinstance(contexte, tuple) and len(contexte) == 3:
        contexte = contexte[2]  # (paires, anomalies, stats)
    stats = (
        contexte.get("stats", contexte) if isinstance(contexte, dict) else {}
    )
    return {"stats": stats}


class MoteurConcorde:
    """Pipeline : import FEC -> équilibre -> mapping -> lettrage -> rapport."""

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        guardian: Optional[Guardian] = None,
        marceau: Optional[Marceau] = None,
    ) -> None:
        """Prépare le pipeline (config YAML) ; Guardian self-checké d'abord.

        config : configuration YAML chargée (contenu dynamique, d'où Any) ;
        le Guardian est lu sous noyau.guardian, comme dans concorde.yaml.
        """
        self.config: dict[str, Any] = config or {}
        config_guardian = self.config.get("noyau", {}).get("guardian", {})
        self.guardian = guardian or Guardian(
            journal_dir=config_guardian.get(
                "journal", "/var/concorde/guardian"
            )
        )
        if not self.guardian.self_check_ok:
            self.guardian.self_check()
        self.marceau = marceau or Marceau()
        self.pipeline: list[dict[str, str]] = (
            self.config.get("pipeline") or ETAPE_DEFAUT
        )

    def _resoudre(self, etape: dict[str, str]) -> Callable[..., object]:
        """Résout une étape no-code YAML en fonction python exécutable."""
        if "module" in etape:
            mod = importlib.import_module(etape["module"])
            fonction_module: Callable[..., object] = getattr(
                mod, etape["fonction"]
            )
            return fonction_module
        fonction_interne: Callable[..., object] = getattr(
            self, "_" + etape["fonction"]
        )
        return fonction_interne

    def _verifier_equilibre(self, donnees: Canonique) -> BilanEquilibre:
        """Étape interne 'verifier_equilibre' (voir verifier_equilibre)."""
        return verifier_equilibre(donnees)

    def _rapport(self, donnees: object) -> dict[str, object]:
        """Étape interne 'rapport' (voir rapport)."""
        return rapport(donnees)

    def _mapper_comptes(
        self, donnees: Union[Canonique, dict[str, Any]]
    ) -> BilanMapping:
        """Étape interne 'mapper_comptes' : mapping de la configuration."""
        cfg = self.config.get("mapping") or {}
        if isinstance(cfg.get("dict"), dict):
            # mapping charge en memoire (ex. fichier Mapping Quadra Odoo.xlsx
            # uploadé dans l'assistant) : prioritaire sur le fichier JSON.
            return mapper_comptes(donnees, cfg["dict"])
        return mapper_comptes(donnees, cfg.get("fichier"))

    def executer(self, donnees: object = None) -> ContexteExecution:
        """Exécute le pipeline ; chaque résultat porte son explication.

        Chaque étape passe par Guardian et reçoit le résultat de la
        précédente ; le bilan porte l'empreinte et la validité de l'audit.
        """
        resultats: list[ResultatEtape] = []
        courant = donnees
        for etape in self.pipeline:
            nom = etape["nom"]
            fonction = self._resoudre(etape)
            if (
                nom == "mapper_comptes"
                and etape.get("fonction") == "mapper_comptes"
            ):
                fonction = self._mapper_comptes
            resultat = self.guardian.envelopper_etape(nom, fonction, courant)
            explication = self.marceau.expliquer_etape(nom, resultat)
            resultats.append(
                {"etape": nom, "resultat": resultat, "marceau": explication}
            )
            courant = resultat
        return {
            "config": self.config,
            "resultats": resultats,
            "empreinte_guardian": self.guardian.empreinte_courante(),
            "audit_valide": self.guardian.verifier_chaine(),
        }
