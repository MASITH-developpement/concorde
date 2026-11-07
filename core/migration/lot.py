# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Le lot de migration : ce qu'un connecteur source a lu, au format commun.

Une ligne (dict) :
  n             numéro de ligne dans la source (pour retrouver l'origine)
  journal_code, journal_lib, ecriture (EcritureNum), date, compte, compte_lib,
  tiers_ref (CompAuxNum), tiers_nom (CompAuxLib), piece (PieceRef), piece_date,
  libelle, debit, credit (centimes int), lettrage, date_lettrage, valid_date,
  montant_devise (centimes ou None), devise,
  analytique    code analytique (vide pour un FEC : la norme n'a pas cette colonne ;
                rempli par les connecteurs Excel/CSV et API qui le fournissent)
  compte_cible  compte Odoo après correspondance (porte 4), sinon None

Une écriture = (journal_code, ecriture) : c'est la clé partout dans le circuit.
"""

from collections import OrderedDict

from ..xlsx_ecrire import euros_texte


def cle_ecriture(l):
    return (l["journal_code"], l["ecriture"])


class Lot:
    def __init__(self, source, lignes):
        self.source = (
            source  # {type, nom, empreinte, encodage, separateur, ...}
        )
        self.lignes = lignes
        self.retirees = []  # [(ligne, motif)] — porte 3 bis
        self.illisibles = []  # [(n, texte, motif)] — porte 1

    def ecritures(self):
        """OrderedDict clé -> [lignes], dans l'ordre du fichier."""
        groupes = OrderedDict()
        for l in self.lignes:
            groupes.setdefault(cle_ecriture(l), []).append(l)
        return groupes

    def totaux(self, lignes=None):
        lignes = self.lignes if lignes is None else lignes
        d = sum(l["debit"] for l in lignes)
        c = sum(l["credit"] for l in lignes)
        return {
            "lignes": len(lignes),
            "ecritures": len({cle_ecriture(l) for l in lignes}),
            "debit": d,
            "credit": c,
        }

    def balance_par_compte(self, cible=False):
        """{compte: solde en centimes} — comptes source, ou cible après correspondance."""
        soldes = {}
        for l in self.lignes:
            k = l.get("compte_cible") if cible else l["compte"]
            soldes[k] = soldes.get(k, 0) + l["debit"] - l["credit"]
        return soldes


def totaux_texte(t):
    return "%s lignes, %s écritures, D %s / C %s" % (
        t["lignes"],
        t["ecritures"],
        euros_texte(t["debit"], ","),
        euros_texte(t["credit"], ","),
    )
