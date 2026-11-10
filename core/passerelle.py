# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Actions de la passerelle Odoo 17 (ligne de commande et interface).

  telecharger(source, ...)  -> liste de produits (fichiers + résumé + alertes)
  analyser_source(source, ...) -> rapport d'analyse (dict)

Les fonctions ne lisent ni n'écrivent rien d'autre que ce qu'on leur donne :
une source (core/odoo_source.py) et un dossier de sortie.
"""

import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from typing import Any

from .analyser import Constat, analyser
from .comptes import ContexteSoldes, alertes_balance
from .guardian import Guardian
from .journal import Journal, nombre_texte, ou_muet
from .odoo_source import Enregistrement, SourceOdoo
from .roles_comptes import (
    ConfigAnalyse,
    lire_configuration,
    roles_du_plan,
    table_du_client,
)
from .soldes_cumules import calculer_soldes
from .telecharger import (
    ErreurFec,
    generer_csv,
    generer_fec,
    generer_xlsx,
    nom_fichier_fec,
)
from .xlsx_ecrire import euros_texte

FORMATS = ("fec", "xlsx", "csv")
OBJETS = ("ecritures", "comptes", "journaux", "tiers", "factures")


class Lecteur:
    """Relit les lignes à la demande.

    SQL : nouvelle requête en flux ; XML-RPC : lecture unique mise en cache
    (l'API est lente).
    """

    def __init__(
        self,
        source: SourceOdoo,
        debut: date | None,
        fin: date | None,
        etats: Sequence[str],
    ) -> None:
        """Mémorise la source et la période à relire."""
        self.source, self.debut, self.fin, self.etats = (
            source,
            debut,
            fin,
            etats,
        )
        self._cache: list[Enregistrement] | None = None

    def lignes(self) -> Iterator[Enregistrement]:
        """Rend un nouvel itérateur sur les lignes de la période."""
        if self.source.nature == "sql":
            return iter(self.source.lignes(self.debut, self.fin, self.etats))
        if self._cache is None:
            self._cache = list(
                self.source.lignes(self.debut, self.fin, self.etats)
            )
        return iter(self._cache)


def telecharger(
    source: SourceOdoo,
    dossier: str,
    formats: Sequence[str] = ("xlsx",),
    objets: Iterable[str] = OBJETS,
    du: date | None = None,
    au: date | None = None,
    brouillons: bool = False,
    separateur: str = "|",
    encodage: str = "iso-8859-15",
    guardian: Guardian | None = None,
    journal: Journal | None = None,
) -> list[dict[str, Any]]:
    """Produit les fichiers demandés dans `dossier`.

    Rôle : action « télécharger » de la ligne de commande et de l'interface.
    Paramètres : source Odoo ; dossier de sortie ; formats (FORMATS) ;
    objets (OBJETS) ; période du / au ; brouillons ; separateur et
    encodage du FEC ; guardian (traçage) ; journal d'activité.
    Retour : liste de produits {format, fichiers: [chemins], resume,
    alertes: [..]} (dicts JSON).
    Erreurs : ValueError (format ou objet inconnu) ; ErreurFec si le FEC
    est refusé (aucun fichier FEC n'est alors produit).
    Usages : scripts/concorde_odoo.py, interface/serveur.py.
    """
    inconnus = set(formats) - set(FORMATS) | set(objets) - set(OBJETS)
    if inconnus:
        raise ValueError("Format ou objet inconnu : %s" % sorted(inconnus))
    if "fec" in formats and brouillons:
        raise ErreurFec(
            "Les brouillons sont incompatibles avec le FEC "
            "(écritures validées uniquement)."
        )
    j = ou_muet(journal)
    etats = ("posted", "draft") if brouillons else ("posted",)
    lecteur = Lecteur(source, du, au, etats)
    societe = source.societe_info()
    j.dire(
        "Société %s — devise %s, SIREN %s"
        % (
            societe["nom"],
            societe["devise"],
            societe["siren"] or "non renseigné",
        )
    )
    j.dire(
        "Formats demandés : %s ; données : %s"
        % (", ".join(f.upper() for f in formats), ", ".join(sorted(objets))),
        "detail",
    )
    objets_demandes = set(objets)
    os.makedirs(dossier, exist_ok=True)
    produits: list[dict[str, Any]] = []
    charges: dict[str, list[Enregistrement]] = {}
    lecteurs: dict[str, Callable[[], list[Enregistrement]]] = {
        "comptes": source.comptes,
        "journaux": source.journaux,
        "tiers": source.tiers,
        "factures": lambda: source.factures(du, au),
    }

    def charger(nom: str) -> list[Enregistrement] | None:
        """Lit (une seule fois) l'objet `nom` s'il est demandé."""
        if nom not in objets_demandes:
            return None
        if nom not in charges:
            charges[nom] = lecteurs[nom]()
            j.dire(
                "%s : %s lus"
                % (nom.capitalize(), nombre_texte(len(charges[nom]))),
                "detail",
            )
        return charges[nom]

    def tracer(etape: str, detail: str) -> None:
        """Trace l'étape dans Guardian s'il est fourni."""
        if guardian:
            guardian.tracer("telecharger", etape, detail)

    if "fec" in formats:
        chemin = os.path.join(
            dossier, nom_fichier_fec(societe["siren"], au or date.today())
        )
        with j.etape(
            "FEC : écriture et contrôle d'équilibre écriture par écriture"
        ) as e:
            r = generer_fec(
                lecteur.lignes(),
                chemin,
                separateur=separateur,
                encodage=encodage,
                devise=societe["devise"],
            )
            e.conclure(
                "%s lignes, %s écritures, débit = crédit = %s €"
                % (
                    nombre_texte(r["lignes"]),
                    nombre_texte(r["ecritures"]),
                    euros_texte(r["total_debit"], ","),
                )
            )
        tracer("fec", "%s lignes=%s" % (chemin, r["lignes"]))
        alertes: list[str] = []
        if r["caracteres_remplaces"]:
            j.dire(
                "%d caractère(s) impossibles en %s remplacés par « ? »"
                % (r["caracteres_remplaces"], r["encodage"]),
                "alerte",
            )
            alertes.append(
                "%d caractère(s) non représentable(s) en %s remplacé(s) "
                "par « ? »" % (r["caracteres_remplaces"], r["encodage"])
            )
        if not societe["siren"]:
            j.dire(
                "SIREN de la société absent : le FEC s'appelle %s"
                % os.path.basename(chemin),
                "alerte",
            )
            alertes.append(
                "SIREN de la société absent dans Odoo : nom du fichier "
                "à corriger avant remise."
            )
        produits.append(
            {
                "format": "fec",
                "fichiers": [chemin],
                "alertes": alertes,
                "resume": "%s lignes, %s écritures, débit = crédit = %s €"
                % (
                    r["lignes"],
                    r["ecritures"],
                    euros_texte(r["total_debit"], ","),
                ),
            }
        )

    if "xlsx" in formats:
        chemin = os.path.join(dossier, "concorde_%s.xlsx" % source.base)
        with j.etape("Excel : une feuille par type de données") as e:
            n = generer_xlsx(
                chemin,
                lignes=(
                    lecteur.lignes()
                    if "ecritures" in objets_demandes
                    else None
                ),
                comptes=charger("comptes"),
                journaux=charger("journaux"),
                tiers=charger("tiers"),
                factures=charger("factures"),
            )
            e.conclure(
                ", ".join("%s %s" % (k, nombre_texte(v)) for k, v in n.items())
            )
        tracer("xlsx", "%s %s" % (chemin, n))
        produits.append(
            {
                "format": "xlsx",
                "fichiers": [chemin],
                "alertes": [],
                "resume": ", ".join("%s : %d" % kv for kv in n.items()),
            }
        )

    if "csv" in formats:
        sous = os.path.join(dossier, "csv_import_odoo")
        with j.etape("CSV d'import Odoo") as e:
            n = generer_csv(
                sous,
                lignes=(
                    lecteur.lignes()
                    if "ecritures" in objets_demandes
                    else None
                ),
                comptes=charger("comptes"),
                journaux=charger("journaux"),
                tiers=charger("tiers"),
            )
            e.conclure("%d fichiers" % len(n))
        tracer("csv", "%s %s" % (sous, n))
        produits.append(
            {
                "format": "csv",
                "fichiers": sorted(n),
                "alertes": [],
                "resume": ", ".join(
                    "%s : %d" % (os.path.basename(k), v)
                    for k, v in sorted(n.items())
                ),
            }
        )
    return produits


def analyser_source(
    source: SourceOdoo,
    du: date | None = None,
    au: date | None = None,
    validees: bool = False,
    guardian: Guardian | None = None,
    journal: Journal | None = None,
    config: ConfigAnalyse | None = None,
    aujourd_hui: date | None = None,
) -> dict[str, Any]:
    """Analyse complète d'une base (écritures, tiers, balance).

    Rôle : action « analyser » ; le journal raconte chaque étape. Les
    règles de solde portent sur le solde cumulé à la date de fin, avec les
    rôles de comptes du client (ADR-0017).
    Paramètres : source Odoo ; période du / au ; validees (écritures
    validées seules, sinon brouillons compris) ; guardian (scellement) ;
    journal d'activité ; config — réglages et tables de rôles (lus dans
    concorde.yaml si absent) ; aujourd_hui (date du jour si absent).
    Retour : le rapport (`Rapport.en_dict`, listes complètes).
    Erreurs : celles de la source (ErreurSource, ErreurMontant…) ;
    ErreurYaml, ErreurRoles si concorde.yaml est invalide.
    Usages : comparaison.comparer_bases, scripts/concorde_odoo.py,
    interface/serveur.py.
    """
    j = ou_muet(journal)
    aujourd_hui = aujourd_hui or date.today()
    config = config or lire_configuration()
    etats = ("posted",) if validees else ("posted", "draft")
    societe = source.societe_info()
    parametres = source.parametres_comptables()
    table = table_du_client(config, source.base, societe["nom"])
    j.dire(
        "Société %s — devise %s, SIREN %s"
        % (
            societe["nom"],
            societe["devise"],
            societe["siren"] or "non renseigné",
        )
    )
    j.dire(
        (
            "Rôles des comptes : table du client %s, puis account_type, puis "
            "préfixe" % table.client
            if table
            else "Rôles des comptes : préfixes du plan comptable général "
            "(aucune table client)"
        ),
        "detail",
    )
    with j.etape("Lecture du plan comptable, des journaux et des tiers") as e:
        comptes, journaux, tiers = (
            source.comptes(),
            source.journaux(),
            source.tiers(),
        )
        e.conclure(
            "%s comptes, %s journaux, %s tiers"
            % (
                nombre_texte(len(comptes)),
                nombre_texte(len(journaux)),
                nombre_texte(len(tiers)),
            )
        )
    with j.etape("Contrôle des écritures et des tiers") as e:
        rapport = analyser(
            source.lignes(du, au, etats),
            comptes,
            journaux,
            tiers,
            aujourd_hui=aujourd_hui,
            societe="%s (%s, base %s)"
            % (societe["nom"], societe["devise"], source.base),
            journal_caba=parametres["journal_caba"],
        )
        e.conclure(
            "%s écritures contrôlées"
            % nombre_texte(rapport.infos["ecritures"])
        )
    _raconter_constats(j, rapport.constats)
    with j.etape("Balance et anomalies par compte (soldes cumulés)") as e:
        calcul = calculer_soldes(
            source,
            du,
            au,
            comptes,
            config.journaux_a_nouveaux,
            aujourd_hui,
            parametres,
        )
        contexte: ContexteSoldes = {
            "cumul_comptes": calcul["cumul_comptes"],
            "tiers": calcul["tiers"],
            "table": table,
            "suspens": _lignes_en_suspens(
                source,
                [
                    code
                    for code, role in roles_du_plan(comptes, table).items()
                    if role.role == "paiement_en_suspens"
                    and calcul["cumul_comptes"].get(code)
                ],
                calcul["depart_bilan"],
                au,
            ),
        }
        bal, alertes_comptes = alertes_balance(
            source.balance(du, au), (), j, contexte
        )
        e.conclure(
            "%s comptes mouvementés ; %s"
            % (
                nombre_texte(bal.infos["comptes_mouvementes"]),
                calcul["infos"]["explication"],
            )
        )
    for c in bal.constats:
        # Même alerte que la surveillance : pas de doublon.
        c["origine"] = "balance"
    rapport.constats.extend(bal.constats)
    rapport.constat(
        "INFO",
        "OUVERTURE_DOUBLE_POSSIBLE",
        "Écriture d'à-nouveaux et historique antérieur présents ensemble "
        "(l'ouverture n'est comptée qu'une fois)",
        calcul["ouvertures"],
    )
    rapport.info("calcul_soldes", calcul["infos"])
    rapport.info("table_roles", table.client if table else None)
    rapport.info("roles_comptes", bal.infos["roles_comptes"])
    rapport.info("comptes_en_alerte", alertes_comptes)
    d = rapport.en_dict()
    s = d["synthese"]
    j.dire(
        "Bilan : %s — %d bloquant, %d alerte(s), %d information(s)"
        % (d["statut"].upper(), s["BLOQUANT"], s["ALERTE"], s["INFO"]),
        (
            "erreur"
            if d["statut"] == "bloquant"
            else "alerte" if d["statut"] == "alertes" else "ok"
        ),
    )
    if guardian:
        guardian.tracer("analyser", d["statut"], d["empreinte"])
        j.dire(
            "Rapport scellé par Guardian (SHA-256 %s…)" % d["empreinte"][:16],
            "detail",
        )
    return d


def _lignes_en_suspens(
    source: SourceOdoo,
    codes: Sequence[str],
    depuis: date | None,
    au: date | None,
) -> dict[str, list[Enregistrement]]:
    """Lignes non lettrées des comptes de paiements en suspens.

    Rôle : détail du constat PAIEMENT_EN_SUSPENS_NON_SOLDE.
    Paramètres : source ; codes des comptes concernés ; depuis — départ du
    cumul des comptes de bilan (None : origine) ; au — date de fin.
    Retour : {code: lignes comptabilisées sans lettrage complet}.
    Erreurs : celles de la source.
    Usages : analyser_source.
    """
    res: dict[str, list[Enregistrement]] = {}
    if not codes:
        return res
    for ligne in source.lignes(depuis, au, ("posted",), comptes=codes):
        if not ligne["lettrage"]:
            res.setdefault(ligne["compte"], []).append(ligne)
    return res


def _raconter_constats(j: Journal, constats: Iterable[Constat]) -> None:
    """Annonce chaque constat au journal, au niveau correspondant."""
    for c in constats:
        niveau = {"BLOQUANT": "erreur", "ALERTE": "alerte"}.get(
            c["niveau"], "detail"
        )
        j.dire("%s : %s" % (c["message"], nombre_texte(c["nombre"])), niveau)
