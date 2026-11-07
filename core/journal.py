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
from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Literal, TypedDict

NIVEAUX = ("etape", "ok", "info", "detail", "alerte", "erreur")


class Evenement(TypedDict):
    """Un événement du journal : horodatage ISO, niveau et message."""

    t: str
    niveau: str
    message: str


def duree_texte(secondes: float) -> str:
    """Formate une durée en texte lisible (ms, secondes ou minutes).

    Rôle : rendre une durée mesurée lisible par un humain.
    Paramètres : secondes — durée en secondes (>= 0).
    Retour : « 250 ms », « 5,2 s » ou « 3 min 07 s ».
    Erreurs : aucune.
    Usages : `_Etape.__exit__`, `core.odoo_source`, `core.bases_locales`,
    `interface.serveur`.
    """
    if secondes < 1:
        return "%d ms" % round(secondes * 1000)
    if secondes < 60:
        return ("%.1f s" % secondes).replace(".", ",")
    return "%d min %02d s" % divmod(round(secondes), 60)


def nombre_texte(nombre: float) -> str:
    """Formate un nombre avec séparateur de milliers (espace fine insécable).

    Rôle : afficher les compteurs du journal (153765 -> « 153 765 »).
    Paramètres : nombre — entier ou décimal à formater.
    Retour : le texte formaté.
    Erreurs : aucune.
    Usages : `core.odoo_source`, `core.comparaison`, `core.passerelle`,
    `core.comptes`, `core.migration.*`, `interface.serveur`.
    """
    return "{:,}".format(nombre).replace(",", " ")


class _Etape:
    """Étape chronométrée du journal, utilisée comme gestionnaire `with`."""

    def __init__(self, journal: "Journal", nom: str) -> None:
        """Mémorise le journal, le nom de l'étape et l'heure de début."""
        self.journal, self.nom = journal, nom
        self.conclusion = ""
        self.debut = time.monotonic()

    def conclure(self, texte: str) -> None:
        """Enregistre la conclusion affichée à la fin de l'étape."""
        self.conclusion = texte

    def __enter__(self) -> "_Etape":
        """Annonce le début de l'étape dans le journal."""
        self.journal.dire("%s…" % self.nom, "etape")
        return self

    def __exit__(
        self,
        type_exc: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        """Annonce la fin (réussite ou échec) et ne masque aucune exception."""
        d = duree_texte(time.monotonic() - self.debut)
        if exc is not None:
            self.journal.dire(
                "✗ %s — échec : %s (%s)" % (self.nom, exc, d), "erreur"
            )
            return False
        suite = " — %s" % self.conclusion if self.conclusion else ""
        self.journal.dire("✓ %s%s (%s)" % (self.nom, suite, d), "ok")
        return False


class Journal:
    """Journal d'activité borné et sûr entre fils."""

    def __init__(
        self,
        taille_max: int = 2000,
        ecouteur: Callable[[Evenement], object] | None = None,
    ) -> None:
        """Crée un journal vide.

        `taille_max` borne le nombre d'événements gardés ; `ecouteur`
        reçoit chaque nouvel événement (affichage en direct).
        """
        self._evenements: list[Evenement] = []
        self._verrou = threading.Lock()
        self._taille_max = taille_max
        self._decalage = 0  # événements tombés (pour la lecture incrémentale)
        self._ecouteur = ecouteur

    def dire(self, message: str, niveau: str = "info") -> Evenement | None:
        """Ajoute un événement au journal et le transmet à l'écouteur.

        Rôle : point d'entrée unique pour raconter une action.
        Paramètres : message — texte affiché ; niveau — un de `NIVEAUX`
        (sinon « info »).
        Retour : l'événement créé (None pour `JournalMuet`).
        Erreurs : celles levées par l'écouteur.
        Usages : tous les modules de `core` qui reçoivent un journal.
        """
        if niveau not in NIVEAUX:
            niveau = "info"
        ev: Evenement = {
            "t": datetime.now().isoformat(timespec="seconds"),
            "niveau": niveau,
            "message": message,
        }
        with self._verrou:
            self._evenements.append(ev)
            if len(self._evenements) > self._taille_max:
                trop = len(self._evenements) - self._taille_max
                del self._evenements[:trop]
                self._decalage += trop
        if self._ecouteur:
            self._ecouteur(ev)
        return ev

    def etape(self, nom: str) -> _Etape:
        """Ouvre une étape chronométrée (à utiliser avec `with`)."""
        return _Etape(self, nom)

    def depuis(self, index: int = 0) -> tuple[list[Evenement], int]:
        """Rend les événements à partir de `index` (numérotation globale).

        Retour : (événements, index du prochain événement à lire).
        """
        with self._verrou:
            debut = max(0, index - self._decalage)
            evs = list(self._evenements[debut:])
            return evs, self._decalage + len(self._evenements)

    def tout(self) -> list[Evenement]:
        """Rend tous les événements encore gardés."""
        return self.depuis(0)[0]


class JournalMuet(Journal):
    """Journal par défaut des fonctions appelées sans journal : muet."""

    def dire(self, message: str, niveau: str = "info") -> Evenement | None:
        """N'enregistre ni n'affiche rien."""
        return None


def ou_muet(journal: Journal | None) -> Journal:
    """Rend le journal fourni, ou un journal muet s'il est absent.

    Rôle : permettre aux fonctions d'accepter un journal optionnel.
    Paramètres : journal — journal de l'appelant ou None.
    Retour : un `Journal` toujours utilisable.
    Erreurs : aucune.
    Usages : `core.odoo_source`, `core.comparaison`, `core.passerelle`,
    `core.comptes`, `core.bases_locales`, `core.migration.*`.
    """
    return journal if journal is not None else JournalMuet()
