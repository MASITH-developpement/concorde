# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Authentification de l'interface : un utilisateur, mot de passe haché.

- Le mot de passe n'est jamais stocké : seule son empreinte scrypt l'est,
  dans la variable CONCORDE_UI_MDP (fichier d'environnement root, mode 600).
- Session : jeton aléatoire de 256 bits, en mémoire, expire après 1 h
  d'inactivité et 10 h au plus. Un redémarrage du service déconnecte.
- Anti-force brute : 5 échecs en 15 min par adresse IP = blocage 15 min.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

N, R, P = 2**15, 8, 1
INACTIVITE_MAX = 3600
DUREE_MAX = 10 * 3600
ECHECS_MAX = 5
FENETRE_ECHECS = 900


def hacher(mdp: str) -> str:
    """Empreinte « scrypt$N$r$p$sel$hash » d'un mot de passe.

    Rôle : produire l'empreinte stockée dans CONCORDE_UI_MDP.
    Paramètres : mdp, le mot de passe en clair.
    Retour : l'empreinte texte (sel aléatoire de 16 octets, en hexadécimal).
    Erreurs : ValueError de hashlib si les paramètres N, R, P sont invalides.
    Usages : scripts/concorde_interface_mdp.py, tests/test_interface.py.
    """
    sel = secrets.token_bytes(16)
    empreinte_brute = hashlib.scrypt(
        mdp.encode("utf-8"), salt=sel, n=N, r=R, p=P, maxmem=2**26
    )
    return "scrypt$%d$%d$%d$%s$%s" % (
        N,
        R,
        P,
        sel.hex(),
        empreinte_brute.hex(),
    )


def verifier(mdp: str, empreinte: str | None) -> bool:
    """Compare un mot de passe à son empreinte, en temps constant.

    Rôle : contrôler le mot de passe saisi à la connexion.
    Paramètres : mdp, le mot de passe saisi ; empreinte, celle de hacher().
    Retour : True si le mot de passe correspond, False sinon.
    Erreurs : aucune — une empreinte absente ou invalide rend False.
    Usages : interface/serveur.py (connexion), tests/test_interface.py.
    """
    try:
        algo, n, r, p, sel, attendu = (empreinte or "").split("$")
        if algo != "scrypt":
            return False
        empreinte_brute = hashlib.scrypt(
            mdp.encode("utf-8"),
            salt=bytes.fromhex(sel),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=2**26,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(empreinte_brute.hex(), attendu)


class Sessions:
    """Sessions ouvertes et échecs de connexion, en mémoire, sous verrou."""

    def __init__(self, horloge: Callable[[], float] = time.monotonic) -> None:
        """Prépare des sessions vides ; horloge est remplaçable en test."""
        self._horloge = horloge
        # jeton -> (création, dernière activité)
        self._sessions: dict[str, tuple[float, float]] = {}
        self._echecs: dict[str, list[float]] = {}  # ip -> [horodatages]
        # (date ISO, ip) pour la surveillance
        self.historique_echecs: deque[tuple[str, str]] = deque(maxlen=1000)
        self._verrou = threading.Lock()

    # --- anti-force brute ----------------------------------------------------
    def bloquee(self, ip: str) -> bool:
        """Vrai si l'adresse a cumulé trop d'échecs dans la fenêtre."""
        maintenant = self._horloge()
        with self._verrou:
            recents = [
                instant
                for instant in self._echecs.get(ip, [])
                if maintenant - instant < FENETRE_ECHECS
            ]
            self._echecs[ip] = recents
            return len(recents) >= ECHECS_MAX

    def echec(self, ip: str) -> None:
        """Enregistre un mot de passe refusé pour cette adresse."""
        with self._verrou:
            self._echecs.setdefault(ip, []).append(self._horloge())
            self.historique_echecs.append(
                (datetime.now().isoformat(timespec="seconds"), ip)
            )

    # --- sessions ------------------------------------------------------------
    def ouvrir(self, ip: str) -> str:
        """Ouvre une session (échecs de l'adresse effacés) ; rend le jeton."""
        jeton = secrets.token_urlsafe(32)
        maintenant = self._horloge()
        with self._verrou:
            self._echecs.pop(ip, None)
            self._sessions[jeton] = (maintenant, maintenant)
        return jeton

    def valide(self, jeton: str | None) -> bool:
        """Vrai si la session vit encore ; prolonge alors son activité."""
        if not jeton:
            return False
        maintenant = self._horloge()
        with self._verrou:
            session = self._sessions.get(jeton)
            if session is None:
                return False
            creation, activite = session
            if (
                maintenant - activite > INACTIVITE_MAX
                or maintenant - creation > DUREE_MAX
            ):
                del self._sessions[jeton]
                return False
            self._sessions[jeton] = (creation, maintenant)
            return True

    def fermer(self, jeton: str | None) -> None:
        """Ferme la session (sans effet si le jeton est inconnu ou absent)."""
        if jeton is None:
            return
        with self._verrou:
            self._sessions.pop(jeton, None)
