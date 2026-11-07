# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la migration ERP -> Odoo, portes 1 à 5 (ADR-0004)."""

import json
import os
import tempfile
import unittest
from datetime import date

from core.journal import Journal
from core.migration import controles, correspondance, filtres
from core.migration.circuit import executer
from core.migration.connecteur_fec import ErreurConnecteur, lire_fec

ENTETE = (
    "JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|"
    "CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|"
    "ValidDate|Montantdevise|Idevise"
)


def L(
    j, num, d, compte, debit="0,00", credit="0,00", aux="", lib="lib", let=""
):
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


def fec(*lignes, entete=ENTETE):
    return ("\n".join([entete] + list(lignes)) + "\n").encode("iso-8859-15")


BASE = [
    L("AN", "1", "20250101", "512000", "1000,00"),
    L("AN", "1", "20250101", "101000", credit="1000,00"),
    L("VE", "2", "20250115", "411000", "120,00", aux="C1", let="A"),
    L("VE", "2", "20250115", "706000", credit="100,00"),
    L("VE", "2", "20250115", "445710", credit="20,00"),
    L("BQ", "3", "20250120", "512000", "120,00"),
    L("BQ", "3", "20250120", "411000", credit="120,00", aux="C1", let="A"),
    L("OD", "4", "20250131", "640000", "500,00"),
    L("OD", "4", "20250131", "421000", credit="500,00"),
]
AUJ = date(2026, 11, 6)


class TestConnecteur(unittest.TestCase):
    def test_lecture_complete(self):
        lot = lire_fec(fec(*BASE))
        self.assertEqual(
            lot.totaux(),
            {"lignes": 9, "ecritures": 4, "debit": 174000, "credit": 174000},
        )
        l = lot.lignes[2]
        self.assertEqual(
            (l["tiers_ref"], l["tiers_nom"], l["lettrage"]),
            ("C1", "Tiers C1", "A"),
        )
        self.assertEqual(l["n"], 4)  # numéro de ligne du fichier

    def test_rien_n_est_saute_ni_dedoublonne(self):
        lot = lire_fec(
            fec(
                *(
                    BASE
                    + [
                        "VE|trop|court",
                        BASE[3],
                        L("VE", "9", "20250115", "706000", credit="1,234"),
                    ]
                )
            )
        )
        self.assertEqual(len(lot.illisibles), 2)  # colonnes + 3 décimales
        self.assertEqual(
            sum(1 for l in lot.lignes if l["n"] == 5 or l["n"] == 12), 2
        )

    def test_utf8_bom_tab_et_entete_absente(self):
        brut = (
            b"\xef\xbb\xbf"
            + fec(*BASE).decode("iso-8859-15").replace("|", "\t").encode()
        )
        self.assertEqual(lire_fec(brut).source["separateur"], "\t")
        with self.assertRaises(ErreurConnecteur):
            lire_fec(b"pas un fec\n1|2|3\n")


class TestControles(unittest.TestCase):
    def codes(self, *lignes):
        return {
            c["code"]: c["nombre"]
            for c in controles.controler(lire_fec(fec(*lignes)), AUJ).constats
        }

    def test_lot_sain(self):
        self.assertEqual(self.codes(*BASE), {})

    def test_bloquants(self):
        c = self.codes(
            *(
                BASE
                + [
                    L(
                        "OD", "5", "20250131", "601000", "10,00"
                    ),  # déséquilibrée, 1 ligne
                    L("OD", "6", "20250131", "0", "5,00"),
                    L(
                        "OD", "6", "20250201", "401000", credit="5,00", aux="F"
                    ),  # 2 mois + compte 0
                    L("OD", "7", "20271231", "601000", "1,00"),
                    L(
                        "OD", "7", "20271231", "401000", credit="1,00", aux="F"
                    ),  # future
                    L("OD", "8", "20250131", "601000"),
                    L("OD", "8", "20250131", "401000", aux="F"),
                ]
            )
        )  # nulles
        for code in (
            "MIG_ECRITURE_DESEQUILIBREE",
            "MIG_FICHIER_DESEQUILIBRE",
            "MIG_ECRITURE_UNE_LIGNE",
            "MIG_COMPTE_INVALIDE",
            "MIG_ECRITURE_DEUX_MOIS",
            "MIG_DATE_FUTURE",
            "MIG_MONTANT_NUL",
        ):
            self.assertIn(code, c, code)
        self.assertEqual(c["MIG_MONTANT_NUL"], 2)

    def test_alertes(self):
        c = self.codes(
            *(
                BASE
                + [
                    BASE[5],
                    BASE[6],  # doublons (BQ/3)
                    L("XX", "2", "20250115", "601000", "3,00"),
                    L("XX", "2", "20250115", "411000", credit="3,00"),
                ]
            )
        )
        self.assertEqual(c["MIG_LIGNE_DOUBLON"], 2)
        self.assertEqual(c["MIG_ECRITURE_DEUX_JOURNAUX"], 1)
        self.assertEqual(c["MIG_TIERS_MANQUANT"], 1)
        self.assertEqual(c["MIG_LETTRAGE_NON_SOLDE"], 1)  # lettre A doublée


class TestFiltres(unittest.TestCase):
    def test_a_nouveaux_sur_une_periode(self):
        lot = lire_fec(fec(*BASE))
        r = filtres.appliquer(
            lot,
            [
                {
                    "nom": "AN",
                    "journaux": ["AN"],
                    "du": "2025-01-01",
                    "au": "2025-01-31",
                }
            ],
        )
        self.assertEqual(r["filtres"][0]["ecritures"], 1)
        self.assertEqual(r["filtres"][0]["debit"], 100000)
        self.assertEqual(lot.totaux()["debit"], 74000)
        self.assertEqual(len(lot.retirees), 2)
        lot2 = lire_fec(fec(*BASE))
        filtres.appliquer(lot2, [{"journaux": ["AN"], "au": "2024-12-31"}])
        self.assertEqual(lot2.totaux()["lignes"], 9)  # hors période : rien

    def test_comptes_640_ecritures_entieres(self):
        lot = lire_fec(fec(*BASE))
        filtres.appliquer(lot, [{"nom": "640", "comptes": ["640"]}])
        self.assertNotIn(
            "421000", {l["compte"] for l in lot.lignes}
        )  # contrepartie partie
        self.assertEqual(lot.totaux()["ecritures"], 3)

    def test_portee_lignes_refusee_si_desequilibre(self):
        lot = lire_fec(fec(*BASE))
        with self.assertRaises(filtres.ErreurFiltre):
            filtres.appliquer(lot, [{"comptes": ["640"], "portee": "lignes"}])
        lot = lire_fec(fec(*BASE))  # 640 + 421 : soldé
        filtres.appliquer(
            lot, [{"comptes": ["640", "421"], "portee": "lignes"}]
        )
        self.assertEqual(lot.totaux()["lignes"], 7)

    def test_criteres_divers(self):
        lot = lire_fec(
            fec(
                *(
                    BASE
                    + [
                        L(
                            "OD",
                            "9",
                            "20250131",
                            "601000",
                            "7,00",
                            lib="ESSAI x",
                        ),
                        L(
                            "OD",
                            "9",
                            "20250131",
                            "401000",
                            credit="7,00",
                            aux="F9",
                        ),
                    ]
                )
            )
        )
        filtres.appliquer(lot, [{"nom": "essais", "libelle": "essai"}])
        self.assertEqual(lot.totaux()["ecritures"], 4)
        lot = lire_fec(fec(*BASE))
        filtres.appliquer(
            lot,
            [{"tiers": ["C1"], "montant_min": "100", "montant_max": "150"}],
        )
        self.assertEqual({l["journal_code"] for l in lot.lignes}, {"AN", "OD"})
        lot = lire_fec(fec(*BASE))
        filtres.appliquer(
            lot,
            [
                {
                    "conditions": [
                        {"champ": "piece", "op": "egal", "valeur": "p4"}
                    ]
                }
            ],
        )
        self.assertEqual(lot.totaux()["ecritures"], 3)
        lot = lire_fec(fec(*BASE))
        for l in lot.lignes:
            l["analytique"] = "AXE1-LYON" if l["compte"] == "640000" else ""
        filtres.appliquer(lot, [{"analytique": ["AXE1"]}])
        self.assertEqual(lot.totaux()["ecritures"], 3)

    def test_filtres_invalides(self):
        for f in (
            {"portee": "tout"},
            {"nom": "vide"},
            {"du": "2025-02-01", "au": "2025-01-01"},
            {"inconnu": 1},
            {"conditions": [{"champ": "x", "op": "ressemble"}]},
            {"portee": "lignes", "journaux": ["AN"]},
        ):
            with self.assertRaises(filtres.ErreurFiltre, msg=f):
                filtres.normaliser(f)

    def test_lignes_nulles(self):
        lot = lire_fec(fec(*(BASE + [L("OD", "4", "20250131", "601000")])))
        r = filtres.appliquer(lot, [{"portee": "lignes_nulles"}])
        self.assertEqual(r["filtres"][0]["lignes"], 1)
        self.assertEqual(r["avant"]["debit"], r["apres"]["debit"])


class TestCorrespondance(unittest.TestCase):
    def test_table_et_a_arbitrer(self):
        lot = lire_fec(fec(*BASE))
        r = correspondance.appliquer(
            lot,
            {
                "512000": "512100",
                "101000": "101000",
                "411000": "411100",
                "706000": "706000",
                "445710": "445710",
                "640000": "641100",
                "999": "",
            },
        )
        c = {x["code"]: x for x in r.constats}
        self.assertEqual(
            c["MIG_COMPTE_A_ARBITRER"]["exemples"],
            ["421000 Compte 421000 — 1 ligne(s)"],
        )
        self.assertEqual(lot.lignes[0]["compte_cible"], "512100")
        self.assertIsNone(lot.lignes[-1]["compte_cible"])

    def test_identique_et_formats(self):
        lot = lire_fec(fec(*BASE))
        r = correspondance.appliquer(lot, identique=True)
        self.assertEqual(r.constats, [])
        self.assertTrue(
            all(l["compte_cible"] == l["compte"] for l in lot.lignes)
        )
        self.assertEqual(
            correspondance.charger_table(b'{"401": "401100"}', "t.json"),
            {"401": "401100"},
        )
        self.assertEqual(
            correspondance.charger_table(
                "Compte ERP;Compte Odoo\n401;401100\n411;411100\n".encode(),
                "t.csv",
            ),
            {"401": "401100", "411": "411100"},
        )


class TestCircuit(unittest.TestCase):
    def test_lot_pret_et_conforme(self):
        d = tempfile.mkdtemp()
        j = Journal()
        r = executer(
            fec(*BASE),
            "t.fec",
            d,
            [{"nom": "AN", "journaux": ["AN"]}],
            identique=True,
            aujourd_hui=AUJ,
            journal=j,
        )
        self.assertEqual(r["statut"], "pret", json.dumps(r, default=str)[:500])
        self.assertEqual(
            {p: v["statut"] for p, v in r["portes"].items()},
            dict({k: "verte" for k in r["portes"]}, test="non_jouee"),
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(d, "export", "controle_FEC_comptes_odoo.txt")
            )
        )
        self.assertTrue(
            os.path.isfile(os.path.join(d, "export", "lignes_retirees.xlsx"))
        )
        self.assertEqual(
            r["portes"]["export"]["infos"]["sortie"]["debit"], 74000
        )
        msgs = [e["message"] for e in j.tout()]
        self.assertTrue(any("Bilan du lot : PRÊT" in m for m in msgs))

    def test_lot_bloque(self):
        d = tempfile.mkdtemp()
        r = executer(
            fec(*(BASE + [L("OD", "5", "20250131", "601000", "10,00")])),
            "t.fec",
            d,
            table={"512000": "512000"},
            aujourd_hui=AUJ,
        )
        self.assertEqual(r["statut"], "bloque")
        self.assertEqual(r["portes"]["export"]["statut"], "non_jouee")
        self.assertTrue(os.path.isfile(os.path.join(d, "a_arbitrer.xlsx")))
        self.assertTrue(os.path.isfile(os.path.join(d, "problemes.xlsx")))
        for c in r["portes"]["controles"]["constats"]:
            self.assertTrue(c["explication"]["que_faire"])

    def test_fichier_illisible(self):
        r = executer(b"rien", "x.fec", tempfile.mkdtemp())
        self.assertEqual(r["portes"]["lecture"]["statut"], "bloquee")

    def test_filtre_refuse(self):
        r = executer(
            fec(*BASE),
            "t.fec",
            tempfile.mkdtemp(),
            [{"comptes": ["640"], "portee": "lignes"}],
            identique=True,
        )
        self.assertEqual(r["portes"]["filtres"]["statut"], "bloquee")


if __name__ == "__main__":
    unittest.main()
