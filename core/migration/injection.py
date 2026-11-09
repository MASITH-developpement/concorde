# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 6 — envoi du lot dans la BASE DE TEST du serveur, puis relecture.

ADR-0004. Cible verrouillée : uniquement la base de test configurée
(CONCORDE_TEST_URL / _BASE / _USER / _MDP, adresse locale). Les portes 7 et
8 (base client) viendront ensuite.

Déroulé :
  1. connexion à la base de test (API XML-RPC d'Odoo — jamais de SQL pour
     écrire) ;
  2. préparation : comptes, journaux et tiers manquants créés (codes et
     libellés LUS dans le FEC ; type de compte par les règles du PCG
     ci-dessous, jamais deviné) ;
  3. écritures créées EN BROUILLON par paquets, référence unique
     « CONCORDE/<lot>/<journal>/<n°> » : une écriture déjà présente n'est
     jamais renvoyée ;
  4. validation (action_post) ;
  5. lettrage refait par l'API (reconcile), lettre par lettre ;
  6. relecture SQL de la base de test et comparaison au lot, au centime :
     lignes, écritures, totaux, solde par compte, lignes par tiers, lettres.
     0 écart exigé.

Toute erreur d'Odoo est gardée avec l'écriture en cause (jamais muet).
"""

import os
import threading
import time
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import TracebackType
from typing import Any, Protocol, TypedDict, TypeVar

from ..analyser import Rapport
from ..journal import Journal, nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from ..xml_sur import FauteXmlRpc as FauteXmlRpc
from ..xml_sur import ProxyXmlRpc
from .lot import (
    CleEcriture,
    CleTotaux,
    LigneLot,
    Lot,
    TotauxLot,
    annoncer_constats,
    cle_ecriture,
    cle_texte,
    lignes_par_tiers,
)

# Erreur renvoyée par Odoo via XML-RPC ; nom public pour les doublures des
# tests.

TAILLE_PAQUET = 100

# Vitesse (mesurée le 06/11/2026) : comme l'import natif d'Odoo, on coupe le
# suivi « chatter » pendant l'envoi (pas de message « écriture créée /
# validée » par écriture) : -15 %.
# Parallélisme : DÉSACTIVÉ par défaut. Mesuré : plus lent et source
# d'erreurs de validation (Odoo sérialise la numérotation et le recalcul des
# soldes). Réglable pour essai : CONCORDE_INJECTION_PARALLELES.
CONTEXTE_IMPORT = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_create_nosubscribe": True,
    "mail_notrack": True,
}

ElementTraite = TypeVar("ElementTraite")
ResultatTraitement = TypeVar("ResultatTraitement")


def _paralleles() -> int:
    """Requêtes simultanées (CONCORDE_INJECTION_PARALLELES, 1 par défaut)."""
    try:
        return max(
            1, int(os.environ.get("CONCORDE_INJECTION_PARALLELES", "1"))
        )
    except ValueError:
        return 1


METHODES_AUTORISEES = (
    "search_read",
    "read",
    "search_count",
    "fields_get",
    "create",
    "action_post",
    "reconcile",
)


class ErreurInjection(RuntimeError):
    """Envoi impossible ou interdit vers la base de test."""


class ErreurOdoo(TypedDict):
    """Erreur d'Odoo gardée avec l'écriture (ou la lettre) en cause."""

    ecriture: str
    etape: str
    erreur: str


class Preparation(TypedDict):
    """Comptes, journaux et tiers créés par la préparation."""

    comptes_crees: list[str | None]
    journaux_crees: list[str]
    tiers_crees: int


class ResultatLettrageCommun(TypedDict):
    """Partie toujours présente du bilan du lettrage."""

    lettres: int
    faites: int
    ignorees: int | dict[str, int]


class ResultatLettrage(ResultatLettrageCommun, total=False):
    """Bilan du lettrage : lettres demandées, faites, écartées (détail)."""

    ignorees_detail: dict[str, list[str]]


class ResultatEnvoi(TypedDict):
    """Résultat de la porte 6 : lot, base, préparation, erreurs, durée."""

    lot: str
    base: str
    preparation: Preparation
    deja_presentes: int
    creees: int
    erreurs: list[ErreurOdoo]
    lettrage: ResultatLettrage
    duree_s: float


class ValeursLigneOdoo(TypedDict):
    """Valeurs d'une ligne account.move.line à créer."""

    account_id: int
    partner_id: int | bool
    name: str
    debit: float
    credit: float


class ValeursEcritureOdoo(TypedDict):
    """Valeurs d'une écriture account.move à créer (lignes comprises)."""

    move_type: str
    journal_id: int
    date: str
    ref: str
    line_ids: list[tuple[int, int, ValeursLigneOdoo]]


class ProxyCommun(Protocol):
    """Service XML-RPC « common » d'Odoo (version, authentification)."""

    def version(self) -> Any:
        """Version du serveur (réponse XML-RPC : dict)."""

    def authenticate(
        self,
        base: str,
        utilisateur: str,
        mot_de_passe: str,
        options: dict[str, Any],
    ) -> Any:
        """Identifiant de l'utilisateur, ou False (réponse XML-RPC)."""


class ProxyObjet(Protocol):
    """Service XML-RPC « object » d'Odoo (appel des modèles)."""

    def execute_kw(
        self,
        base: str,
        uid: int,
        mot_de_passe: str,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        """Appelle `methode` du modèle (réponse XML-RPC dynamique)."""


class CurseurLecture(Protocol):
    """Curseur SQL en lecture seule, utilisable avec `with`."""

    def __enter__(self) -> object:
        """Ouvre le bloc `with`."""

    def __exit__(
        self,
        type_exception: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> bool | None:
        """Ferme le bloc `with`."""

    def execute(self, requete: str, parametres: tuple[str, ...]) -> object:
        """Exécute la requête paramétrée."""

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Rangs lus (valeurs SQL de types variés)."""


class ConnexionLecture(Protocol):
    """Connexion SQL à la base de test (ouvre des curseurs)."""

    def cursor(self) -> CurseurLecture:
        """Ouvre un curseur."""


# ---------------------------------------------------------------------------
# Type Odoo 17 d'un compte, par les règles du plan comptable général
# ---------------------------------------------------------------------------


def type_compte_pcg(code: str | None) -> str:
    """Type account.account Odoo 17 d'après le PCG (règles documentées).

    Jamais « equity_unaffected » : Odoo n'en admet qu'un (résultat de
    l'exercice).
    """
    c = (code or "").strip()
    regles = (
        (("16", "17"), "liability_non_current"),
        (("1",), "equity"),
        (("28", "29"), "asset_non_current"),
        (("2",), "asset_non_current"),
        (("3",), "asset_current"),
        (("409",), "asset_current"),  # fournisseurs débiteurs (avant « 40 »)
        (("40",), "liability_payable"),
        (("41",), "asset_receivable"),
        (("486",), "asset_prepayments"),
        (("4456", "4458", "46", "47", "48"), "asset_current"),
        (("4",), "liability_current"),
        (("51", "53"), "asset_cash"),
        (("5",), "asset_current"),
        (("68",), "expense_depreciation"),
        (("6",), "expense"),
        (("7",), "income"),
        (("8", "9"), "off_balance"),
    )
    for prefixes, t in regles:
        if c.startswith(prefixes):
            return t
    return "asset_current"


def euros(centimes: int) -> float:
    """Centimes -> euros (float exact à 2 décimales) pour l'API Odoo."""
    return float(Decimal(int(centimes)) / 100)


def _centimes_base(montant: object) -> int:
    """Montant SQL en euros (numeric) -> centimes, sans arrondi flottant."""
    return int((Decimal(str(montant)) * 100).to_integral_value())


def decouper(
    elements: list[ElementTraite], taille: int
) -> list[list[ElementTraite]]:
    """Découpe une liste en paquets.

    Rôle : envoyer ou lire par paquets (limite des requêtes XML-RPC).
    Paramètres : elements — liste à découper ; taille — taille maximale
    d'un paquet.
    Retour : paquets successifs, dans l'ordre (dernier paquet plus court).
    Erreurs : ValueError si `taille` vaut 0.
    Usages : preparer, envoyer, lettrer, connecteurs.pennylane.
    """
    paquets: list[list[ElementTraite]] = []
    for debut in range(0, len(elements), taille):
        fin = debut + taille
        paquets.append(elements[debut:fin])
    return paquets


# ---------------------------------------------------------------------------
# Client d'écriture, limité à la base de test
# ---------------------------------------------------------------------------


def _serveur_xmlrpc(adresse: str) -> ProxyXmlRpc:
    """Client XML-RPC vers `adresse` (None autorisé dans les échanges)."""
    return ProxyXmlRpc(adresse, allow_none=True)


class CibleOdoo:
    """Client XML-RPC vers une base Odoo 17 (méthodes limitées).

    Destination d'un transfert (ADR-0008) : le transfert garantit la
    simulation, le test et le feu vert avant toute écriture réelle.
    `methodes_autorisees` : seules méthodes que `appel` accepte (une
    sous-classe peut en autoriser d'autres, pour un usage précis).
    """

    methodes_autorisees: tuple[str, ...] = METHODES_AUTORISEES

    def __init__(
        self,
        url: str,
        base: str,
        utilisateur: str,
        mot_de_passe: str,
        proxy_commun: ProxyCommun | None = None,
        proxy_objet: ProxyObjet | None = None,
    ) -> None:
        """S'identifie sur la base.

        Lève ErreurInjection si l'adresse ferait circuler le mot de passe
        en clair (http hors de ce serveur) ou si l'identification est
        refusée.
        """
        if proxy_objet is None and not url.startswith(
            ("https://", "http://127.0.0.1", "http://localhost")
        ):
            raise ErreurInjection(
                "Adresse Odoo non chiffrée (%s) : https:// exigé hors de ce "
                "serveur." % url
            )
        self.base, self._mdp, self._url = base, mot_de_passe, url
        self._objet_fixe = proxy_objet  # tests : un faux Odoo partagé
        # Un client XML-RPC par fil (non partageable).
        self._local = threading.local()
        commun: ProxyCommun = proxy_commun or _serveur_xmlrpc(
            url + "/xmlrpc/2/common"
        )
        self.version: str = commun.version().get("server_version", "?")
        self.uid: int = commun.authenticate(
            base, utilisateur, mot_de_passe, {}
        )
        if not self.uid:
            raise ErreurInjection(
                "Authentification refusée sur la base %s." % base
            )

    def _objet(self) -> ProxyObjet:
        """Service « object » : le faux Odoo des tests, ou celui du fil."""
        if self._objet_fixe is not None:
            return self._objet_fixe
        objet_fil: ProxyObjet | None = getattr(self._local, "objet", None)
        if objet_fil is None:
            objet_fil = _serveur_xmlrpc(self._url + "/xmlrpc/2/object")
            self._local.objet = objet_fil
        return objet_fil

    def appel(
        self,
        modele: str,
        methode: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Appelle une méthode autorisée d'un modèle Odoo.

        Retourne la réponse XML-RPC (type dynamique). Lève PermissionError
        si la méthode n'est pas dans `methodes_autorisees`.
        """
        if methode not in self.methodes_autorisees:
            raise PermissionError(
                "Méthode %r interdite à l'envoi vers Odoo." % methode
            )
        kw = dict(kwargs or {})
        kw["context"] = dict(CONTEXTE_IMPORT, **kw.get("context", {}))
        return self._objet().execute_kw(
            self.base, self.uid, self._mdp, modele, methode, args, kw
        )


class CibleTest(CibleOdoo):
    """Base de test locale du serveur (porte 6 de l'ADR-0004)."""

    def __init__(
        self,
        url: str,
        base: str,
        utilisateur: str,
        mot_de_passe: str,
        proxy_commun: ProxyCommun | None = None,
        proxy_objet: ProxyObjet | None = None,
    ) -> None:
        """Vérifie la cible (base de test, adresse locale) et s'identifie.

        Lève ErreurInjection si la base ou l'adresse ne sont pas autorisées
        ou si l'identification est refusée.
        """
        attendu = os.environ.get("CONCORDE_TEST_BASE")
        if not attendu or base != attendu:
            raise ErreurInjection(
                "Porte 6 : seule la base de test configurée (%r) est "
                "autorisée, pas %r." % (attendu, base)
            )
        if proxy_objet is None and not url.startswith(
            ("http://127.0.0.1", "http://localhost")
        ):
            raise ErreurInjection(
                "Porte 6 : la base de test doit être sur ce serveur (%s)."
                % url
            )
        super().__init__(
            url, base, utilisateur, mot_de_passe, proxy_commun, proxy_objet
        )


def en_parallele(
    fonction: Callable[[ElementTraite], ResultatTraitement],
    elements: list[ElementTraite],
    paralleles: int | None = None,
) -> list[ResultatTraitement]:
    """Applique `fonction` à chaque élément, `paralleles` à la fois.

    Rôle : répartir des appels Odoo sur plusieurs fils, ordre conservé.
    Paramètres : fonction — appliquée à chaque élément ; elements — liste ;
    paralleles — requêtes simultanées (défaut : CONCORDE_INJECTION_
    PARALLELES).
    Retour : résultats, dans l'ordre des éléments.
    Erreurs : celles de `fonction`, propagées.
    Usages : envoyer (création, validation), lettrer.
    """
    n = paralleles or _paralleles()
    if n <= 1 or len(elements) <= 1:
        return [fonction(e) for e in elements]
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fonction, elements))


def cible_depuis_env() -> CibleTest:
    """Cible de test décrite par les variables CONCORDE_TEST_*."""
    return CibleTest(
        os.environ.get("CONCORDE_TEST_URL", "http://127.0.0.1:8017"),
        os.environ.get("CONCORDE_TEST_BASE", ""),
        os.environ.get("CONCORDE_TEST_USER", "admin"),
        os.environ.get("CONCORDE_TEST_MDP", ""),
    )


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------


def lot_id(lot: Lot) -> str:
    """Identifiant court du lot : début de l'empreinte de la source."""
    return lot.source["empreinte"][:10]


def ref_ecriture(debut: str, cle: CleEcriture) -> str:
    """Référence Odoo unique d'une écriture.

    Rôle : un seul format de référence (idempotence : une écriture déjà
    présente sous sa référence n'est jamais renvoyée).
    Paramètres : debut — « CONCORDE/<lot> » ou référence de transfert ;
    cle — (journal, numéro).
    Retour : « <debut>/<journal>/<n°> ».
    Erreurs : aucune.
    Usages : envoyer, connecteurs.odoo, connecteurs.pennylane.
    """
    return "%s/%s/%s" % (debut, cle[0], cle[1])


def references_presentes(cible: CibleOdoo, refs: list[str]) -> set[str]:
    """Références d'écritures déjà présentes dans Odoo.

    Rôle : savoir ce qui a déjà été envoyé (reprise sans doublon).
    Paramètres : cible ; refs — références cherchées.
    Retour : sous-ensemble des références trouvées.
    Erreurs : celles d'Odoo (XML-RPC).
    Usages : envoyer, connecteurs.odoo.ConnecteurOdoo.ecrire (essai).
    """
    deja: set[str] = set()
    for paquet_refs in decouper(refs, 1000):
        deja |= {
            m["ref"]
            for m in cible.appel(
                "account.move",
                "search_read",
                [[["ref", "in", paquet_refs]]],
                {"fields": ["ref"]},
            )
        }
    return deja


def _erreur_odoo(exc: Exception) -> str:
    """Dernière ligne utile du message d'erreur d'Odoo (300 caractères)."""
    texte = getattr(exc, "faultString", None) or str(exc)
    lignes = [ligne for ligne in texte.strip().splitlines() if ligne.strip()]
    return lignes[-1][:300] if lignes else type(exc).__name__


class Existants(TypedDict):
    """Ce que le lot demande et ce que la base Odoo contient déjà.

    `*_lot` : codes (ou références) demandés par le lot, avec le libellé
    lu dans la source ; les autres : ce qui existe déjà dans Odoo.
    """

    comptes_lot: dict[str | None, str]
    comptes: dict[str | None, tuple[int, bool]]
    journaux_lot: dict[str, str]
    journaux: dict[str, int]
    tiers_lot: dict[str, str]
    tiers: dict[str, int]


def rechercher_existants(cible: CibleOdoo, lot: Lot) -> Existants:
    """Comptes, journaux et tiers du lot déjà présents dans Odoo.

    Rôle : un seul endroit qui cherche, pour la simulation comme pour
    l'envoi.
    Paramètres : cible — base Odoo ; lot — comptes cibles renseignés.
    Retour : Existants (demandés et trouvés).
    Erreurs : celles d'Odoo (XML-RPC).
    Usages : manquants, preparer.
    """
    comptes_lot: OrderedDict[str | None, str] = OrderedDict()
    journaux_lot: OrderedDict[str, str] = OrderedDict()
    tiers_lot: OrderedDict[str, str] = OrderedDict()
    for ligne in lot.lignes:
        comptes_lot.setdefault(ligne["compte_cible"], ligne["compte_lib"])
        journaux_lot.setdefault(ligne["journal_code"], ligne["journal_lib"])
        if ligne["tiers_ref"]:
            tiers_lot.setdefault(ligne["tiers_ref"], ligne["tiers_nom"])
    comptes: dict[str | None, tuple[int, bool]] = {
        c["code"]: (c["id"], c["reconcile"])
        for c in cible.appel(
            "account.account",
            "search_read",
            [[["code", "in", list(comptes_lot)]]],
            {
                "fields": ["code", "reconcile"],
                "context": {"active_test": False},
            },
        )
    }
    journaux: dict[str, int] = {
        jr["code"]: jr["id"]
        for jr in cible.appel(
            "account.journal",
            "search_read",
            [[["code", "in", list(journaux_lot)]]],
            {"fields": ["code"], "context": {"active_test": False}},
        )
    }
    tiers: dict[str, int] = {}
    for paquet_refs in decouper(list(tiers_lot), 500):
        for partenaire in cible.appel(
            "res.partner",
            "search_read",
            [[["ref", "in", paquet_refs]]],
            {"fields": ["ref"], "context": {"active_test": False}},
        ):
            tiers.setdefault(partenaire["ref"], partenaire["id"])
    return {
        "comptes_lot": dict(comptes_lot),
        "comptes": comptes,
        "journaux_lot": dict(journaux_lot),
        "journaux": journaux,
        "tiers_lot": dict(tiers_lot),
        "tiers": tiers,
    }


def manquants(elements_existants: Existants) -> dict[str, list[str]]:
    """Ce que le lot demande et qu'Odoo n'a pas.

    Rôle : refuser d'écrire dans une vraie destination à qui il manque
    un compte, un journal ou un tiers (jamais créé en douce).
    Paramètres : existants — résultat de rechercher_existants.
    Retour : {« comptes » | « journaux » | « tiers » : [codes absents]},
    sans les natures complètes.
    Erreurs : aucune.
    Usages : preparer, connecteurs.odoo.ConnecteurOdoo.ecrire.
    """
    absents = {
        "comptes": [
            str(code)
            for code in elements_existants["comptes_lot"]
            if code not in elements_existants["comptes"]
        ],
        "journaux": [
            code
            for code in elements_existants["journaux_lot"]
            if code not in elements_existants["journaux"]
        ],
        "tiers": [
            ref
            for ref in elements_existants["tiers_lot"]
            if ref not in elements_existants["tiers"]
        ],
    }
    return {nature: codes for nature, codes in absents.items() if codes}


def preparer(
    cible: CibleOdoo, lot: Lot, j: Journal, creer_manquants: bool = True
) -> tuple[
    dict[str | None, tuple[int, bool]],
    dict[str, int],
    dict[str, int],
    Preparation,
]:
    """Trouve comptes, journaux et tiers ; crée les manquants si permis.

    Retourne ({code: (id, lettrable)}, {journal: id}, {tiers: id}, bilan).
    Lève ErreurInjection si un code journal dépasse 5 caractères, ou si
    quelque chose manque alors que `creer_manquants` est faux (vraie
    destination : rien n'est créé sans arbitrage).
    """
    with j.etape("Préparation : comptes, journaux et tiers de la base") as e:
        elements_existants = rechercher_existants(cible, lot)
        absents = manquants(elements_existants)
        if absents and not creer_manquants:
            raise ErreurInjection(
                "Absents de la base %s (à créer par le comptable avant "
                "l'envoi) : %s"
                % (
                    cible.base,
                    " ; ".join(
                        "%s %s" % (nature, ", ".join(codes))
                        for nature, codes in absents.items()
                    ),
                )
            )
        comptes = elements_existants["comptes"]
        a_creer = absents.get("comptes", [])
        for c in a_creer:
            t = type_compte_pcg(c)
            ident = cible.appel(
                "account.account",
                "create",
                [
                    {
                        "code": c,
                        "name": elements_existants["comptes_lot"][c] or c,
                        "account_type": t,
                        "reconcile": t
                        in ("asset_receivable", "liability_payable"),
                    }
                ],
            )
            comptes[c] = (
                ident,
                t in ("asset_receivable", "liability_payable"),
            )
        journaux = elements_existants["journaux"]
        jr_crees: list[str] = []
        for code in absents.get("journaux", []):
            if len(code) > 5:
                raise ErreurInjection(
                    "Code journal %r trop long pour Odoo 17 (5 caractères "
                    "au plus) : à faire arbitrer." % code
                )
            journaux[code] = cible.appel(
                "account.journal",
                "create",
                [
                    {
                        "code": code,
                        "name": elements_existants["journaux_lot"][code]
                        or "Journal %s" % code,
                        "type": "general",
                    }
                ],
            )
            jr_crees.append(code)
        tiers = elements_existants["tiers"]
        t_crees = absents.get("tiers", [])
        for lot_t in decouper(t_crees, 200):
            ids = cible.appel(
                "res.partner",
                "create",
                [
                    [
                        {
                            "name": elements_existants["tiers_lot"][r] or r,
                            "ref": r,
                            "is_company": True,
                        }
                        for r in lot_t
                    ]
                ],
            )
            tiers.update(zip(lot_t, ids))
        e.conclure(
            "%s compte(s) créé(s), %s journal(aux) créé(s), %s tiers créé(s)"
            % (
                nombre_texte(len(a_creer)),
                nombre_texte(len(jr_crees)),
                nombre_texte(len(t_crees)),
            )
        )
    if jr_crees:
        j.dire(
            "Journaux créés en type « divers » : %s" % ", ".join(jr_crees),
            "detail",
        )
    comptes_crees: list[str | None] = list(a_creer)
    return (
        comptes,
        journaux,
        tiers,
        {
            "comptes_crees": comptes_crees,
            "journaux_crees": jr_crees,
            "tiers_crees": len(t_crees),
        },
    )


def envoyer(
    cible: CibleOdoo,
    lot: Lot,
    j: Journal | None = None,
    prefixe: str | None = None,
    creer_manquants: bool = True,
) -> ResultatEnvoi:
    """Envoie le lot : préparation, création, validation, lettrage.

    Rôle : porte 6 (base de test) et écriture d'un transfert (ADR-0008).
    Paramètres : cible ; lot ; j — journal ; prefixe — début des
    références « <prefixe>/<journal>/<n°> » (défaut : CONCORDE/<lot>) ;
    creer_manquants — créer comptes, journaux et tiers absents (base de
    test) ou refuser (vraie destination).
    Retour : ResultatEnvoi (erreurs, lettrage, durée…).
    Erreurs : ErreurInjection (lignes en devise, éléments absents).
    Usages : circuit.executer (porte 6), connecteurs.odoo.
    """
    j = ou_muet(j)
    debut = time.monotonic()
    lid = lot_id(lot)
    j.dire(
        "Base de test %s (Odoo %s) — lot %s"
        % (cible.base, cible.version, lid),
        "info",
    )
    devises = {
        ligne["devise"]
        for ligne in lot.lignes
        if ligne["devise"] and ligne["devise"] != "EUR"
    }
    if devises:
        raise ErreurInjection(
            "Lignes en devise (%s) : non gérées à la porte 6 pour l'instant."
            % ", ".join(sorted(devises))
        )
    comptes, journaux, tiers, prep = preparer(cible, lot, j, creer_manquants)

    ecritures = lot.ecritures()
    debut_ref = prefixe or "CONCORDE/%s" % lid
    refs = {cle: ref_ecriture(debut_ref, cle) for cle in ecritures}
    deja = references_presentes(cible, list(refs.values()))
    if deja:
        j.dire(
            "%s écriture(s) déjà présentes (envoi précédent) : elles ne "
            "sont pas renvoyées" % nombre_texte(len(deja)),
            "info",
        )

    def valeurs_ecriture(
        cle: CleEcriture, lignes: list[LigneLot]
    ) -> ValeursEcritureOdoo:
        """Valeurs Odoo de l'écriture `cle` (montants en euros)."""
        return {
            "move_type": "entry",
            "journal_id": journaux[cle[0]],
            "date": str(lignes[0]["date"]),
            "ref": refs[cle],
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "account_id": comptes[ligne["compte_cible"]][0],
                        "partner_id": tiers.get(ligne["tiers_ref"]) or False,
                        "name": ligne["libelle"] or ligne["piece"] or "/",
                        "debit": euros(ligne["debit"]),
                        "credit": euros(ligne["credit"]),
                    },
                )
                for ligne in lignes
            ],
        }

    a_envoyer = [
        (cle, ls) for cle, ls in ecritures.items() if refs[cle] not in deja
    ]
    crees: dict[CleEcriture, int] = {}
    erreurs: list[ErreurOdoo] = []
    n = _paralleles()
    paquets = decouper(a_envoyer, TAILLE_PAQUET)
    avance = {"fait": 0}
    verrou = threading.Lock()

    def creer(
        paquet: list[tuple[CleEcriture, list[LigneLot]]],
    ) -> tuple[list[tuple[CleEcriture, int]], list[ErreurOdoo]]:
        """Un paquet -> ([(clé, id)], [erreurs]).

        Écriture refusée = isolée, renvoyée une par une.
        """
        errs: list[ErreurOdoo] = []
        try:
            ids = cible.appel(
                "account.move",
                "create",
                [[valeurs_ecriture(c, ls) for c, ls in paquet]],
            )
            res: list[tuple[CleEcriture, int]] = list(
                zip([c for c, _ in paquet], ids)
            )
        except FauteXmlRpc:
            res = []
            for c, ls in paquet:
                try:
                    res.append(
                        (
                            c,
                            cible.appel(
                                "account.move",
                                "create",
                                [valeurs_ecriture(c, ls)],
                            ),
                        )
                    )
                except FauteXmlRpc as exc:
                    errs.append(
                        {
                            "ecriture": cle_texte(c),
                            "etape": "création",
                            "erreur": _erreur_odoo(exc),
                        }
                    )
        with verrou:
            avance["fait"] += len(paquet)
            if (
                avance["fait"] // 1000
                != (avance["fait"] - len(paquet)) // 1000
            ):
                j.dire(
                    "… %s / %s écritures envoyées"
                    % (
                        nombre_texte(avance["fait"]),
                        nombre_texte(len(a_envoyer)),
                    ),
                    "detail",
                )
        return res, errs

    with j.etape(
        "Envoi en brouillon : %s écritures, paquets de %d, %d requête(s) "
        "à la fois" % (nombre_texte(len(a_envoyer)), TAILLE_PAQUET, n)
    ) as e:
        for res, errs in en_parallele(creer, paquets, n):
            crees.update(res)
            erreurs.extend(errs)
        e.conclure(
            "%s créées, %s en erreur"
            % (nombre_texte(len(crees)), nombre_texte(len(erreurs)))
        )

    # Validation : en parallèle PAR JOURNAL (deux validations dans un même
    # journal se disputeraient la numérotation des pièces).
    par_journal: defaultdict[str, list[tuple[CleEcriture, int]]] = defaultdict(
        list
    )
    for c, m in crees.items():
        par_journal[c[0]].append((c, m))

    def valider(
        liste: list[tuple[CleEcriture, int]],
    ) -> tuple[int, list[ErreurOdoo]]:
        """Valide les écritures d'un journal : (nombre validé, erreurs)."""
        ok = 0
        errs: list[ErreurOdoo] = []
        for paquet in decouper(liste, 200):
            try:
                cible.appel(
                    "account.move", "action_post", [[m for _, m in paquet]]
                )
                ok += len(paquet)
            except FauteXmlRpc:
                for c, m in paquet:
                    try:
                        cible.appel("account.move", "action_post", [[m]])
                        ok += 1
                    except FauteXmlRpc as exc:
                        errs.append(
                            {
                                "ecriture": cle_texte(c),
                                "etape": "validation",
                                "erreur": _erreur_odoo(exc),
                            }
                        )
        return ok, errs

    with j.etape(
        "Validation des écritures (%d journaux, %d à la fois)"
        % (len(par_journal), n)
    ) as e:
        # Les plus gros journaux d'abord : la charge se répartit mieux.
        journaux_tries = sorted(par_journal.values(), key=len, reverse=True)
        valides = 0
        for ok, errs in en_parallele(valider, journaux_tries, n):
            valides += ok
            erreurs.extend(errs)
        e.conclure("%s validées" % nombre_texte(valides))

    lettrage = lettrer(cible, lot, crees, comptes, j, erreurs)
    for err in erreurs[:10]:
        j.dire(
            "Erreur Odoo — %s (%s) : %s"
            % (err["ecriture"], err["etape"], err["erreur"]),
            "erreur",
        )
    if len(erreurs) > 10:
        j.dire(
            "… et %d autre(s) erreur(s) (détail dans le rapport)"
            % (len(erreurs) - 10),
            "erreur",
        )
    return {
        "lot": lid,
        "base": cible.base,
        "preparation": prep,
        "deja_presentes": len(deja),
        "creees": len(crees),
        "erreurs": erreurs,
        "lettrage": lettrage,
        "duree_s": round(time.monotonic() - debut, 1),
    }


def lettrer(
    cible: CibleOdoo,
    lot: Lot,
    crees: dict[CleEcriture, int],
    comptes: dict[str | None, tuple[int, bool]],
    j: Journal,
    erreurs: list[ErreurOdoo],
) -> ResultatLettrage:
    """Refait le lettrage du FEC.

    Une lettre = les lignes (compte, tiers, lettre) du lot. Les erreurs sont
    ajoutées à `erreurs`.
    """
    groupes: defaultdict[tuple[str | None, str, str], list[LigneLot]] = (
        defaultdict(list)
    )
    for ligne in lot.lignes:
        if ligne["lettrage"] and cle_ecriture(ligne) in crees:
            groupes[
                (ligne["compte_cible"], ligne["tiers_ref"], ligne["lettrage"])
            ].append(ligne)
    if not groupes:
        return {"lettres": 0, "faites": 0, "ignorees": 0}
    with j.etape(
        "Lettrage : %s lettre(s) à refaire" % nombre_texte(len(groupes))
    ) as e:
        # Lignes Odoo créées, dans l'ordre d'envoi de chaque écriture.
        lignes_odoo: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
        for paquet_ids in decouper(list(crees.values()), 500):
            for ml in cible.appel(
                "account.move.line",
                "search_read",
                [[["move_id", "in", paquet_ids]]],
                {"fields": ["move_id", "debit", "credit"], "order": "id"},
            ):
                lignes_odoo[ml["move_id"][0]].append(ml)
        ident: dict[int, int] = {}
        for cle, lignes in lot.ecritures().items():
            mid = crees.get(cle)
            if mid is None:
                continue
            odoo = lignes_odoo.get(mid, [])
            if len(odoo) != len(lignes):
                continue
            for ligne, ml in zip(lignes, odoo):
                montants = (
                    round(ml["debit"] * 100),
                    round(ml["credit"] * 100),
                )
                if montants == (ligne["debit"], ligne["credit"]):
                    ident[id(ligne)] = ml["id"]
        tentees: dict[str, list[int]] = {}
        ignorees: dict[str, list[str]] = {
            "ligne_seule": [],
            "compte_non_lettrable": [],
        }
        for (compte, tiers_ref, lettre), lignes in groupes.items():
            ids_odoo = [ident.get(id(ligne)) for ligne in lignes]
            ids_trouves = [i for i in ids_odoo if i is not None]
            nom = "lettre %s sur %s%s" % (
                lettre,
                compte,
                " (%s)" % tiers_ref if tiers_ref else "",
            )
            if len(lignes) < 2:
                ignorees["ligne_seule"].append(nom)
                continue
            if not comptes[compte][1]:
                ignorees["compte_non_lettrable"].append(nom)
                continue
            if len(ids_trouves) != len(ids_odoo):
                erreurs.append(
                    {
                        "ecriture": nom,
                        "etape": "lettrage",
                        "erreur": "lignes non retrouvées dans Odoo après "
                        "l'envoi",
                    }
                )
                continue
            tentees[nom] = ids_trouves

        def lettrer_un(
            element: tuple[str, list[int]],
        ) -> tuple[str, str | None]:
            """Lettre une lettre : (nom, erreur Odoo ou None)."""
            nom, ids = element
            try:
                cible.appel("account.move.line", "reconcile", [ids])
            except FauteXmlRpc as exc:
                # reconcile() ne renvoie rien : XML-RPC ne sait pas
                # transmettre ce « rien » (allow_none). Le lettrage est fait ;
                # on le VÉRIFIE ci-dessous de toute façon.
                if "cannot marshal None" not in str(exc.faultString):
                    return nom, _erreur_odoo(exc)
            return nom, None

        for nom, err in en_parallele(lettrer_un, list(tentees.items())):
            if err:
                erreurs.append(
                    {"ecriture": nom, "etape": "lettrage", "erreur": err}
                )
                del tentees[nom]
        # Vérification dans la base : chaque lettre tentée a-t-elle bien un
        # rapprochement ?
        tous = [i for ids in tentees.values() for i in ids]
        lettrees: set[int] = set()
        for paquet_ids in decouper(tous, 1000):
            lettrees |= {
                ml["id"]
                for ml in cible.appel(
                    "account.move.line",
                    "read",
                    [paquet_ids],
                    {"fields": ["matching_number"]},
                )
                if ml["matching_number"]
            }
        faites = 0
        for nom, ids in tentees.items():
            if all(i in lettrees for i in ids):
                faites += 1
            else:
                erreurs.append(
                    {
                        "ecriture": nom,
                        "etape": "lettrage",
                        "erreur": "lettrage demandé mais absent de la base",
                    }
                )
        e.conclure(
            "%s faites et vérifiées ; écartées : %s ligne(s) seule(s) "
            "(contrepartie hors du lot), %s sur compte non lettrable"
            % (
                nombre_texte(faites),
                nombre_texte(len(ignorees["ligne_seule"])),
                nombre_texte(len(ignorees["compte_non_lettrable"])),
            )
        )
    return {
        "lettres": len(groupes),
        "faites": faites,
        "ignorees": {k: len(v) for k, v in ignorees.items()},
        "ignorees_detail": {k: v[:200] for k, v in ignorees.items()},
    }


# ---------------------------------------------------------------------------
# Relecture : la base de test contient-elle exactement le lot ?
# ---------------------------------------------------------------------------


def _lire_rangs(
    connexion: ConnexionLecture, lid: str
) -> list[tuple[Any, ...]]:
    """Lignes du lot `lid` dans la base de test (une requête SQL).

    Rang : (réf. écriture, état, compte, réf. tiers, débit, crédit, lettre).
    """
    curseur = connexion.cursor()
    with curseur:
        curseur.execute(
            "SELECT am.ref, am.state, aa.code, rp.ref, aml.debit, "
            "aml.credit, aml.matching_number FROM account_move_line aml "
            "JOIN account_move am ON am.id = aml.move_id "
            "JOIN account_account aa ON aa.id = aml.account_id "
            "LEFT JOIN res_partner rp ON rp.id = aml.partner_id "
            "WHERE am.ref LIKE %s",
            ("CONCORDE/%s/%%" % lid,),
        )
        return curseur.fetchall()


def relire(
    lot: Lot,
    connexion: ConnexionLecture | None = None,
    base: str | None = None,
    j: Journal | None = None,
) -> Rapport:
    """Relit en SQL (lecture seule) les écritures du lot et compare.

    Sans `connexion`, ouvre (puis ferme) une connexion PostgreSQL en lecture
    seule à `base` (défaut : CONCORDE_TEST_BASE).
    """
    j = ou_muet(j)
    lid = lot_id(lot)
    if connexion is None:
        import psycopg2

        nom_base = base or os.environ.get("CONCORDE_TEST_BASE")
        # Sans nom, libpq choisit la base par défaut (comme dbname=None).
        connexion_base = (
            psycopg2.connect(dbname=nom_base)
            if nom_base
            else psycopg2.connect()
        )
        connexion_base.set_session(readonly=True, autocommit=True)
        try:
            rangs = _lire_rangs(connexion_base, lid)
        finally:
            connexion_base.close()
    else:
        rangs = _lire_rangs(connexion, lid)
    r = Rapport()

    sortie: TotauxLot = {
        "lignes": len(rangs),
        "ecritures": len({x[0] for x in rangs}),
        "debit": sum(_centimes_base(x[4]) for x in rangs),
        "credit": sum(_centimes_base(x[5]) for x in rangs),
    }
    entree = lot.totaux()
    r.info("entree", entree)
    r.info("sortie", sortie)
    libelles_totaux: tuple[tuple[CleTotaux, str], ...] = (
        ("ecritures", "écritures"),
        ("lignes", "lignes"),
        ("debit", "débit"),
        ("credit", "crédit"),
    )
    for k, nom in libelles_totaux:
        if entree[k] != sortie[k]:
            r.constat(
                "BLOQUANT",
                "TEST_ECART",
                "Écart lot / base de test",
                ["%s : lot %s, base de test %s" % (nom, entree[k], sortie[k])],
            )
    r.constat(
        "BLOQUANT",
        "TEST_NON_VALIDEE",
        "Écritures restées en brouillon",
        sorted({x[0] for x in rangs if x[1] != "posted"}),
    )
    sa = lot.balance_par_compte(cible=True)
    sb: defaultdict[str | None, int] = defaultdict(int)
    for x in rangs:
        sb[x[2]] += _centimes_base(x[4]) - _centimes_base(x[5])
    r.constat(
        "BLOQUANT",
        "TEST_ECART_COMPTE",
        "Soldes de comptes différents",
        [
            "%s : lot %s, base %s"
            % (
                k,
                euros_texte(sa.get(k, 0), ","),
                euros_texte(sb.get(k, 0), ","),
            )
            for k in sorted(set(sa) | set(sb), key=str)
            if sa.get(k, 0) != sb.get(k, 0)
        ],
    )
    ta = lignes_par_tiers(lot.lignes)
    tb: defaultdict[str, int] = defaultdict(int)
    for x in rangs:
        if x[3]:
            tb[x[3]] += 1
    r.constat(
        "BLOQUANT",
        "TEST_ECART_TIERS",
        "Lignes de tiers différentes",
        [
            "%s : lot %d, base %d" % (k, ta.get(k, 0), tb.get(k, 0))
            for k in sorted(set(ta) | set(tb))
            if ta.get(k, 0) != tb.get(k, 0)
        ],
    )
    r.info("lignes_lettrees", sum(1 for x in rangs if x[6]))
    annoncer_constats(r, j)
    if not r.constats:
        j.dire(
            "Relecture conforme : %s écritures, %s lignes, D = C = %s €, "
            "soldes et tiers identiques au centime"
            % (
                nombre_texte(sortie["ecritures"]),
                nombre_texte(sortie["lignes"]),
                euros_texte(sortie["debit"], ","),
            ),
            "ok",
        )
    return r
