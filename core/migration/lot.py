# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Le lot de migration : ce qu'un connecteur source a lu, au format commun.

Une ligne (`LigneLot`) :
  n             numéro de ligne dans la source (pour retrouver l'origine)
  journal_code, journal_lib, ecriture (EcritureNum), date, compte,
  compte_lib, tiers_ref (CompAuxNum), tiers_nom (CompAuxLib),
  piece (PieceRef), piece_date, libelle, debit, credit (centimes int),
  lettrage, date_lettrage, valid_date, montant_devise (centimes ou None),
  devise,
  analytique    code analytique (vide pour un FEC : la norme n'a pas cette
                colonne ; rempli par les connecteurs Excel/CSV et API qui
                le fournissent)
  compte_cible  compte Odoo après correspondance (porte 4), sinon None

Une écriture = (journal_code, ecriture) : c'est la clé partout dans le
circuit. Le module porte aussi les routines communes aux portes (clé et
texte d'une écriture, lignes par tiers, annonce des constats).
"""

from collections import OrderedDict
from collections.abc import Iterable
import datetime
from typing import Literal, TypedDict

from ..analyser import Rapport
from ..journal import Journal, nombre_texte
from ..xlsx_ecrire import euros_texte


class LigneLot(TypedDict):
    """Une ligne comptable du lot, au format commun (montants en centimes)."""

    n: int
    journal_code: str
    journal_lib: str
    ecriture: str
    date: datetime.date
    compte: str
    compte_lib: str
    tiers_ref: str
    tiers_nom: str
    piece: str
    piece_date: datetime.date | None
    libelle: str
    debit: int
    credit: int
    lettrage: str
    date_lettrage: datetime.date | None
    valid_date: datetime.date | None
    montant_devise: int | None
    devise: str
    analytique: str
    compte_cible: str | None


class SourceLot(TypedDict):
    """Description de la source lue : type, nom, empreinte, format."""

    type: str
    nom: str
    empreinte: str
    encodage: str
    separateur: str
    lignes_fichier: int


class TotauxLot(TypedDict):
    """Nombre de lignes et d'écritures, totaux débit / crédit (centimes)."""

    lignes: int
    ecritures: int
    debit: int
    credit: int


CleEcriture = tuple[str, str]
CleTotaux = Literal["lignes", "ecritures", "debit", "credit"]
LigneIllisible = tuple[int, str, str]


def cle_ecriture(ligne: LigneLot) -> CleEcriture:
    """Clé de l'écriture d'une ligne.

    Rôle : identifier l'écriture à laquelle appartient une ligne.
    Paramètres : ligne — ligne du lot.
    Retour : (journal_code, ecriture).
    Erreurs : aucune.
    Usages : Lot, filtres, export, injection.
    """
    return (ligne["journal_code"], ligne["ecriture"])


def cle_texte(cle: CleEcriture) -> str:
    """Clé d'écriture lisible.

    Rôle : écrire une clé d'écriture dans un message ou un rapport.
    Paramètres : cle — (journal_code, ecriture).
    Retour : « journal/numéro ».
    Erreurs : aucune.
    Usages : controles, filtres, export, injection.
    """
    return "%s/%s" % cle


def lignes_par_tiers(lignes: Iterable[LigneLot]) -> dict[str, int]:
    """Nombre de lignes par référence de tiers.

    Rôle : compter les lignes portant un tiers, pour comparer une entrée à
    une sortie.
    Paramètres : lignes — lignes du lot (les lignes sans tiers sont
    ignorées).
    Retour : {référence de tiers: nombre de lignes}.
    Erreurs : aucune.
    Usages : export.comparer, injection.relire.
    """
    compte_par_tiers: dict[str, int] = {}
    for ligne in lignes:
        if ligne["tiers_ref"]:
            compte_par_tiers[ligne["tiers_ref"]] = (
                compte_par_tiers.get(ligne["tiers_ref"], 0) + 1
            )
    return compte_par_tiers


def annoncer_constats(rapport: Rapport, journal: Journal) -> None:
    """Écrit chaque constat d'un rapport dans le journal.

    Rôle : annoncer les constats d'une porte (« message : nombre »).
    Paramètres : rapport — Rapport dont les constats sont annoncés ;
    journal — journal de la migration.
    Retour : aucun.
    Erreurs : aucune.
    Usages : controles.controler, export.exporter, injection.relire.
    Un constat BLOQUANT est annoncé en erreur, les autres en alerte.
    """
    for constat in rapport.constats:
        niveau = "erreur" if constat["niveau"] == "BLOQUANT" else "alerte"
        journal.dire(
            "%s : %s" % (constat["message"], nombre_texte(constat["nombre"])),
            niveau,
        )


class Lot:
    """Lot de migration : source, lignes, lignes retirées et illisibles."""

    def __init__(self, source: SourceLot, lignes: list[LigneLot]) -> None:
        """Crée le lot à partir de la source décrite et des lignes lues."""
        self.source = source
        self.lignes = lignes
        self.retirees: list[tuple[LigneLot, object]] = []  # porte 3 bis
        self.illisibles: list[LigneIllisible] = []  # porte 1

    def ecritures(self) -> "OrderedDict[CleEcriture, list[LigneLot]]":
        """OrderedDict clé -> [lignes], dans l'ordre du fichier."""
        groupes: OrderedDict[CleEcriture, list[LigneLot]] = OrderedDict()
        for ligne in self.lignes:
            groupes.setdefault(cle_ecriture(ligne), []).append(ligne)
        return groupes

    def totaux(self, lignes: list[LigneLot] | None = None) -> TotauxLot:
        """Totaux des lignes données (par défaut : toutes celles du lot)."""
        lignes = self.lignes if lignes is None else lignes
        return {
            "lignes": len(lignes),
            "ecritures": len({cle_ecriture(ligne) for ligne in lignes}),
            "debit": sum(ligne["debit"] for ligne in lignes),
            "credit": sum(ligne["credit"] for ligne in lignes),
        }

    def balance_par_compte(self, cible: bool = False) -> dict[str | None, int]:
        """{compte: solde en centimes} — comptes source, ou cibles.

        Avec `cible`, les comptes Odoo après correspondance (None si la
        ligne n'a pas de compte cible).
        """
        soldes: dict[str | None, int] = {}
        for ligne in self.lignes:
            compte = ligne["compte_cible"] if cible else ligne["compte"]
            soldes[compte] = (
                soldes.get(compte, 0) + ligne["debit"] - ligne["credit"]
            )
        return soldes


def totaux_texte(totaux: TotauxLot) -> str:
    """Totaux d'un lot en texte : lignes, écritures, débit et crédit."""
    return "%s lignes, %s écritures, D %s / C %s" % (
        totaux["lignes"],
        totaux["ecritures"],
        euros_texte(totaux["debit"], ","),
        euros_texte(totaux["credit"], ","),
    )
