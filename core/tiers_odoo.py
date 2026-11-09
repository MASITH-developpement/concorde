# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Compléter des fiches de tiers dans Odoo, de façon tracée et réversible.

Commun à « Compléter SIRET et TVA » (ADR-0013) et à « Facture électronique
des tiers » (ADR-0014) : accès Odoo réduit (lire, compléter), écriture qui
n'écrase jamais une fiche déjà renseignée, trace ligne par ligne, et
annulation à partir de cette trace.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, TypedDict

from .migration.injection import CibleOdoo
from .xml_sur import FauteXmlRpc


class AccesOdoo(Protocol):
    """Ce dont ces modules ont besoin d'une base Odoo : appeler ses modèles."""

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Appelle une méthode d'un modèle Odoo."""


class CibleTiers(CibleOdoo):
    """Accès Odoo réduit à lire et compléter des tiers (ADR-0013, 0014)."""

    methodes_autorisees = ("search_read", "read", "fields_get", "write")


class EcritureTiers(TypedDict):
    """Valeurs à écrire sur une fiche de tiers."""

    id: int
    valeurs: dict[str, str]


def valeur_vide(valeur: object) -> bool:
    """Vrai pour une valeur Odoo vide (False, None, chaîne blanche)."""
    return not valeur or not str(valeur).strip()


def ecrire_champs(
    cible: AccesOdoo,
    ecritures: Sequence[EcritureTiers],
    champs_proteges: Sequence[str],
    base: str,
    trace: str,
    source: str,
) -> dict[str, Any]:
    """Écrit des valeurs sur des tiers ; rend le bilan (écrits, ignorés…).

    Rôle : une seule façon de compléter une fiche de tiers. Une fiche dont
    un champ protégé est déjà renseigné n'est pas touchée ; un refus d'Odoo
    n'arrête pas les autres fiches. Chaque écriture ajoute une ligne JSON à
    `trace` (tiers, anciennes et nouvelles valeurs, base, source, date).
    Paramètres : cible ; ecritures ; champs_proteges — champs qui doivent
    être vides pour écrire ; base — nom affiché dans la trace ; trace —
    fichier de trace ; source — d'où viennent les valeurs.
    Retour : {"ecrits": [...], "ignores": [...], "refus": [...]}.
    Erreurs : FauteXmlRpc hors fiche (connexion perdue).
    Usages : tiers_siret.ecrire, tiers_peppol.ecrire_adresses.
    """
    bilan: dict[str, list[Any]] = {"ecrits": [], "ignores": [], "refus": []}
    for ecriture in ecritures:
        champs = sorted(set(champs_proteges) | set(ecriture["valeurs"]))
        actuel = cible.appel(
            "res.partner", "read", [[ecriture["id"]]], {"fields": champs}
        )
        if not actuel or not all(
            valeur_vide(actuel[0][nom]) for nom in champs_proteges
        ):
            bilan["ignores"].append(ecriture["id"])
            continue
        try:
            cible.appel(
                "res.partner", "write", [[ecriture["id"]], ecriture["valeurs"]]
            )
        except FauteXmlRpc as exc:
            bilan["refus"].append(
                {"id": ecriture["id"], "cause": str(exc.faultString)[-300:]}
            )
            continue
        with open(trace, "a", encoding="utf-8") as fichier:
            fichier.write(
                json.dumps(
                    {
                        "le": datetime.now().isoformat(timespec="seconds"),
                        "base": base,
                        "tiers": ecriture["id"],
                        "anciennes": {
                            nom: actuel[0][nom] or ""
                            for nom in ecriture["valeurs"]
                        },
                        "nouvelles": ecriture["valeurs"],
                        "source": source,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        bilan["ecrits"].append(ecriture["id"])
    return bilan


def annuler(cible: AccesOdoo, trace: str) -> dict[str, list[int]]:
    """Remet les anciennes valeurs écrites d'après la trace.

    Rôle : rendre réversible une écriture de `ecrire_champs`. Une fiche
    modifiée depuis (valeur différente de celle écrite) n'est pas touchée.
    Paramètres : cible ; trace — fichier écrit par `ecrire_champs`.
    Retour : {"remis": [...], "ignores": [...]}.
    Erreurs : OSError (trace absente) ; FauteXmlRpc.
    Usages : interface (écrans SIRET et facture électronique), tests.
    """
    bilan: dict[str, list[int]] = {"remis": [], "ignores": []}
    with open(trace, encoding="utf-8") as fichier:
        lignes = [json.loads(ligne) for ligne in fichier if ligne.strip()]
    for ligne in reversed(lignes):
        champs = list(ligne["nouvelles"])
        actuel = cible.appel(
            "res.partner", "read", [[ligne["tiers"]]], {"fields": champs}
        )
        if not actuel or any(
            (actuel[0][nom] or "") != ligne["nouvelles"][nom] for nom in champs
        ):
            bilan["ignores"].append(ligne["tiers"])
            continue
        cible.appel(
            "res.partner",
            "write",
            [
                [ligne["tiers"]],
                {nom: ligne["anciennes"][nom] or False for nom in champs},
            ],
        )
        bilan["remis"].append(ligne["tiers"])
    return bilan
