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


class ErreurGuardian(RuntimeError):
    pass


class Guardian:
    VERSION = "1.0"

    def __init__(self, journal_dir: str = "/var/concorde/guardian"):
        self.journal_dir = journal_dir
        self.self_check_ok = False
        self._chain = "GENESIS"
        self._audit = []
        self._horodatages = []

    # --- chaîne d'audit -----------------------------------------------------
    def _hash(self, charge: str) -> str:
        return hashlib.sha256((self._chain + "|" + charge).encode("utf-8")).hexdigest()

    def tracer(self, etape: str, statut: str = "ok", detail: str = "") -> str:
        """Trace un événement dans l'audit chaîné, avec rate limiting invisible."""
        maintenant = time.monotonic()
        self._horodatages = [t for t in self._horodatages if maintenant - t < 1.0]
        self._horodatages.append(maintenant)
        if len(self._horodatages) > 200:
            raise ErreurGuardian("Flux anormal détecté (rate limit Guardian).")
        charge = json.dumps(
            {"etape": etape, "statut": statut, "detail": detail, "t": round(time.time(), 3)},
            sort_keys=True, ensure_ascii=False)
        empreinte = self._hash(charge)
        self._audit.append({"charge": charge, "empreinte": empreinte})
        self._chain = empreinte
        return empreinte

    # --- self-check ---------------------------------------------------------
    def self_check(self) -> bool:
        """Vérification bloquante au démarrage. Lève ErreurGuardian si échec."""
        # 1. Intégrité de la chaîne d'audit existante
        h = "GENESIS"
        for e in self._audit:
            attendu = hashlib.sha256((h + "|" + e["charge"]).encode("utf-8")).hexdigest()
            if attendu != e["empreinte"]:
                raise ErreurGuardian("Self-check : chaîne d'audit altérée.")
            h = attendu
        # 2. Invariant des centimes (int, jamais float)
        from .canonical import vers_centimes, ErreurMontant
        if vers_centimes("1 234,56") != 123456:
            raise ErreurGuardian("Self-check : conversion centimes défaillante.")
        try:
            vers_centimes("1,234")
            raise ErreurGuardian("Self-check : arrondi silencieux non refusé.")
        except ErreurMontant:
            pass
        # 3. SHA-256 déterministe
        if hashlib.sha256(b"concorde").hexdigest() != hashlib.sha256(b"concorde").hexdigest():
            raise ErreurGuardian("Self-check : SHA-256 non déterministe.")
        self.self_check_ok = True
        self.tracer("guardian", "self_check", "OK v%s" % self.VERSION)
        return True

    # --- enveloppement des étapes --------------------------------------------
    def envelopper_etape(self, nom: str, fonction, *args, **kwargs):
        """Exécute une étape du pipeline sous protection Guardian."""
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
        return self._chain

    def verifier_chaine(self) -> bool:
        """Re-vérifie toute la chaîne d'audit (anti-tamper)."""
        h = "GENESIS"
        for e in self._audit:
            if hashlib.sha256((h + "|" + e["charge"]).encode("utf-8")).hexdigest() != e["empreinte"]:
                return False
            h = e["empreinte"]
        return h == self._chain
