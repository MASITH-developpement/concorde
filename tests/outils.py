# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Doublures partagées par les tests (fausses connexions Odoo et PostgreSQL).

Chaque doublure utilisée par au moins deux fichiers de test vit ici, une
seule fois, pour ne jamais être recopiée.
"""

import os
from types import TracebackType
from typing import Any, Literal, TypeVar

from core.migration import injection

# Dossier racine du dépôt (parent du dossier tests/).
RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Enregistrement Odoo tel que le rend XML-RPC (valeurs hétérogènes : texte,
# nombre, booléen, paire [id, nom]…), ou ligne de données de test.
Enregistrement = dict[str, Any]


class FauxCommun:
    """Point d'entrée XML-RPC « common » d'un Odoo 17 simulé.

    Rôle : remplace ``xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common")``
    pour l'identification, sans réseau.
    Usages : ``tests/test_injection.py``, ``tests/test_odoo_donnees.py``,
    ``tests/test_interface.py``.
    """

    def version(self) -> dict[str, str]:
        """Rend la version du serveur simulé.

        Paramètres : aucun.
        Retour : ``{"server_version": "17.0"}``.
        Erreurs : aucune.
        Usages : détection de version par les sources et l'injection.
        """
        return {"server_version": "17.0"}

    def authenticate(self, *_identifiants: object) -> int:
        """Accepte toute identification et rend l'utilisateur n° 2.

        Paramètres : ``_identifiants`` (base, identifiant, clé, contexte),
        ignorés.
        Retour : l'identifiant d'utilisateur Odoo ``2``.
        Erreurs : aucune.
        Usages : ouverture de session des sources et de l'injection simulées.
        """
        return 2


CurseurAvecContexte = TypeVar("CurseurAvecContexte", bound="CurseurSimule")


class CurseurSimule:
    """Base des faux curseurs PostgreSQL utilisables avec ``with``.

    Rôle : fournit le protocole de gestionnaire de contexte d'un curseur
    psycopg (``with connexion.cursor() as curseur``) ; chaque doublure en
    hérite et n'écrit que ``execute`` / ``fetch*``.
    Usages : ``tests/test_bases_locales.py``, ``tests/test_injection.py``.
    """

    def __enter__(self: CurseurAvecContexte) -> CurseurAvecContexte:
        """Ouvre le bloc ``with``.

        Paramètres : aucun.
        Retour : le curseur lui-même.
        Erreurs : aucune.
        Usages : ``with connexion.cursor() as curseur``.
        """
        return self

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> Literal[False]:
        """Ferme le bloc ``with`` sans masquer d'exception.

        Paramètres : ``type_exception``, ``exception``, ``trace`` — exception
        levée dans le bloc (``None`` s'il n'y en a pas).
        Retour : ``False`` : toute exception est propagée.
        Erreurs : aucune.
        Usages : fin du bloc ``with connexion.cursor() as curseur``.
        """
        return False


# --- FEC de test (tests/test_migration.py, tests/test_connecteurs.py) ---
ENTETE = (
    "JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|"
    "CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|"
    "EcritureLet|DateLet|ValidDate|Montantdevise|Idevise"
)


def ligne_fec(
    j: str,
    num: str,
    d: str,
    compte: str,
    debit: str = "0,00",
    credit: str = "0,00",
    aux: str = "",
    lib: str = "lib",
    let: str = "",
) -> str:
    """Construit une ligne FEC (séparateur « | ») avec les 18 colonnes."""
    return "|".join(
        [
            j,
            j + " lib",
            num,
            d,
            compte,
            "Compte " + compte,
            aux,
            ("Tiers " + aux) if aux else "",
            "P" + num,
            d,
            lib,
            debit,
            credit,
            let,
            d if let else "",
            d,
            "",
            "",
        ]
    )


def fec(*lignes: str, entete: str = ENTETE) -> bytes:
    """Assemble un fichier FEC complet (en-tête + lignes) en ISO-8859-15."""
    return ("\n".join([entete] + list(lignes)) + "\n").encode("iso-8859-15")


BASE = [
    ligne_fec("AN", "1", "20250101", "512000", "1000,00"),
    ligne_fec("AN", "1", "20250101", "101000", credit="1000,00"),
    ligne_fec("VE", "2", "20250115", "411000", "120,00", aux="C1", let="A"),
    ligne_fec("VE", "2", "20250115", "706000", credit="100,00"),
    ligne_fec("VE", "2", "20250115", "445710", credit="20,00"),
    ligne_fec("BQ", "3", "20250120", "512000", "120,00"),
    ligne_fec(
        "BQ", "3", "20250120", "411000", credit="120,00", aux="C1", let="A"
    ),
    ligne_fec("OD", "4", "20250131", "640000", "500,00"),
    ligne_fec("OD", "4", "20250131", "421000", credit="500,00"),
]


# --- Odoo simulés (envoi : test_injection, test_connecteurs ;
# lecture XML-RPC : test_odoo_donnees, test_connecteurs) ---
class FauxOdoo:
    """Odoo simulé : comptes, journaux, tiers, écritures, lettrage."""

    def __init__(self, refuser_compte: int | None = None) -> None:
        """Crée un Odoo vide (un seul compte 512000) ; ``refuser_compte``."""
        self.donnees: dict[str, list[Enregistrement]] = {
            "account.account": [
                {"id": 1, "code": "512000", "reconcile": False}
            ],
            "account.journal": [],
            "res.partner": [],
            "account.move": [],
            "account.move.line": [],
        }
        self.appels: list[tuple[str, str]] = []
        self.refuser_compte = refuser_compte
        self.seq = 100

    def _id(self) -> int:
        """Rend le prochain identifiant d'enregistrement."""
        self.seq += 1
        return self.seq

    def execute_kw(
        self,
        db: str,
        uid: int,
        mdp: str,
        modele: str,
        methode: str,
        args: list[Any],
        kw: dict[str, Any],
    ) -> object:
        """Simule ``execute_kw`` : lecture, création, validation, lettrage."""
        self.appels.append((modele, methode))
        recs = self.donnees[modele]
        if methode == "search_read":
            dom = args[0]
            res = recs
            for champ, op, val in dom:
                if op == "in":
                    if champ == "move_id":
                        res = [r for r in res if r["move_id"][0] in val]
                    else:
                        res = [r for r in res if r.get(champ) in val]
            return [dict(r) for r in res]
        if methode == "read":
            return [dict(r) for r in recs if r["id"] in args[0]]
        if methode == "create":
            vals = args[0]
            if isinstance(vals, list):
                return [self._creer(modele, v) for v in vals]
            return self._creer(modele, vals)
        if methode == "action_post":
            for m in recs:
                if m["id"] in args[0]:
                    m["state"] = "posted"
            return True
        if methode == "reconcile":
            for ml in self.donnees["account.move.line"]:
                if ml["id"] in args[0]:
                    ml["matching_number"] = "M%d" % args[0][0]
            # comme le vrai Odoo : la méthode ne renvoie rien, d'où une
            # erreur de transmission XML-RPC
            raise injection.FauteXmlRpc(
                1, "TypeError: cannot marshal None unless allow_none"
            )
        raise AssertionError(methode)

    def _creer(self, modele: str, v: Enregistrement) -> int:
        """Enregistre ``v`` ; une écriture crée aussi ses lignes."""
        i = self._id()
        if modele == "account.move":
            for _, _, valeurs_ligne in v["line_ids"]:
                if valeurs_ligne["account_id"] == self.refuser_compte:
                    raise injection.FauteXmlRpc(
                        2, "ValidationError: compte refusé"
                    )
            self.donnees[modele].append(
                {"id": i, "ref": v["ref"], "state": "draft"}
            )
            for _, _, valeurs_ligne in v["line_ids"]:
                self.donnees["account.move.line"].append(
                    {
                        "id": self._id(),
                        "move_id": [i, v["ref"]],
                        "debit": valeurs_ligne["debit"],
                        "credit": valeurs_ligne["credit"],
                        "matching_number": False,
                    }
                )
        else:
            self.donnees[modele].append(dict(v, id=i))
        return i


class FauxObjet:
    """Odoo 17 simulé pour la source XML-RPC (pagination par id comprise)."""

    def __init__(self) -> None:
        """Prépare les enregistrements Odoo simulés et le relevé d'appels."""
        self.appels: list[tuple[str, str]] = []
        self.donnees: dict[str, list[Enregistrement]] = {
            "res.company": [
                {
                    "id": 1,
                    "name": "Soc",
                    "company_registry": "666666664",
                    "vat": False,
                    "currency_id": [1, "EUR"],
                    "fiscalyear_last_month": "12",
                    "fiscalyear_last_day": 31,
                    "account_opening_move_id": False,
                    "tax_cash_basis_journal_id": False,
                    "account_journal_payment_debit_account_id": False,
                    "account_journal_payment_credit_account_id": False,
                    "account_journal_suspense_account_id": False,
                    "transfer_account_id": False,
                }
            ],
            "account.account": [
                {
                    "id": 1,
                    "code": "706000",
                    "name": "Prestations",
                    "account_type": "income",
                    "reconcile": False,
                    "deprecated": False,
                },
                {
                    "id": 2,
                    "code": "411000",
                    "name": "Clients",
                    "account_type": "asset_receivable",
                    "reconcile": True,
                    "deprecated": False,
                },
            ],
            "account.journal": [
                {
                    "id": 1,
                    "code": "VEN",
                    "name": "Ventes",
                    "type": "sale",
                    "active": True,
                    "default_account_id": [1, "706000"],
                    "suspense_account_id": False,
                }
            ],
            "account.payment.method.line": [],
            "account.tax": [],
            "account.tax.repartition.line": [],
            "account.move": [
                {
                    "id": 5,
                    "name": "VEN/1",
                    "move_type": "out_invoice",
                    "state": "posted",
                    "journal_id": [1, "Ventes"],
                    "date": "2025-10-03",
                    "invoice_date": "2025-10-03",
                    "ref": False,
                    "write_date": "2025-10-03 10:00:00",
                    "auto_post": "no",
                    "tax_cash_basis_rec_id": False,
                    "reversed_entry_id": False,
                }
            ],
            "res.partner": [
                {
                    "id": 7,
                    "name": "ACME",
                    "ref": "C7",
                    "vat": "FR72666666664",
                    "company_registry": "666666664",
                    "email": False,
                    "phone": False,
                    "street": False,
                    "zip": False,
                    "city": False,
                    "country_code": "FR",
                    "is_company": True,
                    "active": True,
                    "customer_rank": 1,
                    "supplier_rank": 0,
                    "parent_id": False,
                }
            ],
            "account.full.reconcile": [
                {"id": 3, "create_date": "2025-11-02 08:00:00"}
            ],
            "account.analytic.account": [
                {"id": 9, "code": "AXE1", "name": "Axe 1"}
            ],
            "account.move.line": [
                {
                    "id": i,
                    "move_id": [5, "VEN/1"],
                    "account_id": [acc, ""],
                    "partner_id": [7, "ACME"],
                    "name": "L%d" % i,
                    "debit": d,
                    "credit": c,
                    "matching_number": "A1" if acc == 2 else False,
                    "full_reconcile_id": [3, "A1"] if acc == 2 else False,
                    "amount_currency": d - c,
                    "currency_id": [1, "EUR"],
                    "company_currency_id": [1, "EUR"],
                    "date_maturity": False,
                    "write_date": "2025-10-03 10:00:00",
                    "date": "2025-10-03",
                    "parent_state": "posted",
                }
                for i, acc, d, c in ((11, 1, 0.0, 100.1), (12, 2, 100.1, 0.0))
            ],
        }

    def execute_kw(
        self,
        db: str,
        uid: int,
        cle: str,
        modele: str,
        methode: str,
        args: list[Any],
        kw: dict[str, Any],
    ) -> list[Enregistrement]:
        """Simule ``read`` et ``search_read`` (pagination par id)."""
        self.appels.append((modele, methode))
        recs = self.donnees[modele]
        if methode == "read":
            return [r for r in recs if r["id"] in args[0]]
        dom = args[0]
        mini = max(
            [
                c[2]
                for c in dom
                if isinstance(c, tuple) and c[:2] == ("id", ">")
            ]
            or [0]
        )
        res = [r for r in recs if r["id"] > mini]
        return res[: kw.get("limit") or None]
