# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Photo comptable d'une base Odoo 14 à 18, en lecture seule (ADR-0010).

La photo est prise en SQL sur la copie de la base, avant et après la
montée de version, puis comparée au centime (tolérance zéro).

Ce qui change d'une version à l'autre est lu dans la ligne elle-même
(`to_jsonb`), jamais déduit du numéro de version :
- code du compte : colonne `code` jusqu'à 17, `code_store` (par société)
  en 18 ;
- lien analytique -> ligne d'écriture : `move_id` en 14 et 15,
  `move_line_id` à partir de 16 ;
- dates de verrouillage : toutes les colonnes `*_lock_date` de la société.

Seules les écritures validées (`posted`) comptent. L'analytique ne couvre
que le plan principal (`account_id` des lignes analytiques).
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, TypedDict

from ..odoo_source import ConnexionSql, centimes

SECTIONS_PHOTO = (
    "balance",
    "balance_tiers",
    "journaux",
    "lettrage",
    "analytique",
    "verrous",
)

_SQL_VERSION_PHOTO = (
    "SELECT latest_version FROM ir_module_module WHERE name = 'base'"
)
_SQL_COMPTES_PHOTO = (
    "SELECT a.id, to_jsonb(a) ->> 'code', to_jsonb(a) -> 'code_store' "
    "FROM account_account a"
)
_SQL_JOURNAUX_PHOTO = "SELECT j.id, j.code FROM account_journal j"
_SQL_LIGNES_PHOTO = (
    "SELECT l.company_id, EXTRACT(YEAR FROM l.date)::int, l.account_id, "
    "l.partner_id, SUM(l.debit), SUM(l.credit), "
    "COUNT(l.full_reconcile_id), SUM(l.amount_residual) "
    "FROM account_move_line l JOIN account_move m ON m.id = l.move_id "
    "WHERE m.state = 'posted' GROUP BY 1, 2, 3, 4"
)
_SQL_PIECES_PHOTO = (
    "SELECT m.company_id, EXTRACT(YEAR FROM m.date)::int, m.journal_id, "
    "COUNT(DISTINCT m.id), COUNT(*), SUM(l.debit), SUM(l.credit) "
    "FROM account_move m JOIN account_move_line l ON l.move_id = m.id "
    "WHERE m.state = 'posted' GROUP BY 1, 2, 3"
)
_SQL_ANALYTIQUE_PHOTO = (
    "SELECT al.account_id, COUNT(*), SUM(al.amount) "
    "FROM account_analytic_line al "
    "WHERE COALESCE(to_jsonb(al) ->> 'move_line_id', "
    "to_jsonb(al) ->> 'move_id') IS NOT NULL GROUP BY 1"
)
_SQL_SOCIETES_PHOTO = "SELECT c.id, to_jsonb(c) FROM res_company c"


class ErreurPhoto(Exception):
    """La base ne se lit pas comme une base Odoo 14 à 18 (cause nommée)."""


class PhotoComptable(TypedDict):
    """Photo comptable d'une base : sections {clé: valeurs} et empreinte."""

    base: str
    version: str
    sections: dict[str, dict[str, str]]
    empreinte: str


class EcartPhoto(TypedDict):
    """Une différence entre deux photos (valeur vide = clé absente)."""

    section: str
    cle: str
    avant: str
    apres: str


def _requete(connexion: ConnexionSql, sql: str) -> list[tuple[Any, ...]]:
    """Exécute une requête de lecture ; rend toutes ses lignes."""
    with connexion.cursor() as curseur:
        curseur.execute(sql)
        lignes: list[tuple[Any, ...]] = curseur.fetchall()
        return lignes


def ajouter_valeurs(
    cumuls: dict[str, list[int]], cle: str, valeurs: list[int]
) -> None:
    """Ajoute `valeurs` terme à terme au cumul de `cle`.

    Rôle : cumuler les montants d'une section de photo.
    Paramètres : cumuls — {clé: valeurs}, modifié sur place ; cle ;
    valeurs — entiers (centimes, nombres de lignes).
    Retour : rien.
    Erreurs : aucune.
    Usages : prendre_photo, tests/integration/verifier_photo.
    """
    cumul = cumuls.setdefault(cle, [0] * len(valeurs))
    for rang, valeur in enumerate(valeurs):
        cumul[rang] += valeur


def sections_texte(
    cumuls: Mapping[str, Mapping[str, list[int]]],
) -> dict[str, dict[str, str]]:
    """Cumuls -> {section: {clé: "valeur valeur …"}}, clés triées.

    Rôle : la forme unique sous laquelle une photo est comparée et gardée.
    Paramètres : cumuls — {section: {clé: valeurs}}.
    Retour : sections en texte.
    Erreurs : aucune.
    Usages : prendre_photo, tests/integration/verifier_photo.
    """
    return {
        section: {
            cle: " ".join(str(valeur) for valeur in valeurs)
            for cle, valeurs in sorted(valeurs_section.items())
        }
        for section, valeurs_section in cumuls.items()
    }


def _codes_comptes(connexion: ConnexionSql) -> dict[tuple[int, int], str]:
    """{(société, compte): code}, que le code soit unique ou par société.

    Erreurs : ErreurPhoto si un compte n'a de code ni commun ni pour une
    société (schéma inconnu).
    """
    codes: dict[tuple[int, int], str] = {}
    for ident, code, codes_societes in _requete(connexion, _SQL_COMPTES_PHOTO):
        if code:
            codes[(0, ident)] = code
        elif isinstance(codes_societes, dict) and codes_societes:
            for societe, code_societe in codes_societes.items():
                codes[(int(societe), ident)] = str(code_societe)
        else:
            raise ErreurPhoto(
                "Compte n° %s sans code (ni code, ni code_store) : "
                "schéma Odoo non reconnu." % ident
            )
    return codes


def _code(
    codes: Mapping[tuple[int, int], str], societe: int, compte: int
) -> str:
    """Code du compte pour la société (code commun sinon). ErreurPhoto."""
    code = codes.get((0, compte)) or codes.get((societe, compte))
    if code is None:
        raise ErreurPhoto(
            "Compte n° %s sans code pour la société %s." % (compte, societe)
        )
    return code


def _sections_lignes(
    connexion: ConnexionSql, sections: dict[str, dict[str, list[int]]]
) -> None:
    """Balance, balance tiers et lettrage, depuis les lignes validées."""
    codes = _codes_comptes(connexion)
    for (
        societe,
        annee,
        compte,
        tiers,
        debit,
        credit,
        lettrees,
        reste,
    ) in _requete(connexion, _SQL_LIGNES_PHOTO):
        code = _code(codes, societe, compte)
        montants = [centimes(debit), centimes(credit)]
        ajouter_valeurs(
            sections["balance"], "s%s|%s|%s" % (societe, annee, code), montants
        )
        if tiers is not None:
            ajouter_valeurs(
                sections["balance_tiers"],
                "s%s|%s|%s|p%s" % (societe, annee, code, tiers),
                montants,
            )
        ajouter_valeurs(
            sections["lettrage"],
            "s%s|%s" % (societe, code),
            [int(lettrees), centimes(reste)],
        )


def _sections_pieces(
    connexion: ConnexionSql, sections: dict[str, dict[str, list[int]]]
) -> None:
    """Journaux (écritures, lignes, débit, crédit) et analytique."""
    journaux = dict(_requete(connexion, _SQL_JOURNAUX_PHOTO))
    for societe, annee, journal, ecritures, lignes, debit, credit in _requete(
        connexion, _SQL_PIECES_PHOTO
    ):
        ajouter_valeurs(
            sections["journaux"],
            "s%s|%s|%s" % (societe, annee, journaux.get(journal, journal)),
            [int(ecritures), int(lignes), centimes(debit), centimes(credit)],
        )
    for compte, nombre, montant in _requete(connexion, _SQL_ANALYTIQUE_PHOTO):
        ajouter_valeurs(
            sections["analytique"],
            "a%s" % compte,
            [int(nombre), centimes(montant)],
        )


def _dates_verrous(connexion: ConnexionSql) -> dict[str, str]:
    """{"s<société>|<colonne>": date ISO ou ""} pour chaque *_lock_date."""
    verrous: dict[str, str] = {}
    for societe, colonnes in _requete(connexion, _SQL_SOCIETES_PHOTO):
        for nom, valeur in colonnes.items():
            if nom.endswith("_lock_date"):
                verrous["s%s|%s" % (societe, nom)] = str(valeur or "")
    return dict(sorted(verrous.items()))


def empreinte_sections(sections: Mapping[str, Mapping[str, str]]) -> str:
    """Empreinte SHA-256 des sections d'une photo.

    Rôle : savoir en une valeur si deux photos sont identiques.
    Paramètres : sections — {section: {clé: valeurs}}.
    Retour : empreinte hexadécimale.
    Erreurs : aucune.
    Usages : prendre_photo, tests.
    """
    texte = json.dumps(sections, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def prendre_photo(connexion: ConnexionSql, base: str) -> PhotoComptable:
    """Photo comptable d'une base Odoo 14 à 18 (lecture seule).

    Rôle : figer l'état comptable avant ou après une montée de version.
    Paramètres : connexion — session SQL en lecture seule
    (odoo_source.connexion_lecture_seule) ; base — nom, pour le rapport.
    Retour : PhotoComptable (montants en centimes, clés triées).
    Erreurs : ErreurPhoto (base non Odoo, schéma inconnu) ; ErreurMontant
    (montant non exact au centime) ; psycopg2.Error (table absente).
    Usages : montée de version (ADR-0010), tests/integration/verifier_photo.
    """
    version = _requete(connexion, _SQL_VERSION_PHOTO)
    if not version:
        raise ErreurPhoto("Base %s : module base absent, pas Odoo." % base)
    cumuls: dict[str, dict[str, list[int]]] = {
        section: {} for section in SECTIONS_PHOTO if section != "verrous"
    }
    _sections_lignes(connexion, cumuls)
    _sections_pieces(connexion, cumuls)
    sections = sections_texte(cumuls)
    sections["verrous"] = _dates_verrous(connexion)
    connexion.rollback()
    return {
        "base": base,
        "version": str(version[0][0]),
        "sections": sections,
        "empreinte": empreinte_sections(sections),
    }


def charger_photo(chemin: str) -> PhotoComptable:
    """Relit une photo enregistrée et vérifie son empreinte.

    Rôle : comparer des photos prises à des moments différents, sans
    risque qu'un fichier modifié à la main passe inaperçu.
    Paramètres : chemin — fichier JSON écrit par la commande `photo`.
    Retour : PhotoComptable.
    Erreurs : ErreurPhoto (forme inattendue, empreinte fausse) ; OSError ;
    ValueError (JSON illisible).
    Usages : scripts/concorde_montee (comparer), tests.
    """
    with open(chemin, encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    if not isinstance(donnees, dict) or not isinstance(
        donnees.get("sections"), dict
    ):
        raise ErreurPhoto("%s : ce n'est pas une photo CONCORDE." % chemin)
    lue: PhotoComptable = {
        "base": str(donnees.get("base", "")),
        "version": str(donnees.get("version", "")),
        "sections": donnees["sections"],
        "empreinte": str(donnees.get("empreinte", "")),
    }
    if empreinte_sections(lue["sections"]) != lue["empreinte"]:
        raise ErreurPhoto(
            "%s : empreinte fausse, la photo a été modifiée." % chemin
        )
    return lue


def comparer_photos(
    avant: PhotoComptable, apres: PhotoComptable
) -> list[EcartPhoto]:
    """Différences entre deux photos, section par section, au centime.

    Rôle : prouver qu'une montée de version n'a rien changé (zéro écart).
    Paramètres : avant, apres — photos de la même base.
    Retour : liste des écarts (vide si identiques), triée.
    Erreurs : aucune.
    Usages : montée de version (ADR-0010), tests.
    """
    ecarts: list[EcartPhoto] = []
    for section in SECTIONS_PHOTO:
        valeurs_avant = avant["sections"].get(section, {})
        valeurs_apres = apres["sections"].get(section, {})
        for cle in sorted(set(valeurs_avant) | set(valeurs_apres)):
            if valeurs_avant.get(cle) != valeurs_apres.get(cle):
                ecarts.append(
                    {
                        "section": section,
                        "cle": cle,
                        "avant": valeurs_avant.get(cle, ""),
                        "apres": valeurs_apres.get(cle, ""),
                    }
                )
    return ecarts
