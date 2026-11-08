# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Lecteur YAML minimal (core/yaml_min.py) : structures Python exactes.

Chaque test donne un texte YAML du sous-ensemble géré par CONCORDE et
vérifie la structure Python rendue, à l'identique (types compris).
"""

import os
import tempfile
import unittest

from core.yaml_min import ErreurYaml, ValeurYaml, charger_yaml, parse_yaml
from tests.outils import RACINE_DEPOT

# Chemin du vrai fichier de configuration à la racine du dépôt.
CHEMIN_CONFIGURATION = os.path.join(RACINE_DEPOT, "concorde.yaml")


def lire_lignes(*lignes_yaml: str) -> ValeurYaml:
    """Assemble des lignes YAML et les fait lire par ``parse_yaml``.

    Rôle : écrire chaque document de test ligne à ligne, indentation
    visible, sans recopier l'assemblage dans chaque test.
    Paramètres : ``lignes_yaml``, les lignes du document, sans fin de
    ligne.
    Retour : la structure Python rendue par ``parse_yaml``.
    Erreurs : aucune propre ; celles de ``parse_yaml``.
    Usages : tous les tests de ce fichier qui lisent un texte YAML.
    """
    return parse_yaml("\n".join(lignes_yaml))


def section(arbre: ValeurYaml, cle: str) -> dict[str, ValeurYaml]:
    """Rend la sous-table ``cle`` d'une table YAML, contrôle de type compris.

    Rôle : descendre dans la configuration lue en garantissant à chaque
    niveau qu'il s'agit bien d'une table (``dict``).
    Paramètres : ``arbre``, la table parente ; ``cle``, la clé cherchée.
    Retour : la sous-table associée à ``cle``.
    Erreurs : ``AssertionError`` si ``arbre`` ou la valeur trouvée n'est
    pas une table ; ``KeyError`` si la clé manque.
    Usages : ``TestVraieConfiguration``.
    """
    if not isinstance(arbre, dict):
        raise AssertionError(f"table attendue, obtenu {arbre!r}")
    sous_table = arbre[cle]
    if not isinstance(sous_table, dict):
        raise AssertionError(f"{cle} : table attendue")
    return sous_table


class TestScalaires(unittest.TestCase):
    """Conversion des valeurs : chaînes, entiers, booléens, valeur nulle."""

    def test_chaine_nue(self) -> None:
        """Une valeur sans guillemets reste une chaîne, espaces internes."""
        self.assertEqual(
            lire_lignes("slogan: La passerelle comptable"),
            {"slogan": "La passerelle comptable"},
        )

    def test_entiers(self) -> None:
        """Les entiers (positif, nul, négatif) deviennent des ``int``."""
        valeur_lue = lire_lignes("positif: 200", "nul: 0", "negatif: -15")
        self.assertEqual(
            valeur_lue, {"positif": 200, "nul": 0, "negatif": -15}
        )
        if not isinstance(valeur_lue, dict):
            self.fail("table attendue")
        self.assertIs(type(valeur_lue["positif"]), int)

    def test_decimal_reste_chaine(self) -> None:
        """Un décimal n'est jamais converti en float : il reste chaîne."""
        self.assertEqual(lire_lignes("taux: 1.5"), {"taux": "1.5"})

    def test_booleens_toutes_casses(self) -> None:
        """``true``/``false`` sont reconnus quelle que soit la casse."""
        self.assertEqual(
            lire_lignes("a: true", "b: False", "c: TRUE", "d: false"),
            {"a": True, "b": False, "c": True, "d": False},
        )

    def test_valeur_nulle_rend_chaine_vide(self) -> None:
        """``~``, ``null`` et ``NULL`` donnent la chaîne vide."""
        self.assertEqual(
            lire_lignes("a: ~", "b: null", "c: NULL"),
            {"a": "", "b": "", "c": ""},
        )

    def test_guillemets_doubles_et_simples(self) -> None:
        """Les guillemets sont retirés et le contenu n'est pas converti."""
        self.assertEqual(
            lire_lignes(
                'version: "1.0"',
                "native: '17'",
                'drapeau: "true"',
                'diese: "a # b"',
            ),
            {
                "version": "1.0",
                "native": "17",
                "drapeau": "true",
                "diese": "a # b",
            },
        )

    def test_deux_points_dans_la_valeur(self) -> None:
        """Seul le premier ``:`` sépare la clé : la suite reste valeur."""
        self.assertEqual(
            lire_lignes("adresse: http://127.0.0.1:8069"),
            {"adresse": "http://127.0.0.1:8069"},
        )

    def test_cle_entre_guillemets(self) -> None:
        """Les guillemets autour d'une clé sont retirés."""
        self.assertEqual(
            lire_lignes('"cle double": 1', "'cle simple': 2"),
            {"cle double": 1, "cle simple": 2},
        )


class TestStructure(unittest.TestCase):
    """Documents vides, commentaires, imbrication et listes."""

    def test_document_vide(self) -> None:
        """Un texte vide ou blanc rend une table vide."""
        self.assertEqual(parse_yaml(""), {})
        self.assertEqual(lire_lignes("", "   ", ""), {})

    def test_document_de_commentaires(self) -> None:
        """Un texte fait seulement de commentaires rend une table vide."""
        self.assertEqual(lire_lignes("# titre", "  # retrait"), {})

    def test_commentaires_et_lignes_vides_ignores(self) -> None:
        """Commentaires (même indentés) et lignes vides sont sautés."""
        self.assertEqual(
            lire_lignes(
                "# en-tête",
                "",
                "noyau:",
                "  # commentaire indenté",
                "",
                "  actif: true",
                "nom: CONCORDE",
            ),
            {"noyau": {"actif": True}, "nom": "CONCORDE"},
        )

    def test_fins_de_ligne_windows(self) -> None:
        """Les fins de ligne ``\\r\\n`` sont lues comme ``\\n``."""
        self.assertEqual(
            parse_yaml("a: 1\r\nb:\r\n  c: oui\r\n"),
            {"a": 1, "b": {"c": "oui"}},
        )

    def test_imbrication_par_indentation(self) -> None:
        """Les tables imbriquées suivent l'indentation, retour compris."""
        self.assertEqual(
            lire_lignes(
                "noyau:",
                "  guardian:",
                "    obligatoire: true",
                "    journal: /var/log",
                "  marceau:",
                "    actif: false",
                "mapping:",
                "  fichier: m.json",
            ),
            {
                "noyau": {
                    "guardian": {"obligatoire": True, "journal": "/var/log"},
                    "marceau": {"actif": False},
                },
                "mapping": {"fichier": "m.json"},
            },
        )

    def test_indentation_initiale(self) -> None:
        """Un document entièrement décalé est lu depuis son retrait."""
        self.assertEqual(
            lire_lignes("    a: 1", "    b: deux"), {"a": 1, "b": "deux"}
        )

    def test_cle_sans_valeur_rend_table_vide(self) -> None:
        """Une clé sans valeur ni bloc enfant vaut une table vide."""
        self.assertEqual(
            lire_lignes("vide:", "suite: 1", "fin:"),
            {"vide": {}, "suite": 1, "fin": {}},
        )

    def test_liste_de_scalaires(self) -> None:
        """Une liste de scalaires convertit chaque élément."""
        self.assertEqual(
            lire_lignes(
                "elements:",
                "  - texte",
                "  - 42",
                "  - true",
                '  - "a: b"',
                "  - 'c: d'",
            ),
            {"elements": ["texte", 42, True, "a: b", "c: d"]},
        )

    def test_liste_au_meme_retrait_que_la_cle(self) -> None:
        """Une liste non indentée sous sa clé lui appartient."""
        self.assertEqual(
            lire_lignes("etapes:", "- un", "- deux", "nom: x"),
            {"etapes": ["un", "deux"], "nom": "x"},
        )

    def test_liste_racine(self) -> None:
        """Un document qui commence par ``- `` est une liste."""
        self.assertEqual(lire_lignes("- 1", "- deux"), [1, "deux"])

    def test_liste_de_tables(self) -> None:
        """Les attributs indentés sous le tiret forment une table."""
        self.assertEqual(
            lire_lignes(
                "pipeline:",
                "  - nom: importer",
                "    module: core.fec",
                "    actif: true",
                "  - nom: lettrer",
                "    ordre: 2",
                "regles:",
                "  jamais_float: true",
            ),
            {
                "pipeline": [
                    {"nom": "importer", "module": "core.fec", "actif": True},
                    {"nom": "lettrer", "ordre": 2},
                ],
                "regles": {"jamais_float": True},
            },
        )

    def test_liste_de_tables_valeurs_vides(self) -> None:
        """Une clé vide, au tiret ou en attribut, vaut la chaîne vide."""
        self.assertEqual(
            lire_lignes("- nom:", "  option:", "- nom: b"),
            [{"nom": "", "option": ""}, {"nom": "b"}],
        )


class TestCommentairesEnFinDeLigne(unittest.TestCase):
    """Un ``#`` précédé d'un espace, hors guillemets, ouvre un commentaire."""

    def test_commentaire_retire_de_la_valeur(self) -> None:
        """Le commentaire en fin de ligne ne fait pas partie de la valeur."""
        self.assertEqual(
            lire_lignes("a: val # commentaire", "b: 3  # nombre"),
            {"a": "val", "b": 3},
        )

    def test_diese_entre_guillemets_ou_colle_reste_texte(self) -> None:
        """Un ``#`` entre guillemets ou collé au texte reste du texte."""
        self.assertEqual(
            lire_lignes(
                "a: 'x # y' # note",
                "b: c#d",
                "c: l'arrondi # note",
            ),
            {"a": "x # y", "b": "c#d", "c": "l'arrondi"},
        )

    def test_commentaire_apres_tiret(self) -> None:
        """Après un tiret, le commentaire n'est ni valeur ni clé."""
        self.assertEqual(lire_lignes("- x # c: d", "- 2 # n"), ["x", 2])


class TestListesEnLigne(unittest.TestCase):
    """Listes de scalaires écrites entre crochets sur une seule ligne."""

    def test_liste_de_scalaires(self) -> None:
        """Chaque élément est converti ; les guillemets sont retirés."""
        self.assertEqual(
            lire_lignes('versions: ["14", "15", 16, odoo, true]'),
            {"versions": ["14", "15", 16, "odoo", True]},
        )

    def test_liste_vide(self) -> None:
        """``[]`` et ``[ ]`` donnent une liste vide."""
        self.assertEqual(
            lire_lignes("a: []", "b: [ ]  # vide"), {"a": [], "b": []}
        )

    def test_virgule_et_crochet_entre_guillemets(self) -> None:
        """Virgule et crochet entre guillemets restent dans l'élément."""
        self.assertEqual(
            lire_lignes("a: [\"x, y\", '[z]', w]"),
            {"a": ["x, y", "[z]", "w"]},
        )

    def test_liste_en_ligne_comme_element(self) -> None:
        """Un élément de liste peut être une liste en ligne."""
        self.assertEqual(lire_lignes("- [1, 2]", "- 3"), [[1, 2], 3])

    def test_liste_entre_guillemets_reste_chaine(self) -> None:
        """Des crochets entre guillemets forment une simple chaîne."""
        self.assertEqual(lire_lignes('a: "[1, 2]"'), {"a": "[1, 2]"})

    def test_constructions_non_gerees(self) -> None:
        """Imbrication, table en ligne, crochet non fermé, élément vide."""
        for texte_yaml in (
            "a: [[1], 2]",
            "a: [1, {b: 2}]",
            "a: {b: 1}",
            "a: [1, 2",
            "a: [1, , 2]",
            "a: [1, 2,]",
        ):
            with self.subTest(texte_yaml=texte_yaml):
                with self.assertRaises(ErreurYaml):
                    parse_yaml(texte_yaml)


class TestListesImbriquees(unittest.TestCase):
    """Blocs (liste, table) imbriqués sous un élément de liste."""

    def test_liste_sous_un_element_de_liste(self) -> None:
        """Une liste sous un attribut d'élément lui appartient."""
        self.assertEqual(
            lire_lignes(
                "liste:",
                "  - nom: a",
                "    sous:",
                "      - x",
                "fin: 1",
            ),
            {"liste": [{"nom": "a", "sous": ["x"]}], "fin": 1},
        )

    def test_table_sous_un_element_de_liste(self) -> None:
        """Une table sous un attribut d'élément n'est pas aplatie."""
        self.assertEqual(
            lire_lignes("- nom: a", "  opts:", "    x: 1", "- nom: b"),
            [{"nom": "a", "opts": {"x": 1}}, {"nom": "b"}],
        )

    def test_liste_de_listes(self) -> None:
        """Un tiret suivi d'un tiret ouvre une liste imbriquée."""
        self.assertEqual(
            lire_lignes("- - a", "  - b", "- c"), [["a", "b"], "c"]
        )

    def test_tiret_seul(self) -> None:
        """Un tiret seul prend le bloc indenté qui suit, sinon ""."""
        self.assertEqual(
            lire_lignes("-", "  a: 1", "  b: 2", "-"), [{"a": 1, "b": 2}, ""]
        )

    def test_url_en_element_reste_scalaire(self) -> None:
        """Un ``:`` non suivi d'un espace ne fait pas une clé."""
        self.assertEqual(
            lire_lignes("- http://127.0.0.1:8069"), ["http://127.0.0.1:8069"]
        )

    def test_cle_entre_guillemets_avec_deux_points(self) -> None:
        """Le ``: `` d'une clé entre guillemets reste dans la clé."""
        self.assertEqual(lire_lignes("'a: b': 1"), {"a: b": 1})


class TestErreursExplicites(unittest.TestCase):
    """Une construction non gérée lève ``ErreurYaml``, ligne citée."""

    def verifier_erreur(self, numero_attendu: int, *lignes_yaml: str) -> None:
        """Vérifie que la lecture échoue en citant la bonne ligne.

        Rôle : contrôler à la fois le type d'erreur, l'attribut
        ``numero_ligne`` et sa présence dans le message.
        Paramètres : ``numero_attendu``, numéro (à partir de 1) de la ligne
        fautive ; ``lignes_yaml``, les lignes du document.
        Retour : aucun.
        Erreurs : échec du test si aucune ``ErreurYaml`` n'est levée ou si
        la ligne citée diffère.
        Usages : tous les tests de ``TestErreursExplicites``.
        """
        with self.assertRaises(ErreurYaml) as contexte_erreur:
            lire_lignes(*lignes_yaml)
        self.assertEqual(
            contexte_erreur.exception.numero_ligne, numero_attendu
        )
        self.assertIn(
            f"ligne {numero_attendu}", str(contexte_erreur.exception)
        )

    def test_erreur_est_une_value_error(self) -> None:
        """``ErreurYaml`` hérite de ``ValueError``."""
        self.assertTrue(issubclass(ErreurYaml, ValueError))

    def test_retrait_incoherent(self) -> None:
        """Une ligne plus indentée sous une valeur déjà donnée."""
        self.verifier_erreur(2, "a: 1", "  b: 2", "c: 3")

    def test_retrait_entre_deux_niveaux(self) -> None:
        """Une ligne revenant à un retrait jamais ouvert."""
        self.verifier_erreur(4, "a:", "    b: 1", "    c: 2", "  d: 3")

    def test_retrait_inferieur_au_premier(self) -> None:
        """Une ligne moins indentée que la première ligne du document."""
        self.verifier_erreur(3, "  a: 1", "", "b: 2")

    def test_liste_apres_cle_au_meme_niveau(self) -> None:
        """Un tiret là où une clé de la table est attendue."""
        self.verifier_erreur(2, "a: 1", "- x")

    def test_cle_apres_liste_racine(self) -> None:
        """Une clé au niveau d'une liste racine."""
        self.verifier_erreur(3, "- x", "# note", "b: 1")

    def test_cle_apres_liste_indentee(self) -> None:
        """Une clé au retrait d'une liste qui n'est pas une table."""
        self.verifier_erreur(3, "a:", "  - x", "  b: 1")

    def test_contenu_sous_un_scalaire_de_liste(self) -> None:
        """Un bloc indenté sous un élément scalaire de liste."""
        self.verifier_erreur(2, "- x", "  y: 1")

    def test_ligne_sans_cle(self) -> None:
        """Une ligne de table sans ``clé:`` n'est pas devinée."""
        self.verifier_erreur(2, "a: 1", "texte libre")

    def test_cle_entre_guillemets_non_fermee(self) -> None:
        """Une clé dont le guillemet n'est pas fermé n'est pas devinée."""
        self.verifier_erreur(1, "'a: 1")

    def test_numero_compte_lignes_vides_et_commentaires(self) -> None:
        """Le numéro cité est celui du texte d'origine."""
        self.verifier_erreur(3, "# titre", "", "a: [1", "b: {c: 1}")


class TestChargementFichier(unittest.TestCase):
    """Lecture d'un fichier YAML depuis le disque."""

    def test_fichier_utf8(self) -> None:
        """Un fichier UTF-8 est lu, accents compris."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin_fichier = os.path.join(dossier, "essai.yaml")
            with open(chemin_fichier, "w", encoding="utf-8") as fichier:
                fichier.write("marque: MARQUÉ DÉPOSÉ\nordre: 3\n")
            self.assertEqual(
                charger_yaml(chemin_fichier),
                {"marque": "MARQUÉ DÉPOSÉ", "ordre": 3},
            )

    def test_fichier_absent(self) -> None:
        """Un chemin inexistant lève ``FileNotFoundError``."""
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaises(FileNotFoundError):
                charger_yaml(os.path.join(dossier, "absent.yaml"))


class TestVraieConfiguration(unittest.TestCase):
    """Le vrai ``concorde.yaml`` du dépôt est lu avec les bonnes valeurs."""

    def setUp(self) -> None:
        """Charge la configuration réelle avant chaque test."""
        self.configuration = charger_yaml(CHEMIN_CONFIGURATION)

    def test_entete(self) -> None:
        """Les valeurs de premier niveau sont exactes et typées."""
        if not isinstance(self.configuration, dict):
            self.fail("concorde.yaml : table attendue")
        self.assertEqual(self.configuration["version"], "1.0")
        self.assertEqual(self.configuration["nom"], "CONCORDE")
        self.assertEqual(self.configuration["marque"], "MARQUÉ DÉPOSÉ")

    def test_noyau_guardian(self) -> None:
        """La section ``noyau.guardian`` est lue entièrement."""
        guardian = section(section(self.configuration, "noyau"), "guardian")
        self.assertEqual(guardian["journal"], "/var/concorde/guardian")
        self.assertIs(guardian["obligatoire"], True)
        self.assertEqual(guardian["self_check"], "bloquant")
        self.assertEqual(guardian["rate_limit"], "200_evenements_par_seconde")

    def test_pipeline(self) -> None:
        """Le pipeline est une liste de tables, étapes dans l'ordre."""
        if not isinstance(self.configuration, dict):
            self.fail("concorde.yaml : table attendue")
        pipeline = self.configuration["pipeline"]
        if not isinstance(pipeline, list):
            self.fail("pipeline : liste attendue")
        noms_etapes = [
            etape["nom"] for etape in pipeline if isinstance(etape, dict)
        ]
        self.assertEqual(
            noms_etapes,
            [
                "importer_fec",
                "verifier_equilibre",
                "mapper_comptes",
                "lettrer",
                "rapport",
            ],
        )
        self.assertEqual(
            pipeline[0],
            {
                "nom": "importer_fec",
                "module": "core.fec_parser",
                "fonction": "parse_fec",
                "description": (
                    "Import FEC avec idempotence et refus d'arrondi silencieux"
                ),
            },
        )

    def test_regles(self) -> None:
        """Les règles de montant gardent leurs types (entier, booléen)."""
        regles = section(self.configuration, "regles")
        self.assertEqual(regles["tolerance_concordance"], 0)
        self.assertIs(regles["jamais_float"], True)
        self.assertEqual(regles["montants"], "centimes_entier")

    def test_cible(self) -> None:
        """La section ``cible`` : versions en liste, chaînes exactes."""
        cible = section(self.configuration, "cible")
        self.assertEqual(
            cible["versions"], ["14", "15", "16", "17", "18", "19"]
        )
        self.assertEqual(cible["version_native"], "17")
        self.assertEqual(cible["conversion_chainee"], "14->15->16->17->18->19")
        self.assertEqual(cible["mode_defaut"], "dry-run")


if __name__ == "__main__":
    unittest.main()
