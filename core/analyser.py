# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Analyse des données comptables lues dans un Odoo 17 — lecture seule, zéro LLM.

Reçoit les enregistrements d'une source (core/odoo_source.py) et rend un
rapport de constats, classés BLOQUANT / ALERTE / INFO, chacun avec son
nombre total et des exemples (les listes complètes vont dans le JSON).

Contrôles :
  ÉCRITURES  équilibre au centime (écriture et total), ligne sans compte,
             écriture d'une seule ligne, ligne à montant nul, date future,
             compte client / fournisseur sans tiers, compte déprécié utilisé,
             doublons probables (journal + date + référence + montant),
             brouillons anciens.
  TIERS      société sans SIREN ni TVA, SIREN / TVA FR invalides, doublons
             (même TVA, même SIREN ou même nom normalisé).
  PLAN       compte utilisé absent du plan, journal inactif utilisé.
"""

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta

from .demat import siren_valide, tva_fr_valide
from .odoo_source import TYPES_TIERS
from .xlsx_ecrire import euros_texte

NIVEAUX = ("BLOQUANT", "ALERTE", "INFO")
EXEMPLES_MAX = 20
JOURS_BROUILLON_ANCIEN = 30


class Rapport:
    def __init__(self):
        self.constats = []
        self.infos = {}

    def info(self, cle, valeur):
        self.infos[cle] = valeur

    def constat(self, niveau, code, message, elements):
        """Ajoute un constat si `elements` (liste) n'est pas vide."""
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

    def compte(self, niveau):
        return sum(1 for c in self.constats if c["niveau"] == niveau)

    @property
    def statut(self):
        if self.compte("BLOQUANT"):
            return "bloquant"
        return "alertes" if self.compte("ALERTE") else "conforme"

    def en_dict(self, complet=True):
        constats = sorted(
            self.constats,
            key=lambda c: (NIVEAUX.index(c["niveau"]), c["code"]),
        )
        if not complet:
            constats = [
                {k: v for k, v in c.items() if k != "elements"}
                for c in constats
            ]
        d = {
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


def _normaliser_nom(nom):
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
    lignes, comptes=(), journaux=(), tiers=(), aujourd_hui=None, societe=None
):
    """Analyse complète. `lignes` est un itérable (une seule passe)."""
    aujourd_hui = aujourd_hui or date.today()
    r = Rapport()
    if societe:
        r.info("societe", societe)
    plan = {c["code"]: c for c in comptes}
    journaux_inactifs = {j["code"] for j in journaux if not j["actif"]}

    nb = 0
    debit = credit = 0
    par_etat = Counter()
    par_journal = Counter()
    d_min = d_max = None
    ecritures = {}  # ecriture_id -> résumé
    sans_compte, nulles, futures, sans_tiers, depreciees = [], [], [], [], []
    planifiees = (
        []
    )  # brouillons à comptabilisation automatique (amortissements…)
    hors_plan, journal_inactif = set(), set()
    tiers_utilises = set()

    for l in lignes:
        nb += 1
        debit += l["debit"]
        credit += l["credit"]
        par_etat[l["etat"]] += 1
        par_journal[l["journal_code"]] += 1
        if l["date"]:
            d_min = l["date"] if d_min is None else min(d_min, l["date"])
            d_max = l["date"] if d_max is None else max(d_max, l["date"])
        e = ecritures.get(l["ecriture_id"])
        if e is None:
            nom = (
                l["ecriture"]
                if l["ecriture"] not in ("", "/")
                else (
                    "brouillon %s id %s"
                    % (l["journal_code"], l["ecriture_id"])
                )
            )
            e = ecritures[l["ecriture_id"]] = {
                "ecriture": nom,
                "planifiee": l.get("auto_post", "no") not in ("", "no"),
                "journal": l["journal_code"],
                "date": l["date"],
                "etat": l["etat"],
                "reference": l["reference"],
                "lignes": 0,
                "solde": 0,
                "debit": 0,
            }
        e["lignes"] += 1
        e["solde"] += l["debit"] - l["credit"]
        e["debit"] += l["debit"]
        ref_l = "%s (ligne %s)" % (e["ecriture"], l["ligne_id"])
        if not l["compte"]:
            sans_compte.append(ref_l)
        elif plan and l["compte"] not in plan:
            hors_plan.add(l["compte"])
        elif plan and plan[l["compte"]]["deprecie"]:
            depreciees.append("%s — compte %s" % (ref_l, l["compte"]))
        if l["debit"] == 0 and l["credit"] == 0:
            nulles.append(ref_l)
        if l["compte_type"] in TYPES_TIERS and not l["tiers_id"]:
            sans_tiers.append("%s — compte %s" % (ref_l, l["compte"]))
        if l["tiers_id"]:
            tiers_utilises.add(l["tiers_id"])
        if l["journal_code"] in journaux_inactifs:
            journal_inactif.add(l["journal_code"])

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
        "Écritures planifiées (brouillons comptabilisés automatiquement à leur "
        "date : amortissements, récurrences)",
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

    groupes = defaultdict(list)
    for e in ecritures.values():
        if e["reference"] and e["debit"]:
            groupes[
                (
                    e["journal"],
                    e["date"],
                    e["reference"].strip().upper(),
                    e["debit"],
                )
            ].append(e["ecriture"])
    r.constat(
        "ALERTE",
        "DOUBLON_PROBABLE",
        "Doublons probables (même journal, date, référence et montant)",
        [
            "%s : %s" % (k[2], ", ".join(v))
            for k, v in groupes.items()
            if len(v) > 1
        ],
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


def _analyser_tiers(r, tiers):
    """Contrôles sur les tiers (sociétés mères) utilisés dans les écritures."""
    r.info("tiers_utilises", len(tiers))
    sans_id, siren_ko, tva_ko = [], [], []
    par_tva, par_siren, par_nom = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
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
        nom = _normaliser_nom(t["nom"])
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
    doublons = []
    for cle, grp in (("TVA", par_tva), ("SIREN", par_siren), ("nom", par_nom)):
        doublons += [
            "%s identique : %s" % (cle, " / ".join(v))
            for v in grp.values()
            if len(v) > 1
        ]
    r.constat("ALERTE", "TIERS_DOUBLON", "Tiers en double probable", doublons)


def rendu_texte(rapport):
    """Rapport lisible en console."""
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
