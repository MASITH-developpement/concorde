# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Montée de version d'une base Odoo sur le serveur CONCORDE (ADR-0010, 0012).

Une montée = un dossier `<racine>/<id>/` avec `montee.json` (état de chaque
étape), la sauvegarde déposée, les journaux, les photos et l'inventaire.
Les données du client (`donnees/`) sont dans ce dossier, sur le volume
chiffré quand il est utilisé (volume.py).

Conteneurs : un réseau Docker interne propre à la montée (aucun port
publié), un PostgreSQL jetable, puis un Odoo de chaque version visée avec
OpenUpgrade non modifié. Garde-fous : place disque avant et pendant,
mémoire et processeur bridés, une seule montée à la fois.
"""

import json
import os
import secrets
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, TypedDict

from ..fichier_json import ecrire_json_atomique
from ..journal import Journal, ou_muet
from ..odoo_source import connexion_lecture_seule
from .commandes import ErreurCommande, executer, fin_de_sortie
from .inventaire import couverture_saut, inventorier, lire_modules
from .openupgrade import OPENUPGRADELIB, recuperer, sauts, version_majeure
from .photo import (
    EcartPhoto,
    PhotoComptable,
    charger_photo,
    comparer_photos,
    prendre_photo,
)
from .sauvegarde import (
    InfoSauvegarde,
    ecrire_sauvegarde,
    examiner_sauvegarde,
    extraire_sauvegarde,
)

DISQUE_HOTE = os.environ.get("CONCORDE_DISQUE_HOTE", "/")
MODULES_ODOO = "/usr/lib/python3/dist-packages/odoo/addons"
SCRIPTS_MONTEE = "openupgrade_scripts/scripts"
UTILISATEUR_PG = "odoo"
NOM_BASE = "concorde_montee"
MEMOIRE_CONTENEUR = "1536m"
PROCESSEURS_CONTENEUR = "1"
PART_PROCESSEUR = "256"  # priorité basse face au site (défaut Docker 1024)
GO = 1024**3
MARGE_DEPART = 3 * GO
LIBRE_MINIMUM = 2 * GO
SURVEILLANCE_S = 10.0
ECARTS_GARDES = 200
CHEMIN_MONTEES = os.environ.get(
    "CONCORDE_MONTEES", "/var/lib/concorde-montee/montees"
)
CHEMIN_OPENUPGRADE = os.environ.get(
    "CONCORDE_OPENUPGRADE", "/var/lib/concorde-montee/openupgrade"
)
# Statuts d'une montée et de ses étapes.
VERTE = "verte"
BLOQUEE = "bloquee"
EN_COURS = "en_cours"
ATTENTE = "attente_feu_vert"
LIVREE = "livree"
ARRETEE = "arretee"
# Fichiers d'arrêt déposés par l'interface (ADR-0016).
ARRET_URGENCE = "arret-urgence"
PREFIXE_ARRET = "arret-"
ETAPES_MONTEE = (
    "inventaire",
    "photo_avant",
    "sauts",
    "photo_apres",
    "comparaison",
    "feu_vert",
    "nouvel_essai",
    "livraison",
)

# Lance un programme : (arguments, journal, entrée) -> sortie. Remplacé
# dans les tests ; en vrai, commandes.executer.
LanceurProgramme = Callable[..., str]


class ErreurMontee(ValueError):
    """Montée refusée ou arrêtée (la cause est nommée)."""


class EtapeMontee(TypedDict, total=False):
    """État d'une étape : statut, cause, détails, durée."""

    statut: str
    erreur: str
    infos: dict[str, Any]
    duree_s: float


class EtatMontee(TypedDict):
    """État complet d'une montée, écrit dans montee.json."""

    id: str
    cree_le: str
    statut: str
    arrivee: int
    depart: int
    sauvegarde: InfoSauvegarde
    base_client: str
    etapes: dict[str, EtapeMontee]


def dossier_montee(racine: str, ident: str) -> str:
    """Dossier d'une montée (identifiant vérifié). Lève ErreurMontee."""
    if not ident.startswith("M") or not ident[1:].replace("-", "").isalnum():
        raise ErreurMontee("Montée inconnue : %s" % ident)
    return os.path.join(racine, ident)


def charger(racine: str, ident: str) -> EtatMontee:
    """État d'une montée enregistrée. Lève ErreurMontee si inconnue."""
    chemin = os.path.join(dossier_montee(racine, ident), "montee.json")
    if not os.path.isfile(chemin):
        raise ErreurMontee("Montée inconnue : %s" % ident)
    with open(chemin, encoding="utf-8") as fichier:
        etat: EtatMontee = json.load(fichier)
    return etat


def sauver(racine: str, etat: EtatMontee) -> None:
    """Écrit montee.json (écriture atomique, droits du dossier : 700)."""
    ecrire_json_atomique(
        os.path.join(dossier_montee(racine, etat["id"]), "montee.json"),
        etat,
        ascii_seul=False,
        retrait=1,
    )


def creer(
    racine: str, sauvegarde: str, arrivee: int, journal: Journal | None = None
) -> EtatMontee:
    """Enregistre une montée à partir d'une sauvegarde Odoo (.zip).

    Rôle : point de départ ; rien n'est restauré ni lancé.
    Paramètres : racine — dossier des montées ; sauvegarde — .zip
    déposé (déplacé dans le dossier de la montée) ; arrivee — version
    voulue ; journal.
    Retour : EtatMontee (statut « en_attente »).
    Erreurs : ErreurSauvegarde (zip refusé) ; ErreurOpenUpgrade (saut
    impossible) ; ErreurMontee (version absente du manifeste) ; OSError.
    Usages : scripts/concorde_montee (creer), service de montée.
    """
    info = examiner_sauvegarde(sauvegarde)
    if info["version"] is None:
        raise ErreurMontee(
            "Version d'Odoo absente de la sauvegarde (manifest.json) : "
            "faire une sauvegarde depuis le gestionnaire de bases d'Odoo."
        )
    depart = version_majeure(info["version"])
    sauts(depart, arrivee)
    ident = "M%s-%s" % (
        datetime.now().strftime("%Y%m%d%H%M%S"),
        uuid.uuid4().hex[:4],
    )
    dossier = dossier_montee(racine, ident)
    os.makedirs(os.path.join(dossier, "depot"), mode=0o700)
    shutil.move(sauvegarde, os.path.join(dossier, "depot", info["nom"]))
    etat: EtatMontee = {
        "id": ident,
        "cree_le": datetime.now().isoformat(timespec="seconds"),
        "statut": "en_attente",
        "arrivee": arrivee,
        "depart": depart,
        "sauvegarde": info,
        "base_client": info["base"] or os.path.splitext(info["nom"])[0],
        "etapes": {nom: {"statut": "non_jouee"} for nom in ETAPES_MONTEE},
    }
    sauver(racine, etat)
    ou_muet(journal).dire(
        "Montée %s créée : %s, Odoo %d -> %d"
        % (ident, info["nom"], depart, arrivee),
        "ok",
    )
    return etat


def place_libre(chemin: str) -> int:
    """Octets libres : le plus petit entre `chemin` et le disque du serveur.

    Le volume chiffré est un fichier creux sur le disque du serveur : sa
    place libre annoncée peut dépasser celle du disque réel (DISQUE_HOTE).
    """
    return min(
        shutil.disk_usage(dossier).free for dossier in (chemin, DISQUE_HOTE)
    )


def verifier_place(chemin: str, octets_base: int) -> None:
    """Garde-fou de départ : 3 fois la base décompressée, plus 3 Go.

    Rôle : refuser une montée qui remplirait le disque du site (ADR-0012).
    Paramètres : chemin — dossier de la montée ; octets_base — taille
    décompressée de la sauvegarde.
    Retour : aucun.
    Erreurs : ErreurMontee, avec les chiffres.
    Usages : Montee.preparer, tests.
    """
    besoin = 3 * octets_base + MARGE_DEPART
    libre = place_libre(chemin)
    if libre < besoin:
        raise ErreurMontee(
            "Place disque insuffisante : %.1f Go libres, %.1f Go "
            "nécessaires (3 × %.1f Go de base + 3 Go). Agrandir le disque "
            "du serveur avant cette montée."
            % (libre / GO, besoin / GO, octets_base / GO)
        )


class Montee:
    """Conduite d'une montée : conteneurs, étapes, garde-fous."""

    def __init__(
        self,
        racine: str,
        ident: str,
        openupgrade: str = CHEMIN_OPENUPGRADE,
        lanceur: LanceurProgramme | None = None,
        journal: Journal | None = None,
        arrets: str | None = None,
        ident_arret: str | None = None,
    ) -> None:
        """Relit la montée ; prépare les noms de ses conteneurs.

        `lanceur` : commandes.executer par défaut (simulé dans les tests).
        `arrets` : dossier où l'interface dépose les fichiers d'arrêt
        (ADR-0016) ; None : la montée ne peut pas être arrêtée de l'écran.
        `ident_arret` : montée dont le fichier d'arrêt compte (celle qui a
        reçu le feu vert, pour un nouvel essai) ; par défaut, celle-ci.
        """
        self.racine = racine
        self.etat = charger(racine, ident)
        self.dossier = dossier_montee(racine, ident)
        self.openupgrade = openupgrade
        self.lancer = lanceur or executer
        self.journal = ou_muet(journal)
        nom = "concorde-%s" % ident.lower()
        self.reseau = nom
        self.conteneur_pg = nom + "-pg"
        self.donnees = os.path.join(self.dossier, "donnees")
        self.arrets = arrets
        self.ident_arret = ident_arret or ident

    # --- arrêt (ADR-0016) --------------------------------------------------
    def arret_demande(self) -> str | None:
        """« urgence », « demande » (cette montée) ou None."""
        if self.arrets is None:
            return None
        if os.path.exists(os.path.join(self.arrets, ARRET_URGENCE)):
            return "urgence"
        if os.path.exists(
            os.path.join(self.arrets, PREFIXE_ARRET + self.ident_arret)
        ):
            return "demande"
        return None

    def _verifier_arret(self) -> None:
        """Entre deux étapes : lève ErreurMontee si l'arrêt est demandé."""
        genre = self.arret_demande()
        if genre is not None:
            raise ErreurMontee("Montée arrêtée (arrêt %s)." % genre)

    def effacer_copie(self) -> None:
        """Efface la copie de travail d'une montée arrêtée (ADR-0016).

        Conteneurs retirés ; bases, sauvegarde déposée, accès et livraison
        effacés. montee.json et les journaux restent pour l'historique.
        """
        self.arreter()
        for nom in ("donnees", "depot", "acces", "livraison"):
            chemin = os.path.join(self.dossier, nom)
            if os.path.isdir(chemin):
                shutil.rmtree(chemin)
        self._etape("arret", ARRETEE, "Arrêtée à la demande : copie effacée.")
        self._statut(ARRETEE)

    # --- état ----------------------------------------------------------------
    def _etape(
        self,
        nom: str,
        statut: str,
        erreur: str | None = None,
        infos: dict[str, Any] | None = None,
        duree_s: float | None = None,
    ) -> None:
        """Remplace l'état d'une étape et enregistre la montée."""
        etape: EtapeMontee = {"statut": statut}
        if erreur is not None:
            etape["erreur"] = erreur
        if infos is not None:
            etape["infos"] = infos
        if duree_s is not None:
            etape["duree_s"] = round(duree_s, 1)
        self.etat["etapes"][nom] = etape
        sauver(self.racine, self.etat)

    def _statut(self, statut: str) -> None:
        """Change le statut de la montée et enregistre."""
        self.etat["statut"] = statut
        sauver(self.racine, self.etat)

    def _fichier(self, *parties: str) -> str:
        """Chemin dans le dossier de la montée (dossier parent créé)."""
        chemin = os.path.join(self.dossier, *parties)
        os.makedirs(os.path.dirname(chemin), mode=0o700, exist_ok=True)
        return chemin

    # --- conteneurs ----------------------------------------------------------
    def _docker(
        self,
        *arguments: str,
        journal: str | None = None,
        entree: Any = None,
    ) -> str:
        """Lance `docker` avec ces arguments (lanceur de la montée)."""
        return self.lancer(["docker", *arguments], journal, entree)

    def _existe(self, quoi: str, nom: str) -> bool:
        """Vrai si le conteneur ou le réseau `nom` existe."""
        filtre = (
            ["ps", "-aq"] if quoi == "conteneur" else ["network", "ls", "-q"]
        )
        return bool(
            self._docker(*filtre, "--filter", "name=^%s$" % nom).strip()
        )

    def _fichier_acces(self) -> str:
        """Fichier env (600) du mot de passe du PostgreSQL jetable."""
        return self._fichier("acces", "postgres.env")

    def _acces(self) -> dict[str, str]:
        """Mot de passe du PostgreSQL jetable (créé au premier appel)."""
        chemin = self._fichier_acces()
        if not os.path.isfile(chemin):
            ancien = os.umask(0o077)
            try:
                with open(chemin, "w", encoding="utf-8") as fichier:
                    fichier.write(
                        "POSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\n"
                        "USER=%s\nPASSWORD=%s\nHOST=%s\n"
                        % (
                            UTILISATEUR_PG,
                            mot := secrets.token_urlsafe(24),
                            UTILISATEUR_PG,
                            mot,
                            self.conteneur_pg,
                        )
                    )
            finally:
                os.umask(ancien)
        with open(chemin, encoding="utf-8") as fichier:
            valeurs = dict(
                ligne.rstrip("\n").split("=", 1)
                for ligne in fichier
                if "=" in ligne
            )
        return valeurs

    def _limites(self) -> list[str]:
        """Bridage d'un conteneur : mémoire sans swap, processeur, priorité."""
        return [
            "--memory",
            MEMOIRE_CONTENEUR,
            "--memory-swap",
            MEMOIRE_CONTENEUR,
            "--cpus",
            PROCESSEURS_CONTENEUR,
            "--cpu-shares",
            PART_PROCESSEUR,
        ]

    def preparer(self) -> None:
        """Place vérifiée, réseau interne, PostgreSQL démarré, base restaurée.

        La restauration n'est faite qu'une fois (reprise possible).
        Lève ErreurMontee (place disque), ErreurCommande, ErreurSauvegarde.
        """
        info = self.etat["sauvegarde"]
        restauree = os.path.join(self.donnees, "restauree")
        if not os.path.isfile(restauree):
            verifier_place(self.dossier, info["octets_decompresses"])
        self._acces()
        for sous in ("pgdata", "odoo"):
            os.makedirs(
                os.path.join(self.donnees, sous), mode=0o700, exist_ok=True
            )
        if not self._existe("reseau", self.reseau):
            self._docker("network", "create", "--internal", self.reseau)
        if not self._existe("conteneur", self.conteneur_pg):
            self._docker(
                "run",
                "-d",
                "--name",
                self.conteneur_pg,
                "--network",
                self.reseau,
                *self._limites(),
                "--env-file",
                self._fichier_acces(),
                "-v",
                "%s:/var/lib/postgresql/data"
                % os.path.join(self.donnees, "pgdata"),
                "postgres:%d" % info["pg_version"],
            )
        self._attendre_postgres()
        if os.path.isfile(restauree):
            return
        self.journal.dire("Restauration de la sauvegarde", "etape")
        extraction = os.path.join(self.donnees, "extraction")
        dump, pieces = extraire_sauvegarde(
            os.path.join(self.dossier, "depot", info["nom"]), extraction
        )
        self._psql("createdb", NOM_BASE)
        with open(dump, "rb") as flux:
            self._docker(
                "exec",
                "-i",
                self.conteneur_pg,
                "psql",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                UTILISATEUR_PG,
                "-d",
                NOM_BASE,
                journal=self._fichier("journaux", "restauration.log"),
                entree=flux,
            )
        filestore = os.path.join(self.donnees, "odoo", "filestore", NOM_BASE)
        if os.path.isdir(filestore):
            shutil.rmtree(filestore)
        os.makedirs(os.path.dirname(filestore), exist_ok=True)
        shutil.move(pieces, filestore)
        shutil.rmtree(extraction)
        with open(restauree, "w", encoding="utf-8") as marque:
            marque.write(datetime.now().isoformat(timespec="seconds"))

    def _psql(self, programme: str, *arguments: str) -> str:
        """Outil PostgreSQL (createdb, pg_dump…) dans le conteneur jetable."""
        return self._docker(
            "exec",
            self.conteneur_pg,
            programme,
            "-U",
            UTILISATEUR_PG,
            *arguments,
        )

    def _attendre_postgres(self, essais: int = 60) -> None:
        """Attend que PostgreSQL accepte les connexions. Lève ErreurMontee."""
        for _ in range(essais):
            try:
                self._psql("pg_isready", "-q")
                return
            except ErreurCommande:
                time.sleep(2)
        raise ErreurMontee(
            "PostgreSQL jetable : pas prêt après %d essais." % essais
        )

    def arreter(self) -> None:
        """Retire le PostgreSQL jetable et le réseau (données gardées)."""
        if self._existe("conteneur", self.conteneur_pg):
            self._docker("rm", "-f", self.conteneur_pg)
        if self._existe("reseau", self.reseau):
            self._docker("network", "rm", self.reseau)

    @contextmanager
    def conteneurs(self) -> Iterator[None]:
        """Conteneurs prêts pendant le bloc, toujours arrêtés après."""
        try:
            self.preparer()
            yield
        finally:
            self.arreter()

    def _connexion(self) -> Any:
        """Connexion en lecture seule à la base restaurée (réseau interne)."""
        adresse = self._docker(
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            self.conteneur_pg,
        ).strip()
        acces = self._acces()
        return connexion_lecture_seule(
            NOM_BASE,
            {
                "host": adresse,
                "user": acces["POSTGRES_USER"],
                "password": acces["POSTGRES_PASSWORD"],
            },
        )

    # --- étapes --------------------------------------------------------------
    def faire_inventaire(self) -> bool:
        """Étape 1 : modules, saut par saut ; vrai si rien ne bloque."""
        debut = time.monotonic()
        connexion = self._connexion()
        try:
            version, modules = lire_modules(connexion, NOM_BASE)
        finally:
            connexion.close()
        if version_majeure(version) != self.etat["depart"]:
            raise ErreurMontee(
                "La base restaurée est en Odoo %s, la sauvegarde annonçait "
                "Odoo %d : sauvegarde incohérente, montée arrêtée."
                % (version, self.etat["depart"])
            )
        couvertures = {
            cible: couverture_saut(recuperer(self.openupgrade, cible), cible)
            for cible in sauts(self.etat["depart"], self.etat["arrivee"])
        }
        resultat = inventorier(
            self.etat["base_client"],
            version,
            modules,
            self.etat["arrivee"],
            couvertures,
        )
        ecrire_json_atomique(
            self._fichier("inventaire.json"),
            resultat,
            ascii_seul=False,
            retrait=1,
        )
        bloquants = [
            "Odoo %d : %s (%s)"
            % (saut["vers"], bloquant["module"], bloquant["cause"])
            for saut in resultat["sauts"]
            for bloquant in saut["bloquants"]
        ]
        self._etape(
            "inventaire",
            BLOQUEE if bloquants else VERTE,
            "; ".join(bloquants) if bloquants else None,
            {
                "version": version,
                "modules": len(modules),
                "a_verifier": sum(
                    len(saut["a_verifier"]) for saut in resultat["sauts"]
                ),
                "bloquants": len(bloquants),
            },
            time.monotonic() - debut,
        )
        return not bloquants

    def photo(self, nom: str) -> PhotoComptable:
        """Étapes 2 et 4 : photo comptable, écrite dans <nom>.json."""
        debut = time.monotonic()
        connexion = self._connexion()
        try:
            cliche = prendre_photo(connexion, self.etat["base_client"])
        finally:
            connexion.close()
        ecrire_json_atomique(
            self._fichier(nom + ".json"), cliche, ascii_seul=False, retrait=1
        )
        self._etape(
            nom,
            VERTE,
            infos={
                "version": cliche["version"],
                "empreinte": cliche["empreinte"],
                "elements": {
                    section: len(valeurs)
                    for section, valeurs in cliche["sections"].items()
                },
            },
            duree_s=time.monotonic() - debut,
        )
        return cliche

    def _image_saut(self, cible: int) -> str:
        """Image Odoo de la version visée, avec openupgradelib (figée)."""
        image = "concorde-openupgrade:%d" % cible
        recette = (
            "FROM odoo:%d.0\nUSER root\nRUN PIP_BREAK_SYSTEM_PACKAGES=1 pip3 "
            "install --no-cache-dir %s\nUSER odoo\n" % (cible, OPENUPGRADELIB)
        )
        self._docker(
            "build",
            "-q",
            "-t",
            image,
            "-",
            journal=self._fichier("journaux", "image-%d.log" % cible),
            entree=recette.encode(),
        )
        return image

    def _proprietaire_odoo(self, image: str) -> None:
        """Donne les pièces jointes au compte odoo de l'image."""
        identite = self._docker(
            "run", "--rm", "--entrypoint", "id", image, "-u"
        )
        uid = identite.strip()
        if not uid.isdigit():
            raise ErreurMontee("Compte odoo de l'image illisible : %r" % uid)
        for parent, dossiers, fichiers in os.walk(
            os.path.join(self.donnees, "odoo")
        ):
            os.chown(parent, int(uid), int(uid))
            for nom in dossiers + fichiers:
                os.chown(os.path.join(parent, nom), int(uid), int(uid))

    @contextmanager
    def _surveiller_disque(self, conteneur: str) -> Iterator[list[str]]:
        """Arrête `conteneur` si le disque passe sous LIBRE_MINIMUM.

        Rend une liste qui reçoit la cause de l'arrêt (vide sinon).
        """
        causes: list[str] = []
        fini = threading.Event()

        def guetter() -> None:
            """Mesure la place libre toutes les SURVEILLANCE_S secondes."""
            while not fini.wait(SURVEILLANCE_S):
                genre = self.arret_demande()
                if genre is not None:
                    causes.append("arrêt %s demandé : saut arrêté" % genre)
                    self._docker("kill", conteneur)
                    return
                libre = place_libre(self.dossier)
                if libre < LIBRE_MINIMUM:
                    causes.append(
                        "disque presque plein (%.1f Go libres) : saut arrêté "
                        "pour protéger le site" % (libre / GO)
                    )
                    self._docker("kill", conteneur)
                    return

        guetteur = threading.Thread(target=guetter, daemon=True)
        guetteur.start()
        try:
            yield causes
        finally:
            fini.set()
            guetteur.join()

    def monter(self) -> None:
        """Étape 3 : un saut par version, OpenUpgrade non modifié.

        Lève ErreurMontee au premier saut en échec (saut et cause nommés).
        """
        resultats: dict[str, Any] = {}
        self._etape("sauts", EN_COURS, infos=resultats)
        for cible in sauts(self.etat["depart"], self.etat["arrivee"]):
            self.journal.dire("Saut vers Odoo %d" % cible, "etape")
            debut = time.monotonic()
            code_ou = recuperer(self.openupgrade, cible)
            image = self._image_saut(cible)
            self._proprietaire_odoo(image)
            conteneur = "%s-odoo%d" % (self.reseau, cible)
            journal = self._fichier("journaux", "saut-%d.log" % cible)
            try:
                with self._surveiller_disque(conteneur) as causes:
                    self._docker(
                        "run",
                        "--rm",
                        "--name",
                        conteneur,
                        "--network",
                        self.reseau,
                        *self._limites(),
                        "--env-file",
                        self._fichier_acces(),
                        "-v",
                        "%s:/var/lib/odoo"
                        % os.path.join(self.donnees, "odoo"),
                        "-v",
                        "%s:/mnt/openupgrade:ro" % code_ou,
                        image,
                        "--",
                        "-d",
                        NOM_BASE,
                        "--addons-path=%s,/mnt/openupgrade" % MODULES_ODOO,
                        "--upgrade-path=/mnt/openupgrade/%s" % SCRIPTS_MONTEE,
                        "--load=base,web,openupgrade_framework",
                        "--update=all",
                        "--stop-after-init",
                        journal=journal,
                    )
            except ErreurCommande as exc:
                cause = causes[0] if causes else str(exc)
                resultats[str(cible)] = {
                    "statut": BLOQUEE,
                    "erreur": cause,
                    "duree_s": round(time.monotonic() - debut, 1),
                }
                self._etape(
                    "sauts",
                    BLOQUEE,
                    "Odoo %d : %s" % (cible, cause),
                    resultats,
                )
                raise ErreurMontee(
                    "Saut vers Odoo %d en échec : %s" % (cible, cause)
                ) from exc
            finally:
                self._effacer_image(image, cible)
            with open(journal, encoding="utf-8", errors="replace") as fichier:
                erreurs = [
                    ligne.strip() for ligne in fichier if " ERROR " in ligne
                ]
            resultats[str(cible)] = {
                "statut": VERTE,
                "duree_s": round(time.monotonic() - debut, 1),
                "lignes_erreur": len(erreurs),
                "exemples": erreurs[:5],
            }
            self._etape("sauts", EN_COURS, infos=resultats)
        self._etape("sauts", VERTE, infos=resultats)

    def _effacer_image(self, image: str, cible: int) -> None:
        """Efface l'image du saut, et l'image Odoo si elle ne sert plus."""
        self._docker("image", "rm", "-f", image)
        base = "odoo:%d.0" % cible
        if not self._docker(
            "ps", "-aq", "--filter", "ancestor=%s" % base
        ).strip():
            try:
                self._docker("image", "rm", base)
            except ErreurCommande as exc:
                self.journal.dire("Image %s gardée : %s" % (base, exc), "info")

    def comparer(self) -> list[EcartPhoto]:
        """Étape 4 (suite) : photo avant contre photo après, tolérance zéro."""
        ecarts = comparer_photos(
            charger_photo(self._fichier("photo_avant.json")),
            charger_photo(self._fichier("photo_apres.json")),
        )
        ecrire_json_atomique(
            self._fichier("ecarts.json"), ecarts, ascii_seul=False, retrait=1
        )
        self._etape(
            "comparaison",
            BLOQUEE if ecarts else VERTE,
            "%d écart(s) au centime" % len(ecarts) if ecarts else None,
            {"ecarts": len(ecarts), "exemples": ecarts[:ECARTS_GARDES]},
        )
        return ecarts

    def circuit(self) -> str:
        """Étapes 1 à 4 de bout en bout ; rend le statut final de la montée.

        Statut « attente_feu_vert » seulement avec zéro écart ; sinon
        « bloquee », avec l'étape et la cause nommées.
        """
        self._statut(EN_COURS)
        try:
            with self.conteneurs():
                if not self.faire_inventaire():
                    self._statut(BLOQUEE)
                    return BLOQUEE
                self._verifier_arret()
                self.photo("photo_avant")
                self._verifier_arret()
                self.monter()
                self._verifier_arret()
                self.photo("photo_apres")
                ecarts = self.comparer()
        except (ErreurMontee, ErreurCommande, OSError, ValueError) as exc:
            self.journal.dire("Montée arrêtée : %s" % exc, "erreur")
            arret = self.arret_demande() is not None
            self._etape("arret", ARRETEE if arret else BLOQUEE, str(exc))
            self._statut(ARRETEE if arret else BLOQUEE)
            return ARRETEE if arret else BLOQUEE
        statut = BLOQUEE if ecarts else ATTENTE
        self._statut(statut)
        return statut

    def donner_feu_vert(self, confirmation: str, par: str) -> None:
        """Étape 5 : feu vert, nom de la base du client retapé.

        Lève ErreurMontee si la montée n'attend pas de feu vert, si le feu
        vert est déjà donné, ou si le nom ne correspond pas.
        """
        if self.etat["statut"] != ATTENTE:
            raise ErreurMontee(
                "Cette montée n'attend pas de feu vert (statut %s)."
                % self.etat["statut"]
            )
        if self.etat["etapes"]["feu_vert"].get("statut") == VERTE:
            raise ErreurMontee("Le feu vert est déjà donné pour cette montée.")
        if confirmation.strip() != self.etat["base_client"]:
            raise ErreurMontee(
                "Nom de la base mal retapé : rien n'est validé."
            )
        self._etape(
            "feu_vert",
            VERTE,
            infos={
                "par": par,
                "le": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def livrer(self) -> str:
        """Étape 7 : sauvegarde Odoo de la base montée ; rend son chemin.

        Lève ErreurMontee si le feu vert ou le nouvel essai manquent.
        """
        for etape in ("feu_vert", "nouvel_essai"):
            if self.etat["etapes"][etape].get("statut") != VERTE:
                raise ErreurMontee(
                    "Livraison impossible : étape %s pas faite." % etape
                )
        essai = Montee(
            self.racine,
            str(self.etat["etapes"]["nouvel_essai"]["infos"]["montee"]),
            self.openupgrade,
            self.lancer,
            self.journal,
        )
        nom = "%s_odoo%d.zip" % (
            self.etat["base_client"],
            self.etat["arrivee"],
        )
        sortie = self._fichier("livraison", nom)
        with essai.conteneurs():
            essai._psql(
                "pg_dump",
                "--no-owner",
                "-f",
                "/var/lib/postgresql/data/livraison.sql",
                NOM_BASE,
            )
        dump = os.path.join(essai.donnees, "pgdata", "livraison.sql")
        empreinte = ecrire_sauvegarde(
            sortie,
            dump,
            os.path.join(essai.donnees, "odoo", "filestore", NOM_BASE),
            {
                "odoo_dump": "1",
                "db_name": self.etat["base_client"],
                "version": "%d.0" % self.etat["arrivee"],
                "major_version": "%d.0" % self.etat["arrivee"],
            },
        )
        os.remove(dump)
        self._etape(
            "livraison",
            VERTE,
            infos={
                "fichier": nom,
                "octets": os.path.getsize(sortie),
                "sha256": empreinte,
                "le": datetime.now().isoformat(timespec="seconds"),
            },
        )
        self._statut(LIVREE)
        return sortie


def nouvel_essai(
    racine: str,
    ident: str,
    sauvegarde: str,
    openupgrade: str = CHEMIN_OPENUPGRADE,
    lanceur: LanceurProgramme | None = None,
    journal: Journal | None = None,
    arrets: str | None = None,
) -> str:
    """Étape 6 : copie fraîche, même montée, zéro écart exigé.

    Rôle : la base du client a vécu depuis la première copie ; on refait
    tout sur une copie du jour, juste avant la bascule (ADR-0010).
    Paramètres : racine ; ident — montée qui a reçu le feu vert ;
    sauvegarde — nouvelle sauvegarde .zip ; openupgrade ; lanceur ;
    journal ; arrets — dossier des fichiers d'arrêt (ADR-0016).
    Retour : statut du nouvel essai (« attente_feu_vert » = bon).
    Erreurs : ErreurMontee (feu vert absent, autre base, autre version) ;
    ErreurSauvegarde.
    Usages : scripts/concorde_montee (nouvel-essai), service de montée.
    """
    premiere = Montee(racine, ident, openupgrade, lanceur, journal)
    if premiere.etat["etapes"]["feu_vert"].get("statut") != VERTE:
        raise ErreurMontee("Nouvel essai impossible : pas de feu vert.")
    essai = creer(racine, sauvegarde, premiere.etat["arrivee"], journal)
    if (
        essai["base_client"] != premiere.etat["base_client"]
        or essai["depart"] != premiere.etat["depart"]
    ):
        raise ErreurMontee(
            "La nouvelle sauvegarde n'est pas celle de la même base, à la "
            "même version (%s, Odoo %d)."
            % (essai["base_client"], essai["depart"])
        )
    statut = Montee(
        racine,
        essai["id"],
        openupgrade,
        lanceur,
        journal,
        arrets,
        ident,
    ).circuit()
    premiere._etape(
        "nouvel_essai",
        VERTE if statut == ATTENTE else BLOQUEE,
        (
            None
            if statut == ATTENTE
            else "Le nouvel essai ne passe pas (%s)." % statut
        ),
        {"montee": essai["id"], "statut": statut},
    )
    return statut


def fin_de_journal(chemin: str) -> str:
    """Dernières lignes d'un journal de la montée (pour l'écran)."""
    return fin_de_sortie("", chemin)
