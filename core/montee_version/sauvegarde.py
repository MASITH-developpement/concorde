# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Sauvegarde Odoo (.zip) : relire celle du client, produire la base montée.

Format standard d'Odoo (gestionnaire de bases) : `dump.sql` (pg_dump en
texte), `filestore/` (pièces jointes) et `manifest.json` (version, nom de
la base). Seuls ces trois éléments sont lus ; un chemin qui sortirait du
dossier d'extraction est refusé.
"""

import hashlib
import json
import os
import shutil
import zipfile
from typing import Any, TypedDict

from .openupgrade import version_majeure

NOM_DUMP = "dump.sql"
NOM_MANIFESTE = "manifest.json"
DOSSIER_PIECES = "filestore"
_BLOC = 1 << 20
PG_DEFAUT = 13
PG_MIN = 10
PG_MAX = 17


class ErreurSauvegarde(ValueError):
    """Sauvegarde Odoo refusée (forme, contenu ou chemin dangereux)."""


class InfoSauvegarde(TypedDict):
    """Ce que dit une sauvegarde, avant toute restauration."""

    nom: str
    octets: int
    sha256: str
    octets_decompresses: int
    pieces_jointes: int
    version: str | None
    base: str | None
    pg_version: int


def empreinte_fichier(chemin: str) -> str:
    """SHA-256 d'un fichier, lu par blocs.

    Rôle : prouver dans le rapport quelle sauvegarde a été montée et
    laquelle est livrée.
    Paramètres : chemin — fichier.
    Retour : empreinte hexadécimale.
    Erreurs : OSError.
    Usages : examiner_sauvegarde, ecrire_sauvegarde.
    """
    calcul = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(_BLOC), b""):
            calcul.update(bloc)
    return calcul.hexdigest()


def version_postgres(texte: object) -> int:
    """Version majeure de PostgreSQL du client (manifest.json).

    Rôle : restaurer la base dans la même version majeure que chez le
    client, pour que sa sauvegarde se recharge sans surprise.
    Paramètres : texte — « pg_version » du manifeste (« 13.4 », « 9.6 »),
    ou None.
    Retour : version majeure (13 si absente).
    Erreurs : ErreurSauvegarde si elle est illisible ou hors de 10 à 17.
    Usages : examiner_sauvegarde.
    """
    if texte is None:
        return PG_DEFAUT
    majeure = str(texte).strip().split(".", 1)[0]
    if not majeure.isdigit() or not PG_MIN <= int(majeure) <= PG_MAX:
        raise ErreurSauvegarde(
            "Version de PostgreSQL du client non prise en charge : %r "
            "(attendu %d à %d)." % (texte, PG_MIN, PG_MAX)
        )
    return int(majeure)


def _membres_surs(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Membres utiles (dump, manifeste, pièces jointes), chemins vérifiés."""
    membres = []
    for membre in archive.infolist():
        nom = membre.filename
        if nom.startswith("/") or ".." in nom.split("/") or "\\" in nom:
            raise ErreurSauvegarde(
                "Chemin refusé dans la sauvegarde : %r" % nom
            )
        if nom in (NOM_DUMP, NOM_MANIFESTE) or (
            nom.startswith(DOSSIER_PIECES + "/") and not membre.is_dir()
        ):
            membres.append(membre)
    return membres


def examiner_sauvegarde(chemin: str) -> InfoSauvegarde:
    """Relit une sauvegarde Odoo sans l'extraire.

    Rôle : refuser tout de suite une sauvegarde inutilisable, et connaître
    sa taille réelle pour le garde-fou du disque (ADR-0012).
    Paramètres : chemin — fichier .zip déposé.
    Retour : InfoSauvegarde (version et base lues dans manifest.json,
    None s'il manque).
    Erreurs : ErreurSauvegarde (pas un zip, pas de dump.sql, manifeste
    illisible, chemin dangereux) ; OSError.
    Usages : montee.creer, scripts/concorde_montee, tests.
    """
    try:
        archive = zipfile.ZipFile(chemin)
    except zipfile.BadZipFile as exc:
        raise ErreurSauvegarde(
            "Ce n'est pas une sauvegarde Odoo (.zip) : %s" % exc
        ) from exc
    with archive:
        membres = _membres_surs(archive)
        noms = {membre.filename for membre in membres}
        if NOM_DUMP not in noms:
            raise ErreurSauvegarde(
                "Sauvegarde sans %s : faire une sauvegarde Odoo « zip "
                "(avec pièces jointes) »." % NOM_DUMP
            )
        manifeste: dict[str, Any] = {}
        if NOM_MANIFESTE in noms:
            try:
                manifeste = json.loads(archive.read(NOM_MANIFESTE))
            except ValueError as exc:
                raise ErreurSauvegarde("manifest.json illisible.") from exc
        version = manifeste.get("version")
        if version is not None:
            version_majeure(str(version))
        return {
            "nom": os.path.basename(chemin),
            "octets": os.path.getsize(chemin),
            "sha256": empreinte_fichier(chemin),
            "octets_decompresses": sum(membre.file_size for membre in membres),
            "pieces_jointes": sum(
                1 for nom in noms if nom.startswith(DOSSIER_PIECES + "/")
            ),
            "version": None if version is None else str(version),
            "base": manifeste.get("db_name"),
            "pg_version": version_postgres(manifeste.get("pg_version")),
        }


def extraire_sauvegarde(chemin: str, dossier: str) -> tuple[str, str]:
    """Extrait le dump et les pièces jointes dans `dossier`.

    Rôle : préparer la restauration dans le volume chiffré.
    Paramètres : chemin — sauvegarde .zip ; dossier — destination (créée).
    Retour : (chemin de dump.sql, dossier des pièces jointes, créé même
    vide).
    Erreurs : ErreurSauvegarde (chemin dangereux, dump absent) ; OSError.
    Usages : montee.restaurer.
    """
    os.makedirs(os.path.join(dossier, DOSSIER_PIECES), exist_ok=True)
    with zipfile.ZipFile(chemin) as archive:
        membres = _membres_surs(archive)
        if NOM_DUMP not in {membre.filename for membre in membres}:
            raise ErreurSauvegarde("Sauvegarde sans %s." % NOM_DUMP)
        for membre in membres:
            cible = os.path.join(dossier, membre.filename)
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            with archive.open(membre) as source, open(cible, "wb") as copie:
                shutil.copyfileobj(source, copie, _BLOC)
    return (
        os.path.join(dossier, NOM_DUMP),
        os.path.join(dossier, DOSSIER_PIECES),
    )


def ecrire_sauvegarde(
    chemin: str, dump: str, pieces: str, manifeste: dict[str, Any]
) -> str:
    """Produit une sauvegarde Odoo standard ; rend son empreinte.

    Rôle : livrer la base montée dans le format que le client sait
    restaurer (gestionnaire de bases d'Odoo).
    Paramètres : chemin — .zip à écrire ; dump — dump.sql de la base
    montée ; pieces — dossier des pièces jointes ; manifeste — contenu de
    manifest.json.
    Retour : SHA-256 du .zip écrit.
    Erreurs : OSError.
    Usages : montee.livrer.
    """
    temporaire = chemin + ".tmp"
    with zipfile.ZipFile(
        temporaire, "w", zipfile.ZIP_DEFLATED, allowZip64=True
    ) as archive:
        archive.write(dump, NOM_DUMP)
        for parent, _, noms in os.walk(pieces):
            for nom in sorted(noms):
                complet = os.path.join(parent, nom)
                relatif = os.path.relpath(complet, pieces)
                archive.write(complet, DOSSIER_PIECES + "/" + relatif)
        archive.writestr(
            NOM_MANIFESTE, json.dumps(manifeste, indent=4, ensure_ascii=False)
        )
    os.replace(temporaire, chemin)
    return empreinte_fichier(chemin)
