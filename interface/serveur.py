# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Interface web de CONCORDE — bibliothèque standard Python uniquement.

Choix d'architecture : ADR-0002 et ADR-0003.
Écoute sur 127.0.0.1 seulement : Caddy fournit le HTTPS devant.
Un seul utilisateur, mot de passe haché (interface/auth.py).

Configuration (variables d'environnement) :
  CONCORDE_UI_MDP           empreinte scrypt du mot de passe
                            (scripts/concorde_interface_mdp.py)
  CONCORDE_UI_PORT          port d'écoute (défaut 18090)
  CONCORDE_UI_DONNEES       dossier des résultats
                            (défaut /var/lib/concorde-interface)
  CONCORDE_UI_SURVEILLANCE  minutes entre deux passages de surveillance
                            (défaut 15, 0 = jamais)
  CONCORDE_ODOO_URL         Odoo à surveiller (défaut http://127.0.0.1:8017)
  PGHOST PGPORT PGUSER PGPASSWORD   accès PostgreSQL des bases Odoo 17 ;
                            à défaut, POSTGRES_USER / POSTGRES_PASSWORD
                            (deploy/.env).

API (JSON ; toute requête qui modifie exige l'en-tête X-Concorde: 1) :
  POST /api/connexion  /api/deconnexion          GET /api/etat
  GET  /api/bases
  POST /api/distants   DELETE /api/distants/<id>
  POST /api/taches     GET /api/taches
  GET  /api/taches/<id>?depuis=<n>
  GET  /api/taches/<id>/fichiers/<n>  /zip  /rapport.json
  GET  /api/taches/<id>/constats/<code>.csv
  GET  /api/comptes?base=…
  GET  /api/comptes/<code>/grand-livre?base=…
  GET  /api/ecritures/<id>?base=…
  GET  /api/alertes   GET /api/alertes/resume    POST /api/alertes/vue
  POST /api/surveillance                         GET /api/journal?depuis=<n>
  GET  /api/sauvegardes    GET /api/cles    POST /api/cles/revoquer
  GET  /api/comparer/choix?base_a=…&base_b=…
       (comptes et analytiques des deux bases)
  GET  /api/rapport?jour=…   POST /api/rapport   GET /api/rapport/export?jour=…
       (rapport du jour)
  POST /api/distants/<id>/cle   DELETE /api/distants/<id>/cle
  POST /api/bases/nom  {base_id, libelle}
       (nom parlant d'une base, vide = retiré)
  Écran Transferts (ADR-0011, interface/transferts.py) :
  GET  /api/logiciels   GET /api/connexions   POST /api/connexions
  POST /api/connexions/<id>/secret {champ, valeur}   (jamais renvoyé)
  POST /api/connexions/<id>/tester    DELETE /api/connexions/<id>
  POST /api/connexions/<id>/depot?nom=…   (corps = le FEC brut)
  POST /api/tables?nom=…                  (corps = la table brute)
  GET  /api/transferts   POST /api/transferts   GET /api/transferts/<id>
  GET  /api/transferts/<id>/fichier?chemin=…
  POST /api/transferts/<id>/feu-vert {destination, confirmation, sauvegarde_du}
  Écran Montée de version (ADR-0012, interface/montees.py) :
  GET  /api/montees   GET /api/montees/demandes/<id>
  GET  /api/montees/<id>/livraison
  POST /api/montees/depot?nom=…   (corps = la sauvegarde Odoo .zip)
  POST /api/montees {depot, arrivee}
  POST /api/montees/<id>/(circuit|feu-vert|nouvel-essai|livrer)
  Compléter SIRET et TVA (ADR-0013, interface/siret.py) :
  POST /api/siret {analyse, connexion}   GET /api/siret/<tâche>
  POST /api/siret/<tâche>/ecrire {cible, choix, confirmation}
  POST /api/siret/<tâche>/annuler {cible}
  (suppression / réinitialisation d'une base LOCALE : POST /api/taches avec
   action = supprimer_base | reinitialiser_base et confirmation = nom
   retapé — ADR-0005)
"""

import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import traceback
import uuid
import zipfile
from collections.abc import Callable, Iterable
from datetime import date, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from core import bases_locales
from core import rapport_jour
from core.comparaison import comparer_bases
from core.comptes import alertes_balance, grand_livre
from core.connecteurs.secrets import CHEMIN_SECRETS
from core.fichier_json import ecrire_json_atomique
from core.guardian import Guardian
from core.journal import Journal, duree_texte, nombre_texte
from core.marceau import Marceau
from core.odoo_source import (
    ETATS,
    ErreurSource,
    SourceSqlOdoo17,
    SourceXmlRpcOdoo17,
    transport_xmlrpc,
)
from core.passerelle import FORMATS, OBJETS, analyser_source, telecharger
from core.xml_sur import ProxyXmlRpc
from core.surveillance import (
    DOSSIER_SECURITE,
    CentreAlertes,
    comparer_instantanes,
    constats_securite,
    controles_techniques,
    depuis_24h,
)
from interface.auth import Sessions, verifier
from interface.montees import ERREURS_MONTEE_ECRAN, EcranMontees
from interface.siret import ERREURS_SIRET, EcranSiret
from interface.transferts import ERREURS_ECRAN, EcranTransferts

# Objet JSON (tâche, base, constat, corps de requête) : contenu dynamique,
# relu depuis le disque ou reçu du navigateur, d'où les valeurs Any.
ObjetJson = dict[str, Any]
# Paramètres d'URL (?cle=valeur), dernière valeur gardée.
ParametresUrl = dict[str, str]
# Travail d'une tâche branchée par un autre module (écran Transferts) :
# (tâche, journal, guardian) ; remplit tache["resultat"], lève en cas d'échec.
Travail = Callable[[ObjetJson, Journal, Guardian], None]
SourceOdoo = SourceSqlOdoo17 | SourceXmlRpcOdoo17

STATIQUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
COOKIE = "concorde_session"
CORPS_MAX = 64 * 1024
TACHES_SIMULTANEES = 2
LIMITE_GRAND_LIVRE = 500
_marceau = Marceau()


def _bases_ecriture_configurees() -> set[str]:
    """Bases locales dont CONCORDE a les identifiants d'écriture (API Odoo).

    Aujourd'hui : la base de test (CONCORDE_TEST_BASE / CONCORDE_TEST_MDP dans
    /etc/concorde/interface.env). Les mots de passe ne sortent jamais d'ici.
    """
    base = os.environ.get("CONCORDE_TEST_BASE")
    return {base} if base and os.environ.get("CONCORDE_TEST_MDP") else set()


def _json_defaut(valeur: object) -> str:
    """Conversion JSON des valeurs non natives : dates en ISO, sinon texte."""
    if isinstance(valeur, (date, datetime)):
        return valeur.isoformat()
    return str(valeur)


def _date(texte: str | None) -> date | None:
    """Date AAAA-MM-JJ, ou None si vide.

    Rôle : lire les dates de période saisies dans l'interface.
    Paramètres : texte, la date saisie (ou None / vide).
    Retour : la date, ou None si texte est vide.
    Erreurs : ValueError si la date est mal formée.
    Usages : Taches._executer_tache, Taches._comparer,
    Gestionnaire._params_tache, Gestionnaire._source_requete.
    """
    return date.fromisoformat(texte) if texte else None


def _jour_valide(jour: str) -> bool:
    """Vrai si jour est une date AAAA-MM-JJ.

    Rôle : valider le jour d'un rapport avant de le lire ou l'enregistrer.
    Paramètres : jour, le texte reçu.
    Retour : True si la date est lisible, False sinon.
    Erreurs : aucune.
    Usages : Gestionnaire.do_POST (/api/rapport), Gestionnaire._rapport.
    """
    try:
        date.fromisoformat(jour)
    except ValueError:
        return False
    return True


def _motif_erreur(exc: BaseException) -> str:
    """Texte « Type : message » d'une exception.

    Rôle : décrire une erreur pour l'écran ou le diagnostic.
    Paramètres : exc, l'exception attrapée.
    Retour : le texte, par exemple « ValueError : date invalide ».
    Erreurs : aucune.
    Usages : Bases._lister_sql (bases écartées), Taches._executer_tache.
    """
    return "%s : %s" % (type(exc).__name__, exc)


def _lire_json(chemin: str) -> Any:
    """Contenu d'un fichier JSON (UTF-8).

    Rôle : relire un fichier de données de l'interface.
    Paramètres : chemin, le fichier à lire.
    Retour : la valeur JSON décodée (dynamique, d'où Any).
    Erreurs : OSError si le fichier est illisible, ValueError si le JSON
    est invalide.
    Usages : Bases.charger_libelles, Taches._recharger,
    Surveillance._surveiller_base, Gestionnaire._rapport,
    Gestionnaire._constat_csv.
    """
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def _fichier_instantane(dossier: str, nom_base: str) -> str:
    """Chemin de la photo de surveillance d'une base.

    Rôle : nommer la photo d'une base sans caractère dangereux.
    Paramètres : dossier, celui des photos ; nom_base, la base Odoo.
    Retour : le chemin du fichier JSON de la photo.
    Erreurs : aucune.
    Usages : Taches._supprimer_base, Surveillance._surveiller_base.
    """
    return os.path.join(dossier, re.sub(r"[^\w-]", "_", nom_base) + ".json")


def _explication(constat: ObjetJson) -> dict[str, Any]:
    """Explication en clair d'un constat (assistant Marceau).

    Rôle : joindre à un constat son explication lisible.
    Paramètres : constat, avec ses clés « code » et « message ».
    Retour : l'explication rendue par Marceau.expliquer_alerte.
    Erreurs : celles de Marceau.expliquer_alerte.
    Usages : _constat_explique, Taches._comparer.
    """
    return _marceau.expliquer_alerte(constat["code"], constat["message"])


def _constat_explique(constat: ObjetJson) -> ObjetJson:
    """Copie d'un constat, sans sa liste d'éléments, avec son explication.

    Rôle : préparer un constat pour l'écran (allégé et expliqué).
    Paramètres : constat, le constat complet.
    Retour : la copie allégée, avec la clé « explication ».
    Erreurs : celles de _explication.
    Usages : Taches._executer_tache, Gestionnaire._balance.
    """
    return dict(
        {cle: valeur for cle, valeur in constat.items() if cle != "elements"},
        explication=_explication(constat),
    )


def _evenement_info(code: str, message: str, exemple: str) -> ObjetJson:
    """Constat d'information pour le centre d'alertes.

    Rôle : décrire une action faite (base supprimée, clé révoquée…).
    Paramètres : code, le code du constat ; message, son libellé ;
    exemple, le détail affiché.
    Retour : le constat, de niveau INFO et de nombre 1.
    Erreurs : aucune.
    Usages : Taches._supprimer_base, Gestionnaire.do_POST
    (/api/cles/revoquer).
    """
    return {
        "code": code,
        "niveau": "INFO",
        "nombre": 1,
        "message": message,
        "exemples": [exemple],
    }


def _noms_bases_locales(bases: "Bases", rafraichir: bool = False) -> list[str]:
    """Noms des bases de ce serveur (lues en SQL).

    Rôle : lister les bases locales pour les contrôles de suppression,
    de clés API et du centre d'alertes.
    Paramètres : bases, l'annuaire ; rafraichir, relire PostgreSQL.
    Retour : les noms des bases locales.
    Erreurs : celles de Bases.lister.
    Usages : Taches._supprimer_base, Gestionnaire.do_GET (/api/cles),
    Gestionnaire.do_POST (/api/cles/revoquer).
    """
    return [
        base["nom"]
        for base in bases.lister(rafraichir=rafraichir)
        if base["source"] == "sql"
    ]


def _disposition_piece_jointe(nom_fichier: str) -> str:
    """Valeur de l'en-tête Content-Disposition d'un téléchargement.

    Rôle : proposer au navigateur d'enregistrer la réponse sous ce nom.
    Paramètres : nom_fichier, le nom proposé.
    Retour : le texte de l'en-tête.
    Erreurs : aucune.
    Usages : Gestionnaire._fichier, _rapport, _zip, _constat_csv.
    """
    return 'attachment; filename="%s"' % nom_fichier


def _cookie_session(jeton: str | None) -> dict[str, str]:
    """En-tête Set-Cookie de la session.

    Rôle : poser le cookie de session (HttpOnly, Secure, SameSite=Strict).
    Paramètres : jeton, celui de la session ouverte ; None efface le cookie.
    Retour : l'en-tête à envoyer, sous forme {nom : valeur}.
    Erreurs : aucune.
    Usages : Gestionnaire._connexion, Gestionnaire.do_POST
    (/api/deconnexion).
    """
    if jeton is None:
        debut = "%s=; Path=/; Max-Age=0" % COOKIE
    else:
        debut = "%s=%s; Path=/" % (COOKIE, jeton)
    return {"Set-Cookie": debut + "; HttpOnly; Secure; SameSite=Strict"}


# ---------------------------------------------------------------------------
# Bases Odoo : bases SQL du serveur + Odoo distants (XML-RPC, clé en mémoire)
# ---------------------------------------------------------------------------


class Bases:
    """Annuaire des bases ; les clés API des Odoo distants restent en RAM."""

    DUREE_CACHE = 60

    def __init__(
        self, fabrique_sql: Callable[..., SourceSqlOdoo17] | None = None
    ) -> None:
        """Annuaire vide ; fabrique_sql ouvre une base SQL (remplaçable)."""
        self._fabrique_sql = fabrique_sql or SourceSqlOdoo17
        self._distants: dict[str, ObjetJson] = {}
        self._cache: tuple[float, list[ObjetJson]] = (0.0, [])
        self._verrou = threading.Lock()
        self.pg_ok, self.pg_erreur = True, ""
        # Bases du serveur écartées au dernier passage : {nom : motif}.
        self.bases_ignorees: dict[str, str] = {}
        # {id de base : nom parlant} — bases du serveur
        self._libelles: dict[str, str] = {}
        self._fichier_libelles: str | None = None

    # --- noms parlants -------------------------------------------------------
    LIBELLE_MAX = 60

    def charger_libelles(self, chemin: str) -> None:
        """Relit les noms parlants des bases du serveur (gardés sur disque)."""
        self._fichier_libelles = chemin
        if os.path.isfile(chemin):
            try:
                self._libelles = {
                    cle: str(valeur)
                    for cle, valeur in _lire_json(chemin).items()
                }
            except (OSError, ValueError):
                self._libelles = {}

    @classmethod
    def nettoyer_libelle(cls, libelle: object) -> str:
        """Nom parlant sur une ligne, espaces réduits.

        ValueError si le nom dépasse LIBELLE_MAX caractères.
        """
        texte = " ".join(
            str(libelle or "").split()
        )  # espaces et retours ligne
        if len(texte) > cls.LIBELLE_MAX:
            raise ValueError(
                "Nom trop long (%d caractères au plus)." % cls.LIBELLE_MAX
            )
        return texte

    def renommer(self, ident: str, libelle: object) -> str:
        """Donne (ou retire, si vide) un nom parlant ; rend le nom gardé."""
        texte = self.nettoyer_libelle(libelle)
        # hors verrou (lister le prend)
        connues = {base["id"] for base in self.lister()}
        if ident not in connues:
            raise ValueError("Base inconnue : %s" % ident)
        with self._verrou:
            if ident in self._distants:
                self._distants[ident]["libelle"] = texte
                return texte
            if texte:
                self._libelles[ident] = texte
            else:
                self._libelles.pop(ident, None)
            if self._fichier_libelles:
                ecrire_json_atomique(
                    self._fichier_libelles,
                    self._libelles,
                    ascii_seul=False,
                    retrait=1,
                )
        return texte

    def _lister_sql(self) -> list[ObjetJson]:
        """Bases Odoo 17 du serveur PostgreSQL, avec leur société."""
        try:
            import psycopg2
        except ImportError:
            self.pg_ok, self.pg_erreur = False, "psycopg2 n'est pas installé"
            return []
        try:
            connexion = psycopg2.connect(dbname="postgres", connect_timeout=5)
        except Exception as exc:
            self.pg_ok = False
            self.pg_erreur = "%s (PGHOST=%s)" % (
                str(exc).strip().splitlines()[0],
                os.environ.get("PGHOST", "?"),
            )
            return []
        self.pg_ok, self.pg_erreur = True, ""
        try:
            with connexion.cursor() as curseur:
                curseur.execute(
                    "SELECT datname FROM pg_database WHERE NOT datistemplate "
                    "AND datname <> 'postgres' ORDER BY datname"
                )
                noms: list[str] = [ligne[0] for ligne in curseur.fetchall()]
        finally:
            connexion.close()
        bases: list[ObjetJson] = []
        ignorees: dict[str, str] = {}
        for nom in noms:
            try:
                source = self._fabrique_sql(nom)
            except Exception as exc:
                # pas une base Odoo 17 (ou inaccessible) : écartée, motif gardé
                ignorees[nom] = _motif_erreur(exc)
                continue
            try:
                bases.append(self._description_sql(nom, source))
            except Exception as exc:
                # société illisible : base écartée, motif gardé
                ignorees[nom] = _motif_erreur(exc)
            finally:
                source.fermer()
        self.bases_ignorees = ignorees
        return bases

    @staticmethod
    def _description_sql(nom: str, source: SourceSqlOdoo17) -> ObjetJson:
        """Fiche d'une base du serveur (version Odoo, société)."""
        societe = source.societe_info()
        return {
            "id": "sql:" + nom,
            "nom": nom,
            "source": "sql",
            "version": source.version_serveur,
            "societe": societe["nom"],
            "devise": societe["devise"],
            "siren": societe["siren"],
        }

    def _modeles(self) -> dict[str, str]:
        """Bases modèles connues ; vide si PostgreSQL ne répond pas."""
        try:
            modeles: dict[str, str] = bases_locales.lister_modeles()
        except Exception:
            return {}
        return modeles

    def lister(self, rafraichir: bool = False) -> list[ObjetJson]:
        """Toutes les bases (serveur puis distantes), sans clé API.

        Rôle : décrire les bases proposées à l'écran et aux tâches.
        Paramètres : rafraichir, relire PostgreSQL sans attendre le cache.
        Retour : les fiches des bases (copies).
        Erreurs : celles de bases_locales.protegees.
        Usages : Bases.renommer, Bases.nom, Taches, Surveillance,
        Gestionnaire, _noms_bases_locales.
        """
        with self._verrou:
            instant_cache, sql = self._cache
            if (
                rafraichir
                or time.monotonic() - instant_cache > self.DUREE_CACHE
            ):
                sql = self._lister_sql()
                modeles = self._modeles() if sql else {}
                protegees = bases_locales.protegees()
                ecriture = _bases_ecriture_configurees()
                for base in sql:
                    base["modele"] = modeles.get(base["nom"])
                    base["protegee"] = base["nom"] in protegees
                    # Lecture : SQL en lecture seule. Écriture : toujours par
                    # l'API d'Odoo (ADR-0001), possible seulement si CONCORDE
                    # a les identifiants.
                    base["lecture"] = "SQL direct (lecture seule)"
                    base["ecriture"] = (
                        "API Odoo — identifiants configurés"
                        if base["nom"] in ecriture
                        else "API Odoo — à configurer"
                    )
                    base["ecriture_ok"] = base["nom"] in ecriture
                self._cache = (time.monotonic(), sql)
            distants = [
                dict(
                    {
                        cle: valeur
                        for cle, valeur in distant.items()
                        if cle != "cle"
                    },
                    cle_presente=bool(distant.get("cle")),
                    lecture="API Odoo (%s)" % distant["url"],
                    ecriture=(
                        "API Odoo — même clé "
                        "(étapes 7 et 8 de la migration)"
                    ),
                    ecriture_ok=bool(distant.get("cle")),
                )
                for distant in self._distants.values()
            ]
            sql = [
                dict(base, libelle=self._libelles.get(base["id"], ""))
                for base in sql
            ]
        return sql + distants

    def ajouter_distant(
        self,
        url: str,
        base: str,
        utilisateur: str,
        cle: str,
        libelle: object = "",
    ) -> str:
        """Ajoute un Odoo distant après un essai de connexion ; rend son id."""
        if not re.match(r"^https?://", url or ""):
            raise ErreurSource("URL invalide (http:// ou https://).")
        texte = self.nettoyer_libelle(libelle)
        source = SourceXmlRpcOdoo17(url, base, utilisateur, cle, timeout=30)
        societe = source.societe_info()
        ident = "xmlrpc:" + uuid.uuid4().hex[:8]
        with self._verrou:
            self._distants[ident] = {
                "id": ident,
                "nom": base,
                "source": "xmlrpc",
                "url": url.rstrip("/"),
                "utilisateur": utilisateur,
                "version": source.version_serveur,
                "societe": societe["nom"],
                "devise": societe["devise"],
                "siren": societe["siren"],
                "cle": cle,
                "libelle": texte or "%s (%s)" % (societe["nom"], base),
            }
        return ident

    def supprimer_cle(self, ident: str) -> bool:
        """Efface la clé API gardée ; la base reste listée, déconnectée."""
        with self._verrou:
            distant = self._distants.get(ident)
            if not distant:
                return False
            distant["cle"] = None
            return True

    def saisir_cle(self, ident: str, cle: str) -> None:
        """Remplace la clé API d'un Odoo distant après l'avoir essayée."""
        with self._verrou:
            distant = self._distants.get(ident)
        if not distant:
            raise ErreurSource("Base inconnue : %s" % ident)
        SourceXmlRpcOdoo17(
            distant["url"],
            distant["nom"],
            distant["utilisateur"],
            cle,
            timeout=30,
        )  # essai de connexion avec la nouvelle clé
        with self._verrou:
            distant["cle"] = cle

    def retirer_distant(self, ident: str) -> bool:
        """Retire un Odoo distant de l'annuaire (rien ne change chez lui)."""
        with self._verrou:
            return self._distants.pop(ident, None) is not None

    def ouvrir(self, ident: str, journal: Journal | None = None) -> SourceOdoo:
        """Ouvre la source de lecture d'une base (SQL ou XML-RPC).

        Rôle : donner accès aux données d'une base de l'annuaire.
        Paramètres : ident, l'id de la base ; journal, où raconter.
        Retour : la source ouverte (à fermer par l'appelant).
        Erreurs : ErreurSource si la base est inconnue ou sans clé API ;
        erreurs de connexion de la source.
        Usages : Taches, Surveillance, Gestionnaire.
        """
        if ident.startswith("sql:"):
            return self._fabrique_sql(ident[4:], journal=journal)
        with self._verrou:
            distant = self._distants.get(ident)
        if not distant:
            raise ErreurSource("Base inconnue : %s" % ident)
        if not distant.get("cle"):
            raise ErreurSource(
                "Clé API supprimée pour « %s » : ressaisissez-la dans l'écran "
                "Bases." % distant["nom"]
            )
        return SourceXmlRpcOdoo17(
            distant["url"],
            distant["nom"],
            distant["utilisateur"],
            distant["cle"],
            journal=journal,
        )

    def nom(self, ident: str) -> str:
        """Nom affiché d'une base : « nom parlant (nom) » ou son nom seul."""
        fiche = next(
            (base for base in self.lister() if base["id"] == ident), None
        )
        if not fiche:
            return ident
        nom_base: str = fiche["nom"]
        if fiche.get("libelle"):
            return "%s (%s)" % (fiche["libelle"], nom_base)
        return nom_base


# ---------------------------------------------------------------------------
# Tâches (analyse, téléchargement) : exécutées en arrière-plan, racontées
# ---------------------------------------------------------------------------


class Taches:
    """Tâches longues exécutées en arrière-plan, gardées sur disque."""

    def __init__(
        self,
        dossier: str,
        bases: Bases,
        centre: CentreAlertes | None = None,
    ) -> None:
        """Prépare le dossier des tâches et relit l'historique."""
        self.dossier = dossier
        self.bases = bases
        self.centre = centre
        self._taches: dict[str, ObjetJson] = {}
        self._journaux: dict[str, Journal] = {}
        self._verrou = threading.Lock()
        self._places = threading.Semaphore(TACHES_SIMULTANEES)
        self.travaux: dict[str, Travail] = {}
        os.makedirs(dossier, exist_ok=True)
        self._recharger()

    def _meta(self, ident: str) -> str:
        """Chemin du fichier tache.json d'une tâche."""
        return os.path.join(self.dossier, ident, "tache.json")

    def _recharger(self) -> None:
        """Historique : relit les tâches des sessions précédentes."""
        for nom in sorted(os.listdir(self.dossier)):
            chemin = self._meta(nom)
            if not os.path.isfile(chemin):
                continue
            try:
                tache = _lire_json(chemin)
            except (OSError, ValueError):
                continue  # fiche illisible : tâche absente de l'historique
            if tache.get("statut") in ("en_attente", "en_cours"):
                tache["statut"] = "interrompue"
                tache["erreur"] = "Service redémarré pendant la tâche."
            self._taches[tache["id"]] = tache

    def _sauver(self, tache: ObjetJson) -> None:
        """Enregistre la fiche d'une tâche (écriture atomique)."""
        os.makedirs(os.path.join(self.dossier, tache["id"]), exist_ok=True)
        ecrire_json_atomique(
            self._meta(tache["id"]),
            tache,
            ascii_seul=False,
            conversion=_json_defaut,
        )

    ACTIONS = {
        "analyser": "analyse",
        "telecharger": "téléchargement",
        "supprimer_base": "suppression",
        "reinitialiser_base": "réinitialisation",
        "comparer": "comparaison",
        "transfert": "transfert",
        "feu_vert": "feu vert",
        "siret_proposer": "propositions SIRET et TVA",
        "siret_ecrire": "écriture SIRET et TVA",
        "siret_annuler": "annulation SIRET et TVA",
    }
    # Actions sur une base de l'écran Bases (POST /api/taches).
    ACTIONS_BASE = (
        "analyser",
        "telecharger",
        "supprimer_base",
        "reinitialiser_base",
        "comparer",
    )

    def creer(
        self, action: str | None, base_id: str | None, params: ObjetJson
    ) -> str:
        """Crée une tâche et la lance en arrière-plan ; rend son id.

        Rôle : point d'entrée de POST /api/taches.
        Paramètres : action (clé de ACTIONS_BASE), base_id (id de la base),
        params (paramètres validés par Gestionnaire._params_tache).
        Retour : l'id de la tâche.
        Erreurs : ValueError si l'action ou une base est inconnue, ou si la
        suppression vise une base distante.
        Usages : Gestionnaire.do_POST, tests/test_interface.py.
        """
        if action is None or action not in self.ACTIONS_BASE:
            raise ValueError("Action inconnue : %s" % action)
        if action in ("supprimer_base", "reinitialiser_base") and not str(
            base_id
        ).startswith("sql:"):
            raise ValueError(
                "Seules les bases de ce serveur peuvent être supprimées ou "
                "réinitialisées. Une base client distante ne se supprime "
                "jamais depuis CONCORDE : utilisez « Retirer de CONCORDE »."
            )
        base = next(
            (fiche for fiche in self.bases.lister() if fiche["id"] == base_id),
            None,
        )
        if base is None:
            raise ValueError("Base inconnue : %s" % base_id)
        if action == "comparer" and not any(
            fiche["id"] == params.get("base_b")
            for fiche in self.bases.lister()
        ):
            raise ValueError("Base B inconnue : %s" % params.get("base_b"))
        return self.lancer(
            action, base_id, base["nom"], base.get("societe", ""), params
        )

    def lancer(
        self,
        action: str,
        base_id: str | None,
        nom: str,
        societe: str,
        params: ObjetJson,
    ) -> str:
        """Enregistre une tâche et la lance en arrière-plan ; rend son id.

        Rôle : un seul endroit qui crée la fiche, le journal et le fil
        d'exécution d'une tâche (limite de TACHES_SIMULTANEES comprise).
        Paramètres : action — clé de ACTIONS (pour une action hors
        ACTIONS_BASE, son travail doit être dans `travaux`) ; base_id —
        base visée ou None ; nom et societe — ce qu'affiche l'historique ;
        params — paramètres déjà validés.
        Retour : l'id de la tâche.
        Erreurs : ValueError si l'action est inconnue ou sans travail.
        Usages : creer, interface/transferts.py.
        """
        if action not in self.ACTIONS or (
            action not in self.ACTIONS_BASE and action not in self.travaux
        ):
            raise ValueError("Action inconnue : %s" % action)
        ident = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(
            3
        )
        tache: ObjetJson = {
            "id": ident,
            "action": action,
            "base_id": base_id,
            "base": nom,
            "societe": societe,
            "params": params,
            "statut": "en_attente",
            "cree_le": datetime.now().isoformat(timespec="seconds"),
            "duree_s": None,
            "erreur": None,
            "resultat": None,
            "fichiers": [],
            "journal": [],
        }
        journal = Journal()
        journal.dire(
            "Tâche créée : %s — %s" % (self.ACTIONS[action], nom),
            "etape",
        )
        with self._verrou:
            self._taches[ident] = tache
            self._journaux[ident] = journal
        self._sauver(tache)
        threading.Thread(
            target=self._executer, args=(tache, journal), daemon=True
        ).start()
        return ident

    def _executer(self, tache: ObjetJson, journal: Journal) -> None:
        """Attend une place libre puis exécute la tâche."""
        if not self._places.acquire(blocking=False):
            journal.dire(
                "Deux tâches tournent déjà : celle-ci attend son tour", "info"
            )
            self._places.acquire()
        try:
            self._executer_tache(tache, journal)
        finally:
            self._places.release()

    def _executer_tache(self, tache: ObjetJson, journal: Journal) -> None:
        """Exécute la tâche ; toute erreur est rendue à l'écran."""
        tache["statut"] = "en_cours"
        self._sauver(tache)
        debut = time.monotonic()
        guardian = Guardian()
        guardian.self_check()
        journal.dire(
            "Guardian : contrôle d'intégrité de démarrage réussi", "detail"
        )
        source: SourceOdoo | None = None
        try:
            parametres = tache["params"]
            if tache["action"] in self.travaux:
                self.travaux[tache["action"]](tache, journal, guardian)
                tache["statut"] = "terminee"
                return
            if tache["action"] in ("supprimer_base", "reinitialiser_base"):
                self._supprimer_base(tache, parametres, journal, guardian)
                tache["statut"] = "terminee"
                return
            if tache["action"] == "comparer":
                self._comparer(tache, parametres, journal, guardian)
                tache["statut"] = "terminee"
                return
            source = self.bases.ouvrir(tache["base_id"], journal=journal)
            if tache["action"] == "analyser":
                self._analyser(tache, parametres, source, journal, guardian)
            else:
                self._telecharger(tache, parametres, source, journal, guardian)
            tache["statut"] = "terminee"
        except Exception as exc:
            # erreur rendue telle quelle à l'écran (jamais muet)
            tache["statut"] = "echec"
            tache["erreur"] = _motif_erreur(exc)
            journal.dire("Échec : %s" % tache["erreur"], "erreur")
            traceback.print_exc()
        finally:
            if source is not None:
                source.fermer()
            tache["duree_s"] = round(time.monotonic() - debut, 1)
            tache["empreinte_guardian"] = guardian.empreinte_courante()
            if tache["statut"] == "terminee":
                journal.dire(
                    "Terminé en %s" % duree_texte(time.monotonic() - debut),
                    "ok",
                )
            tache["journal"] = journal.tout()
            self._sauver(tache)

    def _analyser(
        self,
        tache: ObjetJson,
        parametres: ObjetJson,
        source: SourceOdoo,
        journal: Journal,
        guardian: Guardian,
    ) -> None:
        """Analyse d'une base : rapport.json complet, résultat allégé."""
        rapport = analyser_source(
            source,
            _date(parametres.get("du")),
            _date(parametres.get("au")),
            bool(parametres.get("validees")),
            guardian,
            journal=journal,
        )
        chemin = os.path.join(self.dossier, tache["id"], "rapport.json")
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump(
                rapport, fichier, ensure_ascii=False, default=_json_defaut
            )
        # Résultat allégé (exemples) ; listes complètes dans rapport.json.
        tache["resultat"] = json.loads(
            json.dumps(
                {
                    cle: valeur
                    for cle, valeur in rapport.items()
                    if cle != "constats"
                },
                default=_json_defaut,
            )
        )
        tache["resultat"]["constats"] = [
            _constat_explique(constat) for constat in rapport["constats"]
        ]
        if (
            self.centre is not None
            and not parametres.get("du")
            and not parametres.get("au")
        ):
            for origine in ("analyse", "balance"):
                nouvelles, resolues = self.centre.synchroniser(
                    origine,
                    tache["base"],
                    [
                        constat
                        for constat in rapport["constats"]
                        if constat.get("origine", "analyse") == origine
                    ],
                )
                _raconter_centre(journal, nouvelles, resolues)

    def _telecharger(
        self,
        tache: ObjetJson,
        parametres: ObjetJson,
        source: SourceOdoo,
        journal: Journal,
        guardian: Guardian,
    ) -> None:
        """Export d'une base dans les formats choisis ; fichiers listés."""
        sortie = os.path.join(self.dossier, tache["id"], "fichiers")
        produits = telecharger(
            source,
            sortie,
            formats=parametres.get("formats") or ["xlsx"],
            objets=parametres.get("objets") or list(OBJETS),
            du=_date(parametres.get("du")),
            au=_date(parametres.get("au")),
            brouillons=bool(parametres.get("brouillons")),
            separateur="\t" if parametres.get("separateur") == "tab" else "|",
            encodage=parametres.get("encodage") or "iso-8859-15",
            guardian=guardian,
            journal=journal,
        )
        fichiers: list[ObjetJson] = []
        for produit in produits:
            for chemin_fichier in produit["fichiers"]:
                fichiers.append(
                    {
                        "n": len(fichiers),
                        "format": produit["format"],
                        "nom": os.path.relpath(chemin_fichier, sortie),
                        "chemin": chemin_fichier,
                        "taille": os.path.getsize(chemin_fichier),
                    }
                )
        tache["fichiers"] = fichiers
        tache["resultat"] = {
            "produits": [
                {
                    "format": produit["format"],
                    "resume": produit["resume"],
                    "alertes": produit["alertes"],
                }
                for produit in produits
            ]
        }
        journal.dire(
            "%d fichier(s) prêt(s) au téléchargement" % len(fichiers),
            "ok",
        )

    def _supprimer_base(
        self,
        tache: ObjetJson,
        parametres: ObjetJson,
        journal: Journal,
        guardian: Guardian,
    ) -> None:
        """Suppression / réinitialisation d'une base LOCALE (ADR-0005).

        Le contrôle et l'action sont faits par core/bases_locales.
        """
        nom = tache["base"]
        locales = _noms_bases_locales(self.bases, rafraichir=True)
        with self._verrou:
            en_cours = {
                autre["base"]
                for autre in self._taches.values()
                if autre["id"] != tache["id"]
                and autre["statut"] in ("en_attente", "en_cours")
            }
        dossier = os.path.join(self.dossier, "sauvegardes")
        # côté serveur : décide « base de test »
        modeles = bases_locales.lister_modeles()
        if tache["action"] == "reinitialiser_base":
            chemin = bases_locales.reinitialiser(
                nom,
                parametres.get("confirmation"),
                locales,
                modeles,
                dossier,
                en_cours,
                journal=journal,
            )
        else:
            chemin = bases_locales.supprimer(
                nom,
                parametres.get("confirmation"),
                locales,
                dossier,
                en_cours,
                journal=journal,
                modeles=modeles,
            )
        sauvegarde = os.path.basename(chemin) if chemin else None
        guardian.tracer(
            "bases", tache["action"], "%s sauvegarde=%s" % (nom, sauvegarde)
        )
        tache["resultat"] = {"sauvegarde": sauvegarde, "base": nom}
        self.bases.lister(rafraichir=True)
        if self.centre is not None:
            supprimee = tache["action"] == "supprimer_base"
            self.centre.evenements(
                nom,
                [
                    _evenement_info(
                        (
                            "BASE_SUPPRIMEE"
                            if supprimee
                            else "BASE_REINITIALISEE"
                        ),
                        (
                            "Base supprimée"
                            if supprimee
                            else "Base réinitialisée"
                        ),
                        (
                            "Sauvegarde : %s" % sauvegarde
                            if sauvegarde
                            else "Base de test : pas de sauvegarde"
                        ),
                    )
                ],
            )
            if supprimee:
                self.centre.tout_resoudre_absents(
                    set(_noms_bases_locales(self.bases))
                )
        if self.surveillance_dossier:
            photo = _fichier_instantane(self.surveillance_dossier, nom)
            if os.path.isfile(photo):
                os.remove(photo)  # la prochaine photo repart de zéro

    surveillance_dossier: str | None = None

    def _comparer(
        self,
        tache: ObjetJson,
        parametres: ObjetJson,
        journal: Journal,
        guardian: Guardian,
    ) -> None:
        """Vérifie, analyse et compare deux bases (lecture seule)."""
        source_a = self.bases.ouvrir(tache["base_id"], journal=journal)
        try:
            source_b = self.bases.ouvrir(parametres["base_b"], journal=journal)
        except Exception:
            source_a.fermer()
            raise
        try:
            etats = (
                ("posted", "draft")
                if parametres.get("brouillons")
                else ("posted",)
            )
            resultat = comparer_bases(
                source_a,
                source_b,
                _date(parametres.get("du")),
                _date(parametres.get("au")),
                etats,
                parametres.get("date_copie") or None,
                os.path.join(self.dossier, tache["id"], "fichiers"),
                journal,
                parametres.get("comptes") or None,
                parametres.get("analytiques") or None,
            )
        finally:
            source_a.fermer()
            source_b.fermer()
        guardian.tracer(
            "comparer",
            resultat["comparaison"]["statut"],
            resultat["comparaison"]["empreinte"],
        )
        for constat in resultat["comparaison"]["constats"]:
            constat["explication"] = _explication(constat)
        for cote in ("analyse_A", "analyse_B"):
            for constat in resultat[cote]["constats"]:
                constat["explication"] = _explication(constat)
        if resultat.get("fichier"):
            tache["fichiers"] = [
                {
                    "n": 0,
                    "format": "xlsx",
                    "nom": os.path.basename(resultat["fichier"]),
                    "chemin": resultat["fichier"],
                    "taille": os.path.getsize(resultat["fichier"]),
                }
            ]
            resultat["fichier"] = os.path.basename(resultat["fichier"])
        tache["base_b"] = self.bases.nom(parametres["base_b"])
        tache["resultat"] = json.loads(
            json.dumps(resultat, default=_json_defaut)
        )

    def lister(self) -> list[ObjetJson]:
        """Résumé des tâches, des plus récentes aux plus anciennes."""
        with self._verrou:
            taches = list(self._taches.values())
        taches.sort(key=lambda tache: tache["cree_le"], reverse=True)
        return [
            {
                cle: tache.get(cle)
                for cle in (
                    "id",
                    "action",
                    "base",
                    "societe",
                    "statut",
                    "cree_le",
                    "duree_s",
                    "erreur",
                    "params",
                )
            }
            for tache in taches
        ]

    def du_jour(self, jour: str) -> list[ObjetJson]:
        """Tâches créées ce jour-là (copies complètes, sans leur journal)."""
        with self._verrou:
            return [
                {
                    cle: valeur
                    for cle, valeur in tache.items()
                    if cle != "journal"
                }
                for tache in self._taches.values()
                if (tache.get("cree_le") or "")[:10] == jour
            ]

    def echecs_24h(self) -> list[tuple[str, str, str, str]]:
        """Tâches en échec depuis 24 h : (créée le, action, base, erreur)."""
        with self._verrou:
            taches = list(self._taches.values())
        return [
            (
                tache["cree_le"],
                tache["action"],
                tache["base"],
                tache.get("erreur") or "?",
            )
            for tache in taches
            if tache["statut"] == "echec" and depuis_24h(tache["cree_le"])
        ]

    def obtenir(self, ident: str, depuis: int = 0) -> ObjetJson | None:
        """Vue d'une tâche et de son journal à partir de l'index depuis."""
        with self._verrou:
            tache = self._taches.get(ident)
            journal = self._journaux.get(ident)
        if tache is None:
            return None
        vue = {
            cle: valeur for cle, valeur in tache.items() if cle != "journal"
        }
        vue["fichiers"] = [
            {cle: fichier[cle] for cle in ("n", "format", "nom", "taille")}
            for fichier in tache["fichiers"]
        ]
        if journal is not None:
            vue["journal"], vue["journal_suivant"] = journal.depuis(depuis)
        else:
            evenements = tache.get("journal") or []
            vue["journal"] = evenements[depuis:]
            vue["journal_suivant"] = len(evenements)
        return vue

    def fichier(self, ident: str, numero: int) -> str | None:
        """Chemin d'un fichier produit, s'il est enregistré dans la tâche."""
        with self._verrou:
            tache = self._taches.get(ident)
        if not tache:
            return None
        produit = next(
            (
                fichier
                for fichier in tache["fichiers"]
                if fichier["n"] == numero
            ),
            None,
        )
        if not produit:
            return None
        chemin = os.path.realpath(produit["chemin"])
        if not chemin.startswith(os.path.realpath(self.dossier) + os.sep):
            return None
        return chemin if os.path.isfile(chemin) else None

    def rapport(self, ident: str) -> str | None:
        """Chemin du rapport.json d'une analyse terminée, sinon None."""
        with self._verrou:
            tache = self._taches.get(ident)
        if (
            not tache
            or tache["action"] != "analyser"
            or tache["statut"] != "terminee"
        ):
            return None
        chemin = os.path.join(self.dossier, ident, "rapport.json")
        return chemin if os.path.isfile(chemin) else None


def _raconter_centre(
    journal: Journal,
    nouvelles: Iterable[str],
    resolues: Iterable[str],
    nom_base: str | None = None,
) -> None:
    """Raconte les alertes apparues et résolues au centre d'alertes.

    Rôle : rendre visibles dans le journal les changements d'alertes.
    Paramètres : journal, où raconter ; nouvelles et resolues, les messages
    rendus par CentreAlertes.synchroniser ; nom_base, préfixe des lignes
    (« base — nouvelle alerte : … ») si fourni.
    Retour : aucun.
    Erreurs : aucune.
    Usages : Taches._analyser, Surveillance.passer,
    Surveillance._surveiller_base.
    """
    if nom_base is None:
        prefixe, nouvelle, resolue = "", "Nouvelle alerte", "Alerte résolue"
    else:
        prefixe, nouvelle, resolue = (
            nom_base + " — ",
            "nouvelle alerte",
            "alerte résolue",
        )
    for message in nouvelles:
        journal.dire("%s%s : %s" % (prefixe, nouvelle, message), "alerte")
    for message in resolues:
        journal.dire("%s%s : %s" % (prefixe, resolue, message), "ok")


# ---------------------------------------------------------------------------
# Surveillance périodique : techniques, changements, anomalies par compte
# ---------------------------------------------------------------------------


class Surveillance:
    """Passages périodiques : serveur, sécurité, changements et balances."""

    def __init__(self, app: "Application", minutes: int) -> None:
        """Prépare le dossier des photos ; minutes = 0 : aucun passage auto."""
        self.app = app
        self.minutes = minutes
        self.dossier = os.path.join(app.dossier, "instantanes")
        os.makedirs(self.dossier, exist_ok=True)
        self._verrou = threading.Lock()
        self.dernier_passage: str | None = None
        self.en_cours = False

    def demarrer(self) -> None:
        """Lance la boucle périodique (si minutes > 0)."""
        if self.minutes > 0:
            threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self) -> None:
        """Passage toutes les minutes ; une erreur n'arrête pas la boucle."""
        time.sleep(10)  # laisse le service démarrer
        while True:
            try:
                self.passer()
            except Exception:
                traceback.print_exc()
            time.sleep(self.minutes * 60)

    def lancer_maintenant(self) -> bool:
        """Lance un passage immédiat ; False si un passage est en cours."""
        if self.en_cours:
            return False
        threading.Thread(target=self.passer, daemon=True).start()
        return True

    def _verifier_odoo(self) -> tuple[bool, str]:
        """Odoo répond-il (XML-RPC, 5 s au plus) ? Rend (succès, message)."""
        url = os.environ.get(
            "CONCORDE_ODOO_URL", "http://127.0.0.1:8017"
        ).rstrip("/")
        try:
            version_odoo = ProxyXmlRpc(
                url + "/xmlrpc/2/common", transport=transport_xmlrpc(url, 5)
            ).version()
            if not isinstance(version_odoo, dict):
                return False, "%s : réponse inattendue (%r)" % (
                    url,
                    version_odoo,
                )
            return True, "Odoo %s répond (%s)" % (
                version_odoo.get("server_version", "?"),
                url,
            )
        except Exception as exc:
            return False, "%s : %s" % (url, exc)

    def passer(self) -> None:
        """Un passage complet de surveillance (un seul à la fois)."""
        if not self._verrou.acquire(blocking=False):
            return
        self.en_cours = True
        journal = self.app.journal
        debut = time.monotonic()
        try:
            journal.dire("Surveillance : début du passage", "etape")
            bases = [
                base
                for base in self.app.bases.lister(rafraichir=True)
                if base["source"] == "sql"
            ]
            if self.app.bases.pg_ok:
                journal.dire(
                    "PostgreSQL joignable : %d base(s) Odoo 17" % len(bases),
                    "ok",
                )
            else:
                journal.dire(
                    "PostgreSQL injoignable : %s" % self.app.bases.pg_erreur,
                    "erreur",
                )
            odoo_ok, odoo_msg = self._verifier_odoo()
            journal.dire(
                odoo_msg if odoo_ok else "Odoo injoignable : %s" % odoo_msg,
                "ok" if odoo_ok else "erreur",
            )
            for base in bases:
                try:
                    self._surveiller_base(base, journal)
                except Exception as exc:
                    journal.dire(
                        "Base %s : surveillance impossible — %s"
                        % (base["nom"], exc),
                        "erreur",
                    )
            techniques = controles_techniques(
                self.app.bases.pg_ok,
                self.app.bases.pg_erreur,
                odoo_ok,
                odoo_msg,
                self.app.dossier,
                self.app.taches.echecs_24h(),
                [
                    echec
                    for echec in list(self.app.sessions.historique_echecs)
                    if depuis_24h(echec[0])
                ],
            )
            nouvelles, resolues = self.app.centre.synchroniser(
                "technique", "serveur", techniques.constats
            )
            _raconter_centre(journal, nouvelles, resolues)
            securite, infos_securite = constats_securite()
            nouvelles, resolues = self.app.centre.synchroniser(
                "securite", "serveur", securite
            )
            _raconter_centre(journal, nouvelles, resolues)
            for nom, infos in infos_securite.items():
                journal.dire(
                    "Sécurité — dernier %s : %s (%s)"
                    % (
                        (
                            "contrôle mineur / rançongiciel"
                            if nom == "controle"
                            else "antivirus ClamAV"
                        ),
                        (infos.get("statut") or "?").upper(),
                        infos["date"].replace("T", " "),
                    ),
                    "ok" if infos.get("statut") == "conforme" else "alerte",
                )
            journal.dire(
                "Disque : %s libre"
                % techniques.infos.get("disque_libre", "?"),
                "detail",
            )
            bases_locales.purger_sauvegardes(
                os.path.join(self.app.dossier, "sauvegardes"), journal=journal
            )
            resume = self.app.centre.resume()
            journal.dire(
                "Surveillance terminée en %s — %d alerte(s) active(s), "
                "%d à voir"
                % (
                    duree_texte(time.monotonic() - debut),
                    resume["actives"],
                    resume["non_vues"],
                ),
                "alerte" if resume["non_vues"] else "ok",
            )
            self.dernier_passage = datetime.now().isoformat(timespec="seconds")
        finally:
            self.en_cours = False
            self._verrou.release()

    def _surveiller_base(self, base: ObjetJson, journal: Journal) -> None:
        """Photo d'une base comparée à la précédente, puis sa balance."""
        # sans journal : on résume ici
        source = self.app.bases.ouvrir(base["id"])
        try:
            chemin = _fichier_instantane(self.dossier, base["nom"])
            ancien = None
            if os.path.isfile(chemin):
                ancien = _lire_json(chemin)
            nouveau = source.instantane()
            changements = comparer_instantanes(ancien, nouveau)
            presents = [
                constat
                for constat in changements.constats
                if constat["nombre"]
            ]
            if presents:
                self.app.centre.evenements(base["nom"], presents)
                for constat in presents:
                    journal.dire(
                        "%s — %s : %s"
                        % (
                            base["nom"],
                            constat["message"],
                            nombre_texte(constat["nombre"]),
                        ),
                        "alerte" if constat["niveau"] == "ALERTE" else "info",
                    )
            else:
                journal.dire(
                    "%s — aucun changement depuis le dernier passage"
                    % base["nom"],
                    "detail",
                )
            ecrire_json_atomique(chemin, nouveau)

            rapport_balance, _ = alertes_balance(
                source.balance(), source.balance_tiers()
            )
            nouvelles, resolues = self.app.centre.synchroniser(
                "balance", base["nom"], rapport_balance.constats
            )
            nombre_anomalies = sum(
                1
                for constat in rapport_balance.constats
                if constat["niveau"] in ("BLOQUANT", "ALERTE")
            )
            desequilibree = any(
                constat["code"] == "BALANCE_DESEQUILIBREE"
                for constat in rapport_balance.constats
            )
            journal.dire(
                "%s — balance : %s, %d anomalie(s) par compte"
                % (
                    base["nom"],
                    "DÉSÉQUILIBRÉE" if desequilibree else "équilibrée",
                    nombre_anomalies,
                ),
                "alerte" if nombre_anomalies else "ok",
            )
            _raconter_centre(journal, nouvelles, resolues, base["nom"])
        finally:
            source.fermer()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Application:
    """État partagé du service : sessions, bases, tâches, alertes."""

    def __init__(
        self,
        empreinte_mdp: str,
        dossier: str,
        bases: Bases | None = None,
        minutes_surveillance: int = 0,
        fichier_secrets: str = CHEMIN_SECRETS,
        montees: EcranMontees | None = None,
    ) -> None:
        """Assemble le service autour du dossier de données.

        Lève ValueError si CONCORDE_DEPOT_MAX_MO est invalide.
        """
        self.empreinte_mdp = empreinte_mdp
        self.dossier = dossier
        os.makedirs(dossier, exist_ok=True)
        self.sessions = Sessions()
        self.bases = bases or Bases()
        if hasattr(self.bases, "charger_libelles"):
            self.bases.charger_libelles(
                os.path.join(dossier, "noms_bases.json")
            )
        self.journal = Journal(taille_max=1000)
        self.centre = CentreAlertes(os.path.join(dossier, "alertes.json"))
        self.taches = Taches(dossier, self.bases, self.centre)
        self.surveillance = Surveillance(self, minutes_surveillance)
        self.taches.surveillance_dossier = self.surveillance.dossier
        self.transferts = EcranTransferts(
            dossier, self.taches, self.journal, fichier_secrets
        )
        self.montees = montees or EcranMontees(self.journal)
        self.siret = EcranSiret(
            self.taches, self.transferts.annuaire, self.journal
        )
        self.journal.dire("Service CONCORDE démarré", "ok")


class Gestionnaire(BaseHTTPRequestHandler):
    """Traitement d'une requête HTTP : fichiers statiques et API JSON."""

    server_version = "CONCORDE"
    sys_version = ""
    app: ClassVar[Application]  # injectée par creer_serveur()

    # --- outils --------------------------------------------------------------
    def log_message(self, format: str, *args: object) -> None:
        """Journal d'accès sur la sortie d'erreur, avec l'IP réelle."""
        sys.stderr.write("%s %s\n" % (self._ip(), format % args))

    def _ip(self) -> str:
        """Adresse du client (celle transmise par Caddy si en local)."""
        ip: str = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):  # derrière Caddy : IP réelle transmise
            transmise = self.headers.get("X-Forwarded-For", "")
            if transmise:
                return transmise.split(",")[-1].strip()
        return ip

    def _entetes_securite(self) -> None:
        """En-têtes de sécurité communs à toutes les réponses."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")

    def _envoyer(
        self,
        code: int,
        corps: bytes = b"",
        type_: str = "application/json; charset=utf-8",
        entetes: dict[str, str] | None = None,
    ) -> None:
        """Envoie une réponse complète (corps omis pour HEAD)."""
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self._entetes_securite()
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _json(
        self,
        code: int,
        donnees: object,
        entetes: dict[str, str] | None = None,
    ) -> None:
        """Envoie une réponse JSON."""
        self._envoyer(
            code,
            json.dumps(
                donnees, ensure_ascii=False, default=_json_defaut
            ).encode("utf-8"),
            entetes=entetes,
        )

    def _erreur(self, code: int, message: str) -> None:
        """Envoie une erreur JSON {"erreur": message}."""
        self._json(code, {"erreur": message})

    def _corps(self) -> ObjetJson:
        """Corps JSON de la requête (objet) ; ValueError si refusé."""
        taille = int(self.headers.get("Content-Length") or 0)
        if taille > CORPS_MAX:
            raise ValueError("Requête trop volumineuse.")
        brut = self.rfile.read(taille) if taille else b"{}"
        donnees = json.loads(brut.decode("utf-8") or "{}")
        if not isinstance(donnees, dict):
            raise ValueError("Objet JSON attendu.")
        return donnees

    def _requete(self) -> ParametresUrl:
        """Paramètres de l'URL (dernière valeur de chaque paramètre)."""
        return {
            cle: valeurs[-1]
            for cle, valeurs in parse_qs(urlparse(self.path).query).items()
        }

    def _jeton(self) -> str | None:
        """Jeton de session lu dans le cookie, ou None."""
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        return cookies[COOKIE].value if COOKIE in cookies else None

    def _connecte(self) -> bool:
        """Vrai si la requête porte une session valide."""
        return self.app.sessions.valide(self._jeton())

    def _fichier(
        self, chemin: str, nom: str, type_: str | None = None
    ) -> None:
        """Envoie un fichier en téléchargement, par blocs de 64 Kio."""
        type_ = (
            type_ or mimetypes.guess_type(nom)[0] or "application/octet-stream"
        )
        taille = os.path.getsize(chemin)
        self.send_response(200)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(taille))
        nom_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", nom)
        self.send_header(
            "Content-Disposition", _disposition_piece_jointe(nom_ascii)
        )
        self._entetes_securite()
        self.end_headers()
        with open(chemin, "rb") as fichier:
            while True:
                bloc = fichier.read(1 << 16)
                if not bloc:
                    break
                self.wfile.write(bloc)

    # --- routage -------------------------------------------------------------
    def do_HEAD(self) -> None:
        """HEAD : comme GET, sans le corps."""
        self.do_GET()

    def do_GET(self) -> None:
        """Routes GET : fichiers statiques et lectures de l'API."""
        chemin = urlparse(self.path).path
        if not chemin.startswith("/api/"):
            return self._statique(chemin)
        if chemin == "/api/etat":
            return self._json(200, {"connecte": self._connecte()})
        if chemin.startswith(
            ("/api/logiciels", "/api/connexions", "/api/transferts")
        ):
            if not self._connecte():
                return self._erreur(401, "Connexion requise.")
            return self._get_transferts(chemin)
        if chemin.startswith("/api/montees"):
            if not self._connecte():
                return self._erreur(401, "Connexion requise.")
            return self._get_montees(chemin)
        if re.fullmatch(r"/api/siret/[\w-]+", chemin):
            if not self._connecte():
                return self._erreur(401, "Connexion requise.")
            ident_siret = chemin.split("/")[3]
            return self._ecran(
                200,
                lambda: self.app.siret.propositions(ident_siret),
                ERREURS_SIRET,
            )
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        requete = self._requete()
        if chemin == "/api/bases":
            return self._json(
                200,
                {
                    "bases": self.app.bases.lister(
                        rafraichir="rafraichir" in requete
                    )
                },
            )
        if chemin == "/api/taches":
            return self._json(200, {"taches": self.app.taches.lister()})
        correspondance = re.fullmatch(r"/api/taches/([\w-]+)", chemin)
        if correspondance:
            tache = self.app.taches.obtenir(
                correspondance.group(1), int(requete.get("depuis") or 0)
            )
            return (
                self._json(200, tache)
                if tache
                else self._erreur(404, "Tâche inconnue.")
            )
        correspondance = re.fullmatch(
            r"/api/taches/([\w-]+)/fichiers/(\d+)", chemin
        )
        if correspondance:
            produit = self.app.taches.fichier(
                correspondance.group(1), int(correspondance.group(2))
            )
            if not produit:
                return self._erreur(404, "Fichier inconnu.")
            return self._fichier(produit, os.path.basename(produit))
        correspondance = re.fullmatch(r"/api/taches/([\w-]+)/zip", chemin)
        if correspondance:
            return self._zip(correspondance.group(1))
        correspondance = re.fullmatch(
            r"/api/taches/([\w-]+)/rapport\.json", chemin
        )
        if correspondance:
            rapport = self.app.taches.rapport(correspondance.group(1))
            if not rapport:
                return self._erreur(404, "Rapport indisponible.")
            return self._fichier(
                rapport, "concorde_analyse_%s.json" % correspondance.group(1)
            )
        correspondance = re.fullmatch(
            r"/api/taches/([\w-]+)/constats/([A-Z_]+)\.csv", chemin
        )
        if correspondance:
            return self._constat_csv(
                correspondance.group(1), correspondance.group(2)
            )
        if chemin == "/api/comptes":
            return self._balance(requete)
        correspondance = re.fullmatch(
            r"/api/comptes/([\w.-]+)/grand-livre", chemin
        )
        if correspondance:
            return self._grand_livre(correspondance.group(1), requete)
        correspondance = re.fullmatch(r"/api/ecritures/(\d+)", chemin)
        if correspondance:
            return self._ecriture(int(correspondance.group(1)), requete)
        if chemin == "/api/alertes":
            return self._json(
                200,
                {
                    "alertes": self.app.centre.lister(requete.get("statut")),
                    "dernier_passage": self.app.surveillance.dernier_passage,
                    "en_cours": self.app.surveillance.en_cours,
                },
            )
        if chemin == "/api/alertes/resume":
            return self._json(200, self.app.centre.resume())
        if chemin == "/api/cles":
            locales = _noms_bases_locales(self.app.bases)
            try:
                cles = bases_locales.lister_cles_api(locales)
            except Exception as exc:
                return self._erreur(
                    500, "Lecture des clés impossible : %s" % exc
                )
            return self._json(200, {"cles": cles})
        if chemin == "/api/rapport":
            return self._rapport(requete)
        if chemin == "/api/rapport/export":
            return self._rapport(requete, export=True)
        if chemin == "/api/comparer/choix":
            return self._choix_comparaison(requete)
        if chemin == "/api/sauvegardes":
            return self._json(
                200,
                {
                    "sauvegardes": bases_locales.lister_sauvegardes(
                        os.path.join(self.app.dossier, "sauvegardes")
                    ),
                    "retention_jours": bases_locales._retention(),
                },
            )
        if chemin == "/api/journal":
            evenements, suivant = self.app.journal.depuis(
                int(requete.get("depuis") or 0)
            )
            return self._json(200, {"journal": evenements, "suivant": suivant})
        return self._erreur(404, "Route inconnue.")

    def _verifier_origine(self) -> bool:
        """Anti-CSRF : en-tête personnalisé exigé.

        Un formulaire d'un site tiers ne peut pas poser cet en-tête.
        """
        return self.headers.get("X-Concorde") == "1"

    def do_POST(self) -> None:
        """Routes POST : connexion et actions qui modifient."""
        chemin = urlparse(self.path).path
        if not self._verifier_origine():
            return self._erreur(403, "Requête refusée.")
        if chemin in ("/api/tables", "/api/montees/depot") or re.fullmatch(
            r"/api/connexions/[\w-]+/depot", chemin
        ):
            if not self._connecte():
                return self._erreur(401, "Connexion requise.")
            return self._televerser(chemin)
        try:
            corps = self._corps()
        except (ValueError, UnicodeDecodeError) as exc:
            return self._erreur(400, str(exc))
        if chemin == "/api/connexion":
            return self._connexion(corps)
        if chemin == "/api/deconnexion":
            self.app.sessions.fermer(self._jeton())
            return self._json(200, {"ok": True}, entetes=_cookie_session(None))
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        if chemin == "/api/taches":
            try:
                params = self._params_tache(corps)
                ident = self.app.taches.creer(
                    corps.get("action"), corps.get("base_id"), params
                )
            except ValueError as exc:
                return self._erreur(400, str(exc))
            return self._json(201, {"id": ident})
        if chemin == "/api/distants":
            try:
                ident = self.app.bases.ajouter_distant(
                    corps.get("url", "").strip(),
                    corps.get("base", "").strip(),
                    corps.get("utilisateur", "").strip(),
                    corps.get("cle", ""),
                    corps.get("libelle", ""),
                )
            except Exception as exc:
                return self._erreur(400, "Connexion impossible : %s" % exc)
            self.app.journal.dire(
                "Odoo distant ajouté : %s" % corps.get("url"), "info"
            )
            return self._json(201, {"id": ident})
        if chemin == "/api/bases/nom":
            try:
                nom = self.app.bases.renommer(
                    str(corps.get("base_id") or ""), corps.get("libelle", "")
                )
            except ValueError as exc:
                return self._erreur(400, str(exc))
            self.app.journal.dire(
                "Base %s : nom « %s »"
                % (corps.get("base_id"), nom or "(retiré)"),
                "info",
            )
            return self._json(200, {"ok": True, "libelle": nom})
        correspondance = re.fullmatch(
            r"/api/distants/(xmlrpc:\w+)/cle", chemin
        )
        if correspondance:
            try:
                self.app.bases.saisir_cle(
                    correspondance.group(1), str(corps.get("cle") or "")
                )
            except Exception as exc:
                return self._erreur(400, "Clé refusée : %s" % exc)
            self.app.journal.dire(
                "Clé API ressaisie pour %s"
                % self.app.bases.nom(correspondance.group(1))
            )
            return self._json(200, {"ok": True})
        if chemin.startswith(("/api/connexions", "/api/transferts")):
            return self._post_transferts(chemin, corps)
        if chemin.startswith("/api/montees"):
            return self._post_montees(chemin, corps)
        if chemin.startswith("/api/siret"):
            return self._post_siret(chemin, corps)
        if chemin == "/api/cles/revoquer":
            return self._revoquer_cle(corps)
        if chemin == "/api/rapport":
            return self._enregistrer_rapport(corps)
        if chemin == "/api/alertes/vue":
            self.app.centre.marquer_vue(corps.get("id"))
            return self._json(200, self.app.centre.resume())
        if chemin == "/api/surveillance":
            lance = self.app.surveillance.lancer_maintenant()
            return self._json(
                202 if lance else 409,
                {
                    "lance": lance,
                    "message": (
                        "Passage lancé."
                        if lance
                        else "Un passage est déjà en cours."
                    ),
                },
            )
        return self._erreur(404, "Route inconnue.")

    def do_DELETE(self) -> None:
        """Routes DELETE : clé API et bases distantes."""
        chemin = urlparse(self.path).path
        if not self._verifier_origine():
            return self._erreur(403, "Requête refusée.")
        if not self._connecte():
            return self._erreur(401, "Connexion requise.")
        if re.fullmatch(r"/api/connexions/[\w-]+", chemin):
            ident_connexion = chemin.split("/")[3]
            return self._ecran(
                200, lambda: self.app.transferts.retirer(ident_connexion)
            )
        correspondance = re.fullmatch(
            r"/api/distants/(xmlrpc:\w+)/cle", chemin
        )
        if correspondance and self.app.bases.supprimer_cle(
            correspondance.group(1)
        ):
            self.app.journal.dire(
                "Clé API supprimée de CONCORDE pour %s (rien ne change chez "
                "le client)" % self.app.bases.nom(correspondance.group(1)),
                "info",
            )
            return self._json(200, {"ok": True})
        correspondance = re.fullmatch(r"/api/distants/(xmlrpc:\w+)", chemin)
        if correspondance and self.app.bases.retirer_distant(
            correspondance.group(1)
        ):
            self.app.journal.dire("Base distante retirée de CONCORDE", "info")
            return self._json(200, {"ok": True})
        return self._erreur(404, "Base inconnue.")

    # --- écran Transferts (ADR-0011) ----------------------------------------
    def _ecran(
        self,
        code: int,
        appel: Callable[[], object],
        refus: tuple[type[BaseException], ...] = ERREURS_ECRAN,
    ) -> None:
        """Exécute une action de l'écran Transferts et envoie sa réponse.

        Rôle : une seule traduction des refus en HTTP 400, cause comprise
        (jamais de secret : les erreurs n'en contiennent pas).
        Paramètres : code — code HTTP en cas de succès ; appel — l'action ;
        refus — erreurs rendues en 400 (celles de l'écran Transferts par
        défaut).
        Retour : aucun (réponse envoyée).
        Erreurs : aucune (chaque refus devient une réponse 400).
        Usages : _get_transferts, _post_transferts, _get_montees,
        _post_montees, _televerser, do_DELETE.
        """
        try:
            donnees = appel()
        except refus as exc:
            return self._erreur(400, str(exc))
        return self._json(code, donnees)

    def _get_transferts(self, chemin: str) -> None:
        """Lectures de l'écran Transferts."""
        ecran = self.app.transferts
        parties = chemin.split("/")  # ["", "api", "transferts", <id>, …]
        if chemin == "/api/logiciels":
            return self._ecran(200, ecran.logiciels)
        if chemin == "/api/connexions":
            return self._ecran(200, ecran.connexions)
        if chemin == "/api/transferts":
            return self._ecran(200, ecran.lister_transferts)
        if re.fullmatch(r"/api/transferts/[\w-]+", chemin):
            return self._ecran(200, lambda: ecran.detail_transfert(parties[3]))
        if re.fullmatch(r"/api/transferts/[\w-]+/fichier", chemin):
            try:
                fichier = ecran.chemin_fichier(
                    parties[3], self._requete().get("chemin", "")
                )
            except ERREURS_ECRAN as exc:
                return self._erreur(404, str(exc))
            return self._fichier(fichier, os.path.basename(fichier))
        return self._erreur(404, "Route inconnue.")

    def _post_transferts(self, chemin: str, corps: ObjetJson) -> None:
        """Actions de l'écran Transferts (corps JSON)."""
        ecran = self.app.transferts
        parties = chemin.split("/")  # ["", "api", <écran>, <id>, <action>]
        if chemin == "/api/connexions":
            return self._ecran(201, lambda: ecran.ajouter(corps))
        if chemin == "/api/transferts":
            return self._ecran(
                201, lambda: {"id": ecran.lancer_transfert(corps)}
            )
        if re.fullmatch(r"/api/connexions/[\w-]+/secret", chemin):
            return self._ecran(
                200,
                lambda: {"secrets": ecran.ecrire_secret(parties[3], corps)},
            )
        if re.fullmatch(r"/api/connexions/[\w-]+/tester", chemin):
            return self._ecran(200, lambda: ecran.tester(parties[3]))
        if re.fullmatch(r"/api/transferts/[\w-]+/feu-vert", chemin):
            return self._ecran(
                201,
                lambda: {"id": ecran.feu_vert(parties[3], corps, self._ip())},
            )
        return self._erreur(404, "Route inconnue.")

    # --- écran Montée de version (ADR-0012) ----------------------------------
    ROUTES_MONTEE = {
        "circuit": "circuit",
        "feu-vert": "feu_vert",
        "nouvel-essai": "nouvel_essai",
        "livrer": "livrer",
    }

    def _get_montees(self, chemin: str) -> None:
        """Lectures de l'écran Montée de version."""
        ecran = self.app.montees
        parties = chemin.split("/")  # ["", "api", "montees", <id>, …]
        if chemin == "/api/montees":
            return self._ecran(200, ecran.etat, ERREURS_MONTEE_ECRAN)
        if re.fullmatch(r"/api/montees/demandes/\w+", chemin):
            return self._ecran(
                200,
                lambda: ecran.resultat_demande(parties[4]),
                ERREURS_MONTEE_ECRAN,
            )
        if re.fullmatch(r"/api/montees/[\w-]+/livraison", chemin):
            try:
                fichier = ecran.livraison(parties[3])
            except ERREURS_MONTEE_ECRAN as exc:
                return self._erreur(404, str(exc))
            return self._fichier(
                fichier, os.path.basename(fichier), "application/zip"
            )
        return self._erreur(404, "Route inconnue.")

    def _post_montees(self, chemin: str, corps: ObjetJson) -> None:
        """Demandes au service de montée (corps JSON)."""
        ecran = self.app.montees
        parties = chemin.split("/")
        if chemin == "/api/montees":
            return self._ecran(
                201,
                lambda: ecran.demander("creer", corps, None, self._ip()),
                ERREURS_MONTEE_ECRAN,
            )
        if (
            re.fullmatch(r"/api/montees/[\w-]+/[\w-]+", chemin)
            and parties[4] in self.ROUTES_MONTEE
        ):
            return self._ecran(
                201,
                lambda: ecran.demander(
                    self.ROUTES_MONTEE[parties[4]],
                    corps,
                    parties[3],
                    self._ip(),
                ),
                ERREURS_MONTEE_ECRAN,
            )
        return self._erreur(404, "Route inconnue.")

    def _post_siret(self, chemin: str, corps: ObjetJson) -> None:
        """Compléter SIRET et TVA : propositions, écriture, annulation."""
        ecran = self.app.siret
        parties = chemin.split("/")  # ["", "api", "siret", <tâche>, <action>]
        if chemin == "/api/siret":
            return self._ecran(
                201,
                lambda: {"id": ecran.lancer_propositions(corps)},
                ERREURS_SIRET,
            )
        if re.fullmatch(r"/api/siret/[\w-]+/ecrire", chemin):
            return self._ecran(
                201,
                lambda: {
                    "id": ecran.lancer_ecriture(parties[3], corps, self._ip())
                },
                ERREURS_SIRET,
            )
        if re.fullmatch(r"/api/siret/[\w-]+/annuler", chemin):
            return self._ecran(
                201,
                lambda: {"id": ecran.lancer_annulation(parties[3], corps)},
                ERREURS_SIRET,
            )
        return self._erreur(404, "Route inconnue.")

    def _televerser(self, chemin: str) -> None:
        """Fichier envoyé brut : FEC déposé ou table de correspondance."""
        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._erreur(400, "Taille du fichier invalide.")
        nom = self._requete().get("nom", "")
        ecran = self.app.transferts
        if chemin == "/api/montees/depot":
            return self._ecran(
                201,
                lambda: self.app.montees.deposer(nom, self.rfile, taille),
                ERREURS_MONTEE_ECRAN,
            )
        if chemin == "/api/tables":
            return self._ecran(
                201, lambda: ecran.recevoir_table(nom, self.rfile, taille)
            )
        ident = chemin.split("/")[3]
        return self._ecran(
            201, lambda: ecran.deposer(ident, nom, self.rfile, taille)
        )

    # --- actions -------------------------------------------------------------
    def _connexion(self, corps: ObjetJson) -> None:
        """Contrôle du mot de passe, anti-force brute, ouverture de session."""
        ip = self._ip()
        if self.app.sessions.bloquee(ip):
            self.app.journal.dire(
                "Connexion bloquée (trop d'essais) depuis %s" % ip, "alerte"
            )
            return self._erreur(
                429, "Trop d'essais. Réessayez dans 15 minutes."
            )
        if not verifier(str(corps.get("mdp", "")), self.app.empreinte_mdp):
            self.app.sessions.echec(ip)
            self.app.journal.dire(
                "Mot de passe refusé depuis %s" % ip, "alerte"
            )
            time.sleep(0.5)
            return self._erreur(401, "Mot de passe incorrect.")
        jeton = self.app.sessions.ouvrir(ip)
        self.app.journal.dire("Connexion réussie depuis %s" % ip, "info")
        return self._json(200, {"ok": True}, entetes=_cookie_session(jeton))

    def _revoquer_cle(self, corps: ObjetJson) -> None:
        """Révoque une clé API d'une base locale (POST /api/cles/revoquer)."""
        locales = _noms_bases_locales(self.app.bases)
        base = str(corps.get("base") or "")
        try:
            nom = bases_locales.revoquer_cle_api(
                base,
                corps.get("id"),
                str(corps.get("confirmation") or ""),
                locales,
                journal=self.app.journal,
            )
        except bases_locales.SuppressionInterdite as exc:
            return self._erreur(400, str(exc))
        except Exception as exc:
            return self._erreur(500, "Révocation impossible : %s" % exc)
        self.app.centre.evenements(
            base,
            [
                _evenement_info(
                    "CLE_API_REVOQUEE", "Clé API révoquée", "Clé « %s »" % nom
                )
            ],
        )
        return self._json(200, {"ok": True, "cle": nom})

    def _enregistrer_rapport(self, corps: ObjetJson) -> None:
        """Enregistre les choix du rapport du jour (POST /api/rapport)."""
        jour = str(corps.get("jour") or "")
        if not _jour_valide(jour):
            return self._erreur(400, "Date invalide (AAAA-MM-JJ).")
        saisie = rapport_jour.nettoyer_saisie(corps)
        dossier = os.path.join(self.app.dossier, "rapports")
        os.makedirs(dossier, exist_ok=True)
        ecrire_json_atomique(
            os.path.join(dossier, jour + ".json"),
            saisie,
            ascii_seul=False,
            retrait=1,
        )
        self.app.journal.dire(
            "Rapport du %s enregistré (%d conclusion(s) masquée(s), "
            "%d ajout(s))"
            % (
                jour,
                sum(
                    1
                    for conclusion in saisie["conclusions"]
                    if not conclusion["visible"]
                ),
                len(saisie["ajouts"]),
            ),
            "info",
        )
        return self._rapport({"jour": jour})

    @staticmethod
    def _params_tache(corps: ObjetJson) -> ObjetJson:
        """Paramètres d'une tâche, validés ; ValueError si invalides."""
        params: ObjetJson = {}
        for cle in ("du", "au"):
            valeur = corps.get(cle) or None
            if valeur:
                _date(valeur)  # valide AAAA-MM-JJ (ValueError sinon)
            params[cle] = valeur
        if params["du"] and params["au"] and params["du"] > params["au"]:
            raise ValueError("La date de début est après la date de fin.")
        params["validees"] = bool(corps.get("validees"))
        params["brouillons"] = bool(corps.get("brouillons"))
        params["formats"] = [
            choix for choix in corps.get("formats") or [] if choix in FORMATS
        ]
        params["objets"] = [
            choix for choix in corps.get("objets") or [] if choix in OBJETS
        ]
        if corps.get("action") == "telecharger" and not params["formats"]:
            raise ValueError("Choisissez au moins un format.")
        if corps.get("action") == "telecharger" and not params["objets"]:
            raise ValueError("Choisissez au moins un type de données.")
        params["separateur"] = (
            "tab" if corps.get("separateur") == "tab" else "pipe"
        )
        params["encodage"] = (
            "utf-8" if corps.get("encodage") == "utf-8" else "iso-8859-15"
        )
        if corps.get("action") in ("supprimer_base", "reinitialiser_base"):
            params["confirmation"] = str(corps.get("confirmation") or "")
        if corps.get("action") == "comparer":
            params["base_b"] = str(corps.get("base_id_b") or "")
            if not params["base_b"] or params["base_b"] == corps.get(
                "base_id"
            ):
                raise ValueError("Choisissez deux bases différentes.")
            date_copie = (corps.get("date_copie") or "").strip()
            if date_copie:
                # ValueError si la date est invalide
                datetime.fromisoformat(date_copie)
            params["date_copie"] = date_copie
            for cle in ("comptes", "analytiques"):
                liste = corps.get(cle) or []
                if not isinstance(liste, list) or len(liste) > 5000:
                    raise ValueError("Liste « %s » invalide." % cle)
                params[cle] = sorted(
                    {
                        str(element).strip()[:120]
                        for element in liste
                        if str(element).strip()
                    }
                )
        return params

    def _source_requete(
        self, requete: ParametresUrl
    ) -> tuple[SourceOdoo, date | None, date | None, tuple[str, ...]]:
        """Ouvre la base demandée (?base=…) avec les filtres communs.

        Rôle : préparer les lectures de balance, grand livre et écriture.
        Paramètres : requete, les paramètres d'URL (base, du, au, brouillons).
        Retour : (source ouverte, début, fin, états d'écriture lus).
        Erreurs : ValueError si la base est inconnue ou une date invalide.
        Usages : Gestionnaire._balance, _grand_livre, _ecriture.
        """
        base = requete.get("base") or ""
        if not any(fiche["id"] == base for fiche in self.app.bases.lister()):
            raise ValueError("Base inconnue.")
        debut, fin = _date(requete.get("du")), _date(requete.get("au"))
        etats: tuple[str, ...] = (
            ("posted", "draft")
            if requete.get("brouillons") == "1"
            else ("posted",)
        )
        return self.app.bases.ouvrir(base), debut, fin, etats

    def _rapport(self, requete: ParametresUrl, export: bool = False) -> None:
        """Rapport du jour : automatique + choix enregistrés.

        export = page HTML imprimable, proposée en téléchargement.
        """
        jour = requete.get("jour") or date.today().isoformat()
        if not _jour_valide(jour):
            return self._erreur(400, "Date invalide (AAAA-MM-JJ).")
        securite: ObjetJson = {}
        for nom in ("controle", "antivirus"):
            chemin = os.path.join(DOSSIER_SECURITE, nom + ".json")
            try:
                securite[nom] = _lire_json(chemin)
            except (OSError, ValueError):
                # contrôle pas encore passé ou fichier illisible : la
                # rubrique reste vide dans le rapport
                continue
        automatique = rapport_jour.construire(
            jour,
            self.app.centre.lister(),
            self.app.taches.du_jour(jour),
            securite,
        )
        enregistre = None
        chemin = os.path.join(self.app.dossier, "rapports", jour + ".json")
        if os.path.isfile(chemin):
            enregistre = _lire_json(chemin)
        rapport = rapport_jour.fusionner(automatique, enregistre)
        if not export:
            return self._json(200, rapport)
        corps = rapport_jour.rendu_html(rapport).encode("utf-8")
        self._envoyer(
            200,
            corps,
            "text/html; charset=utf-8",
            {
                "Content-Disposition": _disposition_piece_jointe(
                    "concorde_rapport_%s.html" % jour
                )
            },
        )

    def _choix_comparaison(self, requete: ParametresUrl) -> None:
        """Comptes et analytiques présents dans l'une des deux bases."""
        connues = {fiche["id"] for fiche in self.app.bases.lister()}
        ids = [requete.get("base_a") or "", requete.get("base_b") or ""]
        if not all(ident in connues for ident in ids):
            return self._erreur(400, "Base inconnue.")
        comptes: dict[str, ObjetJson] = {}
        analytiques: dict[str, ObjetJson] = {}
        for lettre, ident in zip("AB", ids):
            try:
                source = self.app.bases.ouvrir(ident)
            except Exception as exc:
                return self._erreur(
                    500, "Base %s illisible : %s" % (lettre, exc)
                )
            try:
                for compte in source.comptes():
                    entree = comptes.setdefault(
                        compte["code"],
                        {
                            "code": compte["code"],
                            "libelle": compte["libelle"],
                            "bases": "",
                        },
                    )
                    entree["bases"] += lettre
                for nom in sorted(set(source.noms_analytiques().values())):
                    entree = analytiques.setdefault(
                        nom, {"nom": nom, "bases": ""}
                    )
                    if lettre not in entree["bases"]:
                        entree["bases"] += lettre
            finally:
                source.fermer()
        return self._json(
            200,
            {
                "comptes": sorted(
                    comptes.values(), key=lambda compte: compte["code"]
                ),
                "analytiques": sorted(
                    analytiques.values(),
                    key=lambda analytique: analytique["nom"].lower(),
                ),
            },
        )

    def _balance(self, requete: ParametresUrl) -> None:
        """Balance d'une base, avec ses alertes par compte."""
        try:
            source, debut, fin, etats = self._source_requete(requete)
        except ValueError as exc:
            return self._erreur(400, str(exc))
        depart = time.monotonic()
        try:
            balance = source.balance(debut, fin, etats)
            rapport, par_compte = alertes_balance(
                balance, source.balance_tiers(debut, fin, etats)
            )
        except Exception as exc:
            return self._erreur(500, "Balance impossible : %s" % exc)
        finally:
            source.fermer()
        constats = [
            _constat_explique(constat)
            for constat in rapport.en_dict()["constats"]
        ]
        self.app.journal.dire(
            "Balance de %s consultée (%s comptes, %s)"
            % (
                self.app.bases.nom(requete["base"]),
                nombre_texte(len(balance)),
                duree_texte(time.monotonic() - depart),
            ),
            "detail",
        )
        return self._json(
            200,
            {
                "comptes": [
                    dict(compte, alertes=par_compte.get(compte["code"], []))
                    for compte in balance
                ],
                "infos": rapport.infos,
                "constats": constats,
            },
        )

    def _grand_livre(self, code: str, requete: ParametresUrl) -> None:
        """Grand livre d'un compte, par pages de LIMITE_GRAND_LIVRE lignes."""
        try:
            source, debut, fin, etats = self._source_requete(requete)
            decalage = max(0, int(requete.get("offset") or 0))
        except ValueError as exc:
            return self._erreur(400, str(exc))
        try:
            page, totaux = grand_livre(
                source.lignes(debut, fin, etats, comptes=[code]),
                decalage,
                LIMITE_GRAND_LIVRE,
            )
        except Exception as exc:
            return self._erreur(500, "Grand livre impossible : %s" % exc)
        finally:
            source.fermer()
        return self._json(
            200,
            {
                "compte": code,
                "lignes": page,
                "totaux": totaux,
                "offset": decalage,
                "limite": LIMITE_GRAND_LIVRE,
            },
        )

    def _ecriture(self, ident: int, requete: ParametresUrl) -> None:
        """Lignes d'une écriture comptable."""
        try:
            source, _, _, _ = self._source_requete(requete)
        except ValueError as exc:
            return self._erreur(400, str(exc))
        try:
            lignes = source.ecriture(ident)
        except Exception as exc:
            return self._erreur(500, "Écriture illisible : %s" % exc)
        finally:
            source.fermer()
        if not lignes:
            return self._erreur(404, "Écriture introuvable.")
        return self._json(200, {"lignes": lignes, "etats": list(ETATS)})

    def _zip(self, ident: str) -> None:
        """Tous les fichiers d'une tâche dans une archive zip."""
        tache = self.app.taches.obtenir(ident)
        if not tache or not tache["fichiers"]:
            return self._erreur(404, "Aucun fichier.")
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
            for produit in tache["fichiers"]:
                chemin = self.app.taches.fichier(ident, produit["n"])
                if chemin:
                    archive.write(chemin, produit["nom"])
        self._envoyer(
            200,
            tampon.getvalue(),
            "application/zip",
            {
                "Content-Disposition": _disposition_piece_jointe(
                    "concorde_%s.zip" % ident
                )
            },
        )

    def _constat_csv(self, ident: str, code: str) -> None:
        """Éléments complets d'un constat d'analyse, en CSV."""
        chemin_rapport = self.app.taches.rapport(ident)
        if not chemin_rapport:
            return self._erreur(404, "Rapport indisponible.")
        rapport = _lire_json(chemin_rapport)
        constat = next(
            (
                candidat
                for candidat in rapport["constats"]
                if candidat["code"] == code
            ),
            None,
        )
        if not constat:
            return self._erreur(404, "Constat inconnu.")
        tampon = io.StringIO()
        ecrivain = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
        ecrivain.writerow([constat["message"]])
        for element in constat["elements"]:
            ecrivain.writerow([element])
        self._envoyer(
            200,
            ("﻿" + tampon.getvalue()).encode("utf-8"),
            "text/csv; charset=utf-8",
            {
                "Content-Disposition": _disposition_piece_jointe(
                    "%s_%s.csv" % (code.lower(), ident)
                )
            },
        )

    def _statique(self, chemin: str) -> None:
        """Fichier de interface/static (jamais en dehors de ce dossier)."""
        if chemin in ("/", ""):
            chemin = "/index.html"
        nom = os.path.normpath(chemin.lstrip("/"))
        complet = os.path.realpath(os.path.join(STATIQUE, nom))
        if not complet.startswith(
            os.path.realpath(STATIQUE) + os.sep
        ) or not os.path.isfile(complet):
            return self._erreur(404, "Introuvable.")
        with open(complet, "rb") as fichier:
            corps = fichier.read()
        type_ = mimetypes.guess_type(complet)[0] or "application/octet-stream"
        if type_.startswith("text/") or type_ in ("application/javascript",):
            type_ += "; charset=utf-8"
        self._envoyer(200, corps, type_)


def creer_serveur(
    app: Application, hote: str = "127.0.0.1", port: int = 18090
) -> ThreadingHTTPServer:
    """Serveur HTTP multi-fils servant l'application.

    Rôle : relier l'application à un gestionnaire de requêtes.
    Paramètres : app, l'application ; hote et port d'écoute.
    Retour : le serveur, prêt pour serve_forever().
    Erreurs : OSError si l'adresse est déjà prise.
    Usages : main, tests/test_interface.py.
    """

    class GestionnaireConcorde(Gestionnaire):
        """Gestionnaire lié à cette application."""

    GestionnaireConcorde.app = app
    serveur = ThreadingHTTPServer((hote, port), GestionnaireConcorde)
    serveur.daemon_threads = True
    return serveur


def _env_postgres() -> None:
    """PG* (libpq) à défaut repris de POSTGRES_USER / POSTGRES_PASSWORD."""
    for variable_pg, variable_docker in (
        ("PGUSER", "POSTGRES_USER"),
        ("PGPASSWORD", "POSTGRES_PASSWORD"),
    ):
        if not os.environ.get(variable_pg) and os.environ.get(variable_docker):
            os.environ[variable_pg] = os.environ[variable_docker]


def main() -> int:
    """Démarre l'interface (configurée par l'environnement) ; code retour."""
    empreinte = os.environ.get("CONCORDE_UI_MDP", "")
    if not empreinte.startswith("scrypt$"):
        print(
            "ERREUR : CONCORDE_UI_MDP absent. "
            "Lancez scripts/concorde_interface_mdp.py.",
            file=sys.stderr,
        )
        return 1
    _env_postgres()
    port = int(os.environ.get("CONCORDE_UI_PORT", "18090"))
    dossier = os.environ.get(
        "CONCORDE_UI_DONNEES", "/var/lib/concorde-interface"
    )
    minutes = int(os.environ.get("CONCORDE_UI_SURVEILLANCE", "15"))
    app = Application(empreinte, dossier, minutes_surveillance=minutes)
    serveur = creer_serveur(app, "127.0.0.1", port)
    app.surveillance.demarrer()
    print(
        "CONCORDE interface : http://127.0.0.1:%d "
        "(données : %s, surveillance : %s)"
        % (
            port,
            dossier,
            "toutes les %d min" % minutes if minutes else "désactivée",
        )
    )
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        # arrêt demandé au clavier (Ctrl+C) : sortie normale, code 0
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
