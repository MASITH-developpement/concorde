# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 3 bis — retirer des écritures du lot avant l'envoi.

Exemples : les à-nouveaux (journal « AN ») de janvier 2025 ; les comptes
commençant par 640 ; un compte analytique ; un tiers ; les libellés
contenant « essai »…

Un filtre (dict, ou ligne YAML/JSON) — tous les critères donnés doivent être
vrais :
  nom          texte libre, repris dans le rapport
  journaux     codes journal                          (vide = tous)
  comptes      préfixes de comptes, ex. ["640", "6411"] (vide = tous)
  sauf_comptes préfixes de comptes à NE PAS retenir
  analytique   codes (ou préfixes) analytiques — colonne fournie par les
               exports Excel/CSV et les API ; le FEC légal n'en a pas
  tiers        références de tiers (CompAuxNum)
  libelle      texte contenu dans le libellé (sans tenir compte des
               majuscules)
  piece        préfixe de la référence de pièce
  montant_min, montant_max   bornes en euros sur le montant de la ligne
               (débit ou crédit)
  du, au       période AAAA-MM-JJ, bornes incluses     (vide = sans limite)
  conditions   conditions libres sur n'importe quelle colonne :
               [{"champ": "piece", "op": "commence_par", "valeur": "AV"}, …]
               op : commence_par, contient, egal, different, vide, non_vide
  portee    « ecritures » (défaut) : retire les écritures ENTIÈRES qui ont
                au moins une ligne qui correspond — l'équilibre est garanti ;
            « lignes » : retire seulement les lignes qui correspondent ;
                REFUSÉ pour toute écriture où ces lignes ne se soldent pas
                à 0,00 € (sinon l'écriture restante serait déséquilibrée) ;
            « lignes_nulles » : retire les lignes à 0,00 € (totaux
                inchangés).

Garanties : chaque retrait est compté et chiffré au centime ; totaux après =
totaux avant − retraits, vérifié ; les lignes retirées sont gardées
(fichier à part).
"""

from collections.abc import Callable, Iterable, Mapping
from datetime import date
from typing import Any, TypedDict

from ..canonical import vers_centimes
from ..journal import Journal, nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from .lot import CleEcriture, LigneLot, Lot, TotauxLot, cle_ecriture, cle_texte

PORTEES = ("ecritures", "lignes", "lignes_nulles")
OPERATEURS = (
    "commence_par",
    "contient",
    "egal",
    "different",
    "vide",
    "non_vide",
)
CRITERES = (
    "journaux",
    "comptes",
    "sauf_comptes",
    "analytique",
    "tiers",
    "libelle",
    "piece",
    "montant_min",
    "montant_max",
    "du",
    "au",
    "conditions",
)


class ErreurFiltre(ValueError):
    """Filtre invalide, ou retrait qui déséquilibrerait une écriture."""


class ErreurConservation(RuntimeError):
    """Totaux après filtres ≠ totaux avant − retraits (garantie violée)."""


class ConditionFiltre(TypedDict):
    """Condition libre normalisée : champ, opérateur, valeur en minuscules."""

    champ: str
    op: str
    valeur: str


class FiltreNormalise(TypedDict):
    """Filtre validé : listes nettoyées, montants en centimes, dates."""

    nom: object
    portee: str
    journaux: list[str]
    comptes: list[str]
    sauf_comptes: list[str]
    analytique: list[str]
    tiers: list[str]
    libelle: str
    piece: str
    montant_min: int | None
    montant_max: int | None
    du: date | None
    au: date | None
    conditions: list[ConditionFiltre]


class RetraitFiltre(TypedDict):
    """Bilan d'un filtre : lignes et écritures retirées, montants."""

    nom: object
    portee: str
    lignes: int
    ecritures: int
    debit: int
    credit: int


class ResultatFiltres(TypedDict):
    """Totaux avant / après filtres et bilan de chaque filtre."""

    avant: TotauxLot
    apres: TotauxLot
    filtres: list[RetraitFiltre]


def _liste_textes(valeur: Any) -> list[str]:
    """Critère liste (liste, ou texte séparé par des virgules) -> textes.

    `valeur` vient du filtre fourni (JSON / YAML) : type libre. Les
    éléments vides sont écartés.
    """
    elements = valeur or []
    return [
        str(x).strip()
        for x in (
            elements.split(",") if isinstance(elements, str) else elements
        )
        if str(x).strip()
    ]


def _centimes_ou_rien(valeur: Any) -> int | None:
    """Montant en euros (texte ou nombre) -> centimes ; None si absent."""
    return vers_centimes(str(valeur)) if valeur not in (None, "") else None


def _date_ou_rien(valeur: Any) -> date | None:
    """Date AAAA-MM-JJ -> date ; None si absente. Lève ValueError."""
    return date.fromisoformat(str(valeur)) if valeur else None


def normaliser(filtre: Mapping[str, Any]) -> FiltreNormalise:
    """Valide un filtre et convertit ses dates. Lève ErreurFiltre.

    `filtre` vient d'un fichier JSON / YAML : ses valeurs ont un type libre.
    """
    brut = dict(filtre)
    brut.setdefault("nom", "filtre")
    nom = brut["nom"]
    portee = brut.get("portee") or "ecritures"
    if portee not in PORTEES:
        raise ErreurFiltre(
            "Filtre %r : portée inconnue %r (%s)."
            % (nom, portee, ", ".join(PORTEES))
        )
    inconnus = set(brut) - set(CRITERES) - {"nom", "portee"}
    if inconnus:
        raise ErreurFiltre(
            "Filtre %r : critère(s) inconnu(s) %s (attendus : %s)."
            % (nom, ", ".join(sorted(inconnus)), ", ".join(CRITERES))
        )
    journaux = _liste_textes(brut.get("journaux"))
    comptes = _liste_textes(brut.get("comptes"))
    sauf_comptes = _liste_textes(brut.get("sauf_comptes"))
    analytique = _liste_textes(brut.get("analytique"))
    tiers = _liste_textes(brut.get("tiers"))
    libelle = (brut.get("libelle") or "").strip().lower()
    piece = (brut.get("piece") or "").strip()
    montant_min = _centimes_ou_rien(brut.get("montant_min"))
    montant_max = _centimes_ou_rien(brut.get("montant_max"))
    conditions: list[ConditionFiltre] = []
    for condition in brut.get("conditions") or []:
        if condition.get("op") not in OPERATEURS:
            raise ErreurFiltre(
                "Filtre %r : opérateur %r inconnu (%s)."
                % (nom, condition.get("op"), ", ".join(OPERATEURS))
            )
        if not condition.get("champ"):
            raise ErreurFiltre("Filtre %r : condition sans champ." % nom)
        conditions.append(
            {
                "champ": condition["champ"],
                "op": condition["op"],
                "valeur": str(condition.get("valeur", "")).strip().lower(),
            }
        )
    debut_periode = _date_ou_rien(brut.get("du"))
    fin_periode = _date_ou_rien(brut.get("au"))
    if debut_periode and fin_periode and debut_periode > fin_periode:
        raise ErreurFiltre("Filtre %r : début après la fin." % nom)
    if portee == "lignes" and not comptes:
        raise ErreurFiltre(
            "Filtre %r : la portée « lignes » exige une liste de comptes."
            % nom
        )
    # Tous les critères sauf `sauf_comptes`, qui ne retient rien seul.
    criteres_retenus = (
        journaux,
        comptes,
        analytique,
        tiers,
        libelle,
        piece,
        montant_min,
        montant_max,
        debut_periode,
        fin_periode,
        conditions,
    )
    if portee in ("ecritures", "lignes") and not any(criteres_retenus):
        raise ErreurFiltre(
            "Filtre %r : sans journal, compte ni période, il retirerait "
            "tout le fichier." % nom
        )
    return {
        "nom": nom,
        "portee": portee,
        "journaux": journaux,
        "comptes": comptes,
        "sauf_comptes": sauf_comptes,
        "analytique": analytique,
        "tiers": tiers,
        "libelle": libelle,
        "piece": piece,
        "montant_min": montant_min,
        "montant_max": montant_max,
        "conditions": conditions,
        "du": debut_periode,
        "au": fin_periode,
    }


def _condition(condition: ConditionFiltre, ligne: LigneLot) -> bool:
    """Vrai si la ligne remplit la condition libre (sans casse)."""
    champs_ligne: Mapping[str, object] = ligne
    valeur_champ = champs_ligne.get(condition["champ"])
    texte = str(valeur_champ if valeur_champ is not None else "")
    texte = texte.strip().lower()
    attendu = condition["valeur"]
    operations: dict[str, Callable[[], bool]] = {
        "commence_par": lambda: texte.startswith(attendu),
        "contient": lambda: attendu in texte,
        "egal": lambda: texte == attendu,
        "different": lambda: texte != attendu,
        "vide": lambda: not texte,
        "non_vide": lambda: bool(texte),
    }
    return operations[condition["op"]]()


def _ligne_correspond(filtre: FiltreNormalise, ligne: LigneLot) -> bool:
    """Vrai si la ligne remplit tous les critères du filtre."""
    montant = ligne["debit"] or ligne["credit"]
    analytique = ligne.get("analytique") or ""
    debut_periode, fin_periode = filtre["du"], filtre["au"]
    montant_min, montant_max = filtre["montant_min"], filtre["montant_max"]
    return (
        (not filtre["journaux"] or ligne["journal_code"] in filtre["journaux"])
        and (
            not filtre["comptes"]
            or ligne["compte"].startswith(tuple(filtre["comptes"]))
        )
        and (
            not filtre["sauf_comptes"]
            or not ligne["compte"].startswith(tuple(filtre["sauf_comptes"]))
        )
        and (
            not filtre["analytique"]
            or any(analytique.startswith(a) for a in filtre["analytique"])
        )
        and (not filtre["tiers"] or ligne.get("tiers_ref") in filtre["tiers"])
        and (
            not filtre["libelle"]
            or filtre["libelle"] in (ligne.get("libelle") or "").lower()
        )
        and (
            not filtre["piece"]
            or (ligne.get("piece") or "").startswith(filtre["piece"])
        )
        and (montant_min is None or montant >= montant_min)
        and (montant_max is None or montant <= montant_max)
        and (not debut_periode or ligne["date"] >= debut_periode)
        and (not fin_periode or ligne["date"] <= fin_periode)
        and all(_condition(c, ligne) for c in filtre["conditions"])
    )


def _lignes_a_retirer(lot: Lot, filtre: FiltreNormalise) -> list[LigneLot]:
    """Lignes du lot que le filtre retire, selon sa portée.

    Lève ErreurFiltre si un filtre « lignes » couperait une écriture.
    """
    if filtre["portee"] == "lignes_nulles":
        return [
            ligne
            for ligne in lot.lignes
            if not ligne["debit"] and not ligne["credit"]
        ]
    if filtre["portee"] == "lignes":
        retirees = [
            ligne for ligne in lot.lignes if _ligne_correspond(filtre, ligne)
        ]
        soldes: dict[CleEcriture, int] = {}
        for ligne in retirees:
            soldes[cle_ecriture(ligne)] = (
                soldes.get(cle_ecriture(ligne), 0)
                + ligne["debit"]
                - ligne["credit"]
            )
        coupees = [
            "%s (%s €)" % (cle_texte(k), euros_texte(s, ","))
            for k, s in soldes.items()
            if s
        ]
        if coupees:
            raise ErreurFiltre(
                "Filtre %r refusé : retirer ces lignes déséquilibrerait %d "
                "écriture(s) : %s%s. Retirez les écritures entières "
                "(portée « ecritures ») ou ajoutez la contrepartie au filtre."
                % (
                    filtre["nom"],
                    len(coupees),
                    ", ".join(coupees[:5]),
                    "…" if len(coupees) > 5 else "",
                )
            )
        return retirees
    cles = {
        cle_ecriture(ligne)
        for ligne in lot.lignes
        if _ligne_correspond(filtre, ligne)
    }
    return [ligne for ligne in lot.lignes if cle_ecriture(ligne) in cles]


def appliquer(
    lot: Lot,
    filtres: Iterable[Mapping[str, Any]],
    journal: Journal | None = None,
) -> ResultatFiltres:
    """Applique les filtres dans l'ordre et modifie le lot.

    Retourne le rapport des retraits. Lève ErreurFiltre si un filtre
    « lignes » couperait une écriture en deux, ErreurConservation si les
    totaux après filtres ne valent pas les totaux avant moins les retraits.
    """
    j = ou_muet(journal)
    avant = lot.totaux()
    rapport: list[RetraitFiltre] = []
    for filtre_brut in filtres:
        filtre = normaliser(filtre_brut)
        retirees = _lignes_a_retirer(lot, filtre)
        ids = {id(ligne) for ligne in retirees}
        lot.lignes = [ligne for ligne in lot.lignes if id(ligne) not in ids]
        lot.retirees.extend((ligne, filtre["nom"]) for ligne in retirees)
        retrait: RetraitFiltre = {
            "nom": filtre["nom"],
            "portee": filtre["portee"],
            "lignes": len(retirees),
            "ecritures": len({cle_ecriture(ligne) for ligne in retirees}),
            "debit": sum(ligne["debit"] for ligne in retirees),
            "credit": sum(ligne["credit"] for ligne in retirees),
        }
        rapport.append(retrait)
        j.dire(
            "Filtre « %s » : %s écriture(s), %s ligne(s) retirées "
            "— D %s / C %s €"
            % (
                filtre["nom"],
                nombre_texte(retrait["ecritures"]),
                nombre_texte(retrait["lignes"]),
                euros_texte(retrait["debit"], ","),
                euros_texte(retrait["credit"], ","),
            ),
            "alerte" if retrait["lignes"] else "detail",
        )
    apres = lot.totaux()
    retire_d = sum(retrait["debit"] for retrait in rapport)
    retire_c = sum(retrait["credit"] for retrait in rapport)
    # Garantie : rien ne se perd ni ne se crée.
    if (
        apres["debit"] != avant["debit"] - retire_d
        or apres["credit"] != avant["credit"] - retire_c
    ):
        raise ErreurConservation(
            "Totaux après filtres incohérents : D %s / C %s, attendus "
            "D %s / C %s"
            % (
                euros_texte(apres["debit"], ","),
                euros_texte(apres["credit"], ","),
                euros_texte(avant["debit"] - retire_d, ","),
                euros_texte(avant["credit"] - retire_c, ","),
            )
        )
    if rapport:
        j.dire(
            "Après filtres : %s lignes (avant %s), totaux vérifiés au centime"
            % (nombre_texte(apres["lignes"]), nombre_texte(avant["lignes"])),
            "ok",
        )
    return {"avant": avant, "apres": apres, "filtres": rapport}
