# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 4 — correspondance des comptes source -> comptes Odoo.

Règle MASITH : on traduit UNIQUEMENT avec la table arbitrée par le
comptable. Un compte absent de la table n'est jamais deviné : il part dans
un fichier « à arbitrer » (xlsx, colonne « Compte Odoo » à remplir) et la
migration bloque.

Exception explicite : `identique=True` (choix du comptable, tracé dans le
journal et le rapport) garde les numéros de comptes tels quels.

Table acceptée : xlsx (core/mapping.py, colonnes détectées), JSON
{source: cible}, CSV à deux colonnes « source;cible ».
"""

import csv
import io
import json
from collections.abc import Mapping
from typing import TypedDict

from ..analyser import Rapport
from ..journal import Journal, nombre_texte, ou_muet
from ..mapping import charger_mapping_xlsx
from ..xlsx_ecrire import Centimes, ecrire_xlsx
from .lot import Lot


class ErreurTable(ValueError):
    """Table de correspondance illisible (format ou contenu)."""


class CompteAArbitrer(TypedDict):
    """Compte source absent de la table : libellé, lignes et montants."""

    libelle: str
    lignes: int
    debit: int
    credit: int


def charger_table(brut: bytes, nom: str) -> dict[str, str]:
    """Table de correspondance -> {compte source: compte Odoo}.

    Lève ErreurTable si le format n'est pas reconnu ou le JSON n'est pas un
    objet.
    """
    nom_minuscule = nom.lower()
    if nom_minuscule.endswith(".xlsx"):
        return dict(charger_mapping_xlsx(brut, nom))
    texte = brut.decode("utf-8-sig")
    if nom_minuscule.endswith(".json"):
        contenu_json = json.loads(texte)
        if not isinstance(contenu_json, dict):
            raise ErreurTable(
                "Table JSON : objet {compte source: compte Odoo} attendu."
            )
        return {
            str(k).strip(): str(v).strip() for k, v in contenu_json.items()
        }
    if nom_minuscule.endswith(".csv") or nom_minuscule.endswith(".txt"):
        sep = ";" if texte.count(";") >= texte.count(",") else ","
        table: dict[str, str] = {}
        for i, row in enumerate(
            csv.reader(io.StringIO(texte), delimiter=sep), 1
        ):
            if len(row) < 2 or not row[0].strip():
                continue
            if i == 1 and not any(ch.isdigit() for ch in row[0]):
                continue  # ligne d'en-tête
            table[row[0].strip()] = row[1].strip()
        return table
    raise ErreurTable(
        "Format de table non reconnu (xlsx, json ou csv) : %s" % nom
    )


def appliquer(
    lot: Lot,
    table: Mapping[str, str] | None = None,
    identique: bool = False,
    journal: Journal | None = None,
) -> Rapport:
    """Renseigne `compte_cible` sur chaque ligne. Retourne un Rapport."""
    j = ou_muet(journal)
    r = Rapport()
    if identique:
        j.dire(
            "Correspondance : comptes repris À L'IDENTIQUE "
            "(choix explicite du comptable)",
            "alerte",
        )
        for ligne in lot.lignes:
            ligne["compte_cible"] = ligne["compte"]
        r.info("mode", "identique")
        r.info("comptes", len({ligne["compte"] for ligne in lot.lignes}))
        return r
    table = table or {}
    vides = [k for k, v in table.items() if not v]
    a_arbitrer: dict[str, CompteAArbitrer] = {}
    for ligne in lot.lignes:
        cible = table.get(ligne["compte"])
        ligne["compte_cible"] = cible or None
        if not cible:
            compte_a_arbitrer = a_arbitrer.setdefault(
                ligne["compte"],
                {
                    "libelle": ligne["compte_lib"],
                    "lignes": 0,
                    "debit": 0,
                    "credit": 0,
                },
            )
            compte_a_arbitrer["lignes"] += 1
            compte_a_arbitrer["debit"] += ligne["debit"]
            compte_a_arbitrer["credit"] += ligne["credit"]
    sources = {ligne["compte"] for ligne in lot.lignes}
    r.info("mode", "table")
    r.info("comptes_source", len(sources))
    r.info("comptes_traduits", len(sources) - len(a_arbitrer))
    r.info("a_arbitrer", a_arbitrer)
    r.constat(
        "BLOQUANT",
        "MIG_COMPTE_A_ARBITRER",
        "Comptes absents de la table (à arbitrer)",
        [
            "%s %s — %s ligne(s)" % (k, v["libelle"], v["lignes"])
            for k, v in sorted(a_arbitrer.items())
        ],
    )
    if vides:
        r.constat(
            "ALERTE",
            "MIG_TABLE_CIBLE_VIDE",
            "Lignes de la table sans compte Odoo",
            sorted(vides),
        )
    fusions: dict[str, list[str]] = {}
    for s, c in table.items():
        if s in sources and c:
            fusions.setdefault(c, []).append(s)
    r.constat(
        "INFO",
        "MIG_COMPTES_FUSIONNES",
        "Comptes source regroupés sur un même compte Odoo",
        [
            "%s ← %s" % (c, ", ".join(sorted(s)))
            for c, s in sorted(fusions.items())
            if len(s) > 1
        ],
    )
    j.dire(
        "Correspondance : %s comptes source, %s traduits, %s à arbitrer"
        % (
            nombre_texte(len(sources)),
            nombre_texte(len(sources) - len(a_arbitrer)),
            nombre_texte(len(a_arbitrer)),
        ),
        "erreur" if a_arbitrer else "ok",
    )
    return r


def ecrire_a_arbitrer(
    chemin: str, a_arbitrer: Mapping[str, CompteAArbitrer]
) -> None:
    """Fichier xlsx pour le comptable : une ligne par compte à traduire."""
    ecrire_xlsx(
        chemin,
        [
            (
                "A arbitrer",
                (
                    "Compte source",
                    "Libellé",
                    "Lignes",
                    "Débit",
                    "Crédit",
                    "Compte Odoo (à remplir)",
                ),
                (
                    [
                        k,
                        v["libelle"],
                        v["lignes"],
                        Centimes(v["debit"]),
                        Centimes(v["credit"]),
                        "",
                    ]
                    for k, v in sorted(a_arbitrer.items())
                ),
            )
        ],
    )
