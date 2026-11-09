#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Liaison AzalPlus (ADR-0015) : vérifier, puis émettre une mission.

  python3 -m scripts.concorde_azalplus verifier
  python3 -m scripts.concorde_azalplus emettre <transfert> <destination>

`verifier` ne crée rien : il dit l'état des verrous, si la clé d'API
répond, et si chaque prestation réglée existe au catalogue d'AzalPlus
(avec le prix qu'AzalPlus lui donne).

`emettre` rejoue la demande pour un transfert déjà abouti — utile quand
AzalPlus était injoignable, ou quand le SIREN du client vient d'y être
renseigné. Une mission déjà émise ne l'est pas deux fois.
"""

import argparse
import sys

from core.azalplus_documents import (
    CHEMIN_REGLAGES_AZALPLUS,
    EmetteurAzalPlus,
    ErreurAzalPlusDocuments,
    emetteur_azalplus,
    reglages_azalplus,
)
from core.connecteurs.base import ErreurConnexion
from core.connecteurs.connexions import Annuaire, ErreurAnnuaire
from core.connecteurs.secrets import ErreurSecrets
from core.connecteurs.transfert import charger, mission_azalplus
from core.journal import Journal
from scripts.outils_cli import premiere_ligne

OUI_NON = {True: "oui", False: "non"}


def _dire(libelle: str, valeur: object) -> None:
    """Une ligne de rapport alignée, pour se relire d'un coup d'oeil."""
    print("  %-22s %s" % (libelle + " ", valeur))


def _verifier(emetteur: EmetteurAzalPlus) -> int:
    """Dit l'état de la liaison sans rien créer ; rend le code de sortie."""
    reglages = emetteur.reglages
    print("Réglages lus dans %s" % CHEMIN_REGLAGES_AZALPLUS)
    _dire("actif", OUI_NON[bool(reglages.get("actif"))])
    _dire("essai à blanc", OUI_NON[emetteur.essai])
    _dire("adresse", reglages.get("adresse") or "(aucune)")
    _dire(
        "société émettrice",
        reglages.get("societe_emettrice") or "(celle du porteur de la clé)",
    )
    _dire("client absent", reglages.get("client_absent"))
    _dire("rapport", reglages.get("rapport"))
    _dire("statut du devis", reglages.get("statut_devis"))
    declencheurs = reglages.get("declencheurs")
    if isinstance(declencheurs, dict):
        for genre in sorted(declencheurs):
            _dire(
                "déclencheur %s" % genre,
                OUI_NON[emetteur.declencheur_ouvert(genre)],
            )
    appel = emetteur.appel()
    lus = appel.requete("GET", "/clients", {"limit": 1})
    print("AzalPlus répond : la clé d'API est acceptée.")
    if not isinstance(lus, (dict, list)):
        print("Réponse inattendue d'AzalPlus.", file=sys.stderr)
        return 1
    prestations = reglages.get("prestations")
    for genre, modeles in sorted(
        (prestations if isinstance(prestations, dict) else {}).items()
    ):
        print("Prestations de « %s » :" % genre)
        if not isinstance(modeles, list) or not modeles:
            print("  aucune — aucun devis ne pourra être créé.")
            continue
        for modele in modeles:
            if not isinstance(modele, dict):
                print("  prestation mal écrite.", file=sys.stderr)
                return 1
            code = str(modele.get("produit") or "")
            produit = emetteur.produit_par_code(appel, code)
            print(
                "  %s « %s » — %s %s HT, TVA %s %% — quantité : %s"
                % (
                    code,
                    produit.get("name"),
                    produit.get("sale_price"),
                    produit.get("unit") or "",
                    produit.get("tax_rate"),
                    modele.get("quantite") or "forfait",
                )
            )
    return 0


def _emettre(
    emetteur: EmetteurAzalPlus,
    annuaire_connexions: Annuaire,
    ident: str,
    destination: str,
) -> int:
    """Rejoue la demande pour un transfert abouti ; code de sortie."""
    journal = Journal()
    etat = charger(ident)
    etat_dest = etat["destinations"].get(destination)
    if etat_dest is None:
        print(
            "Destination inconnue dans le transfert %s : %s"
            % (ident, destination),
            file=sys.stderr,
        )
        return 1
    mission = mission_azalplus(
        annuaire_connexions, etat, destination, etat_dest, journal
    )
    emission = emetteur.emettre(mission, journal)
    if emission["refus"]:
        print("Rien n'est parti : %s" % emission["refus"])
        return 1
    if emission["essai"]:
        print(
            "Essai à blanc — %d ligne(s) de devis pour %s :"
            % (len(emission["lignes"]), emission["client"])
        )
        for ligne in emission["lignes"]:
            print(
                "  %s x %s a %s"
                % (
                    ligne["quantite"],
                    ligne["designation"],
                    ligne["prix_unitaire"],
                )
            )
        return 0
    print(
        "Devis %s créé pour %s ; rapport : %s"
        % (
            emission["devis"],
            emission["client"],
            emission["rapport"] or "(aucun)",
        )
    )
    return 0


def main() -> int:
    """Lit la ligne de commande et lance la sous-commande."""
    analyseur = argparse.ArgumentParser(description=premiere_ligne(__doc__))
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("verifier")
    emettre = sous.add_parser("emettre")
    emettre.add_argument("transfert")
    emettre.add_argument("destination")
    args = analyseur.parse_args()
    try:
        emetteur = emetteur_azalplus(reglages_azalplus())
        if args.commande == "verifier":
            return _verifier(emetteur)
        return _emettre(
            emetteur,
            Annuaire(),
            args.transfert,
            args.destination,
        )
    except (
        ErreurAzalPlusDocuments,
        ErreurAnnuaire,
        ErreurConnexion,
        ErreurSecrets,
        ValueError,
        OSError,
    ) as exc:
        print("Refusé : %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
