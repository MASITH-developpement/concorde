# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Actions de la passerelle Odoo 17, communes à la ligne de commande et à l'interface.

  telecharger(source, ...)  -> liste de produits (fichiers + résumé + alertes)
  analyser_source(source, ...) -> rapport d'analyse (dict)

Les fonctions ne lisent ni n'écrivent rien d'autre que ce qu'on leur donne :
une source (core/odoo_source.py) et un dossier de sortie.
"""

import os
from datetime import date

from .analyser import analyser
from .comptes import alertes_balance
from .journal import nombre_texte, ou_muet
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
    """Relit les lignes à la demande : SQL = nouvelle requête en flux ;
    XML-RPC = lecture unique mise en cache (l'API est lente)."""

    def __init__(self, source, debut, fin, etats):
        self.source, self.debut, self.fin, self.etats = (
            source,
            debut,
            fin,
            etats,
        )
        self._cache = None

    def lignes(self):
        if self.source.nature == "sql":
            return self.source.lignes(self.debut, self.fin, self.etats)
        if self._cache is None:
            self._cache = self.source.lignes(self.debut, self.fin, self.etats)
        return iter(self._cache)


def telecharger(
    source,
    dossier,
    formats=("xlsx",),
    objets=OBJETS,
    du=None,
    au=None,
    brouillons=False,
    separateur="|",
    encodage="iso-8859-15",
    guardian=None,
    journal=None,
):
    """Produit les fichiers demandés dans `dossier`.

    Retourne une liste de dicts : {format, fichiers: [chemins], resume, alertes: [..]}.
    Lève ErreurFec si le FEC est refusé (aucun fichier FEC n'est alors produit).
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
    objets = set(objets)
    os.makedirs(dossier, exist_ok=True)
    produits = []
    charges = {}

    def charger(nom):
        if nom not in objets:
            return None
        if nom not in charges:
            charges[nom] = {
                "comptes": source.comptes,
                "journaux": source.journaux,
                "tiers": source.tiers,
                "factures": lambda: source.factures(du, au),
            }[nom]()
            j.dire(
                "%s : %s lus"
                % (nom.capitalize(), nombre_texte(len(charges[nom]))),
                "detail",
            )
        return charges[nom]

    def tracer(etape, detail):
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
        alertes = []
        if r["caracteres_remplaces"]:
            j.dire(
                "%d caractère(s) impossibles en %s remplacés par « ? »"
                % (r["caracteres_remplaces"], r["encodage"]),
                "alerte",
            )
            alertes.append(
                "%d caractère(s) non représentable(s) en %s remplacé(s) par « ? »"
                % (r["caracteres_remplaces"], r["encodage"])
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
                lignes=lecteur.lignes() if "ecritures" in objets else None,
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
                lignes=lecteur.lignes() if "ecritures" in objets else None,
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
    source, du=None, au=None, validees=False, guardian=None, journal=None
):
    """Analyse complète d'une base (écritures, tiers, balance).

    Retourne le rapport (dict, listes complètes). Le journal raconte chaque étape.
    """
    j = ou_muet(journal)
    etats = ("posted",) if validees else ("posted", "draft")
    societe = source.societe_info()
    j.dire(
        "Société %s — devise %s, SIREN %s"
        % (
            societe["nom"],
            societe["devise"],
            societe["siren"] or "non renseigné",
        )
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
            societe="%s (%s, base %s)"
            % (societe["nom"], societe["devise"], source.base),
        )
        e.conclure(
            "%s écritures contrôlées"
            % nombre_texte(rapport.infos["ecritures"])
        )
    _raconter_constats(j, rapport.constats)
    with j.etape("Balance et anomalies par compte") as e:
        bal, alertes_comptes = alertes_balance(
            source.balance(du, au), source.balance_tiers(du, au), j
        )
        e.conclure(
            "%s comptes mouvementés"
            % nombre_texte(bal.infos["comptes_mouvementes"])
        )
    for c in bal.constats:
        c["origine"] = (
            "balance"  # même alerte que la surveillance : pas de doublon
        )
    rapport.constats.extend(bal.constats)
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


def _raconter_constats(j, constats):
    for c in constats:
        niveau = {"BLOQUANT": "erreur", "ALERTE": "alerte"}.get(
            c["niveau"], "detail"
        )
        j.dire("%s : %s" % (c["message"], nombre_texte(c["nombre"])), niveau)
