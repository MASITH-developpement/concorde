# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la porte 6 : envoi dans la base de test (faux Odoo) et relecture."""

import os
import unittest
import xmlrpc.client

from core.migration import injection
from core.migration.connecteur_fec import lire_fec
from core.migration.correspondance import appliquer
from tests.test_migration import BASE, fec


class FauxCommun:
    def version(self):
        return {"server_version": "17.0"}

    def authenticate(self, *a):
        return 2


class FauxOdoo:
    """Odoo simulé : comptes, journaux, tiers, écritures, lettrage."""

    def __init__(self, refuser_compte=None):
        self.donnees = {
            "account.account": [
                {"id": 1, "code": "512000", "reconcile": False}
            ],
            "account.journal": [],
            "res.partner": [],
            "account.move": [],
            "account.move.line": [],
        }
        self.appels = []
        self.refuser_compte = refuser_compte
        self.seq = 100

    def _id(self):
        self.seq += 1
        return self.seq

    def execute_kw(self, db, uid, mdp, modele, methode, args, kw):
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
            # comme le vrai Odoo : la méthode ne renvoie rien -> erreur de transmission
            raise xmlrpc.client.Fault(
                1, "TypeError: cannot marshal None unless allow_none"
            )
        raise AssertionError(methode)

    def _creer(self, modele, v):
        i = self._id()
        if modele == "account.move":
            for _, _, l in v["line_ids"]:
                if l["account_id"] == self.refuser_compte:
                    raise xmlrpc.client.Fault(
                        2, "ValidationError: compte refusé"
                    )
            self.donnees[modele].append(
                {"id": i, "ref": v["ref"], "state": "draft"}
            )
            for _, _, l in v["line_ids"]:
                self.donnees["account.move.line"].append(
                    {
                        "id": self._id(),
                        "move_id": [i, v["ref"]],
                        "debit": l["debit"],
                        "credit": l["credit"],
                        "matching_number": False,
                    }
                )
        else:
            self.donnees[modele].append(dict(v, id=i))
        return i


def cible(odoo):
    os.environ["CONCORDE_TEST_BASE"] = "concorde_test"
    return injection.CibleTest(
        "http://127.0.0.1:8017",
        "concorde_test",
        "admin",
        "x",
        proxy_commun=FauxCommun(),
        proxy_objet=odoo,
    )


def lot_pret():
    lot = lire_fec(fec(*BASE))
    appliquer(lot, identique=True)
    return lot


class TestCible(unittest.TestCase):
    def test_seule_la_base_de_test(self):
        os.environ["CONCORDE_TEST_BASE"] = "concorde_test"
        with self.assertRaises(injection.ErreurInjection):
            injection.CibleTest(
                "http://127.0.0.1:8017",
                "alb_alpha",
                "a",
                "b",
                proxy_commun=FauxCommun(),
                proxy_objet=FauxOdoo(),
            )
        with self.assertRaises(injection.ErreurInjection):
            injection.CibleTest(
                "https://client.odoo.com", "concorde_test", "a", "b"
            )

    def test_methodes_limitees(self):
        c = cible(FauxOdoo())
        for m in ("unlink", "write", "button_draft"):
            with self.assertRaises(PermissionError):
                c.appel("account.move", m, [[1]])

    def test_types_pcg(self):
        t = injection.type_compte_pcg
        self.assertEqual(t("41110000"), "asset_receivable")
        self.assertEqual(t("40110000"), "liability_payable")
        self.assertEqual(t("40910000"), "asset_current")
        self.assertEqual(t("16400000"), "liability_non_current")
        self.assertEqual(t("21540000"), "asset_non_current")
        self.assertEqual(t("51210000"), "asset_cash")
        self.assertEqual(t("58000000"), "asset_current")
        self.assertEqual(t("68110000"), "expense_depreciation")
        self.assertEqual(t("70600000"), "income")
        self.assertNotIn("equity_unaffected", {t(str(c)) for c in range(10)})


class TestEnvoi(unittest.TestCase):
    def test_envoi_complet(self):
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
            l["debit"] for l in odoo.donnees["account.move.line"] if l["debit"]
        )
        self.assertEqual(
            debits, [120.0, 120.0, 500.0, 1000.0]
        )  # euros, pas centimes
        self.assertEqual(r["lettrage"]["faites"], 1)  # lettre A, vérifiée
        refs = {m["ref"] for m in odoo.donnees["account.move"]}
        self.assertTrue(all(x.startswith("CONCORDE/") for x in refs))

    def test_reprise_sans_doublon(self):
        odoo = FauxOdoo()
        injection.envoyer(cible(odoo), lot_pret())
        r = injection.envoyer(cible(odoo), lot_pret())
        self.assertEqual((r["deja_presentes"], r["creees"]), (4, 0))
        self.assertEqual(len(odoo.donnees["account.move"]), 4)

    def test_erreur_isolee_par_ecriture(self):
        odoo = FauxOdoo()
        c = cible(odoo)
        lot = lot_pret()
        # le compte 640000 sera créé avec l'id suivant : on le fait refuser par Odoo
        odoo.refuser_compte = None
        comptes, _, _, _ = injection.preparer(c, lot, injection.ou_muet(None))
        odoo.refuser_compte = comptes["640000"][0]
        r = injection.envoyer(c, lot)
        self.assertEqual(r["creees"], 3)
        self.assertEqual(len(r["erreurs"]), 1)
        self.assertEqual(r["erreurs"][0]["ecriture"], "OD/4")
        self.assertIn("compte refusé", r["erreurs"][0]["erreur"])

    def test_devises_refusees(self):
        lot = lot_pret()
        lot.lignes[0]["devise"] = "USD"
        with self.assertRaises(injection.ErreurInjection):
            injection.envoyer(cible(FauxOdoo()), lot)


class FausseConnexionRelecture:
    def __init__(self, rangs):
        self.rangs = rangs

    def cursor(self):
        rangs = self.rangs

        class C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                pass

            def fetchall(self):
                return rangs

        return C()


class TestRelecture(unittest.TestCase):
    def rangs(self, lot, modifier=None):
        lid = injection.lot_id(lot)
        res = []
        for l in lot.lignes:
            r = [
                "CONCORDE/%s/%s/%s" % (lid, l["journal_code"], l["ecriture"]),
                "posted",
                l["compte_cible"],
                l["tiers_ref"] or None,
                l["debit"] / 100,
                l["credit"] / 100,
                "A" if l["lettrage"] else None,
            ]
            res.append(r)
        if modifier:
            modifier(res)
        return [tuple(r) for r in res]

    def test_conforme(self):
        lot = lot_pret()
        r = injection.relire(lot, FausseConnexionRelecture(self.rangs(lot)))
        self.assertEqual(r.constats, [])

    def test_ecarts(self):
        lot = lot_pret()

        def abimer(rs):
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
