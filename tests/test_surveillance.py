# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests : journal, alertes par compte, changements, contrôles techniques, centre d'alertes."""
import os
import tempfile
import unittest

from core.comptes import alertes_balance, grand_livre, solde_texte
from core.explications import CATALOGUE, expliquer
from core.journal import Journal, JournalMuet, duree_texte, nombre_texte
from core.marceau import Marceau
from core.surveillance import CentreAlertes, comparer_instantanes, controles_techniques


def compte(code, debit=0, credit=0, type_="expense", deprecie=False, libelle="X"):
    return {"id": hash(code) % 10000, "code": code, "libelle": libelle, "type": type_,
            "lettrable": False, "deprecie": deprecie, "debit": debit, "credit": credit,
            "lignes": 1 if debit or credit else 0, "non_lettrees": 0}


class TestJournal(unittest.TestCase):
    def test_etapes_et_lecture_incrementale(self):
        j = Journal()
        j.dire("début")
        with j.etape("Lecture") as e:
            e.conclure("12 lignes")
        evs, suivant = j.depuis(0)
        self.assertEqual(suivant, 3)
        self.assertEqual([e["niveau"] for e in evs], ["info", "etape", "ok"])
        self.assertTrue(evs[2]["message"].startswith("✓ Lecture — 12 lignes ("))
        self.assertEqual(j.depuis(3), ([], 3))

    def test_echec_raconte(self):
        j = Journal()
        with self.assertRaises(ValueError):
            with j.etape("Calcul"):
                raise ValueError("boum")
        self.assertEqual(j.tout()[-1]["niveau"], "erreur")
        self.assertIn("boum", j.tout()[-1]["message"])

    def test_borne(self):
        j = Journal(taille_max=3)
        for i in range(5):
            j.dire(str(i))
        evs, suivant = j.depuis(0)
        self.assertEqual([e["message"] for e in evs], ["2", "3", "4"])
        self.assertEqual(suivant, 5)
        self.assertEqual([e["message"] for e in j.depuis(4)[0]], ["4"])

    def test_muet_et_formats(self):
        JournalMuet().dire("rien")
        with JournalMuet().etape("x"):
            pass
        self.assertEqual(nombre_texte(153765), "153 765")
        self.assertEqual(duree_texte(5.24), "5,2 s")
        self.assertEqual(duree_texte(0.25), "250 ms")
        self.assertEqual(duree_texte(125), "2 min 05 s")


class TestMarceau(unittest.TestCase):
    def test_explications_toujours_locales(self):
        m = Marceau(api_key="cle-factice")          # même avec Mistral configuré…
        x = m.expliquer_alerte("CAISSE_CREDITRICE")
        self.assertEqual(x["titre"], "Caisse créditrice")
        self.assertIn("espèces", x["pourquoi"])
        inconnu = expliquer("CODE_INEXISTANT", "Quelque chose")
        self.assertEqual(inconnu["titre"], "Quelque chose")   # jamais muet

    def test_catalogue_complet(self):
        for code, (titre, pourquoi, que_faire) in CATALOGUE.items():
            self.assertTrue(titre and pourquoi and que_faire, code)


class TestAlertesBalance(unittest.TestCase):
    def codes(self, balance, tiers=()):
        r, par_compte = alertes_balance(balance, tiers)
        return {c["code"]: c["nombre"] for c in r.constats}, par_compte

    def test_regles(self):
        bal = [compte("530000", 0, 100, "asset_cash"),        # caisse créditrice
               compte("512000", 0, 50, "asset_cash"),         # banque créditrice
               compte("471000", 10, 0, "asset_current"),      # attente non soldée
               compte("606000", 0, 30),                       # charge créditrice
               compte("609000", 0, 30),                       # rabais : normal
               compte("603100", 0, 30),                       # variation de stock : libre
               compte("706000", 40, 0, "income"),             # produit débiteur
               compte("445660", 0, 5, "asset_current"),       # TVA déductible créditrice
               compte("445710", 5, 0, "liability_current"),   # TVA collectée débitrice
               compte("626000", 5, 0, deprecie=True),         # déprécié avec solde
               compte("101000", 185, 0, "equity")]            # équilibre (245 = 245)
        c, par_compte = self.codes(bal)
        self.assertNotIn("BALANCE_DESEQUILIBREE", c)
        for code in ("CAISSE_CREDITRICE", "BANQUE_CREDITRICE", "COMPTE_ATTENTE_NON_SOLDE",
                     "CHARGE_CREDITRICE", "PRODUIT_DEBITEUR", "TVA_DEDUCTIBLE_CREDITRICE",
                     "TVA_COLLECTEE_DEBITRICE", "COMPTE_DEPRECIE_SOLDE"):
            self.assertEqual(c[code], 1, code)
        self.assertNotIn("609000", par_compte)
        self.assertNotIn("603100", par_compte)
        self.assertEqual(par_compte["530000"], ["CAISSE_CREDITRICE"])

    def test_desequilibre_bloquant(self):
        r, _ = alertes_balance([compte("601000", 100, 0), compte("401000", 0, 99,
                                                                 "liability_payable")])
        self.assertEqual(r.statut, "bloquant")

    def test_tiers(self):
        bal = [compte("411000", 0, 0, "asset_receivable"),
               compte("401000", 0, 0, "liability_payable")]
        tiers = [{"compte": "411000", "tiers_id": 1, "tiers_nom": "A", "tiers_ref": "",
                  "debit": 0, "credit": 500, "lignes": 1},
                 {"compte": "411000", "tiers_id": 2, "tiers_nom": "B", "tiers_ref": "",
                  "debit": 900, "credit": 0, "lignes": 1},
                 {"compte": "401000", "tiers_id": 3, "tiers_nom": "C", "tiers_ref": "F3",
                  "debit": 200, "credit": 0, "lignes": 1},
                 {"compte": "401000", "tiers_id": None, "tiers_nom": "", "tiers_ref": "",
                  "debit": 50, "credit": 0, "lignes": 1}]
        c, par_compte = self.codes(bal, tiers)
        self.assertEqual(c["CLIENT_CREDITEUR"], 1)
        self.assertEqual(c["FOURNISSEUR_DEBITEUR"], 1)      # la ligne sans tiers est ignorée ici
        self.assertEqual(par_compte["401000"], ["FOURNISSEUR_DEBITEUR"])

    def test_grand_livre_et_solde(self):
        lignes = [{"debit": 100, "credit": 0}, {"debit": 0, "credit": 30},
                  {"debit": 0, "credit": 100}]
        page, tot = grand_livre(lignes, offset=1, limite=1)
        self.assertEqual([l["cumul"] for l in page], [70])
        self.assertEqual(tot, {"lignes": 3, "debit": 100, "credit": 130, "solde": -30})
        self.assertEqual(solde_texte({"debit": 0, "credit": 3000}), "30,00 C")
        self.assertEqual(solde_texte({"debit": 5, "credit": 5}), "0,00")


def photo(ecritures, comptes=None, verrous=None):
    return {"ecritures": ecritures, "comptes": comptes or {"1": "411000"},
            "verrous": verrous or {"periode": None, "exercice": None, "tva": None}}


class TestChangements(unittest.TestCase):
    def codes(self, a, n):
        return {(c["code"], c["niveau"]): c["nombre"]
                for c in comparer_instantanes(a, n).constats}

    def test_premier_passage(self):
        self.assertIn(("INSTANTANE_INITIAL", "INFO"), self.codes(None, photo({})))

    def test_changements(self):
        a = photo({"1": ["posted", "t1", "VEN/1"], "2": ["posted", "t1", "VEN/2"],
                   "3": ["draft", "t1", "/"], "4": ["posted", "t1", "VEN/4"],
                   "5": ["draft", "t1", "/"]},
                  verrous={"periode": None, "exercice": "2025-12-31", "tva": None})
        n = photo({"1": ["draft", "t2", "VEN/1"],         # remise en brouillon
                   "3": ["posted", "t2", "OD/3"],         # validée
                   "4": ["posted", "t2", "VEN/4"],        # modifiée
                   "6": ["draft", "t2", "/"]},            # nouvelle ; 2 et 5 supprimées
                  comptes={"1": "411000", "9": "471000"},
                  verrous={"periode": "2026-06-30", "exercice": "2024-12-31", "tva": None})
        c = self.codes(a, n)
        self.assertEqual(c[("ECRITURES_REMISES_BROUILLON", "ALERTE")], 1)
        self.assertEqual(c[("ECRITURES_VALIDEES", "INFO")], 1)
        self.assertEqual(c[("ECRITURES_MODIFIEES", "INFO")], 1)
        self.assertEqual(c[("ECRITURES_NOUVELLES", "INFO")], 1)
        self.assertEqual(c[("ECRITURES_SUPPRIMEES", "ALERTE")], 1)     # VEN/2 validée
        self.assertEqual(c[("BROUILLONS_SUPPRIMES", "INFO")], 1)       # brouillon 5
        self.assertEqual(c[("COMPTES_CREES", "INFO")], 1)
        self.assertEqual(c[("PERIODE_DEVERROUILLEE", "ALERTE")], 1)    # exercice recule
        self.assertEqual(c[("VERROU_AVANCE", "INFO")], 1)              # période avance

    def test_rien_ne_change(self):
        p = photo({"1": ["posted", "t1", "VEN/1"]})
        self.assertFalse([c for c in comparer_instantanes(p, p).constats if c["nombre"]])


class TestTechniques(unittest.TestCase):
    def test_controles(self):
        d = tempfile.mkdtemp()
        r = controles_techniques(False, "refusé", False, "timeout", d,
                                 [("2026-11-06T06:00:00", "analyser", "b", "boum")],
                                 [("t", "1.2.3.4")] * 3 + [("t", "5.6.7.8")])
        c = {x["code"]: x for x in r.constats}
        self.assertEqual(c["PG_INJOIGNABLE"]["niveau"], "BLOQUANT")
        self.assertIn("ODOO_INJOIGNABLE", c)
        self.assertEqual(c["TACHE_ECHEC"]["nombre"], 1)
        self.assertEqual(c["CONNEXIONS_REFUSEES"]["exemples"][0], "1.2.3.4 : 3 essai(s)")
        ok = controles_techniques(True, "", True, "", d, [], [("t", "ip")] * 2)
        self.assertEqual([x["code"] for x in ok.constats], [])     # 2 essais : pas d'alerte


class TestCentre(unittest.TestCase):
    def constat(self, code, nombre=1, niveau="ALERTE"):
        return {"code": code, "niveau": niveau, "message": code, "nombre": nombre,
                "exemples": ["e"] * nombre}

    def test_cycle_de_vie(self):
        chemin = os.path.join(tempfile.mkdtemp(), "alertes.json")
        c = CentreAlertes(chemin)
        n, r = c.synchroniser("balance", "b", [self.constat("CAISSE_CREDITRICE"),
                                               self.constat("X", niveau="INFO")])
        self.assertEqual((n, r), (["CAISSE_CREDITRICE"], []))     # INFO non retenue
        self.assertEqual(c.resume()["non_vues"], 1)
        c.marquer_vue()
        self.assertEqual(c.resume()["non_vues"], 0)
        c.synchroniser("balance", "b", [self.constat("CAISSE_CREDITRICE", 3)])
        self.assertEqual(c.resume()["non_vues"], 1)              # aggravée : remontrée
        self.assertEqual(c.lister()[0]["explication"]["titre"], "Caisse créditrice")
        # autre source, autre base : intactes
        c.synchroniser("balance", "autre", [self.constat("Y")])
        n, r = c.synchroniser("balance", "b", [])
        self.assertEqual(r, ["CAISSE_CREDITRICE"])
        self.assertEqual(c.lister("resolue")[0]["code"], "CAISSE_CREDITRICE")
        self.assertEqual(len(c.lister("active")), 1)
        # persistance
        c2 = CentreAlertes(chemin)
        self.assertEqual(len(c2.lister()), 2)
        # réapparition : nouvelle alerte active
        n, _ = c2.synchroniser("balance", "b", [self.constat("CAISSE_CREDITRICE")])
        self.assertEqual(n, ["CAISSE_CREDITRICE"])

    def test_evenements(self):
        c = CentreAlertes(os.path.join(tempfile.mkdtemp(), "a.json"))
        c.evenements("b", [self.constat("ECRITURES_SUPPRIMEES"),
                           self.constat("ECRITURES_NOUVELLES", niveau="INFO")])
        evs = c.lister("evenement")
        self.assertEqual(len(evs), 2)
        self.assertEqual(c.resume()["non_vues"], 1)              # seule l'ALERTE compte
        c.synchroniser("changement", "b", [])                    # jamais résolus
        self.assertEqual(len(c.lister("evenement")), 2)


if __name__ == "__main__":
    unittest.main()


class TestSecurite(unittest.TestCase):
    """Lecture des résultats de securite/concorde_securite.py (ADR-0007)."""

    def ecrire(self, d, nom, heures, constats):
        import json
        from datetime import datetime, timedelta
        with open(os.path.join(d, nom + ".json"), "w") as f:
            json.dump({"date": (datetime.now() - timedelta(hours=heures)).isoformat(
                timespec="seconds"), "statut": "x", "synthese": {}, "constats": constats}, f)

    def test_absence_puis_fraicheur(self):
        from core.surveillance import constats_securite
        d = tempfile.mkdtemp()
        self.assertEqual({c["code"] for c in constats_securite(d)[0]},
                         {"SEC_SURVEILLANCE_ARRETEE"})
        self.ecrire(d, "controle", 0, [])
        self.ecrire(d, "antivirus", 10, [])
        self.assertEqual(constats_securite(d)[0], [])
        self.ecrire(d, "controle", 2, [])                    # > 1 h : arrêté
        self.assertEqual([c["code"] for c in constats_securite(d)[0]],
                         ["SEC_SURVEILLANCE_ARRETEE"])

    def test_constats_transmis_et_expliques(self):
        from core.surveillance import constats_securite
        d = tempfile.mkdtemp()
        self.ecrire(d, "controle", 0, [{"niveau": "BLOQUANT", "code": "SEC_PROCESSUS_TEMP",
                                        "message": "m", "nombre": 1, "exemples": ["pid 1"]}])
        self.ecrire(d, "antivirus", 0, [])
        c = constats_securite(d)[0]
        self.assertEqual([x["code"] for x in c], ["SEC_PROCESSUS_TEMP"])
        centre = CentreAlertes(os.path.join(d, "a.json"))
        centre.synchroniser("securite", "serveur", c)
        a = centre.lister("active")[0]
        self.assertEqual(a["categorie"], "technique")
        self.assertIn("/tmp/postgresql", a["explication"]["pourquoi"])

    def test_catalogue_securite_complet(self):
        import re
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "securite", "concorde_securite.py"), encoding="utf-8") as f:
            codes = set(re.findall(r'"(SEC_[A-Z_]+)"', f.read()))
        self.assertTrue(codes)
        self.assertEqual(sorted(codes - set(CATALOGUE)), [])
