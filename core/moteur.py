# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""MOTEUR CONCORDE — orchestration du pipeline, no-code 100 % YAML.

- Refuse de démarrer sans Guardian self-checké (noyau obligatoire)
- Chaque étape du pipeline est enveloppée par Guardian (audit + rate limit)
- Chaque donnée produite est liée à son explication Marceau
"""
import importlib

from .guardian import Guardian
from .marceau import Marceau


class ErreurMoteur(RuntimeError):
    pass


ETAPE_DEFAUT = [
    {"nom": "importer_fec", "module": "core.fec_parser", "fonction": "parse_fec"},
    {"nom": "verifier_equilibre", "fonction": "verifier_equilibre"},
    {"nom": "lettrer", "module": "core.lettrage", "fonction": "lettrer"},
    {"nom": "rapport", "fonction": "rapport"},
]


def verifier_equilibre(canon):
    equilibre = canon.est_equilibre(tolerance=0)
    return {"nb_lignes": len(canon), "equilibre": equilibre,
            "total_debit": canon.total_debit, "total_credit": canon.total_credit,
            "doublons_ignores": canon.doublons_ignores, "canon": canon}


def rapport(contexte):
    if isinstance(contexte, tuple) and len(contexte) == 3:
        contexte = contexte[2]  # (paires, anomalies, stats)
    stats = contexte.get("stats", contexte) if isinstance(contexte, dict) else {}
    return {"stats": stats}


class MoteurConcorde:
    """Moteur pipeline : import FEC -> équilibre -> mapping -> lettrage -> rapport."""

    def __init__(self, config=None, guardian=None, marceau=None):
        self.config = config or {}
        self.guardian = guardian or Guardian(
            journal_dir=self.config.get("guardian", {}).get("journal", "/var/concorde/guardian"))
        if not self.guardian.self_check_ok:
            self.guardian.self_check()
        self.marceau = marceau or Marceau()
        self.pipeline = self.config.get("pipeline") or ETAPE_DEFAUT

    def _resoudre(self, etape):
        """Résout une étape no-code YAML en fonction python exécutable."""
        if "module" in etape:
            mod = importlib.import_module(etape["module"])
            return getattr(mod, etape["fonction"])
        return getattr(self, "_" + etape["fonction"])

    def _verifier_equilibre(self, donnees):
        return verifier_equilibre(donnees)

    def _rapport(self, donnees):
        return rapport(donnees)

    def _mapper_comptes(self, donnees):
        from .mapping import mapper_comptes
        cfg = self.config.get("mapping") or {}
        if isinstance(cfg.get("dict"), dict):
            # mapping charge en memoire (ex. fichier Mapping Quadra Odoo.xlsx
            # uploadé dans l'assistant) : prioritaire sur le fichier JSON.
            return mapper_comptes(donnees, cfg["dict"])
        return mapper_comptes(donnees, cfg.get("fichier"))

    def executer(self, donnees=None):
        """Exécute le pipeline complet. Chaque résultat porte son explication Marceau."""
        contexte = {"config": self.config, "resultats": []}
        courant = donnees
        for etape in self.pipeline:
            nom = etape["nom"]
            fonction = self._resoudre(etape)
            if nom == "mapper_comptes" and etape.get("fonction") == "mapper_comptes":
                fonction = self._mapper_comptes
            resultat = self.guardian.envelopper_etape(nom, fonction, courant)
            explication = self.marceau.expliquer_etape(nom, resultat)
            contexte["resultats"].append({"etape": nom, "resultat": resultat,
                                          "marceau": explication})
            courant = resultat
        contexte["empreinte_guardian"] = self.guardian.empreinte_courante()
        contexte["audit_valide"] = self.guardian.verifier_chaine()
        return contexte
