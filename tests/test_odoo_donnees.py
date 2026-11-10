# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la passerelle Odoo 17 : XML-RPC simulé, FEC, xlsx, CSV, analyse."""

import csv
import io
import os
import re
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from typing import Any

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
from tests.outils import Enregistrement, FauxCommun, FauxObjet


def ligne(**kw: Any) -> Enregistrement:
    """Ligne d'écriture normalisée de test, surchargée par ``kw``."""
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
        "caba_rapprochement_id": None,
        "extourne_de_id": None,
    }
    base.update(kw)
    return base


def facture_equilibree(
    eid: int = 1, montant: int = 12000, **kw: Any
) -> list[Enregistrement]:
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
    """Conversion exacte des montants Odoo en centimes."""

    def test_decimal_et_float_exacts(self) -> None:
        """Vérifie la conversion exacte en centimes des Decimal et float."""
        self.assertEqual(centimes(Decimal("1234.56")), 123456)
        self.assertEqual(centimes(1234.56), 123456)
        self.assertEqual(centimes(0.1), 10)
        self.assertEqual(centimes(False), 0)
        self.assertEqual(centimes(-12.5), -1250)

    def test_refus_arrondi_silencieux(self) -> None:
        """Vérifie qu'un montant non représentable au centime est refusé."""
        with self.assertRaises(ErreurMontant):
            centimes(Decimal("1.234"))
        with self.assertRaises(ErreurMontant):
            centimes(0.1 + 0.2)  # 0.30000000000000004

    def test_euros_texte(self) -> None:
        """Vérifie l'écriture des centimes en euros avec séparateur choisi."""
        self.assertEqual(euros_texte(123456), "1234.56")
        self.assertEqual(euros_texte(-5, ","), "-0,05")
        self.assertEqual(euros_texte(0, ","), "0,00")


class TestFec(unittest.TestCase):
    """Production du FEC réglementaire."""

    def setUp(self) -> None:
        """Prépare un dossier temporaire et le chemin du FEC."""
        self.dossier = tempfile.mkdtemp()
        self.chemin = os.path.join(self.dossier, "FEC.txt")

    def lire(self, encodage: str = "iso-8859-15") -> list[list[str]]:
        """Relit le FEC produit, découpé en champs par ligne."""
        with open(self.chemin, encoding=encodage) as f:
            return [ligne_lue.rstrip("\r\n").split("|") for ligne_lue in f]

    def test_fec_conforme(self) -> None:
        """Vérifie un FEC conforme : colonnes, auxiliaire, lettrage."""
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

    def test_desequilibre_refuse_sans_fichier(self) -> None:
        """Vérifie qu'un FEC déséquilibré est refusé sans aucun fichier."""
        lignes = facture_equilibree()
        lignes[0]["credit"] -= 1  # 1 centime d'écart
        with self.assertRaises(ErreurFec):
            generer_fec(lignes, self.chemin)
        self.assertFalse(os.path.exists(self.chemin))
        self.assertFalse(os.path.exists(self.chemin + ".partiel"))

    def test_brouillon_refuse(self) -> None:
        """Vérifie qu'une écriture brouillon est refusée dans le FEC."""
        with self.assertRaises(ErreurFec):
            generer_fec(facture_equilibree(etat="draft"), self.chemin)

    def test_devise_hors_euro_refusee(self) -> None:
        """Vérifie qu'une devise de tenue autre que l'euro est refusée."""
        with self.assertRaises(ErreurFec):
            generer_fec(facture_equilibree(), self.chemin, devise="USD")

    def test_typographie_et_separateur(self) -> None:
        """Vérifie la translittération et le comptage des caractères perdus."""
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

    def test_nom_reglementaire(self) -> None:
        """Vérifie le nom réglementaire du fichier FEC."""
        self.assertEqual(
            nom_fichier_fec("666666664", date(2025, 12, 31)),
            "666666664FEC20251231.txt",
        )


class TestXlsx(unittest.TestCase):
    """Production du classeur Excel."""

    def test_classeur_valide_et_montants_exacts(self) -> None:
        """Vérifie un classeur valide, échappé, montants et dates exacts."""
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

    def test_caracteres_de_controle_retires(self) -> None:
        """Vérifie le retrait des caractères de contrôle et les négatifs."""
        chemin = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        ecrire_xlsx(chemin, [("F", ["a"], [["x\x01y"], [Centimes(-5)]])])
        with zipfile.ZipFile(chemin) as z:
            f = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn(">xy<", f)
        self.assertIn("<v>-0.05</v>", f)


class TestCsv(unittest.TestCase):
    """Export CSV des écritures pour l'import Odoo."""

    def test_entete_sur_premiere_ligne_seulement(self) -> None:
        """Vérifie que l'en-tête n'est porté que par la 1re ligne."""
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
    """Analyse de conformité des écritures."""

    def analyse(
        self, lignes: list[Enregistrement], **kw: Any
    ) -> dict[str, Any]:
        """Analyse ``lignes`` au 06/11/2026 et rend le rapport en dict."""
        rapport: dict[str, Any] = analyser(
            lignes, aujourd_hui=date(2026, 11, 6), **kw
        ).en_dict()
        return rapport

    def codes(self, d: dict[str, Any]) -> dict[str, int]:
        """Rend le nombre d'occurrences par code de constat."""
        return {c["code"]: c["nombre"] for c in d["constats"]}

    def test_conforme(self) -> None:
        """Vérifie qu'une facture équilibrée est déclarée conforme."""
        d = self.analyse(facture_equilibree())
        self.assertEqual(d["statut"], "conforme")
        self.assertEqual(d["infos"]["total_debit"], "120,00")

    def test_desequilibre_bloquant(self) -> None:
        """Vérifie qu'un déséquilibre d'un centime est bloquant."""
        lignes = facture_equilibree()
        lignes[0]["credit"] += 1
        d = self.analyse(lignes)
        self.assertEqual(d["statut"], "bloquant")
        self.assertIn("ECRITURE_DESEQUILIBREE", self.codes(d))
        self.assertIn("TOTAL_DESEQUILIBRE", self.codes(d))

    def test_alertes(self) -> None:
        """Vérifie tiers, ligne seule, montant nul, date future, doublon."""
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

    def test_amortissement_planifie_en_info(self) -> None:
        """Vérifie qu'une écriture planifiée future reste une information."""
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

    def test_tiers(self) -> None:
        """Vérifie les contrôles SIREN/TVA et doublons de tiers."""
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
            dict(t, id=8, nom="Acme", tva="FR72666666664"),
            dict(t, id=9, nom="Ltd", pays="GB", siren="HRB 123"),
            dict(t, id=10, nom="Bad", siren="123456789"),
        ]
        lignes: list[Enregistrement] = []
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


class TestSourceXmlRpc(unittest.TestCase):
    """Lecture d'un Odoo 17 par XML-RPC (simulé)."""

    def source(self) -> SourceXmlRpcOdoo17:
        """Ouvre une source XML-RPC sur l'Odoo simulé (gardé dans objet)."""
        self.objet = FauxObjet()
        return SourceXmlRpcOdoo17(
            "http://x",
            "b",
            "u",
            "cle",
            proxy_commun=FauxCommun(),
            proxy_objet=self.objet,
        )

    def test_lignes_normalisees(self) -> None:
        """Vérifie la normalisation des lignes lues par XML-RPC."""
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

    def test_lecture_seule(self) -> None:
        """Vérifie que toute écriture vers Odoo est refusée."""
        s = self.source()
        with self.assertRaises(PermissionError):
            s._appel("account.move", "write", [[5], {"ref": "x"}])
        with self.assertRaises(PermissionError):
            s._appel("account.move", "unlink", [[5]])

    def test_pagination(self) -> None:
        """Vérifie la lecture paginée par lots d'identifiants."""
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

    def test_version_autre_que_17_refusee(self) -> None:
        """Vérifie qu'un serveur Odoo autre que 17 est refusé."""

        class Commun18(FauxCommun):
            """Serveur Odoo simulé en version 18."""

            def version(self) -> dict[str, str]:
                """Rend la version 18.0."""
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

    def test_fec_depuis_xmlrpc(self) -> None:
        """Vérifie un FEC équilibré produit depuis la source XML-RPC."""
        chemin = os.path.join(tempfile.mkdtemp(), "f.txt")
        r = generer_fec(self.source().lignes(), chemin)
        self.assertEqual((r["total_debit"], r["total_credit"]), (10010, 10010))
        with open(chemin, encoding="iso-8859-15") as f:
            self.assertTrue(
                re.search(r"\|411000\|Clients\|C7\|ACME\|", f.read())
            )


if __name__ == "__main__":
    unittest.main()
