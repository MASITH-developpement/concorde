"""Lecture XML et XML-RPC protégées (core/xml_sur.py, defusedxml)."""

import unittest

from defusedxml import EntitiesForbidden

from core.xml_sur import lecteur_reponse_xmlrpc, lire_xml

XML_SAIN = b'<feuille><ligne n="1">Banque</ligne></feuille>'
XML_PIEGE = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE bombe [<!ENTITY a "aaaaaaaaaa">'
    b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
    b"<bombe>&b;</bombe>"
)


class TestLectureXmlSure(unittest.TestCase):
    """Un XML normal est lu ; un XML piégé est refusé."""

    def test_xml_sain_lu(self) -> None:
        """Un document ordinaire rend sa racine et ses valeurs."""
        racine = lire_xml(XML_SAIN)
        ligne = racine.find("ligne")
        self.assertIsNotNone(ligne)
        if ligne is not None:
            self.assertEqual(ligne.text, "Banque")
            self.assertEqual(ligne.get("n"), "1")

    def test_bombe_d_entites_refusee(self) -> None:
        """Une déclaration d'entités (bombe XML) lève EntitiesForbidden."""
        with self.assertRaises(EntitiesForbidden):
            lire_xml(XML_PIEGE)

    def test_xmlrpc_protege(self) -> None:
        """Le lecteur de réponses XML-RPC refuse aussi les entités."""
        lecteur, _ = lecteur_reponse_xmlrpc()
        with self.assertRaises(EntitiesForbidden):
            lecteur.feed(XML_PIEGE)


if __name__ == "__main__":
    unittest.main()
