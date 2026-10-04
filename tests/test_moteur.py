# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
# Tests unitaires — tolérance Concordance 0,00 EUR.
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.canonical import Canonique, LigneEcriture, vers_centimes, ErreurMontant
from core.fec_parser import parse_fec, ErreurFEC
from core.lettrage import lettrer
from core.guardian import Guardian, ErreurGuardian
from core.marceau import Marceau
from core.moteur import MoteurConcorde
from core.mapping import charger_mapping, mapper_comptes, ErreurMapping
from samples.generateur_fec_test import generer_fec
from injectors.odoo17 import InjecteurOdoo17, ErreurInjecteur as ErreurInjecteur17
from injectors.odoo18 import InjecteurOdoo18, ErreurInjecteur
from injectors.odoo_conversion import ConvertisseurOdoo, ErreurConversion


class TestCentimes(unittest.TestCase):
    def test_centimes_et_arrondi_interdit(self):
        self.assertEqual(vers_centimes("123,45"), 12345)
        self.assertEqual(vers_centimes("1 234.56"), 123456)
        self.assertEqual(vers_centimes("-12,50"), -1250)
        self.assertEqual(vers_centimes("100"), 10000)
        with self.assertRaises(ErreurMontant):
            vers_centimes("1,234")

    def test_idempotence(self):
        c = Canonique()
        l = LigneEcriture("AC", "1", __import__("datetime").date(2026, 1, 1),
                          "41100000", "Test", debit=10000)
        self.assertTrue(c.ajouter(l))
        self.assertFalse(c.ajouter(l))
        self.assertEqual(len(c), 1)
        self.assertEqual(c.doublons_ignores, 1)


class TestParseurFEC(unittest.TestCase):
    FEC_MINIMAL = (
        "JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;EcritureLib;Debit;Credit\r\n"
        "AC;1;20260201;41100000;Clients;Facture A;100,00;0,00\r\n"
        "AC;1;20260201;70600000;Prestations;Facture A;0,00;100,00\r\n"
    )

    def test_parse_utf8_point_virgule(self):
        canon = parse_fec(self.FEC_MINIMAL.encode("utf-8"))
        self.assertEqual(len(canon), 2)
        self.assertTrue(canon.est_equilibre())
        self.assertEqual(canon.lignes[0].debit, 10000)
        self.assertEqual(canon.lignes[0].compte, "41100000")

    def test_parse_iso_tab_preambule(self):
        brut = generer_fec(5)
        preambule = "MySoft Compta\r\nExercice 2026\r\n"
        canon = parse_fec(preambule.encode("iso-8859-1") + brut)
        self.assertEqual(len(canon), 10)
        self.assertTrue(canon.est_equilibre())

    def test_refuse_trois_decimales(self):
        fec = self.FEC_MINIMAL.replace("100,00;0,00", "100,001;0,00", 1)
        with self.assertRaises(ErreurMontant):
            parse_fec(fec.encode("utf-8"))

    def test_refuse_fec_sans_entete(self):
        with self.assertRaises(ErreurFEC):
            parse_fec("n'importe quoi\r\nsans entete\r\n".encode("utf-8"))


class TestLettrage(unittest.TestCase):
    def test_paires_et_anomalies(self):
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
        paires, anomalies, stats = lettrer(canon)
        self.assertEqual(len(paires), 0)
        self.assertEqual(stats["nb_lignes"], 2)
        fec2 = ("JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;EcritureLib;Debit;Credit\r\n"
                "AC;1;20260201;41100000;Clients;Fact A;50,00;0,00\r\n"
                "AC;2;20260215;41100000;Clients;Regl A;0,00;50,00\r\n")
        canon2 = parse_fec(fec2.encode("utf-8"))
        paires, anomalies, stats = lettrer(canon2)
        self.assertEqual(len(paires), 1)
        self.assertEqual(paires[0]["code"], "L00001")
        self.assertEqual(len(anomalies), 0)
        self.assertEqual(stats["taux_lettrage"], 100.0)


class TestGuardian(unittest.TestCase):
    def test_self_check_bloquant_et_chaine(self):
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

    def test_envelopper_etape(self):
        g = Guardian()
        g.self_check()
        self.assertEqual(g.envelopper_etape("calcul", lambda: 2 + 2), 4)
        with self.assertRaises(ValueError):
            g.envelopper_etape("echec", lambda: int("x"))


class TestMarceauEtMoteur(unittest.TestCase):
    def test_marceau_jamais_muet(self):
        m = Marceau(api_key=None)
        self.assertEqual(m.mode, "regles")
        for question in ["lettrage ?", "c'est quoi Guardian ?", "montants ?", "au hasard ?"]:
            self.assertTrue(len(m.repondre(question)) > 10)

    def test_pipeline_complet(self):
        brut = generer_fec(10)
        moteur = MoteurConcorde()
        contexte = moteur.executer(brut)
        self.assertEqual(len(contexte["resultats"]), 4)
        self.assertTrue(contexte["audit_valide"])
        self.assertTrue(contexte["empreinte_guardian"])
        for r in contexte["resultats"]:
            self.assertTrue(r["marceau"])
        stats = contexte["resultats"][2]["resultat"][2]
        self.assertEqual(stats["nb_lignes"], 20)


class TestMapping(unittest.TestCase):
    MAPPING_CLIENT = [
        ("41100000", "41000000"), ("70600000", "70600000"),
        ("40100000", "40000000"), ("60100000", "60110000"),
    ]

    def test_charger_mapping_tuples(self):
        m = charger_mapping(self.MAPPING_CLIENT)
        self.assertEqual(m["41100000"], "41000000")
        self.assertEqual(len(m), 4)

    def test_mapper_comptes_ok(self):
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
        r = mapper_comptes(canon, self.MAPPING_CLIENT)
        self.assertEqual(r["nb_mappees"], 2)
        self.assertEqual(canon.lignes[0].compte, "41000000")
        self.assertEqual(canon.lignes[1].compte, "70600000")

    def test_mapper_comptes_inconnu_bloquant(self):
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
        mapping_incomplet = [("41100000", "41000000")]
        with self.assertRaises(ErreurMapping) as cm:
            mapper_comptes(canon, mapping_incomplet)
        self.assertIn("70600000", str(cm.exception))

    def test_pipeline_avec_mapping_reel_client(self):
        chemin = "/home/user/tool-results/data-analysis/concorde-fec/mapping.json"
        if not os.path.exists(chemin):
            self.skipTest("mapping client non présent")
        config = {
            "mapping": {"fichier": chemin},
            "pipeline": [
                {"nom": "importer_fec", "module": "core.fec_parser", "fonction": "parse_fec"},
                {"nom": "verifier_equilibre", "fonction": "verifier_equilibre"},
                {"nom": "mapper_comptes", "fonction": "mapper_comptes"},
                {"nom": "lettrer", "module": "core.lettrage", "fonction": "lettrer"},
                {"nom": "rapport", "fonction": "rapport"},
            ],
        }
        comptes = [("41100000", "70615000"), ("40120000", "60411000")]
        brut = generer_fec(10, comptes=comptes)
        moteur = MoteurConcorde(config=config)
        contexte = moteur.executer(brut)
        self.assertEqual(len(contexte["resultats"]), 5)
        self.assertTrue(contexte["audit_valide"])
        canon = contexte["resultats"][1]["resultat"]["canon"]
        self.assertTrue(all(l.compte in ("41000000", "70600000", "40110000", "60400000", "70615000")
                            for l in canon.lignes))


class TestInjecteurOdoo18(unittest.TestCase):
    def test_dry_run_par_defaut(self):
        inj = InjecteurOdoo18()  # aucun paramètre Odoo
        self.assertTrue(inj.dry_run)  # sécurité : jamais d'injection réelle par défaut
        self.assertTrue(inj.guardian.self_check_ok)  # Guardian obligatoire
        self.assertEqual(inj.VERSION_CIBLE, "18")

    def test_injection_dry_run_idempotente(self):
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
        inj = InjecteurOdoo18()
        r1 = inj.injecter(canon)
        self.assertEqual(r1["mode"], "dry-run")
        self.assertEqual(r1["cible"], "odoo-18")
        self.assertEqual(r1["nb_ecritures"], 1)
        self.assertEqual(r1["injectees"][0]["ref"], "CONCORDE/AC/1")
        self.assertEqual(r1["injectees"][0]["total_centimes"], 10000)
        self.assertTrue(r1["injectees"][0]["simule"])
        r2 = inj.injecter(canon)  # re-injection : idempotence au niveau écriture
        self.assertEqual(r2["nb_ecritures"], 1)
        self.assertTrue(inj.guardian.verifier_chaine())

    def test_refuse_journal_desequilibre(self):
        c = Canonique()
        c.ajouter(LigneEcriture("AC", "9", __import__("datetime").date(2026, 1, 1),
                                "41100000", "Orphelin", debit=5000))
        inj = InjecteurOdoo18()
        with self.assertRaises(ErreurInjecteur):
            inj.injecter(c)  # tolérance Concordance 0,00 €

    def test_production_sans_identifiants_refusee(self):
        inj = InjecteurOdoo18(dry_run=False)  # production sans config -> erreur claire
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
        with self.assertRaises(ErreurInjecteur):
            inj.injecter(canon)


class TestConversionOdoo(unittest.TestCase):
    def _canon(self):
        return parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))

    def test_chainee_14_vers_19(self):
        conv = ConvertisseurOdoo()
        self.assertTrue(conv.dry_run)          # jamais de données réelles par défaut
        self.assertTrue(conv.guardian.self_check_ok)
        r = conv.convertir_chainee(self._canon(), source="14", cible="19")
        self.assertEqual(r["source"], "14")
        self.assertEqual(r["cible"], "19")
        self.assertEqual(len(r["etapes"]), 5)  # 14→15→16→17→18→19
        self.assertTrue(all(e["equilibre"] for e in r["etapes"]))
        self.assertEqual(r["nb_lignes_final"], len(self._canon()))
        # montants en centimes inchangés de bout en bout
        self.assertEqual(r["canonique"].total_debit, self._canon().total_debit)
        self.assertEqual(r["canonique"].total_credit, self._canon().total_credit)
        self.assertTrue(all(l.version_source == "19" for l in r["canonique"].lignes))

    def test_saut_unique_17_vers_18(self):
        conv = ConvertisseurOdoo()
        r = conv.convertir_chainee(self._canon(), source="17", cible="18")
        self.assertEqual(len(r["etapes"]), 1)
        self.assertEqual(r["etapes"][0]["saut"], "17→18")
        self.assertEqual(r["version_source_final"], "18")

    def test_refuse_version_non_supportee(self):
        conv = ConvertisseurOdoo()
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(self._canon(), source="13", cible="19")
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(self._canon(), source="19", cible="14")  # rétro refusée

    def test_equilibre_verifie_et_audit_guardian(self):
        conv = ConvertisseurOdoo()
        r = conv.convertir_chainee(self._canon(), source="14", cible="19")
        self.assertTrue(r["canonique"].est_equilibre(tolerance=0))
        self.assertTrue(conv.guardian.verifier_chaine())
        # écriture déséquilibrée -> refus à chaque saut, tolérance 0,00 €
        c = Canonique()
        c.ajouter(LigneEcriture("AC", "9", __import__("datetime").date(2026, 1, 1),
                                "41100000", "Orphelin", debit=5000))
        with self.assertRaises(ErreurConversion):
            conv.convertir_chainee(c, source="14", cible="15")


class TestInjecteurOdoo17(unittest.TestCase):
    """Cible native actuelle : Odoo 17 Community."""

    def test_dry_run_par_defaut(self):
        inj = InjecteurOdoo17()
        self.assertTrue(inj.dry_run)
        self.assertTrue(inj.guardian.self_check_ok)
        self.assertEqual(inj.VERSION_CIBLE, "17")

    def test_injection_dry_run_idempotente(self):
        canon = parse_fec(TestParseurFEC.FEC_MINIMAL.encode("utf-8"))
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

    def test_refuse_journal_desequilibre(self):
        c = Canonique()
        c.ajouter(LigneEcriture("AC", "9", __import__("datetime").date(2026, 1, 1),
                                "41100000", "Orphelin", debit=5000))
        inj = InjecteurOdoo17()
        with self.assertRaises(ErreurInjecteur17):
            inj.injecter(c)  # tolérance Concordance 0,00 €


if __name__ == "__main__":
    unittest.main(verbosity=2)
