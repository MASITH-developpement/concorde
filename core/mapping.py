# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""MAPPING DES COMPTES — Quadra -> Odoo.

Étape no-code du pipeline : applique le fichier de correspondance fourni par
le client (Mapping Quadra Odoo) aux lignes canoniques.

Règles :
- Un compte Quadra sans correspondance = ERREUR BLOQUANTE (aucune création
  implicite : on ne devine jamais un compte comptable).
- Le mapping est injecté par chemin de fichier ou liste de tuples.
- Tolérance Concordance inchangée : le mapping ne touche jamais aux montants.
"""
import json


class ErreurMapping(RuntimeError):
    pass


def charger_mapping(source):
    """Charge un mapping depuis un chemin JSON, une chaîne JSON ou une liste de tuples."""
    if isinstance(source, str) and (source.lstrip().startswith("[") or source.lstrip().startswith("{")):
        rows = json.loads(source)
        return {str(r["quadra"]).strip(): str(r["odoo"]).strip() for r in rows
                if r.get("quadra") and r.get("odoo")}
    if isinstance(source, str):
        with open(source, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return {str(r["quadra"]).strip(): str(r["odoo"]).strip() for r in rows
                if r.get("quadra") and r.get("odoo")}
    if isinstance(source, (list, tuple)):
        return {str(q).strip(): str(o).strip() for q, o in source}
    raise ErreurMapping("Source de mapping non supportée (JSON, chemin, tuples).")


def mapper_comptes(donnees, mapping=None):
    """Étape pipeline : mappe les comptes Quadra vers Odoo sur toutes les lignes."""
    if mapping is None:
        raise ErreurMapping("Aucun mapping fourni (fichier Mapping Quadra Odoo requis).")
    if isinstance(mapping, (str, list, tuple)):
        mapping = charger_mapping(mapping)

    if isinstance(donnees, dict):
        canon = donnees.get("canon") or donnees.get("resultat", {}).get("canon")
    else:
        canon = donnees
    if canon is None:
        raise ErreurMapping("Aucun journal canonique à mapper.")

    inconnus = {}
    for l in canon.lignes:
        cible = mapping.get(l.compte)
        if cible is None:
            inconnus[l.compte] = inconnus.get(l.compte, 0) + 1
        else:
            l.compte = cible
    if inconnus:
        detail = ", ".join("%s (x%s)" % (c, n) for c, n in sorted(inconnus.items()))
        raise ErreurMapping(
            "Comptes Quadra absents du mapping Odoo — aucun compte deviné : %s" % detail)
    return {"nb_lignes": len(canon), "nb_mappees": len(canon),
            "inconnus": 0, "canon": canon}
