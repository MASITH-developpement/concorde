# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Connecteur AzalPlus : lecture seule de la base PostgreSQL (ADR-0009).

AzalPlus est une SOURCE : l'écriture attend l'API v2 d'AzalPlus (point B
de l'ADR-0009). Paramètres : `hote`, `port`, `base` (« azals »),
`utilisateur` (rôle dédié en lecture seule), `tenant_id`, `societe_id` ;
option `sslmode` (« require » par défaut). Secret : `mot_de_passe`.

Règles (arbitrages de Stéphane du 08/11/2026) :
  - chaque requête filtre l'entreprise (`tenant_id`, comparé en UUID) et
    la société ; lignes supprimées et archivées exclues ;
  - statuts « VALIDEE » et « VALIDE » lus comme validés ; tout autre
    statut est exclu et compté ;
  - lignes sans société : jamais lues, comptées et signalées ;
  - tiers : AzalPlus porte le NOM du tiers. Un nom qui désigne un seul
    client ou fournisseur actif ayant un code donne ce code, signalé ;
    introuvable, sans code ou en double : ligne illisible (bloquant).
"""

import uuid
from collections.abc import Mapping
from types import TracebackType
from typing import Any, ClassVar, Protocol

from ..canonical import ErreurMontant
from ..journal import Journal, nombre_texte
from ..migration.lot import LigneIllisible, LigneLot, Lot
from ..odoo_source import centimes
from .base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    PerimetreLecture,
    nouveau_lot,
)

STATUTS_VALIDES = ("VALIDEE", "VALIDE")

_SQL_SOCIETE_AZALPLUS = """
SELECT count(*) FILTER (WHERE e.societe_id = %(societe)s),
       count(*) FILTER (WHERE e.societe_id IS NULL),
       count(*) FILTER (WHERE e.societe_id = %(societe)s
                        AND e.statut <> ALL(%(statuts)s))
FROM azalplus.comptabilite_ecritures e
WHERE e.tenant_id = %(tenant)s AND e.deleted_at IS NULL AND NOT e.archived
"""

_SQL_LIGNES_AZALPLUS = """
SELECT e.date_ecriture, e.journal,
       (SELECT j.libelle FROM azalplus.comptabilite_journaux j
         WHERE j.tenant_id = e.tenant_id AND j.code = e.journal
           AND j.deleted_at IS NULL
           AND (j.societe_id = e.societe_id OR j.societe_id IS NULL)
         ORDER BY j.societe_id NULLS LAST LIMIT 1),
       e.piece, e.piece_origine, e.compte, e.compte_libelle, e.tiers,
       e.libelle, e.debit, e.credit, e.code_lettrage, e.devise,
       e.montant_devise, e.analytique
FROM azalplus.comptabilite_ecritures e
WHERE e.tenant_id = %(tenant)s AND e.societe_id = %(societe)s
  AND e.deleted_at IS NULL AND NOT e.archived
  AND e.statut = ANY(%(statuts)s)
  AND (%(du)s::date IS NULL OR e.date_ecriture >= %(du)s::date)
  AND (%(au)s::date IS NULL OR e.date_ecriture <= %(au)s::date)
ORDER BY e.date_ecriture, e.journal, e.piece, e.id
"""

_SQL_TIERS_AZALPLUS = """
SELECT c.name, c.code FROM azalplus.clients c
 WHERE c.tenant_id = %(tenant)s AND c.deleted_at IS NULL
UNION ALL
SELECT f.raison_sociale, f.code FROM azalplus.fournisseurs f
 WHERE f.tenant_id = %(tenant)s AND f.deleted_at IS NULL
"""


class CurseurAzalPlus(Protocol):
    """Curseur PostgreSQL (DB-API) utilisé par le connecteur."""

    def __enter__(self) -> "CurseurAzalPlus":
        """Ouvre le bloc with."""

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> bool | None:
        """Ferme le bloc with."""

    def execute(self, requete: str, parametres: Mapping[str, object]) -> None:
        """Exécute une requête de lecture."""

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Toutes les lignes lues (types SQL variés)."""


class ConnexionAzalPlus(Protocol):
    """Connexion PostgreSQL (DB-API) utilisée par le connecteur."""

    def cursor(self, name: str | None = None) -> CurseurAzalPlus:
        """Ouvre un curseur (`name` : curseur côté serveur, non utilisé)."""

    def set_session(self, *, readonly: bool, autocommit: bool) -> None:
        """Règle le mode de la session."""

    def close(self) -> None:
        """Ferme la connexion."""


def resoudre_tiers(noms: Mapping[str, list[str]], nom: str) -> tuple[str, str]:
    """Code d'un tiers AzalPlus d'après son nom.

    Rôle : appliquer la règle des tiers (code trouvé par le nom, jamais
    deviné).
    Paramètres : noms — {nom: [codes des clients et fournisseurs actifs
    portant ce nom]} ; nom — tiers de la ligne.
    Retour : (code, motif) : code non vide si le tiers est trouvé, sinon
    motif du refus (introuvable, en double, sans code).
    Erreurs : aucune.
    Usages : ConnecteurAzalPlus.lire.
    """
    codes = noms.get(nom, [])
    if not codes:
        return "", (
            "tiers « %s » introuvable parmi les clients et fournisseurs" % nom
        )
    if len(codes) > 1:
        return "", "tiers « %s » porté par %d clients ou fournisseurs" % (
            nom,
            len(codes),
        )
    if not codes[0]:
        return "", "tiers « %s » sans code dans AzalPlus" % nom
    return codes[0], ""


class ConnecteurAzalPlus(Connecteur):
    """Une société d'une entreprise AzalPlus, lue dans PostgreSQL."""

    logiciel = "azalplus"
    libelle = "AzalPlus (lecture seule)"
    capacites: ClassVar[CapacitesConnecteur] = {
        "lecture": "base",
        "ecriture": None,
    }
    parametres_requis = (
        "hote",
        "port",
        "base",
        "utilisateur",
        "tenant_id",
        "societe_id",
    )
    parametres_facultatifs = ("sslmode",)
    secrets_requis = ("mot_de_passe",)

    def __init__(
        self,
        parametres: Mapping[str, str],
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        """Vérifie les paramètres ; entreprise et société en UUID.

        Lève ErreurConnexion si un paramètre manque ou si `tenant_id` /
        `societe_id` ne sont pas des UUID.
        """
        super().__init__(parametres, secrets)
        try:
            self.tenant = uuid.UUID(self.parametres["tenant_id"])
            self.societe = uuid.UUID(self.parametres["societe_id"])
        except ValueError as exc:
            raise ErreurConnexion(
                "AzalPlus : tenant_id et societe_id doivent être des UUID."
            ) from exc

    def _connecter(self) -> ConnexionAzalPlus:
        """Connexion en lecture seule. Lève ErreurConnexion."""
        try:
            import psycopg2  # dépendance optionnelle (ADR-0001)
        except ImportError as exc:
            raise ErreurConnexion(
                "AzalPlus : psycopg2 n'est pas installé."
            ) from exc
        try:
            connexion = psycopg2.connect(
                host=self.parametres["hote"],
                port=int(self.parametres["port"]),
                dbname=self.parametres["base"],
                user=self.parametres["utilisateur"],
                password=self._secrets["mot_de_passe"],
                sslmode=self.parametres.get("sslmode", "require"),
                connect_timeout=15,
            )
        except (psycopg2.Error, ValueError) as exc:
            raise ErreurConnexion("AzalPlus : %s" % exc) from exc
        connexion.set_session(readonly=True, autocommit=False)
        return connexion

    def _lire(
        self, requete: str, parametres: Mapping[str, object]
    ) -> list[tuple[Any, ...]]:
        """Exécute une requête de lecture. Lève ErreurConnexion."""
        connexion = self._connecter()
        import psycopg2  # déjà chargé par _connecter

        try:
            with connexion.cursor() as curseur:
                curseur.execute(requete, parametres)
                return curseur.fetchall()
        except psycopg2.Error as exc:
            raise ErreurConnexion("AzalPlus : %s" % exc) from exc
        finally:
            connexion.close()

    def _parametres_sql(self, **autres: object) -> dict[str, object]:
        """Paramètres communs : entreprise, société, statuts lus."""
        return dict(
            tenant=str(self.tenant),
            societe=str(self.societe),
            statuts=list(STATUTS_VALIDES),
            **autres,
        )

    def _compter(self, journal: Journal) -> tuple[int, int, int]:
        """(lignes de la société, sans société, autres statuts) ; signale."""
        rangs = self._lire(_SQL_SOCIETE_AZALPLUS, self._parametres_sql())
        de_la_societe, sans_societe, autres_statuts = (
            int(valeur or 0) for valeur in rangs[0]
        )
        if sans_societe:
            journal.dire(
                "%s ligne(s) d'écritures sans société dans AzalPlus : non "
                "lues, à rattacher à leur société dans AzalPlus"
                % nombre_texte(sans_societe),
                "alerte",
            )
        if autres_statuts:
            journal.dire(
                "%s ligne(s) ni « VALIDEE » ni « VALIDE » : non lues"
                % nombre_texte(autres_statuts),
                "alerte",
            )
        return de_la_societe, sans_societe, autres_statuts

    def tester(self, journal: Journal) -> InfoConnexion:
        """Se connecte, compte les lignes lisibles et celles écartées."""
        de_la_societe, _, _ = self._compter(journal)
        journal.dire(
            "AzalPlus : %s ligne(s) d'écritures pour la société %s"
            % (nombre_texte(de_la_societe), self.societe),
            "ok",
        )
        return {
            "logiciel": self.logiciel,
            "societe": str(self.societe),
            "siren": "",
            "devise": "EUR",
            "version": "base %s" % self.parametres["base"],
        }

    def lire(self, perimetre: PerimetreLecture, journal: Journal) -> Lot:
        """Lignes validées de la société et de la période -> Lot."""
        self._compter(journal)
        rangs = self._lire(
            _SQL_LIGNES_AZALPLUS,
            self._parametres_sql(du=perimetre["du"], au=perimetre["au"]),
        )
        noms: dict[str, list[str]] = {}
        for nom, code in self._lire(
            _SQL_TIERS_AZALPLUS, self._parametres_sql()
        ):
            noms.setdefault(nom or "", []).append(code or "")
        lignes: list[LigneLot] = []
        illisibles: list[LigneIllisible] = []
        trouves_par_nom: dict[str, str] = {}
        for numero, rang in enumerate(rangs, 1):
            (
                jour,
                code_journal,
                libelle_journal,
                piece,
                piece_origine,
                compte,
                compte_libelle,
                tiers,
                libelle,
                debit,
                credit,
                lettrage,
                devise,
                montant_devise,
                analytique,
            ) = rang
            code_tiers, motif = ("", "")
            if tiers:
                code_tiers, motif = resoudre_tiers(noms, tiers)
                if code_tiers:
                    trouves_par_nom[tiers] = code_tiers
            try:
                montants = (centimes(debit), centimes(credit))
                en_devise = (
                    centimes(montant_devise)
                    if devise and devise != "EUR"
                    else None
                )
            except ErreurMontant as exc:
                motif = str(exc)
                montants, en_devise = (0, 0), None
            if motif:
                illisibles.append(
                    (numero, "%s/%s" % (code_journal, piece), motif)
                )
            lignes.append(
                {
                    "n": numero,
                    "journal_code": code_journal or "",
                    "journal_lib": libelle_journal or "",
                    "ecriture": piece or "",
                    "date": jour,
                    "compte": compte or "",
                    "compte_lib": compte_libelle or "",
                    "tiers_ref": code_tiers,
                    "tiers_nom": tiers or "",
                    "piece": piece_origine or piece or "",
                    "piece_date": None,
                    "libelle": libelle or "",
                    "debit": montants[0],
                    "credit": montants[1],
                    "lettrage": lettrage or "",
                    "date_lettrage": None,
                    "valid_date": None,
                    "montant_devise": en_devise,
                    "devise": devise if en_devise is not None else "",
                    "analytique": analytique or "",
                    "compte_cible": None,
                }
            )
        lot = nouveau_lot(self.logiciel, str(self.societe), lignes)
        lot.illisibles = illisibles
        lot.signalements = [
            "tiers « %s » retrouvé par son nom : code %s" % (nom, code)
            for nom, code in sorted(trouves_par_nom.items())
        ]
        journal.dire(
            "AzalPlus : %s ligne(s) lue(s), %s tiers retrouvé(s) par leur "
            "nom, %s ligne(s) bloquée(s)"
            % (
                nombre_texte(len(lignes)),
                nombre_texte(len(trouves_par_nom)),
                nombre_texte(len(illisibles)),
            ),
            "ok" if not illisibles else "alerte",
        )
        return lot
