# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Transfert : une source, une ou plusieurs destinations (ADR-0008, point 4).

La source est lue une fois ; sa photo (FEC) est gardée dans le dossier du
transfert. Chaque destination suit ensuite la même procédure, sans
dépendre des autres :

  1 données       lecture, filtres, batterie de contrôles
  2 concordance   correspondance des comptes, totaux au centime
  3 simulation    essai à blanc dans la destination (rien n'est écrit)
  4 test          écriture dans l'environnement de test, relue au centime
  -> rapport, puis ATTENTE DU FEU VERT
  5 feu vert      donné par Stéphane (nom de la destination retapé,
                  date de la sauvegarde de la destination)
  6 nouveau test  source relue, étapes 1 à 4 rejouées ; la source doit
                  être identique à celle du rapport
  7 transfert     écriture dans la destination, relue au centime

Une étape ne s'ouvre que si la précédente est bonne. Sans environnement de
test, la destination s'arrête après la simulation. Une seule écriture à la
fois par connexion (verrou par connexion).
"""

import copy
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, TypedDict

from ..analyser import Constat
from ..fichier_json import ecrire_json_atomique
from ..guardian import Guardian
from ..journal import Journal, ou_muet
from ..migration import controles, correspondance, export, filtres
from ..migration.circuit import constats_expliques, statut_constats
from ..migration.lot import CleTotaux, Lot, TotauxLot
from ..telecharger import ErreurFec
from .base import Connecteur, ErreurConnexion, PerimetreLecture
from .connexions import Annuaire, ErreurAnnuaire
from .secrets import ErreurSecrets

CHEMIN_TRANSFERTS = os.environ.get(
    "CONCORDE_TRANSFERTS", "/var/lib/concorde-interface/transferts"
)
ETAPES = (
    "donnees",
    "concordance",
    "simulation",
    "test",
    "feu_vert",
    "nouveau_test",
    "transfert",
)
CLES_TOTAUX: tuple[CleTotaux, ...] = ("lignes", "ecritures", "debit", "credit")
# Statuts d'une destination.
BLOQUEE = "bloquee"
SANS_TEST = "arretee_sans_test"
ATTENTE = "attente_feu_vert"
TRANSFEREE = "transferee"
# Erreurs d'un logiciel ou de l'annuaire, rapportées dans l'étape en cause.
ERREURS_CONNEXION = (ErreurConnexion, ErreurAnnuaire, ErreurSecrets)

_verrous: dict[str, threading.Lock] = {}
_verrou_des_verrous = threading.Lock()


class ErreurTransfert(ValueError):
    """Demande invalide, ou feu vert refusé (le motif est nommé)."""


class DemandeTransfert(TypedDict):
    """Ce qui est demandé : connexions, période, filtres, correspondances.

    `tables` et `identique` sont rangés par connexion destination : la
    correspondance des comptes vaut pour un couple source -> destination.
    """

    source: str
    destinations: list[str]
    du: str | None
    au: str | None
    filtres: list[dict[str, Any]]
    tables: dict[str, dict[str, str]]
    identique: dict[str, bool]


class EtatEtape(TypedDict, total=False):
    """Résultat d'une étape pour une destination."""

    statut: str
    erreur: str
    infos: dict[str, Any]
    constats: list[dict[str, Any]]
    fichiers: dict[str, str]


class EtatDestination(TypedDict, total=False):
    """Où en est une destination : statut, étapes, feu vert."""

    statut: str
    reference: str
    etapes: dict[str, EtatEtape]
    empreinte_lot: str
    totaux: TotauxLot
    feu_vert: dict[str, str]


class EtatTransfert(TypedDict):
    """État complet d'un transfert, écrit dans transfert.json."""

    id: str
    cree_le: str
    demande: DemandeTransfert
    photo_source: str | None
    destinations: dict[str, EtatDestination]


@contextmanager
def verrou_connexion(ident: str) -> Iterator[None]:
    """Une seule écriture à la fois dans une connexion.

    Rôle : deux transferts vers la même connexion passent l'un après
    l'autre (ADR-0008, point 7).
    Paramètres : ident — identifiant de la connexion écrite.
    Retour : gestionnaire de contexte (verrou tenu pendant le bloc).
    Erreurs : aucune.
    Usages : _tester, donner_feu_vert.
    """
    with _verrou_des_verrous:
        verrou = _verrous.setdefault(ident, threading.Lock())
    with verrou:
        yield


def empreinte_lot(lot: Lot) -> str:
    """Empreinte SHA-256 des lignes du lot (ordre et contenu).

    Rôle : savoir si la source a changé entre le rapport et le feu vert.
    Paramètres : lot.
    Retour : empreinte hexadécimale.
    Erreurs : aucune.
    Usages : _preparer_destination, donner_feu_vert.
    """
    texte = json.dumps(lot.lignes, sort_keys=True, default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _perimetre(demande: DemandeTransfert) -> PerimetreLecture:
    """Période de la demande, en dates."""
    return {
        "du": date.fromisoformat(demande["du"]) if demande["du"] else None,
        "au": date.fromisoformat(demande["au"]) if demande["au"] else None,
    }


def _dossier(racine: str, ident: str) -> str:
    """Dossier d'un transfert."""
    return os.path.join(racine, ident)


def _sauver(etat: EtatTransfert, racine: str) -> None:
    """Écrit transfert.json dans le dossier du transfert."""
    dossier = _dossier(racine, etat["id"])
    os.makedirs(dossier, exist_ok=True)
    ecrire_json_atomique(
        os.path.join(dossier, "transfert.json"),
        etat,
        ascii_seul=False,
        retrait=1,
        conversion=str,
    )


def charger(ident: str, racine: str = CHEMIN_TRANSFERTS) -> EtatTransfert:
    """État d'un transfert enregistré.

    Rôle : reprendre un transfert après le rapport (le feu vert peut venir
    après un redémarrage du service).
    Paramètres : ident — identifiant du transfert ; racine — dossier des
    transferts.
    Retour : EtatTransfert.
    Erreurs : ErreurTransfert si le transfert est inconnu.
    Usages : donner_feu_vert, interface.
    """
    chemin = os.path.join(_dossier(racine, ident), "transfert.json")
    if not os.path.isfile(chemin):
        raise ErreurTransfert("Transfert inconnu : %s" % ident)
    with open(chemin, encoding="utf-8") as fichier:
        etat: EtatTransfert = json.load(fichier)
    return etat


def _valider(annuaire_connexions: Annuaire, demande: DemandeTransfert) -> None:
    """Refuse une demande impossible, avant toute lecture."""
    if not demande["destinations"]:
        raise ErreurTransfert("Aucune destination.")
    if len(set(demande["destinations"])) != len(demande["destinations"]):
        raise ErreurTransfert("Une destination est donnée deux fois.")
    if demande["source"] in demande["destinations"]:
        raise ErreurTransfert(
            "La source ne peut pas être une destination : CONCORDE "
            "n'écrit jamais dans la source d'un transfert."
        )
    _perimetre(demande)  # dates invalides : ValueError tout de suite
    roles = [(demande["source"], "source")] + [
        (ident_destination, "destination")
        for ident_destination in demande["destinations"]
    ]
    for ident, role in roles:
        try:
            fiche = annuaire_connexions.obtenir(ident)
            capacites = annuaire_connexions.ouvrir(ident).capacites
        except ERREURS_CONNEXION as exc:
            raise ErreurTransfert("%s %s : %s" % (role, ident, exc)) from exc
        sait_faire = (
            capacites["lecture"] if role == "source" else capacites["ecriture"]
        )
        if not sait_faire:
            raise ErreurTransfert(
                "%s %s (%s) : ce logiciel ne sait pas %s."
                % (
                    role,
                    ident,
                    fiche["libelle"],
                    "lire" if role == "source" else "écrire",
                )
            )


def _bloquer(
    etat: EtatDestination, etape: str, detail: EtatEtape, journal: Journal
) -> tuple[EtatDestination, None]:
    """Arrête la destination à l'étape donnée, motif au journal."""
    detail["statut"] = BLOQUEE
    etat["etapes"][etape] = detail
    etat["statut"] = BLOQUEE
    journal.dire(
        "Étape %s bloquée%s"
        % (etape, " : " + detail["erreur"] if "erreur" in detail else ""),
        "erreur",
    )
    return etat, None


def _etat_etape(
    constats: Sequence[Constat], infos: dict[str, Any]
) -> EtatEtape:
    """État d'une étape jugée sur ses constats."""
    return {
        "statut": statut_constats(constats),
        "infos": infos,
        "constats": constats_expliques(constats),
    }


def _tester(
    annuaire_connexions: Annuaire,
    ident_dest: str,
    destination: Connecteur,
    lot: Lot,
    reference_test: str,
    journal: Journal,
) -> EtatEtape | None:
    """Écrit le lot dans l'environnement de test, le relit, compare.

    Retourne None s'il n'y a pas d'environnement de test.
    """
    fiche = annuaire_connexions.obtenir(ident_dest)
    cible: Connecteur | None
    if fiche["connexion_test"]:
        cible = annuaire_connexions.ouvrir(fiche["connexion_test"])
        ident_cible = fiche["connexion_test"]
    else:
        cible = destination.environnement_test()
        ident_cible = ident_dest + "#test"
    if cible is None:
        return None
    with verrou_connexion(ident_cible):
        ecrit = cible.ecrire(lot, reference_test, essai=False, journal=journal)
        if ecrit["erreurs"]:
            return {
                "statut": BLOQUEE,
                "erreur": "; ".join(ecrit["erreurs"]),
                "infos": {"ecriture": ecrit},
            }
        relu = cible.relire(reference_test, journal)
    ecart = export.comparer(lot, relu)
    return _etat_etape(
        ecart.constats, {"ecriture": ecrit, "relecture": ecart.infos}
    )


def _preparer_destination(
    annuaire_connexions: Annuaire,
    lot_source: Lot,
    demande: DemandeTransfert,
    ident_dest: str,
    references: tuple[str, str],
    dossier_dest: str,
    aujourd_hui: date | None,
    journal: Journal,
) -> tuple[EtatDestination, Lot | None]:
    """Étapes 1 à 4 pour une destination.

    Rôle : la même vérification avant le rapport et après le feu vert.
    Paramètres : annuaire ; lot_source — lu une fois, jamais modifié ;
    demande ; ident_dest — connexion destination ; references —
    (référence du transfert, référence du test) ; dossier_dest — dossier
    des fichiers de la destination ; aujourd_hui — date des contrôles ;
    journal.
    Retour : (état de la destination, lot prêt) ; lot None si une étape
    bloque ou s'il n'y a pas d'environnement de test.
    Erreurs : aucune (chaque erreur est rapportée dans son étape).
    Usages : creer, donner_feu_vert.
    """
    reference, reference_test = references
    etat: EtatDestination = {
        "statut": "en_cours",
        "reference": reference,
        "etapes": {nom_etape: {"statut": "non_jouee"} for nom_etape in ETAPES},
    }
    etapes = etat["etapes"]
    lot = copy.deepcopy(lot_source)

    journal.dire("Étape 1 — Vérifier les données", "etape")
    try:
        filtres.appliquer(lot, demande["filtres"], journal=journal)
    except filtres.ErreurFiltre as exc:
        return _bloquer(etat, "donnees", {"erreur": str(exc)}, journal)
    rapport_controles = controles.controler(lot, aujourd_hui, journal=journal)
    etapes["donnees"] = _etat_etape(
        rapport_controles.constats, rapport_controles.infos
    )
    if etapes["donnees"]["statut"] == BLOQUEE:
        return _bloquer(etat, "donnees", etapes["donnees"], journal)

    journal.dire("Étape 2 — Vérifier la concordance", "etape")
    rapport_correspondance = correspondance.appliquer(
        lot,
        demande["tables"].get(ident_dest),
        demande["identique"].get(ident_dest, False),
        journal=journal,
    )
    fichiers: dict[str, str] = {}
    a_arbitrer = rapport_correspondance.infos.pop("a_arbitrer", None) or {}
    if a_arbitrer:
        os.makedirs(dossier_dest, exist_ok=True)
        fichiers["a_arbitrer"] = os.path.join(dossier_dest, "a_arbitrer.xlsx")
        correspondance.ecrire_a_arbitrer(fichiers["a_arbitrer"], a_arbitrer)
    deja_retirees = len(lot_source.retirees)
    retirees_filtres = [ligne for ligne, _ in lot.retirees[deja_retirees:]]
    avant = lot_source.totaux()
    apres = lot.totaux(lot.lignes + retirees_filtres)
    rapport_correspondance.constat(
        "BLOQUANT",
        "TRF_ECART_CONCORDANCE",
        "Totaux différents entre la source et le lot (lot + lignes retirées)",
        [
            "%s : source %s, lot %s" % (cle, avant[cle], apres[cle])
            for cle in CLES_TOTAUX
            if avant[cle] != apres[cle]
        ],
    )
    etapes["concordance"] = _etat_etape(
        rapport_correspondance.constats, rapport_correspondance.infos
    )
    etapes["concordance"]["fichiers"] = fichiers
    if etapes["concordance"]["statut"] == BLOQUEE:
        return _bloquer(etat, "concordance", etapes["concordance"], journal)
    etat["empreinte_lot"] = empreinte_lot(lot)
    etat["totaux"] = lot.totaux()

    journal.dire("Étape 3 — Simuler le résultat (rien n'est écrit)", "etape")
    try:
        destination = annuaire_connexions.ouvrir(ident_dest)
        simulation = destination.ecrire(
            lot, reference, essai=True, journal=journal
        )
    except ERREURS_CONNEXION as exc:
        return _bloquer(etat, "simulation", {"erreur": str(exc)}, journal)
    etapes["simulation"] = {
        "statut": BLOQUEE if simulation["erreurs"] else "verte",
        "infos": {"ecriture": simulation},
    }
    if simulation["erreurs"]:
        etapes["simulation"]["erreur"] = "; ".join(simulation["erreurs"])
        return _bloquer(etat, "simulation", etapes["simulation"], journal)

    journal.dire("Étape 4 — Test de transfert", "etape")
    try:
        test = _tester(
            annuaire_connexions,
            ident_dest,
            destination,
            lot,
            reference_test,
            journal,
        )
    except ERREURS_CONNEXION as exc:
        return _bloquer(etat, "test", {"erreur": str(exc)}, journal)
    if test is None:
        etapes["test"] = {
            "statut": SANS_TEST,
            "erreur": "Aucun environnement de test pour cette destination : "
            "arrêt après la simulation (ADR-0008).",
        }
        etat["statut"] = SANS_TEST
        journal.dire(etapes["test"]["erreur"], "alerte")
        return etat, None
    etapes["test"] = test
    if test["statut"] == BLOQUEE:
        return _bloquer(etat, "test", test, journal)
    etat["statut"] = ATTENTE
    return etat, lot


def _photo_source(lot: Lot, dossier: str, journal: Journal) -> str | None:
    """Photo FEC de la source lue ; None (et alerte) si impossible."""
    chemin = os.path.join(dossier, "source", "FEC_source.txt")
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    try:
        export.ecrire_fec_lot(lot, chemin)
    except (OSError, ErreurFec) as exc:
        journal.dire("Photo de la source impossible : %s" % exc, "alerte")
        return None
    return chemin


def creer(
    annuaire_connexions: Annuaire,
    demande: DemandeTransfert,
    racine: str = CHEMIN_TRANSFERTS,
    aujourd_hui: date | None = None,
    journal: Journal | None = None,
    guardian: Guardian | None = None,
) -> EtatTransfert:
    """Crée un transfert et joue les étapes 1 à 4 pour chaque destination.

    Rôle : préparer le rapport sur lequel Stéphane donne (ou non) le feu
    vert. Rien n'est écrit dans une vraie destination.
    Paramètres : annuaire ; demande ; racine — dossier des transferts ;
    aujourd_hui — date des contrôles (dates futures) ; journal ;
    guardian — audit (par défaut, celui du serveur).
    Retour : EtatTransfert tel qu'écrit dans <racine>/<id>/transfert.json
    (dates en texte ISO), relu après écriture.
    Erreurs : ErreurTransfert si la demande est impossible (rien n'est
    alors lu ni écrit) ; ValueError si une date est invalide.
    Usages : interface (écran Transferts), tests.
    """
    journal_actif = ou_muet(journal)
    audit = guardian or Guardian()
    audit.self_check()
    _valider(annuaire_connexions, demande)
    ident = "T%s-%s" % (
        datetime.now().strftime("%Y%m%d%H%M%S"),
        uuid.uuid4().hex[:4],
    )
    dossier = _dossier(racine, ident)
    etat: EtatTransfert = {
        "id": ident,
        "cree_le": datetime.now().isoformat(timespec="seconds"),
        "demande": demande,
        "photo_source": None,
        "destinations": {},
    }
    journal_actif.dire(
        "Transfert %s : %s -> %s"
        % (ident, demande["source"], ", ".join(demande["destinations"])),
        "etape",
    )
    try:
        lot_source = annuaire_connexions.ouvrir(demande["source"]).lire(
            _perimetre(demande), journal_actif
        )
    except ERREURS_CONNEXION as exc:
        for ident_dest in demande["destinations"]:
            etat["destinations"][ident_dest] = {
                "statut": BLOQUEE,
                "etapes": {
                    "donnees": {
                        "statut": BLOQUEE,
                        "erreur": "Source illisible : %s" % exc,
                    }
                },
            }
        journal_actif.dire("Source illisible : %s" % exc, "erreur")
        _sauver(etat, racine)
        return charger(ident, racine)
    audit.tracer("transfert", "lecture", lot_source.source["empreinte"])
    etat["photo_source"] = _photo_source(lot_source, dossier, journal_actif)
    for ident_dest in demande["destinations"]:
        journal_actif.dire("Destination %s" % ident_dest, "etape")
        etat_dest, _ = _preparer_destination(
            annuaire_connexions,
            lot_source,
            demande,
            ident_dest,
            ("CONCORDE/%s" % ident, "CONCORDE/%s/test1" % ident),
            os.path.join(dossier, ident_dest),
            aujourd_hui,
            journal_actif,
        )
        etat["destinations"][ident_dest] = etat_dest
        audit.tracer("transfert", ident_dest, etat_dest["statut"])
        if etat_dest["statut"] == ATTENTE:
            journal_actif.dire(
                "%s : rapport prêt, en attente du feu vert" % ident_dest, "ok"
            )
    _sauver(etat, racine)
    return charger(ident, racine)


def donner_feu_vert(
    annuaire_connexions: Annuaire,
    ident: str,
    ident_dest: str,
    confirmation: str,
    sauvegarde_du: date,
    par: str,
    racine: str = CHEMIN_TRANSFERTS,
    aujourd_hui: date | None = None,
    journal: Journal | None = None,
    guardian: Guardian | None = None,
) -> EtatDestination:
    """Feu vert pour une destination : nouveau test, puis transfert.

    Rôle : étapes 5 à 7 (ADR-0008, point 4).
    Paramètres : annuaire ; ident — transfert ; ident_dest — destination ;
    confirmation — libellé de la destination, retapé ; sauvegarde_du —
    date de la sauvegarde de la destination ; par — qui donne le feu vert
    ; racine ; aujourd_hui ; journal ; guardian.
    Retour : état de la destination (statut « transferee » si tout est
    conforme), aussi écrit dans transfert.json.
    Erreurs : ErreurTransfert si le feu vert est refusé : transfert ou
    destination inconnus, destination pas en attente, libellé mal
    retapé, sauvegarde absente ou datée du futur. Rien n'est alors écrit.
    Usages : interface (écran Transferts), tests.
    """
    journal_actif = ou_muet(journal)
    jour = aujourd_hui or date.today()
    etat = charger(ident, racine)
    etat_dest = etat["destinations"].get(ident_dest)
    if etat_dest is None:
        raise ErreurTransfert("Destination inconnue : %s" % ident_dest)
    if etat_dest["statut"] != ATTENTE:
        raise ErreurTransfert(
            "%s n'attend pas de feu vert (statut %s)."
            % (ident_dest, etat_dest["statut"])
        )
    fiche = annuaire_connexions.obtenir(ident_dest)
    if confirmation.strip() != fiche["libelle"]:
        raise ErreurTransfert(
            "Le nom de la destination n'est pas retapé à l'identique : "
            "rien n'est parti."
        )
    if sauvegarde_du > jour:
        raise ErreurTransfert("Date de sauvegarde dans le futur.")
    audit = guardian or Guardian()
    audit.self_check()
    etapes = etat_dest["etapes"]
    etapes["feu_vert"] = {
        "statut": "verte",
        "infos": {
            "par": par,
            "le": datetime.now().isoformat(timespec="seconds"),
            "sauvegarde_du": sauvegarde_du.isoformat(),
        },
    }
    audit.tracer(
        "transfert", "feu_vert", "%s %s %s" % (ident, ident_dest, par)
    )

    def finir(statut: str, etape: str, detail: EtatEtape) -> EtatDestination:
        """Termine la destination, enregistre et rend son état."""
        etapes[etape] = detail
        etat_dest["statut"] = statut
        etat["destinations"][ident_dest] = etat_dest
        _sauver(etat, racine)
        audit.tracer("transfert", etape, "%s %s" % (ident_dest, statut))
        enregistre = charger(ident, racine)["destinations"][ident_dest]
        journal_actif.dire(
            "%s : %s" % (ident_dest, statut),
            "ok" if statut == TRANSFEREE else "erreur",
        )
        return enregistre

    journal_actif.dire("Étape 6 — Nouveau test de transfert", "etape")
    demande = etat["demande"]
    try:
        lot_source = annuaire_connexions.ouvrir(demande["source"]).lire(
            _perimetre(demande), journal_actif
        )
    except ERREURS_CONNEXION as exc:
        return finir(
            BLOQUEE,
            "nouveau_test",
            {"statut": BLOQUEE, "erreur": "Source illisible : %s" % exc},
        )
    nouveau, lot = _preparer_destination(
        annuaire_connexions,
        lot_source,
        demande,
        ident_dest,
        (etat_dest["reference"], "CONCORDE/%s/test2" % ident),
        os.path.join(_dossier(racine, ident), ident_dest, "nouveau_test"),
        aujourd_hui,
        journal_actif,
    )
    if lot is None:
        return finir(
            BLOQUEE,
            "nouveau_test",
            {
                "statut": BLOQUEE,
                "erreur": "Le nouveau test ne passe plus (statut %s)."
                % nouveau["statut"],
                "infos": {"etapes": nouveau["etapes"]},
            },
        )
    if empreinte_lot(lot) != etat_dest["empreinte_lot"]:
        return finir(
            BLOQUEE,
            "nouveau_test",
            {
                "statut": BLOQUEE,
                "erreur": "La source a changé depuis le rapport : créer un "
                "nouveau transfert.",
            },
        )
    etapes["nouveau_test"] = {
        "statut": "verte",
        "infos": {"etapes": nouveau["etapes"]},
    }

    journal_actif.dire("Étape 7 — Transfert", "etape")
    try:
        destination = annuaire_connexions.ouvrir(ident_dest)
        with verrou_connexion(ident_dest):
            ecrit = destination.ecrire(
                lot, etat_dest["reference"], essai=False, journal=journal_actif
            )
            if ecrit["erreurs"]:
                return finir(
                    BLOQUEE,
                    "transfert",
                    {
                        "statut": BLOQUEE,
                        "erreur": "; ".join(ecrit["erreurs"]),
                        "infos": {"ecriture": ecrit},
                    },
                )
            relu = destination.relire(etat_dest["reference"], journal_actif)
    except ERREURS_CONNEXION as exc:
        return finir(
            BLOQUEE, "transfert", {"statut": BLOQUEE, "erreur": str(exc)}
        )
    ecart = export.comparer(lot, relu)
    detail = _etat_etape(
        ecart.constats, {"ecriture": ecrit, "relecture": ecart.infos}
    )
    return finir(
        TRANSFEREE if detail["statut"] == "verte" else BLOQUEE,
        "transfert",
        detail,
    )
