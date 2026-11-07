# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Bases Odoo LOCALES : suppression, réinitialisation, clés API (ADR-0005).

Ce que ce module permet :
  - supprimer une base Odoo 17 du serveur local (copie de base client, base
    de test), APRÈS une sauvegarde complète vérifiée ;
  - réinitialiser une base de test depuis son modèle vierge (PostgreSQL
    TEMPLATE) ;
  - lister et révoquer les clés API d'une base Odoo 17 du serveur (la valeur
    secrète d'une clé n'est jamais lue ni affichée).

Ce qui est IMPOSSIBLE par construction (arbitrage de Stéphane, 06/11/2026) :
  supprimer une base chez un client. Aucune fonction ne prend une URL, une
  base distante (« xmlrpc:… ») ou un hôte PostgreSQL non local ; aucun code
  de CONCORDE n'appelle le service de gestion des bases d'un Odoo
  (tests/test_bases_locales.py le vérifie sur tout le dépôt).

Garde-fous, dans l'ordre — le premier qui échoue arrête tout :
  1. hôte PostgreSQL local (boucle locale, socket, réseau Docker
     172.16.0.0/12) ;
  2. base présente dans la liste des bases Odoo 17 locales (pas une autre
     application) ;
  3. base non protégée (CONCORDE_BASES_PROTEGEES, défaut : « concorde ») ;
  4. aucune tâche CONCORDE en cours sur la base ;
  5. confirmation = nom exact de la base, retapé ;
  6. copie de base client : sauvegarde pg_dump complète, relue
     (pg_restore --list), avant de supprimer ; si elle échoue, rien n'est
     supprimé.
Base de TEST (celle qui a un modèle vierge « <nom>_modele ») : pas de
sauvegarde, son contenu est jetable par définition (arbitrage de Stéphane,
06/11/2026). C'est l'existence du modèle, lue côté serveur, qui en décide —
jamais un paramètre venu de l'écran.
Sauvegardes gardées 7 jours (CONCORDE_SAUVEGARDE_JOURS), puis effacées.
"""

import contextlib
import ipaddress
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterable, Iterator
from datetime import datetime
from types import TracebackType
from typing import (
    Any,
    Callable,
    Optional,
    Protocol,
    SupportsInt,
    TypedDict,
    Union,
)

from .journal import Journal, duree_texte, ou_muet


class CurseurPg(Protocol):
    """Curseur PostgreSQL (psycopg2) tel que ce module l'utilise."""

    rowcount: int

    def __enter__(self) -> "CurseurPg":
        """Ouvre le bloc ``with``."""

    def __exit__(
        self,
        type_exception: Optional[type[BaseException]],
        exception: Optional[BaseException],
        trace: Optional[TracebackType],
    ) -> Optional[bool]:
        """Ferme le bloc ``with``."""

    def execute(
        self, requete: str, parametres: tuple[object, ...] = ...
    ) -> object:
        """Exécute un ordre SQL (paramètres passés séparément)."""

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Toutes les lignes lues (valeurs de la base : types dynamiques)."""

    def fetchone(self) -> Optional[tuple[Any, ...]]:
        """La ligne suivante, ou None."""


class ConnexionPg(Protocol):
    """Connexion PostgreSQL fournie par l'appelant (non fermée ici)."""

    def cursor(self) -> CurseurPg:
        """Ouvre un curseur."""


class ConnexionPgFermable(ConnexionPg, Protocol):
    """Connexion PostgreSQL ouverte par ce module, qu'il ferme lui-même."""

    def close(self) -> None:
        """Ferme la connexion."""


class FonctionSauvegarde(Protocol):
    """Signature d'une sauvegarde de base (sauvegarder ou une doublure)."""

    def __call__(
        self, nom: str, dossier: str, journal: Optional[Journal] = None
    ) -> str:
        """Sauvegarde la base nom dans dossier ; rend le chemin du fichier."""


class SauvegardeListee(TypedDict):
    """Une sauvegarde présente dans le dossier des sauvegardes."""

    fichier: str
    taille: int
    date: str
    base: str


class CleApi(TypedDict):
    """Une clé API d'une base locale (jamais sa valeur secrète)."""

    base: str
    id: int
    nom: str
    login: str
    portee: str
    cree_le: datetime


def _retention() -> int:
    """Durée de garde des sauvegardes en jours (7 par défaut, 1 minimum)."""
    try:
        return max(1, int(os.environ.get("CONCORDE_SAUVEGARDE_JOURS", "7")))
    except ValueError:
        return 7


RETENTION_JOURS = _retention()
PROTEGEES_DEFAUT = ("concorde",)
SYSTEME = ("postgres", "template0", "template1")
_NOM_VALIDE = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")


class SuppressionInterdite(PermissionError):
    """Opération refusée par un garde-fou (jamais contournable)."""


def protegees() -> set[str]:
    """Bases jamais supprimées : CONCORDE_BASES_PROTEGEES + bases système.

    Rôle : liste des bases protégées (défaut : « concorde »).
    Paramètres : aucun (lit l'environnement).
    Retour : ensemble des noms protégés, bases système comprises.
    Erreurs : aucune.
    Usages : _verifier, interface/serveur.py.
    """
    brut = os.environ.get("CONCORDE_BASES_PROTEGEES")
    noms = (
        PROTEGEES_DEFAUT
        if brut is None
        else [n.strip() for n in brut.split(",")]
    )
    return set(n for n in noms if n) | set(SYSTEME)


def verifier_hote_local(hote: Optional[str] = None) -> None:
    """Refuse tout hôte PostgreSQL qui n'est pas ce serveur.

    Rôle : garde-fou n° 1 (boucle locale, socket ou réseau Docker).
    Paramètres : hote, hôte à vérifier (PGHOST si None).
    Retour : aucun.
    Erreurs : SuppressionInterdite si l'hôte n'est pas local.
    Usages : _verifier, lister_cles_api, revoquer_cle_api.
    """
    hote = os.environ.get("PGHOST", "") if hote is None else hote
    if hote in ("", "localhost") or hote.startswith("/"):
        return
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        raise SuppressionInterdite(
            "Hôte PostgreSQL %r : nom non vérifiable, suppression refusée "
            "(seules les bases de ce serveur peuvent être supprimées)." % hote
        )
    if not (ip.is_loopback or ip in ipaddress.ip_network("172.16.0.0/12")):
        raise SuppressionInterdite(
            "Hôte PostgreSQL %s : ce n'est pas ce serveur. Supprimer une "
            "base ailleurs (chez un client) est interdit." % hote
        )


def _identifiant_sql(nom_base: object) -> str:
    """Nom de base vérifié et entre guillemets doubles, prêt pour le SQL.

    Rôle : seule façon d'insérer un nom de base dans une requête
    (DROP, CREATE).
    Paramètres : nom_base (str), nom de base ou de modèle.
    Retour : '"nom_base"'.
    Erreurs : SuppressionInterdite si le nom ne respecte pas _NOM_VALIDE
    (lettres, chiffres, « _ . - », 63 caractères au plus : jamais de
    guillemet).
    Usages : supprimer(), reinitialiser().
    """
    nom_conforme = isinstance(nom_base, str) and _NOM_VALIDE.match(nom_base)
    if not nom_conforme:
        raise SuppressionInterdite("Nom de base invalide : %r." % (nom_base,))
    return '"%s"' % nom_base


def _verifier(
    nom: str,
    bases_locales: set[str],
    en_cours: set[str],
    confirmation: Optional[str],
) -> None:
    """Garde-fous 1 à 5 avant une suppression ; SuppressionInterdite sinon."""
    if not isinstance(nom, str) or ":" in nom or "/" in nom:
        raise SuppressionInterdite(
            "%r n'est pas une base locale : supprimer une base distante "
            "(chez un client) est interdit par conception. Pour la sortir "
            "de CONCORDE, utilisez « Retirer »." % (nom,)
        )
    if not _NOM_VALIDE.match(nom):
        raise SuppressionInterdite("Nom de base invalide : %r." % nom)
    verifier_hote_local()
    if nom not in bases_locales:
        raise SuppressionInterdite(
            "« %s » n'est pas une base Odoo 17 de ce serveur : CONCORDE ne "
            "la supprimera pas." % nom
        )
    if nom in protegees():
        raise SuppressionInterdite(
            "« %s » est protégée (CONCORDE_BASES_PROTEGEES)." % nom
        )
    if nom in en_cours:
        raise SuppressionInterdite(
            "Une tâche CONCORDE travaille sur « %s » : attendez sa fin." % nom
        )
    if confirmation != nom:
        raise SuppressionInterdite(
            "Confirmation incorrecte : retapez exactement « %s »." % nom
        )


def _connexion_base(nom: str, ecriture: bool = False) -> ConnexionPgFermable:
    """Connexion locale à la base nom (lecture seule sauf ecriture=True).

    Rôle : seule ouverture de connexion PostgreSQL du module.
    Paramètres : nom, base ; ecriture, autorise les modifications.
    Retour : connexion en autocommit, à fermer par l'appelant.
    Erreurs : celles de psycopg2.connect (base absente, accès refusé).
    Usages : _connexion_admin, lister_cles_api, revoquer_cle_api.
    """
    import psycopg2

    connexion_brute = psycopg2.connect(dbname=nom, connect_timeout=10)
    if ecriture:
        connexion_brute.autocommit = True
    else:
        connexion_brute.set_session(readonly=True, autocommit=True)
    cx: ConnexionPgFermable = connexion_brute
    return cx


def _connexion_admin() -> ConnexionPgFermable:
    """Connexion d'administration (base « postgres », autocommit)."""
    return _connexion_base("postgres", ecriture=True)


@contextlib.contextmanager
def _connexion_ou_nouvelle(
    connexion: Optional[ConnexionPg],
    ouvrir: Callable[[], ConnexionPgFermable],
) -> Iterator[ConnexionPg]:
    """Connexion fournie, ou nouvelle connexion fermée en fin de bloc.

    Rôle : une connexion passée par l'appelant n'est jamais fermée ici ;
    celle ouverte par ouvrir() l'est toujours, même en cas d'erreur.
    Paramètres : connexion, fournie par l'appelant (ou None) ; ouvrir,
    fonction qui ouvre une connexion.
    Retour : gestionnaire de contexte qui rend la connexion à utiliser.
    Erreurs : celles de ouvrir() et du bloc, propagées.
    Usages : supprimer, reinitialiser, lister_modeles, lister_cles_api,
    revoquer_cle_api.
    """
    if connexion is not None:
        yield connexion
        return
    nouvelle = ouvrir()
    try:
        yield nouvelle
    finally:
        nouvelle.close()


def _chemin_executable(nom: str) -> str:
    """Chemin absolu d'un programme du PATH (pg_dump, pg_restore).

    Rôle : lancer un outil PostgreSQL par son chemin complet.
    Paramètres : nom du programme.
    Retour : chemin absolu trouvé par shutil.which.
    Erreurs : FileNotFoundError explicite si le programme est absent.
    Usages : sauvegarder (pg_dump, pg_restore).
    """
    chemin = shutil.which(nom)
    if chemin is None:
        raise FileNotFoundError(
            "Programme « %s » introuvable : installez les outils clients "
            "PostgreSQL." % nom
        )
    return chemin


def sauvegarder(
    nom: str, dossier: str, journal: Optional[Journal] = None
) -> str:
    """pg_dump complet (format custom), relu par pg_restore --list.

    Rôle : sauvegarde vérifiée avant toute suppression d'une copie client.
    Paramètres : nom de la base ; dossier des sauvegardes (créé en 0700) ;
    journal d'activité (muet si None).
    Retour : chemin du fichier .dump.
    Erreurs : RuntimeError si la sauvegarde échoue ou est illisible (rien
    n'est supprimé) ; FileNotFoundError si pg_dump/pg_restore manque.
    Usages : défaut de fonction_sauvegarde (supprimer, reinitialiser).
    """
    j = ou_muet(journal)
    os.makedirs(dossier, mode=0o700, exist_ok=True)
    chemin = os.path.join(
        dossier, "%s_%s.dump" % (nom, datetime.now().strftime("%Y%m%d-%H%M%S"))
    )
    tmp = chemin + ".partiel"
    debut = time.monotonic()
    j.dire("Sauvegarde de « %s » (pg_dump)…" % nom, "etape")
    r = subprocess.run(
        [
            _chemin_executable("pg_dump"),
            "--format=custom",
            "--no-owner",
            "--file",
            tmp,
            "--dbname",
            nom,
        ],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if (
        r.returncode != 0
        or not os.path.isfile(tmp)
        or os.path.getsize(tmp) == 0
    ):
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(
            "Sauvegarde échouée, rien n'est supprimé : %s"
            % (r.stderr.strip()[-300:] or "fichier vide")
        )
    v = subprocess.run(
        [_chemin_executable("pg_restore"), "--list", tmp],
        capture_output=True,
        text=True,
        timeout=600,
    )
    objets = sum(
        1
        for ligne in v.stdout.splitlines()
        if ligne and not ligne.startswith(";")
    )
    if v.returncode != 0 or objets == 0:
        os.remove(tmp)
        raise RuntimeError(
            "Sauvegarde illisible (pg_restore --list), rien n'est supprimé."
        )
    os.replace(tmp, chemin)
    j.dire(
        "✓ Sauvegarde vérifiée : %s (%.1f Mo, %d objets, %s)"
        % (
            os.path.basename(chemin),
            os.path.getsize(chemin) / 1e6,
            objets,
            duree_texte(time.monotonic() - debut),
        ),
        "ok",
    )
    return chemin


def supprimer(
    nom: str,
    confirmation: Optional[str],
    bases_locales: Iterable[str],
    dossier_sauvegardes: str,
    en_cours: Iterable[str] = (),
    journal: Optional[Journal] = None,
    connexion: Optional[ConnexionPg] = None,
    fonction_sauvegarde: FonctionSauvegarde = sauvegarder,
    modeles: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Supprime une base Odoo 17 LOCALE après les garde-fous.

    Rôle : sauvegarde (sauf base de test) puis DROP DATABASE.
    Paramètres : nom et confirmation (nom retapé) ; bases_locales et
    en_cours, lus côté serveur ; dossier_sauvegardes ; journal ;
    connexion (ouverte ici si None) ; fonction_sauvegarde ; modeles,
    {base : modèle vierge} (une base qui y figure est une base de test).
    Retour : chemin de la sauvegarde, None pour une base de test.
    Erreurs : SuppressionInterdite (garde-fou), RuntimeError (sauvegarde).
    Usages : reinitialiser, interface/serveur.py.
    """
    j = ou_muet(journal)
    _verifier(nom, set(bases_locales), set(en_cours), confirmation)
    j.dire(
        "Garde-fous passés pour « %s » : base locale, non protégée, "
        "confirmation exacte" % nom,
        "detail",
    )
    modeles_connus = modeles or {}
    base_de_test = nom in modeles_connus
    chemin: Optional[str]
    if base_de_test:
        chemin = None
        j.dire(
            "Base de test (modèle vierge « %s ») : pas de sauvegarde"
            % modeles_connus[nom],
            "detail",
        )
    else:
        chemin = fonction_sauvegarde(nom, dossier_sauvegardes, journal=j)
    with _connexion_ou_nouvelle(connexion, _connexion_admin) as cx:
        with cx.cursor() as cur:
            j.dire(
                "Suppression de « %s » (connexions ouvertes fermées)…" % nom,
                "etape",
            )
            cur.execute(
                "DROP DATABASE %s WITH (FORCE)" % _identifiant_sql(nom)
            )
    j.dire(
        "✓ Base « %s » supprimée. %s"
        % (
            nom,
            (
                "Sauvegarde : %s (gardée %d jours)"
                % (os.path.basename(chemin), _retention())
                if chemin
                else "Pas de sauvegarde (base de test)."
            ),
        ),
        "ok",
    )
    j.dire(
        "Les pièces jointes (filestore) de « %s » restent dans le volume "
        "Docker d'Odoo ; à nettoyer par root si besoin." % nom,
        "detail",
    )
    return chemin


def reinitialiser(
    nom: str,
    confirmation: Optional[str],
    bases_locales: Iterable[str],
    modeles: Optional[dict[str, str]],
    dossier_sauvegardes: str,
    en_cours: Iterable[str] = (),
    journal: Optional[Journal] = None,
    connexion: Optional[ConnexionPg] = None,
    fonction_sauvegarde: FonctionSauvegarde = sauvegarder,
) -> Optional[str]:
    """Supprime la base de test (sans sauvegarde), la recrée vierge.

    modeles : {base : modèle}, lu côté serveur (lister_modeles()).
    """
    j = ou_muet(journal)
    modele = (modeles or {}).get(nom)
    if not modele:
        raise SuppressionInterdite(
            "« %s » n'a pas de modèle vierge : ce n'est pas une base de "
            "test, elle ne se réinitialise pas." % nom
        )
    # Modèle vérifié AVANT la suppression : un refus ne laisse jamais
    # la base supprimée sans recréation.
    identifiant_modele = _identifiant_sql(modele)
    with _connexion_ou_nouvelle(connexion, _connexion_admin) as cx:
        chemin = supprimer(
            nom,
            confirmation,
            bases_locales,
            dossier_sauvegardes,
            en_cours,
            j,
            cx,
            fonction_sauvegarde,
            modeles,
        )
        with cx.cursor() as cur:
            j.dire(
                "Recréation de « %s » depuis le modèle vierge « %s »…"
                % (nom, modele),
                "etape",
            )
            cur.execute(
                "CREATE DATABASE %s TEMPLATE %s"
                % (_identifiant_sql(nom), identifiant_modele)
            )
        j.dire("✓ « %s » est de nouveau vierge" % nom, "ok")
    return chemin


def lister_modeles() -> dict[str, str]:
    """Bases modèles (PostgreSQL TEMPLATE) : {nom de base : nom du modèle}."""
    with _connexion_ou_nouvelle(None, _connexion_admin) as cx:
        with cx.cursor() as cur:
            cur.execute(
                "SELECT datname FROM pg_database WHERE datistemplate "
                "AND datname LIKE '%%\\_modele'"
            )
            noms: list[str] = [r[0] for r in cur.fetchall()]
    longueur_suffixe = len("_modele")
    return {n[:-longueur_suffixe]: n for n in noms}


def purger_sauvegardes(
    dossier: str,
    jours: Optional[int] = None,
    journal: Optional[Journal] = None,
) -> list[str]:
    """Efface les sauvegardes .dump plus vieilles que jours (rétention).

    Retourne les noms de fichiers effacés ([] si le dossier n'existe pas).
    """
    j = ou_muet(journal)
    jours = jours or _retention()
    if not os.path.isdir(dossier):
        return []
    limite = time.time() - jours * 86400
    retirees = []
    for f in sorted(os.listdir(dossier)):
        chemin = os.path.join(dossier, f)
        if f.endswith(".dump") and os.path.getmtime(chemin) < limite:
            os.remove(chemin)
            retirees.append(f)
            j.dire(
                "Sauvegarde de plus de %d jours effacée : %s" % (jours, f),
                "detail",
            )
    return retirees


def lister_sauvegardes(dossier: str) -> list[SauvegardeListee]:
    """Sauvegardes .dump du dossier, de la plus récente à la plus ancienne."""
    if not os.path.isdir(dossier):
        return []
    res: list[SauvegardeListee] = []
    for f in sorted(os.listdir(dossier), reverse=True):
        if f.endswith(".dump"):
            chemin = os.path.join(dossier, f)
            res.append(
                {
                    "fichier": f,
                    "taille": os.path.getsize(chemin),
                    "date": datetime.fromtimestamp(
                        os.path.getmtime(chemin)
                    ).isoformat(timespec="seconds"),
                    "base": f.rsplit("_", 2)[0],
                }
            )
    return res


# ---------------------------------------------------------------------------
# Clés API des bases Odoo 17 du serveur
# ---------------------------------------------------------------------------


def lister_cles_api(
    bases_locales: Iterable[str], connexion: Optional[ConnexionPg] = None
) -> list[CleApi]:
    """Clés API de chaque base locale : nom, utilisateur, portée, date.

    Jamais la valeur de la clé.
    """
    verifier_hote_local()
    res: list[CleApi] = []
    for nom in bases_locales:
        with _connexion_ou_nouvelle(
            connexion, lambda: _connexion_base(nom)
        ) as cx:
            with cx.cursor() as cur:
                cur.execute(
                    "SELECT k.id, k.name, u.login, k.scope, k.create_date "
                    "FROM res_users_apikeys k "
                    "JOIN res_users u ON u.id = k.user_id "
                    "ORDER BY k.create_date"
                )
                for r in cur.fetchall():
                    res.append(
                        {
                            "base": nom,
                            "id": r[0],
                            "nom": r[1] or "",
                            "login": r[2],
                            "portee": r[3] or "toutes",
                            "cree_le": r[4],
                        }
                    )
    return res


def revoquer_cle_api(
    base: str,
    ident: Union[str, SupportsInt, None],
    confirmation: Optional[str],
    bases_locales: Iterable[str],
    journal: Optional[Journal] = None,
    connexion: Optional[ConnexionPg] = None,
) -> str:
    """Révoque UNE clé API d'une base Odoo 17 du serveur. Retourne son nom.

    Garde-fous : hôte local, base locale, clé existante, nom de la clé
    retapé. Seule la ligne de cette clé est supprimée (res_users_apikeys) :
    Odoo la refuse dès la requête suivante. Jamais sur une base distante
    (chez un client).
    """
    j = ou_muet(journal)
    if not isinstance(base, str) or ":" in base or "/" in base:
        raise SuppressionInterdite(
            "%r n'est pas une base de ce serveur : CONCORDE ne révoque "
            "pas de clé chez un client." % (base,)
        )
    verifier_hote_local()
    if base not in set(bases_locales):
        raise SuppressionInterdite(
            "« %s » n'est pas une base Odoo 17 de ce serveur." % base
        )
    try:
        if ident is None:
            raise TypeError("identifiant de clé absent")
        identifiant_cle = int(ident)
    except (TypeError, ValueError):
        raise SuppressionInterdite(
            "Identifiant de clé invalide : %r." % (ident,)
        )
    with _connexion_ou_nouvelle(
        connexion, lambda: _connexion_base(base, ecriture=True)
    ) as cx:
        with cx.cursor() as cur:
            cur.execute(
                "SELECT name FROM res_users_apikeys WHERE id = %s",
                (identifiant_cle,),
            )
            ligne = cur.fetchone()
            if not ligne:
                raise SuppressionInterdite(
                    "Clé n° %d introuvable dans « %s »."
                    % (identifiant_cle, base)
                )
            nom_cle: str = ligne[0] or ""
            if confirmation != nom_cle:
                raise SuppressionInterdite(
                    "Confirmation incorrecte : retapez exactement « %s »."
                    % nom_cle
                )
            cur.execute(
                "DELETE FROM res_users_apikeys WHERE id = %s",
                (identifiant_cle,),
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    "Révocation incertaine (%d ligne(s)) : vérifiez dans Odoo."
                    % cur.rowcount
                )
    j.dire(
        "✓ Clé API « %s » révoquée dans la base « %s »" % (nom_cle, base), "ok"
    )
    return nom_cle
