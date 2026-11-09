# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Écran « Compléter SIRET et TVA » (ADR-0013).

Depuis le constat « Sociétés françaises sans SIREN ni TVA » d'une analyse :
1. propositions (tâche « siret_proposer ») : tiers relus dans la connexion
   Odoo choisie, annuaire public de l'État, contrôles par calcul ;
2. essai sur la connexion de test (tâche « siret_ecrire », cible test) ;
3. feu vert : mêmes choix, nom de la connexion retapé, production.
Seuls un SIRET et une TVA proposés par l'annuaire peuvent être écrits :
rien n'est saisi à la main.
"""

import json
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import Annuaire
from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.secrets import ErreurSecrets
from core.guardian import Guardian
from core.journal import Journal
from core.tiers_odoo import CibleTiers, annuler
from core.tiers_siret import (
    Choix,
    ErreurSiret,
    Proposition,
    ecrire,
    identifiants_constat,
    lire_tiers,
    proposer,
)
from interface.transferts import ErreurEcran, texte_corps

if (
    TYPE_CHECKING
):  # import seulement pour les types : serveur importe ce module
    from interface.serveur import Taches

ObjetJson = dict[str, Any]
CONSTAT_TIERS = "TIERS_SANS_SIREN_TVA"
CIBLES = ("test", "production")
NOM_PROPOSITIONS = "propositions.json"
NOM_ESSAI = "essai_test.json"
# Refus de l'écran SIRET, rendus au navigateur avec leur cause.
ERREURS_SIRET = (
    ErreurEcran,
    ErreurSiret,
    ErreurConnexion,
    ErreurSecrets,
    ValueError,
)


class EcranSiret:
    """Compléter SIRET et TVA : propositions, essai, feu vert, annulation."""

    def __init__(
        self, taches: "Taches", annuaire: Annuaire, journal: Journal
    ) -> None:
        """Branche les trois tâches de l'écran."""
        self.taches = taches
        self.annuaire = annuaire
        self.journal = journal
        taches.travaux["siret_proposer"] = self._travail_proposer
        taches.travaux["siret_ecrire"] = self._travail_ecrire
        taches.travaux["siret_annuler"] = self._travail_annuler

    # --- outils --------------------------------------------------------------
    def _connecteur(self, ident: str) -> ConnecteurOdoo:
        """Connexion Odoo ouverte (avec sa clé API). Lève ErreurEcran."""
        connecteur = self.annuaire.ouvrir(ident)
        if not isinstance(connecteur, ConnecteurOdoo):
            raise ErreurEcran("La connexion %s n'est pas un Odoo." % ident)
        return connecteur

    def _fichier(self, tache: str, nom: str) -> str:
        """Fichier dans le dossier d'une tâche « siret_proposer »."""
        return os.path.join(self.taches.dossier, tache, nom)

    def _tache_propositions(self, ident: str) -> ObjetJson:
        """Tâche de propositions terminée. Lève ErreurEcran."""
        tache = self.taches.obtenir(ident)
        if (
            tache is None
            or tache["action"] != "siret_proposer"
            or tache["statut"] != "terminee"
        ):
            raise ErreurEcran("Propositions inconnues ou pas encore prêtes.")
        return tache

    def _lire(self, chemin: str) -> Any:
        """Fichier JSON d'une tâche ; None s'il n'existe pas."""
        if not os.path.isfile(chemin):
            return None
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier)

    # --- 1. propositions -----------------------------------------------------
    def lancer_propositions(self, corps: Mapping[str, Any]) -> str:
        """Lance les propositions pour le constat d'une analyse.

        Corps : analyse (tâche d'analyse terminée), connexion (Odoo, avec
        une connexion de test). Lève ErreurEcran.
        """
        analyse = texte_corps(corps, "analyse")
        rapport = self.taches.rapport(analyse)
        if rapport is None:
            raise ErreurEcran("Analyse inconnue ou pas terminée.")
        with open(rapport, encoding="utf-8") as fichier:
            constats = json.load(fichier)["constats"]
        constat = next(
            (
                un_constat
                for un_constat in constats
                if un_constat["code"] == CONSTAT_TIERS
            ),
            None,
        )
        if constat is None:
            raise ErreurEcran(
                "Cette analyse ne signale aucun tiers à compléter."
            )
        connexion = texte_corps(corps, "connexion")
        fiche = self.annuaire.obtenir(connexion)
        if fiche["logiciel"] != ConnecteurOdoo.logiciel:
            raise ErreurEcran("Choisir une connexion Odoo.")
        if not fiche["connexion_test"]:
            raise ErreurEcran(
                "« %s » n'a pas de connexion de test : les écritures passent "
                "d'abord par la copie de test (ADR-0013). Ajoutez-la dans "
                "Transferts." % fiche["libelle"]
            )
        return self.taches.lancer(
            "siret_proposer",
            None,
            "%s — SIRET et TVA" % fiche["libelle"],
            "",
            {
                "analyse": analyse,
                "connexion": connexion,
                "identifiants": identifiants_constat(constat["elements"]),
            },
        )

    def _travail_proposer(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « siret_proposer » : tiers relus, annuaire, contrôles."""
        parametres = tache["params"]
        cible = self._connecteur(parametres["connexion"]).cible(CibleTiers)
        tiers = lire_tiers(cible, parametres["identifiants"])
        journal.dire(
            "%d tiers à compléter sur %d signalés (les autres le sont déjà)"
            % (len(tiers), len(parametres["identifiants"])),
            "etape",
        )
        propositions = proposer(tiers)
        with open(
            self._fichier(tache["id"], NOM_PROPOSITIONS), "w", encoding="utf-8"
        ) as fichier:
            json.dump(propositions, fichier, ensure_ascii=False)
        comptes: dict[str, int] = {}
        for proposition_tiers in propositions:
            comptes[proposition_tiers["classe"]] = (
                comptes.get(proposition_tiers["classe"], 0) + 1
            )
        guardian.tracer("siret", "propositions", json.dumps(comptes))
        tache["resultat"] = {"tiers": len(tiers), "classes": comptes}

    def propositions(self, ident: str) -> ObjetJson:
        """Propositions, connexions et essai sur la copie de test."""
        tache = self._tache_propositions(ident)
        fiche = self.annuaire.obtenir(tache["params"]["connexion"])
        test = self.annuaire.obtenir(str(fiche["connexion_test"]))
        return {
            "tache": ident,
            "connexion": fiche["libelle"],
            "connexion_test": test["libelle"],
            "propositions": self._lire(self._fichier(ident, NOM_PROPOSITIONS)),
            "essai_test": self._lire(self._fichier(ident, NOM_ESSAI)),
        }

    # --- 2. et 3. écrire -----------------------------------------------------
    def _choix_valides(self, ident: str, recus: object) -> list[Choix]:
        """Choix reçus, acceptés seulement s'ils viennent des propositions."""
        propositions: list[Proposition] = (
            self._lire(self._fichier(ident, NOM_PROPOSITIONS)) or []
        )
        par_tiers = {
            proposition_tiers["tiers"]["id"]: proposition_tiers
            for proposition_tiers in propositions
        }
        if not isinstance(recus, list) or not recus:
            raise ErreurEcran("Aucun tiers choisi.")
        choix: list[Choix] = []
        for recu in recus:
            if not isinstance(recu, dict):
                raise ErreurEcran("Choix mal formé.")
            ident_tiers = recu.get("id")
            proposition_tiers = (
                par_tiers.get(ident_tiers)
                if isinstance(ident_tiers, int)
                else None
            )
            siret, tva = str(recu.get("siret") or ""), str(
                recu.get("tva") or ""
            )
            if proposition_tiers is None or not any(
                possible["siret"] == siret and tva in ("", possible["tva"])
                for possible in proposition_tiers["candidates"]
            ):
                raise ErreurEcran(
                    "Choix refusé pour le tiers %s : il ne vient pas des "
                    "propositions de l'annuaire." % recu.get("id")
                )
            choix.append(
                {
                    "id": proposition_tiers["tiers"]["id"],
                    "siret": siret,
                    "tva": tva,
                }
            )
        return sorted(choix, key=lambda un_choix: un_choix["id"])

    def lancer_ecriture(
        self, ident: str, corps: Mapping[str, Any], ip: str
    ) -> str:
        """Essai sur la copie de test, ou production après feu vert.

        Production : mêmes choix que l'essai sur la copie de test, et nom
        de la connexion de production retapé. Lève ErreurEcran.
        """
        tache = self._tache_propositions(ident)
        cible = texte_corps(corps, "cible")
        if cible not in CIBLES:
            raise ErreurEcran("Cible inconnue : test ou production.")
        choix = self._choix_valides(ident, corps.get("choix"))
        fiche = self.annuaire.obtenir(tache["params"]["connexion"])
        connexion = (
            str(fiche["connexion_test"]) if cible == "test" else fiche["id"]
        )
        if cible == "production":
            essai = self._lire(self._fichier(ident, NOM_ESSAI))
            if not essai or essai["choix"] != choix:
                raise ErreurEcran(
                    "Feu vert impossible : faire d'abord l'essai sur la copie "
                    "de test avec exactement les mêmes choix."
                )
            if texte_corps(corps, "confirmation") != fiche["libelle"]:
                raise ErreurEcran(
                    "Nom de la connexion mal retapé : rien n'est écrit."
                )
        return self.taches.lancer(
            "siret_ecrire",
            None,
            "%s — SIRET et TVA (%s)" % (fiche["libelle"], cible),
            "",
            {
                "propositions": ident,
                "connexion": connexion,
                "cible": cible,
                "choix": choix,
                "par": "session de l'interface depuis %s" % ip,
            },
        )

    def _travail_ecrire(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « siret_ecrire » : écriture tracée, bilan."""
        parametres = tache["params"]
        connexion = parametres["connexion"]
        libelle = self.annuaire.obtenir(connexion)["libelle"]
        bilan = ecrire(
            self._connecteur(connexion).cible(CibleTiers),
            parametres["choix"],
            libelle,
            self._fichier(
                parametres["propositions"],
                "trace-%s.jsonl" % parametres["cible"],
            ),
        )
        journal.dire(
            "%s : %d fiche(s) complétée(s), %d déjà complétée(s), %d refus"
            % (
                libelle,
                len(bilan["ecrits"]),
                len(bilan["ignores"]),
                len(bilan["refus"]),
            ),
            "ok" if not bilan["refus"] else "alerte",
        )
        guardian.tracer(
            "siret",
            parametres["cible"],
            "%s %s %d" % (libelle, parametres["par"], len(bilan["ecrits"])),
        )
        if parametres["cible"] == "test":
            with open(
                self._fichier(parametres["propositions"], NOM_ESSAI),
                "w",
                encoding="utf-8",
            ) as fichier:
                json.dump(
                    {"choix": parametres["choix"], "bilan": bilan},
                    fichier,
                    ensure_ascii=False,
                )
        tache["resultat"] = dict(
            bilan, cible=parametres["cible"], base=libelle
        )

    def lancer_annulation(self, ident: str, corps: Mapping[str, Any]) -> str:
        """Remet les anciennes valeurs (test ou production).

        Lève ErreurEcran.
        """
        tache = self._tache_propositions(ident)
        cible = texte_corps(corps, "cible")
        if cible not in CIBLES:
            raise ErreurEcran("Cible inconnue : test ou production.")
        if not os.path.isfile(self._fichier(ident, "trace-%s.jsonl" % cible)):
            raise ErreurEcran("Rien à annuler : aucune écriture tracée.")
        fiche = self.annuaire.obtenir(tache["params"]["connexion"])
        connexion = (
            str(fiche["connexion_test"]) if cible == "test" else fiche["id"]
        )
        return self.taches.lancer(
            "siret_annuler",
            None,
            "%s — annulation SIRET et TVA (%s)" % (fiche["libelle"], cible),
            "",
            {"propositions": ident, "connexion": connexion, "cible": cible},
        )

    def _travail_annuler(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « siret_annuler » : anciennes valeurs remises."""
        parametres = tache["params"]
        bilan = annuler(
            self._connecteur(parametres["connexion"]).cible(CibleTiers),
            self._fichier(
                parametres["propositions"],
                "trace-%s.jsonl" % parametres["cible"],
            ),
        )
        guardian.tracer("siret", "annulation", json.dumps(bilan))
        tache["resultat"] = dict(bilan, cible=parametres["cible"])
