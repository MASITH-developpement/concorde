# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Vérifie la photo comptable SQL sur un vrai Odoo (14 à 18) — ADR-0010.

1. Crée des écritures connues par l'API (ventes, encaissement lettré,
   règlement partiel, analytique), sur deux années.
2. Prend la photo en SQL (montee_version.photo.prendre_photo).
3. Recalcule les mêmes sections par l'ORM d'Odoo (XML-RPC), sans SQL.
4. Exige zéro écart. Sinon : chaque écart en annotation d'erreur de la
   CI, et code de sortie 1.

Lancement (CI) : python -m tests.integration.verifier_photo
Variables : ODOO_URL, ODOO_BASE, ODOO_UTILISATEUR, ODOO_MOT_DE_PASSE,
et PG* pour la lecture SQL. Base jetable de la CI uniquement : ce script
ÉCRIT dans Odoo.
"""

import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from core.montee_version.photo import (
    SECTIONS_PHOTO,
    EcartPhoto,
    PhotoComptable,
    ajouter_valeurs,
    comparer_photos,
    empreinte_sections,
    prendre_photo,
    sections_texte,
)
from core.odoo_source import centimes, connexion_lecture_seule, proxys_xmlrpc
from core.xml_sur import FauteXmlRpc


class OdooVerif:
    """Appels ORM vers la base de la CI (lecture et création)."""

    def __init__(
        self, url: str, base: str, utilisateur: str, mot_de_passe: str
    ) -> None:
        """S'authentifie ; lève RuntimeError si l'accès est refusé."""
        # Méthodes XML-RPC dynamiques : valeurs de types variés (Any).
        proxys: tuple[Any, Any] = proxys_xmlrpc(url.rstrip("/"), 300)
        commun, self._objet = proxys
        self.version = str(commun.version()["server_version"])
        self.base, self._mot_de_passe = base, mot_de_passe
        self.uid = commun.authenticate(base, utilisateur, mot_de_passe, {})
        if not self.uid:
            raise RuntimeError("Authentification refusée sur %s" % base)

    def appel(
        self,
        modele: str,
        methode: str,
        arguments: Sequence[Any],
        options: Mapping[str, Any] | None = None,
    ) -> Any:
        """execute_kw ; rend la valeur d'Odoo (types XML-RPC variés)."""
        return self._objet.execute_kw(
            self.base,
            self.uid,
            self._mot_de_passe,
            modele,
            methode,
            list(arguments),
            dict(options or {}),
        )

    def champs(self, modele: str) -> dict[str, Any]:
        """fields_get : {champ: attributs (type, store)}."""
        champs: dict[str, Any] = self.appel(
            modele, "fields_get", [], {"attributes": ["type", "store"]}
        )
        return champs

    def lire(
        self,
        modele: str,
        domaine: list[Any],
        champs: list[str],
        contexte: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """search_read complet (sans limite)."""
        lignes: list[dict[str, Any]] = self.appel(
            modele,
            "search_read",
            [domaine],
            {"fields": champs, "context": dict(contexte or {})},
        )
        return lignes

    def creer(self, modele: str, valeurs: Mapping[str, Any]) -> int:
        """create ; rend l'identifiant."""
        ident: int = self.appel(modele, "create", [dict(valeurs)])
        return ident


def _ident(valeur: Any) -> int | None:
    """Champ many2one XML-RPC ([id, nom] ou False) -> id ou None."""
    return int(valeur[0]) if valeur else None


def _compte_analytique(odoo: OdooVerif) -> int:
    """Crée un compte analytique (avec un plan à partir de 16).

    L'utilisateur reçoit d'abord le groupe « Comptabilité analytique »,
    absent par défaut d'une base neuve.
    """
    groupe = odoo.lire(
        "ir.model.data",
        [
            ("module", "=", "analytic"),
            ("name", "=", "group_analytic_accounting"),
        ],
        ["res_id"],
    )
    if not groupe:
        raise RuntimeError("Groupe analytic.group_analytic_accounting absent")
    odoo.appel(
        "res.users",
        "write",
        [[odoo.uid], {"groups_id": [(4, groupe[0]["res_id"])]}],
    )
    valeurs: dict[str, Any] = {"name": "Concorde analytique"}
    if "plan_id" in odoo.champs("account.analytic.account"):
        plans = odoo.lire("account.analytic.plan", [], ["id"])
        valeurs["plan_id"] = (
            plans[0]["id"]
            if plans
            else odoo.creer("account.analytic.plan", {"name": "Concorde"})
        )
    return odoo.creer("account.analytic.account", valeurs)


def _ecriture(
    odoo: OdooVerif,
    journal: int,
    jour: str,
    lignes: list[dict[str, Any]],
) -> list[int]:
    """Crée et valide une écriture ; rend les id de ses lignes."""
    ecriture = odoo.creer(
        "account.move",
        {
            "move_type": "entry",
            "journal_id": journal,
            "date": jour,
            "ref": "CONCORDE/photo/%s" % jour,
            "line_ids": [(0, 0, ligne) for ligne in lignes],
        },
    )
    _action(odoo, "account.move", "action_post", [ecriture])
    etat = odoo.lire("account.move", [("id", "=", ecriture)], ["state"])
    if etat[0]["state"] != "posted":
        raise RuntimeError("Écriture %s non validée : %s" % (jour, etat))
    return [
        ligne["id"]
        for ligne in odoo.lire(
            "account.move.line", [("move_id", "=", ecriture)], ["id"]
        )
    ]


def _action(
    odoo: OdooVerif, modele: str, methode: str, ids: list[int]
) -> None:
    """Lance une action Odoo dont on ignore la valeur de retour.

    Rôle : `action_post` ou `reconcile` rendent, selon la version, None ou
    un objet qu'XML-RPC ne sait pas transmettre ; la faute « marshal »
    arrive après l'enregistrement. Toute autre faute est relevée.
    L'appelant vérifie toujours l'effet en relisant la base.
    Paramètres : odoo ; modele ; methode ; ids — enregistrements visés.
    Retour : rien.
    Erreurs : FauteXmlRpc (sauf la faute de transmission du retour).
    Usages : _ecriture, _lettrer.
    """
    try:
        odoo.appel(modele, methode, [ids])
    except FauteXmlRpc as faute:
        if "marshal" not in str(faute):
            raise


def _lettrer(odoo: OdooVerif, lignes: list[int]) -> None:
    """Lettre des lignes, puis vérifie en relisant ; RuntimeError sinon."""
    _action(odoo, "account.move.line", "reconcile", lignes)
    relues = odoo.lire(
        "account.move.line",
        [("id", "in", lignes)],
        ["matched_debit_ids", "matched_credit_ids"],
    )
    if not all(
        ligne["matched_debit_ids"] or ligne["matched_credit_ids"]
        for ligne in relues
    ):
        raise RuntimeError("Lettrage non enregistré : %s" % lignes)


def creer_donnees(odoo: OdooVerif) -> None:
    """Écritures connues sur 2023 et 2024 (vente, encaissements, analytique).

    Erreurs : RuntimeError si un journal ou un compte attendu manque.
    """
    societe = _ident(
        odoo.lire("res.users", [("id", "=", odoo.uid)], ["company_id"])[0][
            "company_id"
        ]
    )
    journaux = {
        journal["type"]: journal
        for journal in odoo.lire(
            "account.journal",
            [("company_id", "=", societe)],
            ["type", "default_account_id"],
        )
    }
    if not {"general", "sale", "bank"} <= set(journaux):
        raise RuntimeError("Journaux attendus absents : %s" % sorted(journaux))
    divers = journaux["general"]["id"]
    produit = _ident(journaux["sale"]["default_account_id"])
    banque = _ident(journaux["bank"]["default_account_id"])
    client = odoo.creer("res.partner", {"name": "Client Concorde"})
    creance = _ident(
        odoo.lire(
            "res.partner",
            [("id", "=", client)],
            ["property_account_receivable_id"],
            {"allowed_company_ids": [societe]},
        )[0]["property_account_receivable_id"]
    )
    analytique = _compte_analytique(odoo)
    if "analytic_distribution" in odoo.champs("account.move.line"):
        lien_analytique: dict[str, Any] = {
            "analytic_distribution": {str(analytique): 100}
        }
    else:
        lien_analytique = {"analytic_account_id": analytique}

    def ligne(compte: Any, debit: str, credit: str, **extra: Any) -> Any:
        """Ligne d'écriture (montants en euros, texte exact)."""
        return dict(
            extra,
            account_id=compte,
            name="Concorde",
            debit=float(debit),
            credit=float(credit),
        )

    vente = _ecriture(
        odoo,
        divers,
        "2023-06-30",
        [
            ligne(creance, "120.00", "0", partner_id=client),
            ligne(produit, "0", "120.00", **lien_analytique),
        ],
    )
    encaissement = _ecriture(
        odoo,
        divers,
        "2024-01-15",
        [
            ligne(banque, "120.00", "0"),
            ligne(creance, "0", "120.00", partner_id=client),
        ],
    )
    _lettrer(odoo, [vente[0], encaissement[1]])
    vente_partielle = _ecriture(
        odoo,
        divers,
        "2024-03-01",
        [
            ligne(creance, "200.00", "0", partner_id=client),
            ligne(produit, "0", "200.00", **lien_analytique),
        ],
    )
    acompte = _ecriture(
        odoo,
        divers,
        "2024-04-02",
        [
            ligne(banque, "80.33", "0"),
            ligne(creance, "0", "80.33", partner_id=client),
        ],
    )
    _lettrer(odoo, [vente_partielle[0], acompte[1]])


def _codes_par_societe(
    odoo: OdooVerif, societes: set[int]
) -> dict[tuple[int, int], str]:
    """{(société, compte): code} lu par l'ORM, société par société."""
    codes: dict[tuple[int, int], str] = {}
    for societe in societes:
        for compte in odoo.lire(
            "account.account",
            [],
            ["code"],
            {"allowed_company_ids": [societe], "active_test": False},
        ):
            codes[(societe, compte["id"])] = str(compte["code"])
    return codes


def photo_orm(odoo: OdooVerif) -> PhotoComptable:
    """Mêmes sections que la photo SQL, calculées par l'ORM d'Odoo."""
    lignes = odoo.lire(
        "account.move.line",
        [("parent_state", "=", "posted")],
        [
            "company_id",
            "date",
            "account_id",
            "partner_id",
            "journal_id",
            "move_id",
            "debit",
            "credit",
            "full_reconcile_id",
            "amount_residual",
        ],
        {"active_test": False},
    )
    societes = {int(ligne["company_id"][0]) for ligne in lignes}
    societes |= {
        societe["id"] for societe in odoo.lire("res.company", [], ["id"])
    }
    codes = _codes_par_societe(odoo, societes)
    journaux = {
        journal["id"]: journal["code"]
        for journal in odoo.lire(
            "account.journal", [], ["code"], {"active_test": False}
        )
    }
    cumuls: dict[str, dict[str, list[int]]] = {
        section: {} for section in SECTIONS_PHOTO if section != "verrous"
    }
    ecritures: dict[str, set[int]] = {}
    for ligne in lignes:
        societe = int(ligne["company_id"][0])
        annee = str(ligne["date"])[:4]
        code = codes[(societe, int(ligne["account_id"][0]))]
        montants = [centimes(ligne["debit"]), centimes(ligne["credit"])]
        ajouter_valeurs(
            cumuls["balance"], "s%s|%s|%s" % (societe, annee, code), montants
        )
        tiers = _ident(ligne["partner_id"])
        if tiers is not None:
            ajouter_valeurs(
                cumuls["balance_tiers"],
                "s%s|%s|%s|p%s" % (societe, annee, code, tiers),
                montants,
            )
        ajouter_valeurs(
            cumuls["lettrage"],
            "s%s|%s" % (societe, code),
            [
                1 if ligne["full_reconcile_id"] else 0,
                centimes(ligne["amount_residual"]),
            ],
        )
        cle_journal = "s%s|%s|%s" % (
            societe,
            annee,
            journaux[int(ligne["journal_id"][0])],
        )
        ecritures.setdefault(cle_journal, set()).add(int(ligne["move_id"][0]))
        ajouter_valeurs(cumuls["journaux"], cle_journal, [0, 1] + montants)
    for cle_journal, pieces in ecritures.items():
        cumuls["journaux"][cle_journal][0] = len(pieces)
    lien = (
        "move_line_id"
        if "move_line_id" in odoo.champs("account.analytic.line")
        else "move_id"
    )
    for analytique in odoo.lire(
        "account.analytic.line",
        [(lien, "!=", False)],
        ["account_id", "amount"],
    ):
        ajouter_valeurs(
            cumuls["analytique"],
            "a%s" % _ident(analytique["account_id"]),
            [1, centimes(analytique["amount"])],
        )
    sections = sections_texte(cumuls)
    sections["verrous"] = _verrous_orm(odoo)
    return {
        "base": odoo.base,
        "version": odoo.version,
        "sections": sections,
        "empreinte": empreinte_sections(sections),
    }


def _verrous_orm(odoo: OdooVerif) -> dict[str, str]:
    """Dates de verrouillage stockées de chaque société, par l'ORM."""
    noms = sorted(
        nom
        for nom, attributs in odoo.champs("res.company").items()
        if nom.endswith("_lock_date") and attributs.get("store")
    )
    verrous: dict[str, str] = {}
    for societe in odoo.lire("res.company", [], noms):
        for nom in noms:
            verrous["s%s|%s" % (societe["id"], nom)] = str(societe[nom] or "")
    return dict(sorted(verrous.items()))


def annoncer(ecarts: list[EcartPhoto], version: str) -> None:
    """Écrit chaque écart en annotation d'erreur de la CI (GitHub)."""
    for ecart in ecarts[:40]:
        print(
            "::error::Odoo %s %s %s : SQL=%r ORM=%r"
            % (
                version,
                ecart["section"],
                ecart["cle"],
                ecart["avant"],
                ecart["apres"],
            )
        )


def main() -> int:
    """Crée les données, compare SQL et ORM ; 0 si zéro écart, 1 sinon."""
    odoo = OdooVerif(
        os.environ["ODOO_URL"],
        os.environ["ODOO_BASE"],
        os.environ["ODOO_UTILISATEUR"],
        os.environ["ODOO_MOT_DE_PASSE"],
    )
    creer_donnees(odoo)
    connexion = connexion_lecture_seule(odoo.base)
    try:
        photo_sql = prendre_photo(connexion, odoo.base)
    finally:
        connexion.close()
    ecarts = comparer_photos(photo_sql, photo_orm(odoo))
    tailles = {
        section: len(valeurs)
        for section, valeurs in photo_sql["sections"].items()
    }
    print("Odoo %s, photo SQL : %s" % (odoo.version, tailles))
    if ecarts:
        annoncer(ecarts, odoo.version)
        print("%d écart(s) entre SQL et ORM." % len(ecarts))
        return 1
    if not all(tailles[section] for section in SECTIONS_PHOTO[:5]):
        print("::error::Odoo %s : section vide %s" % (odoo.version, tailles))
        return 1
    print("Zéro écart entre la photo SQL et l'ORM d'Odoo %s." % odoo.version)
    return 0


if __name__ == "__main__":
    try:
        CODE_SORTIE = main()
    except Exception as exc:
        print("::error::%s : %s" % (type(exc).__name__, str(exc)[:900]))
        raise
    sys.exit(CODE_SORTIE)
