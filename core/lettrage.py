# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Lettrage : reconstruction des paires débit/crédit, détection d'anomalies."""

from collections import defaultdict
from typing import Any, TypedDict, Union

from .canonical import Canonique, LigneEcriture, extraire_canon


class PaireLettrage(TypedDict):
    """Une paire lettrée : une ligne au débit, une au crédit, même montant."""

    code: str
    compte: str
    montant: int
    ligne_debit: LigneEcriture
    ligne_credit: LigneEcriture


class StatsLettrage(TypedDict):
    """Statistiques du lettrage d'un journal (montants en centimes)."""

    nb_lignes: int
    nb_paires: int
    nb_anomalies: int
    taux_lettrage: float
    total_debit: int
    total_credit: int


def lettrer(
    canon: Union[Canonique, dict[str, Any]], prefixe: str = "L"
) -> tuple[list[PaireLettrage], list[LigneEcriture], StatsLettrage]:
    """Reconstruit les paires débit/crédit par compte et montant exact.

    Accepte un Canonique ou un dict de pipeline portant la clé 'canon'.
    Retourne (paires, anomalies, stats).
    - paires : liste de {code, ligne_debit, ligne_credit, compte, montant}
    - anomalies : lignes non appariables (montant orphelin)
    Lève ValueError si le dict de pipeline ne porte aucun journal.
    """
    journal_canonique = extraire_canon(canon)
    if journal_canonique is None:
        raise ValueError("Aucun journal canonique à lettrer.")
    par_compte: defaultdict[str, dict[str, list[LigneEcriture]]] = defaultdict(
        lambda: {"debits": [], "credits": []}
    )
    for ligne in journal_canonique.lignes:
        if ligne.debit > 0:
            par_compte[ligne.compte]["debits"].append(ligne)
        elif ligne.credit > 0:
            par_compte[ligne.compte]["credits"].append(ligne)

    paires: list[PaireLettrage] = []
    anomalies: list[LigneEcriture] = []
    compteur = 0
    for compte, dico in par_compte.items():
        credits = list(dico["credits"])
        for ligne_debit in dico["debits"]:
            match = None
            for ligne_credit in credits:
                if ligne_credit.credit == ligne_debit.debit:
                    match = ligne_credit
                    break
            if match is not None:
                credits.remove(match)
                compteur += 1
                code = "%s%05d" % (prefixe, compteur)
                ligne_debit.lettrage = code
                match.lettrage = code
                paires.append(
                    {
                        "code": code,
                        "compte": compte,
                        "montant": ligne_debit.debit,
                        "ligne_debit": ligne_debit,
                        "ligne_credit": match,
                    }
                )
            else:
                anomalies.append(ligne_debit)
        anomalies.extend(credits)

    total = len(journal_canonique.lignes)
    stats: StatsLettrage = {
        "nb_lignes": total,
        "nb_paires": len(paires),
        "nb_anomalies": len(anomalies),
        "taux_lettrage": (100.0 * (2 * len(paires)) / total) if total else 0.0,
        "total_debit": journal_canonique.total_debit,
        "total_credit": journal_canonique.total_credit,
    }
    return paires, anomalies, stats
