# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Circuit commun des écrans qui complètent des tiers (ADR-0013, ADR-0014).

1. préparation (tâche propre à chaque écran) : résultats rangés dans
   « propositions.json », dans le dossier de la tâche ;
2. essai sur la connexion de test (tâche « <écran>_ecrire », cible test) ;
3. feu vert : mêmes choix, nom de la connexion retapé, production ;
4. annulation à partir de la trace (tâche « <écran>_annuler »).
Seule une valeur venue des résultats de la préparation peut être écrite :
chaque écran vérifie les choix reçus (`choix_valides`).
"""

import json
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import Annuaire, FicheConnexion
from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.secrets import ErreurSecrets
from core.guardian import Guardian
from core.journal import Journal
from core.tiers_odoo import AccesOdoo, CibleTiers, annuler
from interface.transferts import ErreurEcran, texte_corps

if (
    TYPE_CHECKING
):  # import seulement pour les types : serveur importe ce module
    from interface.serveur import Taches

ObjetJson = dict[str, Any]
CIBLES = ("test", "production")
NOM_PROPOSITIONS = "propositions.json"
NOM_ESSAI = "essai_test.json"
# Refus communs aux écrans de tiers, rendus avec leur cause (HTTP 400).
ERREURS_TIERS = (
    ErreurEcran,
    ErreurConnexion,
    ErreurSecrets,
    ValueError,
)


class EcranTiers:
    """Écran qui prépare, essaie, valide et annule des écritures de tiers.

    Une sous-classe donne : `prefixe` (nom des tâches), `action_preparer`,
    `titre`, la tâche de préparation (`_travail_preparer`), la vérification
    des choix (`choix_valides`) et l'écriture (`ecrire_choix`).
    """

    prefixe: ClassVar[str]
    action_preparer: ClassVar[str]
    titre: ClassVar[str]

    def __init__(
        self, taches: "Taches", annuaire: Annuaire, journal: Journal
    ) -> None:
        """Branche les tâches de l'écran."""
        self.taches = taches
        self.annuaire = annuaire
        self.journal = journal
        taches.travaux[self.action_preparer] = self._travail_preparer
        taches.travaux[self.prefixe + "_ecrire"] = self._travail_ecrire
        taches.travaux[self.prefixe + "_annuler"] = self._travail_annuler

    # --- à fournir par chaque écran ------------------------------------------
    def _travail_preparer(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche de préparation : écrit propositions.json."""
        raise NotImplementedError

    def choix_valides(self, ident: str, recus: object) -> list[Any]:
        """Choix reçus, acceptés seulement s'ils viennent des résultats."""
        raise NotImplementedError

    def ecrire_choix(
        self, cible: AccesOdoo, choix: list[Any], base: str, trace: str
    ) -> dict[str, Any]:
        """Écrit les choix dans une base ; rend le bilan."""
        raise NotImplementedError

    # --- outils --------------------------------------------------------------
    def connecteur(self, ident: str) -> ConnecteurOdoo:
        """Connexion Odoo ouverte (avec sa clé API). Lève ErreurEcran."""
        ouvert = self.annuaire.ouvrir(ident)
        if not isinstance(ouvert, ConnecteurOdoo):
            raise ErreurEcran("La connexion %s n'est pas un Odoo." % ident)
        return ouvert

    def connexion_avec_test(self, ident: str) -> FicheConnexion:
        """Connexion Odoo qui a une connexion de test. Lève ErreurEcran."""
        fiche = self.annuaire.obtenir(ident)
        if fiche["logiciel"] != ConnecteurOdoo.logiciel:
            raise ErreurEcran("Choisir une connexion Odoo.")
        if not fiche["connexion_test"]:
            raise ErreurEcran(
                "« %s » n'a pas de connexion de test : les écritures passent "
                "d'abord par la copie de test. Ajoutez-la dans Transferts."
                % fiche["libelle"]
            )
        return fiche

    def fichier(self, tache: str, nom: str) -> str:
        """Fichier dans le dossier d'une tâche de préparation."""
        return os.path.join(self.taches.dossier, tache, nom)

    def lire(self, chemin: str) -> Any:
        """Fichier JSON d'une tâche ; None s'il n'existe pas."""
        if not os.path.isfile(chemin):
            return None
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier)

    def enregistrer(self, tache: ObjetJson, resultats: list[Any]) -> None:
        """Range les résultats de la préparation (propositions.json)."""
        with open(
            self.fichier(tache["id"], NOM_PROPOSITIONS), "w", encoding="utf-8"
        ) as fichier:
            json.dump(resultats, fichier, ensure_ascii=False)

    def tache_preparee(self, ident: str) -> ObjetJson:
        """Tâche de préparation terminée. Lève ErreurEcran."""
        tache = self.taches.obtenir(ident)
        if (
            tache is None
            or tache["action"] != self.action_preparer
            or tache["statut"] != "terminee"
        ):
            raise ErreurEcran("Résultats inconnus ou pas encore prêts.")
        return tache

    def resultats(self, ident: str) -> ObjetJson:
        """Résultats, connexions et essai sur la copie de test."""
        tache = self.tache_preparee(ident)
        fiche = self.annuaire.obtenir(tache["params"]["connexion"])
        test = self.annuaire.obtenir(str(fiche["connexion_test"]))
        return {
            "tache": ident,
            "connexion": fiche["libelle"],
            "connexion_test": test["libelle"],
            "propositions": self.lire(self.fichier(ident, NOM_PROPOSITIONS)),
            "essai_test": self.lire(self.fichier(ident, NOM_ESSAI)),
        }

    def _cible(self, ident: str, corps: Mapping[str, Any]) -> tuple[str, str]:
        """(cible, connexion à écrire) d'une demande. Lève ErreurEcran."""
        tache = self.tache_preparee(ident)
        cible = texte_corps(corps, "cible")
        if cible not in CIBLES:
            raise ErreurEcran("Cible inconnue : test ou production.")
        fiche = self.annuaire.obtenir(tache["params"]["connexion"])
        connexion = (
            str(fiche["connexion_test"]) if cible == "test" else fiche["id"]
        )
        return cible, connexion

    # --- essai, feu vert, annulation -----------------------------------------
    def lancer_ecriture(
        self, ident: str, corps: Mapping[str, Any], ip: str
    ) -> str:
        """Essai sur la copie de test, ou production après feu vert.

        Production : mêmes choix que l'essai sur la copie de test, et nom
        de la connexion de production retapé. Lève ErreurEcran.
        """
        cible, connexion = self._cible(ident, corps)
        choix = self.choix_valides(ident, corps.get("choix"))
        fiche = self.annuaire.obtenir(
            self.tache_preparee(ident)["params"]["connexion"]
        )
        if cible == "production":
            essai = self.lire(self.fichier(ident, NOM_ESSAI))
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
            self.prefixe + "_ecrire",
            None,
            "%s — %s (%s)" % (fiche["libelle"], self.titre, cible),
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
        """Tâche « <écran>_ecrire » : écriture tracée, bilan."""
        parametres = tache["params"]
        libelle = self.annuaire.obtenir(parametres["connexion"])["libelle"]
        bilan = self.ecrire_choix(
            self.connecteur(parametres["connexion"]).cible(CibleTiers),
            parametres["choix"],
            libelle,
            self.fichier(
                parametres["propositions"],
                "trace-%s.jsonl" % parametres["cible"],
            ),
        )
        journal.dire(
            "%s : %d fiche(s) complétée(s), %d déjà renseignée(s), %d refus"
            % (
                libelle,
                len(bilan["ecrits"]),
                len(bilan["ignores"]),
                len(bilan["refus"]),
            ),
            "ok" if not bilan["refus"] else "alerte",
        )
        guardian.tracer(
            self.prefixe,
            parametres["cible"],
            "%s %s %d" % (libelle, parametres["par"], len(bilan["ecrits"])),
        )
        if parametres["cible"] == "test":
            with open(
                self.fichier(parametres["propositions"], NOM_ESSAI),
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
        cible, connexion = self._cible(ident, corps)
        if not os.path.isfile(self.fichier(ident, "trace-%s.jsonl" % cible)):
            raise ErreurEcran("Rien à annuler : aucune écriture tracée.")
        libelle = self.annuaire.obtenir(connexion)["libelle"]
        return self.taches.lancer(
            self.prefixe + "_annuler",
            None,
            "%s — annulation %s (%s)" % (libelle, self.titre, cible),
            "",
            {"propositions": ident, "connexion": connexion, "cible": cible},
        )

    def _travail_annuler(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « <écran>_annuler » : anciennes valeurs remises."""
        parametres = tache["params"]
        bilan = annuler(
            self.connecteur(parametres["connexion"]).cible(CibleTiers),
            self.fichier(
                parametres["propositions"],
                "trace-%s.jsonl" % parametres["cible"],
            ),
        )
        guardian.tracer(self.prefixe, "annulation", json.dumps(bilan))
        tache["resultat"] = dict(bilan, cible=parametres["cible"])


def compter_classes(resultats: list[Mapping[str, Any]]) -> dict[str, int]:
    """Nombre de résultats par classe (« sure », « inscrit »…)."""
    comptes: dict[str, int] = {}
    for un_resultat in resultats:
        classe = str(un_resultat["classe"])
        comptes[classe] = comptes.get(classe, 0) + 1
    return comptes
