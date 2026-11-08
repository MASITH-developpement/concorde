# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Connecteur Odoo 17 : lecture et écriture par l'API XML-RPC (ADR-0008).

Paramètres : `url` (https://…, ou http://127.0.0.1 sur ce serveur), `base`,
`utilisateur` ; option `creer_manquants` = « oui » pour une base de test
vierge (comptes, journaux et tiers absents créés). Secret : `cle_api`.

Sur une vraie destination (`creer_manquants` absent), un compte, un journal
ou un tiers absent de la base BLOQUE l'écriture : rien n'est créé sans
arbitrage du comptable.

Lecture : core/odoo_source.SourceXmlRpcOdoo17 (lecture seule).
Écriture : core/migration/injection.envoyer (brouillon, validation,
lettrage ; références « <référence du transfert>/<journal>/<n°> »).
Relecture : par l'API, pour Odoo Online comme pour un Odoo sur site.
"""

from typing import ClassVar

from ..journal import Journal
from ..migration import injection
from ..migration.lot import LigneLot, Lot
from ..odoo_source import Enregistrement, ErreurSource, SourceXmlRpcOdoo17
from ..xml_sur import ErreurXmlRpc
from .base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    PerimetreLecture,
    ResultatEcriture,
    nouveau_lot,
)

# Erreurs d'Odoo ou du réseau, rendues en ErreurConnexion.
ERREURS_ODOO = (ErreurSource, injection.ErreurInjection, ErreurXmlRpc, OSError)


def ligne_depuis_odoo(numero: int, enregistrement: Enregistrement) -> LigneLot:
    """Ligne d'écriture Odoo (format de odoo_source) -> ligne du Lot.

    Rôle : un seul endroit qui traduit une ligne Odoo vers le pivot.
    Paramètres : numero — rang de la ligne ; enregistrement — ligne lue
    par SourceXmlRpcOdoo17.lignes (montants en centimes).
    Retour : LigneLot (compte cible vide).
    Erreurs : KeyError si un champ du format commun manque.
    Usages : ConnecteurOdoo.lire, ConnecteurOdoo.relire.
    """
    return {
        "n": numero,
        "journal_code": enregistrement["journal_code"],
        "journal_lib": enregistrement["journal_lib"],
        "ecriture": enregistrement["ecriture"],
        "date": enregistrement["date"],
        "compte": enregistrement["compte"],
        "compte_lib": enregistrement["compte_lib"],
        "tiers_ref": enregistrement["tiers_ref"],
        "tiers_nom": enregistrement["tiers_nom"],
        "piece": enregistrement["reference"] or enregistrement["ecriture"],
        "piece_date": enregistrement["piece_date"],
        "libelle": enregistrement["libelle"],
        "debit": enregistrement["debit"],
        "credit": enregistrement["credit"],
        "lettrage": enregistrement["lettrage"],
        "date_lettrage": enregistrement["date_lettrage"],
        "valid_date": None,
        "montant_devise": enregistrement["montant_devise"],
        "devise": enregistrement["devise"],
        "analytique": enregistrement["analytique"],
        "compte_cible": None,
    }


class ConnecteurOdoo(Connecteur):
    """Une base Odoo 17, lue et écrite par l'API XML-RPC."""

    logiciel = "odoo"
    libelle = "Odoo 17"
    capacites: ClassVar[CapacitesConnecteur] = {
        "lecture": "api",
        "ecriture": "api",
    }
    parametres_requis = ("url", "base", "utilisateur")
    secrets_requis = ("cle_api",)

    def _creer_manquants(self) -> bool:
        """Vrai pour une base de test vierge (paramètre creer_manquants)."""
        return self.parametres.get("creer_manquants", "").lower() == "oui"

    def _source(self, journal: Journal) -> SourceXmlRpcOdoo17:
        """Source de lecture (lecture seule). Lève ErreurConnexion."""
        try:
            return SourceXmlRpcOdoo17(
                self.parametres["url"],
                self.parametres["base"],
                self.parametres["utilisateur"],
                self._secrets["cle_api"],
                journal=journal,
            )
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc

    def _cible(self) -> injection.CibleOdoo:
        """Cible d'écriture. Lève ErreurConnexion."""
        try:
            return injection.CibleOdoo(
                self.parametres["url"],
                self.parametres["base"],
                self.parametres["utilisateur"],
                self._secrets["cle_api"],
            )
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc

    def tester(self, journal: Journal) -> InfoConnexion:
        """Se connecte et lit la société."""
        source = self._source(journal)
        try:
            societe = source.societe_info()
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc
        return {
            "logiciel": self.logiciel,
            "societe": str(societe["nom"]),
            "siren": str(societe["siren"]),
            "devise": str(societe["devise"]),
            "version": str(source.version_serveur),
        }

    def _lot(self, lignes: list[Enregistrement]) -> Lot:
        """Lignes Odoo lues -> Lot."""
        return nouveau_lot(
            self.logiciel,
            self.parametres["base"],
            [
                ligne_depuis_odoo(numero, enregistrement)
                for numero, enregistrement in enumerate(lignes, 1)
            ],
        )

    def lire(self, perimetre: PerimetreLecture, journal: Journal) -> Lot:
        """Lignes validées de la période."""
        source = self._source(journal)
        try:
            return self._lot(source.lignes(perimetre["du"], perimetre["au"]))
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Essai : ce qui manque et ce qui serait créé. Sinon : envoi."""
        cible = self._cible()
        cles = list(lot.ecritures())
        refs = [injection.ref_ecriture(reference, cle) for cle in cles]
        try:
            absents = injection.manquants(
                injection.rechercher_existants(cible, lot)
            )
            deja = injection.references_presentes(cible, refs)
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc
        erreurs = (
            []
            if self._creer_manquants()
            else [
                "Absents de la base %s : %s %s"
                % (self.parametres["base"], nature, ", ".join(codes))
                for nature, codes in absents.items()
            ]
        )
        resultat: ResultatEcriture = {
            "essai": essai,
            "ecritures_a_creer": len(refs) - len(deja),
            "ecritures_deja_presentes": len(deja),
            "erreurs": erreurs,
            "fichiers": {},
        }
        if essai or erreurs:
            return resultat
        try:
            envoi = injection.envoyer(
                cible, lot, journal, reference, self._creer_manquants()
            )
        except ERREURS_ODOO as exc:
            resultat["erreurs"].append(str(exc))
            return resultat
        resultat["erreurs"] = [
            "%s (%s) : %s"
            % (
                erreur_odoo["ecriture"],
                erreur_odoo["etape"],
                erreur_odoo["erreur"],
            )
            for erreur_odoo in envoi["erreurs"]
        ]
        return resultat

    def relire(self, reference: str, journal: Journal) -> Lot:
        """Écritures validées dont la référence commence par `reference`."""
        source = self._source(journal)
        try:
            lignes = source.lignes(reference_prefixe=reference)
        except ERREURS_ODOO as exc:
            raise ErreurConnexion("Odoo : %s" % exc) from exc
        return self._lot(lignes)
