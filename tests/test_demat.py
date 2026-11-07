# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
# Tests du contrôle de dématérialisation (core/demat.py) sur une base Odoo simulée.
import base64
import fnmatch
import unittest
from datetime import date

from core.demat import (ALERTE, BLOQUANT, ControleDemat, centimes_odoo,
                        pdf_contient_xml, rendu_html, rendu_texte, siren_valide,
                        siret_valide, tva_fr_valide)

AUJ = date(2026, 11, 2)
SIREN_OK = "732829320"          # clé de Luhn valide
TVA_OK = "FR44732829320"


def _cond(rec, cond):
    champ, op, val = cond
    v = rec.get(champ)
    v = v[0] if isinstance(v, list) and v and op in ("=", "in") else v
    if op == "=":
        return v == val
    if op == "!=":
        return v != val
    if op == "in":
        return v in val
    if op == ">=":
        return v is not None and v is not False and str(v) >= str(val)
    if op == "ilike":
        return str(val).lower() in str(v or "").lower()
    if op == "=ilike":
        return fnmatch.fnmatch(str(v or "").lower(), str(val).lower().replace("%", "*"))
    raise AssertionError(op)


def _eval(rec, domaine):
    """Évaluateur de domaine Odoo minimal (notation polonaise, '|' et ET implicite)."""
    def un(i):
        t = domaine[i]
        if t == "|":
            a, i = un(i + 1)
            b, i = un(i)
            return a or b, i
        return _cond(rec, t), i + 1
    i, ok = 0, True
    while i < len(domaine):
        r, i = un(i)
        ok = ok and r
    return ok


class SourceSimulee:
    """Fausse base Odoo : dict modele -> liste d'enregistrements."""

    def __init__(self, donnees, modules=("account_edi_ubl_cii", "account_peppol")):
        self.donnees = donnees
        self.modules = set(modules)
        self.appels = []

    def champs(self, modele):
        recs = self.donnees.get(modele)
        if recs is None:
            return {}
        noms = set()
        for r in recs:
            noms.update(r)
        return {n: {} for n in noms | {"id"}}

    def lire(self, modele, domaine, champs, offset=0, limit=None, ordre="id"):
        self.appels.append(modele)
        recs = [r for r in self.donnees.get(modele, []) if _eval(r, domaine)]
        recs = recs[offset:offset + limit] if limit else recs[offset:]
        return [{k: r.get(k, False) for k in list(champs) + ["id"]} for r in recs]

    def modules_installes(self, noms):
        return self.modules & set(noms)


def base(**surcharges):
    d = {
        "res.company": [{"id": 1, "name": "MASITH", "country_code": "FR",
                         "vat": TVA_OK, "company_registry": SIREN_OK}],
        "res.partner": [
            {"id": 10, "name": "Client SA", "is_company": True, "country_code": "FR",
             "vat": TVA_OK, "company_registry": SIREN_OK},
            {"id": 11, "name": "Client sans SIREN", "is_company": True,
             "country_code": "FR", "vat": "", "company_registry": ""},
            {"id": 20, "name": "Fournisseur", "is_company": True, "country_code": "FR",
             "vat": TVA_OK, "company_registry": SIREN_OK},
        ],
        "account.move": [
            {"id": 1, "name": "FAC/2026/001", "move_type": "out_invoice", "state": "posted",
             "invoice_date": "2026-10-20", "amount_total": 120.0,
             "commercial_partner_id": [10, "Client SA"], "ubl_cii_xml_id": [500, "x.xml"],
             "peppol_move_state": "done", "is_move_sent": True},
            {"id": 2, "name": "FAC/2026/002", "move_type": "out_invoice", "state": "posted",
             "invoice_date": "2026-10-21", "amount_total": 60.0,
             "commercial_partner_id": [10, "Client SA"], "ubl_cii_xml_id": False,
             "invoice_pdf_report_id": [601, "FAC2.pdf"],
             "peppol_move_state": "done", "is_move_sent": True},
            {"id": 3, "name": "FACTU/2026/003", "move_type": "in_invoice", "state": "posted",
             "ref": "F-1", "invoice_date": "2026-10-10", "create_date": "2026-10-10 10:00:00",
             "amount_total": 50.0, "commercial_partner_id": [20, "Fournisseur"],
             "ubl_cii_xml_id": False},
        ],
        "ir.attachment": [
            {"id": 601, "res_model": "account.move", "res_id": 2, "name": "FAC2.pdf",
             "mimetype": "application/pdf",
             "datas": base64.b64encode(b"%PDF-1.7 ... /F (factur-x.xml) ...").decode()},
            {"id": 602, "res_model": "account.move", "res_id": 3, "name": "facture.xml",
             "mimetype": "application/xml", "datas": ""},
        ],
        "account.edi.format": [{"id": 1, "name": "Factur-X", "code": "facturx_1_0_05"}],
    }
    d.update(surcharges)
    return d


def lancer(donnees, **kw):
    return ControleDemat(SourceSimulee(donnees, **kw.pop("src_kw", {})),
                         jours=30, aujourd_hui=AUJ, **kw).executer().en_dict()


def codes(rapport):
    return {a["code"]: a for a in rapport["anomalies"]}


class TestIdentifiants(unittest.TestCase):
    def test_siren_siret_tva(self):
        self.assertTrue(siren_valide(SIREN_OK))
        self.assertFalse(siren_valide("732829321"))
        self.assertTrue(siren_valide("356000000"))       # La Poste
        self.assertTrue(siret_valide("73282932000074"))
        self.assertFalse(siret_valide("73282932000075"))
        self.assertTrue(tva_fr_valide(TVA_OK))
        self.assertTrue(tva_fr_valide("fr 44 732829320"))
        self.assertFalse(tva_fr_valide("FR45732829320"))

    def test_centimes(self):
        self.assertEqual(centimes_odoo(0.1 + 0.2), 30)
        self.assertEqual(centimes_odoo(1234.56), 123456)
        self.assertEqual(centimes_odoo(False), 0)

    def test_pdf(self):
        self.assertTrue(pdf_contient_xml(base64.b64encode(b"%PDF x Factur-X.xml")))
        self.assertFalse(pdf_contient_xml(base64.b64encode(b"%PDF sans xml")))
        self.assertFalse(pdf_contient_xml(base64.b64encode(b"pas un pdf factur-x.xml")))
        self.assertFalse(pdf_contient_xml("@@@"))


class TestControle(unittest.TestCase):
    def test_base_conforme(self):
        r = lancer(base())
        self.assertEqual(r["statut"], "conforme", r["anomalies"])
        self.assertEqual(r["infos"]["emission_total"], 2)
        self.assertEqual(r["infos"]["emission_avec_xml"], 2)   # dont 1 via PDF Factur-X
        self.assertEqual(r["infos"]["reception_avec_xml"], 1)
        self.assertEqual(r["infos"]["reception_taux_electronique"], "100 %")
        self.assertEqual(len(r["empreinte"]), 64)

    def test_empreinte_deterministe(self):
        self.assertEqual(lancer(base())["empreinte"], lancer(base())["empreinte"])

    def test_sans_inspection_pdf(self):
        r = lancer(base(), inspecter_pdf=False)
        self.assertEqual(r["infos"]["emission_avec_xml"], 1)
        self.assertIn("b2b_sans_xml", codes(r))

    def test_lecture_seule(self):
        src = SourceSimulee(base())
        ControleDemat(src, aujourd_hui=AUJ).executer()
        self.assertFalse(hasattr(src, "ecrire"))

    def test_societe_sans_siren_bloquant(self):
        d = base()
        d["res.company"] = [{"id": 1, "name": "X", "country_code": "FR", "vat": "",
                             "company_registry": ""}]
        r = lancer(d)
        self.assertEqual(r["statut"], "non_conforme")
        self.assertEqual(codes(r)["societe_sans_siren"]["niveau"], BLOQUANT)

    def test_aucun_module(self):
        r = lancer(base(), src_kw={"modules": ()})
        self.assertEqual(codes(r)["aucun_module_einvoice"]["niveau"], BLOQUANT)

    def test_edi_et_peppol_en_erreur(self):
        d = base()
        d["account.move"][0].update(edi_blocking_level="error",
                                    edi_error_message="<p>XML <b>invalide</b></p>")
        d["account.move"][1].update(peppol_move_state="error")
        c = codes(lancer(d))
        self.assertEqual(c["edi_erreur"]["niveau"], BLOQUANT)
        self.assertIn("XML invalide", c["edi_erreur"]["exemples"][0])
        self.assertEqual(c["peppol_erreur"]["niveau"], BLOQUANT)

    def test_client_b2b_sans_siren(self):
        d = base()
        d["account.move"][0]["commercial_partner_id"] = [11, "Client sans SIREN"]
        c = codes(lancer(d))
        self.assertEqual(c["client_sans_siren"]["niveau"], ALERTE)

    def test_doublon_reception(self):
        d = base()
        d["account.move"].append(dict(d["account.move"][2], id=4, name="FACTU/2026/004",
                                      ref="f-1 "))
        c = codes(lancer(d))
        self.assertIn("doublon_probable", c)

    def test_reception_peu_electronique(self):
        d = base()
        d["ir.attachment"] = d["ir.attachment"][:1]
        c = codes(lancer(d))
        self.assertEqual(c["reception_peu_electronique"]["niveau"], ALERTE)

    def test_brouillons_hors_emission(self):
        d = base()
        d["account.move"].append({"id": 9, "name": "/", "move_type": "out_invoice",
                                  "state": "draft", "invoice_date": "2026-10-25",
                                  "commercial_partner_id": [11, "x"]})
        r = lancer(d)
        self.assertEqual(r["infos"]["emission_total"], 2)

    def test_troncature_signalee(self):
        r = lancer(base(), max_factures=1)
        self.assertIn("analyse_tronquee", codes(r))

    def test_modele_edi_absent(self):
        d = base()
        del d["account.edi.format"]
        r = lancer(d)
        self.assertEqual(r["infos"]["formats_edi"], [])
        self.assertEqual(r["statut"], "conforme")

    def test_rendus(self):
        d = base()
        d["res.partner"][0]["name"] = "<script>"
        d["account.move"][1]["invoice_pdf_report_id"] = False
        r = lancer(d)
        self.assertIn("Résultat : À VÉRIFIER", rendu_texte(r))
        self.assertNotIn("<script>", rendu_html(r))
        self.assertIn("&lt;script&gt;", rendu_html(r))


if __name__ == "__main__":
    unittest.main()
