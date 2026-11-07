# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests unitaires du moteur — tolérance Concordance 0,00 EUR."""

import json
import os
import tempfile
import unittest
from datetime import date
from typing import TypeVar

from core.canonical import (
    Canonique,
    LigneEcriture,
    vers_centimes,
    ErreurMontant,
)
from core.fec_parser import parse_fec, ErreurFEC
from core.lettrage import lettrer
from core.guardian import Guardian, ErreurGuardian
from core.marceau import Marceau
from core.moteur import ContexteExecution, MoteurConcorde
from core.mapping import charger_mapping, mapper_comptes, ErreurMapping
from samples.generateur_fec_test import generer_fec
from injectors.odoo17 import (
    InjecteurOdoo17,
    ErreurInjecteur as ErreurInjecteur17,
)
from injectors.odoo18 import InjecteurOdoo18, ErreurInjecteur
from injectors.odoo_conversion import ConvertisseurOdoo, ErreurConversion

FEC_MINIMAL = (
    "JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;EcritureLib;"
    "Debit;Credit\r\n"
    "AC;1;20260201;41100000;Clients;Facture A;100,00;0,00\r\n"
    "AC;1;20260201;70600000;Prestations;Facture A;0,00;100,00\r\n"
)


def journal_minimal() -> Canonique:
    """Lit le FEC minimal équilibré (une facture client de 100,00 EUR).

    Paramètres : aucun.
    Retour : le journal canonique de deux lignes issu de ``FEC_MINIMAL``.
    Erreurs : ``ErreurFEC`` / ``ErreurMontant`` si le FEC était invalide.
    Usages : tests du lettrage, du mapping, des injecteurs, de la conversion.
    """
    canon: Canonique = parse_fec(FEC_MINIMAL.encode("utf-8"))
    return canon


TypeResultat = TypeVar("TypeResultat")


def resultat_etape(
    contexte: ContexteExecution, rang: int, type_attendu: type[TypeResultat]
) -> TypeResultat:
    """Rend le résultat d'une étape du pipeline, de type vérifié.

    Paramètres : ``contexte`` bilan rendu par ``MoteurConcorde.executer`` ;
    ``rang`` rang de l'étape (0 = première) ; ``type_attendu`` type que
    l'étape doit avoir produit (``tuple``, ``dict``…).
    Retour : le résultat de l'étape, du type attendu.
    Erreurs : ``AssertionError`` si le résultat n'a pas le type attendu
    (échec du test).
    Usages : ``test_pipeline_complet``, ``test_pipeline_avec_fichier_mapping``.
    """
    resultat = contexte["resultats"][rang]["resultat"]
    if not isinstance(resultat, type_attendu):
        raise AssertionError(
            "Étape %d : %r au lieu de %s"
            % (rang, type(resultat), type_attendu.__name__)
        )
    return resultat


def journal_desequilibre() -> Canonique:
    """Construit un journal d'une seule ligne au débit (50,00 EUR orphelins).

    Paramètres : aucun.
    Retour : un journal canonique volontairement déséquilibré.
    Erreurs : aucune.
    Usages : refus des injecteurs Odoo 17/18 et de la conversion de version.
    """
    canon = Canonique()
    canon.ajouter(
        LigneEcriture(
            "AC",
            "9",
            date(2026, 1, 1),
            "41100000",
            "Orphelin",
            debit=5000,
        )
    )
    return canon


class TestCentimes(unittest.TestCase):
    """Conversion des montants texte en centimes entiers."""

    def test_centimes_et_arrondi_interdit(self) -> None:
        """Vérifie la conversion en centimes et le refus de trois décimales."""
        self.assertEqual(vers_centimes("123,45"), 12345)
        self.assertEqual(vers_centimes("1 234.56"), 123456)
        self.assertEqual(vers_centimes("-12,50"), -1250)
        self.assertEqual(vers_centimes("100"), 10000)
        with self.assertRaises(ErreurMontant):
            vers_centimes("1,234")

    def test_idempotence(self) -> None:
        """Vérifie qu'une ligne ajoutée deux fois n'est comptée qu'une fois."""
        c = Canonique()
        ligne_canon = LigneEcriture(
            "AC",
            "1",
            date(2026, 1, 1),
            "41100000",
            "Test",
            debit=10000,
        )
        self.assertTrue(c.ajouter(ligne_canon))
        self.assertFalse(c.ajouter(ligne_canon))
        self.assertEqual(len(c), 1)
        self.assertEqual(c.doublons_ignores, 1)


class TestParseurFEC(unittest.TestCase):
    """Lecture des fichiers FEC (encodages, séparateurs, préambule)."""

    def test_parse_utf8_point_virgule(self) -> None:
        """Vérifie la lecture d'un FEC UTF-8 séparé par des points-virgules."""
        canon = journal_minimal()
        self.assertEqual(len(canon), 2)
        self.assertTrue(canon.est_equilibre())
        self.assertEqual(canon.lignes[0].debit, 10000)
        self.assertEqual(canon.lignes[0].compte, "41100000")

    def test_parse_iso_tab_preambule(self) -> None:
        """Vérifie la lecture d'un FEC ISO-8859-1 tabulé avec préambule."""
        brut = generer_fec(5)
        preambule = "MySoft Compta\r\nExercice 2026\r\n"
        canon = parse_fec(preambule.encode("iso-8859-1") + brut)
        self.assertEqual(len(canon), 10)
        self.assertTrue(canon.est_equilibre())

    def test_refuse_trois_decimales(self) -> None:
        """Vérifie le refus d'un montant à trois décimales."""
        fec = FEC_MINIMAL.replace("100,00;0,00", "100,001;0,00", 1)
        with self.assertRaises(ErreurMontant):
            parse_fec(fec.encode("utf-8"))

    def test_refuse_fec_sans_entete(self) -> None:
        """Vérifie le refus d'un fichier sans en-tête FEC."""
        with self.assertRaises(ErreurFEC):
            parse_fec("n'importe quoi\r\nsans entete\r\n".encode("utf-8"))


class TestLettrage(unittest.TestCase):
    """Lettrage automatique des comptes de tiers."""

    def test_paires_et_anomalies(self) -> None:
        """Vérifie qu'une facture et son règlement sont lettrés ensemble."""
        canon = journal_minimal()
        paires, anomalies, stats = lettrer(canon)
        self.assertEqual(len(paires), 0)
        self.assertEqual(stats["nb_lignes"], 2)
        fec2 = (
            "JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;"
            "EcritureLib;Debit;Credit\r\n"
            "AC;1;20260201;41100000;Clients;Fact A;50,00;0,00\r\n"
            "AC;2;20260215;41100000;Clients;Regl A;0,00;50,00\r\n"
        )
        canon2 = parse_fec(fec2.encode("utf-8"))
        paires, anomalies, stats = lettrer(canon2)
        self.assertEqual(len(paires), 1)
        self.assertEqual(paires[0]["code"], "L00001")
        self.assertEqual(len(anomalies), 0)
        self.assertEqual(stats["taux_lettrage"], 100.0)


class TestGuardian(unittest.TestCase):
    """Chaîne d'audit Guardian."""

    def test_self_check_bloquant_et_chaine(self) -> None:
        """Vérifie que toute altération de la chaîne d'audit est détectée."""
        g = Guardian()
        self.assertTrue(g.self_check())
        g.tracer("etape_test", "ok", "detail")
        self.assertTrue(g.verifier_chaine())
        g._audit[1]["charge"] = g._audit[1]["charge"] + "x"
        self.assertFalse(g.verifier_chaine())
        g2 = Guardian()
        g2._audit = [{"charge": "a", "empreinte": "faux"}]
        with self.assertRaises(ErreurGuardian):
            g2.self_check()

    def test_envelopper_etape(self) -> None:
        """Vérifie qu'une étape enveloppée rend son résultat ou son erreur."""
        g = Guardian()
        g.self_check()
        self.assertEqual(g.envelopper_etape("calcul", lambda: 2 + 2), 4)
        with self.assertRaises(ValueError):
            g.envelopper_etape("echec", lambda: int("x"))


class TestMarceauEtMoteur(unittest.TestCase):
    """Assistant Marceau et pipeline par défaut du moteur."""

    def test_marceau_jamais_muet(self) -> None:
        """Vérifie que Marceau répond toujours, même sans clé d'API."""
        m = Marceau(api_key=None)
        self.assertEqual(m.mode, "regles")
        for question in [
            "lettrage ?",
            "c'est quoi Guardian ?",
            "montants ?",
            "au hasard ?",
        ]:
            self.assertTrue(len(m.repondre(question)) > 10)

    def test_pipeline_complet(self) -> None:
        """Vérifie le pipeline par défaut sur un FEC synthétique."""
        brut = generer_fec(10)
        moteur = MoteurConcorde()
        contexte = moteur.executer(brut)
        self.assertEqual(len(contexte["resultats"]), 4)
        self.assertTrue(contexte["audit_valide"])
        self.assertTrue(contexte["empreinte_guardian"])
        for r in contexte["resultats"]:
            self.assertTrue(r["marceau"])
        stats = resultat_etape(contexte, 2, tuple)[2]
        self.assertEqual(stats["nb_lignes"], 20)


class TestMapping(unittest.TestCase):
    """Correspondance des comptes Quadra vers Odoo."""

    MAPPING_CLIENT = [
        ("41100000", "41000000"),
        ("70600000", "70600000"),
        ("40100000", "40000000"),
        ("60100000", "60110000"),
    ]

    def test_charger_mapping_tuples(self) -> None:
        """Vérifie le chargement d'un mapping donné en paires."""
        m = charger_mapping(self.MAPPING_CLIENT)
        self.assertEqual(m["41100000"], "41000000")
        self.assertEqual(len(m), 4)

    def test_mapper_comptes_ok(self) -> None:
        """Vérifie le remplacement des comptes par leur correspondance Odoo."""
        canon = journal_minimal()
        r = mapper_comptes(canon, self.MAPPING_CLIENT)
        self.assertEqual(r["nb_mappees"], 2)
        self.assertEqual(canon.lignes[0].compte, "41000000")
        self.assertEqual(canon.lignes[1].compte, "70600000")

    def test_mapper_comptes_inconnu_bloquant(self) -> None:
        """Vérifie qu'un compte sans correspondance bloque le mapping."""
        canon = journal_minimal()
        mapping_incomplet = [("41100000", "41000000")]
        with self.assertRaises(ErreurMapping) as cm:
            mapper_comptes(canon, mapping_incomplet)
        self.assertIn("70600000", str(cm.exception))

    def test_pipeline_avec_fichier_mapping(self) -> None:
        """Vérifie le pipeline complet avec un mapping lu depuis un JSON."""
        correspondances = [
            {"quadra": "41100000", "odoo": "41000000"},
            {"quadra": "70615000", "odoo": "70600000"},
            {"quadra": "40120000", "odoo": "40110000"},
            {"quadra": "60411000", "odoo": "60400000"},
        ]
        with tempfile.TemporaryDirectory() as dossier_temporaire:
            chemin_mapping = os.path.join(dossier_temporaire, "mapping.json")
            with open(chemin_mapping, "w", encoding="utf-8") as fichier:
                json.dump(correspondances, fichier)
            config = {
                "mapping": {"fichier": chemin_mapping},
                "pipeline": [
                    {
                        "nom": "importer_fec",
                        "module": "core.fec_parser",
                        "fonction": "parse_fec",
                    },
                    {
                        "nom": "verifier_equilibre",
                        "fonction": "verifier_equilibre",
                    },
                    {"nom": "mapper_comptes", "fonction": "mapper_comptes"},
                    {
                        "nom": "lettrer",
                        "module": "core.lettrage",
                        "fonction": "lettrer",
                    },
                    {"nom": "rapport", "fonction": "rapport"},
                ],
            }
            comptes = [("41100000", "70615000"), ("40120000", "60411000")]
            brut = generer_fec(10, comptes=comptes)
            moteur = MoteurConcorde(config=config)
            contexte = moteur.executer(brut)
        self.assertEqual(len(contexte["resultats"]), 5)
        self.assertTrue(contexte["audit_valide"])
        canon = resultat_etape(contexte, 1, dict)["canon"]
        comptes_attendus = {"41000000", "70600000", "40110000", "60400000"}
        self.assertEqual(
            {ligne_canon.compte for ligne_canon in canon.lignes},
            comptes_attendus,
        )


class TestInjecteurOdoo18(unittest.TestCase):
    """Injecteur Odoo 18 (simulation par défaut)."""

    def test_dry_run_par_defaut(self) -> None:
        """Vérifie que l'injecteur Odoo 18 simule par défaut."""
        inj = InjecteurOdoo18()  # aucun paramètre Odoo
        self.assertTrue(
            inj.dry_run
        )  # sécurité : jamais d'injection réelle par défaut
        self.assertTrue(inj.guardian.self_check_ok)  # Guardian obligatoire
        self.assertEqual(inj.VERSION_CIBLE, "18")

    def test_injection_dry_run_idempotente(self) -> None:
        """Vérifie que la simulation Odoo 18 est idempotente par écriture."""
        canon = journal_minimal()
        inj = InjecteurOdoo18()
        r1 = inj.injecter(canon)
        self.assertEqual(r1["mode"], "dry-run")
        self.assertEqual(r1["cible"], "odoo-18")
        self.assertEqual(r1["nb_ecritures"], 1)
        self.assertEqual(r1["injectees"][0]["ref"], "CONCORDE/AC/1")
        self.assertEqual(r1["injectees"][0]["total_centimes"], 10000)
        self.assertTrue(r1["injectees"][0]["simule"])
        r2 = inj.injecter(
            canon
        )  # re-injection : idempotence au niveau écriture
        self.assertEqual(r2["nb_ecritures"], 1)
        self.assertTrue(inj.guardian.verifier_chaine())

    def test_refuse_journal_desequilibre(self) -> None:
        """Vérifie le refus d'injecter un journal déséquilibré dans Odoo 18."""
        c = journal_desequilibre()
        inj = InjecteurOdoo18()
        with self.assertRaises(ErreurInjecteur):
            inj.injecter(c)  # tolérance Concordance 0,00 €

    def test_production_sans_identifiants_refusee(self) -> None:
        """Vérifie le refus d'une injection réelle sans identifiants Odoo."""
        inj = InjecteurOdoo18(
            dry_run=False
        )  # production sans config -> erreur claire
        canon = journal_minimal()
        with self.assertRaises(ErreurInjecteur):
            inj.injecter(canon)


class TestConversionOdoo(unittest.TestCase):
    """Conversion des écritures d'une version d'Odoo à une autre."""

    def test_chainee_14_vers_19(self) -> None:
        """Vérifie la conversion 14 vers 19 saut par saut, sans écart."""
        conv = ConvertisseurOdoo()
        self.assertTrue(conv.dry_run)  # jamais de données réelles par défaut
        self.assertTrue(conv.guardian.self_check_ok)
        r = conv.convertir_chainee(journal_minimal(), source="14", cible="19")
        self.assertEqual(r["source"], "14")
        self.assertEqual(r["cible"], "19")
        self.assertEqual(len(r["etapes"]), 5)  # 14→15→16→17→18→19
        self.assertTrue(all(e["equilibre"] for e in r["etapes"]))
        self.assertEqual(r["nb_lignes_final"], len(journal_minimal()))
        # montants en centimes inchangés de bout en bout
        self.assertEqual(
            r["canonique"].total_debit, journal_minimal().total_debit
        )
        self.assertEqual(
            r["canonique"].total_credit, journal_minimal().total_credit
        )
        self.assertTrue(
            all(
                ligne_canon.version_source == "19"
                for ligne_canon in r["canonique"].lignes
            )
        )

    def test_saut_unique_17_vers_18(self) -> None:
        """Vérifie la conversion directe 17 vers 18 en un seul saut."""
        conv = ConvertisseurOdoo()
        r = conv.convertir_chainee(journal_minimal(), source="17", cible="18")
        self.assertEqual(len(r["etapes"]), 1)
        self.assertEqual(r["etapes"][0]["saut"], "17→18")
        self.assertEqual(r["version_source_final"], "18")

    def test_refuse_version_non_supportee(self) -> None:
        """Vérifie le refus des versions inconnues et des retours arrière."""
        conv = ConvertisseurOdoo()
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(journal_minimal(), source="13", cible="19")
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(
                journal_minimal(), source="19", cible="14"
            )  # rétro refusée

    def test_equilibre_verifie_et_audit_guardian(self) -> None:
        """Vérifie l'équilibre à chaque saut et la chaîne d'audit."""
        conv = ConvertisseurOdoo()
        r = conv.convertir_chainee(journal_minimal(), source="14", cible="19")
        self.assertTrue(r["canonique"].est_equilibre(tolerance=0))
        self.assertTrue(conv.guardian.verifier_chaine())
        # écriture déséquilibrée -> refus à chaque saut, tolérance 0,00 €
        c = journal_desequilibre()
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(c, source="14", cible="15")


class TestInjecteurOdoo17(unittest.TestCase):
    """Cible native actuelle : Odoo 17 Community."""

    def test_dry_run_par_defaut(self) -> None:
        """Vérifie que l'injecteur Odoo 17 simule par défaut."""
        inj = InjecteurOdoo17()
        self.assertTrue(inj.dry_run)
        self.assertTrue(inj.guardian.self_check_ok)
        self.assertEqual(inj.VERSION_CIBLE, "17")

    def test_injection_dry_run_idempotente(self) -> None:
        """Vérifie que la simulation Odoo 17 est idempotente par écriture."""
        canon = journal_minimal()
        inj = InjecteurOdoo17()
        r = inj.injecter(canon)
        self.assertEqual(r["mode"], "dry-run")
        self.assertEqual(r["cible"], "odoo-17")
        self.assertEqual(r["nb_ecritures"], 1)
        self.assertEqual(r["injectees"][0]["total_centimes"], 10000)
        self.assertTrue(r["injectees"][0]["simule"])
        r2 = inj.injecter(canon)
        self.assertEqual(r2["nb_ecritures"], 1)
        self.assertTrue(inj.guardian.verifier_chaine())

    def test_refuse_journal_desequilibre(self) -> None:
        """Vérifie le refus d'injecter un journal déséquilibré dans Odoo 17."""
        c = journal_desequilibre()
        inj = InjecteurOdoo17()
        with self.assertRaises(ErreurInjecteur17):
            inj.injecter(c)  # tolérance Concordance 0,00 €


if __name__ == "__main__":
    unittest.main(verbosity=2)
