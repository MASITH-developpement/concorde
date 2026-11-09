# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Compléter le SIRET et la TVA des tiers (ADR-0013).

1. `lire_tiers` : les tiers d'un constat, relus dans Odoo (une fiche déjà
   complétée est écartée).
2. `proposer` : pour chacun, l'annuaire public des entreprises (État) est
   interrogé avec le nom et le code postal ; chaque candidate est contrôlée
   par calcul (SIRET : Luhn et SIREN ; TVA : clé et SIREN) puis classée
   « sûre », « à choisir » ou « introuvable ».
3. `ecrire` : les choix validés sont écrits par l'API d'Odoo (trois champs
   de res.partner seulement), sans jamais écraser une fiche complétée
   entre-temps ; chaque écriture est tracée. `annuler` remet les anciennes
   valeurs à partir de la trace.
"""

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, TypedDict

from .analyser import normaliser_nom
from .connecteurs.http_json import ClientJson
from .demat import siren_valide, siret_valide, tva_fr_valide
from .migration.injection import CibleOdoo
from .xml_sur import FauteXmlRpc

ANNUAIRE_ENTREPRISES = "https://recherche-entreprises.api.gouv.fr"
PAUSE_ANNUAIRE_S = 0.15  # environ 7 appels par seconde (limite publiée)
CANDIDATES_MAX = 5
CHAMPS_LUS = ("name", "zip", "city", "vat", "company_registry")
_IDENTIFIANT_CONSTAT = re.compile(r"\(id (\d+)\)$")
SURE = "sure"
A_CHOISIR = "a_choisir"
INTROUVABLE = "introuvable"


class ErreurSiret(ValueError):
    """Demande impossible (aucun tiers, choix incohérent)."""


class TiersACompleter(TypedDict):
    """Un tiers relu dans Odoo."""

    id: int
    nom: str
    code_postal: str
    ville: str


class Candidate(TypedDict):
    """Une entreprise de l'annuaire, avec le SIRET et la TVA retenus."""

    siren: str
    siret: str
    tva: str
    nom: str
    adresse: str
    code_postal: str
    controles: list[str]
    meme_nom: bool
    meme_code_postal: bool


class Proposition(TypedDict):
    """Ce que CONCORDE propose pour un tiers."""

    tiers: TiersACompleter
    classe: str
    candidates: list[Candidate]


class Choix(TypedDict):
    """Un choix validé : SIRET et TVA (vide : SIRET seul) d'un tiers."""

    id: int
    siret: str
    tva: str


class AccesOdoo(Protocol):
    """Ce dont ce module a besoin d'une base Odoo : appeler ses modèles."""

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Appelle une méthode d'un modèle Odoo."""


class ClientAnnuaire(Protocol):
    """Ce dont ce module a besoin de l'annuaire : des requêtes JSON."""

    def requete(
        self,
        methode: str,
        chemin: str,
        parametres: Mapping[str, object] | None = None,
        corps: object = None,
    ) -> Any:
        """Appelle l'annuaire ; rend le JSON décodé."""


class CibleTiers(CibleOdoo):
    """Accès Odoo réduit à ce que fait l'ADR-0013 : lire et compléter."""

    methodes_autorisees = ("search_read", "read", "fields_get", "write")


def identifiants_constat(elements: Iterable[str]) -> list[int]:
    """Identifiants Odoo des éléments d'un constat (« NOM (id 8159) »).

    Rôle : partir exactement des tiers signalés par l'analyse.
    Paramètres : elements — éléments du constat TIERS_SANS_SIREN_TVA.
    Retour : identifiants, dans l'ordre, sans doublon.
    Erreurs : aucune (un élément sans identifiant est ignoré).
    Usages : interface (écran SIRET), tests.
    """
    vus: list[int] = []
    for element in elements:
        trouve = _IDENTIFIANT_CONSTAT.search(str(element).strip())
        if trouve and int(trouve.group(1)) not in vus:
            vus.append(int(trouve.group(1)))
    return vus


def champ_siret(cible: AccesOdoo) -> str:
    """Champ du SIRET dans cette base : `siret` s'il existe, sinon
    `company_registry` (lecture de fields_get)."""
    champs = cible.appel(
        "res.partner",
        "fields_get",
        [["siret", "company_registry"]],
        {"attributes": ["type", "readonly"]},
    )
    if "siret" in champs and not champs["siret"].get("readonly"):
        return "siret"
    return "company_registry"


def _vide(valeur: object) -> bool:
    """Vrai pour une valeur Odoo vide (False, None, chaîne blanche)."""
    return not valeur or not str(valeur).strip()


def lire_tiers(
    cible: AccesOdoo, identifiants: Sequence[int]
) -> list[TiersACompleter]:
    """Relit les tiers dans Odoo ; garde ceux qui n'ont ni SIRET ni TVA.

    Rôle : ne jamais proposer pour une fiche déjà complétée.
    Paramètres : cible — base Odoo ; identifiants — tiers du constat.
    Retour : tiers à compléter, dans l'ordre des identifiants.
    Erreurs : ErreurSiret si la liste est vide ; FauteXmlRpc (Odoo).
    Usages : interface (écran SIRET).
    """
    if not identifiants:
        raise ErreurSiret("Aucun tiers à compléter dans ce constat.")
    champ = champ_siret(cible)
    lignes = cible.appel(
        "res.partner",
        "read",
        [list(identifiants)],
        {"fields": list(CHAMPS_LUS) + ([champ] if champ == "siret" else [])},
    )
    par_id = {int(ligne["id"]): ligne for ligne in lignes}
    return [
        {
            "id": ident,
            "nom": str(par_id[ident]["name"] or ""),
            "code_postal": str(par_id[ident]["zip"] or "").strip(),
            "ville": str(par_id[ident]["city"] or "").strip(),
        }
        for ident in identifiants
        if ident in par_id
        and _vide(par_id[ident]["vat"])
        and _vide(par_id[ident]["company_registry"])
        and _vide(par_id[ident].get("siret"))
    ]


def controler(
    siret: str, tva: str, siren: str, tva_exigee: bool = True
) -> list[str]:
    """Contrôles par calcul d'une candidate ; rend les anomalies.

    Rôle : la règle de l'arbitrage 2 de l'ADR-0013, en un seul endroit.
    Paramètres : siret — 14 chiffres ; tva — numéro de l'annuaire (peut
    être vide) ; siren — SIREN de l'entreprise ; tva_exigee — une TVA
    absente est-elle une anomalie (non pour un choix « SIRET seul »).
    Retour : liste des contrôles en échec, nommés.
    Erreurs : aucune.
    Usages : lire_candidate, ecrire (contrôle refait avant d'écrire), tests.
    """
    anomalies = []
    if not siren_valide(siren):
        anomalies.append("SIREN invalide (clé de Luhn)")
    if not siret_valide(siret):
        anomalies.append("SIRET invalide (clé de Luhn)")
    if siret[:9] != siren:
        anomalies.append("le SIRET n'appartient pas à ce SIREN")
    if not tva:
        if tva_exigee:
            anomalies.append("TVA absente de l'annuaire")
    elif not tva_fr_valide(tva) or tva[-9:] != siren:
        anomalies.append("TVA fausse (clé ou SIREN)")
    return anomalies


def lire_candidate(
    resultat: Mapping[str, Any], tiers: TiersACompleter
) -> Candidate | None:
    """Entreprise de l'annuaire -> candidate (None si elle est fermée).

    SIRET : établissement actif au code postal du tiers, sinon le siège.
    Même nom : raison sociale ou sigle égaux au nom du tiers, une fois la
    forme juridique et la ponctuation retirées.
    """
    code_postal = tiers["code_postal"]
    if resultat.get("etat_administratif") != "A":
        return None
    siren = str(resultat.get("siren") or "")
    siege = resultat.get("siege") or {}
    retenu = siege
    for etablissement in resultat.get("matching_etablissements") or []:
        if (
            etablissement.get("etat_administratif") == "A"
            and code_postal
            and etablissement.get("code_postal") == code_postal
        ):
            retenu = etablissement
            break
    tva = next(
        (
            str(numero)
            for numero in resultat.get("tva") or []
            if str(numero).startswith("FR")
        ),
        "",
    )
    siret = str(retenu.get("siret") or "")
    return {
        "siren": siren,
        "siret": siret,
        "tva": tva,
        "nom": str(resultat.get("nom_complet") or ""),
        "adresse": str(retenu.get("adresse") or ""),
        "code_postal": str(retenu.get("code_postal") or ""),
        "controles": controler(siret, tva, siren),
        "meme_nom": bool(normaliser_nom(tiers["nom"]))
        and normaliser_nom(tiers["nom"])
        in {
            normaliser_nom(str(resultat.get(cle) or ""))
            for cle in ("nom_raison_sociale", "sigle")
        },
        "meme_code_postal": bool(code_postal)
        and retenu.get("code_postal") == code_postal,
    }


def classer(candidates: list[Candidate]) -> str:
    """Sûre, à choisir ou introuvable (ADR-0013, point 1).

    Sûre : une seule candidate a le même nom, le même code postal et
    passe tous les contrôles par calcul.
    """
    if not candidates:
        return INTROUVABLE
    parfaites = [
        trouvee
        for trouvee in candidates
        if trouvee["meme_nom"]
        and trouvee["meme_code_postal"]
        and not trouvee["controles"]
    ]
    return SURE if len(parfaites) == 1 else A_CHOISIR


def _rang(trouvee: Candidate) -> tuple[bool, bool, int]:
    """Ordre d'affichage : même nom, même code postal, moins d'anomalies."""
    return (
        not trouvee["meme_nom"],
        not trouvee["meme_code_postal"],
        len(trouvee["controles"]),
    )


def proposer(
    tiers: Sequence[TiersACompleter],
    annuaire: ClientAnnuaire | None = None,
    attendre: Callable[[float], None] = time.sleep,
) -> list[Proposition]:
    """Interroge l'annuaire pour chaque tiers ; rend les propositions.

    Rôle : point 1 de l'ADR-0013 (proposer, jamais deviner).
    Paramètres : tiers — à compléter ; annuaire — client de l'annuaire
    (défaut : l'annuaire public de l'État) ; attendre — pause entre deux
    appels (limite de l'État).
    Retour : une proposition par tiers.
    Erreurs : ErreurConnexion si l'annuaire est injoignable.
    Usages : interface (écran SIRET), tests.
    """
    client: ClientAnnuaire = annuaire or ClientJson(ANNUAIRE_ENTREPRISES, "")
    propositions: list[Proposition] = []
    for un_tiers in tiers:
        parametres: dict[str, object] = {
            "q": un_tiers["nom"],
            "per_page": CANDIDATES_MAX,
        }
        if re.fullmatch(r"\d{5}", un_tiers["code_postal"]):
            parametres["code_postal"] = un_tiers["code_postal"]
        reponse = client.requete("GET", "/search", parametres)
        attendre(PAUSE_ANNUAIRE_S)
        if not reponse.get("results") and "code_postal" in parametres:
            # Code postal faux dans Odoo : le nom seul (jamais « sûr »).
            del parametres["code_postal"]
            reponse = client.requete("GET", "/search", parametres)
            attendre(PAUSE_ANNUAIRE_S)
        trouvees = [
            trouvee
            for trouvee in (
                lire_candidate(resultat, un_tiers)
                for resultat in reponse.get("results") or []
            )
            if trouvee is not None
        ]
        trouvees.sort(key=_rang)
        propositions.append(
            {
                "tiers": un_tiers,
                "classe": classer(trouvees),
                "candidates": trouvees,
            }
        )
    return propositions


def ecrire(
    cible: AccesOdoo,
    choix: Sequence[Choix],
    base: str,
    trace: str,
) -> dict[str, Any]:
    """Écrit les choix validés ; rend le bilan (écrits, ignorés, refus).

    Rôle : point 4 de l'ADR-0013. Contrôles refaits avant d'écrire ; une
    fiche complétée entre-temps n'est pas touchée ; un refus d'Odoo
    n'arrête pas les autres fiches. Chaque écriture ajoute une ligne JSON
    à `trace` (tiers, champs, anciennes et nouvelles valeurs, base, date).
    Paramètres : cible ; choix ; base — nom affiché dans la trace ; trace
    — fichier de trace.
    Retour : {"ecrits": [...], "ignores": [...], "refus": [...]}.
    Erreurs : ErreurSiret (choix qui échoue aux contrôles : rien n'est
    écrit) ; FauteXmlRpc hors fiche (connexion perdue).
    Usages : interface (écran SIRET), tests.
    """
    for un_choix in choix:
        anomalies = controler(
            un_choix["siret"], un_choix["tva"], un_choix["siret"][:9], False
        )
        if anomalies:
            raise ErreurSiret(
                "Tiers %d : %s. Rien n'est écrit."
                % (un_choix["id"], ", ".join(anomalies))
            )
    champ = champ_siret(cible)
    bilan: dict[str, list[Any]] = {"ecrits": [], "ignores": [], "refus": []}
    for un_choix in choix:
        actuel = cible.appel(
            "res.partner",
            "read",
            [[un_choix["id"]]],
            {"fields": ["vat", champ]},
        )
        if not actuel or not (
            _vide(actuel[0]["vat"]) and _vide(actuel[0][champ])
        ):
            bilan["ignores"].append(un_choix["id"])
            continue
        valeurs = {champ: un_choix["siret"]}
        if un_choix["tva"]:
            valeurs["vat"] = un_choix["tva"]
        try:
            cible.appel("res.partner", "write", [[un_choix["id"]], valeurs])
        except FauteXmlRpc as exc:
            bilan["refus"].append(
                {"id": un_choix["id"], "cause": str(exc.faultString)[-300:]}
            )
            continue
        with open(trace, "a", encoding="utf-8") as fichier:
            fichier.write(
                json.dumps(
                    {
                        "le": datetime.now().isoformat(timespec="seconds"),
                        "base": base,
                        "tiers": un_choix["id"],
                        "anciennes": {
                            nom: actuel[0][nom] or "" for nom in valeurs
                        },
                        "nouvelles": valeurs,
                        "source": ANNUAIRE_ENTREPRISES,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        bilan["ecrits"].append(un_choix["id"])
    return bilan


def annuler(cible: AccesOdoo, trace: str) -> dict[str, list[int]]:
    """Remet les anciennes valeurs écrites d'après la trace.

    Rôle : rendre réversible une écriture de l'ADR-0013. Une fiche
    modifiée depuis (valeur différente de celle écrite) n'est pas touchée.
    Paramètres : cible ; trace — fichier écrit par `ecrire`.
    Retour : {"remis": [...], "ignores": [...]}.
    Erreurs : OSError (trace absente) ; FauteXmlRpc.
    Usages : interface (écran SIRET), tests.
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
