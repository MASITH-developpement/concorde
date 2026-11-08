# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Connecteurs et transferts entre logiciels comptables (ADR-0008).

  base        ce que tout connecteur sait faire : tester, lire, écrire, relire
  secrets     jetons et clés, dans /etc/concorde/connecteurs.env (hors git)
  registre    liste des logiciels branchés
  connexions  annuaire des connexions enregistrées (sans aucun secret)
  transfert   procédure en 7 étapes, une destination indépendante des autres
  fec         FEC déposé dans CONCORDE (lecture) ou produit (écriture)

Tous les connecteurs rendent et reçoivent le même `Lot`
(core/migration/lot.py), en centimes : c'est le pivot.
"""
