# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Analyse des données comptables lues dans un Odoo 17 (lecture seule, 0 LLM).

Reçoit les enregistrements d'une source (core/odoo_source.py) et rend un
rapport de constats, classés BLOQUANT / ALERTE / INFO, chacun avec son
nombre total et des exemples (les listes complètes vont dans le JSON).

Contrôles :
  ÉCRITURES  équilibre au centime (écriture et total), ligne sans compte,
             écriture d'une seule ligne, ligne à montant nul (hors journal
             de TVA sur encaissements, ventilée par journal), date future,
             compte client / fournisseur sans tiers, compte déprécié utilisé,
             doublons probables (journal + date + référence + montant ; sur
             le journal de TVA sur encaissements, même rapprochement et
             paires écriture + extourne écartées), brouillons anciens.
  TIERS      société sans SIREN ni TVA, SIREN / TVA FR invalides, doublons
             (même TVA, même SIREN ou même nom normalisé).
  PLAN       compte utilisé absent du plan, journal inactif utilisé.
"""

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any, TypedDict

from .demat import siren_valide, tva_fr_valide
from .odoo_source import TYPES_TIERS
from .xlsx_ecrire import euros_texte

NIVEAUX = ("BLOQUANT", "ALERTE", "INFO")
EXEMPLES_MAX = 20
JOURS_BROUILLON_ANCIEN = 30

# Constat d'un rapport : niveau, code, message, nombre, exemples, elements
# (et « origine » ajoutée par certains appelants). Destiné au JSON.
Constat = dict[str, Any]


class ResumeEcriture(TypedDict):
    """Résumé d'une écriture construit pendant la lecture des lignes."""

    id: int
    ecriture: str
    planifiee: bool
    journal: str
    date: date | None
    etat: str
    reference: str
    lignes: int
    solde: int
    debit: int
    caba_rapprochement_id: int | None
    extourne_de_id: int | None


class Rapport:
    """Rapport de constats (BLOQUANT / ALERTE / INFO) et d'informations.

    Partagé par l'analyse, la comparaison, la balance, la surveillance,
    la migration et la sécurité.
    """

    def __init__(self) -> None:
        """Crée un rapport vide."""
        self.constats: list[Constat] = []
        # Informations libres du rapport (valeurs sérialisables en JSON).
        self.infos: dict[str, Any] = {}

    def info(self, cle: str, valeur: object) -> None:
        """Enregistre (ou remplace) l'information `cle`."""
        self.infos[cle] = valeur

    def constat(
        self,
        niveau: str,
        code: str,
        message: str,
        elements: Sequence[object],
    ) -> None:
        """Ajoute un constat si `elements` n'est pas vide.

        Rôle : point d'entrée unique de tous les contrôles.
        Paramètres : niveau (un de NIVEAUX), code stable, message lisible,
        elements — liste complète des éléments en cause.
        Retour : aucun.
        Erreurs : aucune.
        Usages : analyser, comparaison, comptes, surveillance, migration,
        securite.
        """
        if not elements:
            return
        self.constats.append(
            {
                "niveau": niveau,
                "code": code,
                "message": message,
                "nombre": len(elements),
                "exemples": elements[:EXEMPLES_MAX],
                "elements": elements,
            }
        )

    def compte(self, niveau: str) -> int:
        """Nombre de constats du niveau donné."""
        return sum(1 for c in self.constats if c["niveau"] == niveau)

    @property
    def statut(self) -> str:
        """« bloquant », « alertes » ou « conforme »."""
        if self.compte("BLOQUANT"):
            return "bloquant"
        return "alertes" if self.compte("ALERTE") else "conforme"

    def en_dict(self, complet: bool = True) -> dict[str, Any]:
        """Rend le rapport en dict JSON, scellé par une empreinte SHA-256.

        Rôle : produire la forme publiée (fichier, interface) du rapport.
        Paramètres : complet — False retire les listes complètes
        (`elements`) et ne garde que les exemples.
        Retour : {statut, infos, synthese, constats, empreinte}.
        Erreurs : ValueError si un constat a un niveau inconnu.
        Usages : passerelle, comparaison, interface, scripts, securite.
        """
        constats = sorted(
            self.constats,
            key=lambda c: (NIVEAUX.index(c["niveau"]), c["code"]),
        )
        if not complet:
            constats = [
                {k: v for k, v in c.items() if k != "elements"}
                for c in constats
            ]
        d: dict[str, Any] = {
            "statut": self.statut,
            "infos": self.infos,
            "synthese": {n: self.compte(n) for n in NIVEAUX},
            "constats": constats,
        }
        d["empreinte"] = hashlib.sha256(
            json.dumps(
                d, sort_keys=True, default=str, ensure_ascii=False
            ).encode()
        ).hexdigest()
        return d


def normaliser_nom(nom: str | None) -> str:
    """Nom en majuscules ASCII, sans forme juridique ni ponctuation.

    Usages : analyser (doublons de tiers), tiers_siret (rapprochement avec
    l'annuaire des entreprises).
    """
    s = (
        unicodedata.normalize("NFKD", nom or "")
        .encode("ascii", "ignore")
        .decode()
        .upper()
    )
    s = re.sub(
        r"\b(SARL|SAS|SASU|SA|EURL|SCI|SNC|SELARL|ETS|STE|SOCIETE)\b", " ", s
    )
    return re.sub(r"[^A-Z0-9]", "", s)


def analyser(
    lignes: Iterable[Mapping[str, Any]],
    comptes: Iterable[Mapping[str, Any]] = (),
    journaux: Iterable[Mapping[str, Any]] = (),
    tiers: Iterable[Mapping[str, Any]] = (),
    aujourd_hui: date | None = None,
    societe: str | None = None,
    journal_caba: str = "",
) -> Rapport:
    """Analyse complète. `lignes` est un itérable (une seule passe).

    journal_caba : code du journal de TVA sur encaissements de la société
    ('' : aucun), traité à part pour les doublons et les lignes nulles.
    """
    aujourd_hui = aujourd_hui or date.today()
    r = Rapport()
    if societe:
        r.info("societe", societe)
    plan = {c["code"]: c for c in comptes}
    journaux_inactifs = {j["code"] for j in journaux if not j["actif"]}

    nb = 0
    debit = credit = 0
    par_etat: Counter[str] = Counter()
    par_journal: Counter[str] = Counter()
    d_min: date | None = None
    d_max: date | None = None
    ecritures: dict[int, ResumeEcriture] = {}  # ecriture_id -> résumé
    sans_compte: list[str] = []
    nulles: list[str] = []
    nulles_par_journal: Counter[str] = Counter()
    nulles_caba = 0
    futures: list[str] = []
    sans_tiers: list[str] = []
    depreciees: list[str] = []
    # Brouillons à comptabilisation automatique (amortissements…).
    planifiees: list[str] = []
    hors_plan: set[str] = set()
    journal_inactif: set[str] = set()
    tiers_utilises: set[int] = set()

    for ligne in lignes:
        nb += 1
        debit += ligne["debit"]
        credit += ligne["credit"]
        par_etat[ligne["etat"]] += 1
        par_journal[ligne["journal_code"]] += 1
        if ligne["date"]:
            d_min = (
                ligne["date"] if d_min is None else min(d_min, ligne["date"])
            )
            d_max = (
                ligne["date"] if d_max is None else max(d_max, ligne["date"])
            )
        e = ecritures.get(ligne["ecriture_id"])
        if e is None:
            nom = (
                ligne["ecriture"]
                if ligne["ecriture"] not in ("", "/")
                else (
                    "brouillon %s id %s"
                    % (ligne["journal_code"], ligne["ecriture_id"])
                )
            )
            e = ecritures[ligne["ecriture_id"]] = {
                "id": ligne["ecriture_id"],
                "ecriture": nom,
                "planifiee": ligne.get("auto_post", "no") not in ("", "no"),
                "journal": ligne["journal_code"],
                "date": ligne["date"],
                "etat": ligne["etat"],
                "reference": ligne["reference"],
                "lignes": 0,
                "solde": 0,
                "debit": 0,
                "caba_rapprochement_id": ligne["caba_rapprochement_id"],
                "extourne_de_id": ligne["extourne_de_id"],
            }
        e["lignes"] += 1
        e["solde"] += ligne["debit"] - ligne["credit"]
        e["debit"] += ligne["debit"]
        ref_l = "%s (ligne %s)" % (e["ecriture"], ligne["ligne_id"])
        if not ligne["compte"]:
            sans_compte.append(ref_l)
        elif plan and ligne["compte"] not in plan:
            hors_plan.add(ligne["compte"])
        elif plan and plan[ligne["compte"]]["deprecie"]:
            depreciees.append("%s — compte %s" % (ref_l, ligne["compte"]))
        if ligne["debit"] == 0 and ligne["credit"] == 0:
            if journal_caba and ligne["journal_code"] == journal_caba:
                nulles_caba += 1
            else:
                nulles.append(
                    "%s — journal %s" % (ref_l, ligne["journal_code"])
                )
                nulles_par_journal[ligne["journal_code"]] += 1
        if ligne["compte_type"] in TYPES_TIERS and not ligne["tiers_id"]:
            sans_tiers.append("%s — compte %s" % (ref_l, ligne["compte"]))
        if ligne["tiers_id"]:
            tiers_utilises.add(ligne["tiers_id"])
        if ligne["journal_code"] in journaux_inactifs:
            journal_inactif.add(ligne["journal_code"])

    for e in sorted(
        ecritures.values(), key=lambda e: e["date"] or date.min, reverse=True
    ):
        if e["date"] and e["date"] > aujourd_hui:
            cible = planifiees if e["planifiee"] else futures
            cible.append(
                "%s du %s" % (e["ecriture"], e["date"].strftime("%d/%m/%Y"))
            )

    r.info("lignes", nb)
    r.info("ecritures", len(ecritures))
    r.info("periode", [d_min, d_max])
    r.info("total_debit", euros_texte(debit, ","))
    r.info("total_credit", euros_texte(credit, ","))
    r.info("par_etat", dict(par_etat))
    r.info("par_journal", dict(sorted(par_journal.items())))
    r.info("journal_tva_encaissements", journal_caba)
    r.info(
        "lignes_montant_nul_par_journal",
        dict(sorted(nulles_par_journal.items())),
    )
    r.info("lignes_montant_nul_caba_ecartees", nulles_caba)

    # --- BLOQUANTS ---------------------------------------------------------
    desequ = [
        "%s : écart %s €" % (e["ecriture"], euros_texte(e["solde"], ","))
        for e in ecritures.values()
        if e["solde"]
    ]
    r.constat(
        "BLOQUANT",
        "ECRITURE_DESEQUILIBREE",
        "Écritures déséquilibrées (tolérance 0,00 €)",
        desequ,
    )
    if debit != credit:
        r.constat(
            "BLOQUANT",
            "TOTAL_DESEQUILIBRE",
            "Total débit ≠ total crédit",
            [
                "D %s / C %s"
                % (euros_texte(debit, ","), euros_texte(credit, ","))
            ],
        )
    r.constat(
        "BLOQUANT", "LIGNE_SANS_COMPTE", "Lignes sans compte", sans_compte
    )

    # --- ALERTES -----------------------------------------------------------
    r.constat(
        "ALERTE",
        "DATE_FUTURE",
        "Écritures datées après le %s" % aujourd_hui.strftime("%d/%m/%Y"),
        futures,
    )
    r.constat(
        "INFO",
        "ECRITURE_PLANIFIEE",
        "Écritures planifiées (brouillons comptabilisés automatiquement à "
        "leur date : amortissements, récurrences)",
        planifiees,
    )
    r.constat(
        "ALERTE",
        "ECRITURE_UNE_LIGNE",
        "Écritures d'une seule ligne",
        [e["ecriture"] for e in ecritures.values() if e["lignes"] == 1],
    )
    r.constat("ALERTE", "LIGNE_MONTANT_NUL", "Lignes à montant nul", nulles)
    r.constat(
        "ALERTE",
        "TIERS_MANQUANT",
        "Lignes sur compte client / fournisseur sans tiers",
        sans_tiers,
    )
    r.constat(
        "ALERTE",
        "COMPTE_DEPRECIE",
        "Lignes sur un compte déprécié",
        depreciees,
    )
    r.constat(
        "ALERTE",
        "COMPTE_HORS_PLAN",
        "Comptes utilisés absents du plan",
        sorted(hors_plan),
    )
    r.constat(
        "ALERTE",
        "JOURNAL_INACTIF",
        "Journaux inactifs encore utilisés",
        sorted(journal_inactif),
    )

    r.constat(
        "ALERTE",
        "DOUBLON_PROBABLE",
        "Doublons probables (même journal, date, référence et montant ; "
        "TVA sur encaissements : même rapprochement, hors extournes)",
        doublons_probables(ecritures.values(), journal_caba),
    )

    limite = aujourd_hui - timedelta(days=JOURS_BROUILLON_ANCIEN)
    r.constat(
        "INFO",
        "BROUILLON_ANCIEN",
        "Brouillons datés de plus de %d jours" % JOURS_BROUILLON_ANCIEN,
        [
            e["ecriture"]
            for e in ecritures.values()
            if e["etat"] == "draft" and e["date"] and e["date"] < limite
        ],
    )

    # --- TIERS -------------------------------------------------------------
    if tiers:
        _analyser_tiers(
            r,
            [
                t
                for t in tiers
                if t["id"] in tiers_utilises and not t["parent_id"]
            ],
        )
    return r


def doublons_probables(
    ecritures: Iterable[ResumeEcriture], journal_caba: str
) -> list[str]:
    """Groupes d'écritures probablement saisies deux fois.

    Rôle : regrouper les écritures par journal, date, référence et montant
    débit. Sur le journal de TVA sur encaissements (`journal_caba`), Odoo
    crée une écriture par règlement partiel : la clé y ajoute le
    rapprochement (`tax_cash_basis_rec_id`, s'il est renseigné), et une
    écriture et son extourne (`reversed_entry_id`) ne comptent pas.
    Paramètres : résumés des écritures ; code du journal de TVA sur
    encaissements ('' : aucun).
    Retour : un texte « référence : écriture, écriture… » par groupe d'au
    moins deux écritures.
    Erreurs : KeyError si un résumé est incomplet.
    Usages : analyser, tests.
    """
    groupes: defaultdict[
        tuple[str, date | None, str, int, int | None], list[ResumeEcriture]
    ] = defaultdict(list)
    for ecriture in ecritures:
        if ecriture["reference"] and ecriture["debit"]:
            caba = bool(journal_caba) and ecriture["journal"] == journal_caba
            groupes[
                (
                    ecriture["journal"],
                    ecriture["date"],
                    ecriture["reference"].strip().upper(),
                    ecriture["debit"],
                    ecriture["caba_rapprochement_id"] if caba else None,
                )
            ].append(ecriture)
    res = []
    for cle, groupe in groupes.items():
        if journal_caba and cle[0] == journal_caba:
            ids = {ecriture["id"] for ecriture in groupe}
            extournes = {
                ecriture["extourne_de_id"]
                for ecriture in groupe
                if ecriture["extourne_de_id"] in ids
            }
            groupe = [
                ecriture
                for ecriture in groupe
                if ecriture["id"] not in extournes
                and ecriture["extourne_de_id"] not in ids
            ]
        if len(groupe) > 1:
            res.append(
                "%s : %s"
                % (
                    cle[2],
                    ", ".join(ecriture["ecriture"] for ecriture in groupe),
                )
            )
    return res


def _analyser_tiers(r: Rapport, tiers: Sequence[Mapping[str, Any]]) -> None:
    """Contrôles sur les tiers (sociétés mères) utilisés dans les écritures."""
    r.info("tiers_utilises", len(tiers))
    sans_id: list[str] = []
    siren_ko: list[str] = []
    tva_ko: list[str] = []
    par_tva: defaultdict[str, list[str]] = defaultdict(list)
    par_siren: defaultdict[str, list[str]] = defaultdict(list)
    par_nom: defaultdict[str, list[str]] = defaultdict(list)
    for t in tiers:
        etiquette = "%s (id %s)" % (t["nom"], t["id"])
        tva = re.sub(r"\s", "", t["tva"]).upper()
        siren = re.sub(r"\D", "", t["siren"])[:9]
        fr = (t["pays"] or "FR") == "FR"
        if t["societe"] and fr and not tva and not siren:
            sans_id.append(etiquette)
        if siren and fr and not siren_valide(siren):
            siren_ko.append("%s : %s" % (etiquette, t["siren"]))
        if tva.startswith("FR") and not tva_fr_valide(tva):
            tva_ko.append("%s : %s" % (etiquette, t["tva"]))
        if tva:
            par_tva[tva].append(etiquette)
        if siren and fr:
            par_siren[siren].append(etiquette)
        nom = normaliser_nom(t["nom"])
        if nom:
            par_nom[nom].append(etiquette)
    r.constat(
        "ALERTE",
        "TIERS_SANS_SIREN_TVA",
        "Sociétés françaises sans SIREN ni TVA",
        sans_id,
    )
    r.constat(
        "ALERTE", "SIREN_INVALIDE", "SIREN invalides (clé de Luhn)", siren_ko
    )
    r.constat(
        "ALERTE",
        "TVA_INVALIDE",
        "TVA intracommunautaires FR invalides",
        tva_ko,
    )
    doublons: list[str] = []
    for cle, grp in (("TVA", par_tva), ("SIREN", par_siren), ("nom", par_nom)):
        doublons += [
            "%s identique : %s" % (cle, " / ".join(v))
            for v in grp.values()
            if len(v) > 1
        ]
    r.constat("ALERTE", "TIERS_DOUBLON", "Tiers en double probable", doublons)


def rendu_texte(rapport: Mapping[str, Any]) -> str:
    """Rend lisible en console un rapport (forme `Rapport.en_dict`)."""
    i = rapport["infos"]
    out = ["CONCORDE — Analyse des données Odoo 17", "=" * 40]
    if "societe" in i:
        out.append("Société   : %s" % i["societe"])
    p = i.get("periode") or [None, None]
    out.append(
        "Période   : %s → %s"
        % tuple(
            d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else "?"
            for d in p
        )
    )
    out.append(
        "Lignes    : %s   Écritures : %s"
        % (i.get("lignes"), i.get("ecritures"))
    )
    out.append(
        "Débit     : %s €   Crédit : %s €"
        % (i.get("total_debit"), i.get("total_credit"))
    )
    out.append("États     : %s" % i.get("par_etat"))
    out.append("")
    s = rapport["synthese"]
    out.append(
        "STATUT : %s  (%d bloquant, %d alerte, %d info)"
        % (rapport["statut"].upper(), s["BLOQUANT"], s["ALERTE"], s["INFO"])
    )
    for c in rapport["constats"]:
        out.append("")
        out.append("[%s] %s — %d" % (c["niveau"], c["message"], c["nombre"]))
        for ex in c["exemples"][:5]:
            out.append("    · %s" % ex)
        if c["nombre"] > 5:
            out.append(
                "    … et %d autre(s) (détail dans le JSON)"
                % (c["nombre"] - 5)
            )
    out.append("")
    out.append("Empreinte SHA-256 : %s" % rapport["empreinte"])
    return "\n".join(out)
