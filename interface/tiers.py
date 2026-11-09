# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Circuit commun des écrans qui complètent des tiers (ADR-0013, ADR-0014).

1. préparation (tâche propre à chaque écran) : résultats rangés dans
   « propositions.json », dans le dossier de la tâche ;
2. essai sur la copie de test (tâche « <écran>_ecrire », cible test) ;
3. feu vert : mêmes choix, nom de la base retapé, production ;
4. annulation à partir de la trace (tâche « <écran>_annuler »).
Seule une valeur venue des résultats de la préparation peut être écrite :
chaque écran vérifie les choix reçus (`choix_valides`).

Bases où écrire (« sources ») : celles du sélecteur de l'interface où
CONCORDE peut écrire (« base:<id> ») et les connexions Odoo de l'écran
Transferts (« connexion:<id> »). On choisit la base à compléter et sa
copie de test, qui doit être une autre base.
"""

import json
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import Annuaire
from core.connecteurs.odoo import ConnecteurOdoo
from core.connecteurs.secrets import ErreurSecrets
from core.guardian import Guardian
from core.journal import Journal
from core.migration.injection import ErreurInjection
from core.odoo_source import ErreurSource
from core.tiers_odoo import AccesOdoo, CibleTiers, annuler
from interface.transferts import ErreurEcran, texte_corps

if (
    TYPE_CHECKING
):  # import seulement pour les types : serveur importe ce module
    from interface.serveur import Bases, Taches

ObjetJson = dict[str, Any]
CIBLES = ("test", "production")
NOM_PROPOSITIONS = "propositions.json"
NOM_ESSAI = "essai_test.json"
# Refus communs aux écrans de tiers, rendus avec leur cause (HTTP 400).
ERREURS_TIERS = (
    ErreurEcran,
    ErreurConnexion,
    ErreurSecrets,
    ErreurSource,
    ErreurInjection,
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
        self,
        taches: "Taches",
        bases: "Bases",
        annuaire: Annuaire,
        journal: Journal,
    ) -> None:
        """Branche les tâches de l'écran."""
        self.taches = taches
        self.bases = bases
        self.annuaire = annuaire
        self.journal = journal
        taches.travaux[self.action_preparer] = self._travail_preparer
        taches.travaux[self.prefixe + "_ecrire"] = self._travail_ecrire
        taches.travaux[self.prefixe + "_annuler"] = self._travail_annuler
        taches.annulations[self.prefixe + "_ecrire"] = self._defaire_ecriture

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

    def sources(self) -> list[ObjetJson]:
        """Bases où CONCORDE peut écrire : sélecteur, puis Transferts."""
        trouvees: list[ObjetJson] = [
            {
                "id": "base:" + str(base["id"]),
                "libelle": str(base.get("libelle") or base["nom"]),
            }
            for base in self.bases.lister()
            if base.get("ecriture_ok")
        ]
        for fiche in self.annuaire.lister():
            if fiche["logiciel"] == ConnecteurOdoo.logiciel:
                trouvees.append(
                    {
                        "id": "connexion:" + fiche["id"],
                        "libelle": fiche["libelle"],
                    }
                )
        return trouvees

    def libelle_source(self, ident: str) -> str:
        """Nom affiché d'une base où écrire (son identifiant si inconnue)."""
        return next(
            (
                str(source["libelle"])
                for source in self.sources()
                if source["id"] == ident
            ),
            ident,
        )

    def acces(self, ident: str) -> AccesOdoo:
        """Accès en écriture, réduit à lire et compléter des tiers.

        Lève ErreurEcran (base inconnue), ErreurSource, ErreurConnexion.
        """
        genre, _, cle = ident.partition(":")
        if genre == "base":
            return self.bases.acces_ecriture(cle, CibleTiers)
        if genre == "connexion":
            return self.connecteur(cle).cible(CibleTiers)
        raise ErreurEcran("Base inconnue : %s" % ident)

    def couple(self, corps: Mapping[str, Any]) -> tuple[str, str]:
        """(base à compléter, copie de test) choisies. Lève ErreurEcran."""
        connues = {source["id"] for source in self.sources()}
        production = texte_corps(corps, "production")
        test = texte_corps(corps, "test")
        if production not in connues:
            raise ErreurEcran(
                "Choisir la base à compléter parmi celles où CONCORDE peut "
                "écrire."
            )
        if test not in connues:
            raise ErreurEcran(
                "Choisir la copie de test : les écritures y passent d'abord."
            )
        if test == production:
            raise ErreurEcran(
                "La copie de test doit être une autre base que celle à "
                "compléter."
            )
        return production, test

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
        """Résultats, bases (à compléter et de test), essai sur le test."""
        parametres = self.tache_preparee(ident)["params"]
        return {
            "tache": ident,
            "connexion": self.libelle_source(parametres["production"]),
            "connexion_test": self.libelle_source(parametres["test"]),
            "propositions": self.lire(self.fichier(ident, NOM_PROPOSITIONS)),
            "essai_test": self.lire(self.fichier(ident, NOM_ESSAI)),
        }

    def _cible(self, ident: str, corps: Mapping[str, Any]) -> tuple[str, str]:
        """(cible, base à écrire) d'une demande. Lève ErreurEcran."""
        parametres = self.tache_preparee(ident)["params"]
        cible = texte_corps(corps, "cible")
        if cible not in CIBLES:
            raise ErreurEcran("Cible inconnue : test ou production.")
        return cible, str(parametres[cible])

    # --- essai, feu vert, annulation -----------------------------------------
    def lancer_ecriture(
        self, ident: str, corps: Mapping[str, Any], ip: str
    ) -> str:
        """Essai sur la copie de test, ou production après feu vert.

        Production : mêmes choix que l'essai sur la copie de test, et nom
        de la base à compléter retapé. Lève ErreurEcran.
        """
        cible, source = self._cible(ident, corps)
        choix = self.choix_valides(ident, corps.get("choix"))
        nom_production = self.libelle_source(
            self.tache_preparee(ident)["params"]["production"]
        )
        if cible == "production":
            essai = self.lire(self.fichier(ident, NOM_ESSAI))
            if not essai or essai["choix"] != choix:
                raise ErreurEcran(
                    "Feu vert impossible : faire d'abord l'essai sur la copie "
                    "de test avec exactement les mêmes choix."
                )
            if texte_corps(corps, "confirmation") != nom_production:
                raise ErreurEcran(
                    "Nom de la base mal retapé : rien n'est écrit."
                )
        return self.taches.lancer(
            self.prefixe + "_ecrire",
            None,
            "%s — %s (%s)" % (nom_production, self.titre, cible),
            "",
            {
                "propositions": ident,
                "source": source,
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
        libelle = self.libelle_source(parametres["source"])
        bilan = self.ecrire_choix(
            self.acces(parametres["source"]),
            parametres["choix"],
            libelle,
            self.trace(tache),
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

    def trace(self, tache: ObjetJson) -> str:
        """Trace propre à une tâche d'écriture (une par tâche)."""
        parametres = tache["params"]
        return self.fichier(
            parametres["propositions"],
            "trace-%s-%s.jsonl" % (parametres["cible"], tache["id"]),
        )

    def traces(self, ident: str, cible: str) -> list[str]:
        """Traces d'écriture d'une préparation, la plus récente d'abord."""
        dossier = os.path.join(self.taches.dossier, ident)
        if not os.path.isdir(dossier):
            return []
        noms = [
            nom
            for nom in os.listdir(dossier)
            if nom.startswith("trace-%s-" % cible) and nom.endswith(".jsonl")
        ]
        chemins = [os.path.join(dossier, nom) for nom in noms]
        return sorted(chemins, key=os.path.getmtime, reverse=True)

    def _defaire_ecriture(
        self, tache: ObjetJson, journal: Journal
    ) -> ObjetJson:
        """Écriture arrêtée : remet les fiches qu'elle a écrites (ADR-0016)."""
        trace = self.trace(tache)
        if not os.path.isfile(trace):
            return {"remis": [], "ignores": []}
        bilan = annuler(self.acces(tache["params"]["source"]), trace)
        journal.dire(
            "%d fiche(s) remise(s), %d modifiée(s) depuis (laissée(s))"
            % (len(bilan["remis"]), len(bilan["ignores"])),
            "info",
        )
        return dict(bilan)

    def lancer_annulation(self, ident: str, corps: Mapping[str, Any]) -> str:
        """Remet les anciennes valeurs (test ou production).

        Lève ErreurEcran.
        """
        cible, source = self._cible(ident, corps)
        if not self.traces(ident, cible):
            raise ErreurEcran("Rien à annuler : aucune écriture tracée.")
        libelle = self.libelle_source(source)
        return self.taches.lancer(
            self.prefixe + "_annuler",
            None,
            "%s — annulation %s (%s)" % (libelle, self.titre, cible),
            "",
            {"propositions": ident, "source": source, "cible": cible},
        )

    def _travail_annuler(
        self, tache: ObjetJson, journal: Journal, guardian: Guardian
    ) -> None:
        """Tâche « <écran>_annuler » : anciennes valeurs remises."""
        parametres = tache["params"]
        acces = self.acces(parametres["source"])
        bilan: dict[str, list[int]] = {"remis": [], "ignores": []}
        for trace in self.traces(
            parametres["propositions"], parametres["cible"]
        ):
            un_bilan = annuler(acces, trace)
            bilan["remis"] += un_bilan["remis"]
            bilan["ignores"] += un_bilan["ignores"]
        guardian.tracer(self.prefixe, "annulation", json.dumps(bilan))
        tache["resultat"] = dict(bilan, cible=parametres["cible"])


def compter_classes(resultats: list[Mapping[str, Any]]) -> dict[str, int]:
    """Nombre de résultats par classe (« sure », « inscrit »…)."""
    comptes: dict[str, int] = {}
    for un_resultat in resultats:
        classe = str(un_resultat["classe"])
        comptes[classe] = comptes.get(classe, 0) + 1
    return comptes
