# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests : vérifier, analyser et comparer deux bases (core/comparaison.py)."""

import copy
import os
import tempfile
import unittest
import zipfile
from datetime import date
from typing import Any

from core.comparaison import (
    comparer,
    ecrire_classeur,
    filtrer_lignes,
    rapprocher,
    verifier,
    _regrouper,
)
from core.odoo_source import analytique_comptes, analytique_texte
from tests.outils import Enregistrement


def ligne(
    eid: int,
    num: str,
    compte: str,
    debit: int = 0,
    credit: int = 0,
    **kw: Any,
) -> Enregistrement:
    """Construit une ligne d'écriture ; ``kw`` surcharge tout champ."""
    ligne_construite: Enregistrement = {
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
    ligne_construite.update(kw)
    return ligne_construite


def ecriture(
    eid: int, num: str, montant: int = 12000, **kw: Any
) -> list[Enregistrement]:
    """Construit une écriture équilibrée 411000 / 706000 de ``montant``."""
    return [
        ligne(
            eid,
            num,
            "411000",
            debit=montant,
            type="asset_receivable",
            tiers_ref="C1",
            **dict(kw),
        ),
        ligne(
            eid,
            num,
            "706000",
            credit=montant,
            analytique="AXE1 100 %",
            **dict(kw),
        ),
    ]


BASE = (
    ecriture(1, "VEN/1")
    + ecriture(2, "VEN/2")
    + ecriture(3, "VEN/3")
    + ecriture(4, "/", etat="draft", ref="BR4")
)


class TestAnalytique(unittest.TestCase):
    """Texte des répartitions analytiques."""

    def test_texte_stable(self) -> None:
        """Vérifie un texte analytique stable quel que soit l'ordre."""
        noms = {86: "Labo", 252: "PHARMA", 266: "Frais"}
        a = analytique_texte({"86,252": 98.76, "266": 1.24}, noms)
        b = analytique_texte({"266": 1.24, "252,86": 98.76}, noms)
        self.assertEqual(a, b)
        self.assertEqual(a, "Frais 1.24 % ; Labo+PHARMA 98.76 %")
        self.assertEqual(analytique_texte({"999": 100}, noms), "#999 100 %")
        self.assertEqual(analytique_texte(None, noms), "")


class TestComparer(unittest.TestCase):
    """Comparaison de deux bases écriture par écriture."""

    def codes(
        self, a: list[Enregistrement], b: list[Enregistrement], **kw: Any
    ) -> tuple[dict[str, Any], Any, Any]:
        """Compare deux bases : constats par code, détails, rapport."""
        r, det = comparer(a, b, **kw)
        return {c["code"]: c for c in r.constats}, det, r

    def test_identiques(self) -> None:
        """Vérifie que deux bases identiques ne donnent aucun constat."""
        c, det, r = self.codes(BASE, copy.deepcopy(BASE))
        self.assertEqual(c, {})
        self.assertEqual(r.infos["ecritures_identiques"], 4)

    def test_rapprochement_par_contenu_pour_les_brouillons(self) -> None:
        """Vérifie le rapprochement par contenu (identifiants différents)."""
        b = copy.deepcopy(BASE)
        for ligne_base in b:
            ligne_base[
                "ecriture_id"
            ] += 100  # identifiants différents (autre base)
        couples, sa, sb = rapprocher(_regrouper(BASE), _regrouper(b))
        self.assertEqual((len(couples), sa, sb), (4, [], []))

    def test_quatre_modifications(self) -> None:
        """Vérifie libellé, analytique, date, retrait et ajout détectés."""
        b = copy.deepcopy(BASE)
        b[0]["libelle"] = "lib (MODIFIÉ)"  # VEN/1 : libellé
        b[3]["analytique"] = "AXE2 100 %"  # VEN/2 : analytique seule
        for ligne_base in b[4:6]:
            ligne_base["date"] = date(2025, 11, 8)  # VEN/3 : date
        b = b[:6] + ecriture(5, "VEN/5")  # brouillon retiré, VEN/5 ajoutée
        c, det, _ = self.codes(BASE, b)
        self.assertEqual(c["CMP_ECRITURE_DIFFERENTE"]["nombre"], 2)
        self.assertEqual(c["CMP_ANALYTIQUE_SEULE"]["nombre"], 1)
        self.assertEqual(c["CMP_SEULEMENT_A"]["nombre"], 1)
        self.assertEqual(c["CMP_SEULEMENT_B"]["nombre"], 1)
        textes = " ".join(c["CMP_ECRITURE_DIFFERENTE"]["exemples"])
        self.assertIn("MODIFIÉ", textes)
        self.assertIn("date 2025-11-07 → 2025-11-08", textes)

    def test_soldes(self) -> None:
        """Vérifie les écarts de solde par compte et par tiers."""
        b = copy.deepcopy(BASE)
        b[0]["debit"] = b[1]["credit"] = 15000
        c, det, _ = self.codes(BASE, b)
        cles = {e["cle"] for e in det["comptes"]}
        self.assertEqual(cles, {"411000", "706000"})
        self.assertEqual(c["CMP_ECART_TIERS"]["nombre"], 1)

    def test_date_de_copie_et_conflits(self) -> None:
        """Vérifie le côté modifié après la copie et les conflits."""
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

    def test_verification_et_classeur(self) -> None:
        """Vérifie les contrôles d'une base et le classeur des écarts."""
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


class TestFiltres(unittest.TestCase):
    """Filtres par compte et par compte analytique."""

    def test_comptes_analytiques_d_une_repartition(self) -> None:
        """Vérifie la liste des comptes analytiques d'une répartition."""
        noms = {86: "Labo", 252: "PHARMA", 266: "Frais"}
        self.assertEqual(
            analytique_comptes({"86,252": 98.76, "266,86": 1.24}, noms),
            ["Frais", "Labo", "PHARMA"],
        )
        self.assertEqual(analytique_comptes({"999": 100}, noms), ["#999"])
        self.assertEqual(analytique_comptes(None, noms), [])

    def lignes(self) -> list[Enregistrement]:
        """Rend la base de test avec ses comptes analytiques détaillés."""
        res = []
        for ligne_base in copy.deepcopy(BASE):
            ligne_base["analytique_comptes"] = (
                ["AXE1"] if ligne_base["analytique"] else []
            )
            res.append(ligne_base)
        res[3]["analytique_comptes"] = ["AXE2", "PHARMA"]
        return res

    def test_filtre_comptes_analytique_et_cumul(self) -> None:
        """Vérifie les filtres compte, analytique et leur cumul."""
        lignes_filtrables = self.lignes()
        self.assertEqual(len(filtrer_lignes(lignes_filtrables)), 8)
        self.assertEqual(
            {
                ligne_base["compte"]
                for ligne_base in filtrer_lignes(lignes_filtrables, ["411000"])
            },
            {"411000"},
        )
        self.assertEqual(
            len(filtrer_lignes(lignes_filtrables, analytiques=["PHARMA"])), 1
        )
        self.assertEqual(
            len(
                filtrer_lignes(
                    lignes_filtrables, analytiques=["AXE1", "PHARMA"]
                )
            ),
            4,
        )
        self.assertEqual(
            filtrer_lignes(lignes_filtrables, ["411000"], ["PHARMA"]), []
        )  # cumul
        self.assertEqual(
            len(filtrer_lignes(lignes_filtrables, ["706000"], ["PHARMA"])), 1
        )

    def test_comparaison_filtree(self) -> None:
        """Vérifie qu'une comparaison filtrée ignore les écarts hors filtre."""
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


if __name__ == "__main__":
    unittest.main()
