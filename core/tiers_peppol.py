# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Facture électronique des tiers : inscription et adresse (ADR-0014).

1. `lire_tiers_facturation` : tous les clients et fournisseurs d'une base
   Odoo, avec leur SIREN (SIRET, company_registry ou TVA française).
2. `verifier` : pour chaque SIREN, le répertoire Peppol public est
   interrogé (le SIREN seul part) ; le tiers est « inscrit » (adresses
   trouvées), « non trouvé » (à vérifier : ce n'est pas une preuve de
   non-inscription) ou « sans SIREN ».
3. `ecrire_adresses` : l'adresse choisie va dans les champs peppol_eas et
   peppol_endpoint du tiers, par la routine commune tiers_odoo.ecrire_champs
   (fiche déjà renseignée jamais écrasée, trace, annulation).
"""

import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TypedDict

from .connecteurs.http_json import ClientJson
from .demat import extraire_siren
from .tiers_odoo import AccesOdoo, EcritureTiers, ecrire_champs, valeur_vide

REPERTOIRE_PEPPOL = "https://directory.peppol.eu"
PAUSE_PEPPOL_S = 0.2  # aucune limite publiée : environ 5 appels par seconde
RESULTATS_PEPPOL = 50
LOT_TIERS = 500
INSCRIT = "inscrit"
NON_TROUVE = "non_trouve"
SANS_SIREN = "sans_siren"
# Schémas français : 0225 (SIREN + routage), 0002 (SIREN), 0009 (SIRET).
_ADRESSE_FRANCAISE = re.compile(
    r"^(?P<schema>0225|0002|0009):"
    r"(?P<identifiant>(?P<siren>\d{9})(?P<suite>.*))$"
)
# Documents Peppol reconnus -> nom affiché.
TYPES_DOCUMENTS = (
    ("CreditNote-2", "avoir UBL"),
    ("Invoice-2", "facture UBL"),
    ("CrossIndustryInvoice", "facture CII (Factur-X)"),
)


class ErreurPeppol(ValueError):
    """Écriture impossible (champs absents, schéma refusé, choix faux)."""


class ClientRepertoire(Protocol):
    """Ce dont ce module a besoin du répertoire : des requêtes JSON."""

    def requete(
        self,
        methode: str,
        chemin: str,
        parametres: Mapping[str, object] | None = None,
        corps: object = None,
    ) -> Any:
        """Appelle le répertoire ; rend le JSON décodé."""


class TiersFacturation(TypedDict):
    """Un client ou fournisseur relu dans Odoo."""

    id: int
    nom: str
    siren: str
    client: bool
    fournisseur: bool
    adresse_actuelle: str


class AdressePeppol(TypedDict):
    """Une adresse de facture électronique trouvée sur Peppol."""

    schema: str
    identifiant: str
    documents: list[str]
    inscrit_le: str


class Verification(TypedDict):
    """Résultat pour un tiers."""

    tiers: TiersFacturation
    classe: str
    adresses: list[AdressePeppol]
    proposee: AdressePeppol | None


def _champs_peppol(cible: AccesOdoo) -> dict[str, Any]:
    """Champs Peppol (et siret) de la base ; vide s'ils manquent."""
    champs: dict[str, Any] = cible.appel(
        "res.partner",
        "fields_get",
        [["peppol_eas", "peppol_endpoint", "siret"]],
        {"attributes": ["type", "selection", "readonly"]},
    )
    return champs


def lire_tiers_facturation(cible: AccesOdoo) -> list[TiersFacturation]:
    """Tous les clients et fournisseurs (sociétés mères), avec leur SIREN.

    Rôle : la liste à vérifier (arbitrage 3 : tous les tiers).
    Paramètres : cible — base Odoo.
    Retour : tiers, par identifiant ; SIREN vide s'il est introuvable.
    Erreurs : FauteXmlRpc (Odoo).
    Usages : interface (écran Facture électronique), tests.
    """
    champs_base = _champs_peppol(cible)
    champs = [
        "name",
        "vat",
        "company_registry",
        "customer_rank",
        "supplier_rank",
    ]
    champs += [
        nom
        for nom in ("siret", "peppol_eas", "peppol_endpoint")
        if nom in champs_base
    ]
    domaine = [
        "&",
        ("parent_id", "=", False),
        "|",
        ("customer_rank", ">", 0),
        ("supplier_rank", ">", 0),
    ]
    tiers: list[TiersFacturation] = []
    depart = 0
    while True:
        lot = cible.appel(
            "res.partner",
            "search_read",
            [domaine],
            {
                "fields": champs,
                "offset": depart,
                "limit": LOT_TIERS,
                "order": "id",
            },
        )
        for fiche in lot:
            adresse = ""
            if not valeur_vide(fiche.get("peppol_endpoint")):
                adresse = "%s:%s" % (
                    fiche.get("peppol_eas") or "",
                    fiche["peppol_endpoint"],
                )
            tiers.append(
                {
                    "id": int(fiche["id"]),
                    "nom": str(fiche["name"] or ""),
                    "siren": extraire_siren(fiche),
                    "client": (fiche["customer_rank"] or 0) > 0,
                    "fournisseur": (fiche["supplier_rank"] or 0) > 0,
                    "adresse_actuelle": adresse,
                }
            )
        if len(lot) < LOT_TIERS:
            return tiers
        depart += LOT_TIERS


def documents_acceptes(types: Sequence[Mapping[str, Any]]) -> list[str]:
    """Noms des documents qu'une adresse accepte (facture, avoir…)."""
    noms = []
    for type_document in types:
        valeur = str(type_document.get("value") or "")
        for motif, nom in TYPES_DOCUMENTS:
            if motif in valeur and nom not in noms:
                noms.append(nom)
                break
    return noms


def adresses_peppol(
    reponse: Mapping[str, Any], siren: str
) -> list[AdressePeppol]:
    """Adresses françaises de ce SIREN dans une réponse du répertoire.

    Seules les adresses dont le SIREN est exactement celui du tiers sont
    gardées (la recherche du répertoire est large). Un SIRET (0009) doit
    avoir 5 chiffres après le SIREN.
    """
    adresses: list[AdressePeppol] = []
    for trouvee in reponse.get("matches") or []:
        valeur = str((trouvee.get("participantID") or {}).get("value") or "")
        decoupe = _ADRESSE_FRANCAISE.match(valeur)
        if decoupe is None or decoupe.group("siren") != siren:
            continue
        if decoupe.group("schema") == "0009" and not re.fullmatch(
            r"\d{5}", decoupe.group("suite")
        ):
            continue
        entites = trouvee.get("entities") or [{}]
        adresses.append(
            {
                "schema": decoupe.group("schema"),
                "identifiant": decoupe.group("identifiant"),
                "documents": documents_acceptes(trouvee.get("docTypes") or []),
                "inscrit_le": str(entites[0].get("regDate") or ""),
            }
        )
    return sorted(
        adresses,
        key=lambda adresse: (adresse["schema"], adresse["identifiant"]),
    )


def adresse_proposee(
    adresses: Sequence[AdressePeppol],
) -> AdressePeppol | None:
    """Adresse proposée d'office : sans code de routage (SIREN seul).

    Arbitrage 4 : 0225 ou 0002 avec le SIREN seul ; sinon aucune (choix).
    """
    for schema in ("0225", "0002"):
        for adresse in adresses:
            if (
                adresse["schema"] == schema
                and len(adresse["identifiant"]) == 9
            ):
                return adresse
    return None


def verifier(
    tiers: Sequence[TiersFacturation],
    repertoire: ClientRepertoire | None = None,
    attendre: Callable[[float], None] = time.sleep,
) -> list[Verification]:
    """Inscription de chaque tiers, d'après le répertoire Peppol.

    Rôle : points 1 et 2 de l'ADR-0014. Un même SIREN n'est demandé
    qu'une fois.
    Paramètres : tiers ; repertoire — client du répertoire (défaut : le
    répertoire public) ; attendre — pause entre deux appels.
    Retour : une vérification par tiers.
    Erreurs : ErreurConnexion si le répertoire est injoignable.
    Usages : interface (écran Facture électronique), tests.
    """
    client: ClientRepertoire = repertoire or ClientJson(REPERTOIRE_PEPPOL, "")
    par_siren: dict[str, list[AdressePeppol]] = {}
    resultats: list[Verification] = []
    for un_tiers in tiers:
        siren = un_tiers["siren"]
        if not siren:
            resultats.append(
                {
                    "tiers": un_tiers,
                    "classe": SANS_SIREN,
                    "adresses": [],
                    "proposee": None,
                }
            )
            continue
        if siren not in par_siren:
            reponse = client.requete(
                "GET",
                "/search/1.0/json",
                {"q": siren, "rpc": RESULTATS_PEPPOL},
            )
            par_siren[siren] = adresses_peppol(reponse, siren)
            attendre(PAUSE_PEPPOL_S)
        adresses = par_siren[siren]
        resultats.append(
            {
                "tiers": un_tiers,
                "classe": INSCRIT if adresses else NON_TROUVE,
                "adresses": adresses,
                "proposee": adresse_proposee(adresses),
            }
        )
    return resultats


def ecrire_adresses(
    cible: AccesOdoo,
    choix: Sequence[Mapping[str, Any]],
    base: str,
    trace: str,
) -> dict[str, Any]:
    """Écrit l'adresse choisie de chaque tiers ; rend le bilan.

    Rôle : point 2 de l'ADR-0014. Les champs doivent exister dans la base
    et le schéma doit être accepté par cette version d'Odoo ; sinon rien
    n'est écrit. Un tiers qui a déjà une adresse n'est pas touché.
    Paramètres : cible ; choix — [{id, schema, identifiant}] ; base ;
    trace.
    Retour : bilan de tiers_odoo.ecrire_champs.
    Erreurs : ErreurPeppol (champs absents, schéma refusé : la cause est
    nommée) ; FauteXmlRpc.
    Usages : interface (écran Facture électronique), tests.
    """
    champs = _champs_peppol(cible)
    if "peppol_eas" not in champs or "peppol_endpoint" not in champs:
        raise ErreurPeppol(
            "Cette base n'a pas les champs Peppol (module de facture "
            "électronique d'Odoo non installé) : rien n'est écrit."
        )
    acceptes = {
        str(code) for code, _ in champs["peppol_eas"].get("selection") or []
    }
    refuses = sorted(
        {str(un_choix["schema"]) for un_choix in choix} - acceptes
    )
    if refuses:
        raise ErreurPeppol(
            "Schéma %s non accepté par cette version d'Odoo : rien n'est "
            "écrit." % ", ".join(refuses)
        )
    ecritures: list[EcritureTiers] = [
        {
            "id": int(un_choix["id"]),
            "valeurs": {
                "peppol_eas": str(un_choix["schema"]),
                "peppol_endpoint": str(un_choix["identifiant"]),
            },
        }
        for un_choix in choix
    ]
    return ecrire_champs(
        cible, ecritures, ["peppol_endpoint"], base, trace, REPERTOIRE_PEPPOL
    )
