# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests : vérifier, analyser et comparer deux bases (core/comparaison.py)."""

import copy
import os
import tempfile
import unittest
import zipfile
from datetime import date

from core.comparaison import (
    comparer,
    ecrire_classeur,
    rapprocher,
    verifier,
    _regrouper,
)
from core.odoo_source import analytique_texte


def ligne(eid, num, compte, debit=0, credit=0, **kw):
    l = {
        "ligne_id": eid * 10 + len(compte),
        "ecriture_id": eid,
        "ecriture": num,
        "journal_code": kw.pop("journal", "VEN"),
        "date": kw.pop("d", date(2025, 11, 7)),
        "reference": kw.pop("ref", "F%d" % eid),
        "etat": kw.pop("etat", "posted"),
        "compte": compte,
        "compte_type": kw.pop("type", "income"),
        "tiers_ref": "",
        "tiers_nom": "",
        "libelle": "lib",
        "debit": debit,
        "credit": credit,
        "lettrage": "",
        "analytique": "",
        "modifie_le": "2026-10-01 10:00:00",
    }
    l.update(kw)
    return l


def ecriture(eid, num, montant=12000, **kw):
    return [
        ligne(
            eid,
            num,
            "411000",
            debit=montant,
            type="asset_receivable",
            tiers_ref="C1",
            **dict(kw)
        ),
        ligne(
            eid,
            num,
            "706000",
            credit=montant,
            analytique="AXE1 100 %",
            **dict(kw)
        ),
    ]


BASE = (
    ecriture(1, "VEN/1")
    + ecriture(2, "VEN/2")
    + ecriture(3, "VEN/3")
    + ecriture(4, "/", etat="draft", ref="BR4")
)


class TestAnalytique(unittest.TestCase):
    def test_texte_stable(self):
        noms = {86: "Labo", 252: "PHARMA", 266: "Frais"}
        a = analytique_texte({"86,252": 98.76, "266": 1.24}, noms)
        b = analytique_texte({"266": 1.24, "252,86": 98.76}, noms)
        self.assertEqual(a, b)
        self.assertEqual(a, "Frais 1.24 % ; Labo+PHARMA 98.76 %")
        self.assertEqual(analytique_texte({"999": 100}, noms), "#999 100 %")
        self.assertEqual(analytique_texte(None, noms), "")


class TestComparer(unittest.TestCase):
    def codes(self, a, b, **kw):
        r, det = comparer(a, b, **kw)
        return {c["code"]: c for c in r.constats}, det, r

    def test_identiques(self):
        c, det, r = self.codes(BASE, copy.deepcopy(BASE))
        self.assertEqual(c, {})
        self.assertEqual(r.infos["ecritures_identiques"], 4)

    def test_rapprochement_par_contenu_pour_les_brouillons(self):
        b = copy.deepcopy(BASE)
        for l in b:
            l["ecriture_id"] += 100  # identifiants différents (autre base)
        couples, sa, sb = rapprocher(_regrouper(BASE), _regrouper(b))
        self.assertEqual((len(couples), sa, sb), (4, [], []))

    def test_quatre_modifications(self):
        b = copy.deepcopy(BASE)
        b[0]["libelle"] = "lib (MODIFIÉ)"  # VEN/1 : libellé
        b[3]["analytique"] = "AXE2 100 %"  # VEN/2 : analytique seule
        for l in b[4:6]:
            l["date"] = date(2025, 11, 8)  # VEN/3 : date
        b = b[:6] + ecriture(5, "VEN/5")  # brouillon retiré, VEN/5 ajoutée
        c, det, _ = self.codes(BASE, b)
        self.assertEqual(c["CMP_ECRITURE_DIFFERENTE"]["nombre"], 2)
        self.assertEqual(c["CMP_ANALYTIQUE_SEULE"]["nombre"], 1)
        self.assertEqual(c["CMP_SEULEMENT_A"]["nombre"], 1)
        self.assertEqual(c["CMP_SEULEMENT_B"]["nombre"], 1)
        textes = " ".join(c["CMP_ECRITURE_DIFFERENTE"]["exemples"])
        self.assertIn("MODIFIÉ", textes)
        self.assertIn("date 2025-11-07 → 2025-11-08", textes)

    def test_soldes(self):
        b = copy.deepcopy(BASE)
        b[0]["debit"] = b[1]["credit"] = 15000
        c, det, _ = self.codes(BASE, b)
        cles = {e["cle"] for e in det["comptes"]}
        self.assertEqual(cles, {"411000", "706000"})
        self.assertEqual(c["CMP_ECART_TIERS"]["nombre"], 1)

    def test_date_de_copie_et_conflits(self):
        a, b = copy.deepcopy(BASE), copy.deepcopy(BASE)
        a[0]["libelle"] = "corrigé en A"
        a[0]["modifie_le"] = "2026-11-01 09:00:00"
        b[0][
            "modifie_le"
        ] = "2026-11-02 09:00:00"  # VEN/1 : modifiée des deux côtés
        b[2]["libelle"] = "corrigé en B"
        b[2]["modifie_le"] = "2026-11-03 09:00:00"  # VEN/2 : seulement en B
        c, det, _ = self.codes(a, b, date_copie="2026-10-14T18:01:57")
        self.assertEqual(c["CMP_CONFLIT"]["nombre"], 1)
        cotes = sorted(x["cote"] for x in det["differentes"])
        self.assertEqual(
            cotes,
            [
                "CONFLIT : modifiée des deux côtés après la copie",
                "modifiée dans B après la copie",
            ],
        )

    def test_verification_et_classeur(self):
        b = copy.deepcopy(BASE)
        b[1]["analytique"] = "#266 100 %"
        b[0]["debit"] += 1
        v = {x["code"] for x in verifier(b, "B").constats}
        self.assertEqual(
            v, {"CMP_BASE_DESEQUILIBREE", "CMP_ANALYTIQUE_ORPHELINE"}
        )
        r, det = comparer(BASE, b)
        chemin = os.path.join(tempfile.mkdtemp(), "c.xlsx")
        ecrire_classeur(chemin, "A", "B", r, det)
        with zipfile.ZipFile(chemin) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("Ecarts comptes", z.read("xl/workbook.xml").decode())


if __name__ == "__main__":
    unittest.main()


class TestFiltres(unittest.TestCase):
    def test_comptes_analytiques_d_une_repartition(self):
        from core.odoo_source import analytique_comptes

        noms = {86: "Labo", 252: "PHARMA", 266: "Frais"}
        self.assertEqual(
            analytique_comptes({"86,252": 98.76, "266,86": 1.24}, noms),
            ["Frais", "Labo", "PHARMA"],
        )
        self.assertEqual(analytique_comptes({"999": 100}, noms), ["#999"])
        self.assertEqual(analytique_comptes(None, noms), [])

    def lignes(self):
        res = []
        for l in copy.deepcopy(BASE):
            l["analytique_comptes"] = ["AXE1"] if l["analytique"] else []
            res.append(l)
        res[3]["analytique_comptes"] = ["AXE2", "PHARMA"]
        return res

    def test_filtre_comptes_analytique_et_cumul(self):
        from core.comparaison import filtrer_lignes

        L = self.lignes()
        self.assertEqual(len(filtrer_lignes(L)), 8)
        self.assertEqual(
            {l["compte"] for l in filtrer_lignes(L, ["411000"])}, {"411000"}
        )
        self.assertEqual(len(filtrer_lignes(L, analytiques=["PHARMA"])), 1)
        self.assertEqual(
            len(filtrer_lignes(L, analytiques=["AXE1", "PHARMA"])), 4
        )
        self.assertEqual(
            filtrer_lignes(L, ["411000"], ["PHARMA"]), []
        )  # cumul
        self.assertEqual(len(filtrer_lignes(L, ["706000"], ["PHARMA"])), 1)

    def test_comparaison_filtree(self):
        from core.comparaison import filtrer_lignes

        a, b = self.lignes(), self.lignes()
        b[0]["debit"] = b[1]["credit"] = 15000  # VEN/1 change sur 411 et 706
        r, _ = comparer(
            filtrer_lignes(a, analytiques=["PHARMA"]),
            filtrer_lignes(b, analytiques=["PHARMA"]),
        )
        self.assertEqual(r.constats, [])  # VEN/1 hors du filtre PHARMA
        r, _ = comparer(
            filtrer_lignes(a, ["411000"]), filtrer_lignes(b, ["411000"])
        )
        self.assertIn(
            "CMP_ECRITURE_DIFFERENTE", {c["code"] for c in r.constats}
        )
