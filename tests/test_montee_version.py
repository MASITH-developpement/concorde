# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests de la photo comptable multi-version (ADR-0010).

Base simulée : réponses SQL d'un Odoo 17 (code de compte en colonne) et
d'un Odoo 18 (code par société dans code_store). La vérification sur de
vrais Odoo 14 à 18 est faite par la CI (tests/integration/verifier_photo).
"""

import sys
import unittest
from decimal import Decimal
from typing import Any
from unittest import mock

from core.canonical import ErreurMontant
from core.montee_version import photo
from core.odoo_source import (
    ErreurSource,
    connexion_lecture_seule,
    proxys_xmlrpc,
)


class CurseurPhoto:
    """Curseur simulé : rend les lignes prévues pour chaque requête."""

    def __init__(self, reponses: dict[str, list[tuple[Any, ...]]]) -> None:
        """reponses : {requête SQL exacte: lignes}."""
        self.reponses = reponses
        self.lignes: list[tuple[Any, ...]] = []

    def __enter__(self) -> "CurseurPhoto":
        """Ouverture du bloc with."""
        return self

    def __exit__(self, *details: object) -> None:
        """Fermeture du bloc with."""

    def execute(self, sql: str) -> None:
        """Choisit les lignes de la requête (KeyError si imprévue)."""
        self.lignes = self.reponses[sql]

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Lignes de la dernière requête."""
        return self.lignes


class BasePhoto:
    """Connexion simulée (même interface que psycopg2)."""

    def __init__(self, reponses: dict[str, list[tuple[Any, ...]]]) -> None:
        """reponses : {requête SQL exacte: lignes}."""
        self.reponses = reponses
        self.annulations = 0

    def cursor(self, name: str | None = None) -> CurseurPhoto:
        """Nouveau curseur."""
        return CurseurPhoto(self.reponses)

    def set_session(self, *, readonly: bool, autocommit: bool) -> None:
        """Mode de session (sans effet ici)."""

    def rollback(self) -> None:
        """Compte les fins de transaction."""
        self.annulations += 1

    def close(self) -> None:
        """Fermeture (sans effet ici)."""


def reponses_odoo(comptes: list[tuple[Any, ...]]) -> dict[str, Any]:
    """Réponses d'une petite base : vente 2023, encaissement 2024."""
    return {
        photo._SQL_VERSION_PHOTO: [("17.0.1.3",)],
        photo._SQL_COMPTES_PHOTO: comptes,
        photo._SQL_JOURNAUX_PHOTO: [(1, "OD")],
        photo._SQL_LIGNES_PHOTO: [
            (1, 2023, 10, 7, Decimal("120.00"), Decimal("0"), 1, Decimal(0)),
            (1, 2023, 20, None, Decimal("0"), Decimal("120.00"), 0, None),
            (1, 2024, 10, 7, Decimal("0"), Decimal("120.00"), 1, Decimal(0)),
            (1, 2024, 30, None, Decimal("120.00"), Decimal("0"), 0, None),
        ],
        photo._SQL_PIECES_PHOTO: [
            (1, 2023, 1, 1, 2, Decimal("120.00"), Decimal("120.00")),
            (1, 2024, 1, 1, 2, Decimal("120.00"), Decimal("120.00")),
            (1, 2024, 99, 1, 2, Decimal("5.00"), Decimal("5.00")),
        ],
        photo._SQL_ANALYTIQUE_PHOTO: [(4, 1, Decimal("120.00"))],
        photo._SQL_SOCIETES_PHOTO: [
            (
                1,
                {
                    "name": "Société",
                    "fiscalyear_lock_date": "2023-12-31",
                    "tax_lock_date": None,
                },
            )
        ],
    }


COMPTES_CODE_COMMUN = [
    (10, "411000", None),
    (20, "706000", None),
    (30, "512000", None),
]
COMPTES_CODE_PAR_SOCIETE = [
    (10, None, {"1": "411000"}),
    (20, None, {"1": "706000"}),
    (30, None, {"1": "512000", "2": "512100"}),
]


class TestPhoto(unittest.TestCase):
    """prendre_photo : sections, clés, montants en centimes, empreinte."""

    def test_photo_odoo_17(self) -> None:
        """Chaque section porte les montants attendus, en centimes."""
        base = BasePhoto(reponses_odoo(COMPTES_CODE_COMMUN))
        resultat = photo.prendre_photo(base, "demo")
        sections = resultat["sections"]
        self.assertEqual(resultat["version"], "17.0.1.3")
        self.assertEqual(sections["balance"]["s1|2023|411000"], "12000 0")
        self.assertEqual(sections["balance"]["s1|2024|512000"], "12000 0")
        self.assertEqual(
            sections["balance_tiers"],
            {"s1|2023|411000|p7": "12000 0", "s1|2024|411000|p7": "0 12000"},
        )
        self.assertEqual(sections["lettrage"]["s1|411000"], "2 0")
        self.assertEqual(sections["lettrage"]["s1|706000"], "0 0")
        self.assertEqual(sections["journaux"]["s1|2023|OD"], "1 2 12000 12000")
        self.assertEqual(sections["journaux"]["s1|2024|99"], "1 2 500 500")
        self.assertEqual(sections["analytique"], {"a4": "1 12000"})
        self.assertEqual(
            sections["verrous"],
            {
                "s1|fiscalyear_lock_date": "2023-12-31",
                "s1|tax_lock_date": "",
            },
        )
        self.assertEqual(base.annulations, 1)
        self.assertEqual(
            resultat["empreinte"], photo.empreinte_sections(sections)
        )

    def test_photo_odoo_18_code_par_societe(self) -> None:
        """Code dans code_store (Odoo 18) : mêmes sections qu'en 17."""
        photo_code_commun = photo.prendre_photo(
            BasePhoto(reponses_odoo(COMPTES_CODE_COMMUN)), "a"
        )
        photo_code_societe = photo.prendre_photo(
            BasePhoto(reponses_odoo(COMPTES_CODE_PAR_SOCIETE)), "b"
        )
        self.assertEqual(
            photo_code_commun["sections"], photo_code_societe["sections"]
        )
        self.assertEqual(
            photo_code_commun["empreinte"], photo_code_societe["empreinte"]
        )

    def test_compte_sans_code(self) -> None:
        """Un compte sans code ni code_store : erreur nommée."""
        base = BasePhoto(reponses_odoo([(10, None, None)]))
        with self.assertRaisesRegex(photo.ErreurPhoto, "n° 10 sans code"):
            photo.prendre_photo(base, "demo")

    def test_code_absent_pour_la_societe(self) -> None:
        """Code connu pour une autre société seulement : erreur nommée."""
        comptes = [(10, None, {"2": "411000"})] + COMPTES_CODE_COMMUN[1:]
        with self.assertRaisesRegex(photo.ErreurPhoto, "société 1"):
            photo.prendre_photo(BasePhoto(reponses_odoo(comptes)), "demo")

    def test_base_non_odoo(self) -> None:
        """Pas de module base : ce n'est pas une base Odoo."""
        reponses = reponses_odoo(COMPTES_CODE_COMMUN)
        reponses[photo._SQL_VERSION_PHOTO] = []
        with self.assertRaisesRegex(photo.ErreurPhoto, "pas Odoo"):
            photo.prendre_photo(BasePhoto(reponses), "demo")

    def test_montant_non_exact(self) -> None:
        """Un montant au millième est refusé, jamais arrondi."""
        reponses = reponses_odoo(COMPTES_CODE_COMMUN)
        reponses[photo._SQL_ANALYTIQUE_PHOTO] = [(4, 1, Decimal("1.005"))]
        with self.assertRaises(ErreurMontant):
            photo.prendre_photo(BasePhoto(reponses), "demo")


class TestComparer(unittest.TestCase):
    """comparer_photos : zéro écart, valeur changée, clé absente."""

    def setUp(self) -> None:
        """Photo de référence."""
        self.avant = photo.prendre_photo(
            BasePhoto(reponses_odoo(COMPTES_CODE_COMMUN)), "demo"
        )

    def test_identiques(self) -> None:
        """Deux photos identiques : aucun écart."""
        apres = photo.prendre_photo(
            BasePhoto(reponses_odoo(COMPTES_CODE_COMMUN)), "x"
        )
        self.assertEqual(photo.comparer_photos(self.avant, apres), [])

    def test_ecarts(self) -> None:
        """Montant changé, clé disparue, section absente : tout est listé."""
        reponses = reponses_odoo(COMPTES_CODE_COMMUN)
        reponses[photo._SQL_ANALYTIQUE_PHOTO] = []
        reponses[photo._SQL_LIGNES_PHOTO] = reponses[photo._SQL_LIGNES_PHOTO][
            :3
        ] + [(1, 2024, 30, None, Decimal("120.01"), Decimal(0), 0, None)]
        apres = photo.prendre_photo(BasePhoto(reponses), "demo")
        del apres["sections"]["verrous"]
        ecarts = photo.comparer_photos(self.avant, apres)
        self.assertEqual(
            [(ecart["section"], ecart["cle"]) for ecart in ecarts],
            [
                ("balance", "s1|2024|512000"),
                ("analytique", "a4"),
                ("verrous", "s1|fiscalyear_lock_date"),
                ("verrous", "s1|tax_lock_date"),
            ],
        )
        self.assertEqual(ecarts[0]["avant"], "12000 0")
        self.assertEqual(ecarts[0]["apres"], "12001 0")
        self.assertEqual(ecarts[1]["apres"], "")


class TestOuvertures(unittest.TestCase):
    """Routines partagées : connexion SQL en lecture seule, proxys XML-RPC."""

    def test_sans_psycopg2(self) -> None:
        """psycopg2 absent : erreur nommée."""
        with mock.patch.dict(sys.modules, {"psycopg2": None}):
            with self.assertRaisesRegex(ErreurSource, "psycopg2"):
                connexion_lecture_seule("demo")

    def test_session_lecture_seule(self) -> None:
        """La connexion ouverte est mise en lecture seule."""
        faux = mock.Mock()
        with mock.patch.dict(sys.modules, {"psycopg2": faux}):
            connexion = connexion_lecture_seule("demo")
        faux.connect.assert_called_once_with(dbname="demo")
        self.assertIs(connexion, faux.connect.return_value)
        faux.connect.return_value.set_session.assert_called_once_with(
            readonly=True, autocommit=False
        )

    def test_proxys(self) -> None:
        """Deux accès : common et object, sur la même adresse."""
        commun, objet = proxys_xmlrpc("https://odoo.exemple", 5)
        self.assertIn("odoo.exemple/xmlrpc/2/common", repr(commun))
        self.assertIn("odoo.exemple/xmlrpc/2/object", repr(objet))


if __name__ == "__main__":
    unittest.main()
