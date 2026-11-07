# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Vérifier, analyser et comparer deux bases Odoo 17 sur une période — LECTURE SEULE.

Pour chaque base (A et B) : vérification (équilibre, analytique orpheline) et analyse
complète (core/passerelle.analyser_source). Puis comparaison :

  1. totaux (lignes, écritures, débit, crédit) ;
  2. soldes par compte, par journal, par tiers (client / fournisseur) ;
  3. écriture par écriture. Rapprochement : d'abord par (journal, numéro de pièce) ;
     pour les brouillons « / » et le reste, par contenu (journal, date, référence, total).
     Classes : identique, différente (détail : date, référence, comptes, montants, tiers,
     libellés, lettrage), « analytique seule », seulement dans A, seulement dans B ;
  4. analytique : répartitions différentes, comptes analytiques disparus (« #id »).

Option `date_copie` (B est une copie de A faite à cette date, ou l'inverse) : chaque
écriture différente est marquée selon le côté modifié après la copie — c'est la base de
l'alignement prod / test (ADR-0006) : modifiée d'un seul côté = application possible,
modifiée des deux côtés = CONFLIT.

Rien n'est écrit dans aucune base. Montants en centimes.
"""
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from .analyser import Rapport
from .comptes import solde_texte
from .journal import nombre_texte, ou_muet
from .xlsx_ecrire import Centimes, ecrire_xlsx, euros_texte

EXEMPLES = 30


def _regrouper(lignes):
    """{ecriture_id: {entete, lignes}} dans l'ordre de lecture."""
    ecr = OrderedDict()
    for l in lignes:
        e = ecr.get(l["ecriture_id"])
        if e is None:
            e = ecr[l["ecriture_id"]] = {
                "id": l["ecriture_id"], "journal": l["journal_code"], "numero": l["ecriture"],
                "date": l["date"], "reference": l["reference"], "etat": l["etat"],
                "modifie_le": str(l.get("modifie_le") or ""), "lignes": []}
        e["lignes"].append(l)
        if str(l.get("modifie_le") or "") > e["modifie_le"]:
            e["modifie_le"] = str(l.get("modifie_le") or "")
    for e in ecr.values():
        e["total"] = sum(l["debit"] for l in e["lignes"])
    return ecr


def _tiers(l):
    return l["tiers_ref"] or (l["tiers_nom"] or "").strip().upper()


def _sig_ligne(l, analytique=True):
    s = (l["compte"], _tiers(l), l["debit"], l["credit"], (l["libelle"] or "").strip(),
         bool(l["lettrage"]))
    return s + ((l.get("analytique") or "",) if analytique else ())


def _cle_contenu(e):
    return (e["journal"], e["date"], (e["reference"] or "").strip(), e["total"])


def rapprocher(ea, eb):
    """Couples (a, b) d'écritures, et listes des orphelines de chaque côté."""
    par_num_b = defaultdict(list)
    for e in eb.values():
        if e["numero"] not in ("", "/"):
            par_num_b[(e["journal"], e["numero"])].append(e)
    couples, reste_a, pris_b = [], [], set()
    for e in ea.values():
        cands = [x for x in par_num_b.get((e["journal"], e["numero"]), []) if x["id"] not in pris_b]
        if e["numero"] not in ("", "/") and cands:
            couples.append((e, cands[0]))
            pris_b.add(cands[0]["id"])
        else:
            reste_a.append(e)
    par_contenu_b = defaultdict(list)
    for e in eb.values():
        if e["id"] not in pris_b:
            par_contenu_b[_cle_contenu(e)].append(e)
    seul_a = []
    for e in reste_a:
        cands = par_contenu_b.get(_cle_contenu(e))
        if cands:
            b = cands.pop(0)
            couples.append((e, b))
            pris_b.add(b["id"])
        else:
            seul_a.append(e)
    seul_b = [e for e in eb.values() if e["id"] not in pris_b]
    return couples, seul_a, seul_b


def differences(a, b):
    """Liste lisible des différences entre deux écritures rapprochées ('' = identiques)."""
    diffs = []
    if a["date"] != b["date"]:
        diffs.append("date %s → %s" % (a["date"], b["date"]))
    if (a["reference"] or "") != (b["reference"] or ""):
        diffs.append("référence « %s » → « %s »" % (a["reference"], b["reference"]))
    if a["etat"] != b["etat"]:
        diffs.append("état %s → %s" % (a["etat"], b["etat"]))
    sa = Counter(_sig_ligne(l) for l in a["lignes"])
    sb = Counter(_sig_ligne(l) for l in b["lignes"])
    if sa != sb:
        sans_an_a = Counter(_sig_ligne(l, False) for l in a["lignes"])
        sans_an_b = Counter(_sig_ligne(l, False) for l in b["lignes"])
        if sans_an_a == sans_an_b:
            diffs.append("analytique seule")
        else:
            moins, plus = sans_an_a - sans_an_b, sans_an_b - sans_an_a
            for s in list(moins)[:3]:
                diffs.append("ligne A seulement : %s %s %s/%s « %s »" % (
                    s[0], s[1], euros_texte(s[2], ","), euros_texte(s[3], ","), s[4][:40]))
            for s in list(plus)[:3]:
                diffs.append("ligne B seulement : %s %s %s/%s « %s »" % (
                    s[0], s[1], euros_texte(s[2], ","), euros_texte(s[3], ","), s[4][:40]))
    return diffs


def _agreger(lignes, cle):
    d = defaultdict(lambda: [0, 0, 0])
    for l in lignes:
        k = cle(l)
        if k is None:
            continue
        d[k][0] += l["debit"]
        d[k][1] += l["credit"]
        d[k][2] += 1
    return d


def comparer(lignes_a, lignes_b, nom_a="A", nom_b="B", date_copie=None, journal=None):
    """Compare deux listes de lignes (format des sources). Retourne (Rapport, détails)."""
    j = ou_muet(journal)
    r = Rapport()
    if date_copie:   # même forme que write_date d'Odoo : « AAAA-MM-JJ HH:MM:SS » (UTC)
        date_copie = str(date_copie).replace("T", " ")[:19]
    ea, eb = _regrouper(lignes_a), _regrouper(lignes_b)

    # 1. Totaux
    for nom, lignes, ecr in ((nom_a, lignes_a, ea), (nom_b, lignes_b, eb)):
        r.info("totaux_" + nom, {"lignes": len(lignes), "ecritures": len(ecr),
                                 "debit": sum(l["debit"] for l in lignes),
                                 "credit": sum(l["credit"] for l in lignes)})
    ta, tb = r.infos["totaux_" + nom_a], r.infos["totaux_" + nom_b]
    j.dire("Totaux — %s : %s écritures, D %s | %s : %s écritures, D %s" % (
        nom_a, nombre_texte(ta["ecritures"]), euros_texte(ta["debit"], ","),
        nom_b, nombre_texte(tb["ecritures"]), euros_texte(tb["debit"], ",")),
        "ok" if ta == tb else "alerte")

    # 2. Soldes par compte, journal, tiers
    details = {}
    for code, nom_dim, cle in (
            ("CMP_ECART_COMPTE", "comptes", lambda l: l["compte"]),
            ("CMP_ECART_JOURNAL", "journaux", lambda l: l["journal_code"]),
            ("CMP_ECART_TIERS", "tiers", lambda l: (l["compte"], _tiers(l))
             if l["compte_type"] in ("asset_receivable", "liability_payable") else None)):
        da, db = _agreger(lignes_a, cle), _agreger(lignes_b, cle)
        ecarts = []
        for k in sorted(set(da) | set(db), key=str):
            sa_ = da[k][0] - da[k][1] if k in da else 0
            sb_ = db[k][0] - db[k][1] if k in db else 0
            if sa_ != sb_ or (k in da) != (k in db):
                ecarts.append({"cle": " / ".join(k) if isinstance(k, tuple) else k,
                               "solde_a": sa_, "solde_b": sb_, "ecart": sb_ - sa_,
                               "lignes_a": da[k][2] if k in da else 0,
                               "lignes_b": db[k][2] if k in db else 0})
        details[nom_dim] = ecarts
        r.constat("ALERTE", code, "Soldes différents (%s)" % nom_dim,
                  ["%s : %s → %s (écart %s €)" % (
                      e["cle"], solde_texte({"debit": max(e["solde_a"], 0),
                                             "credit": max(-e["solde_a"], 0)}),
                      solde_texte({"debit": max(e["solde_b"], 0), "credit": max(-e["solde_b"], 0)}),
                      euros_texte(e["ecart"], ",")) for e in ecarts])
        j.dire("Soldes par %s : %s écart(s)" % (
            {"comptes": "compte", "journaux": "journal", "tiers": "tiers"}[nom_dim],
            nombre_texte(len(ecarts))), "alerte" if ecarts else "ok")

    # 3. Écriture par écriture
    couples, seul_a, seul_b = rapprocher(ea, eb)
    identiques, differentes, analytique_seule, conflits = 0, [], [], []
    for a, b in couples:
        diffs = differences(a, b)
        if not diffs:
            identiques += 1
            continue
        cote = ""
        if date_copie:
            ma, mb = a["modifie_le"] > date_copie, b["modifie_le"] > date_copie
            cote = {(True, True): "CONFLIT : modifiée des deux côtés après la copie",
                    (True, False): "modifiée dans %s après la copie" % nom_a,
                    (False, True): "modifiée dans %s après la copie" % nom_b,
                    (False, False): "aucune modification datée après la copie"}[(ma, mb)]
        ligne = {"journal": a["journal"], "numero_a": a["numero"], "numero_b": b["numero"],
                 "date": a["date"], "total_a": a["total"], "total_b": b["total"],
                 "differences": diffs, "cote": cote}
        if diffs == ["analytique seule"]:
            analytique_seule.append(ligne)
        else:
            differentes.append(ligne)
        if cote.startswith("CONFLIT"):
            conflits.append(ligne)
    details.update({"differentes": differentes, "analytique_seule": analytique_seule,
                    "seul_a": seul_a, "seul_b": seul_b, "conflits": conflits})
    r.info("ecritures_rapprochees", len(couples))
    r.info("ecritures_identiques", identiques)

    def lib(x):
        return "%s %s du %s (%s €)" % (x["journal"], x.get("numero_a") or x.get("numero"),
                                       x["date"], euros_texte(x.get("total_a", x.get("total", 0)),
                                                              ","))
    r.constat("ALERTE", "CMP_ECRITURE_DIFFERENTE", "Écritures différentes",
              ["%s : %s%s" % (lib(x), " ; ".join(x["differences"][:3]),
                              " — " + x["cote"] if x["cote"] else "") for x in differentes])
    r.constat("INFO", "CMP_ANALYTIQUE_SEULE", "Écritures dont seule l'analytique diffère",
              ["%s%s" % (lib(x), " — " + x["cote"] if x["cote"] else "")
               for x in analytique_seule])
    r.constat("ALERTE", "CMP_SEULEMENT_A", "Écritures présentes seulement dans %s" % nom_a,
              [lib(dict(x, numero_a=x["numero"])) for x in seul_a])
    r.constat("ALERTE", "CMP_SEULEMENT_B", "Écritures présentes seulement dans %s" % nom_b,
              [lib(dict(x, numero_a=x["numero"])) for x in seul_b])
    if date_copie:
        r.constat("BLOQUANT", "CMP_CONFLIT",
                  "Conflits : écritures modifiées dans les deux bases après la copie",
                  [lib(x) for x in conflits])
    j.dire("Écritures : %s rapprochées, %s identiques, %s différentes, %s analytique seule, "
           "%s seulement dans %s, %s seulement dans %s" % (
               nombre_texte(len(couples)), nombre_texte(identiques),
               nombre_texte(len(differentes)), nombre_texte(len(analytique_seule)),
               nombre_texte(len(seul_a)), nom_a, nombre_texte(len(seul_b)), nom_b),
           "ok" if not (differentes or seul_a or seul_b) else "alerte")
    return r, details


def verifier(lignes, nom):
    """Vérifications propres à une base : équilibre et analytique orpheline."""
    r = Rapport()
    debit = sum(l["debit"] for l in lignes)
    credit = sum(l["credit"] for l in lignes)
    if debit != credit:
        r.constat("BLOQUANT", "CMP_BASE_DESEQUILIBREE", "Base %s déséquilibrée" % nom,
                  ["D %s / C %s" % (euros_texte(debit, ","), euros_texte(credit, ","))])
    orphelins = sorted({l["analytique"] for l in lignes if "#" in (l.get("analytique") or "")})
    r.constat("ALERTE", "CMP_ANALYTIQUE_ORPHELINE",
              "%s : répartitions vers des comptes analytiques disparus" % nom,
              orphelins[:EXEMPLES])
    return r


def ecrire_classeur(chemin, nom_a, nom_b, rapport, details):
    """Classeur xlsx : synthèse et une feuille par type d'écart."""
    i = rapport.infos
    synth = [["Constat", "Niveau", "Nombre"]]
    synth += [[c["message"], c["niveau"], c["nombre"]] for c in rapport.constats]
    feuilles = [("Synthese", ("Élément", nom_a, nom_b), [
        ["Écritures", i["totaux_" + nom_a]["ecritures"], i["totaux_" + nom_b]["ecritures"]],
        ["Lignes", i["totaux_" + nom_a]["lignes"], i["totaux_" + nom_b]["lignes"]],
        ["Débit", Centimes(i["totaux_" + nom_a]["debit"]), Centimes(i["totaux_" + nom_b]["debit"])],
        ["Crédit", Centimes(i["totaux_" + nom_a]["credit"]),
         Centimes(i["totaux_" + nom_b]["credit"])],
        ["Écritures rapprochées", i.get("ecritures_rapprochees"), ""],
        ["Écritures identiques", i.get("ecritures_identiques"), ""]] + [[""] * 3] + synth)]
    for nom_f, cle in (("Ecarts comptes", "comptes"), ("Ecarts journaux", "journaux"),
                       ("Ecarts tiers", "tiers")):
        feuilles.append((nom_f, ("Clé", "Solde " + nom_a, "Solde " + nom_b, "Écart (B - A)",
                                 "Lignes " + nom_a, "Lignes " + nom_b),
                         [[e["cle"], Centimes(e["solde_a"]), Centimes(e["solde_b"]),
                           Centimes(e["ecart"]), e["lignes_a"], e["lignes_b"]]
                          for e in details[cle]]))
    for nom_f, cle in (("Ecritures differentes", "differentes"),
                       ("Analytique seule", "analytique_seule"), ("Conflits", "conflits")):
        feuilles.append((nom_f, ("Journal", "N° " + nom_a, "N° " + nom_b, "Date",
                                 "Total " + nom_a, "Total " + nom_b, "Différences", "Côté modifié"),
                         [[x["journal"], x["numero_a"], x["numero_b"], x["date"],
                           Centimes(x["total_a"]), Centimes(x["total_b"]),
                           " ; ".join(x["differences"]), x["cote"]] for x in details[cle]]))
    for nom_f, cle in (("Seulement " + nom_a, "seul_a"), ("Seulement " + nom_b, "seul_b")):
        feuilles.append((nom_f[:31], ("Journal", "N°", "Date", "Référence", "Total", "État",
                                      "id Odoo"),
                         [[x["journal"], x["numero"], x["date"], x["reference"],
                           Centimes(x["total"]), x["etat"], x["id"]] for x in details[cle]]))
    return ecrire_xlsx(chemin, feuilles)


def filtrer_lignes(lignes, comptes=None, analytiques=None):
    """Garde les lignes sur les comptes comptables choisis ET (si donnés) touchant au moins un
    des comptes analytiques choisis. Sans filtre : toutes les lignes."""
    comptes = set(comptes or ())
    analytiques = set(analytiques or ())
    return [l for l in lignes
            if (not comptes or l["compte"] in comptes)
            and (not analytiques or analytiques & set(l.get("analytique_comptes") or ()))]


def comparer_bases(source_a, source_b, du=None, au=None, etats=("posted",), date_copie=None,
                   dossier=None, journal=None, comptes=None, analytiques=None):
    """Vérifie, analyse et compare deux bases (sources SQL ou XML-RPC). Retourne un dict.

    comptes / analytiques : listes de comptes (codes) et de comptes analytiques (code ou nom)
    à comparer ; la vérification et l'analyse de chaque base restent complètes.
    """
    from .passerelle import analyser_source
    j = ou_muet(journal)
    nom_a, nom_b = "A", "B"
    res = {"base_a": source_a.base, "base_b": source_b.base, "du": du, "au": au,
           "etats": list(etats), "date_copie": date_copie,
           "filtre_comptes": sorted(comptes or ()), "filtre_analytiques": sorted(analytiques or ())}
    lignes = {}
    for nom, src in ((nom_a, source_a), (nom_b, source_b)):
        with j.etape("Base %s (%s) : lecture des écritures de la période" % (nom, src.base)) as e:
            lignes[nom] = list(src.lignes(du, au, etats))
            e.conclure("%s lignes" % nombre_texte(len(lignes[nom])))
        with j.etape("Base %s : vérification et analyse" % nom) as e:
            v = verifier(lignes[nom], nom)
            a = analyser_source(src, du, au, etats == ("posted",))
            res["analyse_" + nom] = {
                "statut": a["statut"], "synthese": a["synthese"],
                "constats": [{k: c[k] for k in ("niveau", "code", "message", "nombre",
                                                "exemples")}
                             for c in v.en_dict(complet=False)["constats"] + a["constats"]]}
            e.conclure("%s — %d bloquant, %d alerte(s)" % (
                a["statut"], a["synthese"]["BLOQUANT"], a["synthese"]["ALERTE"]))
    if comptes or analytiques:
        for nom in (nom_a, nom_b):
            avant = len(lignes[nom])
            lignes[nom] = filtrer_lignes(lignes[nom], comptes, analytiques)
            j.dire("Base %s : filtre %s%s%s — %s lignes gardées sur %s" % (
                nom, "%d compte(s)" % len(comptes) if comptes else "",
                " et " if comptes and analytiques else "",
                "%d compte(s) analytique(s)" % len(analytiques) if analytiques else "",
                nombre_texte(len(lignes[nom])), nombre_texte(avant)), "detail")
    with j.etape("Comparaison %s ↔ %s" % (source_a.base, source_b.base)) as e:
        r, details = comparer(lignes[nom_a], lignes[nom_b], nom_a, nom_b, date_copie, j)
        if comptes or analytiques:
            r.info("filtres", {"comptes": sorted(comptes or ()),
                               "analytiques": sorted(analytiques or ())})
        d = r.en_dict(complet=False)
        e.conclure("%s — %d alerte(s)" % (d["statut"], d["synthese"]["ALERTE"]))
    res["comparaison"] = d
    res["details_nombre"] = {k: len(v) for k, v in details.items()}
    if dossier:
        import os
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, "comparaison_%s_%s.xlsx" % (source_a.base, source_b.base))
        ecrire_classeur(chemin, nom_a, nom_b, r, details)
        res["fichier"] = chemin
        j.dire("Détail complet : %s" % os.path.basename(chemin), "ok")
    res["date"] = datetime.now().isoformat(timespec="seconds")
    return res
