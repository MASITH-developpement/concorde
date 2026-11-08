# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Client REST JSON commun aux connecteurs par API (ADR-0008, point 8).

Python standard (http.client), TLS vérifié, jeton Bearer. Une limite
d'appels (429) est attendue puis la requête est reprise ; au-delà de
`essais`, erreur nommée. Le jeton n'apparaît jamais dans un message.
"""

import http.client
import json
import ssl
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from .base import ErreurConnexion

ATTENTE_MAX_S = 60


class ReponseHttp(Protocol):
    """Réponse HTTP (http.client.HTTPResponse ou doublure de test)."""

    status: int

    def read(self) -> bytes:
        """Corps de la réponse."""

    def getheader(self, name: str) -> str | None:
        """Valeur d'un en-tête, ou None (nom de paramètre de http.client)."""


class ConnexionHttp(Protocol):
    """Connexion HTTP (http.client ou doublure de test)."""

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] = ...,
    ) -> None:
        """Envoie une requête."""

    def getresponse(self) -> ReponseHttp:
        """Lit la réponse."""

    def close(self) -> None:
        """Ferme la connexion."""


def connexion_https(
    hote: str, port: int | None, delai: float
) -> ConnexionHttp:
    """Connexion HTTPS avec vérification du certificat.

    Rôle : la seule façon d'ouvrir une connexion vers un éditeur.
    Paramètres : hote ; port (None = 443) ; delai — secondes.
    Retour : connexion http.client.
    Erreurs : aucune à l'ouverture (la connexion se fait à la requête).
    Usages : ClientJson.
    """
    return http.client.HTTPSConnection(
        hote, port, timeout=delai, context=ssl.create_default_context()
    )


class ClientJson:
    """Appels REST JSON vers une API d'éditeur, jeton Bearer."""

    def __init__(
        self,
        adresse: str,
        jeton: str,
        entetes: Mapping[str, str] | None = None,
        delai: float = 30,
        essais: int = 5,
        ouvrir: (
            Callable[[str, int | None, float], ConnexionHttp] | None
        ) = None,
        attendre: Callable[[float], None] = time.sleep,
    ) -> None:
        """Garde l'adresse (https:// exigé) et le jeton.

        `ouvrir` : fabrique de connexion (défaut : connexion_https,
        certificat vérifié). Lève ErreurConnexion si l'adresse n'est pas
        en https.
        """
        morceaux = urlsplit(adresse)
        if morceaux.scheme != "https" or not morceaux.hostname:
            raise ErreurConnexion("Adresse d'API non chiffrée : %s" % adresse)
        self.hote = morceaux.hostname
        self.port = morceaux.port
        self.racine = morceaux.path.rstrip("/")
        self._jeton = jeton
        self._entetes = dict(entetes or {})
        self.delai, self.essais = delai, essais
        self._ouvrir = ouvrir or connexion_https
        self._attendre = attendre

    def requete(
        self,
        methode: str,
        chemin: str,
        parametres: Mapping[str, object] | None = None,
        corps: object = None,
    ) -> Any:
        """Appelle l'API ; rend le JSON décodé (types JSON variés).

        Lève ErreurConnexion : refus (4xx, 5xx, message de l'éditeur),
        serveur injoignable, réponse non JSON, limite d'appels persistante.
        """
        url = self.racine + chemin
        if parametres:
            url += "?" + urlencode(
                {
                    cle: (
                        json.dumps(valeur, default=str)
                        if isinstance(valeur, (list, dict))
                        else str(valeur)
                    )
                    for cle, valeur in parametres.items()
                }
            )
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        entetes = dict(
            self._entetes,
            Authorization="Bearer " + self._jeton,
            Accept="application/json",
        )
        if donnees is not None:
            entetes["Content-Type"] = "application/json"
        for essai in range(1, self.essais + 1):
            connexion = self._ouvrir(self.hote, self.port, self.delai)
            try:
                connexion.request(methode, url, donnees, entetes)
                reponse = connexion.getresponse()
                brut = reponse.read()
            except OSError as exc:
                raise ErreurConnexion(
                    "%s injoignable : %s" % (self.hote, exc)
                ) from exc
            finally:
                connexion.close()
            if reponse.status != 429:
                return _decoder(methode, chemin, reponse.status, brut)
            if essai < self.essais:
                self._attendre(_attente(reponse.getheader("Retry-After")))
        raise ErreurConnexion(
            "%s : limite d'appels atteinte %d fois" % (self.hote, self.essais)
        )

    def tout_lire(
        self, chemin: str, parametres: Mapping[str, object] | None = None
    ) -> list[dict[str, Any]]:
        """Toutes les pages d'une liste (curseur `next_cursor`).

        Rôle : lire une liste complète sans en perdre la fin.
        Paramètres : chemin ; parametres — filtres (limit 100 ajouté).
        Retour : éléments JSON de toutes les pages.
        Erreurs : ErreurConnexion (celles de requete).
        Usages : connecteurs.pennylane.
        """
        elements: list[dict[str, Any]] = []
        curseur = ""
        while True:
            demande = dict(parametres or {}, limit=100)
            if curseur:
                demande["cursor"] = curseur
            page = self.requete("GET", chemin, demande)
            elements.extend(page.get("items") or [])
            curseur = page.get("next_cursor") or ""
            if not page.get("has_more") or not curseur:
                return elements


def _attente(retry_after: str | None) -> float:
    """Secondes à attendre d'après Retry-After (2 s par défaut, 60 au plus)."""
    try:
        return min(float(retry_after or 2), ATTENTE_MAX_S)
    except ValueError:
        return 2.0


def _decoder(methode: str, chemin: str, statut: int, brut: bytes) -> Any:
    """Réponse -> JSON, ou ErreurConnexion nommée (sans le jeton)."""
    try:
        valeur = json.loads(brut.decode("utf-8")) if brut else {}
    except (UnicodeDecodeError, ValueError) as exc:
        raise ErreurConnexion(
            "%s %s : réponse illisible (HTTP %d)" % (methode, chemin, statut)
        ) from exc
    if 200 <= statut < 300:
        return valeur
    message = ""
    if isinstance(valeur, dict):
        message = str(valeur.get("message") or valeur.get("error") or "")
    if statut in (401, 403):
        message = message or "jeton invalide ou droits insuffisants"
    raise ErreurConnexion(
        "%s %s refusé (HTTP %d) : %s"
        % (methode, chemin, statut, message[:300] or "sans détail")
    )
