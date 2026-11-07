# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 3 — batterie de contrôles de migration (méthode MASITH).

BLOQUANT (la migration ne passe pas tant qu'il en reste) :
  ligne illisible, écriture déséquilibrée, fichier déséquilibré, ligne à
  montant nul, écriture d'une seule ligne, compte vide ou « 0 », écriture à
  cheval sur deux mois, écriture datée après aujourd'hui (à trancher),
  ligne débit ET crédit.
ALERTE (à regarder, ne bloque pas) :
  même numéro d'écriture dans deux journaux, dates différentes dans une
  écriture (même mois), lignes en double, compte client / fournisseur sans
  tiers, lettrage non soldé.
"""

from collections import defaultdict
from datetime import date

from ..analyser import Rapport
from ..journal import Journal, nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from .lot import Lot, annoncer_constats, cle_ecriture, cle_texte

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

# Ce qui rend deux lignes identiques : journal, écriture, date, compte,
# tiers, libellé, débit, crédit.
SignatureLigne = tuple[str, str, date, str, str, str, int, int]


def controler(
    lot: Lot,
    aujourd_hui: date | None = None,
    journal: Journal | None = None,
) -> Rapport:
    """Applique la batterie au lot. Retourne un Rapport (constats + infos)."""
    j = ou_muet(journal)
    aujourd_hui = aujourd_hui or date.today()
    r = Rapport()
    totaux = lot.totaux()
    r.info("lignes", totaux["lignes"])
    r.info("ecritures", totaux["ecritures"])
    r.info("total_debit", euros_texte(totaux["debit"], ","))
    r.info("total_credit", euros_texte(totaux["credit"], ","))
    dates = [ligne["date"] for ligne in lot.lignes]
    r.info("periode", [min(dates), max(dates)] if dates else [None, None])
    r.info("journaux", sorted({ligne["journal_code"] for ligne in lot.lignes}))

    r.constat(
        "BLOQUANT",
        "MIG_LIGNE_ILLISIBLE",
        "Lignes illisibles dans le fichier",
        ["ligne %d : %s" % (n, motif) for n, _, motif in lot.illisibles],
    )
    ecritures = lot.ecritures()
    desequ: list[str] = []
    une_ligne: list[str] = []
    deux_mois: list[str] = []
    dates_diff: list[str] = []
    futures: list[str] = []
    for cle, lignes in ecritures.items():
        s = sum(ligne["debit"] - ligne["credit"] for ligne in lignes)
        if s:
            desequ.append(
                "%s : écart %s € (lignes %s)"
                % (
                    cle_texte(cle),
                    euros_texte(s, ","),
                    ", ".join(str(ligne["n"]) for ligne in lignes[:6]),
                )
            )
        if len(lignes) == 1:
            une_ligne.append(
                "%s (ligne %d)" % (cle_texte(cle), lignes[0]["n"])
            )
        mois = {(ligne["date"].year, ligne["date"].month) for ligne in lignes}
        if len(mois) > 1:
            deux_mois.append(
                "%s : %s"
                % (
                    cle_texte(cle),
                    ", ".join("%02d/%d" % (m, a) for a, m in sorted(mois)),
                )
            )
        elif len({ligne["date"] for ligne in lignes}) > 1:
            dates_diff.append(cle_texte(cle))
        if max(ligne["date"] for ligne in lignes) > aujourd_hui:
            futures.append(
                "%s du %s"
                % (
                    cle_texte(cle),
                    max(ligne["date"] for ligne in lignes).strftime(
                        "%d/%m/%Y"
                    ),
                )
            )
    r.constat(
        "BLOQUANT",
        "MIG_ECRITURE_DESEQUILIBREE",
        "Écritures déséquilibrées",
        desequ,
    )
    if totaux["debit"] != totaux["credit"]:
        r.constat(
            "BLOQUANT",
            "MIG_FICHIER_DESEQUILIBRE",
            "Fichier déséquilibré",
            [
                "D %s / C %s"
                % (
                    euros_texte(totaux["debit"], ","),
                    euros_texte(totaux["credit"], ","),
                )
            ],
        )
    r.constat(
        "BLOQUANT",
        "MIG_MONTANT_NUL",
        "Lignes à montant nul",
        [
            "%s (ligne %d)" % (cle_texte(cle_ecriture(ligne)), ligne["n"])
            for ligne in lot.lignes
            if not ligne["debit"] and not ligne["credit"]
        ],
    )
    r.constat(
        "BLOQUANT",
        "MIG_DEBIT_ET_CREDIT",
        "Lignes avec un débit ET un crédit",
        [
            "ligne %d" % ligne["n"]
            for ligne in lot.lignes
            if ligne["debit"] and ligne["credit"]
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
            "ligne %d : %r" % (ligne["n"], ligne["compte"])
            for ligne in lot.lignes
            if not ligne["compte"].strip("0 ")
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

    par_num: defaultdict[str, set[str]] = defaultdict(set)
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
    vues: dict[SignatureLigne, int] = {}
    doublons: list[str] = []
    for ligne in lot.lignes:
        signature: SignatureLigne = (
            ligne["journal_code"],
            ligne["ecriture"],
            ligne["date"],
            ligne["compte"],
            ligne["tiers_ref"],
            ligne["libelle"],
            ligne["debit"],
            ligne["credit"],
        )
        if signature in vues:
            doublons.append(
                "lignes %d et %d (%s)"
                % (vues[signature], ligne["n"], cle_texte(signature[:2]))
            )
        else:
            vues[signature] = ligne["n"]
    r.constat(
        "ALERTE", "MIG_LIGNE_DOUBLON", "Lignes identiques en double", doublons
    )
    r.constat(
        "ALERTE",
        "MIG_TIERS_MANQUANT",
        "Lignes sur compte client / fournisseur sans compte auxiliaire",
        [
            "ligne %d : compte %s" % (ligne["n"], ligne["compte"])
            for ligne in lot.lignes
            if ligne["compte"].startswith(PREFIXES_TIERS)
            and not ligne["tiers_ref"]
        ],
    )
    lettres: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    for ligne in lot.lignes:
        if ligne["lettrage"]:
            lettres[
                (ligne["compte"], ligne["tiers_ref"], ligne["lettrage"])
            ] += (ligne["debit"] - ligne["credit"])
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
        "tiers",
        len(
            {ligne["tiers_ref"] for ligne in lot.lignes if ligne["tiers_ref"]}
        ),
    )

    annoncer_constats(r, j)
    if not r.constats:
        j.dire(
            "Aucun problème : les %s écritures passent tous les contrôles"
            % nombre_texte(totaux["ecritures"]),
            "ok",
        )
    return r
