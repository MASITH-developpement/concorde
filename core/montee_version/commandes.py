# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Seul endroit de la montée de version qui lance un programme (git, docker…).

Toujours une liste d'arguments, jamais de shell : aucune valeur ne peut
devenir une commande. La sortie complète va dans un journal sur disque ;
une erreur rend le code de retour et les dernières lignes, nommés.
"""

import subprocess  # lancement de git, docker et cryptsetup (liste d'arguments)
from collections.abc import Sequence
from contextlib import nullcontext
from typing import IO

LIGNES_ERREUR = 12


class ErreurCommande(RuntimeError):
    """Programme en échec : code de retour et fin de sa sortie."""


def executer(
    arguments: Sequence[str],
    journal: str | None = None,
    entree: IO[bytes] | bytes | None = None,
    delai: float | None = None,
) -> str:
    """Lance un programme et attend sa fin.

    Rôle : un seul point de lancement, sans shell, avec un journal.
    Paramètres : arguments — programme puis arguments ; journal —
    fichier où ajouter toute la sortie (sinon gardée en mémoire) ;
    entree — octets ou fichier ouvert donné sur l'entrée standard ;
    delai — secondes au plus (None = sans limite).
    Retour : la sortie (vide si elle est partie dans le journal).
    Erreurs : ErreurCommande si le code de retour n'est pas 0 ou si le
    délai est dépassé (programme et fin de sortie nommés) ; OSError si
    le programme est introuvable.
    Usages : openupgrade.recuperer, montee, volume.
    """
    nom = " ".join(arguments[:2])
    donnees = entree if isinstance(entree, bytes) else None
    flux = None if isinstance(entree, bytes) else entree
    with (
        open(journal, "ab") if journal is not None else nullcontext(None)
    ) as fichier:
        try:
            fini = subprocess.run(
                list(arguments),
                input=donnees,
                stdin=flux,
                stdout=subprocess.PIPE if fichier is None else fichier,
                stderr=subprocess.STDOUT,
                timeout=delai,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ErreurCommande(
                "%s : arrêté après %d s." % (nom, int(delai or 0))
            ) from exc
    sortie = (
        "" if fichier is not None else fini.stdout.decode("utf-8", "replace")
    )
    if fini.returncode != 0:
        raise ErreurCommande(
            "%s : code %d. %s"
            % (nom, fini.returncode, fin_de_sortie(sortie, journal))
        )
    return sortie


def fin_de_sortie(sortie: str, journal: str | None) -> str:
    """Dernières lignes d'une sortie, ou du journal où elle a été écrite.

    Rôle : nommer la cause d'un échec sans recopier tout le journal.
    Paramètres : sortie — texte gardé en mémoire ; journal — fichier.
    Retour : au plus LIGNES_ERREUR lignes, jointes par « | ».
    Erreurs : aucune (journal illisible : la cause est rendue).
    Usages : executer, montee.
    """
    texte = sortie
    if journal is not None:
        try:
            with open(journal, encoding="utf-8", errors="replace") as fichier:
                texte = fichier.read()[-20000:]
        except OSError as exc:
            texte = "(journal illisible : %s)" % exc
    lignes = [ligne for ligne in texte.splitlines() if ligne.strip()]
    return " | ".join(lignes[-LIGNES_ERREUR:])
