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
from .mapping import (
    ErreurMapping,
    _compte_txt,
    _colonne_cellule,
    _norm_entete,
    lire_feuille_xlsx,
)
from xml.etree import ElementTree as ET

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# en-têtes acceptés pour chaque rôle (déjà normalisés par _norm_entete)
CLES_CODE = ("code", "numero", "compte", "accountcode", "codecompte",
             "numerocompte", "ncompte", "comptenum", "num")
CLES_INTITULE = ("intitule", "libelle", "nom", "name", "description",
                 "accountname", "nomcompte", "intitulecompte", "libellecompte")
CLES_TYPE = ("type", "typecompte", "accounttype", "account_type", "nature")

# types Odoo account.account.account_type (17.0)
TYPES_ACCOUNT = {
    "receivable", "payable", "bank", "cash", "credit_card", "asset_current",
    "asset_non_current", "asset_cash", "asset_fixed", "asset_receivable",
    "liability_current", "liability_payable", "liability_non_current",
    "equity", "equity_unallocated", "income", "income_other", "expense",
    "expense_depreciation", "expense_direct_cost", "off_sheet",
    "unaffected",
}

# libellés humains -> account_type Odoo
CORRESP_TYPE = {
    "client": "asset_receivable", "fournisseur": "liability_payable",
    "receivable": "asset_receivable", "payable": "liability_payable",
    "banque": "bank", "bank": "bank", "caisse": "cash", "cash": "cash",
    "actif": "asset_current", "asset": "asset_current",
    "actifcirculant": "asset_current",
    "immobilisation": "asset_fixed", "actifnoncirculant": "asset_fixed",
    "passif": "liability_current", "liability": "liability_current",
    "passifcirculant": "liability_current",
    "capitauxpropres": "equity", "equity": "equity",
    "produit": "income", "income": "income", "revenu": "income",
    "charge": "expense", "expense": "expense", "depense": "expense",
    "nonaffecte": "unaffected",
}


class ErreurPlanComptable(ErreurMapping):
    pass


def charger_plan_xlsx(brut, nom_fichier=""):
    """Charge un plan comptable depuis un classeur .xlsx (octets).

    Retourne une liste ordonnée de dicts {code, nom, type} :
    - code  : texte non vide (jamais '10130000.0') ;
    - nom   : texte non vide ;
    - type  : account_type Odoo 17 si déterminé SINON None (explicite :
              le wizard créera le compte sans type forcé, Odoo applique
              le type par défaut de la séquence).
    """
    def _err(message):
        raise ErreurPlanComptable(
            "Fichier du plan comptable %r : %s"
            % (nom_fichier or "xlsx", message))

    feuille, racine, _valeur = lire_feuille_xlsx(
        brut, nom_fichier, quoi="du plan comptable")

    def _valeurs_ligne(row):
        vals = {}
        for rang, c in enumerate(row.iter(NS_MAIN + "c")):
            col = _colonne_cellule(c, rang)
            val = _valeur(c)
            if val is not None:
                vals[col] = val
        return vals

    lignes = list(racine.iter(NS_MAIN + "row"))

    # 1. détection de l'en-tête (parmi les 50 premières lignes) : colonnes
    # et INDEX de la ligne d'en-tête (la lecture commence après elle).
    col_code = col_intitule = col_type = None
    idx_entete = None
    for idx, row in enumerate(lignes[:50]):
        entetes = {}
        for col, val in _valeurs_ligne(row).items():
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
            "du fichier pour adapter la détection.")

    # 2. lecture des comptes (strictement après la ligne d'en-tête)
    comptes = []
    vus = {}
    for row in lignes[idx_entete + 1:]:
        vals = _valeurs_ligne(row)
        code = _compte_txt(vals.get(col_code, "") or "").strip()
        nom = str(vals.get(col_intitule, "") or "").strip()
        type_txt = _compte_txt(vals.get(col_type, "") or "").strip() \
            if col_type is not None else ""
        if not code:
            continue  # ligne vide / de présentation
        if not nom:
            _err("compte %s sans intitulé — CONCORDE ne devine jamais "
                 "un libellé de compte." % code)
        typ = _resoudre_type(type_txt, code)
        if code in vus and vus[code] != (nom, typ):
            _err("compte %s défini plusieurs fois avec des intitulés "
                 "différents (%r / %r)." % (code, vus[code][0], nom))
        vus[code] = (nom, typ)
        comptes.append({"code": code, "nom": nom, "type": typ})
    if not comptes:
        _err("aucun compte trouvé sous l'en-tête.")
    return comptes


def _resoudre_type(type_txt, code):
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


def dictionnaire_plan(comptes):
    """Liste de comptes -> dict {code: (nom, type)}."""
    return {c["code"]: (c["nom"], c["type"]) for c in comptes}
