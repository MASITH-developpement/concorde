# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Authentification de l'interface : un utilisateur, mot de passe haché (scrypt).

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
from datetime import datetime

N, R, P = 2**15, 8, 1
INACTIVITE_MAX = 3600
DUREE_MAX = 10 * 3600
ECHECS_MAX = 5
FENETRE_ECHECS = 900


def hacher(mdp):
    """Empreinte « scrypt$N$r$p$sel$hash » d'un mot de passe."""
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(
        mdp.encode("utf-8"), salt=sel, n=N, r=R, p=P, maxmem=2**26
    )
    return "scrypt$%d$%d$%d$%s$%s" % (N, R, P, sel.hex(), h.hex())


def verifier(mdp, empreinte):
    """Comparaison en temps constant. False si l'empreinte est absente ou invalide."""
    try:
        algo, n, r, p, sel, attendu = (empreinte or "").split("$")
        if algo != "scrypt":
            return False
        h = hashlib.scrypt(
            mdp.encode("utf-8"),
            salt=bytes.fromhex(sel),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=2**26,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h.hex(), attendu)


class Sessions:
    def __init__(self, horloge=time.monotonic):
        self._horloge = horloge
        self._sessions = {}  # jeton -> (création, dernière activité)
        self._echecs = {}  # ip -> [horodatages]
        self.historique_echecs = deque(
            maxlen=1000
        )  # (date ISO, ip) pour la surveillance
        self._verrou = threading.Lock()

    # --- anti-force brute ------------------------------------------------------
    def bloquee(self, ip):
        maintenant = self._horloge()
        with self._verrou:
            recents = [
                t
                for t in self._echecs.get(ip, [])
                if maintenant - t < FENETRE_ECHECS
            ]
            self._echecs[ip] = recents
            return len(recents) >= ECHECS_MAX

    def echec(self, ip):
        with self._verrou:
            self._echecs.setdefault(ip, []).append(self._horloge())
            self.historique_echecs.append(
                (datetime.now().isoformat(timespec="seconds"), ip)
            )

    # --- sessions -------------------------------------------------------------
    def ouvrir(self, ip):
        jeton = secrets.token_urlsafe(32)
        maintenant = self._horloge()
        with self._verrou:
            self._echecs.pop(ip, None)
            self._sessions[jeton] = (maintenant, maintenant)
        return jeton

    def valide(self, jeton):
        if not jeton:
            return False
        maintenant = self._horloge()
        with self._verrou:
            s = self._sessions.get(jeton)
            if s is None:
                return False
            creation, activite = s
            if (
                maintenant - activite > INACTIVITE_MAX
                or maintenant - creation > DUREE_MAX
            ):
                del self._sessions[jeton]
                return False
            self._sessions[jeton] = (creation, maintenant)
            return True

    def fermer(self, jeton):
        with self._verrou:
            self._sessions.pop(jeton, None)
