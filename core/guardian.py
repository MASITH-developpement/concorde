# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""GUARDIAN — surveillance invisible, 100 % déterministe, zéro LLM.

- self_check() bloquant au démarrage : le moteur refuse de tourner sans lui
- envelopper_etape() : chaque étape du pipeline est tracée et protégée
- Audit chaîné SHA-256 : toute altération du journal casse la chaîne
- Rate limiting invisible : un flux anormal est bloqué sans message visible
"""

import hashlib
import json
import time
from typing import Callable, Optional, ParamSpec, TypedDict, TypeVar

_Parametres = ParamSpec("_Parametres")
_Resultat = TypeVar("_Resultat")


class ErreurGuardian(RuntimeError):
    """Refus Guardian : self-check en échec ou flux anormal."""


class MaillonAudit(TypedDict):
    """Un maillon de la chaîne d'audit : événement JSON et son empreinte."""

    charge: str
    empreinte: str


def _empreinte_maillon(precedente: str, charge: str) -> str:
    """Empreinte SHA-256 d'un maillon, chaînée à la précédente.

    Rôle : calcul unique de la chaîne d'audit (écriture et vérification).
    Paramètres : precedente, empreinte du maillon précédent ('GENESIS'
    au départ) ; charge, événement JSON du maillon.
    Retour : empreinte hexadécimale.
    Erreurs : aucune.
    Usages : Guardian._hash, Guardian._derniere_empreinte_valide.
    """
    return hashlib.sha256(
        (precedente + "|" + charge).encode("utf-8")
    ).hexdigest()


class Guardian:
    """Surveillance déterministe : self-check, audit chaîné, rate limit."""

    VERSION = "1.0"

    def __init__(self, journal_dir: str = "/var/concorde/guardian") -> None:
        """Crée un Guardian à chaîne vide ; self-check à faire avant usage."""
        self.journal_dir = journal_dir
        self.self_check_ok = False
        self._chain = "GENESIS"
        self._audit: list[MaillonAudit] = []
        self._horodatages: list[float] = []

    # --- chaîne d'audit -----------------------------------------------------
    def _hash(self, charge: str) -> str:
        """Empreinte du prochain maillon (chaînée à la courante)."""
        return _empreinte_maillon(self._chain, charge)

    def _derniere_empreinte_valide(self) -> Optional[str]:
        """Dernière empreinte recalculée, ou None si un maillon est altéré.

        Rôle : recalcule toute la chaîne d'audit depuis 'GENESIS'.
        Paramètres : aucun.
        Retour : empreinte du dernier maillon ('GENESIS' si vide), None
        dès qu'un maillon ne correspond pas à son empreinte.
        Erreurs : aucune.
        Usages : self_check, verifier_chaine.
        """
        empreinte = "GENESIS"
        for maillon in self._audit:
            attendu = _empreinte_maillon(empreinte, maillon["charge"])
            if attendu != maillon["empreinte"]:
                return None
            empreinte = attendu
        return empreinte

    def tracer(self, etape: str, statut: str = "ok", detail: str = "") -> str:
        """Trace un événement dans l'audit chaîné (rate limiting invisible)."""
        maintenant = time.monotonic()
        self._horodatages = [
            t for t in self._horodatages if maintenant - t < 1.0
        ]
        self._horodatages.append(maintenant)
        if len(self._horodatages) > 200:
            raise ErreurGuardian("Flux anormal détecté (rate limit Guardian).")
        charge = json.dumps(
            {
                "etape": etape,
                "statut": statut,
                "detail": detail,
                "t": round(time.time(), 3),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        empreinte = self._hash(charge)
        self._audit.append({"charge": charge, "empreinte": empreinte})
        self._chain = empreinte
        return empreinte

    # --- self-check ---------------------------------------------------------
    def self_check(self) -> bool:
        """Vérification bloquante au démarrage ; ErreurGuardian si échec."""
        # 1. Intégrité de la chaîne d'audit existante
        if self._derniere_empreinte_valide() is None:
            raise ErreurGuardian("Self-check : chaîne d'audit altérée.")
        # 2. Invariant des centimes (int, jamais float)
        from .canonical import vers_centimes, ErreurMontant

        if vers_centimes("1 234,56") != 123456:
            raise ErreurGuardian(
                "Self-check : conversion centimes défaillante."
            )
        try:
            vers_centimes("1,234")
            raise ErreurGuardian("Self-check : arrondi silencieux non refusé.")
        except ErreurMontant:
            pass
        # 3. SHA-256 déterministe
        if (
            hashlib.sha256(b"concorde").hexdigest()
            != hashlib.sha256(b"concorde").hexdigest()
        ):
            raise ErreurGuardian("Self-check : SHA-256 non déterministe.")
        self.self_check_ok = True
        self.tracer("guardian", "self_check", "OK v%s" % self.VERSION)
        return True

    # --- enveloppement des étapes --------------------------------------------
    def envelopper_etape(
        self,
        nom: str,
        fonction: Callable[_Parametres, _Resultat],
        *args: _Parametres.args,
        **kwargs: _Parametres.kwargs,
    ) -> _Resultat:
        """Exécute une étape du pipeline sous protection Guardian.

        Rôle : self-check si besoin, trace l'étape (durée ou erreur).
        Paramètres : nom de l'étape, fonction et ses arguments.
        Retour : le résultat de fonction.
        Erreurs : ErreurGuardian (self-check, rate limit) ; toute
        exception de fonction est tracée puis relancée.
        Usages : moteur.MoteurConcorde.executer, injectors, interface.
        """
        if not self.self_check_ok:
            self.self_check()
        debut = time.monotonic()
        try:
            resultat = fonction(*args, **kwargs)
        except Exception as e:
            self.tracer(nom, "erreur", "%s: %s" % (type(e).__name__, e))
            raise
        duree_ms = round((time.monotonic() - debut) * 1000.0, 3)
        self.tracer(nom, "ok", "duree_ms=%s" % duree_ms)
        return resultat

    # --- accès audit ---------------------------------------------------------
    def empreinte_courante(self) -> str:
        """Empreinte du dernier maillon de la chaîne d'audit."""
        return self._chain

    def verifier_chaine(self) -> bool:
        """Re-vérifie toute la chaîne d'audit (anti-tamper)."""
        derniere = self._derniere_empreinte_valide()
        return derniere is not None and derniere == self._chain
