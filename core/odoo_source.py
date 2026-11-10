# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Lecture des données comptables d'un Odoo 17 — deux sources, un seul format.

  SourceSqlOdoo17     lecture directe PostgreSQL (rapide : ~150 000 lignes en
                      quelques secondes). Transaction en LECTURE SEULE.
                      psycopg2 est chargé uniquement pour cette source.
                      Identifiants : variables libpq (PGHOST, PGPORT, PGUSER,
                      PGPASSWORD) — jamais en argument.
  SourceXmlRpcOdoo17  passe par l'API d'Odoo (marche partout, Odoo Online
                      compris). Clé API dans ODOO_API_KEY. LECTURE SEULE :
                      seules search_read / read / fields_get sont autorisées.

Les deux sources rendent exactement les mêmes enregistrements (dict) :
le reste de CONCORDE ne sait pas d'où viennent les données.

Montants : TOUJOURS en centimes (int). Un montant Odoo qui ne tombe pas
juste au centime est refusé (ErreurMontant), jamais arrondi.

ÉCRITURE : aucune ici. Les écritures dans Odoo passent toujours par l'ORM
(XML-RPC, injectors/), jamais par SQL (ADR-0001).
"""

import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from http.client import HTTPConnection, HTTPSConnection
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from .canonical import ErreurMontant
from .journal import Journal, duree_texte, nombre_texte, ou_muet
from .xml_sur import (
    ProxyXmlRpc,
    TransportXmlRpc,
    TransportXmlRpcSur,
)

if TYPE_CHECKING:
    # Import réservé au typage : surveillance importe (via analyser) ce
    # module, l'importer ici à l'exécution créerait un cycle.
    from .surveillance import Instantane

# Types de comptes Odoo 17 qui portent un compte auxiliaire (tiers).
TYPES_TIERS = ("asset_receivable", "liability_payable")

# Lignes de facture purement décoratives : jamais comptables.
TYPES_AFFICHAGE = ("line_section", "line_note")

TYPES_FACTURE = ("out_invoice", "out_refund", "in_invoice", "in_refund")

ETATS = ("posted", "draft", "cancel")

# Enregistrement rendu par une source (ligne, compte, journal, tiers,
# facture, solde) : dictionnaire au schéma décrit dans « Format commun »
# ci-dessous, dont les valeurs viennent de PostgreSQL ou de XML-RPC
# (texte, centimes, dates, booléens, identifiants).
Enregistrement = dict[str, Any]

# Critère d'un domaine Odoo : opérateur logique (« | ») ou
# (champ, opérateur, valeur).
CritereDomaine = str | tuple[str, str, object]
Domaine = list[CritereDomaine]

# Hôte accepté par TransportXmlRpc.make_connection.
HoteXmlRpc = str | tuple[str, dict[str, str]]

_ConnexionHttp = TypeVar("_ConnexionHttp", bound=HTTPConnection)


class ErreurSource(RuntimeError):
    """Erreur explicite de lecture (connexion, version, paramètre)."""


class SourceOdoo(Protocol):
    """Interface commune des sources Odoo 17 (SQL et XML-RPC)."""

    nature: str
    base: str
    societe: int

    def societe_info(self) -> Enregistrement:
        """Identité de la société lue (nom, SIREN, TVA, devise)."""

    def lignes(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
        comptes: Iterable[str] | None = None,
        ecriture: int | None = None,
    ) -> Iterable[Enregistrement]:
        """Lignes d'écritures triées comme `cle_tri`."""

    def balance(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Balance générale de tous les comptes du plan."""

    def balance_tiers(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Soldes par compte client / fournisseur et par tiers."""

    def soldes(
        self, depuis: date | None = None, jusqu_au: date | None = None
    ) -> list[Enregistrement]:
        """Soldes comptabilisés par (compte, tiers), bornes comprises."""

    def parametres_comptables(self) -> Enregistrement:
        """Fin d'exercice, écriture d'ouverture, journal de TVA sur
        encaissements de la société."""

    def ecritures_ouverture(
        self, journaux: Sequence[str], fin: date | None = None
    ) -> list[Enregistrement]:
        """Écritures d'à-nouveaux (validées ou brouillons)."""

    def nombre_lignes_avant(self, jour: date) -> int:
        """Nombre de lignes comptabilisées datées avant `jour`."""

    def comptes(self) -> list[Enregistrement]:
        """Plan comptable de la société."""

    def journaux(self) -> list[Enregistrement]:
        """Journaux de la société."""

    def tiers(self) -> list[Enregistrement]:
        """Tiers (partenaires) visibles par la société."""

    def factures(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ETATS,
    ) -> list[Enregistrement]:
        """Factures et avoirs clients / fournisseurs."""

    def ecriture(self, ident: int | str) -> list[Enregistrement]:
        """Une écriture et ses lignes (tous états confondus)."""

    def verrous(self) -> dict[str, date | None]:
        """Dates de verrouillage : période, exercice, TVA."""

    def instantane(self) -> "Instantane":
        """Photo légère de la base (écritures, comptes, verrous)."""

    def noms_analytiques(self) -> dict[int, str]:
        """{id: code ou nom} des comptes analytiques."""

    def fermer(self) -> None:
        """Libère la connexion éventuelle."""


# ---------------------------------------------------------------------------
# Conversions strictes
# ---------------------------------------------------------------------------


def centimes(valeur: object) -> int:
    """Convertit un montant Odoo en centimes entiers, sans arrondi.

    Rôle : seule porte d'entrée des montants Odoo (Decimal SQL ou float
    XML-RPC). repr() d'un float XML-RPC rend la valeur décimale stockée
    par Odoo (ex. 123.45 -> '123.45') : la conversion est exacte.
    Paramètres : valeur — montant Odoo ; None ou False valent 0.
    Retour : le montant en centimes (int).
    Erreurs : ErreurMontant si le montant ne tombe pas juste au centime
    (arrondi silencieux interdit).
    Usages : sources SQL et XML-RPC de ce module, tests.
    """
    if valeur in (None, False):
        return 0
    d = valeur if isinstance(valeur, Decimal) else Decimal(repr(valeur))
    c = d * 100
    if c != c.to_integral_value():
        raise ErreurMontant("Montant Odoo non exact au centime : %s" % valeur)
    return int(c)


def _date(val: object) -> date | None:
    """Convertit une date Odoo (date, datetime ou texte ISO) ; vide -> None."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


def _texte(val: object) -> str:
    """Convertit un texte Odoo en str.

    False ou None -> '' ; dict de traductions (jsonb) -> fr_FR, puis
    en_US, puis la première traduction.
    """
    if val in (None, False):
        return ""
    if isinstance(val, dict):
        traduction = (
            val.get("fr_FR")
            or val.get("en_US")
            or next(iter(val.values()), "")
        )
        return "" if traduction in (None, False) else str(traduction)
    return str(val)


def _m2o(val: object) -> tuple[Any, Any]:
    """Rend (id, nom) d'un many2one XML-RPC ; (None, '') si vide.

    Les éléments viennent tels quels de la réponse XML-RPC (Any).
    """
    if isinstance(val, (list, tuple)) and val:
        return val[0], (val[1] if len(val) > 1 else "")
    return None, ""


def _lots(liste: Sequence[int], taille: int) -> Iterator[Sequence[int]]:
    """Découpe `liste` en tranches successives d'au plus `taille` éléments."""
    for debut_lot in range(0, len(liste), taille):
        fin_lot = debut_lot + taille
        yield liste[debut_lot:fin_lot]


def _periode_texte(debut: date | None, fin: date | None) -> str:
    """Décrit la période lue pour le journal (« , du … au … »)."""
    if debut and fin:
        return ", du %s au %s" % (
            debut.strftime("%d/%m/%Y"),
            fin.strftime("%d/%m/%Y"),
        )
    if debut:
        return ", depuis le %s" % debut.strftime("%d/%m/%Y")
    if fin:
        return ", jusqu'au %s" % fin.strftime("%d/%m/%Y")
    return ", toutes dates"


def balance_depuis_lignes(
    comptes: Iterable[Mapping[str, Any]], lignes: Iterable[Mapping[str, Any]]
) -> list[Enregistrement]:
    """Calcule la balance en Python (source XML-RPC), au format de la SQL.

    Rôle : totaliser débit, crédit, lignes et lignes non lettrées par compte.
    Paramètres : comptes — plan comptable (`comptes()`) ; lignes — lignes
    d'écritures (`lignes()`).
    Retour : un enregistrement par compte du plan, trié par code.
    Erreurs : KeyError si une clé attendue manque.
    Usages : `SourceXmlRpcOdoo17.balance`.
    """
    par_code = {
        c["code"]: dict(c, debit=0, credit=0, lignes=0, non_lettrees=0)
        for c in comptes
    }
    for ligne in lignes:
        c = par_code.get(ligne["compte"])
        if c is None:
            continue
        c["debit"] += ligne["debit"]
        c["credit"] += ligne["credit"]
        c["lignes"] += 1
        if (
            c["lettrable"]
            and not ligne["lettrage"]
            and (ligne["debit"] or ligne["credit"])
        ):
            c["non_lettrees"] += 1
    return sorted(par_code.values(), key=lambda c: c["code"])


def balance_tiers_depuis_lignes(
    lignes: Iterable[Mapping[str, Any]],
    types: Sequence[str] | None = TYPES_TIERS,
) -> list[Enregistrement]:
    """Calcule les soldes par compte et par tiers en Python.

    Rôle : totaliser débit, crédit et lignes par (compte, tiers).
    Paramètres : lignes — lignes portant compte, tiers_id, tiers_nom,
    tiers_ref, debit, credit (et compte_type si `types` est donné) ;
    types — types de comptes retenus (clients et fournisseurs par défaut),
    None pour tous les comptes.
    Retour : un enregistrement par (compte, tiers), au format de la SQL.
    Erreurs : KeyError si une clé attendue manque.
    Usages : `SourceXmlRpcOdoo17.balance_tiers` et `.soldes`.
    """
    groupes: dict[tuple[str, int | None], Enregistrement] = {}
    for ligne in lignes:
        if types is not None and ligne["compte_type"] not in types:
            continue
        g = groupes.setdefault(
            (ligne["compte"], ligne["tiers_id"]),
            {
                "compte": ligne["compte"],
                "tiers_id": ligne["tiers_id"],
                "tiers_nom": ligne["tiers_nom"],
                "tiers_ref": ligne["tiers_ref"],
                "debit": 0,
                "credit": 0,
                "lignes": 0,
            },
        )
        g["debit"] += ligne["debit"]
        g["credit"] += ligne["credit"]
        g["lignes"] += 1
    return list(groupes.values())


def _comptes_de_cle(cle: object, noms: Mapping[int, str]) -> Iterator[str]:
    """Traduit une clé de répartition (« 86,252 ») en codes ou noms.

    Rôle : décoder les identifiants de comptes analytiques d'une clé.
    Paramètres : cle — clé de `analytic_distribution` ; noms — {id: code ou
    nom} des comptes analytiques.
    Retour : un libellé par identifiant (« #id » si le compte a disparu).
    Erreurs : ValueError si un identifiant n'est pas un entier.
    Usages : `analytique_texte`, `analytique_comptes`.
    """
    return (
        noms.get(int(i), "#%s" % i)
        for i in str(cle).split(",")
        if str(i).strip()
    )


def analytique_texte(
    distribution: Mapping[str, float] | None, noms: Mapping[int, str]
) -> str:
    """Rend une répartition analytique Odoo 17 en texte stable.

    Rôle : rendre comparable entre bases une répartition
    {"86,252": 98.76, ...} : chaque clé combine un compte par plan, les
    identifiants sont traduits en code (ou nom).
    Paramètres : distribution — `analytic_distribution` d'une ligne
    (None ou vide : aucune) ; noms — {id: libellé} des comptes analytiques.
    Retour : « CODE1+CODE2 98.76 % ; … » (pourcentages à 2 décimales,
    éléments triés) ou ''.
    Erreurs : ValueError si un identifiant ou un pourcentage est invalide.
    Usages : `SourceSqlOdoo17.lignes`, `SourceXmlRpcOdoo17.lignes`, tests.
    """
    if not distribution:
        return ""
    parts = []
    for cle, pct in distribution.items():
        comptes = "+".join(sorted(_comptes_de_cle(cle, noms)))
        parts.append(
            "%s %s %%"
            % (comptes, ("%.2f" % float(pct)).rstrip("0").rstrip("."))
        )
    return " ; ".join(sorted(parts))


def analytique_comptes(
    distribution: Mapping[str, float] | None, noms: Mapping[int, str]
) -> list[str]:
    """Liste les comptes analytiques touchés par une répartition.

    Rôle : permettre le filtre par compte analytique (comparaison).
    Paramètres : distribution — `analytic_distribution` d'une ligne ;
    noms — {id: code ou nom} des comptes analytiques.
    Retour : codes (ou noms) triés, sans doublon ; [] sans répartition.
    Erreurs : ValueError si un identifiant n'est pas un entier.
    Usages : `SourceSqlOdoo17.lignes`, `SourceXmlRpcOdoo17.lignes`, tests.
    """
    if not distribution:
        return []
    return sorted(
        {
            libelle
            for cle in distribution
            for libelle in _comptes_de_cle(cle, noms)
        }
    )


def cle_tri(ligne: Mapping[str, Any]) -> tuple[date, str, int, int]:
    """Clé d'ordre stable : date, numéro, id d'écriture, id de ligne.

    L'id d'écriture départage les brouillons, tous numérotés « / ».
    """
    return (
        ligne["date"] or date.min,
        ligne["ecriture"],
        ligne["ecriture_id"],
        ligne["ligne_id"],
    )


def _verrous_texte(
    verrous: Mapping[str, date | None],
) -> dict[str, str | None]:
    """Rend les dates de verrouillage au format ISO (None si absente).

    Usages : `SourceSqlOdoo17.instantane`, `SourceXmlRpcOdoo17.instantane`.
    """
    return {k: (d.isoformat() if d else None) for k, d in verrous.items()}


def transport_xmlrpc(url: str, delai: float) -> TransportXmlRpc:
    """Crée le transport XML-RPC adapté à `url`, avec délai d'attente.

    Rôle : borner la durée de chaque appel XML-RPC (HTTP ou HTTPS).
    Paramètres : url — adresse du serveur (https://… => connexion
    chiffrée) ; delai — délai d'attente en secondes.
    Retour : un transport à passer à `ProxyXmlRpc`.
    Erreurs : aucune (les erreurs réseau surviennent à l'appel).
    Usages : `proxys_xmlrpc`, `interface.serveur.Surveillance._verifier_odoo`.
    """
    if url.startswith("https"):
        return _TransportSurDelai(delai)
    return _TransportDelai(delai)


def proxys_xmlrpc(url: str, delai: float) -> tuple[ProxyXmlRpc, ProxyXmlRpc]:
    """Accès XML-RPC « common » et « object » d'un serveur Odoo.

    Rôle : un seul endroit qui ouvre l'API XML-RPC d'Odoo (délai borné,
    XML lu sans risque, None autorisé dans les échanges).
    Paramètres : url — adresse du serveur, sans / final ; delai — délai
    d'attente de chaque appel, en secondes.
    Retour : (proxy common, proxy object).
    Erreurs : aucune ici (les erreurs réseau surviennent à l'appel).
    Usages : SourceXmlRpcOdoo17, core.demat.SourceXmlRpc,
    tests/integration/verifier_photo.
    """
    return (
        ProxyXmlRpc(
            url + "/xmlrpc/2/common",
            transport=transport_xmlrpc(url, delai),
            allow_none=True,
        ),
        ProxyXmlRpc(
            url + "/xmlrpc/2/object",
            transport=transport_xmlrpc(url, delai),
            allow_none=True,
        ),
    )


def _avec_delai(connexion: _ConnexionHttp, delai: float) -> _ConnexionHttp:
    """Applique le délai d'attente à une connexion HTTP et la rend.

    Usages : `_TransportDelai`, `_TransportSurDelai`.
    """
    connexion.timeout = delai
    return connexion


class _TransportDelai(TransportXmlRpc):
    """Transport XML-RPC HTTP avec délai d'attente."""

    def __init__(self, delai: float) -> None:
        """Mémorise le délai d'attente (secondes)."""
        super().__init__()
        self.delai = delai

    def make_connection(self, host: HoteXmlRpc) -> HTTPConnection:
        """Ouvre la connexion HTTP avec le délai d'attente."""
        return _avec_delai(super().make_connection(host), self.delai)


class _TransportSurDelai(TransportXmlRpcSur):
    """Transport XML-RPC HTTPS avec délai d'attente."""

    def __init__(self, delai: float) -> None:
        """Mémorise le délai d'attente (secondes)."""
        super().__init__()
        self.delai = delai

    def make_connection(self, host: HoteXmlRpc) -> HTTPSConnection:
        """Ouvre la connexion HTTPS avec le délai d'attente."""
        return _avec_delai(super().make_connection(host), self.delai)


# ---------------------------------------------------------------------------
# Format commun des enregistrements
# ---------------------------------------------------------------------------
#
# ligne d'écriture :
#   ligne_id, ecriture_id, ecriture (nom), type_piece (move_type), etat,
#   journal_code, journal_lib, date, piece_date, reference,
#   compte, compte_lib, compte_type, tiers_id, tiers_ref, tiers_nom,
#   libelle, debit, credit (centimes), lettrage, date_lettrage,
#   montant_devise (centimes, signé), devise, echeance, modifie_le,
#   auto_post ('no' ou planification : brouillon comptabilisé
#              automatiquement),
#   analytique (texte stable : « CODE1+CODE2 98.76 % ; … », comptes par
#               code ou nom — comparable d'une base à l'autre ; '' si
#               aucune répartition),
#   analytique_comptes (liste triée des comptes analytiques touchés)
#
# compte  : id, code, libelle, type, lettrable, deprecie
# journal : id, code, libelle, type, actif
# tiers   : id, nom, ref, tva, siren, email, telephone, rue, cp, ville,
#           pays, societe, actif, client, fournisseur, parent_id
# facture : id, numero, type_piece, etat, etat_paiement, journal_code,
#           tiers_id, tiers_nom, date, date_facture, echeance, reference,
#           ht, tva, ttc, reste_du (centimes, signés comme Odoo), devise


# ---------------------------------------------------------------------------
# Source SQL (PostgreSQL, lecture seule)
# ---------------------------------------------------------------------------

_SQL_LIGNES = """
SELECT aml.id, am.id, am.name, am.move_type, am.state,
       aj.code, COALESCE(aj.name->>'fr_FR', aj.name->>'en_US'),
       am.date, am.invoice_date, am.ref,
       aa.code, COALESCE(aa.name->>'fr_FR', aa.name->>'en_US'),
       aa.account_type,
       rp.id, rp.ref, rp.name,
       aml.name, aml.debit, aml.credit,
       CASE WHEN aml.full_reconcile_id IS NOT NULL
            THEN aml.matching_number END,
       afr.create_date,
       CASE WHEN aml.currency_id <> aml.company_currency_id
            THEN aml.amount_currency END,
       CASE WHEN aml.currency_id <> aml.company_currency_id
            THEN cur.name END,
       aml.date_maturity, GREATEST(am.write_date, aml.write_date),
       am.auto_post,
       aml.analytic_distribution,
       am.tax_cash_basis_rec_id, am.reversed_entry_id
  FROM account_move_line aml
  JOIN account_move am ON am.id = aml.move_id
  JOIN account_journal aj ON aj.id = am.journal_id
  LEFT JOIN account_account aa ON aa.id = aml.account_id
  LEFT JOIN res_partner rp ON rp.id = aml.partner_id
  LEFT JOIN account_full_reconcile afr ON afr.id = aml.full_reconcile_id
  LEFT JOIN res_currency cur ON cur.id = aml.currency_id
 WHERE aml.company_id = %(societe)s
   AND am.state = ANY(%(etats)s)
   AND (aml.display_type IS NULL OR aml.display_type <> ALL(%(affichage)s))
   AND (%(debut)s::date IS NULL OR am.date >= %(debut)s::date)
   AND (%(fin)s::date IS NULL OR am.date <= %(fin)s::date)
   AND (%(comptes)s::text[] IS NULL OR aa.code = ANY(%(comptes)s::text[]))
   AND (%(ecriture)s::int IS NULL OR am.id = %(ecriture)s::int)
 ORDER BY am.date, am.name, am.id, aml.id
"""

PAS_PROGRESSION = (
    25000  # le journal annonce l'avancement toutes les 25 000 lignes
)

_SQL_BALANCE = """
SELECT aa.id, aa.code, COALESCE(aa.name->>'fr_FR', aa.name->>'en_US'),
       aa.account_type, aa.reconcile, aa.deprecated,
       COALESCE(SUM(aml.debit), 0), COALESCE(SUM(aml.credit), 0),
       COUNT(aml.id),
       COUNT(aml.id) FILTER (WHERE aa.reconcile AND NOT aml.reconciled
                             AND aml.amount_residual <> 0)
  FROM account_account aa
  LEFT JOIN account_move_line aml ON aml.account_id = aa.id
       AND aml.company_id = %(societe)s
       AND aml.parent_state = ANY(%(etats)s)
       AND (aml.display_type IS NULL
            OR aml.display_type <> ALL(%(affichage)s))
       AND (%(debut)s::date IS NULL OR aml.date >= %(debut)s::date)
       AND (%(fin)s::date IS NULL OR aml.date <= %(fin)s::date)
 WHERE aa.company_id = %(societe)s
 GROUP BY aa.id
 ORDER BY aa.code
"""

# Soldes par (compte, tiers) : comptes clients / fournisseurs (`types`)
# ou tous les comptes (`types` NULL).
_SQL_BALANCE_TIERS = """
SELECT aa.code, rp.id, rp.name, rp.ref,
       SUM(aml.debit), SUM(aml.credit), COUNT(*)
  FROM account_move_line aml
  JOIN account_account aa ON aa.id = aml.account_id
  LEFT JOIN res_partner rp ON rp.id = aml.partner_id
 WHERE aml.company_id = %(societe)s
   AND aml.parent_state = ANY(%(etats)s)
   AND (%(types)s::text[] IS NULL
        OR aa.account_type = ANY(%(types)s::text[]))
   AND (%(debut)s::date IS NULL OR aml.date >= %(debut)s::date)
   AND (%(fin)s::date IS NULL OR aml.date <= %(fin)s::date)
 GROUP BY aa.code, rp.id, rp.name, rp.ref
"""

# Écritures d'à-nouveaux : ouverture déclarée dans la société, ou
# écriture d'un des journaux donnés ; validées ou brouillons.
_SQL_OUVERTURE = """
SELECT am.id, am.name, am.date, am.state, aj.code
  FROM account_move am
  JOIN account_journal aj ON aj.id = am.journal_id
 WHERE am.company_id = %(societe)s
   AND am.state IN ('posted', 'draft')
   AND (am.id = %(ouverture)s::int OR aj.code = ANY(%(journaux)s::text[]))
   AND (%(fin)s::date IS NULL OR am.date <= %(fin)s::date)
 ORDER BY am.date, am.id
"""

_CHAMPS_LIGNE = (
    "ligne_id",
    "ecriture_id",
    "ecriture",
    "type_piece",
    "etat",
    "journal_code",
    "journal_lib",
    "date",
    "piece_date",
    "reference",
    "compte",
    "compte_lib",
    "compte_type",
    "tiers_id",
    "tiers_ref",
    "tiers_nom",
    "libelle",
    "debit",
    "credit",
    "lettrage",
    "date_lettrage",
    "montant_devise",
    "devise",
    "echeance",
    "modifie_le",
    "auto_post",
    "analytique",
    "caba_rapprochement_id",
    "extourne_de_id",
)


# Champs texte d'une ligne SQL : NULL -> ''.
_CHAMPS_TEXTE_LIGNE = (
    "ecriture",
    "reference",
    "compte",
    "compte_lib",
    "compte_type",
    "tiers_ref",
    "tiers_nom",
    "libelle",
    "lettrage",
    "devise",
    "journal_lib",
    "auto_post",
)

_ETATS_TEXTE = {
    "posted": "validées",
    "draft": "brouillons",
    "cancel": "annulées",
}


class ConnexionSql(Protocol):
    """Connexion PostgreSQL (DB-API psycopg2) utilisée par la source SQL."""

    def cursor(self, name: str | None = None) -> Any:
        """Ouvre un curseur (nommé = côté serveur) ; objet psycopg2."""

    def set_session(self, *, readonly: bool, autocommit: bool) -> None:
        """Règle le mode de la session (lecture seule ici)."""

    def rollback(self) -> None:
        """Termine la transaction de lecture."""

    def close(self) -> None:
        """Ferme la connexion."""


def connexion_lecture_seule(
    base: str, acces: Mapping[str, str] | None = None
) -> ConnexionSql:
    """Ouvre une connexion PostgreSQL en lecture seule vers `base`.

    Rôle : la seule ouverture de connexion SQL vers une base Odoo.
    Paramètres : base — nom de la base ; acces — host, user, password
    d'un PostgreSQL jetable de montée de version (ADR-0012) ; sans lui,
    tout vient des variables PG* (libpq).
    Retour : connexion psycopg2, session en lecture seule.
    Erreurs : ErreurSource si psycopg2 n'est pas installé ;
    psycopg2.Error si la base est injoignable.
    Usages : SourceSqlOdoo17, montee_version (photo, inventaire).
    """
    try:
        import psycopg2  # dépendance optionnelle (ADR-0001)
    except ImportError as exc:
        raise ErreurSource(
            "Lecture SQL indisponible : psycopg2 n'est pas installé "
            "(utilisez --source xmlrpc)."
        ) from exc
    if acces is None:
        connexion: ConnexionSql = psycopg2.connect(dbname=base)
    else:
        connexion = psycopg2.connect(
            dbname=base,
            host=acces["host"],
            user=acces["user"],
            password=acces["password"],
        )
    connexion.set_session(readonly=True, autocommit=False)
    return connexion


class SourceSqlOdoo17:
    """Lecture directe de la base PostgreSQL d'un Odoo 17 (lecture seule)."""

    nature = "sql"
    TAILLE_LOT = 5000

    def __init__(
        self,
        base: str,
        societe: int | None = None,
        connexion: ConnexionSql | None = None,
        journal: Journal | None = None,
    ) -> None:
        """Ouvre la connexion en lecture seule et vérifie la version.

        Identifiants : variables PG* (libpq), jamais en argument.
        Erreurs : ErreurSource (psycopg2 absent, base non Odoo 17, base
        multi-sociétés sans `societe`).
        """
        self.journal = ou_muet(journal)
        self._noms_an: dict[int, str] | None = None
        self.journal.dire(
            "Connexion à la base %s (PostgreSQL, lecture seule)" % base
        )
        if connexion is None:
            connexion = connexion_lecture_seule(base)
        connexion.set_session(readonly=True, autocommit=False)
        self._cx = connexion
        self.base = base
        try:
            self.version_serveur = self._version()
            if not self.version_serveur.startswith("17."):
                raise ErreurSource(
                    "Base %s : Odoo %s, cette source ne lit que Odoo 17."
                    % (base, self.version_serveur)
                )
            self.societe = societe or self._societe_unique()
        except Exception:
            connexion.close()  # pas d'Odoo 17 ici : on ne laisse rien ouvert
            raise
        self.journal.dire(
            "Connecté : Odoo %s, société n° %s"
            % (self.version_serveur, self.societe),
            "detail",
        )

    def _requete(
        self, sql: str, params: Mapping[str, object] | None = None
    ) -> list[tuple[Any, ...]]:
        """Exécute une requête de lecture et rend toutes ses lignes.

        Les valeurs viennent de psycopg2 (types SQL variés).
        """
        with self._cx.cursor() as cur:
            cur.execute(sql, params or {})
            lignes: list[tuple[Any, ...]] = cur.fetchall()
            return lignes

    def _version(self) -> str:
        """Version du module `base` installé (« ? » si introuvable)."""
        lignes = self._requete(
            "SELECT latest_version FROM ir_module_module WHERE name = 'base'"
        )
        if not lignes:
            return "?"
        version: str = lignes[0][0]
        return version

    def _societe_unique(self) -> int:
        """Identifiant de l'unique société ; ErreurSource sinon."""
        ids: list[int] = [
            r[0]
            for r in self._requete("SELECT id FROM res_company ORDER BY id")
        ]
        if len(ids) != 1:
            raise ErreurSource(
                "Base multi-sociétés (%s) : précisez --societe <id>." % ids
            )
        return ids[0]

    def societe_info(self) -> Enregistrement:
        """Identité de la société lue (nom, SIREN, TVA, devise)."""
        r = self._requete(
            "SELECT c.name, p.company_registry, p.vat, cur.name "
            "FROM res_company c "
            "JOIN res_partner p ON p.id = c.partner_id "
            "JOIN res_currency cur ON cur.id = c.currency_id "
            "WHERE c.id = %(s)s",
            {"s": self.societe},
        )[0]
        return {
            "id": self.societe,
            "nom": r[0],
            "siren": r[1] or "",
            "tva": r[2] or "",
            "devise": r[3],
        }

    def lignes(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
        comptes: Iterable[str] | None = None,
        ecriture: int | None = None,
    ) -> Iterator[Enregistrement]:
        """Lignes d'écritures, triées comme cle_tri. Générateur.

        comptes : liste de codes (grand livre) ; ecriture : id d'une écriture.
        """
        params = {
            "societe": self.societe,
            "etats": list(etats),
            "affichage": list(TYPES_AFFICHAGE),
            "debut": debut,
            "fin": fin,
            "comptes": list(comptes) if comptes else None,
            "ecriture": ecriture,
        }
        bavard = comptes is None and ecriture is None
        if bavard:
            self.journal.dire(
                "Lecture des lignes d'écritures (%s%s)"
                % (
                    ", ".join(_ETATS_TEXTE.get(e, e) for e in etats),
                    _periode_texte(debut, fin),
                )
            )
        debut_t = time.monotonic()
        n = 0
        # Curseur nommé = côté serveur : la mémoire reste stable sur
        # 150 000 lignes.
        with self._cx.cursor(name="concorde_lignes") as cur:
            cur.itersize = self.TAILLE_LOT
            cur.execute(_SQL_LIGNES, params)
            for r in cur:
                n += 1
                if bavard and n % PAS_PROGRESSION == 0:
                    self.journal.dire(
                        "… %s lignes lues" % nombre_texte(n), "detail"
                    )
                ligne: Enregistrement = dict(zip(_CHAMPS_LIGNE, r))
                ligne["debit"] = centimes(ligne["debit"])
                ligne["credit"] = centimes(ligne["credit"])
                ligne["montant_devise"] = (
                    centimes(ligne["montant_devise"])
                    if ligne["montant_devise"] is not None
                    else None
                )
                ligne["date_lettrage"] = _date(ligne["date_lettrage"])
                repartition = ligne["analytique"]
                ligne["analytique"] = analytique_texte(
                    repartition, self.noms_analytiques()
                )
                ligne["analytique_comptes"] = analytique_comptes(
                    repartition, self.noms_analytiques()
                )
                for k in _CHAMPS_TEXTE_LIGNE:
                    ligne[k] = ligne[k] or ""
                yield ligne
        self._cx.rollback()
        if bavard:
            self.journal.dire(
                "%s lignes lues en %s"
                % (nombre_texte(n), duree_texte(time.monotonic() - debut_t)),
                "ok",
            )

    def noms_analytiques(self) -> dict[int, str]:
        """{id: code ou nom} des comptes analytiques (mis en cache)."""
        if self._noms_an is None:
            self._noms_an = {
                r[0]: r[1] or ""
                for r in self._requete(
                    "SELECT id, COALESCE(NULLIF(code, ''), name->>'fr_FR', "
                    "name->>'en_US') FROM account_analytic_account"
                )
            }
        return self._noms_an

    def balance(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Balance générale : tous les comptes du plan, mouvementés ou non."""
        t = time.monotonic()
        res = [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "lettrable": bool(r[4]),
                "deprecie": bool(r[5]),
                "debit": centimes(r[6]),
                "credit": centimes(r[7]),
                "lignes": r[8],
                "non_lettrees": r[9],
            }
            for r in self._requete(
                _SQL_BALANCE,
                {
                    "societe": self.societe,
                    "etats": list(etats),
                    "debut": debut,
                    "fin": fin,
                    "affichage": list(TYPES_AFFICHAGE),
                },
            )
        ]
        self.journal.dire(
            "Balance calculée : %s comptes, dont %s mouvementés (%s)"
            % (
                nombre_texte(len(res)),
                nombre_texte(sum(1 for c in res if c["lignes"])),
                duree_texte(time.monotonic() - t),
            ),
            "detail",
        )
        return res

    def balance_tiers(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Soldes par compte client / fournisseur et par tiers."""
        return self._soldes_compte_tiers(debut, fin, etats, TYPES_TIERS)

    def soldes(
        self, depuis: date | None = None, jusqu_au: date | None = None
    ) -> list[Enregistrement]:
        """Soldes comptabilisés de tous les comptes, par (compte, tiers).

        Rôle : cumul des écritures validées hors période (soldes cumulés de
        l'analyse, ADR-0017).
        Paramètres : depuis, jusqu_au — bornes de date comprises (None :
        sans borne).
        Retour : un enregistrement par (compte, tiers) : compte, tiers_id,
        tiers_nom, tiers_ref, debit, credit (centimes), lignes.
        Erreurs : ErreurMontant ; erreurs psycopg2.
        Usages : passerelle.analyser_source.
        """
        return self._soldes_compte_tiers(depuis, jusqu_au, ("posted",), None)

    def _soldes_compte_tiers(
        self,
        debut: date | None,
        fin: date | None,
        etats: Sequence[str],
        types: Sequence[str] | None,
    ) -> list[Enregistrement]:
        """Totaux par (compte, tiers) de `_SQL_BALANCE_TIERS`.

        Paramètres : période ; états des écritures ; types de comptes
        retenus (None : tous).
        Usages : `balance_tiers`, `soldes`.
        """
        return [
            {
                "compte": rangee[0],
                "tiers_id": rangee[1],
                "tiers_nom": rangee[2] or "",
                "tiers_ref": rangee[3] or "",
                "debit": centimes(rangee[4]),
                "credit": centimes(rangee[5]),
                "lignes": rangee[6],
            }
            for rangee in self._requete(
                _SQL_BALANCE_TIERS,
                {
                    "societe": self.societe,
                    "etats": list(etats),
                    "debut": debut,
                    "fin": fin,
                    "types": list(types) if types is not None else None,
                },
            )
        ]

    def parametres_comptables(self) -> Enregistrement:
        """Paramètres comptables de la société utiles à l'analyse.

        Retour : fin_exercice_mois et fin_exercice_jour (int),
        ouverture_id (écriture d'ouverture déclarée, ou None),
        journal_caba (code du journal de TVA sur encaissements, ou '').
        Erreurs : erreurs psycopg2.
        Usages : passerelle.analyser_source.
        """
        rangee = self._requete(
            "SELECT c.fiscalyear_last_month, c.fiscalyear_last_day, "
            "c.account_opening_move_id, aj.code "
            "FROM res_company c "
            "LEFT JOIN account_journal aj "
            "ON aj.id = c.tax_cash_basis_journal_id "
            "WHERE c.id = %(s)s",
            {"s": self.societe},
        )[0]
        return {
            "fin_exercice_mois": int(rangee[0]),
            "fin_exercice_jour": int(rangee[1]),
            "ouverture_id": rangee[2],
            "journal_caba": rangee[3] or "",
        }

    def ecritures_ouverture(
        self, journaux: Sequence[str], fin: date | None = None
    ) -> list[Enregistrement]:
        """Écritures d'à-nouveaux datées au plus tard `fin`.

        Rôle : repérer l'ouverture pour ne jamais la compter deux fois.
        Paramètres : journaux — codes des journaux d'à-nouveaux ; fin.
        Retour : [{id, nom, date, etat, journal}] triés par date : écriture
        d'ouverture de la société et écritures de ces journaux, validées
        ou brouillons.
        Erreurs : erreurs psycopg2.
        Usages : passerelle.analyser_source.
        """
        return [
            {
                "id": rangee[0],
                "nom": rangee[1] or "",
                "date": rangee[2],
                "etat": rangee[3],
                "journal": rangee[4],
            }
            for rangee in self._requete(
                _SQL_OUVERTURE,
                {
                    "societe": self.societe,
                    "ouverture": self.parametres_comptables()["ouverture_id"],
                    "journaux": list(journaux),
                    "fin": fin,
                },
            )
        ]

    def nombre_lignes_avant(self, jour: date) -> int:
        """Nombre de lignes comptabilisées datées avant `jour`.

        Rôle : mesurer l'historique antérieur à une écriture d'à-nouveaux
        (constat OUVERTURE_DOUBLE_POSSIBLE).
        Erreurs : erreurs psycopg2.
        Usages : soldes_cumules.calculer_soldes.
        """
        nombre: int = self._requete(
            "SELECT COUNT(*) FROM account_move_line "
            "WHERE company_id = %(s)s AND parent_state = 'posted' "
            "AND date < %(jour)s",
            {"s": self.societe, "jour": jour},
        )[0][0]
        return nombre

    def ecriture(self, ident: int | str) -> list[Enregistrement]:
        """Une écriture et ses lignes (toutes états confondus)."""
        return list(self.lignes(etats=ETATS, ecriture=int(ident)))

    def verrous(self) -> dict[str, date | None]:
        """Dates de verrouillage : période, exercice, TVA."""
        r = self._requete(
            "SELECT period_lock_date, fiscalyear_lock_date, tax_lock_date "
            "FROM res_company WHERE id = %(s)s",
            {"s": self.societe},
        )[0]
        return {"periode": r[0], "exercice": r[1], "tva": r[2]}

    def instantane(self) -> "Instantane":
        """Photo légère de la base (état et date de modification de chaque
        écriture, codes de comptes, verrous), pour repérer les changements
        entre deux passages. Dict sérialisable en JSON."""
        ecritures = {
            str(r[0]): [r[1], str(r[2]), r[3] or ""]
            for r in self._requete(
                "SELECT am.id, am.state, am.write_date, am.name "
                "FROM account_move am WHERE am.company_id = %(s)s",
                {"s": self.societe},
            )
        }
        comptes = {
            str(r[0]): r[1]
            for r in self._requete(
                "SELECT id, code FROM account_account "
                "WHERE company_id = %(s)s",
                {"s": self.societe},
            )
        }
        return {
            "ecritures": ecritures,
            "comptes": comptes,
            "verrous": _verrous_texte(self.verrous()),
        }

    def comptes(self) -> list[Enregistrement]:
        """Plan comptable de la société, trié par code."""
        return [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "lettrable": bool(r[4]),
                "deprecie": bool(r[5]),
            }
            for r in self._requete(
                "SELECT id, code, COALESCE(name->>'fr_FR', name->>'en_US'), "
                "account_type, reconcile, deprecated FROM account_account "
                "WHERE company_id = %(s)s ORDER BY code",
                {"s": self.societe},
            )
        ]

    def journaux(self) -> list[Enregistrement]:
        """Journaux de la société, triés par code."""
        return [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "actif": bool(r[4]),
            }
            for r in self._requete(
                "SELECT id, code, COALESCE(name->>'fr_FR', name->>'en_US'), "
                "type, active FROM account_journal WHERE company_id = %(s)s "
                "ORDER BY code",
                {"s": self.societe},
            )
        ]

    def tiers(self) -> list[Enregistrement]:
        """Tiers partagés ou propres à la société, triés par id."""
        return [
            {
                "id": r[0],
                "nom": r[1] or "",
                "ref": r[2] or "",
                "tva": r[3] or "",
                "siren": r[4] or "",
                "email": r[5] or "",
                "telephone": r[6] or "",
                "rue": r[7] or "",
                "cp": r[8] or "",
                "ville": r[9] or "",
                "pays": r[10] or "",
                "societe": bool(r[11]),
                "actif": bool(r[12]),
                "client": (r[13] or 0) > 0,
                "fournisseur": (r[14] or 0) > 0,
                "parent_id": r[15],
            }
            for r in self._requete(
                "SELECT p.id, p.name, p.ref, p.vat, p.company_registry, "
                "p.email, p.phone, p.street, p.zip, p.city, c.code, "
                "p.is_company, p.active, p.customer_rank, p.supplier_rank, "
                "p.parent_id "
                "FROM res_partner p "
                "LEFT JOIN res_country c ON c.id = p.country_id "
                "WHERE p.company_id IS NULL OR p.company_id = %(s)s "
                "ORDER BY p.id",
                {"s": self.societe},
            )
        ]

    def factures(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ETATS,
    ) -> list[Enregistrement]:
        """Factures et avoirs de la période, triés par date et numéro."""
        res = []
        for r in self._requete(
            "SELECT am.id, am.name, am.move_type, am.state, "
            "am.payment_state, aj.code, rp.id, rp.name, am.date, "
            "am.invoice_date, am.invoice_date_due, "
            "am.ref, am.amount_untaxed_signed, am.amount_tax_signed, "
            "am.amount_total_signed, am.amount_residual_signed, cur.name "
            "FROM account_move am "
            "JOIN account_journal aj ON aj.id = am.journal_id "
            "LEFT JOIN res_partner rp ON rp.id = am.partner_id "
            "LEFT JOIN res_currency cur ON cur.id = am.currency_id "
            "WHERE am.company_id = %(s)s AND am.move_type = ANY(%(t)s) "
            "AND am.state = ANY(%(e)s) "
            "AND (%(d)s::date IS NULL OR am.date >= %(d)s::date) "
            "AND (%(f)s::date IS NULL OR am.date <= %(f)s::date) "
            "ORDER BY am.date, am.name",
            {
                "s": self.societe,
                "t": list(TYPES_FACTURE),
                "e": list(etats),
                "d": debut,
                "f": fin,
            },
        ):
            res.append(
                {
                    "id": r[0],
                    "numero": r[1] or "",
                    "type_piece": r[2],
                    "etat": r[3],
                    "etat_paiement": r[4] or "",
                    "journal_code": r[5],
                    "tiers_id": r[6],
                    "tiers_nom": r[7] or "",
                    "date": r[8],
                    "date_facture": r[9],
                    "echeance": r[10],
                    "reference": r[11] or "",
                    "ht": centimes(r[12]),
                    "tva": centimes(r[13]),
                    "ttc": centimes(r[14]),
                    "reste_du": centimes(r[15]),
                    "devise": r[16] or "",
                }
            )
        return res

    def fermer(self) -> None:
        """Ferme la connexion PostgreSQL."""
        self._cx.close()


# ---------------------------------------------------------------------------
# Source XML-RPC (API Odoo, lecture seule)
# ---------------------------------------------------------------------------


class SourceXmlRpcOdoo17:
    """Lecture par l'API XML-RPC d'Odoo 17, avec une clé API."""

    nature = "xmlrpc"
    METHODES_AUTORISEES = ("search_read", "read", "fields_get", "search_count")
    TAILLE_LOT = 2000

    def __init__(
        self,
        url: str,
        base: str,
        utilisateur: str,
        cle_api: str,
        societe: int | None = None,
        timeout: float = 120,
        proxy_commun: Any = None,
        proxy_objet: Any = None,
        journal: Journal | None = None,
    ) -> None:
        """Se connecte à l'API, vérifie la version et s'authentifie.

        `proxy_commun` / `proxy_objet` : proxys XML-RPC (objets dynamiques)
        fournis par les tests ; créés ici s'ils sont absents.
        Erreurs : ErreurSource (version autre que 17, authentification
        refusée, base multi-sociétés sans `societe`).
        """
        self.journal = ou_muet(journal)
        self._noms_an: dict[int, str] | None = None
        self.journal.dire(
            "Connexion à %s, base %s (API XML-RPC, lecture seule)"
            % (url, base)
        )

        self.url = url.rstrip("/")
        self.base = base
        self._cle = cle_api
        if proxy_objet is None:
            proxy_commun, proxy_objet = proxys_xmlrpc(self.url, timeout)
        self._objet = proxy_objet
        self.version_serveur = proxy_commun.version().get(
            "server_version", "?"
        )
        if not str(self.version_serveur).startswith("17."):
            raise ErreurSource(
                "Odoo %s : cette source ne lit que Odoo 17."
                % self.version_serveur
            )
        self.uid = proxy_commun.authenticate(base, utilisateur, cle_api, {})
        if not self.uid:
            raise ErreurSource(
                "Authentification refusée : vérifiez l'URL, la base, le "
                "login et la clé API (Préférences > Sécurité du compte > "
                "Clés API)."
            )
        self.societe = societe or self._societe_unique()
        self.journal.dire(
            "Connecté : Odoo %s, utilisateur n° %s"
            % (self.version_serveur, self.uid),
            "detail",
        )

    def _appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: Mapping[str, object] | None = None,
    ) -> Any:
        """Appelle `methode` sur `modele` par execute_kw (lecture seule).

        Rôle : unique point de passage vers l'API (garde lecture seule).
        Paramètres : modele, methode (une de METHODES_AUTORISEES), args,
        kwargs (contexte fr_FR, archivés compris, par défaut).
        Retour : la réponse XML-RPC brute (structure dynamique).
        Erreurs : PermissionError si la méthode n'est pas autorisée ;
        FauteXmlRpc / OSError venant du serveur.
        Usages : toutes les lectures de cette classe.
        """
        if methode not in self.METHODES_AUTORISEES:
            raise PermissionError(
                "Méthode %r interdite : source en lecture seule." % methode
            )
        kw = dict(kwargs or {})
        kw.setdefault("context", {"lang": "fr_FR", "active_test": False})
        return self._objet.execute_kw(
            self.base, self.uid, self._cle, modele, methode, args, kw
        )

    def _tout_lire(
        self, modele: str, domaine: Domaine, champs: list[str]
    ) -> list[dict[str, Any]]:
        """search_read paginé par id croissant (stable même si la base bouge).

        Retour : tous les enregistrements XML-RPC bruts du domaine.
        Usages : comptes, journaux, tiers, factures, lignes, instantane,
        noms_analytiques.
        """
        res: list[dict[str, Any]] = []
        dernier = 0
        while True:
            lot = self._appel(
                modele,
                "search_read",
                [domaine + [("id", ">", dernier)]],
                {"fields": champs, "order": "id", "limit": self.TAILLE_LOT},
            )
            res.extend(lot)
            if len(lot) < self.TAILLE_LOT:
                return res
            dernier = lot[-1]["id"]

    def _lire_par_lots(
        self, modele: str, ids: Sequence[int], champs: list[str]
    ) -> Iterator[dict[str, Any]]:
        """Lit les enregistrements `ids` de `modele` par lots (read).

        Rôle : lire de nombreux enregistrements sans dépasser TAILLE_LOT.
        Paramètres : modele ; ids — identifiants à lire ; champs à lire.
        Retour : les enregistrements XML-RPC bruts, lot après lot.
        Erreurs : celles de `_appel`.
        Usages : `lignes` (pièces, tiers, rapprochements).
        """
        for lot in _lots(ids, self.TAILLE_LOT):
            yield from self._appel(modele, "read", [lot], {"fields": champs})

    def _societe_unique(self) -> int:
        """Identifiant de l'unique société ; ErreurSource sinon."""
        ids: list[int] = [
            s["id"]
            for s in self._appel(
                "res.company", "search_read", [[]], {"fields": ["id"]}
            )
        ]
        if len(ids) != 1:
            raise ErreurSource(
                "Base multi-sociétés (%s) : précisez --societe <id>." % ids
            )
        return ids[0]

    def _lire_societe(self, champs: list[str]) -> dict[str, Any]:
        """Lit `champs` de la société (enregistrement XML-RPC brut).

        Usages : `societe_info`, `verrous`.
        """
        societe: dict[str, Any] = self._appel(
            "res.company", "read", [[self.societe]], {"fields": champs}
        )[0]
        return societe

    def societe_info(self) -> Enregistrement:
        """Identité de la société lue (nom, SIREN, TVA, devise)."""
        s = self._lire_societe(
            ["name", "company_registry", "vat", "currency_id"]
        )
        return {
            "id": self.societe,
            "nom": s["name"],
            "siren": _texte(s["company_registry"]),
            "tva": _texte(s["vat"]),
            "devise": _m2o(s["currency_id"])[1],
        }

    def lignes(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
        comptes: Iterable[str] | None = None,
        ecriture: int | None = None,
        reference_prefixe: str | None = None,
    ) -> list[Enregistrement]:
        """Lignes d'écritures, triées comme cle_tri (liste complète).

        comptes : liste de codes (grand livre) ; ecriture : id d'une écriture ;
        reference_prefixe : seulement les écritures dont la référence
        commence par « <reference_prefixe>/ » (relecture d'un transfert).
        """
        dom: Domaine = [
            ("company_id", "=", self.societe),
            ("parent_state", "in", list(etats)),
            ("display_type", "not in", list(TYPES_AFFICHAGE)),
        ]
        if comptes:
            dom.append(("account_id.code", "in", list(comptes)))
        if ecriture:
            dom.append(("move_id", "=", int(ecriture)))
        if reference_prefixe:
            dom.append(("move_id.ref", "=like", reference_prefixe + "/%"))
        bavard = comptes is None and ecriture is None
        debut_t = time.monotonic()
        if bavard:
            self.journal.dire(
                "Lecture des lignes d'écritures par l'API (%s) — "
                "plus lent qu'en SQL" % _periode_texte(debut, fin).lstrip(", ")
                or "tout"
            )
        if debut:
            dom.append(("date", ">=", str(debut)))
        if fin:
            dom.append(("date", "<=", str(fin)))
        brutes = self._tout_lire(
            "account.move.line",
            dom,
            [
                "move_id",
                "account_id",
                "partner_id",
                "name",
                "debit",
                "credit",
                "matching_number",
                "full_reconcile_id",
                "amount_currency",
                "currency_id",
                "company_currency_id",
                "date_maturity",
                "write_date",
                "analytic_distribution",
            ],
        )
        plan = {c["id"]: c for c in self.comptes()}
        journaux = {j["id"]: j for j in self.journaux()}
        pieces = {
            m["id"]: m
            for m in self._lire_par_lots(
                "account.move",
                sorted({_m2o(b["move_id"])[0] for b in brutes}),
                [
                    "name",
                    "move_type",
                    "state",
                    "journal_id",
                    "date",
                    "invoice_date",
                    "ref",
                    "write_date",
                    "auto_post",
                    "tax_cash_basis_rec_id",
                    "reversed_entry_id",
                ],
            )
        }
        ids_tiers = sorted({_m2o(b["partner_id"])[0] for b in brutes} - {None})
        tiers = {
            p["id"]: p
            for p in self._lire_par_lots(
                "res.partner", ids_tiers, ["name", "ref"]
            )
        }
        ids_rec = sorted(
            {_m2o(b["full_reconcile_id"])[0] for b in brutes} - {None}
        )
        rapprochements = {
            r["id"]: _date(r["create_date"])
            for r in self._lire_par_lots(
                "account.full.reconcile", ids_rec, ["create_date"]
            )
        }
        res = []
        for b in brutes:
            m = pieces[_m2o(b["move_id"])[0]]
            j = journaux.get(_m2o(m["journal_id"])[0], {})
            c = plan.get(_m2o(b["account_id"])[0], {})
            tid = _m2o(b["partner_id"])[0]
            t = tiers.get(tid, {})
            rec_id = _m2o(b["full_reconcile_id"])[0]
            devise_etr = (
                _m2o(b["currency_id"])[0] != _m2o(b["company_currency_id"])[0]
            )
            res.append(
                {
                    "ligne_id": b["id"],
                    "ecriture_id": m["id"],
                    "ecriture": _texte(m["name"]),
                    "type_piece": m["move_type"],
                    "etat": m["state"],
                    "journal_code": j.get("code", ""),
                    "journal_lib": j.get("libelle", ""),
                    "date": _date(m["date"]),
                    "piece_date": _date(m["invoice_date"]),
                    "reference": _texte(m["ref"]),
                    "compte": c.get("code", ""),
                    "compte_lib": c.get("libelle", ""),
                    "compte_type": c.get("type", ""),
                    "tiers_id": tid,
                    "tiers_ref": _texte(t.get("ref")),
                    "tiers_nom": _texte(t.get("name")),
                    "libelle": _texte(b["name"]),
                    "debit": centimes(b["debit"]),
                    "credit": centimes(b["credit"]),
                    "lettrage": _texte(b["matching_number"]) if rec_id else "",
                    "date_lettrage": (
                        rapprochements.get(rec_id) if rec_id else None
                    ),
                    "montant_devise": (
                        centimes(b["amount_currency"]) if devise_etr else None
                    ),
                    "devise": _m2o(b["currency_id"])[1] if devise_etr else "",
                    "echeance": _date(b["date_maturity"]),
                    "modifie_le": max(
                        str(m["write_date"]), str(b["write_date"])
                    ),
                    "auto_post": _texte(m.get("auto_post")),
                    "analytique": analytique_texte(
                        b.get("analytic_distribution"), self.noms_analytiques()
                    ),
                    "analytique_comptes": analytique_comptes(
                        b.get("analytic_distribution"), self.noms_analytiques()
                    ),
                    "caba_rapprochement_id": _m2o(m["tax_cash_basis_rec_id"])[
                        0
                    ],
                    "extourne_de_id": _m2o(m["reversed_entry_id"])[0],
                }
            )
        # Filtre redondant côté CONCORDE : on ne fait pas aveuglément
        # confiance au domaine.
        if comptes:
            res = [ligne for ligne in res if ligne["compte"] in set(comptes)]
        if ecriture:
            res = [
                ligne for ligne in res if ligne["ecriture_id"] == int(ecriture)
            ]
        if reference_prefixe:
            res = [
                ligne
                for ligne in res
                if ligne["reference"].startswith(reference_prefixe + "/")
            ]
        res.sort(key=cle_tri)
        if bavard:
            self.journal.dire(
                "%s lignes lues en %s"
                % (
                    nombre_texte(len(res)),
                    duree_texte(time.monotonic() - debut_t),
                ),
                "ok",
            )
        return res

    def noms_analytiques(self) -> dict[int, str]:
        """{id: code ou nom} des comptes analytiques (mis en cache).

        Si le module analytique est absent ou illisible (droits), rend {}
        et le signale au journal : les comptes s'affichent par numéro.
        """
        if self._noms_an is None:
            try:
                self._noms_an = {
                    a["id"]: _texte(a.get("code")) or _texte(a.get("name"))
                    for a in self._tout_lire(
                        "account.analytic.account", [], ["code", "name"]
                    )
                }
            except Exception as exc:  # module absent ou droits insuffisants
                self._noms_an = {}
                self.journal.dire(
                    "Comptes analytiques illisibles (%s) : affichés par numéro"
                    % str(exc).splitlines()[-1][:120],
                    "alerte",
                )
        return self._noms_an

    def balance(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Balance générale calculée à partir des lignes lues par l'API."""
        return balance_depuis_lignes(
            self.comptes(), self.lignes(debut, fin, etats)
        )

    def balance_tiers(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ("posted",),
    ) -> list[Enregistrement]:
        """Soldes par compte client / fournisseur et par tiers."""
        return balance_tiers_depuis_lignes(self.lignes(debut, fin, etats))

    def soldes(
        self, depuis: date | None = None, jusqu_au: date | None = None
    ) -> list[Enregistrement]:
        """Soldes comptabilisés de tous les comptes, par (compte, tiers).

        Rôle : cumul des écritures validées hors période (ADR-0017), en ne
        lisant que compte, tiers, date et montants de chaque ligne.
        Paramètres : depuis, jusqu_au — bornes de date comprises (None :
        sans borne).
        Retour : comme `SourceSqlOdoo17.soldes`.
        Erreurs : ErreurMontant ; erreurs de `_appel`.
        Usages : passerelle.analyser_source.
        """
        dom: Domaine = [
            ("company_id", "=", self.societe),
            ("parent_state", "=", "posted"),
            ("display_type", "not in", list(TYPES_AFFICHAGE)),
        ]
        if depuis:
            dom.append(("date", ">=", str(depuis)))
        if jusqu_au:
            dom.append(("date", "<=", str(jusqu_au)))
        brutes = self._tout_lire(
            "account.move.line",
            dom,
            [
                "account_id",
                "partner_id",
                "debit",
                "credit",
                "date",
                "parent_state",
            ],
        )
        codes = {c["id"]: c["code"] for c in self.comptes()}
        ids_tiers = sorted(
            {_m2o(brute["partner_id"])[0] for brute in brutes} - {None}
        )
        tiers = {
            partenaire["id"]: partenaire
            for partenaire in self._lire_par_lots(
                "res.partner", ids_tiers, ["name", "ref"]
            )
        }
        lignes = []
        for brute in brutes:
            jour = _date(brute["date"])
            # Filtre redondant : on ne fait pas aveuglément confiance au
            # domaine.
            if (
                brute["parent_state"] != "posted"
                or (depuis and jour and jour < depuis)
                or (jusqu_au and jour and jour > jusqu_au)
            ):
                continue
            id_tiers = _m2o(brute["partner_id"])[0]
            lignes.append(
                {
                    "compte": codes.get(_m2o(brute["account_id"])[0], ""),
                    "tiers_id": id_tiers,
                    "tiers_nom": _texte(tiers.get(id_tiers, {}).get("name")),
                    "tiers_ref": _texte(tiers.get(id_tiers, {}).get("ref")),
                    "debit": centimes(brute["debit"]),
                    "credit": centimes(brute["credit"]),
                }
            )
        return balance_tiers_depuis_lignes(lignes, None)

    def parametres_comptables(self) -> Enregistrement:
        """Paramètres comptables de la société utiles à l'analyse.

        Retour : comme `SourceSqlOdoo17.parametres_comptables`.
        Erreurs : erreurs de `_appel`.
        Usages : passerelle.analyser_source, `ecritures_ouverture`.
        """
        societe_odoo = self._lire_societe(
            [
                "fiscalyear_last_month",
                "fiscalyear_last_day",
                "account_opening_move_id",
                "tax_cash_basis_journal_id",
            ]
        )
        id_caba = _m2o(societe_odoo["tax_cash_basis_journal_id"])[0]
        codes = {j["id"]: j["code"] for j in self.journaux()}
        return {
            "fin_exercice_mois": int(societe_odoo["fiscalyear_last_month"]),
            "fin_exercice_jour": int(societe_odoo["fiscalyear_last_day"]),
            "ouverture_id": _m2o(societe_odoo["account_opening_move_id"])[0],
            "journal_caba": codes.get(id_caba, "") if id_caba else "",
        }

    def ecritures_ouverture(
        self, journaux: Sequence[str], fin: date | None = None
    ) -> list[Enregistrement]:
        """Écritures d'à-nouveaux datées au plus tard `fin`.

        Retour et usages : comme `SourceSqlOdoo17.ecritures_ouverture`.
        Erreurs : erreurs de `_appel`.
        """
        ouverture = self.parametres_comptables()["ouverture_id"]
        dom: Domaine = [
            ("company_id", "=", self.societe),
            ("state", "in", ["posted", "draft"]),
            "|",
            ("id", "=", ouverture or 0),
            ("journal_id.code", "in", list(journaux)),
        ]
        if fin:
            dom.append(("date", "<=", str(fin)))
        codes = {j["id"]: j["code"] for j in self.journaux()}
        res = []
        for piece in self._tout_lire(
            "account.move", dom, ["name", "date", "state", "journal_id"]
        ):
            jour = _date(piece["date"])
            code = codes.get(_m2o(piece["journal_id"])[0], "")
            # Filtre redondant, comme pour les lignes.
            if (
                piece["state"] not in ("posted", "draft")
                or (piece["id"] != ouverture and code not in journaux)
                or (fin and jour and jour > fin)
            ):
                continue
            res.append(
                {
                    "id": piece["id"],
                    "nom": _texte(piece["name"]),
                    "date": jour,
                    "etat": piece["state"],
                    "journal": code,
                }
            )
        return sorted(res, key=lambda e: (e["date"] or date.min, e["id"]))

    def nombre_lignes_avant(self, jour: date) -> int:
        """Nombre de lignes comptabilisées datées avant `jour`.

        Rôle et usages : comme `SourceSqlOdoo17.nombre_lignes_avant`
        (search_count, en lecture seule).
        Erreurs : erreurs de `_appel`.
        """
        nombre: int = self._appel(
            "account.move.line",
            "search_count",
            [
                [
                    ("company_id", "=", self.societe),
                    ("parent_state", "=", "posted"),
                    ("date", "<", str(jour)),
                ]
            ],
        )
        return nombre

    def ecriture(self, ident: int | str) -> list[Enregistrement]:
        """Une écriture et ses lignes (toutes états confondus)."""
        return self.lignes(etats=ETATS, ecriture=int(ident))

    def verrous(self) -> dict[str, date | None]:
        """Dates de verrouillage : période, exercice, TVA."""
        s = self._lire_societe(
            ["period_lock_date", "fiscalyear_lock_date", "tax_lock_date"]
        )
        return {
            "periode": _date(s["period_lock_date"]),
            "exercice": _date(s["fiscalyear_lock_date"]),
            "tva": _date(s["tax_lock_date"]),
        }

    def instantane(self) -> "Instantane":
        """Photo légère de la base (voir `SourceSqlOdoo17.instantane`)."""
        ecritures = {
            str(m["id"]): [m["state"], str(m["write_date"]), _texte(m["name"])]
            for m in self._tout_lire(
                "account.move",
                [("company_id", "=", self.societe)],
                ["state", "write_date", "name"],
            )
        }
        comptes = {str(c["id"]): c["code"] for c in self.comptes()}
        return {
            "ecritures": ecritures,
            "comptes": comptes,
            "verrous": _verrous_texte(self.verrous()),
        }

    def comptes(self) -> list[Enregistrement]:
        """Plan comptable de la société (ordre des id)."""
        return [
            {
                "id": c["id"],
                "code": c["code"],
                "libelle": _texte(c["name"]),
                "type": c["account_type"],
                "lettrable": bool(c["reconcile"]),
                "deprecie": bool(c["deprecated"]),
            }
            for c in self._tout_lire(
                "account.account",
                [("company_id", "=", self.societe)],
                ["code", "name", "account_type", "reconcile", "deprecated"],
            )
        ]

    def journaux(self) -> list[Enregistrement]:
        """Journaux de la société (ordre des id)."""
        return [
            {
                "id": j["id"],
                "code": j["code"],
                "libelle": _texte(j["name"]),
                "type": j["type"],
                "actif": bool(j["active"]),
            }
            for j in self._tout_lire(
                "account.journal",
                [("company_id", "=", self.societe)],
                ["code", "name", "type", "active"],
            )
        ]

    def tiers(self) -> list[Enregistrement]:
        """Tiers partagés ou propres à la société (ordre des id)."""
        res = []
        for p in self._tout_lire(
            "res.partner",
            [
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.societe),
            ],
            [
                "name",
                "ref",
                "vat",
                "company_registry",
                "email",
                "phone",
                "street",
                "zip",
                "city",
                "country_code",
                "is_company",
                "active",
                "customer_rank",
                "supplier_rank",
                "parent_id",
            ],
        ):
            res.append(
                {
                    "id": p["id"],
                    "nom": _texte(p["name"]),
                    "ref": _texte(p["ref"]),
                    "tva": _texte(p["vat"]),
                    "siren": _texte(p["company_registry"]),
                    "email": _texte(p["email"]),
                    "telephone": _texte(p["phone"]),
                    "rue": _texte(p["street"]),
                    "cp": _texte(p["zip"]),
                    "ville": _texte(p["city"]),
                    "pays": _texte(p["country_code"]),
                    "societe": bool(p["is_company"]),
                    "actif": bool(p["active"]),
                    "client": (p["customer_rank"] or 0) > 0,
                    "fournisseur": (p["supplier_rank"] or 0) > 0,
                    "parent_id": _m2o(p["parent_id"])[0],
                }
            )
        return res

    def factures(
        self,
        debut: date | None = None,
        fin: date | None = None,
        etats: Sequence[str] = ETATS,
    ) -> list[Enregistrement]:
        """Factures et avoirs de la période, triés par date et numéro."""
        dom: Domaine = [
            ("company_id", "=", self.societe),
            ("move_type", "in", list(TYPES_FACTURE)),
            ("state", "in", list(etats)),
        ]
        if debut:
            dom.append(("date", ">=", str(debut)))
        if fin:
            dom.append(("date", "<=", str(fin)))
        journaux = {j["id"]: j["code"] for j in self.journaux()}
        res = []
        for f in self._tout_lire(
            "account.move",
            dom,
            [
                "name",
                "move_type",
                "state",
                "payment_state",
                "journal_id",
                "partner_id",
                "date",
                "invoice_date",
                "invoice_date_due",
                "ref",
                "amount_untaxed_signed",
                "amount_tax_signed",
                "amount_total_signed",
                "amount_residual_signed",
                "currency_id",
            ],
        ):
            tid, tnom = _m2o(f["partner_id"])
            res.append(
                {
                    "id": f["id"],
                    "numero": _texte(f["name"]),
                    "type_piece": f["move_type"],
                    "etat": f["state"],
                    "etat_paiement": _texte(f["payment_state"]),
                    "journal_code": journaux.get(_m2o(f["journal_id"])[0], ""),
                    "tiers_id": tid,
                    "tiers_nom": tnom,
                    "date": _date(f["date"]),
                    "date_facture": _date(f["invoice_date"]),
                    "echeance": _date(f["invoice_date_due"]),
                    "reference": _texte(f["ref"]),
                    "ht": centimes(f["amount_untaxed_signed"]),
                    "tva": centimes(f["amount_tax_signed"]),
                    "ttc": centimes(f["amount_total_signed"]),
                    "reste_du": centimes(f["amount_residual_signed"]),
                    "devise": _m2o(f["currency_id"])[1],
                }
            )
        res.sort(key=lambda f: (f["date"] or date.min, f["numero"]))
        return res

    def fermer(self) -> None:
        """Rien à fermer : l'API XML-RPC est sans connexion persistante."""
