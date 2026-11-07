# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 3 — batterie de contrôles de migration (méthode MASITH).

BLOQUANT (la migration ne passe pas tant qu'il en reste) :
  ligne illisible, écriture déséquilibrée, fichier déséquilibré, ligne à montant nul,
  écriture d'une seule ligne, compte vide ou « 0 », écriture à cheval sur deux mois,
  écriture datée après aujourd'hui (à trancher), ligne débit ET crédit.
ALERTE (à regarder, ne bloque pas) :
  même numéro d'écriture dans deux journaux, dates différentes dans une écriture
  (même mois), lignes en double, compte client / fournisseur sans tiers,
  lettrage non soldé.
"""

from collections import defaultdict
from datetime import date

from ..analyser import Rapport
from ..journal import nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte

PREFIXES_TIERS = (
    "401",
    "403",
    "404",
    "408",
    "411",
    "413",
    "416",
    "418",
    "419",
)


def _e(cle):
    return "%s/%s" % cle


def controler(lot, aujourd_hui=None, journal=None):
    """Applique la batterie au lot. Retourne un Rapport (constats + infos)."""
    j = ou_muet(journal)
    aujourd_hui = aujourd_hui or date.today()
    r = Rapport()
    t = lot.totaux()
    r.info("lignes", t["lignes"])
    r.info("ecritures", t["ecritures"])
    r.info("total_debit", euros_texte(t["debit"], ","))
    r.info("total_credit", euros_texte(t["credit"], ","))
    dates = [l["date"] for l in lot.lignes]
    r.info("periode", [min(dates), max(dates)] if dates else [None, None])
    r.info("journaux", sorted({l["journal_code"] for l in lot.lignes}))

    r.constat(
        "BLOQUANT",
        "MIG_LIGNE_ILLISIBLE",
        "Lignes illisibles dans le fichier",
        ["ligne %d : %s" % (n, motif) for n, _, motif in lot.illisibles],
    )
    ecritures = lot.ecritures()
    desequ, une_ligne, deux_mois, dates_diff, futures = [], [], [], [], []
    for cle, lignes in ecritures.items():
        s = sum(l["debit"] - l["credit"] for l in lignes)
        if s:
            desequ.append(
                "%s : écart %s € (lignes %s)"
                % (
                    _e(cle),
                    euros_texte(s, ","),
                    ", ".join(str(l["n"]) for l in lignes[:6]),
                )
            )
        if len(lignes) == 1:
            une_ligne.append("%s (ligne %d)" % (_e(cle), lignes[0]["n"]))
        mois = {(l["date"].year, l["date"].month) for l in lignes}
        if len(mois) > 1:
            deux_mois.append(
                "%s : %s"
                % (
                    _e(cle),
                    ", ".join("%02d/%d" % (m, a) for a, m in sorted(mois)),
                )
            )
        elif len({l["date"] for l in lignes}) > 1:
            dates_diff.append(_e(cle))
        if max(l["date"] for l in lignes) > aujourd_hui:
            futures.append(
                "%s du %s"
                % (
                    _e(cle),
                    max(l["date"] for l in lignes).strftime("%d/%m/%Y"),
                )
            )
    r.constat(
        "BLOQUANT",
        "MIG_ECRITURE_DESEQUILIBREE",
        "Écritures déséquilibrées",
        desequ,
    )
    if t["debit"] != t["credit"]:
        r.constat(
            "BLOQUANT",
            "MIG_FICHIER_DESEQUILIBRE",
            "Fichier déséquilibré",
            [
                "D %s / C %s"
                % (euros_texte(t["debit"], ","), euros_texte(t["credit"], ","))
            ],
        )
    r.constat(
        "BLOQUANT",
        "MIG_MONTANT_NUL",
        "Lignes à montant nul",
        [
            "%s (ligne %d)" % (_e((l["journal_code"], l["ecriture"])), l["n"])
            for l in lot.lignes
            if not l["debit"] and not l["credit"]
        ],
    )
    r.constat(
        "BLOQUANT",
        "MIG_DEBIT_ET_CREDIT",
        "Lignes avec un débit ET un crédit",
        [
            "ligne %d" % l["n"]
            for l in lot.lignes
            if l["debit"] and l["credit"]
        ],
    )
    r.constat(
        "BLOQUANT",
        "MIG_ECRITURE_UNE_LIGNE",
        "Écritures d'une seule ligne",
        une_ligne,
    )
    r.constat(
        "BLOQUANT",
        "MIG_COMPTE_INVALIDE",
        "Comptes vides ou « 0 »",
        [
            "ligne %d : %r" % (l["n"], l["compte"])
            for l in lot.lignes
            if not l["compte"].strip("0 ")
        ],
    )
    r.constat(
        "BLOQUANT",
        "MIG_ECRITURE_DEUX_MOIS",
        "Écritures à cheval sur deux mois",
        deux_mois,
    )
    r.constat(
        "BLOQUANT",
        "MIG_DATE_FUTURE",
        "Écritures datées après le %s (à trancher)"
        % aujourd_hui.strftime("%d/%m/%Y"),
        futures,
    )

    par_num = defaultdict(set)
    for jc, num in ecritures:
        par_num[num].add(jc)
    r.constat(
        "ALERTE",
        "MIG_ECRITURE_DEUX_JOURNAUX",
        "Même numéro d'écriture dans plusieurs journaux",
        [
            "%s : %s" % (num, ", ".join(sorted(js)))
            for num, js in par_num.items()
            if len(js) > 1
        ],
    )
    r.constat(
        "ALERTE",
        "MIG_DATES_DIFFERENTES",
        "Dates différentes dans une même écriture (même mois)",
        dates_diff,
    )
    vues, doublons = {}, []
    for l in lot.lignes:
        k = (
            l["journal_code"],
            l["ecriture"],
            l["date"],
            l["compte"],
            l["tiers_ref"],
            l["libelle"],
            l["debit"],
            l["credit"],
        )
        if k in vues:
            doublons.append(
                "lignes %d et %d (%s)" % (vues[k], l["n"], _e(k[:2]))
            )
        else:
            vues[k] = l["n"]
    r.constat(
        "ALERTE", "MIG_LIGNE_DOUBLON", "Lignes identiques en double", doublons
    )
    r.constat(
        "ALERTE",
        "MIG_TIERS_MANQUANT",
        "Lignes sur compte client / fournisseur sans compte auxiliaire",
        [
            "ligne %d : compte %s" % (l["n"], l["compte"])
            for l in lot.lignes
            if l["compte"].startswith(PREFIXES_TIERS) and not l["tiers_ref"]
        ],
    )
    lettres = defaultdict(int)
    for l in lot.lignes:
        if l["lettrage"]:
            lettres[(l["compte"], l["tiers_ref"], l["lettrage"])] += (
                l["debit"] - l["credit"]
            )
    r.constat(
        "ALERTE",
        "MIG_LETTRAGE_NON_SOLDE",
        "Lettrages non soldés (lettrage partiel)",
        [
            "%s %s lettre %s : %s €" % (k[0], k[1], k[2], euros_texte(v, ","))
            for k, v in lettres.items()
            if v
        ],
    )
    r.info("lettrages", len(lettres))
    r.info(
        "tiers", len({l["tiers_ref"] for l in lot.lignes if l["tiers_ref"]})
    )

    for c in r.constats:
        niveau = "erreur" if c["niveau"] == "BLOQUANT" else "alerte"
        j.dire("%s : %s" % (c["message"], nombre_texte(c["nombre"])), niveau)
    if not r.constats:
        j.dire(
            "Aucun problème : les %s écritures passent tous les contrôles"
            % nombre_texte(t["ecritures"]),
            "ok",
        )
    return r
