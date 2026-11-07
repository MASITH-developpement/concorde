# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Enchaînement des portes 1 à 5 (sans écriture dans une base) — ADR-0004.

  1 Lecture (connecteur)   2 Filtres   3 Contrôles   4 Correspondance
  5 Export + conformité    6 Test (facultative : base de test)

Chaque porte rend « verte », « bloquée » ou « non jouée ». La porte 5 n'est
jouée que si 1, 3 et 4 sont vertes. Tout est écrit dans le dossier du lot :
  rapport.json, problemes.xlsx, a_arbitrer.xlsx (si besoin), export/…
"""

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, TypedDict

from ..analyser import Constat
from ..guardian import Guardian
from ..journal import Journal, ou_muet
from ..marceau import Marceau
from ..xlsx_ecrire import ecrire_xlsx
from . import controles, correspondance, export, filtres
from .connecteur_fec import ErreurConnecteur, lire_fec
from .filtres import RetraitFiltre
from .lot import SourceLot, TotauxLot

if TYPE_CHECKING:
    from .injection import CibleTest, ResultatEnvoi

PORTES = (
    "lecture",
    "filtres",
    "controles",
    "correspondance",
    "export",
    "test",
)
_marceau = Marceau()


class StatutPorte(TypedDict):
    """Partie toujours présente de l'état d'une porte : son statut."""

    statut: str


class EtatPorte(StatutPorte, total=False):
    """État d'une porte dans le rapport du lot (statut et détails)."""

    erreur: str
    totaux: TotauxLot
    illisibles: int
    avant: TotauxLot
    apres: TotauxLot
    filtres: list[RetraitFiltre]
    infos: dict[str, Any]  # Rapport.infos : valeurs JSON de types variés
    constats: list[dict[str, Any]]
    fichiers: dict[str, str]
    envoi: "ResultatEnvoi"
    relecture: dict[str, Any]  # Rapport.infos de la relecture


class RapportCircuitInitial(TypedDict):
    """Partie du rapport du lot présente dès le début du circuit."""

    source: SourceLot | None
    portes: dict[str, EtatPorte]
    debut: str


class RapportCircuit(RapportCircuitInitial, total=False):
    """Rapport du lot, écrit dans rapport.json (complété en fin de circuit)."""

    statut: str
    fin: str
    empreinte_guardian: str


def _statut(constats: Sequence[Constat]) -> str:
    """« bloquee » si un constat est BLOQUANT, sinon « verte »."""
    return (
        "bloquee"
        if any(c["niveau"] == "BLOQUANT" for c in constats)
        else "verte"
    )


def _constats_expliques(constats: Sequence[Constat]) -> list[dict[str, Any]]:
    """Constats sans leur liste complète, avec l'explication de Marceau."""
    return [
        dict(
            {k: v for k, v in c.items() if k != "elements"},
            explication=_marceau.expliquer_alerte(c["code"], c["message"]),
        )
        for c in constats
    ]


def _vers_json(valeur: object) -> str:
    """Valeur non JSON -> texte (date ISO, sinon str)."""
    return valeur.isoformat() if isinstance(valeur, date) else str(valeur)


def _lignes_problemes(
    tous_constats: Sequence[tuple[str, Constat]],
) -> Iterator[list[object]]:
    """Une ligne de problemes.xlsx par élément de chaque constat.

    Colonnes : porte, niveau, problème, détail, pourquoi, que faire.
    """
    for porte, c in tous_constats:
        explication = _marceau.expliquer_alerte(c["code"])
        for element in c["elements"]:
            yield [
                porte,
                c["niveau"],
                c["message"],
                element,
                explication["pourquoi"],
                explication["que_faire"],
            ]


def executer(
    brut: bytes,
    nom: str,
    dossier: str,
    regles_filtres: Sequence[Mapping[str, Any]] = (),
    table: Mapping[str, str] | None = None,
    identique: bool = False,
    aujourd_hui: date | None = None,
    journal: Journal | None = None,
    tester: bool = False,
    cible: "CibleTest | None" = None,
) -> RapportCircuit:
    """Joue les portes 1 à 5 sur un FEC, puis la porte 6 si `tester`.

    La porte 6 envoie le lot dans la base de test et le relit. Retourne le
    rapport, aussi écrit sur disque (rapport.json).
    """
    j = ou_muet(journal)
    os.makedirs(dossier, exist_ok=True)
    guardian = Guardian()
    guardian.self_check()
    rapport: RapportCircuit = {
        "source": None,
        "portes": {p: {"statut": "non_jouee"} for p in PORTES},
        "debut": datetime.now().isoformat(timespec="seconds"),
    }
    portes = rapport["portes"]
    tous_constats: list[tuple[str, Constat]] = []

    def fin(statut_global: str) -> RapportCircuit:
        """Termine le lot : rapport.json, problemes.xlsx, bilan au journal."""
        rapport["statut"] = statut_global
        rapport["fin"] = datetime.now().isoformat(timespec="seconds")
        rapport["empreinte_guardian"] = guardian.empreinte_courante()
        with open(
            os.path.join(dossier, "rapport.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(
                rapport, f, ensure_ascii=False, indent=1, default=_vers_json
            )
        if tous_constats:
            ecrire_xlsx(
                os.path.join(dossier, "problemes.xlsx"),
                [
                    (
                        "Problemes",
                        (
                            "Porte",
                            "Niveau",
                            "Problème",
                            "Détail",
                            "Pourquoi",
                            "Que faire",
                        ),
                        _lignes_problemes(tous_constats),
                    )
                ],
            )
        j.dire(
            "Bilan du lot : %s"
            % {
                "pret": "PRÊT pour la base de test (porte 6)",
                "teste": "TESTÉ — 0 erreur dans la base de test, prêt pour "
                "la porte 7",
                "bloque": "BLOQUÉ — voir les problèmes",
            }[statut_global],
            "ok" if statut_global in ("pret", "teste") else "erreur",
        )
        return rapport

    # --- Porte 1 : lecture ---------------------------------------------------
    j.dire("Porte 1 — Lecture", "etape")
    try:
        lot = lire_fec(brut, nom, journal=j)
    except ErreurConnecteur as exc:
        portes["lecture"] = {
            "statut": "bloquee",
            "erreur": str(exc),
        }
        j.dire("Fichier illisible : %s" % exc, "erreur")
        return fin("bloque")
    guardian.tracer("migration", "lecture", lot.source["empreinte"])
    rapport["source"] = lot.source
    portes["lecture"] = {
        "statut": "bloquee" if lot.illisibles else "verte",
        "totaux": lot.totaux(),
        "illisibles": len(lot.illisibles),
    }

    # --- Porte 2 : filtres ---------------------------------------------------
    j.dire("Porte 2 — Filtres (%d règle(s))" % len(regles_filtres), "etape")
    try:
        r_f = filtres.appliquer(lot, regles_filtres, journal=j)
        portes["filtres"] = {
            "avant": r_f["avant"],
            "apres": r_f["apres"],
            "filtres": r_f["filtres"],
            "statut": "verte",
        }
    except filtres.ErreurFiltre as exc:
        portes["filtres"] = {
            "statut": "bloquee",
            "erreur": str(exc),
        }
        j.dire(str(exc), "erreur")
        return fin("bloque")

    # --- Porte 3 : contrôles -------------------------------------------------
    j.dire("Porte 3 — Contrôles de migration", "etape")
    r_c = controles.controler(lot, aujourd_hui, journal=j)
    portes["controles"] = {
        "statut": _statut(r_c.constats),
        "infos": r_c.infos,
        "constats": _constats_expliques(r_c.constats),
    }
    tous_constats += [("3 Contrôles", c) for c in r_c.constats]

    # --- Porte 4 : correspondance --------------------------------------------
    j.dire("Porte 4 — Correspondance des comptes", "etape")
    r_m = correspondance.appliquer(lot, table, identique, journal=j)
    a_arb = r_m.infos.get("a_arbitrer") or {}
    if a_arb:
        correspondance.ecrire_a_arbitrer(
            os.path.join(dossier, "a_arbitrer.xlsx"), a_arb
        )
        j.dire(
            "Fichier a_arbitrer.xlsx écrit : %d compte(s) à faire traduire "
            "par le comptable" % len(a_arb),
            "alerte",
        )
    portes["correspondance"] = {
        "statut": _statut(r_m.constats),
        "infos": {k: v for k, v in r_m.infos.items() if k != "a_arbitrer"},
        "constats": _constats_expliques(r_m.constats),
    }
    tous_constats += [("4 Correspondance", c) for c in r_m.constats]

    if "bloquee" in (
        portes["lecture"]["statut"],
        portes["controles"]["statut"],
        portes["correspondance"]["statut"],
    ):
        j.dire(
            "Porte 5 non jouée : des problèmes bloquants restent aux "
            "portes 1, 3 ou 4",
            "alerte",
        )
        return fin("bloque")

    # --- Porte 5 : export et conformité --------------------------------------
    j.dire("Porte 5 — Export et conformité", "etape")
    r_e, fichiers = export.exporter(
        lot, os.path.join(dossier, "export"), journal=j
    )
    portes["export"] = {
        "statut": _statut(r_e.constats),
        "infos": r_e.infos,
        "fichiers": {
            k: os.path.relpath(v, dossier) for k, v in fichiers.items()
        },
        "constats": _constats_expliques(r_e.constats),
    }
    tous_constats += [("5 Export", c) for c in r_e.constats]
    guardian.tracer("migration", "export", portes["export"]["statut"])
    if portes["export"]["statut"] != "verte":
        return fin("bloque")
    if not tester:
        return fin("pret")

    # --- Porte 6 : base de test du serveur -----------------------------------
    from . import injection

    j.dire("Porte 6 — Envoi dans la base de test et relecture", "etape")
    try:
        cible = cible or injection.cible_depuis_env()
        res = injection.envoyer(cible, lot, j)
        r_t = injection.relire(lot, j=j)
    except Exception as exc:
        portes["test"] = {
            "statut": "bloquee",
            "erreur": "%s : %s" % (type(exc).__name__, exc),
        }
        j.dire("Porte 6 impossible : %s" % exc, "erreur")
        return fin("bloque")
    statut = "verte" if not res["erreurs"] and not r_t.constats else "bloquee"
    portes["test"] = {
        "statut": statut,
        "envoi": res,
        "relecture": r_t.infos,
        "constats": _constats_expliques(r_t.constats),
    }
    tous_constats += [("6 Test", c) for c in r_t.constats]
    guardian.tracer(
        "migration", "test", "%s erreurs=%d" % (statut, len(res["erreurs"]))
    )
    return fin("teste" if statut == "verte" else "bloque")
