# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écran Transferts (ADR-0011) : connexions, dépôts, transferts, feu vert.

Aucune règle de transfert ici : l'écran appelle l'annuaire des connexions
(core/connecteurs/connexions.py) et le moteur des 7 étapes
(core/connecteurs/transfert.py). Un secret saisi est écrit aussitôt dans
le fichier de secrets ; aucune réponse n'en contient jamais.

Les chemins des fichiers FEC sont choisis par CONCORDE, jamais par le
navigateur : dépôts dans <données>/depots, FEC produits dans
<données>/sorties.
"""

import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol

from core.connecteurs import transfert
from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import (
    Annuaire,
    ErreurAnnuaire,
    FicheConnexion,
)
from core.connecteurs.fec import NOM_FEC, ConnecteurFec
from core.connecteurs.registre import REGISTRE, classe_connecteur
from core.connecteurs.secrets import (
    CHEMIN_SECRETS,
    ErreurSecrets,
    ecrire_variable,
    nom_variable,
)
from core.fichier_json import ecrire_json_atomique
from core.guardian import Guardian
from core.journal import Journal
from core.mapping import ErreurMapping
from core.migration.correspondance import ErreurTable, charger_table

if (
    TYPE_CHECKING
):  # import seulement pour les types : serveur importe ce module
    from interface.serveur import Taches

# Objet JSON échangé avec le navigateur (comme dans interface/serveur.py).
ObjetJson = dict[str, Any]

DEPOT_MAX_MO_DEFAUT = 200
TABLE_MAX_OCTETS = 5 * 1024 * 1024
_BLOC = 1 << 16
_IDENT_TRANSFERT = re.compile(r"^T\d{14}-[0-9a-f]{4}$")
_JETON_TABLE = re.compile(r"^[0-9a-f]{32}$")


class FluxEntrant(Protocol):
    """Corps d'une requête : ce qui se lit par blocs (rfile du serveur)."""

    def read(self, taille: int = -1, /) -> bytes:
        """Lit au plus `taille` octets ; b"" à la fin."""


class ErreurEcran(ValueError):
    """Demande refusée par l'écran Transferts (la cause est nommée)."""


# Refus rendus au navigateur avec leur cause (HTTP 400).
ERREURS_ECRAN = (
    ErreurEcran,
    ErreurAnnuaire,
    ErreurConnexion,
    ErreurSecrets,
    transfert.ErreurTransfert,
    ErreurTable,
    ErreurMapping,
    ValueError,
    OSError,
)


def taille_depot_max(
    environnement: Mapping[str, str],
    variable: str = "CONCORDE_DEPOT_MAX_MO",
    defaut_mo: int = DEPOT_MAX_MO_DEFAUT,
) -> int:
    """Taille maximale d'un fichier déposé, en octets.

    Rôle : plafond réglable sans toucher au code (ADR-0011, arbitrage 2).
    Paramètres : environnement — variables du service (os.environ) ;
    variable — nom de la variable, en mégaoctets ; defaut_mo — valeur
    sans variable (200 Mo pour un FEC).
    Retour : le plafond en octets.
    Erreurs : ValueError si la variable n'est pas un entier positif (le
    service refuse alors de démarrer, avec la cause).
    Usages : EcranTransferts (FEC), EcranMontees (sauvegardes Odoo).
    """
    texte = environnement.get(variable, "").strip()
    if not texte:
        return defaut_mo * 1024 * 1024
    if not texte.isdigit() or int(texte) == 0:
        raise ValueError(
            "%s doit être un nombre entier de Mo (reçu : %r)."
            % (variable, texte)
        )
    return int(texte) * 1024 * 1024


def recevoir_fichier(
    flux: FluxEntrant, taille: int, chemin: str, taille_max: int
) -> None:
    """Recopie le corps d'une requête dans un fichier, par blocs.

    Rôle : recevoir un fichier envoyé par le navigateur sans le charger
    en mémoire, en refusant ce qui dépasse le plafond avant d'écrire.
    Paramètres : flux — corps de la requête ; taille — Content-Length ;
    chemin — fichier à écrire (son dossier est créé en 700) ;
    taille_max — plafond en octets.
    Retour : aucun.
    Erreurs : ErreurEcran (fichier vide, trop gros, envoi interrompu ; le
    fichier partiel est alors effacé) ; OSError.
    Usages : EcranTransferts.deposer, EcranTransferts.recevoir_table.
    """
    if taille <= 0:
        raise ErreurEcran("Fichier vide ou taille inconnue.")
    if taille > taille_max:
        raise ErreurEcran(
            "Fichier trop gros : %.1f Mo (maximum %d Mo)."
            % (taille / 1048576, taille_max // 1048576)
        )
    os.makedirs(os.path.dirname(chemin), mode=0o700, exist_ok=True)
    restant = taille
    try:
        with open(chemin, "wb") as fichier:
            while restant:
                bloc = flux.read(min(_BLOC, restant))
                if not bloc:
                    raise ErreurEcran("Envoi interrompu : fichier incomplet.")
                fichier.write(bloc)
                restant -= len(bloc)
    except BaseException:
        if os.path.exists(chemin):
            os.remove(chemin)
        raise


def chemin_dans(racine: str, chemin: str) -> bool:
    """Vrai si `chemin` est bien à l'intérieur du dossier `racine`.

    Rôle : un seul contrôle contre la sortie d'un dossier (« .. », liens).
    Paramètres : racine — dossier autorisé ; chemin — chemin à vérifier.
    Retour : True si le chemin réel est sous la racine réelle.
    Erreurs : aucune.
    Usages : EcranTransferts (dépôts, retrait, fichiers d'un transfert).
    """
    reel = os.path.realpath(chemin)
    return reel.startswith(os.path.realpath(racine) + os.sep)


def texte_corps(corps: Mapping[str, Any], cle: str) -> str:
    """Champ texte du corps d'une requête, sans espaces ('' si absent).

    Usages : EcranTransferts, EcranMontees.
    """
    valeur = corps.get(cle)
    return valeur.strip() if isinstance(valeur, str) else ""


class EcranTransferts:
    """Ce que l'écran Transferts peut faire, branché sur les tâches."""

    def __init__(
        self,
        dossier: str,
        taches: "Taches",
        journal: Journal,
        fichier_secrets: str = CHEMIN_SECRETS,
        environnement: Mapping[str, str] | None = None,
    ) -> None:
        """Prépare l'annuaire et les dossiers ; branche les deux tâches.

        Lève ValueError si CONCORDE_DEPOT_MAX_MO est invalide.
        """
        self.annuaire = Annuaire(
            os.path.join(dossier, "connexions.json"), fichier_secrets
        )
        self.racine = os.path.join(dossier, "transferts")
        self.depots = os.path.join(dossier, "depots")
        self.sorties = os.path.join(dossier, "sorties")
        self.tables = os.path.join(dossier, "tables")
        self.depot_max = taille_depot_max(
            os.environ if environnement is None else environnement
        )
        self.taches = taches
        self.journal = journal
        taches.travaux["transfert"] = self._travail_transfert
        taches.travaux["feu_vert"] = self._travail_feu_vert
        taches.annulations["transfert"] = self._defaire_transfert
        taches.annulations["feu_vert"] = self._defaire_feu_vert

    # --- connexions ----------------------------------------------------------
    def logiciels(self) -> ObjetJson:
        """Logiciels branchés et ce que chacun demande (formulaire d'ajout)."""
        return {
            "depot_max": self.depot_max,
            "logiciels": [
                {
                    "logiciel": nom,
                    "libelle": classe.libelle,
                    "lecture": classe.capacites["lecture"],
                    "ecriture": classe.capacites["ecriture"],
                    "fichier": nom == ConnecteurFec.logiciel,
                    "parametres": (
                        []
                        if nom == ConnecteurFec.logiciel
                        else list(classe.parametres_requis)
                    ),
                    "facultatifs": (
                        []
                        if nom == ConnecteurFec.logiciel
                        else list(classe.parametres_facultatifs)
                    ),
                    "secrets": list(classe.secrets_requis),
                }
                for nom, classe in sorted(REGISTRE.items())
            ],
        }

    def _usage_fec(self, fiche: FicheConnexion) -> str | None:
        """« source » (dépôt), « destination » (FEC produit) ou None."""
        if fiche["logiciel"] != ConnecteurFec.logiciel:
            return None
        if "chemin" in fiche["parametres"]:
            return "source"
        return "destination"

    def _depot(self, fiche: FicheConnexion) -> ObjetJson | None:
        """Fiche du dernier FEC déposé pour une connexion source, ou None."""
        chemin = fiche["parametres"].get("chemin", "")
        description = os.path.join(os.path.dirname(chemin), "depot.json")
        if not chemin or not os.path.isfile(description):
            return None
        with open(description, encoding="utf-8") as fichier:
            depot: ObjetJson = json.load(fichier)
        return depot

    def _decrire(self, fiche: FicheConnexion) -> ObjetJson:
        """Ce que l'écran affiche d'une connexion : jamais de secret."""
        classe = classe_connecteur(fiche["logiciel"])
        description: ObjetJson = {
            "id": fiche["id"],
            "logiciel": fiche["logiciel"],
            "logiciel_libelle": classe.libelle,
            "libelle": fiche["libelle"],
            "parametres": {
                nom: valeur
                for nom, valeur in fiche["parametres"].items()
                if nom not in ConnecteurFec.parametres_facultatifs
            },
            "connexion_test": fiche["connexion_test"],
            "cree_le": fiche["cree_le"],
            "dernier_test": fiche["dernier_test"],
            "derniere_info": fiche["derniere_info"],
            "lecture": classe.capacites["lecture"],
            "ecriture": classe.capacites["ecriture"],
            "usage": self._usage_fec(fiche),
            "depot": self._depot(fiche),
        }
        try:
            description["secrets"] = self.annuaire.secrets_renseignes(
                fiche["id"]
            )
        except ErreurSecrets as exc:
            description["secrets"] = {}
            description["secrets_erreur"] = str(exc)
        return description

    def connexions(self) -> list[ObjetJson]:
        """Toutes les connexions, décrites pour l'écran."""
        return [self._decrire(fiche) for fiche in self.annuaire.lister()]

    def ajouter(self, corps: Mapping[str, Any]) -> ObjetJson:
        """Ajoute une connexion ; rend sa description.

        Pour un FEC, CONCORDE choisit le chemin : `usage` « source » (un
        fichier sera déposé) ou « destination » (dossier des FEC produits).
        Lève ErreurEcran, ErreurAnnuaire ou ErreurConnexion.
        """
        logiciel = texte_corps(corps, "logiciel")
        recus = corps.get("parametres") or {}
        if not isinstance(recus, dict) or not all(
            isinstance(valeur, str) for valeur in recus.values()
        ):
            raise ErreurEcran("Paramètres attendus en texte.")
        parametres = {
            str(nom): valeur.strip()
            for nom, valeur in recus.items()
            if valeur.strip()
        }
        if logiciel == ConnecteurFec.logiciel:
            if parametres:
                raise ErreurEcran(
                    "FEC : aucun chemin à donner, CONCORDE range lui-même "
                    "les fichiers."
                )
            dossier_fec = uuid.uuid4().hex
            usage = texte_corps(corps, "usage")
            if usage == "source":
                parametres = {
                    "chemin": os.path.join(self.depots, dossier_fec, NOM_FEC)
                }
            elif usage == "destination":
                parametres = {
                    "dossier": os.path.join(self.sorties, dossier_fec)
                }
            else:
                raise ErreurEcran(
                    "FEC : choisir « source » (fichier déposé) ou "
                    "« destination » (FEC produit par CONCORDE)."
                )
        fiche = self.annuaire.ajouter(
            logiciel,
            texte_corps(corps, "libelle"),
            parametres,
            texte_corps(corps, "connexion_test") or None,
        )
        self.journal.dire(
            "Connexion ajoutée : %s (%s)" % (fiche["libelle"], logiciel),
            "info",
        )
        return self._decrire(fiche)

    def ecrire_secret(
        self, ident: str, corps: Mapping[str, Any]
    ) -> dict[str, bool]:
        """Écrit un secret saisi dans l'écran ; rend « renseigné ou non ».

        La valeur n'est ni gardée, ni journalisée, ni renvoyée.
        Lève ErreurEcran (secret inconnu du logiciel), ErreurAnnuaire,
        ErreurSecrets (valeur vide ou sur plusieurs lignes) ou OSError.
        """
        fiche = self.annuaire.obtenir(ident)
        champ = texte_corps(corps, "champ")
        if champ not in classe_connecteur(fiche["logiciel"]).secrets_requis:
            raise ErreurEcran(
                "Secret inconnu pour ce logiciel : %s" % (champ or "(vide)")
            )
        valeur = corps.get("valeur")
        ecrire_variable(
            self.annuaire.fichier_secrets,
            nom_variable(ident, champ),
            valeur if isinstance(valeur, str) else "",
        )
        self.journal.dire(
            "Secret « %s » enregistré pour %s" % (champ, fiche["libelle"]),
            "info",
        )
        return self.annuaire.secrets_renseignes(ident)

    def tester(self, ident: str) -> ObjetJson:
        """Teste une connexion ; rend sa description à jour.

        Lève ErreurAnnuaire, ErreurSecrets ou ErreurConnexion (la cause
        donnée par le logiciel).
        """
        self.annuaire.tester(ident, Journal())
        fiche = self.annuaire.obtenir(ident)
        self.journal.dire("Connexion testée : %s" % fiche["libelle"], "ok")
        return self._decrire(fiche)

    def retirer(self, ident: str) -> ObjetJson:
        """Retire une connexion, ses secrets et son FEC déposé ; rend {"ok"}.

        Les FEC produits pour une destination restent dans <sorties>.
        Lève ErreurAnnuaire, ErreurSecrets ou OSError.
        """
        fiche = self.annuaire.obtenir(ident)
        self.annuaire.retirer(ident)
        chemin = fiche["parametres"].get("chemin", "")
        dossier_depot = os.path.dirname(chemin)
        if (
            fiche["logiciel"] == ConnecteurFec.logiciel
            and chemin_dans(self.depots, chemin)
            and os.path.isdir(dossier_depot)
        ):
            shutil.rmtree(dossier_depot)
        self.journal.dire("Connexion retirée : %s" % fiche["libelle"], "info")
        return {"ok": True}

    def deposer(
        self, ident: str, nom: str, flux: FluxEntrant, taille: int
    ) -> ObjetJson:
        """Reçoit un FEC pour une connexion source et le relit aussitôt.

        Un fichier refusé n'est pas gardé : l'ancien dépôt reste en place.
        Retour : fiche du dépôt (nom d'origine, taille, lignes, écritures,
        totaux en centimes).
        Lève ErreurEcran, ErreurAnnuaire, ErreurConnexion (FEC refusé par
        la lecture stricte, avec la cause) ou OSError.
        """
        fiche = self.annuaire.obtenir(ident)
        chemin = fiche["parametres"].get("chemin", "")
        if fiche["logiciel"] != ConnecteurFec.logiciel or not chemin_dans(
            self.depots, chemin
        ):
            raise ErreurEcran(
                "Cette connexion ne reçoit pas de fichier déposé."
            )
        recu = chemin + ".recu"
        recevoir_fichier(flux, taille, recu, self.depot_max)
        try:
            lot = ConnecteurFec({"chemin": recu}).lire(
                {"du": None, "au": None}, Journal()
            )
        except ErreurConnexion:
            os.remove(recu)
            raise
        os.replace(recu, chemin)
        totaux = lot.totaux()
        depot: ObjetJson = {
            "nom": os.path.basename(nom)[:200] or NOM_FEC,
            "octets": taille,
            "depose_le": datetime.now().isoformat(timespec="seconds"),
            "lignes": totaux["lignes"],
            "ecritures": totaux["ecritures"],
            "debit": totaux["debit"],
            "credit": totaux["credit"],
        }
        ecrire_json_atomique(
            os.path.join(os.path.dirname(chemin), "depot.json"),
            depot,
            ascii_seul=False,
        )
        self.journal.dire(
            "FEC déposé pour %s : %s (%d lignes)"
            % (fiche["libelle"], depot["nom"], depot["lignes"]),
            "ok",
        )
        return depot

    # --- correspondance des comptes ------------------------------------------
    def recevoir_table(
        self, nom: str, flux: FluxEntrant, taille: int
    ) -> ObjetJson:
        """Reçoit une table de correspondance (xlsx, csv, json).

        Retour : {"jeton", "comptes"} ; le jeton sert à la demande de
        transfert. Lève ErreurEcran, ErreurTable, ErreurMapping,
        ValueError (contenu illisible) ou OSError.
        """
        jeton = uuid.uuid4().hex
        brut_chemin = os.path.join(self.tables, jeton + ".brut")
        recevoir_fichier(flux, taille, brut_chemin, TABLE_MAX_OCTETS)
        try:
            with open(brut_chemin, "rb") as fichier:
                table = charger_table(fichier.read(), os.path.basename(nom))
        finally:
            os.remove(brut_chemin)
        if not table:
            raise ErreurEcran("Table de correspondance vide.")
        ecrire_json_atomique(
            os.path.join(self.tables, jeton + ".json"), table, ascii_seul=False
        )
        return {"jeton": jeton, "comptes": len(table)}

    def _table(self, jeton: object) -> dict[str, str]:
        """Table reçue plus tôt, par son jeton. Lève ErreurEcran."""
        if not isinstance(jeton, str) or not _JETON_TABLE.match(jeton):
            raise ErreurEcran("Table de correspondance inconnue.")
        chemin = os.path.join(self.tables, jeton + ".json")
        if not os.path.isfile(chemin):
            raise ErreurEcran("Table de correspondance inconnue.")
        with open(chemin, encoding="utf-8") as fichier:
            table: dict[str, str] = json.load(fichier)
        return table

    # --- transferts ----------------------------------------------------------
    def _libelle(self, ident: str) -> str:
        """Libellé d'une connexion, ou « (retirée) <id> »."""
        try:
            return self.annuaire.obtenir(ident)["libelle"]
        except ErreurAnnuaire:
            return "(retirée) %s" % ident

    def lancer_transfert(self, corps: Mapping[str, Any]) -> str:
        """Valide la demande puis lance les étapes 1 à 4 ; rend l'id de tâche.

        Corps : source, destinations (liste), du, au (AAAA-MM-JJ ou vide),
        identique {destination: bool}, tables {destination: jeton}.
        Lève ErreurEcran, ErreurTransfert ou ValueError (rien n'est lancé).
        """
        destinations = corps.get("destinations") or []
        identique = corps.get("identique") or {}
        tables = corps.get("tables") or {}
        if (
            not isinstance(destinations, list)
            or not all(isinstance(ident, str) for ident in destinations)
            or not isinstance(identique, dict)
            or not isinstance(tables, dict)
        ):
            raise ErreurEcran("Demande de transfert mal formée.")
        demande: transfert.DemandeTransfert = {
            "source": texte_corps(corps, "source"),
            "destinations": destinations,
            "du": texte_corps(corps, "du") or None,
            "au": texte_corps(corps, "au") or None,
            "filtres": [],
            "tables": {
                ident: self._table(tables[ident])
                for ident in destinations
                if tables.get(ident)
            },
            "identique": {
                ident: identique.get(ident) is True for ident in destinations
            },
        }
        transfert.valider_demande(self.annuaire, demande)
        if demande["du"] and demande["au"] and demande["du"] > demande["au"]:
            raise ErreurEcran("La date de début est après la date de fin.")
        nom = "%s → %s" % (
            self._libelle(demande["source"]),
            ", ".join(self._libelle(ident) for ident in destinations),
        )
        ident_tache = self.taches.lancer(
            "transfert",
            None,
            nom,
            "",
            {"demande": demande, "transfert": transfert.nouvel_identifiant()},
        )
        self.journal.dire("Transfert lancé : %s" % nom, "info")
        return ident_tache

    def _travail_transfert(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « transfert » : étapes 1 à 4, rapport par destination."""
        etat = transfert.creer(
            self.annuaire,
            tache["params"]["demande"],
            self.racine,
            journal=journal,
            guardian=guardian,
            ident=tache["params"]["transfert"],
        )
        tache["resultat"] = {
            "transfert": etat["id"],
            "destinations": {
                ident: etat_dest["statut"]
                for ident, etat_dest in etat["destinations"].items()
            },
        }

    def _defaire_transfert(
        self, tache: ObjetJson, journal: Journal
    ) -> ObjetJson:
        """Transfert arrêté : efface les écritures de test (ADR-0016)."""
        parametres = tache["params"]
        return transfert.defaire(
            self.annuaire,
            parametres["transfert"],
            parametres["demande"]["destinations"],
            False,
            self.racine,
            journal,
        )

    def _defaire_feu_vert(
        self, tache: ObjetJson, journal: Journal
    ) -> ObjetJson:
        """Feu vert arrêté : efface test et production (ADR-0016)."""
        parametres = tache["params"]
        return transfert.defaire(
            self.annuaire,
            parametres["transfert"],
            [parametres["destination"]],
            True,
            self.racine,
            journal,
        )

    def _verifier_ident(self, ident: str) -> None:
        """Refuse un identifiant de transfert mal formé (ErreurEcran)."""
        if not _IDENT_TRANSFERT.match(ident):
            raise ErreurEcran("Transfert inconnu : %s" % ident)

    def lister_transferts(self) -> list[ObjetJson]:
        """Transferts enregistrés, du plus récent au plus ancien."""
        if not os.path.isdir(self.racine):
            return []
        resumes: list[ObjetJson] = []
        for ident in sorted(os.listdir(self.racine), reverse=True):
            if not _IDENT_TRANSFERT.match(ident):
                continue
            etat = transfert.charger(ident, self.racine)
            resumes.append(
                {
                    "id": ident,
                    "cree_le": etat["cree_le"],
                    "source": self._libelle(etat["demande"]["source"]),
                    "destinations": [
                        {
                            "id": ident_dest,
                            "libelle": self._libelle(ident_dest),
                            "statut": etat_dest["statut"],
                        }
                        for ident_dest, etat_dest in etat[
                            "destinations"
                        ].items()
                    ],
                }
            )
        return resumes

    def detail_transfert(self, ident: str) -> ObjetJson:
        """État complet d'un transfert, avec les libellés et ses fichiers.

        Lève ErreurEcran ou ErreurTransfert (inconnu).
        """
        self._verifier_ident(ident)
        etat = transfert.charger(ident, self.racine)
        dossier = os.path.join(self.racine, ident)
        fichiers = sorted(
            os.path.relpath(os.path.join(parent, nom), dossier)
            for parent, _, noms in os.walk(dossier)
            for nom in noms
            if nom != "transfert.json"
        )
        connexions = [etat["demande"]["source"], *etat["destinations"]]
        detail: ObjetJson = dict(etat)
        detail["libelles"] = {
            ident_cx: self._libelle(ident_cx) for ident_cx in connexions
        }
        detail["fichiers"] = fichiers
        return detail

    def chemin_fichier(self, ident: str, relatif: str) -> str:
        """Chemin d'un fichier d'un transfert, sans sortir de son dossier.

        Lève ErreurEcran si le transfert ou le fichier est inconnu.
        """
        self._verifier_ident(ident)
        dossier = os.path.join(self.racine, ident)
        chemin = os.path.join(dossier, relatif)
        if (
            not relatif
            or not chemin_dans(dossier, chemin)
            or not os.path.isfile(chemin)
        ):
            raise ErreurEcran("Fichier inconnu.")
        return chemin

    def feu_vert(self, ident: str, corps: Mapping[str, Any], ip: str) -> str:
        """Contrôle le feu vert, lance les étapes 6 et 7 ; rend l'id de tâche.

        Corps : destination, confirmation (libellé retapé), sauvegarde_du
        (AAAA-MM-JJ). Lève ErreurEcran, ErreurTransfert ou ValueError :
        rien n'est alors lancé.
        """
        self._verifier_ident(ident)
        ident_dest = texte_corps(corps, "destination")
        confirmation = texte_corps(corps, "confirmation")
        texte_date = texte_corps(corps, "sauvegarde_du")
        if not texte_date:
            raise ErreurEcran(
                "Date de la sauvegarde de la destination requise."
            )
        sauvegarde_du = date.fromisoformat(texte_date)
        transfert.controler_feu_vert(
            self.annuaire,
            ident,
            ident_dest,
            confirmation,
            sauvegarde_du,
            self.racine,
        )
        nom = "%s → %s" % (ident, self._libelle(ident_dest))
        ident_tache = self.taches.lancer(
            "feu_vert",
            None,
            nom,
            "",
            {
                "transfert": ident,
                "destination": ident_dest,
                "confirmation": confirmation,
                "sauvegarde_du": sauvegarde_du.isoformat(),
                "par": "session de l'interface depuis %s" % ip,
            },
        )
        self.journal.dire("Feu vert donné : %s" % nom, "alerte")
        return ident_tache

    def _travail_feu_vert(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « feu vert » : nouveau test, puis transfert complet."""
        parametres = tache["params"]
        etat_dest = transfert.donner_feu_vert(
            self.annuaire,
            parametres["transfert"],
            parametres["destination"],
            parametres["confirmation"],
            date.fromisoformat(parametres["sauvegarde_du"]),
            parametres["par"],
            self.racine,
            journal=journal,
            guardian=guardian,
        )
        tache["resultat"] = {
            "transfert": parametres["transfert"],
            "destination": parametres["destination"],
            "statut": etat_dest["statut"],
        }
