# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Socle commun des injecteurs Odoo 17 / 18 et de la chaîne de conversion.

Regroupe ce que les trois modules faisaient chacun de leur côté :
regroupement des lignes canoniques par écriture, connexion XML-RPC v2,
appels `execute_kw`, et l'injecteur lui-même (le payload account.move est
identique entre Odoo 17 et 18 : seules la version cible et l'étiquette
de trace diffèrent).
"""

from collections import defaultdict
from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Any, ClassVar, TypedDict

from core.canonical import Canonique, LigneEcriture
from core.guardian import Guardian
from core.xml_sur import ErreurXmlRpc, ProxyXmlRpc


class ErreurInjecteur(RuntimeError):
    """Refus d'injection : déséquilibre, identifiants absents, code inconnu."""


class EcritureRegroupee(TypedDict):
    """Une écriture : ses lignes canoniques et son total en centimes."""

    ref_ext: str
    journal: str
    numero: str
    date: datetime.date
    libelle: str
    lignes: list[LigneEcriture]
    total: int


class LignePayloadOdoo(TypedDict):
    """Ligne account.move.line envoyée à Odoo (montants en euros)."""

    name: str
    account_id: int | str
    debit: float
    credit: float


class PayloadOdoo(TypedDict):
    """Payload account.move envoyé à Odoo par `create`."""

    ref: str
    journal_id: int | str
    date: str
    move_type: str
    line_ids: list[tuple[int, int, LignePayloadOdoo]]


class RapportInjection(TypedDict):
    """Rapport rendu par `InjecteurOdoo.injecter`."""

    mode: str
    cible: str
    nb_ecritures: int
    deja_importees: list[str]
    injectees: list[dict[str, str | bool | int]]
    refusees: list[dict[str, str]]


@dataclass
class ConnexionOdoo:
    """Session XML-RPC authentifiée sur une base Odoo."""

    db: str
    uid: int
    mot_de_passe: str
    modeles: ProxyXmlRpc

    def executer(
        self,
        modele: str,
        methode: str,
        arguments: list[Any],
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Appelle `execute_kw` sur la base connectée.

        Rôle : point d'appel unique des méthodes ORM Odoo via XML-RPC.
        Paramètres : modele — ex. « account.move » ; methode — ex.
        « search_read » ; arguments — arguments positionnels de la
        méthode ; options — arguments nommés (omis si None).
        Retour : la réponse XML-RPC telle que renvoyée par Odoo (donnée
        dynamique : listes et dictionnaires).
        Erreurs : FauteXmlRpc (refus Odoo), OSError (réseau).
        Usages : InjecteurOdoo (injectors/odoo17.py, odoo18.py),
        ConvertisseurOdoo.extraire (injectors/odoo_conversion.py).
        """
        parametres: list[Any] = [
            self.db,
            self.uid,
            self.mot_de_passe,
            modele,
            methode,
            arguments,
        ]
        if options is not None:
            parametres.append(options)
        return self.modeles.execute_kw(*parametres)


def connecter_odoo(
    url: str,
    db: str,
    utilisateur: str,
    mot_de_passe: str,
    version_attendue: str,
    guardian: Guardian,
    code_trace: str,
    libelle_version: str,
    classe_erreur: type[RuntimeError],
) -> ConnexionOdoo:
    """Ouvre une session XML-RPC v2 et vérifie la version du serveur.

    Rôle : authentifier l'utilisateur ; une version de serveur différente
    de celle attendue est tracée en avertissement (non bloquant), de même
    qu'une version illisible.
    Paramètres : url, db, utilisateur, mot_de_passe — accès Odoo ;
    version_attendue — préfixe attendu (ex. « 17 ») ; guardian — journal
    d'audit ; code_trace — étape tracée (ex. « odoo17 ») ; libelle_version
    — mot du message d'avertissement (« cible » ou « attendue ») ;
    classe_erreur — exception levée en cas de refus.
    Retour : la connexion authentifiée.
    Erreurs : classe_erreur si l'authentification est refusée ;
    ErreurXmlRpc ou OSError si le serveur ne répond pas à
    l'authentification.
    Usages : InjecteurOdoo.connecter, ConvertisseurOdoo.connecter_source.
    """
    commun = ProxyXmlRpc("{}/xmlrpc/2/common".format(url))
    try:
        infos_version = commun.version()
    except (ErreurXmlRpc, OSError) as exc:
        # La vérification de version n'est qu'un avertissement :
        # l'authentification ci-dessous dira si le serveur répond.
        guardian.tracer(
            code_trace, "avertissement", "version_odoo illisible : %s" % exc
        )
        infos_version = {}
    version = (
        str(infos_version.get("server_version", ""))
        if isinstance(infos_version, dict)
        else ""
    )
    if version and not version.startswith(version_attendue):
        guardian.tracer(
            code_trace,
            "avertissement",
            "version_odoo=%s (%s %s)"
            % (version, libelle_version, version_attendue),
        )
    uid = commun.authenticate(db, utilisateur, mot_de_passe, {})
    if not isinstance(uid, int) or not uid:
        raise classe_erreur("Authentification Odoo refusée.")
    modeles = ProxyXmlRpc("{}/xmlrpc/2/object".format(url))
    return ConnexionOdoo(db, uid, mot_de_passe, modeles)


def regrouper_ecritures(
    canon: Canonique,
    prefixer_ref: bool,
    classe_erreur: type[RuntimeError],
) -> list[EcritureRegroupee]:
    """Regroupe les lignes canoniques par écriture (journal + numéro).

    Rôle : former les écritures à injecter ou convertir, chacune
    équilibrée au centime (tolérance Concordance 0,00 €).
    Paramètres : canon — journal canonique ; prefixer_ref — True :
    référence « CONCORDE/<journal>/<numéro> » (idempotence de
    l'injection), False : référence = numéro ; classe_erreur — exception
    levée sur une écriture déséquilibrée.
    Retour : les écritures triées par (journal, numéro).
    Erreurs : classe_erreur si débit ≠ crédit dans une écriture.
    Usages : InjecteurOdoo.regrouper_ecritures, ConvertisseurOdoo._regrouper.
    """
    groupes: defaultdict[tuple[str, str], list[LigneEcriture]] = defaultdict(
        list
    )
    for ligne in canon.lignes:
        groupes[(ligne.journal_code, ligne.ecriture_num)].append(ligne)
    ecritures: list[EcritureRegroupee] = []
    for (journal, num), lignes in sorted(groupes.items()):
        debit = sum(ligne.debit for ligne in lignes)
        credit = sum(ligne.credit for ligne in lignes)
        if debit != credit:
            raise classe_erreur(
                "Écriture %s/%s déséquilibrée (%s vs %s centimes) — "
                "tolérance Concordance 0,00 €." % (journal, num, debit, credit)
            )
        ecritures.append(
            {
                "ref_ext": (
                    "CONCORDE/%s/%s" % (journal, num) if prefixer_ref else num
                ),
                "journal": journal,
                "numero": num,
                "date": lignes[0].date_ecriture,
                "libelle": lignes[0].libelle,
                "lignes": lignes,
                "total": debit,
            }
        )
    return ecritures


class InjecteurOdoo:
    """Injecte le journal canonique CONCORDE dans Odoo (account.move).

    Les sous-classes fixent VERSION_CIBLE et CODE_TRACE.
    """

    VERSION_CIBLE: ClassVar[str] = ""
    CODE_TRACE: ClassVar[str] = ""

    def __init__(
        self,
        url: str | None = None,
        db: str | None = None,
        utilisateur: str | None = None,
        mot_de_passe: str | None = None,
        dry_run: bool = True,
        guardian: Guardian | None = None,
    ) -> None:
        """Prépare l'injecteur ; le Guardian doit passer son self-check.

        dry_run=True (défaut) : aucune connexion ni écriture dans Odoo.
        """
        self.url = url  # ex. http://localhost:8069
        self.db = db
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.dry_run = dry_run  # True par défaut : aucune écriture dans Odoo
        self.guardian = guardian or Guardian()
        if not self.guardian.self_check_ok:
            self.guardian.self_check()  # bloquant
        self._connexion: ConnexionOdoo | None = None

    # --- connexion XML-RPC (uniquement si pas dry-run) -----------------------
    def connecter(self) -> int | None:
        """Ouvre la session Odoo ; rend l'uid (None en dry-run)."""
        if self.dry_run:
            return None  # dry-run : aucune connexion nécessaire
        if not (
            self.url and self.db and self.utilisateur and self.mot_de_passe
        ):
            raise ErreurInjecteur(
                "URL/base/utilisateur/mot de passe Odoo requis hors dry-run."
            )
        self._connexion = connecter_odoo(
            self.url,
            self.db,
            self.utilisateur,
            self.mot_de_passe,
            self.VERSION_CIBLE,
            self.guardian,
            self.CODE_TRACE,
            "cible",
            ErreurInjecteur,
        )
        self.guardian.tracer(
            self.CODE_TRACE, "connexion", "uid=%s" % self._connexion.uid
        )
        return self._connexion.uid

    def _connexion_active(self) -> ConnexionOdoo:
        """Connexion ouverte par `connecter` ; refus si elle manque."""
        if self._connexion is None:
            raise ErreurInjecteur("Aucune connexion Odoo ouverte.")
        return self._connexion

    # --- préparation idempotente des écritures -------------------------------
    @staticmethod
    def regrouper_ecritures(canon: Canonique) -> list[EcritureRegroupee]:
        """Regroupe les lignes canoniques par écriture (journal + numéro)."""
        return regrouper_ecritures(canon, True, ErreurInjecteur)

    @staticmethod
    def euros(centimes: int) -> float:
        """Centimes int -> euros pour Odoo.

        Calcul exact en Decimal ; le float n'apparaît qu'à la frontière
        XML-RPC (2 décimales : valeur restituée exactement par Odoo).
        """
        return float(Decimal(int(centimes)) / 100)

    @classmethod
    def vers_payload_odoo(
        cls,
        ecriture: EcritureRegroupee,
        comptes: dict[str, int] | None = None,
        journaux: dict[str, int] | None = None,
    ) -> PayloadOdoo:
        """Transforme une écriture canonique en payload account.move.

        Montants en euros (centimes / 100) ; compte et journal désignés
        par leur identifiant Odoo. comptes / journaux : {code: id Odoo}.
        Sans eux (dry-run), les codes restent, pour l'affichage seulement.
        """
        comptes, journaux = comptes or {}, journaux or {}
        lignes: list[tuple[int, int, LignePayloadOdoo]] = []
        for ligne in ecriture["lignes"]:
            lignes.append(
                (
                    0,
                    0,
                    {
                        "name": ligne.libelle,
                        "account_id": comptes.get(ligne.compte, ligne.compte),
                        "debit": cls.euros(ligne.debit),
                        "credit": cls.euros(ligne.credit),
                    },
                )
            )
        return {
            "ref": ecriture["ref_ext"],
            "journal_id": journaux.get(
                ecriture["journal"], ecriture["journal"]
            ),
            "date": ecriture["date"].strftime("%Y-%m-%d"),
            "move_type": "entry",
            "line_ids": lignes,
        }

    def _ids_par_code(self, modele: str, codes: list[str]) -> dict[str, int]:
        """{code: id} des enregistrements `modele` dont le code est listé."""
        return {
            enregistrement["code"]: enregistrement["id"]
            for enregistrement in self._connexion_active().executer(
                modele,
                "search_read",
                [[["code", "in", codes]]],
                {"fields": ["code"]},
            )
        }

    def _resoudre(
        self, ecritures: list[EcritureRegroupee]
    ) -> tuple[dict[str, int], dict[str, int]]:
        """{code: id} des comptes et journaux cibles.

        Code inconnu = refus (rien de deviné).
        """
        codes_c = sorted(
            {ligne.compte for e in ecritures for ligne in e["lignes"]}
        )
        codes_j = sorted({e["journal"] for e in ecritures})
        comptes = self._ids_par_code("account.account", codes_c)
        journaux = self._ids_par_code("account.journal", codes_j)
        manquants = ["compte " + c for c in codes_c if c not in comptes] + [
            "journal " + j for j in codes_j if j not in journaux
        ]
        if manquants:
            raise ErreurInjecteur(
                "Absents de la base Odoo cible (rien n'est créé ni deviné) : "
                + ", ".join(manquants[:20])
            )
        return comptes, journaux

    # --- injection -----------------------------------------------------------
    def _deja_importees(self, refs: list[str]) -> set[str]:
        """Refs déjà présentes dans Odoo (idempotence)."""
        if self.dry_run:
            return set()
        existantes = self._connexion_active().executer(
            "account.move",
            "search_read",
            [[["ref", "in", list(refs)]]],
            {"fields": ["ref"]},
        )
        return {e["ref"] for e in existantes}

    def injecter(self, canon: Canonique) -> RapportInjection:
        """Injecte le journal canonique. Retourne un rapport détaillé."""
        if not canon.est_equilibre(tolerance=0):
            raise ErreurInjecteur(
                "Journal déséquilibré (D=%s / C=%s centimes) — injection "
                "refusée, tolérance Concordance 0,00 €."
                % (canon.total_debit, canon.total_credit)
            )
        ecritures = self.regrouper_ecritures(canon)
        self.connecter()
        refs = [e["ref_ext"] for e in ecritures]
        deja = self._deja_importees(refs)
        comptes, journaux = (
            ({}, {}) if self.dry_run else self._resoudre(ecritures)
        )

        rapport: RapportInjection = {
            "mode": "dry-run" if self.dry_run else "production",
            "cible": "odoo-%s" % self.VERSION_CIBLE,
            "nb_ecritures": len(ecritures),
            "deja_importees": sorted(deja),
            "injectees": [],
            "refusees": [],
        }
        for e in ecritures:
            if e["ref_ext"] in deja:
                rapport["refusees"].append(
                    {"ref": e["ref_ext"], "motif": "idempotence"}
                )
                continue
            payload = self.vers_payload_odoo(e, comptes, journaux)
            if self.dry_run:
                rapport["injectees"].append(
                    {
                        "ref": e["ref_ext"],
                        "simule": True,
                        "total_centimes": e["total"],
                        "nb_lignes": len(payload["line_ids"]),
                    }
                )
            else:
                self.guardian.tracer(self.CODE_TRACE, "creation", e["ref_ext"])
                self._connexion_active().executer(
                    "account.move", "create", [payload]
                )
                rapport["injectees"].append(
                    {"ref": e["ref_ext"], "simule": False}
                )
        self.guardian.tracer(
            self.CODE_TRACE,
            "injection",
            "mode=%s ecritures=%s" % (rapport["mode"], len(ecritures)),
        )
        return rapport
