# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Journal d'activité : CONCORDE raconte ce qu'il fait, étape par étape.

Chaque événement : {t (horodatage ISO), niveau, message}.
Niveaux : etape (début d'une étape), ok, info, detail, alerte, erreur.

    j = Journal()
    j.dire("Connexion à testalbhade…")
    with j.etape("Lecture des écritures") as e:
        ...
        e.conclure("153 765 lignes")
        # -> « ✓ Lecture des écritures — 153 765 lignes (5,2 s) »

Le journal est sûr entre fils (l'interface le lit pendant qu'une tâche écrit)
et borné (les plus anciens événements tombent au-delà de `taille_max`).
"""
import threading
import time
from datetime import datetime

NIVEAUX = ("etape", "ok", "info", "detail", "alerte", "erreur")


def duree_texte(secondes):
    if secondes < 1:
        return "%d ms" % round(secondes * 1000)
    if secondes < 60:
        return ("%.1f s" % secondes).replace(".", ",")
    return "%d min %02d s" % divmod(round(secondes), 60)


def nombre_texte(n):
    """153765 -> '153 765' (espace fine insécable)."""
    return "{:,}".format(n).replace(",", " ")


class _Etape:
    def __init__(self, journal, nom):
        self.journal, self.nom = journal, nom
        self.conclusion = ""
        self.debut = time.monotonic()

    def conclure(self, texte):
        self.conclusion = texte

    def __enter__(self):
        self.journal.dire("%s…" % self.nom, "etape")
        return self

    def __exit__(self, type_exc, exc, tb):
        d = duree_texte(time.monotonic() - self.debut)
        if exc is not None:
            self.journal.dire("✗ %s — échec : %s (%s)" % (self.nom, exc, d), "erreur")
            return False
        suite = " — %s" % self.conclusion if self.conclusion else ""
        self.journal.dire("✓ %s%s (%s)" % (self.nom, suite, d), "ok")
        return False


class Journal:
    def __init__(self, taille_max=2000, ecouteur=None):
        self._evenements = []
        self._verrou = threading.Lock()
        self._taille_max = taille_max
        self._decalage = 0          # événements tombés (pour la lecture incrémentale)
        self._ecouteur = ecouteur

    def dire(self, message, niveau="info"):
        if niveau not in NIVEAUX:
            niveau = "info"
        ev = {"t": datetime.now().isoformat(timespec="seconds"), "niveau": niveau,
              "message": message}
        with self._verrou:
            self._evenements.append(ev)
            if len(self._evenements) > self._taille_max:
                trop = len(self._evenements) - self._taille_max
                del self._evenements[:trop]
                self._decalage += trop
        if self._ecouteur:
            self._ecouteur(ev)
        return ev

    def etape(self, nom):
        return _Etape(self, nom)

    def depuis(self, index=0):
        """Événements à partir de `index` (numérotation globale). -> (événements, suivant)."""
        with self._verrou:
            debut = max(0, index - self._decalage)
            evs = list(self._evenements[debut:])
            return evs, self._decalage + len(self._evenements)

    def tout(self):
        return self.depuis(0)[0]


class JournalMuet(Journal):
    """Journal par défaut des fonctions appelées sans journal : n'affiche rien."""

    def dire(self, message, niveau="info"):
        return None


def ou_muet(journal):
    return journal if journal is not None else JournalMuet()
