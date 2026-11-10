# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Tests du contrôle de dématérialisation sur une base Odoo simulée."""

import base64
import fnmatch
import unittest
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from core.demat import (
    ALERTE,
    BLOQUANT,
    ControleDemat,
    centimes_odoo,
    pdf_contient_xml,
    rendu_html,
    rendu_texte,
    siren_valide,
    siret_valide,
    tva_fr_valide,
)
from tests.outils import Enregistrement

AUJ = date(2026, 11, 2)
SIREN_OK = "555555556"  # clé de Luhn valide
TVA_OK = "FR70555555556"

# Condition de domaine Odoo : (champ, opérateur, valeur).
ConditionDomaine = tuple[str, str, Any]
# Domaine Odoo : conditions et opérateurs préfixés ("|").
DomaineOdoo = Sequence[str | ConditionDomaine]


def _cond(rec: Enregistrement, cond: ConditionDomaine) -> bool:
    """Évalue une condition de domaine Odoo sur un enregistrement.

    Paramètres : ``rec`` enregistrement simulé ; ``cond`` condition
    ``(champ, opérateur, valeur)``.
    Retour : ``True`` si l'enregistrement satisfait la condition.
    Erreurs : ``AssertionError`` si l'opérateur n'est pas simulé.
    Usages : ``_eval``.
    """
    champ, op, val = cond
    v = rec.get(champ)
    v = v[0] if isinstance(v, list) and v and op in ("=", "in") else v
    if op == "=":
        return bool(v == val)
    if op == "!=":
        return bool(v != val)
    if op == "in":
        return v in val
    if op == ">=":
        return v is not None and v is not False and str(v) >= str(val)
    if op == "ilike":
        return str(val).lower() in str(v or "").lower()
    if op == "=ilike":
        return fnmatch.fnmatch(
            str(v or "").lower(), str(val).lower().replace("%", "*")
        )
    raise AssertionError(op)


def _eval(rec: Enregistrement, domaine: DomaineOdoo) -> bool:
    """Évalue un domaine Odoo minimal (notation polonaise, « | », ET).

    Paramètres : ``rec`` enregistrement simulé ; ``domaine`` domaine Odoo.
    Retour : ``True`` si l'enregistrement satisfait tout le domaine.
    Erreurs : ``AssertionError`` pour un opérateur logique non simulé.
    Usages : ``SourceSimulee.lire``.
    """

    def un(i: int) -> tuple[bool, int]:
        """Évalue le terme au rang ``i`` ; rend (valeur, rang suivant)."""
        t = domaine[i]
        if t == "|":
            a, i = un(i + 1)
            b, i = un(i)
            return a or b, i
        if isinstance(t, str):
            raise AssertionError(t)
        return _cond(rec, t), i + 1

    i, ok = 0, True
    while i < len(domaine):
        r, i = un(i)
        ok = ok and r
    return ok


class SourceSimulee:
    """Fausse base Odoo : dict modele -> liste d'enregistrements."""

    def __init__(
        self,
        donnees: dict[str, list[Enregistrement]],
        modules: Iterable[str] = ("account_edi_ubl_cii", "account_peppol"),
    ) -> None:
        """Mémorise les données simulées et les modules installés."""
        self.donnees = donnees
        self.modules = set(modules)
        self.appels: list[str] = []

    def champs(self, modele: str) -> dict[str, dict[str, Any]]:
        """Rend les champs du modèle (vide si le modèle est absent)."""
        recs = self.donnees.get(modele)
        if recs is None:
            return {}
        noms: set[str] = set()
        for r in recs:
            noms.update(r)
        return {n: {} for n in noms | {"id"}}

    def lire(
        self,
        modele: str,
        domaine: DomaineOdoo,
        champs: Iterable[str],
        offset: int = 0,
        limit: int | None = None,
        ordre: str = "id",
    ) -> list[Enregistrement]:
        """Rend les enregistrements filtrés par le domaine, paginés."""
        self.appels.append(modele)
        recs = [r for r in self.donnees.get(modele, []) if _eval(r, domaine)]
        if limit:
            fin = offset + limit
            recs = recs[offset:fin]
        else:
            recs = recs[offset:]
        return [
            {k: r.get(k, False) for k in list(champs) + ["id"]} for r in recs
        ]

    def modules_installes(self, noms: Iterable[str]) -> set[str]:
        """Rend, parmi ``noms``, les modules installés dans la base simulée."""
        return self.modules & set(noms)


def base(
    **surcharges: list[Enregistrement],
) -> dict[str, list[Enregistrement]]:
    """Construit une base simulée conforme, modèles remplaçables."""
    d: dict[str, list[Enregistrement]] = {
        "res.company": [
            {
                "id": 1,
                "name": "MASITH",
                "country_code": "FR",
                "vat": TVA_OK,
                "company_registry": SIREN_OK,
            }
        ],
        "res.partner": [
            {
                "id": 10,
                "name": "Client SA",
                "is_company": True,
                "country_code": "FR",
                "vat": TVA_OK,
                "company_registry": SIREN_OK,
            },
            {
                "id": 11,
                "name": "Client sans SIREN",
                "is_company": True,
                "country_code": "FR",
                "vat": "",
                "company_registry": "",
            },
            {
                "id": 20,
                "name": "Fournisseur",
                "is_company": True,
                "country_code": "FR",
                "vat": TVA_OK,
                "company_registry": SIREN_OK,
            },
        ],
        "account.move": [
            {
                "id": 1,
                "name": "FAC/2026/001",
                "move_type": "out_invoice",
                "state": "posted",
                "invoice_date": "2026-10-20",
                "amount_total": 120.0,
                "commercial_partner_id": [10, "Client SA"],
                "ubl_cii_xml_id": [500, "x.xml"],
                "peppol_move_state": "done",
                "is_move_sent": True,
            },
            {
                "id": 2,
                "name": "FAC/2026/002",
                "move_type": "out_invoice",
                "state": "posted",
                "invoice_date": "2026-10-21",
                "amount_total": 60.0,
                "commercial_partner_id": [10, "Client SA"],
                "ubl_cii_xml_id": False,
                "invoice_pdf_report_id": [601, "FAC2.pdf"],
                "peppol_move_state": "done",
                "is_move_sent": True,
            },
            {
                "id": 3,
                "name": "FACTU/2026/003",
                "move_type": "in_invoice",
                "state": "posted",
                "ref": "F-1",
                "invoice_date": "2026-10-10",
                "create_date": "2026-10-10 10:00:00",
                "amount_total": 50.0,
                "commercial_partner_id": [20, "Fournisseur"],
                "ubl_cii_xml_id": False,
            },
        ],
        "ir.attachment": [
            {
                "id": 601,
                "res_model": "account.move",
                "res_id": 2,
                "name": "FAC2.pdf",
                "mimetype": "application/pdf",
                "datas": base64.b64encode(
                    b"%PDF-1.7 ... /F (factur-x.xml) ..."
                ).decode(),
            },
            {
                "id": 602,
                "res_model": "account.move",
                "res_id": 3,
                "name": "facture.xml",
                "mimetype": "application/xml",
                "datas": "",
            },
        ],
        "account.edi.format": [
            {"id": 1, "name": "Factur-X", "code": "facturx_1_0_05"}
        ],
    }
    d.update(surcharges)
    return d


def lancer(
    donnees: dict[str, list[Enregistrement]], **kw: Any
) -> dict[str, Any]:
    """Exécute le contrôle sur 30 jours et rend le rapport en dictionnaire."""
    rapport_demat: dict[str, Any] = (
        ControleDemat(
            SourceSimulee(donnees, **kw.pop("src_kw", {})),
            jours=30,
            aujourd_hui=AUJ,
            **kw,
        )
        .executer()
        .en_dict()
    )
    return rapport_demat


def codes(rapport: dict[str, Any]) -> dict[str, Enregistrement]:
    """Indexe les anomalies du rapport par code."""
    return {a["code"]: a for a in rapport["anomalies"]}


class TestIdentifiants(unittest.TestCase):
    """Validation des identifiants d'entreprise et des montants."""

    def test_siren_siret_tva(self) -> None:
        """Vérifie la clé de contrôle des SIREN, SIRET et TVA françaises."""
        self.assertTrue(siren_valide(SIREN_OK))
        self.assertFalse(siren_valide("555555550"))
        self.assertTrue(siren_valide("356000000"))  # La Poste
        self.assertTrue(siret_valide("55555555600078"))
        self.assertFalse(siret_valide("55555555600070"))
        self.assertTrue(tva_fr_valide(TVA_OK))
        self.assertTrue(tva_fr_valide("fr 70 555555556"))
        self.assertFalse(tva_fr_valide("FR71555555556"))

    def test_centimes(self) -> None:
        """Vérifie la conversion exacte des montants Odoo en centimes."""
        self.assertEqual(centimes_odoo(0.1 + 0.2), 30)
        self.assertEqual(centimes_odoo(1234.56), 123456)
        self.assertEqual(centimes_odoo(False), 0)

    def test_pdf(self) -> None:
        """Vérifie la détection d'un XML Factur-X embarqué dans un PDF."""
        self.assertTrue(
            pdf_contient_xml(base64.b64encode(b"%PDF x Factur-X.xml"))
        )
        self.assertFalse(pdf_contient_xml(base64.b64encode(b"%PDF sans xml")))
        self.assertFalse(
            pdf_contient_xml(base64.b64encode(b"pas un pdf factur-x.xml"))
        )
        self.assertFalse(pdf_contient_xml("@@@"))


class TestControle(unittest.TestCase):
    """Contrôle complet de dématérialisation sur la base simulée."""

    def test_base_conforme(self) -> None:
        """Vérifie qu'une base complète est déclarée conforme."""
        r = lancer(base())
        self.assertEqual(r["statut"], "conforme", r["anomalies"])
        self.assertEqual(r["infos"]["emission_total"], 2)
        self.assertEqual(
            r["infos"]["emission_avec_xml"], 2
        )  # dont 1 via PDF Factur-X
        self.assertEqual(r["infos"]["reception_avec_xml"], 1)
        self.assertEqual(r["infos"]["reception_taux_electronique"], "100 %")
        self.assertEqual(len(r["empreinte"]), 64)

    def test_empreinte_deterministe(self) -> None:
        """Vérifie que deux contrôles identiques ont la même empreinte."""
        self.assertEqual(
            lancer(base())["empreinte"], lancer(base())["empreinte"]
        )

    def test_sans_inspection_pdf(self) -> None:
        """Vérifie qu'un PDF non inspecté compte comme facture sans XML."""
        r = lancer(base(), inspecter_pdf=False)
        self.assertEqual(r["infos"]["emission_avec_xml"], 1)
        self.assertIn("b2b_sans_xml", codes(r))

    def test_lecture_seule(self) -> None:
        """Vérifie que le contrôle n'écrit jamais dans la base."""
        src = SourceSimulee(base())
        ControleDemat(src, aujourd_hui=AUJ).executer()
        self.assertFalse(hasattr(src, "ecrire"))

    def test_societe_sans_siren_bloquant(self) -> None:
        """Vérifie qu'une société sans SIREN est bloquante."""
        d = base()
        d["res.company"] = [
            {
                "id": 1,
                "name": "X",
                "country_code": "FR",
                "vat": "",
                "company_registry": "",
            }
        ]
        r = lancer(d)
        self.assertEqual(r["statut"], "non_conforme")
        self.assertEqual(codes(r)["societe_sans_siren"]["niveau"], BLOQUANT)

    def test_aucun_module(self) -> None:
        """Vérifie qu'une base sans module de facture électronique bloque."""
        r = lancer(base(), src_kw={"modules": ()})
        self.assertEqual(codes(r)["aucun_module_einvoice"]["niveau"], BLOQUANT)

    def test_edi_et_peppol_en_erreur(self) -> None:
        """Vérifie que les erreurs EDI et Peppol sont bloquantes."""
        d = base()
        d["account.move"][0].update(
            edi_blocking_level="error",
            edi_error_message="<p>XML <b>invalide</b></p>",
        )
        d["account.move"][1].update(peppol_move_state="error")
        c = codes(lancer(d))
        self.assertEqual(c["edi_erreur"]["niveau"], BLOQUANT)
        self.assertIn("XML invalide", c["edi_erreur"]["exemples"][0])
        self.assertEqual(c["peppol_erreur"]["niveau"], BLOQUANT)

    def test_client_b2b_sans_siren(self) -> None:
        """Vérifie l'alerte sur une facture à un client sans SIREN."""
        d = base()
        d["account.move"][0]["commercial_partner_id"] = [
            11,
            "Client sans SIREN",
        ]
        c = codes(lancer(d))
        self.assertEqual(c["client_sans_siren"]["niveau"], ALERTE)

    def test_doublon_reception(self) -> None:
        """Vérifie la détection d'une facture fournisseur en double."""
        d = base()
        d["account.move"].append(
            dict(d["account.move"][2], id=4, name="FACTU/2026/004", ref="f-1 ")
        )
        c = codes(lancer(d))
        self.assertIn("doublon_probable", c)

    def test_reception_peu_electronique(self) -> None:
        """Vérifie l'alerte quand trop peu d'achats sont électroniques."""
        d = base()
        d["ir.attachment"] = d["ir.attachment"][:1]
        c = codes(lancer(d))
        self.assertEqual(c["reception_peu_electronique"]["niveau"], ALERTE)

    def test_brouillons_hors_emission(self) -> None:
        """Vérifie que les brouillons ne comptent pas dans l'émission."""
        d = base()
        d["account.move"].append(
            {
                "id": 9,
                "name": "/",
                "move_type": "out_invoice",
                "state": "draft",
                "invoice_date": "2026-10-25",
                "commercial_partner_id": [11, "x"],
            }
        )
        r = lancer(d)
        self.assertEqual(r["infos"]["emission_total"], 2)

    def test_troncature_signalee(self) -> None:
        """Vérifie qu'une analyse tronquée est signalée."""
        r = lancer(base(), max_factures=1)
        self.assertIn("analyse_tronquee", codes(r))

    def test_modele_edi_absent(self) -> None:
        """Vérifie qu'une base sans modèle de format EDI reste lisible."""
        d = base()
        del d["account.edi.format"]
        r = lancer(d)
        self.assertEqual(r["infos"]["formats_edi"], [])
        self.assertEqual(r["statut"], "conforme")

    def test_rendus(self) -> None:
        """Vérifie les rendus texte et HTML, balises échappées."""
        d = base()
        d["res.partner"][0]["name"] = "<script>"
        d["account.move"][1]["invoice_pdf_report_id"] = False
        r = lancer(d)
        self.assertIn("Résultat : À VÉRIFIER", rendu_texte(r))
        self.assertNotIn("<script>", rendu_html(r))
        self.assertIn("&lt;script&gt;", rendu_html(r))


if __name__ == "__main__":
    unittest.main()
