# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la porte 6 : envoi dans la base de test (faux Odoo), relecture."""

import os
import unittest
from collections.abc import Callable

from core.journal import ou_muet
from core.migration import injection
from core.migration.connecteur_fec import lire_fec
from core.migration.correspondance import appliquer
from core.migration.lot import Lot
from tests.outils import CurseurSimule, FauxCommun, FauxOdoo
from tests.outils import BASE, fec

# Rang SQL relu dans la base de test (référence, état, compte, montants…).
RangRelu = tuple[object, ...]


def cible(odoo: FauxOdoo) -> injection.CibleTest:
    """Ouvre la base de test ``concorde_test`` sur le faux Odoo ``odoo``."""
    os.environ["CONCORDE_TEST_BASE"] = "concorde_test"
    return injection.CibleTest(
        "http://127.0.0.1:8017",
        "concorde_test",
        "admin",
        "x",
        proxy_commun=FauxCommun(),
        proxy_objet=odoo,
    )


def lot_pret() -> Lot:
    """Lit le FEC de référence et lui applique la correspondance identique."""
    lot: Lot = lire_fec(fec(*BASE))
    appliquer(lot, identique=True)
    return lot


class TestCible(unittest.TestCase):
    """Garde-fous de la cible : seule la base de test est accessible."""

    def test_seule_la_base_de_test(self) -> None:
        """Vérifie le refus de toute base autre que la base de test."""
        os.environ["CONCORDE_TEST_BASE"] = "concorde_test"
        with self.assertRaises(injection.ErreurInjection):
            injection.CibleTest(
                "http://127.0.0.1:8017",
                "base_production",
                "a",
                "b",
                proxy_commun=FauxCommun(),
                proxy_objet=FauxOdoo(),
            )
        with self.assertRaises(injection.ErreurInjection):
            injection.CibleTest(
                "https://client.odoo.com", "concorde_test", "a", "b"
            )

    def test_methodes_limitees(self) -> None:
        """Vérifie le refus des méthodes Odoo d'effacement ou modification."""
        c = cible(FauxOdoo())
        for m in ("unlink", "write", "button_draft"):
            with self.assertRaises(PermissionError):
                c.appel("account.move", m, [[1]])

    def test_types_pcg(self) -> None:
        """Vérifie le type de compte Odoo déduit du plan comptable."""
        t = injection.type_compte_pcg
        self.assertEqual(t("41110000"), "asset_receivable")
        self.assertEqual(t("40119006"), "liability_payable")
        self.assertEqual(t("40910000"), "asset_current")
        self.assertEqual(t("16409002"), "liability_non_current")
        self.assertEqual(t("21549003"), "asset_non_current")
        self.assertEqual(t("51210000"), "asset_cash")
        self.assertEqual(t("58000000"), "asset_current")
        self.assertEqual(t("68110000"), "expense_depreciation")
        self.assertEqual(t("70609017"), "income")
        self.assertNotIn("equity_unaffected", {t(str(c)) for c in range(10)})


class TestEnvoi(unittest.TestCase):
    """Envoi d'un lot dans le faux Odoo."""

    def test_envoi_complet(self) -> None:
        """Vérifie l'envoi complet : comptes, journaux, tiers, lettrage."""
        odoo = FauxOdoo()
        r = injection.envoyer(cible(odoo), lot_pret())
        self.assertEqual(r["erreurs"], [])
        self.assertEqual(r["creees"], 4)
        self.assertEqual(
            len(r["preparation"]["comptes_crees"]), 6
        )  # 512000 existait
        self.assertEqual(
            r["preparation"]["journaux_crees"], ["AN", "VE", "BQ", "OD"]
        )
        self.assertEqual(r["preparation"]["tiers_crees"], 1)
        self.assertTrue(
            all(m["state"] == "posted" for m in odoo.donnees["account.move"])
        )
        debits = sorted(
            ligne_odoo["debit"]
            for ligne_odoo in odoo.donnees["account.move.line"]
            if ligne_odoo["debit"]
        )
        self.assertEqual(
            debits, [120.0, 120.0, 500.0, 1000.0]
        )  # euros, pas centimes
        self.assertEqual(r["lettrage"]["faites"], 1)  # lettre A, vérifiée
        refs = {m["ref"] for m in odoo.donnees["account.move"]}
        self.assertTrue(all(x.startswith("CONCORDE/") for x in refs))

    def test_reprise_sans_doublon(self) -> None:
        """Vérifie qu'un second envoi ne recrée aucune écriture."""
        odoo = FauxOdoo()
        injection.envoyer(cible(odoo), lot_pret())
        r = injection.envoyer(cible(odoo), lot_pret())
        self.assertEqual((r["deja_presentes"], r["creees"]), (4, 0))
        self.assertEqual(len(odoo.donnees["account.move"]), 4)

    def test_erreur_isolee_par_ecriture(self) -> None:
        """Vérifie qu'un refus d'Odoo n'arrête que l'écriture fautive."""
        odoo = FauxOdoo()
        c = cible(odoo)
        lot = lot_pret()
        # le compte 640000 sera créé avec l'id suivant : Odoo le refusera
        odoo.refuser_compte = None
        comptes, _, _, _ = injection.preparer(c, lot, ou_muet(None))
        odoo.refuser_compte = comptes["640000"][0]
        r = injection.envoyer(c, lot)
        self.assertEqual(r["creees"], 3)
        self.assertEqual(len(r["erreurs"]), 1)
        self.assertEqual(r["erreurs"][0]["ecriture"], "OD/4")
        self.assertIn("compte refusé", r["erreurs"][0]["erreur"])

    def test_devises_refusees(self) -> None:
        """Vérifie le refus d'un lot contenant une devise étrangère."""
        lot = lot_pret()
        lot.lignes[0]["devise"] = "USD"
        with self.assertRaises(injection.ErreurInjection):
            injection.envoyer(cible(FauxOdoo()), lot)


class CurseurRelecture(CurseurSimule):
    """Curseur simulé qui rend toujours les mêmes rangs relus."""

    def __init__(self, rangs: list[RangRelu]) -> None:
        """Retient les rangs que rendra ``fetchall``."""
        self.rangs = rangs

    def execute(self, *_requete: object) -> None:
        """Ignore la requête SQL (les rangs sont fixés à la création)."""

    def fetchall(self) -> list[RangRelu]:
        """Rend les rangs relus."""
        return self.rangs


class FausseConnexionRelecture:
    """Connexion PostgreSQL simulée pour la relecture de la porte 6."""

    def __init__(self, rangs: list[RangRelu]) -> None:
        """Retient les rangs que rendra chaque curseur."""
        self.rangs = rangs

    def cursor(self) -> CurseurRelecture:
        """Ouvre un curseur sur les rangs retenus."""
        return CurseurRelecture(self.rangs)


class TestRelecture(unittest.TestCase):
    """Relecture SQL des écritures envoyées."""

    def rangs(
        self,
        lot: Lot,
        modifier: Callable[[list[list[object]]], None] | None = None,
    ) -> list[RangRelu]:
        """Rangs qu'Odoo rendrait pour ``lot``, abîmés par ``modifier``."""
        lid = injection.lot_id(lot)
        res: list[list[object]] = []
        for ligne_lot in lot.lignes:
            r: list[object] = [
                "CONCORDE/%s/%s/%s"
                % (lid, ligne_lot["journal_code"], ligne_lot["ecriture"]),
                "posted",
                ligne_lot["compte_cible"],
                ligne_lot["tiers_ref"] or None,
                ligne_lot["debit"] / 100,
                ligne_lot["credit"] / 100,
                "A" if ligne_lot["lettrage"] else None,
            ]
            res.append(r)
        if modifier:
            modifier(res)
        return [tuple(r) for r in res]

    def test_conforme(self) -> None:
        """Vérifie qu'une relecture conforme ne donne aucun constat."""
        lot = lot_pret()
        r = injection.relire(lot, FausseConnexionRelecture(self.rangs(lot)))
        self.assertEqual(r.constats, [])

    def test_ecarts(self) -> None:
        """Vérifie la détection des écarts, brouillons et lignes perdues."""
        lot = lot_pret()

        def abimer(rs: list[list[object]]) -> None:
            """Abîme un montant, un état et retire une ligne."""
            rs[0][4] = 999.99  # un montant
            rs[1][1] = "draft"  # une écriture restée en brouillon
            rs.pop()  # une ligne perdue

        r = injection.relire(
            lot, FausseConnexionRelecture(self.rangs(lot, abimer))
        )
        codes = {c["code"] for c in r.constats}
        self.assertTrue(
            {"TEST_ECART", "TEST_NON_VALIDEE", "TEST_ECART_COMPTE"} <= codes
        )


if __name__ == "__main__":
    unittest.main()
