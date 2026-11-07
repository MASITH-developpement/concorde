# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du rapport du jour (core/rapport_jour.py)."""

import unittest
from datetime import datetime

from core.rapport_jour import (
    construire,
    fusionner,
    nettoyer_saisie,
    rendu_html,
)

JOUR = "2026-11-07"
MAINTENANT = datetime(2026, 11, 7, 18, 0)


def alerte(
    ident,
    niveau,
    message,
    base="alb",
    statut="active",
    premiere=JOUR + "T08:00:00",
    resolue=None,
    code="X",
    nombre=3,
):
    return {
        "id": ident,
        "niveau": niveau,
        "message": message,
        "base": base,
        "statut": statut,
        "premiere_fois": premiere,
        "resolue_le": resolue,
        "code": code,
        "nombre": nombre,
        "exemples": [],
    }


ALERTES = [
    alerte("a1", "BLOQUANT", "Caisses créditrices"),
    alerte(
        "a2", "ALERTE", "Clients créditeurs", premiere="2026-11-01T08:00:00"
    ),
    alerte(
        "a3",
        "ALERTE",
        "Comptes d'attente",
        statut="resolue",
        resolue=JOUR + "T10:00:00",
    ),
    alerte(
        "a4",
        "ALERTE",
        "Fournisseurs débiteurs",
        base="vieille",
        statut="resolue",
        resolue=JOUR + "T11:00:00",
    ),
    alerte(
        "e1",
        "INFO",
        "Base supprimée",
        base="vieille",
        statut="evenement",
        code="BASE_SUPPRIMEE",
    ),
    alerte(
        "e2", "ALERTE", "Écritures supprimées", statut="evenement", nombre=2
    ),
]
TACHES = [
    {
        "id": "t1",
        "action": "analyser",
        "base": "alb",
        "statut": "terminee",
        "cree_le": JOUR + "T09:00:00",
        "resultat": {
            "statut": "alertes",
            "synthese": {"BLOQUANT": 0, "ALERTE": 4},
        },
    },
    {
        "id": "t2",
        "action": "comparer",
        "base": "alb",
        "base_b": "prod",
        "statut": "terminee",
        "cree_le": JOUR + "T10:00:00",
        "resultat": {"comparaison": {"statut": "conforme", "constats": []}},
    },
    {
        "id": "t3",
        "action": "comparer",
        "base": "alb",
        "base_b": "prod",
        "statut": "terminee",
        "cree_le": JOUR + "T10:30:00",
        "resultat": {"comparaison": {"statut": "conforme", "constats": []}},
    },
    {
        "id": "t4",
        "action": "telecharger",
        "base": "alb",
        "statut": "echec",
        "cree_le": JOUR + "T12:00:00",
        "erreur": "FEC refusé",
    },
    {
        "id": "t5",
        "action": "analyser",
        "base": "alb",
        "statut": "terminee",
        "cree_le": "2026-11-06T09:00:00",
        "resultat": {},
    },
]
SECURITE = {
    "controle": {
        "date": JOUR + "T17:45:00",
        "statut": "conforme",
        "constats": [],
    },
    "antivirus": {
        "date": JOUR + "T03:45:00",
        "statut": "conforme",
        "infos": {"fichiers_analyses": 37887},
        "constats": [],
    },
}


def rapport():
    return construire(JOUR, ALERTES, TACHES, SECURITE, maintenant=MAINTENANT)


class TestConstruire(unittest.TestCase):
    def test_conclusions(self):
        r = rapport()
        textes = [c["texte_auto"] for c in r["conclusions"]]
        ids = [c["id"] for c in r["conclusions"]]
        quands = [c["quand"] for c in r["conclusions"]]
        self.assertTrue(all(quands))  # chaque ligne datée
        self.assertEqual(quands, sorted(quands))  # ordre chronologique
        for items in r["sections"].values():
            self.assertEqual(
                [x["quand"] for x in items], sorted(x["quand"] for x in items)
            )
        self.assertIn("alerte|a1", ids)
        self.assertTrue(
            any("apparue aujourd'hui" in t for t in textes if "Caisses" in t)
        )
        self.assertTrue(
            any(
                "active depuis" in t
                for t in textes
                if "Clients créditeurs" in t
            )
        )
        a2 = next(c for c in r["conclusions"] if c["id"] == "alerte|a2")
        self.assertEqual(
            a2["quand"], "2026-11-01T08:00:00"
        )  # date d'apparition
        self.assertIn("resolue|a3", ids)
        self.assertNotIn("resolue|a4", ids)  # base supprimée ≠ résolu
        self.assertTrue(
            any(
                "Base vieille supprimée : 1 alerte(s) close(s)" in t
                for t in textes
            )
        )
        self.assertIn("changements|alb", ids)
        self.assertNotIn("changements|vieille", ids)  # déjà dans les travaux
        self.assertTrue(
            any("(2 fois : 10:00, 10:30)" in t for t in textes)
        )  # regroupées
        self.assertTrue(
            any(t.startswith("Échec — téléchargement de alb") for t in textes)
        )
        self.assertTrue(any("37887 fichiers" in t for t in textes))
        self.assertIn(
            "Travaux de la journée : 1 analyse, 2 comparaisons, 1 téléchargement.",
            textes,
        )
        self.assertEqual(
            len(r["sections"]["taches"]), 4
        )  # sans la tâche de la veille

    def test_jour_passe_sans_alertes_actives(self):
        r = construire(
            "2026-11-06", ALERTES, TACHES, {}, maintenant=MAINTENANT
        )
        ids = [c["id"] for c in r["conclusions"]]
        self.assertFalse(any(i.startswith("alerte|") for i in ids))
        self.assertIn("securite|controle", ids)  # aucun résultat


class TestFusionner(unittest.TestCase):
    def test_choix_conserves_apres_regeneration(self):
        auto = rapport()
        saisie = nettoyer_saisie(
            {
                "conclusions": [
                    {"id": "alerte|a1", "visible": False},
                    {
                        "id": "alerte|a2",
                        "texte": "Clients créditeurs : vu avec la compta",
                        "commentaire": "à relancer lundi",
                    },
                    {
                        "id": "ancienne|x",
                        "texte": "Point gardé",
                        "visible": True,
                    },
                ],
                "ajouts": [
                    {
                        "id": "ajout-3",
                        "texte": "Écrit après",
                        "quand": "2026-11-07T16:00:00",
                    },
                    {
                        "id": "ajout-1",
                        "texte": "Migration prévue le 15/11",
                        "quand": "2026-11-07T09:30:00",
                    },
                    {"id": "ajout-2", "texte": "   "},
                ],
                "commentaire": "Journée calme.",
                "sections_masquees": ["taches", "pirate"],
            }
        )
        r = fusionner(auto, saisie)
        par_id = {c["id"]: c for c in r["conclusions"]}
        self.assertFalse(par_id["alerte|a1"]["visible"])
        self.assertEqual(
            par_id["alerte|a2"]["texte"],
            "Clients créditeurs : vu avec la compta",
        )
        self.assertTrue(par_id["alerte|a2"]["modifie"])
        self.assertEqual(
            par_id["alerte|a2"]["commentaire"], "à relancer lundi"
        )
        self.assertTrue(
            par_id["ancienne|x"]["perimee"]
        )  # plus produite, gardée
        self.assertTrue(par_id["resolue|a3"]["nouvelle"])  # apparue depuis
        self.assertEqual(
            [a["texte"] for a in r["ajouts"]],
            ["Migration prévue le 15/11", "Écrit après"],
        )  # triés par heure
        self.assertEqual(r["sections_masquees"], ["taches"])

    def test_export_seulement_le_visible_et_echappe(self):
        auto = rapport()
        saisie = nettoyer_saisie(
            {
                "conclusions": [
                    {"id": "alerte|a1", "visible": False},
                    {
                        "id": "alerte|a2",
                        "texte": "<script>alert(1)</script> créditeurs",
                    },
                ],
                "ajouts": [{"id": "x", "texte": "Mon ajout <b>"}],
                "commentaire": "Ligne 1\nLigne 2",
                "sections_masquees": ["securite"],
            }
        )
        page = rendu_html(fusionner(auto, saisie))
        self.assertNotIn("Caisses créditrices", page)  # masquée
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Mon ajout &lt;b&gt;", page)
        self.assertIn("Ligne 1<br>Ligne 2", page)
        self.assertNotIn("Sécurité du serveur</h2>", page)  # section masquée
        self.assertIn("Travaux de la journée</h2>", page)
        self.assertIn("SIRET 928 983 055 00015", page)
        self.assertIn(
            '<span class="q">07/11/2026 10:00</span>', page
        )  # date et heure

    def test_saisie_bornee(self):
        s = nettoyer_saisie(
            {
                "conclusions": [{"id": "a", "texte": "x" * 5000}] * 600,
                "ajouts": [{"texte": "y"}] * 200,
            }
        )
        self.assertEqual(len(s["conclusions"]), 500)
        self.assertEqual(len(s["conclusions"][0]["texte"]), 2000)
        self.assertEqual(len(s["ajouts"]), 100)


if __name__ == "__main__":
    unittest.main()
