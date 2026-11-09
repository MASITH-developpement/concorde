# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Devis et rapport dans AzalPlus : CONCORDE demande, AzalPlus décide.

ADR-0015. Une mission terminée — transfert, montée de version, contrôle
de dématérialisation — donne deux documents dans AzalPlus : un DEVIS de
la prestation, et le RAPPORT rangé dans la GED du client.

CONCORDE n'écrit jamais dans la base d'AzalPlus et ne fixe jamais un
prix (ADR-0009 ; AZAP-AUTORITE). Il appelle `/api/v1/` avec une clé
d'API : AzalPlus garde la numérotation du devis, les prix de son
catalogue, les totaux, la TVA, les droits et son journal d'audit.

Trois verrous, fermés par défaut : `actif`, le déclencheur de la mission
et `essai_a_blanc`. En essai à blanc, CONCORDE ne fait que LIRE AzalPlus
et dit ce qui partirait.

Refus nommé, jamais de devinette : SIREN introuvable, prestation absente
du catalogue, mesure manquante — rien n'est créé à moitié.
"""

import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, TypedDict

from .connecteurs.http_json import (
    ClientJson,
    ConnexionHttp,
    connexion_https,
)
from .connecteurs.base import ErreurConnexion
from .connecteurs.secrets import (
    CHEMIN_SECRETS,
    ErreurSecrets,
    lire_secrets,
)
from .fichier_json import ecrire_json_atomique
from .journal import Journal, ou_muet
from .yaml_min import charger_yaml

RACINE_CONCORDE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN_REGLAGES_AZALPLUS = os.environ.get(
    "CONCORDE_AZALPLUS_REGLAGES",
    os.path.join(RACINE_CONCORDE, "azalplus_documents.yaml"),
)
CHEMIN_REGISTRE_AZALPLUS = os.environ.get(
    "CONCORDE_AZALPLUS_REGISTRE",
    "/var/lib/concorde-interface/azalplus_documents.json",
)
NOM_VARIABLE_CLE_AZALPLUS = "CONCORDE_AZALPLUS_CLE_API"
QUANTITE_FORFAIT = "forfait"
CLIENT_ABSENT_CREER = "creer"
RAPPORT_GED = "ged"
LIMITE_PAGE_AZALPLUS = 1000
_NON_CHIFFRE = re.compile(r"\D")


class ErreurAzalPlusDocuments(RuntimeError):
    """Émission refusée : réglage, client, prestation ou mesure absents."""


class MissionAzalPlus(TypedDict):
    """Mission terminée, telle que CONCORDE la décrit à AzalPlus.

    `genre` nomme le déclencheur (transfert, montee_version,
    controle_demat) ; `reference` identifie la mission une fois pour
    toutes (elle sert à ne pas créer deux fois le même devis) ; `siren`
    et `societe` sont lus dans le logiciel du client ; `mesures` porte
    les quantités facturables (ecritures, journaux, sauts_de_version,
    societes) ; `fichiers` sont les pièces à ranger dans la GED.
    """

    genre: str
    reference: str
    siren: str
    societe: str
    intitule: str
    resume: str
    mesures: dict[str, int]
    fichiers: list[str]


class EmissionAzalPlus(TypedDict):
    """Ce que CONCORDE a demandé — ou aurait demandé en essai à blanc.

    `refus` vide signifie que la demande est passée ; rempli, il dit
    pourquoi rien n'est parti (verrou fermé, mission déjà émise).
    """

    reference: str
    essai: bool
    refus: str
    client: str
    devis: str
    rapport: str
    lignes: list[dict[str, Any]]


def reglages_azalplus(
    chemin: str = CHEMIN_REGLAGES_AZALPLUS,
) -> dict[str, Any]:
    """Lit les réglages d'émission vers AzalPlus.

    Rôle : un seul endroit qui dit ce qui est activé et à quel prix.
    Paramètres : chemin — le fichier de réglages.
    Retour : les réglages, tels qu'écrits.
    Erreurs : ErreurAzalPlusDocuments si le fichier manque ou n'est pas
    une table de réglages.
    Usages : emetteur_azalplus, interface (écran Transferts), tests.
    """
    if not os.path.exists(chemin):
        raise ErreurAzalPlusDocuments(
            "Réglages d'AzalPlus absents : %s" % chemin
        )
    valeur = charger_yaml(chemin)
    if not isinstance(valeur, dict):
        raise ErreurAzalPlusDocuments(
            "Réglages d'AzalPlus illisibles : %s" % chemin
        )
    return dict(valeur)


def cle_api_azalplus(chemin: str = CHEMIN_SECRETS) -> str:
    """La clé d'API d'AzalPlus, lue dans le fichier de secrets.

    Rôle : garder la clé hors de git et hors des réglages.
    Paramètres : chemin — fichier de secrets des connexions.
    Retour : la clé, ou "" si elle n'y est pas.
    Erreurs : ErreurSecrets si le fichier est lisible par d'autres.
    Usages : emetteur_azalplus.
    """
    return lire_secrets(chemin).get(NOM_VARIABLE_CLE_AZALPLUS, "")


def _donnees(page: object) -> list[dict[str, Any]]:
    """Les enregistrements d'une réponse de liste d'AzalPlus."""
    if isinstance(page, list):
        return [element for element in page if isinstance(element, dict)]
    if isinstance(page, dict):
        for cle in ("data", "items", "results"):
            valeur = page.get(cle)
            if isinstance(valeur, list):
                return [
                    element for element in valeur if isinstance(element, dict)
                ]
    return []


def _enregistrement(reponse: object) -> dict[str, Any]:
    """L'enregistrement d'une réponse de création d'AzalPlus."""
    if isinstance(reponse, dict):
        for cle in ("data", "item", "record"):
            valeur = reponse.get(cle)
            if isinstance(valeur, dict):
                return valeur
        return reponse
    return {}


def siren_normalise(siren: str) -> str:
    """Les neuf chiffres d'un SIREN, quelle que soit sa présentation.

    Rôle : comparer deux SIREN sans se faire piéger par un espace, un
    point ou les cinq chiffres d'établissement d'un SIRET.
    Paramètres : siren — tel qu'il est écrit.
    Retour : neuf chiffres, ou "" si la donnée n'en contient pas assez.
    Erreurs : aucune.
    Usages : EmetteurAzalPlus.client_par_siren.
    """
    chiffres = _NON_CHIFFRE.sub("", siren or "")
    return chiffres[:9] if len(chiffres) >= 9 else ""


def _corps_multipart(
    champs: Mapping[str, str], nom_fichier: str, contenu: bytes
) -> tuple[bytes, str]:
    """Corps multipart/form-data d'un dépôt de fichier, et son type.

    Rôle : le dépôt GED d'AzalPlus attend un formulaire, pas du JSON.
    Paramètres : champs — les valeurs du formulaire ; nom_fichier ;
    contenu — les octets du fichier.
    Retour : (corps, valeur de Content-Type).
    Erreurs : aucune.
    Usages : EmetteurAzalPlus._deposer_fichier.
    """
    limite = "concorde-%s" % uuid.uuid4().hex
    morceaux: list[bytes] = []
    for cle, valeur in champs.items():
        entete = (
            '--%s\r\nContent-Disposition: form-data; name="%s"'
            "\r\n\r\n%s\r\n" % (limite, cle, valeur)
        )
        morceaux.append(entete.encode("utf-8"))
    entete_fichier = (
        '--%s\r\nContent-Disposition: form-data; name="file"; '
        'filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n'
        % (limite, nom_fichier)
    )
    morceaux.append(entete_fichier.encode("utf-8"))
    morceaux.append(contenu)
    morceaux.append(("\r\n--%s--\r\n" % limite).encode("utf-8"))
    return b"".join(morceaux), ("multipart/form-data; boundary=%s" % limite)


class EmetteurAzalPlus:
    """Demande à AzalPlus le devis d'une mission et le rangement de son
    rapport. Ne décide ni le numéro, ni le prix, ni les totaux."""

    def __init__(
        self,
        reglages: dict[str, Any],
        cle: str,
        registre: str = CHEMIN_REGISTRE_AZALPLUS,
        ouvrir: (
            Callable[[str, int | None, float], ConnexionHttp] | None
        ) = None,
        aujourd_hui: date | None = None,
    ) -> None:
        """Garde les réglages et la clé ; n'ouvre aucune connexion.

        `registre` : fichier des missions déjà émises, autorité de
        l'idempotence côté CONCORDE. `ouvrir` : fabrique de connexion
        (défaut : HTTPS à certificat vérifié), remplacée dans les tests.
        `aujourd_hui` : date du devis, pour des tests reproductibles.
        """
        self.reglages = reglages
        self.registre = registre
        self.essai = bool(reglages.get("essai_a_blanc", True))
        self.jour = aujourd_hui or date.today()
        self._cle = cle
        self._ouvrir = ouvrir or connexion_https

    def declencheur_ouvert(self, genre: str) -> bool:
        """Dit si une mission de ce genre doit parler à AzalPlus.

        Rôle : l'unique endroit qui lit les verrous, pour que personne
        ne les réinterprète de son côté.
        Paramètres : genre — transfert, et les genres branchés ensuite.
        Retour : vrai si l'interrupteur général et le déclencheur du
        genre sont tous deux ouverts.
        Erreurs : aucune.
        Usages : emettre, emission_activee.
        """
        if not bool(self.reglages.get("actif")):
            return False
        declencheurs = self.reglages.get("declencheurs")
        if not isinstance(declencheurs, dict):
            return False
        return bool(declencheurs.get(genre))

    def _entetes(self) -> dict[str, str]:
        """L'en-tête qui choisit la société émettrice, s'il est réglé."""
        societe = str(self.reglages.get("societe_emettrice") or "").strip()
        return {"X-Societe-ID": societe} if societe else {}

    def appel(self) -> ClientJson:
        """Le client d'appel à `/api/v1` d'AzalPlus.

        Rôle : une seule fabrique, pour que l'adresse, la clé et la
        société émettrice soient posées au même endroit.
        Paramètres : aucun.
        Retour : ClientJson prêt à l'emploi.
        Erreurs : ErreurAzalPlusDocuments si l'adresse ou la clé manque.
        Usages : emettre, et les tests qui appellent une étape seule.
        """
        adresse = str(self.reglages.get("adresse") or "").strip()
        if not adresse:
            raise ErreurAzalPlusDocuments(
                "Adresse d'AzalPlus non réglée (azalplus_documents.yaml)."
            )
        if not self._cle:
            raise ErreurAzalPlusDocuments(
                "Clé d'API d'AzalPlus absente : renseigner %s dans %s."
                % (NOM_VARIABLE_CLE_AZALPLUS, CHEMIN_SECRETS)
            )
        return ClientJson(
            adresse.rstrip("/") + "/api/v1",
            self._cle,
            entetes=self._entetes(),
            ouvrir=self._ouvrir,
        )

    def deja_emise(self, reference: str) -> EmissionAzalPlus | None:
        """L'émission déjà faite pour cette mission, ou None.

        Rôle : ne jamais créer deux fois le devis d'une même mission,
        même si la mission est rejouée après une panne.
        Paramètres : reference — identifiant de la mission.
        Retour : l'émission inscrite au registre, ou None.
        Erreurs : aucune (registre illisible = aucune émission connue).
        Usages : emettre, interface (écran Transferts).
        """
        inscrites = _lire_registre(self.registre)
        faite = inscrites.get(reference)
        if not isinstance(faite, dict):
            return None
        return EmissionAzalPlus(
            reference=reference,
            essai=bool(faite.get("essai")),
            refus="",
            client=str(faite.get("client") or ""),
            devis=str(faite.get("devis") or ""),
            rapport=str(faite.get("rapport") or ""),
            lignes=[],
        )

    def clients(self, appel: ClientJson) -> list[dict[str, Any]]:
        """Tous les clients du tenant AzalPlus, page par page.

        Rôle : chercher un SIREN sans dépendre de ce que la recherche
        plein texte d'AzalPlus couvre ou non.
        Paramètres : appel — client d'appel à l'API.
        Retour : les clients lus.
        Erreurs : ErreurConnexion (refus, serveur injoignable).
        Usages : client_par_siren.
        """
        lus: list[dict[str, Any]] = []
        depart = 0
        while True:
            page = _donnees(
                appel.requete(
                    "GET",
                    "/clients",
                    {"limit": LIMITE_PAGE_AZALPLUS, "skip": depart},
                )
            )
            lus.extend(page)
            if len(page) < LIMITE_PAGE_AZALPLUS:
                return lus
            depart += len(page)

    def client_par_siren(
        self, appel: ClientJson, mission: MissionAzalPlus
    ) -> dict[str, Any]:
        """Le client AzalPlus de la mission, par son SIREN.

        Rôle : rattacher le devis au bon client, sans jamais deviner.
        Paramètres : appel ; mission — porte le SIREN et le nom lus dans
        le logiciel du client.
        Retour : le client AzalPlus.
        Erreurs : ErreurAzalPlusDocuments si le SIREN est illisible, s'il
        désigne plusieurs clients, ou s'il est introuvable et que le
        réglage `client_absent` vaut « refus ».
        Usages : emettre.
        """
        cherche = siren_normalise(mission["siren"])
        if not cherche:
            raise ErreurAzalPlusDocuments(
                "SIREN illisible pour la mission %s : « %s »."
                % (mission["reference"], mission["siren"])
            )
        trouves = [
            client
            for client in self.clients(appel)
            if siren_normalise(str(client.get("registration_number") or ""))
            == cherche
        ]
        if len(trouves) > 1:
            raise ErreurAzalPlusDocuments(
                "Le SIREN %s désigne %d clients dans AzalPlus : "
                "à démêler avant d'émettre." % (cherche, len(trouves))
            )
        if trouves:
            return trouves[0]
        if str(self.reglages.get("client_absent") or "") != (
            CLIENT_ABSENT_CREER
        ):
            raise ErreurAzalPlusDocuments(
                "Aucun client AzalPlus ne porte le SIREN %s (%s). "
                "Le renseigner dans AzalPlus, ou régler "
                "client_absent: creer." % (cherche, mission["societe"])
            )
        if self.essai:
            return {
                "id": "",
                "name": mission["societe"],
                "registration_number": cherche,
            }
        return _enregistrement(
            appel.requete(
                "POST",
                "/clients",
                corps={
                    "name": mission["societe"],
                    "registration_number": cherche,
                    "is_active": True,
                },
            )
        )

    def produit_par_code(self, appel: ClientJson, code: str) -> dict[str, Any]:
        """Le produit du catalogue AzalPlus qui porte ce code.

        Rôle : lire le prix et le taux de TVA LÀ où ils sont décidés.
        Paramètres : appel ; code — colonne « code » du catalogue.
        Retour : le produit AzalPlus.
        Erreurs : ErreurAzalPlusDocuments si le code est inconnu ou porté
        par plusieurs produits.
        Usages : lignes_devis.
        """
        trouves = [
            produit
            for produit in _donnees(
                appel.requete("GET", "/produits", {"code": code, "limit": 5})
            )
            if str(produit.get("code") or "") == code
        ]
        if len(trouves) != 1:
            raise ErreurAzalPlusDocuments(
                "La prestation « %s » n'existe pas une seule fois au "
                "catalogue AzalPlus (%d trouvée(s))." % (code, len(trouves))
            )
        return trouves[0]

    def _quantite(
        self, mission: MissionAzalPlus, code: str, regle: str
    ) -> int:
        """La quantité d'une ligne : forfait, ou une mesure de la mission."""
        if regle == QUANTITE_FORFAIT:
            return 1
        if regle not in mission["mesures"]:
            raise ErreurAzalPlusDocuments(
                "La prestation « %s » se compte en « %s », mesure absente "
                "de la mission %s." % (code, regle, mission["reference"])
            )
        return int(mission["mesures"][regle])

    def lignes_devis(
        self, appel: ClientJson, mission: MissionAzalPlus
    ) -> list[dict[str, Any]]:
        """Les lignes du devis, prix lus au catalogue AzalPlus.

        Rôle : traduire une mission en lignes, sans jamais fixer un prix.
        Paramètres : appel ; mission.
        Retour : les lignes, au format attendu par AzalPlus.
        Erreurs : ErreurAzalPlusDocuments si aucune prestation n'est
        réglée pour ce genre de mission, si un code produit manque ou est
        inconnu, si une mesure manque, ou si toutes les quantités sont
        nulles (un devis vide ne part pas).
        Usages : emettre.
        """
        modeles = self.reglages.get("prestations")
        reglees = (
            modeles.get(mission["genre"])
            if isinstance(modeles, dict)
            else None
        )
        if not isinstance(reglees, list) or not reglees:
            raise ErreurAzalPlusDocuments(
                "Aucune prestation réglée pour « %s » : préciser les "
                "codes du catalogue dans azalplus_documents.yaml."
                % mission["genre"]
            )
        lignes: list[dict[str, Any]] = []
        for modele in reglees:
            if not isinstance(modele, dict):
                raise ErreurAzalPlusDocuments(
                    "Prestation mal écrite pour « %s »." % mission["genre"]
                )
            code = str(modele.get("produit") or "").strip()
            if not code:
                raise ErreurAzalPlusDocuments(
                    "Une prestation de « %s » n'a pas de code produit."
                    % mission["genre"]
                )
            regle = str(modele.get("quantite") or QUANTITE_FORFAIT).strip()
            quantite = self._quantite(mission, code, regle)
            if quantite <= 0:
                continue
            produit = self.produit_par_code(appel, code)
            lignes.append(
                {
                    "line_type": "product",
                    "produit_id": produit.get("id"),
                    "designation": str(produit.get("name") or code),
                    "unite": str(produit.get("unit") or ""),
                    "quantite": quantite,
                    "prix_unitaire": produit.get("sale_price") or 0,
                    "tva": produit.get("tax_rate") or 0,
                }
            )
        if not lignes:
            raise ErreurAzalPlusDocuments(
                "Toutes les quantités de la mission %s sont nulles : "
                "aucun devis n'est créé." % mission["reference"]
            )
        return lignes

    def _corps_devis(
        self,
        mission: MissionAzalPlus,
        client: dict[str, Any],
        lignes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Le devis demandé à AzalPlus (sans numéro ni total : à lui)."""
        return {
            "customer_id": client.get("id"),
            "client_nom": str(client.get("name") or mission["societe"]),
            "reference": mission["reference"],
            "title": mission["intitule"],
            "objet": mission["intitule"],
            "date": self.jour.isoformat(),
            "status": str(self.reglages.get("statut_devis") or "BROUILLON"),
            "lignes": lignes,
            "notes": mission["resume"],
        }

    def _deposer_fichier(
        self,
        appel: ClientJson,
        chemin: str,
        champs: Mapping[str, str],
    ) -> str:
        """Dépose un fichier dans la GED d'AzalPlus (formulaire, pas JSON)."""
        with open(chemin, "rb") as fichier:
            contenu = fichier.read()
        corps, type_contenu = _corps_multipart(
            champs, os.path.basename(chemin), contenu
        )
        entetes = dict(
            self._entetes(),
            Accept="application/json",
            Authorization="Bearer %s" % self._cle,
        )
        entetes["Content-Type"] = type_contenu
        connexion = self._ouvrir(appel.hote, appel.port, appel.delai)
        try:
            connexion.request(
                "POST", appel.racine + "/ged/upload", corps, entetes
            )
            reponse = connexion.getresponse()
            brut, statut = reponse.read(), reponse.status
        except OSError as exc:
            raise ErreurAzalPlusDocuments(
                "AzalPlus injoignable pour le dépôt du rapport : %s" % exc
            ) from exc
        finally:
            connexion.close()
        if not 200 <= statut < 300:
            raise ErreurAzalPlusDocuments(
                "Dépôt du rapport refusé par AzalPlus (HTTP %d)." % statut
            )
        try:
            lu = json.loads(brut.decode("utf-8")) if brut else {}
        except (UnicodeDecodeError, ValueError) as exc:
            raise ErreurAzalPlusDocuments(
                "Réponse illisible au dépôt du rapport."
            ) from exc
        return str(_enregistrement(lu).get("id") or "")

    def _deposer_rapport(
        self,
        appel: ClientJson,
        mission: MissionAzalPlus,
        client: dict[str, Any],
    ) -> str:
        """Range le rapport de la mission chez le client, dans AzalPlus.

        Rôle : que le rapport vive là où le client est suivi.
        Paramètres : appel ; mission ; client — le client AzalPlus.
        Retour : les identifiants des documents créés, séparés par une
        virgule ; "" si le réglage `rapport` ne vaut pas « ged ».
        Erreurs : ErreurAzalPlusDocuments (dépôt refusé, réponse
        illisible), ErreurConnexion (serveur injoignable).
        Usages : emettre.
        """
        if str(self.reglages.get("rapport") or "") != RAPPORT_GED:
            return ""
        nom = "CONCORDE - %s" % mission["intitule"]
        genre = str(self.reglages.get("type_rapport") or "RAPPORT")
        presents = [
            chemin for chemin in mission["fichiers"] if os.path.exists(chemin)
        ]
        if presents:
            champs = {
                "name": nom,
                "type": genre,
                "description": mission["resume"],
                "entity_type": "clients",
                "entity_id": str(client.get("id") or ""),
                "conditions_acceptees": "true",
            }
            return ",".join(
                self._deposer_fichier(appel, chemin, champs)
                for chemin in presents
            )
        cree = _enregistrement(
            appel.requete(
                "POST",
                "/ged",
                corps={
                    "name": nom,
                    "type": genre,
                    "description": mission["resume"],
                    "entity_type": "clients",
                    "entity_id": client.get("id"),
                    "date_document": self.jour.isoformat(),
                    "auteur": "CONCORDE",
                },
            )
        )
        return str(cree.get("id") or "")

    def _rien(self, mission: MissionAzalPlus, motif: str) -> EmissionAzalPlus:
        """Une émission qui n'a pas eu lieu, avec son motif lisible."""
        return EmissionAzalPlus(
            reference=mission["reference"],
            essai=self.essai,
            refus=motif,
            client="",
            devis="",
            rapport="",
            lignes=[],
        )

    def _inscrire(self, emission: EmissionAzalPlus) -> None:
        """Inscrit l'émission au registre (idempotence des missions)."""
        inscrites = _lire_registre(self.registre)
        inscrites[emission["reference"]] = {
            "essai": emission["essai"],
            "client": emission["client"],
            "devis": emission["devis"],
            "rapport": emission["rapport"],
            "le": self.jour.isoformat(),
        }
        dossier = os.path.dirname(self.registre)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        ecrire_json_atomique(self.registre, inscrites, retrait=2)

    def emettre(
        self, mission: MissionAzalPlus, journal: Journal | None = None
    ) -> EmissionAzalPlus:
        """Demande à AzalPlus le devis et le rangement du rapport.

        Rôle : le seul chemin par lequel une mission devient un devis.
        Paramètres : mission ; journal — pour que l'écran dise ce qui se
        passe.
        Retour : l'émission ; `refus` rempli si un verrou est fermé ou si
        la mission était déjà émise (ce n'est pas une erreur).
        Erreurs : ErreurAzalPlusDocuments (réglage, client, prestation ou
        mesure en défaut), ErreurConnexion (AzalPlus injoignable ou
        refus). Rien n'est alors créé à moitié : le devis part avant le
        rapport, et le registre n'est inscrit qu'une fois les deux faits.
        Usages : emettre_sans_bloquer, tests.
        """
        journal_actif = ou_muet(journal)
        if not self.declencheur_ouvert(mission["genre"]):
            return self._rien(
                mission,
                "AzalPlus fermé pour « %s » : voir actif et declencheurs "
                "dans azalplus_documents.yaml." % mission["genre"],
            )
        faite = self.deja_emise(mission["reference"])
        if faite is not None and not faite["essai"]:
            faite["refus"] = "Mission déjà émise (devis %s)." % faite["devis"]
            journal_actif.dire(faite["refus"], "info")
            return faite
        appel = self.appel()
        client = self.client_par_siren(appel, mission)
        lignes = self.lignes_devis(appel, mission)
        nom_client = str(client.get("name") or mission["societe"])
        if self.essai:
            journal_actif.dire(
                "Essai à blanc : %d ligne(s) de devis pour %s."
                % (len(lignes), nom_client),
                "info",
            )
            return EmissionAzalPlus(
                reference=mission["reference"],
                essai=True,
                refus="",
                client=nom_client,
                devis="",
                rapport="",
                lignes=lignes,
            )
        devis = _enregistrement(
            appel.requete(
                "POST",
                "/devis",
                corps=self._corps_devis(mission, client, lignes),
            )
        )
        numero = str(devis.get("number") or devis.get("id") or "")
        emission = EmissionAzalPlus(
            reference=mission["reference"],
            essai=False,
            refus="",
            client=nom_client,
            devis=numero,
            rapport=self._deposer_rapport(appel, mission, client),
            lignes=lignes,
        )
        self._inscrire(emission)
        journal_actif.dire(
            "AzalPlus : devis %s créé pour %s." % (numero, nom_client), "ok"
        )
        return emission


def _lire_registre(chemin: str) -> dict[str, Any]:
    """Les missions déjà émises ; {} si le registre n'existe pas encore."""
    if not os.path.exists(chemin):
        return {}
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            lu = json.load(fichier)
    except (OSError, ValueError):
        return {}
    return lu if isinstance(lu, dict) else {}


def emetteur_azalplus(
    reglages: dict[str, Any] | None = None,
    cle: str | None = None,
) -> EmetteurAzalPlus:
    """L'émetteur, réglages et clé lus sur le serveur.

    Rôle : une seule fabrique, pour que les trois déclencheurs et l'écran
    lisent les mêmes réglages et la même clé.
    Paramètres : reglages et cle — fournis dans les tests ; lus sur le
    serveur si absents.
    Retour : l'émetteur.
    Erreurs : ErreurAzalPlusDocuments (réglages absents ou illisibles),
    ErreurSecrets (fichier de secrets aux droits trop ouverts).
    Usages : emettre_sans_bloquer, interface (écran Transferts).
    """
    lus = reglages_azalplus() if reglages is None else reglages
    return EmetteurAzalPlus(lus, cle_api_azalplus() if cle is None else cle)


def emettre_sans_bloquer(
    mission: MissionAzalPlus,
    journal: Journal | None = None,
    emetteur: EmetteurAzalPlus | None = None,
) -> EmissionAzalPlus:
    """Émet vers AzalPlus, et dit son refus sans casser la mission.

    Rôle : une mission réussie ne doit jamais être déclarée en échec
    parce qu'AzalPlus a refusé le devis — mais le refus est DIT, au
    journal et dans la valeur rendue, jamais avalé.
    Paramètres : mission ; journal ; emetteur — fourni dans les tests.
    Retour : l'émission ; `refus` porte le motif en cas d'échec.
    Erreurs : aucune.
    Usages : fin d'un transfert, d'une montée de version, d'un contrôle
    de dématérialisation.
    """
    journal_actif = ou_muet(journal)
    try:
        return (emetteur_azalplus() if emetteur is None else emetteur).emettre(
            mission, journal_actif
        )
    except (
        ErreurAzalPlusDocuments,
        ErreurConnexion,
        ErreurSecrets,
        OSError,
    ) as exc:
        motif = str(exc)
        journal_actif.dire("AzalPlus : %s" % motif, "erreur")
        return EmissionAzalPlus(
            reference=mission["reference"],
            essai=False,
            refus=motif,
            client="",
            devis="",
            rapport="",
            lignes=[],
        )


def emission_activee(genre: str) -> bool:
    """Dit si une mission de ce genre doit parler à AzalPlus.

    Rôle : qu'un déclencheur n'identifie pas la source du client, et ne
    lise pas de secret, quand AzalPlus est éteint.
    Paramètres : genre — le genre de mission.
    Retour : vrai si les verrous sont ouverts ; faux si les réglages sont
    absents ou illisibles (fermé par défaut).
    Erreurs : aucune.
    Usages : fin d'un transfert.
    """
    try:
        return emetteur_azalplus().declencheur_ouvert(genre)
    except (ErreurAzalPlusDocuments, ErreurSecrets, OSError):
        return False
