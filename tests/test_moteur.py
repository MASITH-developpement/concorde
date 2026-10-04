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
from core.yaml_min import parse_yaml
from samples.generateur_fec_test import generer_fec


class TestCentimes(unittest.TestCase):
    def test_centimes_et_arrondi_interdit(self):
        self.assertEqual(vers_centimes("123,45"), 12345)
        self.assertEqual(vers_centimes("1 234.56"), 123456)
        self.assertEqual(vers_centimes("-12,50"), -1250)
        self.assertEqual(vers_centimes("100"), 10000)
        with self.assertRaises(ErreurMontant):
            vers_centimes("1,234")  # 3 décimales : refus, jamais d'arrondi silencieux

    def test_idempotence(self):
        c = Canonique()
        l = LigneEcriture("AC", "1", __import__("datetime").date(2026, 1, 1),
                          "411000", "Test", debit=10000)
        self.assertTrue(c.ajouter(l))
        self.assertFalse(c.ajouter(l))  # doublon ignoré
        self.assertEqual(len(c), 1)
        self.assertEqual(c.doublons_ignores, 1)


class TestParseurFEC(unittest.TestCase):
    FEC_MINIMAL = (
        "JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;EcritureLib;Debit;Credit\r\n"
        "AC;1;20260101;411000;Clients;Facture A;100,00;0,00\r\n"
        "AC;1;20260101;706000;Prestations;Facture A;0,00;100,00\r\n"
    )

    def test_parse_utf8_point_virgule(self):
        canon = parse_fec(self.FEC_MINIMAL.encode("utf-8"))
        self.assertEqual(len(canon), 2)
        self.assertTrue(canon.est_equilibre())
        self.assertEqual(canon.lignes[0].debit, 10000)

    def test_parse_iso_tab_preambule(self):
        brut = generer_fec(5)
        preambule = "MySoft Compta\r\nExercice 2026\r\n"
        canon = parse_fec(preambule.encode("iso-8859-1") + brut)
        self.assertEqual(len(canon), 20)
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
        self.assertEqual(len(paires), 0)  # comptes différents : pas de paire sur un même compte
        self.assertEqual(stats["nb_lignes"], 2)
        # paire sur un même compte
        fec2 = ("JournalCode;EcritureNum;EcritureDate;CompteNum;CompteLib;EcritureLib;Debit;Credit\r\n"
                "AC;1;20260101;411000;Clients;Fact A;50,00;0,00\r\n"
                "AC;2;20260315;411000;Clients;Regl A;0,00;50,00\r\n")
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
        # altération -> chaîne cassée
        g._audit[1]["charge"] = g._audit[1]["charge"] + "x"
        self.assertFalse(g.verifier_chaine())
        g2 = Guardian()
        g2._audit = [{"charge": "a", "empreinte": "faux"}]
        with self.assertRaises(ErreurGuardian):
            g2.self_check()  # moteur refuserait de démarrer

    def test_envelopper_etape(self):
        g = Guardian()
        g.self_check()
        self.assertEqual(g.envelopper_etape("calcul", lambda: 2 + 2), 4)
        with self.assertRaises(ValueError):
            g.envelopper_etape("echec", lambda: int("x"))


class TestMarceauEtMoteur(unittest.TestCase):
    def test_marceau_jamais_muet(self):
        m = Marceau(api_key=None)  # pas de clé -> moteur à règles
        self.assertEqual(m.mode, "regles")
        for question in ["lettrage ?", "c'est quoi Guardian ?", "montants ?", "au hasard ?"]:
            self.assertTrue(len(m.repondre(question)) > 10)  # jamais muet

    def test_pipeline_complet(self):
        brut = generer_fec(10)
        moteur = MoteurConcorde()
        contexte = moteur.executer(brut)
        self.assertEqual(len(contexte["resultats"]), 4)
        self.assertTrue(contexte["audit_valide"])
        self.assertTrue(contexte["empreinte_guardian"])
        for r in contexte["resultats"]:
            self.assertTrue(r["marceau"])  # chaque donnée liée à son Marceau
        stats = contexte["resultats"][2]["resultat"][2]
        self.assertEqual(stats["nb_lignes"], 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
