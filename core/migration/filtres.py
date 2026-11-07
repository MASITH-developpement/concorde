# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 3 bis — retirer des écritures du lot avant l'envoi.

Exemples : les à-nouveaux (journal « AN ») de janvier 2025 ; les comptes commençant
par 640 ; un compte analytique ; un tiers ; les libellés contenant « essai »…

Un filtre (dict, ou ligne YAML/JSON) — tous les critères donnés doivent être vrais :
  nom          texte libre, repris dans le rapport
  journaux     codes journal                          (vide = tous)
  comptes      préfixes de comptes, ex. ["640", "6411"] (vide = tous)
  sauf_comptes préfixes de comptes à NE PAS retenir
  analytique   codes (ou préfixes) analytiques — colonne fournie par les exports
               Excel/CSV et les API ; le FEC légal n'en a pas
  tiers        références de tiers (CompAuxNum)
  libelle      texte contenu dans le libellé (sans tenir compte des majuscules)
  piece        préfixe de la référence de pièce
  montant_min, montant_max   bornes en euros sur le montant de la ligne (débit ou crédit)
  du, au       période AAAA-MM-JJ, bornes incluses     (vide = sans limite)
  conditions   conditions libres sur n'importe quelle colonne :
               [{"champ": "piece", "op": "commence_par", "valeur": "AV"}, …]
               op : commence_par, contient, egal, different, vide, non_vide
  portee    « ecritures » (défaut) : retire les écritures ENTIÈRES qui ont au moins
                une ligne qui correspond — l'équilibre est garanti ;
            « lignes » : retire seulement les lignes qui correspondent ; REFUSÉ pour
                toute écriture où ces lignes ne se soldent pas à 0,00 €
                (sinon l'écriture restante serait déséquilibrée) ;
            « lignes_nulles » : retire les lignes à 0,00 € (totaux inchangés).

Garanties : chaque retrait est compté et chiffré au centime ; totaux après = totaux
avant − retraits, vérifié ; les lignes retirées sont gardées (fichier à part).
"""
from datetime import date

from ..canonical import vers_centimes
from ..journal import nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from .lot import cle_ecriture

PORTEES = ("ecritures", "lignes", "lignes_nulles")
OPERATEURS = ("commence_par", "contient", "egal", "different", "vide", "non_vide")
CRITERES = ("journaux", "comptes", "sauf_comptes", "analytique", "tiers", "libelle",
            "piece", "montant_min", "montant_max", "du", "au", "conditions")


class ErreurFiltre(ValueError):
    pass


def normaliser(f):
    """Valide un filtre et convertit ses dates. Lève ErreurFiltre."""
    f = dict(f)
    f.setdefault("nom", "filtre")
    f["portee"] = f.get("portee") or "ecritures"
    if f["portee"] not in PORTEES:
        raise ErreurFiltre("Filtre %r : portée inconnue %r (%s)."
                           % (f["nom"], f["portee"], ", ".join(PORTEES)))
    inconnus = set(f) - set(CRITERES) - {"nom", "portee"}
    if inconnus:
        raise ErreurFiltre("Filtre %r : critère(s) inconnu(s) %s (attendus : %s)."
                           % (f["nom"], ", ".join(sorted(inconnus)), ", ".join(CRITERES)))
    for k in ("journaux", "comptes", "sauf_comptes", "analytique", "tiers"):
        v = f.get(k) or []
        f[k] = [str(x).strip() for x in (v.split(",") if isinstance(v, str) else v)
                if str(x).strip()]
    f["libelle"] = (f.get("libelle") or "").strip().lower()
    f["piece"] = (f.get("piece") or "").strip()
    for k in ("montant_min", "montant_max"):
        v = f.get(k)
        f[k] = vers_centimes(str(v)) if v not in (None, "") else None
    conds = []
    for c in f.get("conditions") or []:
        if c.get("op") not in OPERATEURS:
            raise ErreurFiltre("Filtre %r : opérateur %r inconnu (%s)."
                               % (f["nom"], c.get("op"), ", ".join(OPERATEURS)))
        if not c.get("champ"):
            raise ErreurFiltre("Filtre %r : condition sans champ." % f["nom"])
        conds.append({"champ": c["champ"], "op": c["op"],
                      "valeur": str(c.get("valeur", "")).strip().lower()})
    f["conditions"] = conds
    for k in ("du", "au"):
        v = f.get(k)
        f[k] = date.fromisoformat(str(v)) if v else None
    if f["du"] and f["au"] and f["du"] > f["au"]:
        raise ErreurFiltre("Filtre %r : début après la fin." % f["nom"])
    if f["portee"] == "lignes" and not f["comptes"]:
        raise ErreurFiltre("Filtre %r : la portée « lignes » exige une liste de comptes."
                           % f["nom"])
    if f["portee"] in ("ecritures", "lignes") and not any(
            f[k] for k in CRITERES if k != "sauf_comptes"):
        raise ErreurFiltre("Filtre %r : sans journal, compte ni période, il retirerait "
                           "tout le fichier." % f["nom"])
    return f


def _condition(c, l):
    v = str(l.get(c["champ"]) if l.get(c["champ"]) is not None else "").strip().lower()
    return {"commence_par": lambda: v.startswith(c["valeur"]),
            "contient": lambda: c["valeur"] in v,
            "egal": lambda: v == c["valeur"],
            "different": lambda: v != c["valeur"],
            "vide": lambda: not v,
            "non_vide": lambda: bool(v)}[c["op"]]()


def _ligne_correspond(f, l):
    montant = l["debit"] or l["credit"]
    analytique = l.get("analytique") or ""
    return ((not f["journaux"] or l["journal_code"] in f["journaux"])
            and (not f["comptes"] or l["compte"].startswith(tuple(f["comptes"])))
            and (not f["sauf_comptes"] or not l["compte"].startswith(tuple(f["sauf_comptes"])))
            and (not f["analytique"] or any(analytique.startswith(a) for a in f["analytique"]))
            and (not f["tiers"] or l.get("tiers_ref") in f["tiers"])
            and (not f["libelle"] or f["libelle"] in (l.get("libelle") or "").lower())
            and (not f["piece"] or (l.get("piece") or "").startswith(f["piece"]))
            and (f["montant_min"] is None or montant >= f["montant_min"])
            and (f["montant_max"] is None or montant <= f["montant_max"])
            and (not f["du"] or l["date"] >= f["du"])
            and (not f["au"] or l["date"] <= f["au"])
            and all(_condition(c, l) for c in f["conditions"]))


def appliquer(lot, filtres, journal=None):
    """Applique les filtres dans l'ordre. Modifie le lot. Retourne le rapport des retraits.

    Lève ErreurFiltre si un filtre « lignes » couperait une écriture en deux.
    """
    j = ou_muet(journal)
    avant = lot.totaux()
    rapport = []
    for brut in filtres:
        f = normaliser(brut)
        if f["portee"] == "lignes_nulles":
            retirees = [l for l in lot.lignes if not l["debit"] and not l["credit"]]
        elif f["portee"] == "lignes":
            retirees = [l for l in lot.lignes if _ligne_correspond(f, l)]
            soldes = {}
            for l in retirees:
                soldes[cle_ecriture(l)] = soldes.get(cle_ecriture(l), 0) + l["debit"] - l["credit"]
            coupees = ["%s/%s (%s €)" % (k[0], k[1], euros_texte(s, ","))
                       for k, s in soldes.items() if s]
            if coupees:
                raise ErreurFiltre(
                    "Filtre %r refusé : retirer ces lignes déséquilibrerait %d écriture(s) : %s"
                    "%s. Retirez les écritures entières (portée « ecritures ») ou ajoutez "
                    "la contrepartie au filtre." % (
                        f["nom"], len(coupees), ", ".join(coupees[:5]),
                        "…" if len(coupees) > 5 else ""))
        else:
            cles = {cle_ecriture(l) for l in lot.lignes if _ligne_correspond(f, l)}
            retirees = [l for l in lot.lignes if cle_ecriture(l) in cles]
        ids = {id(l) for l in retirees}
        lot.lignes = [l for l in lot.lignes if id(l) not in ids]
        lot.retirees.extend((l, f["nom"]) for l in retirees)
        t = {"nom": f["nom"], "portee": f["portee"], "lignes": len(retirees),
             "ecritures": len({cle_ecriture(l) for l in retirees}),
             "debit": sum(l["debit"] for l in retirees),
             "credit": sum(l["credit"] for l in retirees)}
        rapport.append(t)
        j.dire("Filtre « %s » : %s écriture(s), %s ligne(s) retirées — D %s / C %s €" % (
            f["nom"], nombre_texte(t["ecritures"]), nombre_texte(t["lignes"]),
            euros_texte(t["debit"], ","), euros_texte(t["credit"], ",")),
            "alerte" if t["lignes"] else "detail")
    apres = lot.totaux()
    retire_d = sum(t["debit"] for t in rapport)
    retire_c = sum(t["credit"] for t in rapport)
    # Garantie : rien ne se perd ni ne se crée.
    assert apres["debit"] == avant["debit"] - retire_d
    assert apres["credit"] == avant["credit"] - retire_c
    if rapport:
        j.dire("Après filtres : %s lignes (avant %s), totaux vérifiés au centime" % (
            nombre_texte(apres["lignes"]), nombre_texte(avant["lignes"])), "ok")
    return {"avant": avant, "apres": apres, "filtres": rapport}
