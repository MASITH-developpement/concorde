# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Soldes cumulés à la date de fin, pour les règles de solde (ADR-0017).

Le solde cumulé d'un compte additionne ses écritures comptabilisées
(brouillons exclus) datées au plus tard à la date de fin :

  comptes de bilan    depuis l'origine, ou depuis la dernière écriture
                      d'à-nouveaux comptabilisée (l'historique antérieur
                      est alors écarté : l'ouverture n'est jamais comptée
                      deux fois) ;
  comptes de gestion  depuis le début de l'exercice qui contient la date
                      de fin (fin d'exercice lue dans la société Odoo).

Lecture seule. Montants en centimes.
"""

import calendar
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any, TypedDict

from .journal import nombre_texte
from .odoo_source import Enregistrement, SourceOdoo

# Comptes Odoo de gestion (solde remis à zéro à chaque exercice).
TYPES_GESTION = (
    "income",
    "income_other",
    "expense",
    "expense_depreciation",
    "expense_direct_cost",
)

# (compte, tiers_id) : clé des soldes par tiers.
CleTiers = tuple[str, int | None]


class SoldeTiers(TypedDict):
    """Solde d'un tiers sur un compte : mouvements de la période et cumul."""

    compte: str
    tiers_id: int | None
    tiers_nom: str
    tiers_ref: str
    periode: int
    cumul: int


class CalculSoldes(TypedDict):
    """Résultat du calcul des soldes cumulés d'une analyse."""

    cumul_comptes: dict[str, int]
    tiers: list[SoldeTiers]
    depart_bilan: date | None
    infos: dict[str, Any]
    ouvertures: list[str]


def debut_exercice(jour: date, mois_fin: int, jour_fin: int) -> date:
    """Premier jour de l'exercice qui contient `jour`.

    Rôle : borne de départ du cumul des comptes de gestion.
    Paramètres : jour ; mois_fin, jour_fin — dernier jour de l'exercice
    (`fiscalyear_last_month`, `fiscalyear_last_day` d'Odoo), ramené au
    dernier jour du mois s'il le dépasse (29 février).
    Retour : le lendemain de la fin de l'exercice précédent.
    Erreurs : ValueError si mois_fin n'est pas entre 1 et 12.
    Usages : `calculer_soldes`, tests.
    """

    def fin_en(annee: int) -> date:
        """Dernier jour de l'exercice qui se termine dans `annee`."""
        dernier = calendar.monthrange(annee, mois_fin)[1]
        return date(annee, mois_fin, min(jour_fin, dernier))

    fin = fin_en(jour.year)
    if jour > fin:
        return fin + timedelta(days=1)
    return fin_en(jour.year - 1) + timedelta(days=1)


def est_compte_gestion(code: str, type_compte: str) -> bool:
    """Dit si un compte est un compte de gestion (charges ou produits).

    Paramètres : code ; type_compte, account_type Odoo ('' si inconnu, le
    préfixe 6 ou 7 décide alors).
    Usages : `calculer_soldes`.
    """
    if type_compte:
        return type_compte in TYPES_GESTION
    return code[:1] in ("6", "7")


def _date_texte(jour: date | None) -> str:
    """Date au format JJ/MM/AAAA ('origine' si None)."""
    return jour.strftime("%d/%m/%Y") if jour else "l'origine"


def _par_cle(soldes: Iterable[Mapping[str, Any]]) -> dict[CleTiers, Any]:
    """Indexe des soldes par (compte, tiers)."""
    return {(solde["compte"], solde["tiers_id"]): solde for solde in soldes}


def _lignes(soldes: Iterable[Mapping[str, Any]], codes: set[str]) -> int:
    """Nombre de lignes des soldes portant sur `codes`."""
    return sum(solde["lignes"] for solde in soldes if solde["compte"] in codes)


def calculer_soldes(
    source: SourceOdoo,
    du: date | None,
    au: date | None,
    comptes: Sequence[Mapping[str, Any]],
    journaux_a_nouveaux: Sequence[str],
    aujourd_hui: date,
    parametres: Mapping[str, Any],
) -> CalculSoldes:
    """Calcule les soldes cumulés à la date de fin, par compte et par tiers.

    Rôle : base des règles de solde de l'analyse (ADR-0017).
    Paramètres : source Odoo ; période du / au (au None : sans borne de
    fin, l'exercice est alors celui d'`aujourd_hui`) ; comptes — plan
    (clés code, type) ; journaux_a_nouveaux — codes des journaux
    d'à-nouveaux ; parametres — `source.parametres_comptables()`.
    Retour : CalculSoldes — cumul par compte, soldes par tiers (période et
    cumul), départ du cumul des comptes de bilan, infos du rapport,
    éléments du constat OUVERTURE_DOUBLE_POSSIBLE.
    Erreurs : celles de la source.
    Usages : passerelle.analyser_source.
    """
    depart_gestion = debut_exercice(
        au or aujourd_hui,
        parametres["fin_exercice_mois"],
        parametres["fin_exercice_jour"],
    )
    ouvertures = source.ecritures_ouverture(journaux_a_nouveaux, au)
    validees = [
        ouverture
        for ouverture in ouvertures
        if ouverture["etat"] == "posted" and ouverture["date"]
    ]
    depart_bilan = max(
        (ouverture["date"] for ouverture in validees), default=None
    )

    lectures: dict[tuple[date | None, date | None], list[Enregistrement]] = {}

    def lire(depuis: date | None) -> list[Enregistrement]:
        """Soldes de `depuis` à la date de fin (une lecture par fenêtre)."""
        if (depuis, au) not in lectures:
            lectures[(depuis, au)] = source.soldes(depuis, au)
        return lectures[(depuis, au)]

    gestion = {
        compte["code"]
        for compte in comptes
        if est_compte_gestion(compte["code"], compte.get("type") or "")
    }
    periode = lire(du)
    cumul_bilan = [
        solde for solde in lire(depart_bilan) if solde["compte"] not in gestion
    ]
    cumul_gestion = [
        solde for solde in lire(depart_gestion) if solde["compte"] in gestion
    ]
    tous = {solde["compte"] for solde in periode} | {
        solde["compte"] for solde in cumul_bilan + cumul_gestion
    }
    bilan = tous - gestion

    cumul = _par_cle(cumul_bilan + cumul_gestion)
    mouvements = _par_cle(periode)
    tiers: list[SoldeTiers] = []
    cumul_comptes: dict[str, int] = {}
    for cle in sorted(
        set(cumul) | set(mouvements),
        key=lambda cle_solde: (cle_solde[0], cle_solde[1] or 0),
    ):
        solde_cumul, solde_periode = cumul.get(cle), mouvements.get(cle)
        nom = solde_cumul or solde_periode or {}
        valeur = (
            solde_cumul["debit"] - solde_cumul["credit"] if solde_cumul else 0
        )
        cumul_comptes[cle[0]] = cumul_comptes.get(cle[0], 0) + valeur
        tiers.append(
            {
                "compte": cle[0],
                "tiers_id": cle[1],
                "tiers_nom": nom.get("tiers_nom", ""),
                "tiers_ref": nom.get("tiers_ref", ""),
                "periode": (
                    solde_periode["debit"] - solde_periode["credit"]
                    if solde_periode
                    else 0
                ),
                "cumul": valeur,
            }
        )

    ecart = (
        _lignes(cumul_bilan, bilan)
        - _lignes(periode, bilan)
        + _lignes(cumul_gestion, gestion)
        - _lignes(periode, gestion)
    )
    brouillons = [
        ouverture for ouverture in ouvertures if ouverture["etat"] != "posted"
    ]
    infos: dict[str, Any] = {
        "mode": "solde cumulé à la date de fin",
        "explication": (
            "Solde cumulé au %s : comptes de bilan depuis %s%s, comptes de "
            "gestion depuis le %s (début d'exercice) ; écritures "
            "comptabilisées seulement, brouillons exclus."
            % (
                _date_texte(au) if au else "dernière écriture",
                _date_texte(depart_bilan),
                (
                    " (à-nouveaux comptabilisé)"
                    if depart_bilan
                    else " (aucun à-nouveaux comptabilisé)"
                ),
                _date_texte(depart_gestion),
            )
        ),
        "date_fin": au,
        "comptes_bilan_depuis": depart_bilan,
        "comptes_gestion_depuis": depart_gestion,
        "a_nouveaux_comptabilises": [
            ouverture["nom"] for ouverture in validees
        ],
        "a_nouveaux_brouillons_ignores": [
            ouverture["nom"] for ouverture in brouillons
        ],
        "lignes_anterieures_prises": max(ecart, 0),
        "lignes_periode_ecartees": max(-ecart, 0),
        "journal_tva_encaissements": parametres["journal_caba"],
    }
    return {
        "cumul_comptes": cumul_comptes,
        "tiers": tiers,
        "depart_bilan": depart_bilan,
        "infos": infos,
        "ouvertures": _ouvertures_doubles(source, ouvertures, depart_bilan),
    }


def _ouvertures_doubles(
    source: SourceOdoo,
    ouvertures: Sequence[Mapping[str, Any]],
    depart_bilan: date | None,
) -> list[str]:
    """Éléments du constat OUVERTURE_DOUBLE_POSSIBLE.

    Rôle : signaler chaque écriture d'à-nouveaux (à partir de celle qui
    sert de départ) précédée d'écritures comptabilisées, et dire laquelle
    des deux est comptée.
    Paramètres : source ; ouvertures (`ecritures_ouverture`) ;
    depart_bilan, date de l'à-nouveaux comptabilisé retenu (ou None).
    Retour : un texte par écriture concernée.
    Erreurs : celles de la source.
    Usages : `calculer_soldes`.
    """
    res = []
    for ouverture in ouvertures:
        if not ouverture["date"] or (
            depart_bilan and ouverture["date"] < depart_bilan
        ):
            continue
        nombre = source.nombre_lignes_avant(ouverture["date"])
        if not nombre:
            continue
        if ouverture["etat"] == "posted":
            choix = (
                "comptabilisée : l'à-nouveaux est compté, les %s lignes "
                "antérieures sont écartées pour les comptes de bilan"
            )
        else:
            choix = (
                "brouillon : l'à-nouveaux n'est pas compté, les %s lignes "
                "comptabilisées antérieures le sont"
            )
        res.append(
            "%s du %s (journal %s), %s"
            % (
                (
                    ouverture["nom"]
                    if ouverture["nom"] not in ("", "/")
                    else "brouillon id %s" % ouverture["id"]
                ),
                _date_texte(ouverture["date"]),
                ouverture["journal"],
                choix % nombre_texte(nombre),
            )
        )
    return res
