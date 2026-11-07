# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la passerelle Odoo 17 : lecture (XML-RPC simulé), FEC, xlsx, CSV, analyse."""

import csv
import io
import os
import re
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal

from core.analyser import analyser
from core.canonical import ErreurMontant
from core.odoo_source import SourceXmlRpcOdoo17, centimes
from core.telecharger import (
    COLONNES_FEC,
    ErreurFec,
    csv_ecritures,
    generer_fec,
    generer_xlsx,
    nom_fichier_fec,
)
from core.xlsx_ecrire import Centimes, ecrire_xlsx, euros_texte


def ligne(**kw):
    base = {
        "ligne_id": 1,
        "ecriture_id": 1,
        "ecriture": "VEN/2025/0001",
        "type_piece": "out_invoice",
        "etat": "posted",
        "journal_code": "VEN",
        "journal_lib": "Ventes",
        "date": date(2025, 10, 3),
        "piece_date": None,
        "reference": "F001",
        "compte": "706000",
        "compte_lib": "Prestations",
        "compte_type": "income",
        "tiers_id": 7,
        "tiers_ref": "C7",
        "tiers_nom": "ACME",
        "libelle": "Prestation",
        "debit": 0,
        "credit": 0,
        "lettrage": "",
        "date_lettrage": None,
        "montant_devise": None,
        "devise": "",
        "echeance": None,
        "modifie_le": "2025-10-03 10:00:00",
        "auto_post": "no",
    }
    base.update(kw)
    return base


def facture_equilibree(eid=1, montant=12000, **kw):
    """Facture de 100 € HT + 20 € TVA = 120 € TTC."""
    return [
        ligne(
            ligne_id=eid * 10 + 1,
            ecriture_id=eid,
            credit=montant * 10 // 12,
            **kw
        ),
        ligne(
            ligne_id=eid * 10 + 2,
            ecriture_id=eid,
            compte="445710",
            credit=montant * 2 // 12,
            **kw
        ),
        ligne(
            ligne_id=eid * 10 + 3,
            ecriture_id=eid,
            compte="411000",
            compte_type="asset_receivable",
            debit=montant,
            lettrage="A1",
            date_lettrage=date(2025, 11, 2),
            **kw
        ),
    ]


class TestCentimes(unittest.TestCase):
    def test_decimal_et_float_exacts(self):
        self.assertEqual(centimes(Decimal("1234.56")), 123456)
        self.assertEqual(centimes(1234.56), 123456)
        self.assertEqual(centimes(0.1), 10)
        self.assertEqual(centimes(False), 0)
        self.assertEqual(centimes(-12.5), -1250)

    def test_refus_arrondi_silencieux(self):
        with self.assertRaises(ErreurMontant):
            centimes(Decimal("1.234"))
        with self.assertRaises(ErreurMontant):
            centimes(0.1 + 0.2)  # 0.30000000000000004

    def test_euros_texte(self):
        self.assertEqual(euros_texte(123456), "1234.56")
        self.assertEqual(euros_texte(-5, ","), "-0,05")
        self.assertEqual(euros_texte(0, ","), "0,00")


class TestFec(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.chemin = os.path.join(self.dossier, "FEC.txt")

    def lire(self, encodage="iso-8859-15"):
        with open(self.chemin, encoding=encodage) as f:
            return [l.rstrip("\r\n").split("|") for l in f]

    def test_fec_conforme(self):
        r = generer_fec(facture_equilibree(), self.chemin)
        self.assertEqual(r["lignes"], 3)
        self.assertEqual(r["total_debit"], r["total_credit"])
        rangs = self.lire()
        self.assertEqual(tuple(rangs[0]), COLONNES_FEC)
        self.assertTrue(all(len(x) == 18 for x in rangs))
        client = rangs[3]
        self.assertEqual(client[4], "411000")
        self.assertEqual(client[6:8], ["C7", "ACME"])  # auxiliaire sur 411
        self.assertEqual(rangs[1][6:8], ["", ""])  # pas d'auxiliaire sur 706
        self.assertEqual(client[11], "120,00")
        self.assertEqual(client[13:15], ["A1", "20251102"])
        self.assertEqual(client[3], "20251003")

    def test_desequilibre_refuse_sans_fichier(self):
        lignes = facture_equilibree()
        lignes[0]["credit"] -= 1  # 1 centime d'écart
        with self.assertRaises(ErreurFec):
            generer_fec(lignes, self.chemin)
        self.assertFalse(os.path.exists(self.chemin))
        self.assertFalse(os.path.exists(self.chemin + ".partiel"))

    def test_brouillon_refuse(self):
        with self.assertRaises(ErreurFec):
            generer_fec(facture_equilibree(etat="draft"), self.chemin)

    def test_devise_hors_euro_refusee(self):
        with self.assertRaises(ErreurFec):
            generer_fec(facture_equilibree(), self.chemin, devise="USD")

    def test_typographie_et_separateur(self):
        lignes = facture_equilibree()
        lignes[0]["libelle"] = "l’essai | “test” – fin…\nsuite"
        lignes[1]["libelle"] = "Ω inconnu"
        r = generer_fec(lignes, self.chemin)
        rangs = self.lire()
        self.assertEqual(rangs[1][10], 'l\'essai   "test" - fin... suite')
        self.assertEqual(rangs[2][10], "? inconnu")
        self.assertEqual(
            r["caracteres_remplaces"], 1
        )  # seul Ω est perdu, et compté

    def test_nom_reglementaire(self):
        self.assertEqual(
            nom_fichier_fec("384684957", date(2025, 12, 31)),
            "384684957FEC20251231.txt",
        )


class TestXlsx(unittest.TestCase):
    def test_classeur_valide_et_montants_exacts(self):
        chemin = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        n = generer_xlsx(
            chemin,
            lignes=facture_equilibree(),
            comptes=[
                {
                    "code": "411000",
                    "libelle": "Clients & co <x>",
                    "type": "asset_receivable",
                    "lettrable": True,
                    "deprecie": False,
                    "id": 3,
                }
            ],
        )
        self.assertEqual(n, {"Ecritures": 3, "Comptes": 1})
        with zipfile.ZipFile(chemin) as z:
            self.assertIsNone(z.testzip())
            feuille = z.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("<v>120.00</v>", feuille)
            self.assertIn("<v>45933</v>", feuille)  # 03/10/2025 en série Excel
            self.assertIn(
                "Clients &amp; co &lt;x&gt;",
                z.read("xl/worksheets/sheet2.xml").decode(),
            )
            self.assertIn(
                'name="Ecritures"', z.read("xl/workbook.xml").decode()
            )

    def test_caracteres_de_controle_retires(self):
        chemin = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        ecrire_xlsx(chemin, [("F", ["a"], [["x\x01y"], [Centimes(-5)]])])
        with zipfile.ZipFile(chemin) as z:
            f = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn(">xy<", f)
        self.assertIn("<v>-0.05</v>", f)


class TestCsv(unittest.TestCase):
    def test_entete_sur_premiere_ligne_seulement(self):
        lignes = facture_equilibree() + facture_equilibree(eid=2)
        rangs = list(
            csv.reader(io.StringIO(csv_ecritures(lignes).lstrip("﻿")))
        )
        self.assertEqual(rangs[0][0], "journal_id/code")
        entetes = [r for r in rangs[1:] if r[0]]
        self.assertEqual(len(entetes), 2)
        self.assertEqual(rangs[3][6:], ["120.00", "0.00"])
        self.assertEqual(rangs[1][5], "concorde_tiers_7")


class TestAnalyse(unittest.TestCase):
    def analyse(self, lignes, **kw):
        return analyser(lignes, aujourd_hui=date(2026, 11, 6), **kw).en_dict()

    def codes(self, d):
        return {c["code"]: c["nombre"] for c in d["constats"]}

    def test_conforme(self):
        d = self.analyse(facture_equilibree())
        self.assertEqual(d["statut"], "conforme")
        self.assertEqual(d["infos"]["total_debit"], "120,00")

    def test_desequilibre_bloquant(self):
        lignes = facture_equilibree()
        lignes[0]["credit"] += 1
        d = self.analyse(lignes)
        self.assertEqual(d["statut"], "bloquant")
        self.assertIn("ECRITURE_DESEQUILIBREE", self.codes(d))
        self.assertIn("TOTAL_DESEQUILIBRE", self.codes(d))

    def test_alertes(self):
        lignes = facture_equilibree()
        lignes[2]["tiers_id"] = None  # 411 sans tiers
        lignes += [
            ligne(ligne_id=99, ecriture_id=9, ecriture="OD/1", debit=0)
        ]  # 1 ligne, nulle
        lignes += facture_equilibree(eid=3, date=date(2030, 1, 1))  # future
        lignes += facture_equilibree(eid=4)  # doublon de 1
        c = self.codes(self.analyse(lignes))
        self.assertEqual(c["TIERS_MANQUANT"], 1)
        self.assertEqual(c["ECRITURE_UNE_LIGNE"], 1)
        self.assertEqual(c["LIGNE_MONTANT_NUL"], 1)
        self.assertEqual(c["DATE_FUTURE"], 1)
        self.assertEqual(c["DOUBLON_PROBABLE"], 1)

    def test_amortissement_planifie_en_info(self):
        lignes = facture_equilibree(
            etat="draft",
            auto_post="at_date",
            date=date(2045, 12, 31),
            ecriture="/",
        )
        d = self.analyse(lignes)
        c = self.codes(d)
        self.assertNotIn("DATE_FUTURE", c)
        self.assertEqual(c["ECRITURE_PLANIFIEE"], 1)
        self.assertEqual(d["statut"], "conforme")

    def test_tiers(self):
        t = {
            "nom": "",
            "ref": "",
            "tva": "",
            "siren": "",
            "email": "",
            "telephone": "",
            "rue": "",
            "cp": "",
            "ville": "",
            "pays": "FR",
            "societe": True,
            "actif": True,
            "client": True,
            "fournisseur": False,
            "parent_id": None,
        }
        tiers = [
            dict(t, id=7, nom="ACME SARL"),
            dict(t, id=8, nom="Acme", tva="FR02384684957"),
            dict(t, id=9, nom="Ltd", pays="GB", siren="HRB 123"),
            dict(t, id=10, nom="Bad", siren="123456789"),
        ]
        lignes = []
        for i, tid in enumerate((7, 8, 9, 10), 1):
            lignes += facture_equilibree(
                eid=i, tiers_id=tid, reference="R%d" % i
            )
        c = self.codes(self.analyse(lignes, tiers=tiers))
        self.assertEqual(
            c["TIERS_SANS_SIREN_TVA"], 1
        )  # ACME seulement (GB exclu)
        self.assertEqual(c["SIREN_INVALIDE"], 1)  # Bad ; HRB (GB) ignoré
        self.assertEqual(c["TIERS_DOUBLON"], 1)  # ACME SARL ~ Acme


class FauxCommun:
    def version(self):
        return {"server_version": "17.0"}

    def authenticate(self, *a):
        return 2


class FauxObjet:
    """Odoo 17 simulé pour la source XML-RPC (pagination par id comprise)."""

    def __init__(self):
        self.appels = []
        self.donnees = {
            "res.company": [
                {
                    "id": 1,
                    "name": "Soc",
                    "company_registry": "384684957",
                    "vat": False,
                    "currency_id": [1, "EUR"],
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
                }
            ],
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
                }
            ],
            "res.partner": [
                {
                    "id": 7,
                    "name": "ACME",
                    "ref": "C7",
                    "vat": "FR02384684957",
                    "company_registry": "384684957",
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
                }
                for i, acc, d, c in ((11, 1, 0.0, 100.1), (12, 2, 100.1, 0.0))
            ],
        }

    def execute_kw(self, db, uid, cle, modele, methode, args, kw):
        self.appels.append((modele, methode))
        recs = self.donnees[modele]
        if methode == "read":
            return [r for r in recs if r["id"] in args[0]]
        dom = args[0]
        mini = max(
            [c[2] for c in dom if isinstance(c, tuple) and c[0] == "id"] or [0]
        )
        res = [r for r in recs if r["id"] > mini]
        return res[: kw.get("limit") or None]


class TestSourceXmlRpc(unittest.TestCase):
    def source(self):
        self.objet = FauxObjet()
        return SourceXmlRpcOdoo17(
            "http://x",
            "b",
            "u",
            "cle",
            proxy_commun=FauxCommun(),
            proxy_objet=self.objet,
        )

    def test_lignes_normalisees(self):
        lignes = self.source().lignes()
        self.assertEqual(len(lignes), 2)
        client = lignes[1]
        self.assertEqual(
            (client["compte"], client["compte_type"]),
            ("411000", "asset_receivable"),
        )
        self.assertEqual(client["debit"], 10010)
        self.assertEqual(
            (client["tiers_ref"], client["lettrage"]), ("C7", "A1")
        )
        self.assertEqual(client["date_lettrage"], date(2025, 11, 2))
        self.assertIsNone(client["montant_devise"])  # devise = société
        self.assertEqual(lignes[0]["lettrage"], "")
        self.assertEqual(lignes[0]["journal_code"], "VEN")

    def test_lecture_seule(self):
        s = self.source()
        with self.assertRaises(PermissionError):
            s._appel("account.move", "write", [[5], {"ref": "x"}])
        with self.assertRaises(PermissionError):
            s._appel("account.move", "unlink", [[5]])

    def test_pagination(self):
        s = self.source()
        s.TAILLE_LOT = 1
        self.assertEqual(len(s.comptes()), 2)
        self.assertEqual(
            sum(
                1
                for m, meth in self.objet.appels
                if m == "account.account" and meth == "search_read"
            ),
            3,
        )

    def test_version_autre_que_17_refusee(self):
        class Commun18(FauxCommun):
            def version(self):
                return {"server_version": "18.0"}

        from core.odoo_source import ErreurSource

        with self.assertRaises(ErreurSource):
            SourceXmlRpcOdoo17(
                "http://x",
                "b",
                "u",
                "c",
                proxy_commun=Commun18(),
                proxy_objet=FauxObjet(),
            )

    def test_fec_depuis_xmlrpc(self):
        chemin = os.path.join(tempfile.mkdtemp(), "f.txt")
        r = generer_fec(self.source().lignes(), chemin)
        self.assertEqual((r["total_debit"], r["total_credit"]), (10010, 10010))
        with open(chemin, encoding="iso-8859-15") as f:
            self.assertTrue(
                re.search(r"\|411000\|Clients\|C7\|ACME\|", f.read())
            )


if __name__ == "__main__":
    unittest.main()
