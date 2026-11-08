# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 5 — export et conformité.

Produit, à partir du lot filtré et traduit :
  - un FEC de contrôle (comptes Odoo), au format DGFiP ;
  - le CSV d'import Odoo (écritures), pour mémoire et contrôle croisé ;
  - le fichier des lignes retirées par les filtres (rien ne disparaît sans
    trace).
Puis RELIT le FEC produit avec le connecteur FEC et compare au lot :
nombre de lignes et d'écritures, totaux, équilibre de chaque écriture,
solde de chaque compte Odoo, nombre de lignes par tiers. Un centime
d'écart = BLOQUANT.
"""

import os
from collections.abc import Iterator
import datetime
from typing import TypedDict

from ..analyser import Rapport
from ..journal import Journal, nombre_texte, ou_muet
from ..telecharger import RapportFec, csv_ecritures, generer_fec
from ..xlsx_ecrire import Centimes, ecrire_xlsx, euros_texte
from .connecteur_fec import lire_fec
from .lot import (
    CleEcriture,
    CleTotaux,
    Lot,
    annoncer_constats,
    cle_ecriture,
    cle_texte,
    lignes_par_tiers,
)


class LigneSortie(TypedDict):
    """Ligne au format attendu par core/telecharger (FEC et CSV)."""

    etat: str
    ecriture_id: int
    ecriture: str
    journal_code: str
    journal_lib: str
    date: datetime.date
    piece_date: datetime.date | None
    reference: str
    compte: str
    compte_lib: str
    compte_type: str
    tiers_id: str | None
    tiers_ref: str
    tiers_nom: str
    libelle: str
    debit: int
    credit: int
    lettrage: str
    date_lettrage: datetime.date | None
    montant_devise: int | None
    devise: str


def lignes_sortie(lot: Lot) -> Iterator[LigneSortie]:
    """Lignes du lot au format attendu par core/telecharger (FEC et CSV).

    Rôle : un seul endroit qui traduit le Lot vers les sorties fichier.
    Paramètres : lot — lignes au format commun ; le compte cible est pris
    s'il est renseigné, sinon le compte source.
    Retour : itérateur de LigneSortie, dans l'ordre du lot.
    Erreurs : aucune.
    Usages : ecrire_fec_lot, exporter (CSV Odoo).
    """
    ids: dict[CleEcriture, int] = {}
    for ligne in lot.lignes:
        eid = ids.setdefault(cle_ecriture(ligne), len(ids) + 1)
        yield {
            "etat": "posted",
            "ecriture_id": eid,
            "ecriture": ligne["ecriture"],
            "journal_code": ligne["journal_code"],
            "journal_lib": ligne["journal_lib"],
            "date": ligne["date"],
            "piece_date": ligne["piece_date"],
            "reference": ligne["piece"],
            "compte": ligne["compte_cible"] or ligne["compte"],
            "compte_lib": ligne["compte_lib"],
            # le compte auxiliaire suit le tiers, quel que soit le compte cible
            "compte_type": "asset_receivable" if ligne["tiers_ref"] else "",
            "tiers_id": ligne["tiers_ref"] or None,
            "tiers_ref": ligne["tiers_ref"],
            "tiers_nom": ligne["tiers_nom"],
            "libelle": ligne["libelle"],
            "debit": ligne["debit"],
            "credit": ligne["credit"],
            "lettrage": ligne["lettrage"],
            "date_lettrage": ligne["date_lettrage"],
            "montant_devise": ligne["montant_devise"],
            "devise": ligne["devise"],
        }


def ecrire_fec_lot(lot: Lot, chemin: str) -> RapportFec:
    """Écrit le lot en FEC DGFiP (UTF-8, séparateur « | »).

    Rôle : produire un FEC à partir du pivot, pour l'export de contrôle,
    la photo d'une source lue par API et les destinations fichier.
    Paramètres : lot ; chemin — fichier à écrire.
    Retour : RapportFec (lignes, écritures, totaux).
    Erreurs : ErreurFec (déséquilibre : aucun fichier n'est laissé) ;
    OSError en écriture.
    Usages : exporter, connecteurs.fec.ConnecteurFec.ecrire,
    connecteurs.transfert (photo de la source).
    """
    return generer_fec(lignes_sortie(lot), chemin, encodage="utf-8")


def exporter(
    lot: Lot, dossier: str, journal: Journal | None = None
) -> tuple[Rapport, dict[str, str]]:
    """Écrit les fichiers et contrôle la conformité.

    Retourne (Rapport, {nature du fichier: chemin}).
    """
    j = ou_muet(journal)
    os.makedirs(dossier, exist_ok=True)
    fichiers: dict[str, str] = {}
    fec = os.path.join(dossier, "controle_FEC_comptes_odoo.txt")
    with j.etape("Export du FEC de contrôle (comptes Odoo)") as e:
        r_fec = ecrire_fec_lot(lot, fec)
        e.conclure("%s lignes" % nombre_texte(r_fec["lignes"]))
    fichiers["fec"] = fec
    chemin_csv = os.path.join(dossier, "import_odoo_ecritures.csv")
    with open(chemin_csv, "w", encoding="utf-8", newline="") as f:
        f.write(csv_ecritures(list(lignes_sortie(lot))))
    fichiers["csv"] = chemin_csv
    if lot.retirees:
        chemin = os.path.join(dossier, "lignes_retirees.xlsx")
        ecrire_xlsx(
            chemin,
            [
                (
                    "Retirees",
                    (
                        "Filtre",
                        "Ligne source",
                        "Journal",
                        "Écriture",
                        "Date",
                        "Compte",
                        "Tiers",
                        "Libellé",
                        "Débit",
                        "Crédit",
                    ),
                    (
                        [
                            motif,
                            ligne["n"],
                            ligne["journal_code"],
                            ligne["ecriture"],
                            ligne["date"],
                            ligne["compte"],
                            ligne["tiers_ref"],
                            ligne["libelle"],
                            Centimes(ligne["debit"]),
                            Centimes(ligne["credit"]),
                        ]
                        for ligne, motif in lot.retirees
                    ),
                )
            ],
        )
        fichiers["retirees"] = chemin
        j.dire(
            "%s ligne(s) retirée(s) gardées dans %s"
            % (nombre_texte(len(lot.retirees)), os.path.basename(chemin)),
            "detail",
        )

    with j.etape(
        "Conformité : relecture du FEC produit et comparaison au centime"
    ) as e:
        with open(fec, "rb") as f_fec:
            relu = lire_fec(f_fec.read(), os.path.basename(fec))
        r = comparer(lot, relu)
        e.conclure(
            "conforme" if not r.constats else "%d écart(s)" % len(r.constats)
        )
    annoncer_constats(r, j)
    return r, fichiers


def comparer(lot: Lot, relu: Lot) -> Rapport:
    """Compare le lot (comptes cibles) au FEC relu.

    Retourne le Rapport des écarts (tous BLOQUANT).
    """
    r = Rapport()
    a, b = lot.totaux(), relu.totaux()
    r.info("entree", a)
    r.info("sortie", b)
    libelles_totaux: tuple[tuple[CleTotaux, str], ...] = (
        ("lignes", "lignes"),
        ("ecritures", "écritures"),
        ("debit", "débit"),
        ("credit", "crédit"),
    )
    for k, nom in libelles_totaux:
        if a[k] != b[k]:
            r.constat(
                "BLOQUANT",
                "MIG_ECART_SORTIE",
                "Écart entrée / sortie",
                ["%s : entrée %s, sortie %s" % (nom, a[k], b[k])],
            )
    r.constat(
        "BLOQUANT",
        "MIG_ILLISIBLE_SORTIE",
        "Lignes illisibles dans le FEC produit",
        ["ligne %d : %s" % (n, m) for n, _, m in relu.illisibles],
    )
    soldes_a = lot.balance_par_compte(cible=True)
    soldes_b = relu.balance_par_compte()
    r.constat(
        "BLOQUANT",
        "MIG_ECART_COMPTE",
        "Soldes de comptes différents entrée / sortie",
        [
            "%s : entrée %s, sortie %s"
            % (
                k,
                euros_texte(soldes_a.get(k, 0), ","),
                euros_texte(soldes_b.get(k, 0), ","),
            )
            for k in sorted(set(soldes_a) | set(soldes_b), key=str)
            if soldes_a.get(k, 0) != soldes_b.get(k, 0)
        ],
    )
    desequ = [
        k
        for k, lignes_relues in relu.ecritures().items()
        if sum(ligne["debit"] - ligne["credit"] for ligne in lignes_relues)
    ]
    r.constat(
        "BLOQUANT",
        "MIG_ECRITURE_DESEQUILIBREE",
        "Écritures déséquilibrées en sortie",
        [cle_texte(k) for k in desequ],
    )
    ta, tb = lignes_par_tiers(lot.lignes), lignes_par_tiers(relu.lignes)
    r.constat(
        "BLOQUANT",
        "MIG_ECART_TIERS",
        "Lignes de tiers différentes entrée / sortie",
        [
            "%s : entrée %d, sortie %d" % (k, ta.get(k, 0), tb.get(k, 0))
            for k in sorted(set(ta) | set(tb))
            if ta.get(k, 0) != tb.get(k, 0)
        ],
    )
    return r
