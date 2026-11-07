# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Migration d'un ERP vers Odoo 17 (ADR-0004).

lot.py           le lot : lignes au format commun (centimes), problèmes, retraits
connecteur_fec   porte 1 — lecture stricte d'un FEC (tiers et lettrage compris)
controles        porte 3 — batterie de contrôles de migration
filtres          porte 3 bis — retrait d'écritures (ex. à-nouveaux « AN » sur une période)
correspondance   porte 4 — table des comptes arbitrée, comptes « à arbitrer »
export           porte 5 — FEC et CSV de contrôle, conformité entrée = sortie au centime
"""
