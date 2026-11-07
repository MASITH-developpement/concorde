# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""PLAN COMPTABLE ODOO — lecture du classeur uploadé.

Rôle (décidé avec le client) : le plan comptable uploadé dans l'assistant
sert à CRÉER automatiquement dans Odoo les comptes manquants (code +
intitulé lus dans le fichier — explicite, jamais deviné). Un compte absent
du fichier reste bloquant (tolérance 0, aucun compte inventé).

Colonnes détectées automatiquement (en-têtes normalisés, indépendants de
la casse/accents/séparateurs) :
- code    : « Code », « Numéro », « Compte », « Account Code »...
- intitulé : « Intitulé », « Libellé », « Nom », « Name »,
             « Description », « Account Name »...
- type    : « Type », « Type de compte »... (optionnel, heuristique
             receivable/payable sinon non renseigné)
Erreurs explicites à la moindre ambiguïté (Marceau : jamais muet).
"""

from typing import NoReturn, Optional, TypedDict, Union

from .mapping import (
    NS_MAIN,
    ErreurMapping,
    _compte_txt,
    _erreur_fichier,
    _norm_entete,
    lire_feuille_xlsx,
    valeurs_cellules_ligne,
)

# en-têtes acceptés pour chaque rôle (déjà normalisés par _norm_entete)
CLES_CODE = (
    "code",
    "numero",
    "compte",
    "accountcode",
    "codecompte",
    "numerocompte",
    "ncompte",
    "comptenum",
    "num",
)
CLES_INTITULE = (
    "intitule",
    "libelle",
    "nom",
    "name",
    "description",
    "accountname",
    "nomcompte",
    "intitulecompte",
    "libellecompte",
)
CLES_TYPE = ("type", "typecompte", "accounttype", "account_type", "nature")

# types Odoo account.account.account_type (17.0)
TYPES_ACCOUNT = {
    "receivable",
    "payable",
    "bank",
    "cash",
    "credit_card",
    "asset_current",
    "asset_non_current",
    "asset_cash",
    "asset_fixed",
    "asset_receivable",
    "liability_current",
    "liability_payable",
    "liability_non_current",
    "equity",
    "equity_unallocated",
    "income",
    "income_other",
    "expense",
    "expense_depreciation",
    "expense_direct_cost",
    "off_sheet",
    "unaffected",
}

# libellés humains -> account_type Odoo
CORRESP_TYPE = {
    "client": "asset_receivable",
    "fournisseur": "liability_payable",
    "receivable": "asset_receivable",
    "payable": "liability_payable",
    "banque": "bank",
    "bank": "bank",
    "caisse": "cash",
    "cash": "cash",
    "actif": "asset_current",
    "asset": "asset_current",
    "actifcirculant": "asset_current",
    "immobilisation": "asset_fixed",
    "actifnoncirculant": "asset_fixed",
    "passif": "liability_current",
    "liability": "liability_current",
    "passifcirculant": "liability_current",
    "capitauxpropres": "equity",
    "equity": "equity",
    "produit": "income",
    "income": "income",
    "revenu": "income",
    "charge": "expense",
    "expense": "expense",
    "depense": "expense",
    "nonaffecte": "unaffected",
}


class ErreurPlanComptable(ErreurMapping):
    """Plan comptable illisible, incomplet ou contradictoire."""


class CompteLu(TypedDict):
    """Compte lu dans le plan comptable : code, intitulé, type Odoo."""

    code: str
    nom: str
    type: Optional[str]


def charger_plan_xlsx(
    brut: Optional[Union[bytes, bytearray]], nom_fichier: str = ""
) -> list[CompteLu]:
    """Charge un plan comptable depuis un classeur .xlsx (octets).

    Retourne une liste ordonnée de dicts {code, nom, type} :
    - code  : texte non vide (jamais '10130000.0') ;
    - nom   : texte non vide ;
    - type  : account_type Odoo 17 si déterminé SINON None (explicite :
              le wizard créera le compte sans type forcé, Odoo applique
              le type par défaut de la séquence).
    """

    def _err(message: str) -> NoReturn:
        """Erreur ErreurPlanComptable pour ce fichier."""
        _erreur_fichier(
            ErreurPlanComptable, "du plan comptable", nom_fichier, message
        )

    feuille, racine, _valeur = lire_feuille_xlsx(
        brut, nom_fichier, quoi="du plan comptable"
    )

    lignes = list(racine.iter(NS_MAIN + "row"))

    # 1. détection de l'en-tête (parmi les 50 premières lignes) : colonnes
    # et INDEX de la ligne d'en-tête (la lecture commence après elle).
    col_code: Optional[int] = None
    col_intitule: Optional[int] = None
    col_type: Optional[int] = None
    idx_entete = 0  # fixé dès que l'en-tête est trouvé (sinon _err)
    for idx, row in enumerate(lignes[:50]):
        entetes: dict[str, int] = {}
        for col, val in valeurs_cellules_ligne(row, _valeur).items():
            entetes[_norm_entete(val)] = col
        for texte, col in entetes.items():
            if col_code is None and texte in CLES_CODE:
                col_code = col
            if col_intitule is None and texte in CLES_INTITULE:
                col_intitule = col
            if col_type is None and texte in CLES_TYPE:
                col_type = col
        if col_code is not None and col_intitule is not None:
            idx_entete = idx
            break
    if col_code is None or col_intitule is None:
        _err(
            "en-tête introuvable — colonnes attendues : code du compte "
            "(« Code », « Numéro », « Compte »...) et intitulé "
            "(« Intitulé », « Libellé », « Nom »...). Envoyez un extrait "
            "du fichier pour adapter la détection."
        )

    # 2. lecture des comptes (strictement après la ligne d'en-tête)
    comptes: list[CompteLu] = []
    vus: dict[str, tuple[str, Optional[str]]] = {}
    debut_donnees = idx_entete + 1
    for row in lignes[debut_donnees:]:
        vals = valeurs_cellules_ligne(row, _valeur)
        code = _compte_txt(vals.get(col_code, "") or "").strip()
        nom = str(vals.get(col_intitule, "") or "").strip()
        type_txt = (
            _compte_txt(vals.get(col_type, "") or "").strip()
            if col_type is not None
            else ""
        )
        if not code:
            continue  # ligne vide / de présentation
        if not nom:
            _err(
                "compte %s sans intitulé — CONCORDE ne devine jamais "
                "un libellé de compte." % code
            )
        typ = _resoudre_type(type_txt, code)
        if code in vus and vus[code] != (nom, typ):
            _err(
                "compte %s défini plusieurs fois avec des intitulés "
                "différents (%r / %r)." % (code, vus[code][0], nom)
            )
        vus[code] = (nom, typ)
        comptes.append({"code": code, "nom": nom, "type": typ})
    if not comptes:
        _err("aucun compte trouvé sous l'en-tête.")
    return comptes


def _resoudre_type(type_txt: str, code: str) -> Optional[str]:
    """Texte de type -> account_type Odoo 17, sinon None (jamais deviné).

    Heuristique EXPLICITE et conservatrice : sans colonne type lisible,
    on se limite aux classes PCG évidentes (411 -> receivable, 401 ->
    payable). Tout le reste -> None : Odoo applique son défaut, aucun
    type inventé.
    """
    t = _norm_entete(type_txt)
    if t:
        for cle, acct in CORRESP_TYPE.items():
            if cle in t:
                return acct
        if t in TYPES_ACCOUNT:
            return t
    c = (code or "").lstrip("0")
    if c.startswith(("411", "416", "419")):
        return "asset_receivable"
    if c.startswith(("401", "408", "409")):
        return "liability_payable"
    return None


def dictionnaire_plan(
    comptes: list[CompteLu],
) -> dict[str, tuple[str, Optional[str]]]:
    """Liste de comptes -> dict {code: (nom, type)}."""
    return {c["code"]: (c["nom"], c["type"]) for c in comptes}
