# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""MARCEAU — noyau conversationnel CONCORDE.

- Avec MISTRAL_API_KEY : appelle l'API Mistral (souveraineté 100 % française)
- Sans clé ou en cas d'échec réseau : moteur à règles déterministe
- Dans tous les cas : Marceau n'est JAMAIS muet.
"""

import http.client
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Optional

API_URL = "https://api.mistral.ai/v1/chat/completions"

# Échecs possibles d'un appel Mistral (réseau, HTTP, réponse illisible ou
# de forme inattendue) : chacun déclenche le repli sur le moteur à règles.
ERREURS_MISTRAL = (
    OSError,
    http.client.HTTPException,
    ValueError,
    LookupError,
    TypeError,
)


def _ouvreur_https() -> urllib.request.OpenerDirector:
    """Ouvreur d'URL limité au schéma https (proxy et redirections inclus).

    Rôle : aucun gestionnaire file:, ftp: ou http: n'est installé ; une
    URL d'un autre schéma lève urllib.error.URLError.
    Paramètres : aucun.
    Retour : urllib.request.OpenerDirector.
    Erreurs : aucune à la construction.
    Usages : Marceau._demander_mistral.
    """
    ouvreur = urllib.request.OpenerDirector()
    for gestionnaire in (
        urllib.request.ProxyHandler(),
        urllib.request.UnknownHandler(),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        ouvreur.add_handler(gestionnaire)
    return ouvreur


class Marceau:
    """Assistant conversationnel : Mistral si configuré, règles sinon."""

    def __init__(
        self, api_key: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """Choisit le mode : 'mistral' avec une clé API, 'regles' sinon."""
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        self.model = model or os.environ.get(
            "MARCEAU_MODEL", "mistral-small-latest"
        )
        self.mode = "mistral" if self.api_key else "regles"
        self.dernier_mode: Optional[str] = None

    # --- API Mistral --------------------------------------------------------
    def _demander_mistral(
        self, question: str, contexte: Optional[dict[str, Any]] = None
    ) -> str:
        """Réponse de l'API Mistral (https uniquement).

        Lève une des ERREURS_MISTRAL si la clé manque, si l'appel échoue
        ou si la réponse n'a pas la forme attendue.
        """
        if not self.api_key:
            raise ValueError("Clé MISTRAL_API_KEY absente.")
        if urllib.parse.urlsplit(API_URL).scheme != "https":
            raise ValueError("API Mistral : seule une URL https est admise.")
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es Marceau, assistant comptable de CONCORDE, "
                    "logiciel français de MASITH. Réponds en français, "
                    "de façon brève et factuelle."
                ),
            }
        ]
        if contexte:
            messages.append(
                {
                    "role": "user",
                    "content": "Contexte : "
                    + json.dumps(contexte, ensure_ascii=False),
                }
            )
        messages.append({"role": "user", "content": question})
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(
                {"model": self.model, "messages": messages}
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
        )
        with _ouvreur_https().open(req, timeout=15) as rep:
            corps = json.loads(rep.read().decode("utf-8"))
        contenu = corps["choices"][0]["message"]["content"]
        if not isinstance(contenu, str):
            raise TypeError("Réponse Mistral sans texte.")
        return contenu

    # --- moteur à règles (repli, jamais muet) --------------------------------
    def _demander_regles(
        self, question: str, contexte: Optional[dict[str, Any]] = None
    ) -> str:
        """Réponse du moteur à règles déterministe (jamais vide)."""
        c = contexte or {}
        if "etape" in c:
            base = "Étape « %s » : " % c["etape"]
            if c.get("statut") == "erreur":
                return (
                    base
                    + "échec — "
                    + str(c.get("detail", "voir le journal Guardian."))
                )
            return base + "terminée avec succès. " + str(c.get("detail", ""))
        if "nb_lignes" in c:
            return (
                "Journal analysé : %s lignes, équilibre débit/crédit : %s, "
                "tolérance Concordance : 0,00 €."
                % (
                    c.get("nb_lignes", "?"),
                    "respecté" if c.get("equilibre") else "NON respecté",
                )
            )
        q = question.lower()
        if "lettrage" in q or "lettr" in q:
            return (
                "Le lettrage reconstruit les paires débit/crédit par compte, "
                "à montant exact en centimes. Toute ligne non appariable est "
                "une anomalie."
            )
        if "conversion" in q or "odoo 1" in q or "version" in q:
            return (
                "CONCORDE convertit les écritures entre toutes les versions "
                "d'Odoo, de la 14 à la 19, via son modèle canonique en "
                "centimes. Chaque saut de version est vérifié : équilibre "
                "0,00 € et idempotence."
            )
        if "guardian" in q:
            return (
                "Guardian est la surveillance déterministe de CONCORDE : "
                "self-check bloquant au démarrage, audit chaîné SHA-256, "
                "zéro LLM."
            )
        if "centimes" in q or "montant" in q:
            return (
                "Tous les montants sont stockés en centimes (entier). "
                "L'arrondi silencieux est interdit et refusé à l'import."
            )
        return (
            "Je suis Marceau, l'assistant de CONCORDE (MASITH). Je peux "
            "t'expliquer l'import FEC, le lettrage, l'équilibre ou Guardian."
        )

    # --- point d'entrée public -----------------------------------------------
    def repondre(
        self, question: str, contexte: Optional[dict[str, Any]] = None
    ) -> str:
        """Répond à une question : Mistral si possible, règles sinon.

        Rôle : point d'entrée unique ; un échec Mistral (ERREURS_MISTRAL)
        bascule en silence sur les règles, Marceau n'est jamais muet.
        Paramètres : question ; contexte, données JSON de l'écran.
        Retour : la réponse (texte non vide) ; dernier_mode indique le
        moteur utilisé.
        Erreurs : aucune pour un échec Mistral.
        Usages : expliquer_etape, interface/serveur.py, surveillance.
        """
        if self.mode == "mistral":
            try:
                reponse = self._demander_mistral(question, contexte)
            except ERREURS_MISTRAL:
                reponse = None  # repli à règles ci-dessous : jamais muet
            if reponse is not None:
                self.dernier_mode = "mistral"
                return reponse
        self.dernier_mode = "regles"
        return self._demander_regles(question, contexte)

    def expliquer_alerte(
        self, code: str, message: Optional[str] = None
    ) -> dict[str, str]:
        """Explication d'une alerte : {titre, pourquoi, que_faire}.

        TOUJOURS par le catalogue à règles (core/explications.py), même si
        Mistral est configuré : les alertes portent des données comptables,
        qui ne sortent pas du serveur (arbitrage du 06/11/2026).
        """
        from .explications import expliquer

        return expliquer(code, message)

    def expliquer_etape(self, nom_etape: str, donnees: object = None) -> str:
        """Chaque donnée du pipeline est liée à son explication Marceau."""
        contexte = {"etape": nom_etape, "detail": _resume(donnees)}
        return self.repondre(
            "Résume le résultat de cette étape pour le comptable.", contexte
        )


def _resume(donnees: object) -> str:
    """Résumé d'un résultat d'étape (lettrage, import, entier) ou ''."""
    if isinstance(donnees, tuple) and len(donnees) == 3:
        donnees = donnees[2]  # (paires, anomalies, stats)
    if isinstance(donnees, dict):
        if "stats" in donnees:
            s = donnees["stats"]
            return "%s lignes, %s paires de lettrage, %s anomalies." % (
                s.get("nb_lignes", "?"),
                s.get("nb_paires", "?"),
                s.get("nb_anomalies", "?"),
            )
        if "nb_lignes" in donnees:
            return "%s lignes importées." % donnees["nb_lignes"]
    if isinstance(donnees, int):
        return "Résultat : %s." % donnees
    return ""
