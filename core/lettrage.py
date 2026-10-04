# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Lettrage : reconstruction des paires débit/crédit et détection d'anomalies."""
from collections import defaultdict

from .canonical import Canonique


def lettrer(canon, prefixe: str = "L"):
    """Reconstruit les paires débit/crédit par compte et par montant exact (centimes).

    Accepte un Canonique ou un dict de pipeline portant la clé 'canon'.
    Retourne (paires, anomalies, stats).
    - paires : liste de {code, ligne_debit, ligne_credit, compte, montant}
    - anomalies : lignes non appariables (montant orphelin)
    """
    if isinstance(canon, dict):
        canon = canon.get("canon") or canon.get("resultat", {}).get("canon")
    par_compte = defaultdict(lambda: {"debits": [], "credits": []})
    for l in canon.lignes:
        if l.debit > 0:
            par_compte[l.compte]["debits"].append(l)
        elif l.credit > 0:
            par_compte[l.compte]["credits"].append(l)

    paires = []
    anomalies = []
    compteur = 0
    for compte, dico in par_compte.items():
        credits = list(dico["credits"])
        for ld in dico["debits"]:
            match = None
            for lc in credits:
                if lc.credit == ld.debit:
                    match = lc
                    break
            if match is not None:
                credits.remove(match)
                compteur += 1
                code = "%s%05d" % (prefixe, compteur)
                ld.lettrage = code
                match.lettrage = code
                paires.append({
                    "code": code, "compte": compte,
                    "montant": ld.debit,
                    "ligne_debit": ld, "ligne_credit": match,
                })
            else:
                anomalies.append(ld)
        anomalies.extend(credits)

    total = len(canon.lignes)
    stats = {
        "nb_lignes": total,
        "nb_paires": len(paires),
        "nb_anomalies": len(anomalies),
        "taux_lettrage": (100.0 * (2 * len(paires)) / total) if total else 0.0,
        "total_debit": canon.total_debit,
        "total_credit": canon.total_credit,
    }
    return paires, anomalies, stats
