# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Garde-fous de suppression des bases (ADR-0005).

La suppression d'une base CHEZ UN CLIENT est interdite et doit rester
impossible par programmation : ces tests le vérifient, y compris en
parcourant tout le code.
"""

import os
import re
import tempfile
import time
import unittest
from collections.abc import Collection, Iterator
from typing import Any, NoReturn

from core import bases_locales as bl
from core.odoo_source import ErreurSource, SourceXmlRpcOdoo17
from interface.serveur import Bases
from tests.outils import RACINE_DEPOT, CurseurSimule


class FausseConnexion:
    """Connexion PostgreSQL simulée qui enregistre chaque ordre SQL reçu."""

    def __init__(self) -> None:
        """Démarre sans aucun ordre SQL enregistré."""
        self.sql: list[str] = []

    def cursor(self) -> "CurseurEnregistreur":
        """Rend un curseur qui consigne ses ordres dans ``self.sql``."""
        return CurseurEnregistreur(self)


class CurseurPgSimule(CurseurSimule):
    """Faux curseur conforme à ``bases_locales.CurseurPg``.

    Rôle : base des doublures passées en ``connexion`` à bases_locales ;
    sans ligne lue et sans ligne touchée tant qu'une sous-classe ne dit
    pas autre chose.
    Usages : ``CurseurEnregistreur``, ``CurseurCles``.
    """

    rowcount = 0

    def execute(
        self, requete: str, parametres: tuple[object, ...] = ()
    ) -> None:
        """Ne fait rien : chaque sous-classe dit ce qu'elle simule."""

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Aucune ligne lue."""
        return []

    def fetchone(self) -> tuple[Any, ...] | None:
        """Aucune ligne lue."""
        return None


class CurseurEnregistreur(CurseurPgSimule):
    """Curseur simulé de ``FausseConnexion`` : n'exécute rien, consigne."""

    def __init__(self, connexion: FausseConnexion) -> None:
        """Rattache le curseur à la connexion qui garde les ordres."""
        self.connexion = connexion

    def execute(
        self, requete: str, parametres: tuple[object, ...] = ()
    ) -> None:
        """Consigne l'ordre SQL au lieu de l'exécuter."""
        self.connexion.sql.append(requete)


def fausse_sauvegarde(
    nom: str, dossier: str, journal: object | None = None
) -> str:
    """Simule un pg_dump réussi et rend le chemin de la sauvegarde."""
    return os.path.join(dossier, nom + "_test.dump")


def sauvegarde_ratee(
    nom: str, dossier: str, journal: object | None = None
) -> NoReturn:
    """Simule un pg_dump en panne : lève toujours RuntimeError."""
    raise RuntimeError("pg_dump en panne")


LOCALES = ["concorde", "concorde_test", "testalbhade"]


class TestHote(unittest.TestCase):
    """Seul un hôte PostgreSQL local autorise une suppression."""

    def setUp(self) -> None:
        """Mémorise PGHOST pour le rétablir après le test."""
        self.ancien = os.environ.get("PGHOST")

    def tearDown(self) -> None:
        """Rétablit PGHOST tel qu'avant le test."""
        if self.ancien is None:
            os.environ.pop("PGHOST", None)
        else:
            os.environ["PGHOST"] = self.ancien

    def test_hotes_locaux_acceptes(self) -> None:
        """Les hôtes locaux (socket, loopback, réseau Docker) sont acceptés."""
        for h in (
            "",
            "localhost",
            "127.0.0.1",
            "::1",
            "172.18.0.2",
            "/var/run/postgresql",
        ):
            bl.verifier_hote_local(h)

    def test_hotes_distants_refuses(self) -> None:
        """Tout hôte distant ou réseau privé hors Docker est refusé."""
        for h in (
            "client.odoo.com",
            "8.8.8.8",
            "10.0.0.5",
            "192.168.1.10",
            "51.15.0.1",
            "172.32.0.1",
        ):
            with self.assertRaises(bl.SuppressionInterdite, msg=h):
                bl.verifier_hote_local(h)

    def test_suppression_refusee_si_hote_distant(self) -> None:
        """PGHOST distant : suppression refusée sans aucun SQL envoyé."""
        os.environ["PGHOST"] = "db.client.example.com"
        cx = FausseConnexion()
        with self.assertRaises(bl.SuppressionInterdite):
            bl.supprimer(
                "testalbhade",
                "testalbhade",
                LOCALES,
                tempfile.mkdtemp(),
                connexion=cx,
                fonction_sauvegarde=fausse_sauvegarde,
            )
        self.assertEqual(cx.sql, [])


class TestGardeFous(unittest.TestCase):
    """Chaque garde-fou de suppression bloque avant tout SQL."""

    def setUp(self) -> None:
        """Hôte local (réseau Docker) et liste de bases protégées d'usine."""
        os.environ["PGHOST"] = "172.18.0.2"
        os.environ.pop("CONCORDE_BASES_PROTEGEES", None)

    def tenter(
        self,
        nom: str,
        confirmation: str | None = None,
        en_cours: Collection[str] = (),
        locales: Collection[str] = LOCALES,
    ) -> list[str]:
        """Tente de supprimer ``nom`` et rend les ordres SQL émis."""
        self.dernier_sql: list[str] = []
        cx = FausseConnexion()
        try:
            bl.supprimer(
                nom,
                nom if confirmation is None else confirmation,
                locales,
                tempfile.mkdtemp(),
                en_cours,
                connexion=cx,
                fonction_sauvegarde=fausse_sauvegarde,
            )
        finally:
            self.dernier_sql = cx.sql
        return cx.sql

    def refuse(
        self,
        nom: str,
        confirmation: str | None = None,
        en_cours: Collection[str] = (),
        locales: Collection[str] = LOCALES,
    ) -> None:
        """Vérifie que la suppression est refusée sans aucun SQL émis."""
        with self.assertRaises(bl.SuppressionInterdite):
            self.tenter(nom, confirmation, en_cours, locales)
        self.assertEqual(self.dernier_sql, [], "aucun SQL ne doit partir")

    def test_base_client_distante_interdite(self) -> None:
        """Une base distante (XML-RPC, URL) ne peut jamais être supprimée."""
        for nom in (
            "xmlrpc:1a2b3c4d",
            "https://client.odoo.com",
            "client.odoo.com/base",
        ):
            self.refuse(nom)

    def test_base_hors_liste_ou_systeme(self) -> None:
        """Base hors liste locale, système ou nom piégé : refusée."""
        self.refuse("azalplus_v2")  # pas une base Odoo 17 locale
        self.refuse("postgres", locales=LOCALES + ["postgres"])
        self.refuse(
            'x"; DROP DATABASE concorde; --',
            locales=['x"; DROP DATABASE concorde; --'],
        )

    def test_protegee(self) -> None:
        """Les bases protégées sont refusées ; la liste est réglable."""
        self.refuse("concorde")
        os.environ["CONCORDE_BASES_PROTEGEES"] = "testalbhade"
        self.refuse("testalbhade")
        self.assertTrue(
            self.tenter("concorde")
        )  # liste remplacée : concorde libérée

    def test_confirmation_et_tache_en_cours(self) -> None:
        """Confirmation inexacte ou tâche en cours : refus."""
        self.refuse("testalbhade", confirmation="testalbhad")
        self.refuse("testalbhade", confirmation="")
        self.refuse("testalbhade", en_cours={"testalbhade"})

    def test_suppression_autorisee(self) -> None:
        """Base locale confirmée : un seul DROP DATABASE est émis."""
        sql = self.tenter("testalbhade")
        self.assertEqual(sql, ['DROP DATABASE "testalbhade" WITH (FORCE)'])

    def test_rien_sans_sauvegarde(self) -> None:
        """Sauvegarde en échec : aucune suppression."""
        cx = FausseConnexion()
        with self.assertRaises(RuntimeError):
            bl.supprimer(
                "testalbhade",
                "testalbhade",
                LOCALES,
                tempfile.mkdtemp(),
                connexion=cx,
                fonction_sauvegarde=sauvegarde_ratee,
            )
        self.assertEqual(cx.sql, [])

    def test_reinitialisation_sans_sauvegarde(self) -> None:
        """Base de test réinitialisée depuis son modèle, sans pg_dump."""
        cx = FausseConnexion()
        chemin = bl.reinitialiser(
            "concorde_test",
            "concorde_test",
            LOCALES,
            {"concorde_test": "concorde_test_modele"},
            tempfile.mkdtemp(),
            connexion=cx,
            fonction_sauvegarde=sauvegarde_ratee,
        )
        self.assertIsNone(chemin)  # base de test : pg_dump jamais appelé
        self.assertEqual(
            cx.sql,
            [
                'DROP DATABASE "concorde_test" WITH (FORCE)',
                'CREATE DATABASE "concorde_test" '
                'TEMPLATE "concorde_test_modele"',
            ],
        )
        with self.assertRaises(
            bl.SuppressionInterdite
        ):  # copie client : pas de modèle
            bl.reinitialiser(
                "testalbhade",
                "testalbhade",
                LOCALES,
                {"concorde_test": "concorde_test_modele"},
                tempfile.mkdtemp(),
                connexion=FausseConnexion(),
                fonction_sauvegarde=fausse_sauvegarde,
            )

    def test_modele_invalide_refuse_avant_suppression(self) -> None:
        """Modèle non conforme refusé AVANT le DROP : rien n'est exécuté."""
        connexion_espion = FausseConnexion()
        modeles_pieges = {"concorde_test": 'x" ; DROP DATABASE "concorde'}
        with self.assertRaises(bl.SuppressionInterdite):
            bl.reinitialiser(
                "concorde_test",
                "concorde_test",
                LOCALES,
                modeles_pieges,
                tempfile.mkdtemp(),
                connexion=connexion_espion,
                fonction_sauvegarde=sauvegarde_ratee,
            )
        self.assertEqual(connexion_espion.sql, [])

    def test_suppression_base_de_test_sans_sauvegarde(self) -> None:
        """Une base de test (avec modèle) est supprimée sans sauvegarde."""
        cx = FausseConnexion()
        chemin = bl.supprimer(
            "concorde_test",
            "concorde_test",
            LOCALES,
            tempfile.mkdtemp(),
            connexion=cx,
            fonction_sauvegarde=sauvegarde_ratee,
            modeles={"concorde_test": "concorde_test_modele"},
        )
        self.assertIsNone(chemin)
        self.assertEqual(
            cx.sql, ['DROP DATABASE "concorde_test" WITH (FORCE)']
        )

    def test_copie_client_toujours_sauvegardee(self) -> None:
        """Une copie client (sans modèle) est toujours sauvegardée avant."""
        # même avec des modèles connus, une base SANS modèle est
        # sauvegardée d'abord
        cx = FausseConnexion()
        with self.assertRaises(RuntimeError):
            bl.supprimer(
                "testalbhade",
                "testalbhade",
                LOCALES,
                tempfile.mkdtemp(),
                connexion=cx,
                fonction_sauvegarde=sauvegarde_ratee,
                modeles={"concorde_test": "concorde_test_modele"},
            )
        self.assertEqual(cx.sql, [])


class TestSauvegardes(unittest.TestCase):
    """Rétention des sauvegardes pg_dump."""

    def test_purge_7_jours(self) -> None:
        """La purge retire les sauvegardes plus vieilles que la rétention."""
        os.environ.pop("CONCORDE_SAUVEGARDE_JOURS", None)
        d = tempfile.mkdtemp()
        vieux, recent = os.path.join(
            d, "a_20250101-000000.dump"
        ), os.path.join(d, "b_x.dump")
        for f in (vieux, recent):
            open(f, "w").close()
        os.utime(vieux, (time.time() - 8 * 86400,) * 2)
        os.utime(recent, (time.time() - 6 * 86400,) * 2)
        self.assertEqual(bl.purger_sauvegardes(d), ["a_20250101-000000.dump"])
        self.assertEqual(
            [s["fichier"] for s in bl.lister_sauvegardes(d)], ["b_x.dump"]
        )
        os.environ["CONCORDE_SAUVEGARDE_JOURS"] = "3"
        self.assertEqual(bl.purger_sauvegardes(d), ["b_x.dump"])  # réglable
        os.environ.pop("CONCORDE_SAUVEGARDE_JOURS")


class TestInterditParConstruction(unittest.TestCase):
    """Aucun code de CONCORDE ne parle au service de gestion des bases
    d'un Odoo, et seul core/bases_locales.py contient un DROP DATABASE."""

    MOTIFS_SERVICE_DB = (
        r"xmlrpc/2/db",
        r"/web/database",
        r"\bexp_drop\b",
        r"\bdrop_database\b",
        r"""['"]drop['"]""",
        r"""jsonrpc.*['"]db['"]""",
    )

    def fichiers(self) -> Iterator[str]:
        """Parcourt les fichiers .py, .js et .sh du code de CONCORDE."""
        for dossier in ("core", "interface", "injectors", "scripts", "deploy"):
            for racine, _, noms in os.walk(
                os.path.join(RACINE_DEPOT, dossier)
            ):
                if "__pycache__" in racine:
                    continue
                for n in noms:
                    if n.endswith((".py", ".js", ".sh")):
                        yield os.path.join(racine, n)

    def test_aucun_appel_au_service_de_bases_odoo(self) -> None:
        """Aucun fichier ne contacte le service de gestion des bases Odoo."""
        fautes = []
        for f in self.fichiers():
            with open(f, encoding="utf-8", errors="replace") as fh:
                texte = fh.read()
            for m in self.MOTIFS_SERVICE_DB:
                if re.search(m, texte, re.IGNORECASE):
                    fautes.append(
                        "%s : %s" % (os.path.relpath(f, RACINE_DEPOT), m)
                    )
        self.assertEqual(
            fautes,
            [],
            "Suppression de base distante possible : interdit (ADR-0005)",
        )

    def test_drop_database_seulement_dans_bases_locales(self) -> None:
        """DROP DATABASE n'apparaît que dans core/bases_locales.py."""
        fautes = []
        for f in self.fichiers():
            if f.endswith(os.path.join("core", "bases_locales.py")):
                continue
            with open(f, encoding="utf-8", errors="replace") as fh:
                if re.search(r"drop\s+database", fh.read(), re.IGNORECASE):
                    fautes.append(os.path.relpath(f, RACINE_DEPOT))
        self.assertEqual(fautes, [])

    def test_source_distante_en_lecture_seule(self) -> None:
        """La source XML-RPC n'autorise que des méthodes de lecture."""
        self.assertEqual(
            set(SourceXmlRpcOdoo17.METHODES_AUTORISEES),
            {"search_read", "read", "fields_get", "search_count"},
        )


class FausseBaseCles:
    """Connexion simulée sur une base qui a une clé API n° 4 « chatgpt »."""

    def __init__(self) -> None:
        """Base avec la seule clé n° 4 « chatgpt », rien de supprimé."""
        self.cles: dict[object, str] = {4: "chatgpt"}
        self.supprimees: list[object] = []

    def cursor(self) -> "CurseurCles":
        """Rend un curseur qui lit et supprime dans ``self.cles``."""
        return CurseurCles(self)


class CurseurCles(CurseurPgSimule):
    """Curseur simulé de ``FausseBaseCles`` (SELECT puis DELETE d'une clé)."""

    def __init__(self, connexion: FausseBaseCles) -> None:
        """Rattache le curseur à la base simulée, sans requête en cours."""
        self.connexion = connexion
        self.rowcount = 0
        self.dernier: tuple[str, tuple[object, ...]] = ("", ())

    def execute(
        self, requete: str, parametres: tuple[object, ...] = ()
    ) -> None:
        """Mémorise la requête ; un DELETE retire la clé visée."""
        self.dernier = (requete, parametres)
        if requete.startswith("DELETE"):
            cles = self.connexion.cles
            self.rowcount = 1 if parametres[0] in cles else 0
            self.connexion.supprimees.append(parametres[0])
            cles.pop(parametres[0], None)

    def fetchone(self) -> tuple[Any, ...] | None:
        """Rend le nom de la clé demandée par le dernier SELECT, ou None."""
        cles = self.connexion.cles
        identifiant_cle = self.dernier[1][0]
        return (cles[identifiant_cle],) if identifiant_cle in cles else None


class TestClesApi(unittest.TestCase):
    """Révocation d'une clé API d'une base Odoo 17 locale."""

    def setUp(self) -> None:
        """Hôte PostgreSQL local (réseau Docker)."""
        os.environ["PGHOST"] = "172.18.0.2"

    def test_revocation(self) -> None:
        """Une clé existante, confirmée par son nom, est révoquée."""
        cx = FausseBaseCles()
        self.assertEqual(
            bl.revoquer_cle_api(
                "concorde", 4, "chatgpt", LOCALES, connexion=cx
            ),
            "chatgpt",
        )
        self.assertEqual(cx.supprimees, [4])

    def test_refus(self) -> None:
        """Confirmation, clé, base distante ou hôte distant : refus."""
        for base, ident, conf in (
            ("concorde", 4, "chatgp"),  # confirmation
            ("concorde", 9, "x"),  # clé inconnue
            ("concorde", "4; DELETE", "chatgpt"),
            ("xmlrpc:abc", 4, "chatgpt"),  # base distante
            ("azalplus_v2", 4, "chatgpt"),
        ):  # pas Odoo 17 local
            cx = FausseBaseCles()
            with self.assertRaises(
                bl.SuppressionInterdite, msg=(base, ident, conf)
            ):
                bl.revoquer_cle_api(base, ident, conf, LOCALES, connexion=cx)
            self.assertEqual(cx.supprimees, [])
        os.environ["PGHOST"] = "client.example.com"
        with self.assertRaises(bl.SuppressionInterdite):
            bl.revoquer_cle_api(
                "concorde", 4, "chatgpt", LOCALES, connexion=FausseBaseCles()
            )


class TestClesDistantes(unittest.TestCase):
    """Clés API des Odoo distants, gardées en mémoire seulement."""

    def test_supprimer_puis_ressaisir(self) -> None:
        """Clé distante oubliée : la base ne s'ouvre plus sans ressaisie."""
        b = Bases()
        b._cache = (float("inf"), [])  # pas de PostgreSQL ici
        b._distants["xmlrpc:1"] = {
            "id": "xmlrpc:1",
            "nom": "client",
            "source": "xmlrpc",
            "url": "https://c.odoo.com",
            "utilisateur": "u",
            "cle": "secret",
        }
        self.assertTrue(b.lister()[0]["cle_presente"])
        self.assertNotIn("cle", b.lister()[0])  # la clé ne sort jamais
        self.assertTrue(b.supprimer_cle("xmlrpc:1"))
        self.assertFalse(b.lister()[0]["cle_presente"])
        with self.assertRaises(ErreurSource):
            b.ouvrir("xmlrpc:1")
        self.assertFalse(b.supprimer_cle("xmlrpc:inconnu"))


class TestNomsDeBases(unittest.TestCase):
    """Nom parlant des bases (« Albhades — production »)."""

    def annuaire(self, chemin: str) -> Bases:
        """Annuaire : une base locale, une distante, noms dans ``chemin``."""
        b = Bases()
        b._cache = (
            float("inf"),
            [
                {
                    "id": "sql:testalbhade",
                    "nom": "testalbhade",
                    "source": "sql",
                    "societe": "Albhades",
                }
            ],
        )
        b._distants["xmlrpc:1"] = {
            "id": "xmlrpc:1",
            "nom": "alb_alpha",
            "source": "xmlrpc",
            "url": "https://alb.odoo.com",
            "utilisateur": "u",
            "cle": "secret",
            "libelle": "Albhades — production",
        }
        b.charger_libelles(chemin)
        return b

    def test_nommer_retrouver_apres_redemarrage(self) -> None:
        """Le nom parlant d'une base survit à un redémarrage."""
        chemin = os.path.join(tempfile.mkdtemp(), "noms.json")
        b = self.annuaire(chemin)
        self.assertEqual(
            b.renommer("sql:testalbhade", "  Albhades —\ncopie du 14/10 "),
            "Albhades — copie du 14/10",
        )
        noms = {x["id"]: x["libelle"] for x in b.lister()}
        self.assertEqual(
            noms,
            {
                "sql:testalbhade": "Albhades — copie du 14/10",
                "xmlrpc:1": "Albhades — production",
            },
        )
        self.assertEqual(
            b.nom("sql:testalbhade"), "Albhades — copie du 14/10 (testalbhade)"
        )
        b2 = self.annuaire(chemin)  # « redémarrage »
        self.assertEqual(
            b2.lister()[0]["libelle"], "Albhades — copie du 14/10"
        )
        b2.renommer("sql:testalbhade", "")  # vide = retiré
        self.assertEqual(self.annuaire(chemin).lister()[0]["libelle"], "")

    def test_refus(self) -> None:
        """Nom inconnu ou trop long refusé ; la clé ne sort jamais."""
        b = self.annuaire(os.path.join(tempfile.mkdtemp(), "noms.json"))
        with self.assertRaises(ValueError):
            b.renommer("sql:inconnue", "x")
        with self.assertRaises(ValueError):
            b.renommer("sql:testalbhade", "x" * 61)
        b.renommer("xmlrpc:1", "Albhades — prod (nouveau nom)")
        self.assertEqual(
            b.lister()[1]["libelle"], "Albhades — prod (nouveau nom)"
        )
        self.assertNotIn("cle", b.lister()[1])  # la clé ne sort jamais


if __name__ == "__main__":
    unittest.main()
