# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Téléchargement des données d'un Odoo 17 : FEC DGFiP, xlsx, CSV d'import Odoo.

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

from .odoo_source import TYPES_TIERS
from .xlsx_ecrire import Centimes, ecrire_xlsx, euros_texte


class ErreurFec(RuntimeError):
    """Génération du FEC refusée (déséquilibre, brouillon, devise)."""


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


def _champ_fec(texte, sep):
    """Un champ FEC ne contient ni séparateur, ni tabulation, ni retour ligne."""
    t = str(texte or "").translate(_TYPO)
    for ch in (sep, "\t", "\r", "\n"):
        t = t.replace(ch, " ")
    return t.strip()


def _d(d):
    return d.strftime("%Y%m%d") if d else ""


def nom_fichier_fec(siren, cloture):
    """Nom réglementaire : <SIREN>FEC<AAAAMMJJ>.txt (clôture de l'exercice)."""
    return "%sFEC%s.txt" % (siren or "SIREN", cloture.strftime("%Y%m%d"))


def generer_fec(
    lignes, chemin, separateur="|", encodage="iso-8859-15", devise="EUR"
):
    """Écrit le FEC des lignes VALIDÉES. Retourne un rapport (dict).

    lignes : itérable trié (date, écriture, ligne) — c'est l'ordre des sources.
    """
    if devise != "EUR":
        raise ErreurFec(
            "Devise de la société %s : le FEC se tient en euros." % devise
        )
    sep = separateur
    nb, debit, credit = 0, 0, 0
    remplaces = 0
    ecart_par_ecriture = Counter()
    ecritures = set()
    tmp = chemin + ".partiel"
    with open(tmp, "w", encoding=encodage, errors="strict", newline="") as f:
        f.write(sep.join(COLONNES_FEC) + "\r\n")
        for l in lignes:
            if l["etat"] != "posted":
                raise ErreurFec(
                    "Écriture %s non validée (%s) : interdite dans un FEC."
                    % (l["ecriture"] or l["ecriture_id"], l["etat"])
                )
            aux = l["compte_type"] in TYPES_TIERS and l["tiers_id"]
            champs = [
                l["journal_code"],
                l["journal_lib"],
                l["ecriture"],
                _d(l["date"]),
                l["compte"],
                l["compte_lib"],
                (l["tiers_ref"] or str(l["tiers_id"])) if aux else "",
                l["tiers_nom"] if aux else "",
                l["reference"] or l["ecriture"],
                _d(l["piece_date"] or l["date"]),
                l["libelle"] or l["reference"] or "/",
                euros_texte(l["debit"], ","),
                euros_texte(l["credit"], ","),
                l["lettrage"],
                _d(l["date_lettrage"]),
                _d(l["date"]),
                (
                    euros_texte(abs(l["montant_devise"]), ",")
                    if l["montant_devise"] is not None
                    else ""
                ),
                l["devise"],
            ]
            ligne = sep.join(_champ_fec(c, sep) for c in champs) + "\r\n"
            sure = ligne.encode(encodage, errors="replace").decode(encodage)
            remplaces += sum(1 for a, b in zip(ligne, sure) if a != b)
            f.write(sure)
            nb += 1
            debit += l["debit"]
            credit += l["credit"]
            ecart_par_ecriture[l["ecriture_id"]] += l["debit"] - l["credit"]
            ecritures.add(l["ecriture_id"])
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
    # Colonnes techniques : servent à la réintégration (aller-retour) — ne pas modifier.
    "id_ligne",
    "id_ecriture",
    "id_tiers",
    "modifie_le",
)


def _ligne_xlsx(l):
    return [
        l["journal_code"],
        l["ecriture"],
        l["date"],
        l["piece_date"],
        l["reference"],
        l["compte"],
        l["compte_lib"],
        l["tiers_ref"],
        l["tiers_nom"],
        l["libelle"],
        Centimes(l["debit"]),
        Centimes(l["credit"]),
        l["lettrage"],
        l["date_lettrage"],
        (
            Centimes(l["montant_devise"])
            if l["montant_devise"] is not None
            else None
        ),
        l["devise"],
        l["echeance"],
        l["etat"],
        l["type_piece"],
        l["ligne_id"],
        l["ecriture_id"],
        l["tiers_id"],
        str(l["modifie_le"] or ""),
    ]


def generer_xlsx(
    chemin, lignes=None, comptes=None, journaux=None, tiers=None, factures=None
):
    """Classeur xlsx des objets fournis (None = feuille absente)."""
    feuilles = []
    if lignes is not None:
        feuilles.append(
            ("Ecritures", ENTETES_LIGNES, (_ligne_xlsx(l) for l in lignes))
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


def _csv(entetes, lignes):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(entetes)
    w.writerows(lignes)
    return "﻿" + buf.getvalue()


def csv_comptes(comptes):
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


def csv_journaux(journaux):
    return _csv(
        ["code", "name", "type"],
        ([j["code"], j["libelle"], j["type"]] for j in journaux if j["actif"]),
    )


def csv_tiers(tiers):
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


def csv_ecritures(lignes):
    """Écritures one2many : la 1re ligne d'une écriture porte l'en-tête.

    Journal par code, compte par code, tiers par identifiant externe du
    csv_tiers (concorde_tiers_<id>). Montants au point, exacts.
    """

    def rangs():
        precedente = None
        for l in lignes:
            entete = l["ecriture_id"] != precedente
            precedente = l["ecriture_id"]
            yield (
                [
                    l["journal_code"],
                    l["date"].isoformat(),
                    l["reference"] or l["ecriture"],
                ]
                if entete
                else ["", "", ""]
            ) + [
                l["compte"],
                l["libelle"],
                "concorde_tiers_%s" % l["tiers_id"] if l["tiers_id"] else "",
                euros_texte(l["debit"]),
                euros_texte(l["credit"]),
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


def generer_csv(dossier, lignes=None, comptes=None, journaux=None, tiers=None):
    """Écrit les CSV d'import Odoo dans <dossier>. Retourne {fichier: nb lignes}."""
    os.makedirs(dossier, exist_ok=True)
    produits = {}
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
