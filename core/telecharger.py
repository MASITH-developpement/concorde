# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Téléchargement des données d'un Odoo 17 : FEC DGFiP, xlsx, CSV d'import.

Les fonctions reçoivent les enregistrements d'une source (core/odoo_source.py,
SQL ou XML-RPC) : elles ne parlent jamais à Odoo.

FEC (article A47 A-1 du LPF) :
  - 18 colonnes, séparateur « | » (ou tabulation), dates AAAAMMJJ,
    montants à la virgule, en euros ;
  - écritures VALIDÉES uniquement (un brouillon n'a pas sa place dans un FEC) ;
  - équilibre vérifié écriture par écriture et au total, tolérance 0,00 € :
    un écart bloque la génération (ErreurFec), aucun fichier n'est produit ;
  - encodage ISO-8859-15 par défaut : la ponctuation typographique (’ “ – …)
    passe en ASCII ; tout autre caractère non représentable est remplacé
    par « ? » et COMPTÉ dans le rapport (jamais en silence).
"""

import csv
import io
import os
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date
from typing import Any, TypedDict

from .odoo_source import TYPES_TIERS
from .xlsx_ecrire import Centimes, Feuille, ecrire_xlsx, euros_texte


class ErreurFec(RuntimeError):
    """Génération du FEC refusée (déséquilibre, brouillon, devise)."""


class RapportFec(TypedDict):
    """Résultat de `generer_fec` : fichier, comptages et totaux."""

    fichier: str
    lignes: int
    ecritures: int
    total_debit: int
    total_credit: int
    caracteres_remplaces: int
    encodage: str


# Enregistrement lu (ligne, compte, journal, tiers, facture) : dictionnaire
# au format commun de core/odoo_source.py, valeurs hétérogènes.
EnregistrementLu = Mapping[str, Any]


COLONNES_FEC = (
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
)


# Ponctuation typographique -> équivalent ASCII (même sens, aucune perte) :
# ces caractères n'existent pas en ISO-8859-15.
_TYPO = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u202f": " ",
        "\u2022": "-",
    }
)


def _champ_fec(texte: object, sep: str) -> str:
    """Nettoie un champ FEC : sans séparateur, tabulation ni retour ligne."""
    t = str(texte or "").translate(_TYPO)
    for ch in (sep, "\t", "\r", "\n"):
        t = t.replace(ch, " ")
    return t.strip()


def _d(d: date | None) -> str:
    """Date au format FEC AAAAMMJJ ('' si absente)."""
    return d.strftime("%Y%m%d") if d else ""


def nom_fichier_fec(siren: str | None, cloture: date) -> str:
    """Nom réglementaire <SIREN>FEC<AAAAMMJJ>.txt (date de clôture)."""
    return "%sFEC%s.txt" % (siren or "SIREN", cloture.strftime("%Y%m%d"))


def generer_fec(
    lignes: Iterable[EnregistrementLu],
    chemin: str,
    separateur: str = "|",
    encodage: str = "iso-8859-15",
    devise: str = "EUR",
) -> RapportFec:
    """Écrit le FEC des lignes VALIDÉES.

    Rôle : produire le FEC réglementaire, jamais en cas de déséquilibre.
    Paramètres : lignes — itérable trié (date, écriture, ligne), l'ordre
    des sources ; chemin du fichier ; separateur ; encodage ; devise de
    la société.
    Retour : RapportFec (lignes, écritures, totaux, caractères remplacés).
    Erreurs : ErreurFec (devise autre que EUR, brouillon, déséquilibre :
    aucun fichier n'est alors laissé) ; OSError en écriture.
    Usages : passerelle.telecharger, migration.export, tests.
    """
    if devise != "EUR":
        raise ErreurFec(
            "Devise de la société %s : le FEC se tient en euros." % devise
        )
    sep = separateur
    nb, debit, credit = 0, 0, 0
    remplaces = 0
    ecart_par_ecriture: Counter[int] = Counter()
    ecritures: set[int] = set()
    tmp = chemin + ".partiel"
    with open(tmp, "w", encoding=encodage, errors="strict", newline="") as f:
        f.write(sep.join(COLONNES_FEC) + "\r\n")
        for ligne in lignes:
            if ligne["etat"] != "posted":
                raise ErreurFec(
                    "Écriture %s non validée (%s) : interdite dans un FEC."
                    % (
                        ligne["ecriture"] or ligne["ecriture_id"],
                        ligne["etat"],
                    )
                )
            aux = ligne["compte_type"] in TYPES_TIERS and ligne["tiers_id"]
            champs = [
                ligne["journal_code"],
                ligne["journal_lib"],
                ligne["ecriture"],
                _d(ligne["date"]),
                ligne["compte"],
                ligne["compte_lib"],
                (ligne["tiers_ref"] or str(ligne["tiers_id"])) if aux else "",
                ligne["tiers_nom"] if aux else "",
                ligne["reference"] or ligne["ecriture"],
                _d(ligne["piece_date"] or ligne["date"]),
                ligne["libelle"] or ligne["reference"] or "/",
                euros_texte(ligne["debit"], ","),
                euros_texte(ligne["credit"], ","),
                ligne["lettrage"],
                _d(ligne["date_lettrage"]),
                _d(ligne["date"]),
                (
                    euros_texte(abs(ligne["montant_devise"]), ",")
                    if ligne["montant_devise"] is not None
                    else ""
                ),
                ligne["devise"],
            ]
            ligne_fec = sep.join(_champ_fec(c, sep) for c in champs) + "\r\n"
            sure = ligne_fec.encode(encodage, errors="replace").decode(
                encodage
            )
            remplaces += sum(1 for a, b in zip(ligne_fec, sure) if a != b)
            f.write(sure)
            nb += 1
            debit += ligne["debit"]
            credit += ligne["credit"]
            ecart_par_ecriture[ligne["ecriture_id"]] += (
                ligne["debit"] - ligne["credit"]
            )
            ecritures.add(ligne["ecriture_id"])
    desequilibres = {k: v for k, v in ecart_par_ecriture.items() if v}
    if desequilibres or debit != credit:
        os.remove(tmp)
        raise ErreurFec(
            "FEC refusé : %d écriture(s) déséquilibrée(s), total D=%s / C=%s "
            "(tolérance 0,00 €). Écritures : %s"
            % (
                len(desequilibres),
                euros_texte(debit, ","),
                euros_texte(credit, ","),
                sorted(desequilibres)[:20],
            )
        )
    os.replace(tmp, chemin)
    return {
        "fichier": chemin,
        "lignes": nb,
        "ecritures": len(ecritures),
        "total_debit": debit,
        "total_credit": credit,
        "caracteres_remplaces": remplaces,
        "encodage": encodage,
    }


# ---------------------------------------------------------------------------
# xlsx — un classeur, une feuille par objet
# ---------------------------------------------------------------------------

ENTETES_LIGNES = (
    "Journal",
    "Écriture",
    "Date",
    "Date pièce",
    "Référence",
    "Compte",
    "Libellé compte",
    "Réf. tiers",
    "Tiers",
    "Libellé",
    "Débit",
    "Crédit",
    "Lettrage",
    "Date lettrage",
    "Montant devise",
    "Devise",
    "Échéance",
    "État",
    "Type pièce",
    # Colonnes techniques : servent à la réintégration (aller-retour),
    # ne pas modifier.
    "id_ligne",
    "id_ecriture",
    "id_tiers",
    "modifie_le",
)


def _ligne_xlsx(ligne: EnregistrementLu) -> list[object]:
    """Cellules d'une ligne d'écriture pour la feuille « Ecritures »."""
    return [
        ligne["journal_code"],
        ligne["ecriture"],
        ligne["date"],
        ligne["piece_date"],
        ligne["reference"],
        ligne["compte"],
        ligne["compte_lib"],
        ligne["tiers_ref"],
        ligne["tiers_nom"],
        ligne["libelle"],
        Centimes(ligne["debit"]),
        Centimes(ligne["credit"]),
        ligne["lettrage"],
        ligne["date_lettrage"],
        (
            Centimes(ligne["montant_devise"])
            if ligne["montant_devise"] is not None
            else None
        ),
        ligne["devise"],
        ligne["echeance"],
        ligne["etat"],
        ligne["type_piece"],
        ligne["ligne_id"],
        ligne["ecriture_id"],
        ligne["tiers_id"],
        str(ligne["modifie_le"] or ""),
    ]


def generer_xlsx(
    chemin: str,
    lignes: Iterable[EnregistrementLu] | None = None,
    comptes: Iterable[EnregistrementLu] | None = None,
    journaux: Iterable[EnregistrementLu] | None = None,
    tiers: Iterable[EnregistrementLu] | None = None,
    factures: Iterable[EnregistrementLu] | None = None,
) -> dict[str, int]:
    """Classeur xlsx des objets fournis (None = feuille absente).

    Retour : {nom de feuille: nombre de lignes de données}.
    """
    feuilles: list[Feuille] = []
    if lignes is not None:
        feuilles.append(
            (
                "Ecritures",
                ENTETES_LIGNES,
                (_ligne_xlsx(ligne) for ligne in lignes),
            )
        )
    if comptes is not None:
        feuilles.append(
            (
                "Comptes",
                ("Code", "Libellé", "Type", "Lettrable", "Déprécié", "id"),
                (
                    [
                        c["code"],
                        c["libelle"],
                        c["type"],
                        c["lettrable"],
                        c["deprecie"],
                        c["id"],
                    ]
                    for c in comptes
                ),
            )
        )
    if journaux is not None:
        feuilles.append(
            (
                "Journaux",
                ("Code", "Libellé", "Type", "Actif", "id"),
                (
                    [j["code"], j["libelle"], j["type"], j["actif"], j["id"]]
                    for j in journaux
                ),
            )
        )
    if tiers is not None:
        feuilles.append(
            (
                "Tiers",
                (
                    "Nom",
                    "Réf.",
                    "TVA",
                    "SIREN",
                    "Email",
                    "Téléphone",
                    "Rue",
                    "CP",
                    "Ville",
                    "Pays",
                    "Société",
                    "Client",
                    "Fournisseur",
                    "Actif",
                    "id",
                    "id_parent",
                ),
                (
                    [
                        t["nom"],
                        t["ref"],
                        t["tva"],
                        t["siren"],
                        t["email"],
                        t["telephone"],
                        t["rue"],
                        t["cp"],
                        t["ville"],
                        t["pays"],
                        t["societe"],
                        t["client"],
                        t["fournisseur"],
                        t["actif"],
                        t["id"],
                        t["parent_id"],
                    ]
                    for t in tiers
                ),
            )
        )
    if factures is not None:
        feuilles.append(
            (
                "Factures",
                (
                    "Numéro",
                    "Type",
                    "État",
                    "Paiement",
                    "Journal",
                    "Tiers",
                    "Date",
                    "Date facture",
                    "Échéance",
                    "Référence",
                    "HT",
                    "TVA",
                    "TTC",
                    "Reste dû",
                    "Devise",
                    "id",
                    "id_tiers",
                ),
                (
                    [
                        f["numero"],
                        f["type_piece"],
                        f["etat"],
                        f["etat_paiement"],
                        f["journal_code"],
                        f["tiers_nom"],
                        f["date"],
                        f["date_facture"],
                        f["echeance"],
                        f["reference"],
                        Centimes(f["ht"]),
                        Centimes(f["tva"]),
                        Centimes(f["ttc"]),
                        Centimes(f["reste_du"]),
                        f["devise"],
                        f["id"],
                        f["tiers_id"],
                    ]
                    for f in factures
                ),
            )
        )
    return ecrire_xlsx(chemin, feuilles)


# ---------------------------------------------------------------------------
# CSV d'import Odoo — pour recharger dans un autre Odoo (17 à 20)
# ---------------------------------------------------------------------------
#
# Entêtes en noms techniques Odoo : reconnus par l'import natif quelle que
# soit la langue de l'interface. Ordre d'import : journaux, comptes, tiers,
# écritures.


def _csv(entetes: Sequence[str], lignes: Iterable[Sequence[object]]) -> str:
    """Texte CSV (BOM UTF-8, fins de ligne CRLF) : entêtes puis lignes.

    Usages : csv_comptes, csv_journaux, csv_tiers, csv_ecritures.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(entetes)
    w.writerows(lignes)
    return "﻿" + buf.getvalue()


def csv_comptes(comptes: Iterable[EnregistrementLu]) -> str:
    """CSV d'import des comptes non dépréciés."""
    return _csv(
        ["code", "name", "account_type", "reconcile"],
        (
            [
                c["code"],
                c["libelle"],
                c["type"],
                "1" if c["lettrable"] else "0",
            ]
            for c in comptes
            if not c["deprecie"]
        ),
    )


def csv_journaux(journaux: Iterable[EnregistrementLu]) -> str:
    """CSV d'import des journaux actifs."""
    return _csv(
        ["code", "name", "type"],
        ([j["code"], j["libelle"], j["type"]] for j in journaux if j["actif"]),
    )


def csv_tiers(tiers: Iterable[EnregistrementLu]) -> str:
    """CSV d'import des tiers actifs (id externe concorde_tiers_<id>)."""
    return _csv(
        [
            "id",
            "name",
            "ref",
            "vat",
            "company_registry",
            "is_company",
            "email",
            "phone",
            "street",
            "zip",
            "city",
            "country_id/code",
        ],
        (
            [
                "concorde_tiers_%s" % t["id"],
                t["nom"],
                t["ref"],
                t["tva"],
                t["siren"],
                "1" if t["societe"] else "0",
                t["email"],
                t["telephone"],
                t["rue"],
                t["cp"],
                t["ville"],
                t["pays"],
            ]
            for t in tiers
            if t["actif"]
        ),
    )


def csv_ecritures(lignes: Iterable[EnregistrementLu]) -> str:
    """Écritures one2many : la 1re ligne d'une écriture porte l'en-tête.

    Journal par code, compte par code, tiers par identifiant externe du
    csv_tiers (concorde_tiers_<id>). Montants au point, exacts.
    """

    def rangs() -> Iterator[list[str]]:
        """Rangs CSV ; l'en-tête n'est écrit qu'à la 1re ligne."""
        precedente = None
        for ligne in lignes:
            entete = ligne["ecriture_id"] != precedente
            precedente = ligne["ecriture_id"]
            yield (
                [
                    ligne["journal_code"],
                    ligne["date"].isoformat(),
                    ligne["reference"] or ligne["ecriture"],
                ]
                if entete
                else ["", "", ""]
            ) + [
                ligne["compte"],
                ligne["libelle"],
                (
                    "concorde_tiers_%s" % ligne["tiers_id"]
                    if ligne["tiers_id"]
                    else ""
                ),
                euros_texte(ligne["debit"]),
                euros_texte(ligne["credit"]),
            ]

    return _csv(
        [
            "journal_id/code",
            "date",
            "ref",
            "line_ids/account_id/code",
            "line_ids/name",
            "line_ids/partner_id/id",
            "line_ids/debit",
            "line_ids/credit",
        ],
        rangs(),
    )


def generer_csv(
    dossier: str,
    lignes: Iterable[EnregistrementLu] | None = None,
    comptes: Iterable[EnregistrementLu] | None = None,
    journaux: Iterable[EnregistrementLu] | None = None,
    tiers: Iterable[EnregistrementLu] | None = None,
) -> dict[str, int]:
    """Écrit les CSV d'import Odoo dans <dossier>.

    Retour : {fichier: nombre de lignes de données}.
    """
    os.makedirs(dossier, exist_ok=True)
    produits: dict[str, int] = {}
    for nom, objets, fonction in (
        ("1_journaux.csv", journaux, csv_journaux),
        ("2_comptes.csv", comptes, csv_comptes),
        ("3_tiers.csv", tiers, csv_tiers),
        ("4_ecritures.csv", lignes, csv_ecritures),
    ):
        if objets is None:
            continue
        contenu = fonction(objets)
        chemin = os.path.join(dossier, nom)
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            f.write(contenu)
        produits[chemin] = contenu.count("\r\n") - 1
    return produits
