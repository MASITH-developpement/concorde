# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Porte 6 — envoi du lot dans la BASE DE TEST du serveur, puis relecture (ADR-0004).

Cible verrouillée : uniquement la base de test configurée (CONCORDE_TEST_URL / _BASE /
_USER / _MDP, adresse locale). Les portes 7 et 8 (base client) viendront ensuite.

Déroulé :
  1. connexion à la base de test (API XML-RPC d'Odoo — jamais de SQL pour écrire) ;
  2. préparation : comptes, journaux et tiers manquants créés (codes et libellés LUS
     dans le FEC ; type de compte par les règles du PCG ci-dessous, jamais deviné) ;
  3. écritures créées EN BROUILLON par paquets, référence unique
     « CONCORDE/<lot>/<journal>/<n°> » : une écriture déjà présente n'est jamais renvoyée ;
  4. validation (action_post) ;
  5. lettrage refait par l'API (reconcile), lettre par lettre ;
  6. relecture SQL de la base de test et comparaison au lot, au centime :
     lignes, écritures, totaux, solde par compte, lignes par tiers, lettres. 0 écart exigé.

Toute erreur d'Odoo est gardée avec l'écriture en cause (jamais muet).
"""
import os
import threading
import time
import xmlrpc.client
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from ..analyser import Rapport
from ..journal import nombre_texte, ou_muet
from ..xlsx_ecrire import euros_texte
from .lot import cle_ecriture

TAILLE_PAQUET = 100

# Vitesse (mesurée le 06/11/2026) : comme l'import natif d'Odoo, on coupe le suivi « chatter »
# pendant l'envoi (pas de message « écriture créée / validée » par écriture) : -15 %.
# Parallélisme : DÉSACTIVÉ par défaut. Mesuré : plus lent et source d'erreurs de validation
# (Odoo sérialise la numérotation et le recalcul des soldes). Réglable pour essai :
# CONCORDE_INJECTION_PARALLELES.
CONTEXTE_IMPORT = {"tracking_disable": True, "mail_create_nolog": True,
                   "mail_create_nosubscribe": True, "mail_notrack": True}


def _paralleles():
    try:
        return max(1, int(os.environ.get("CONCORDE_INJECTION_PARALLELES", "1")))
    except ValueError:
        return 1


METHODES_AUTORISEES = ("search_read", "read", "search_count", "fields_get", "create",
                       "action_post", "reconcile")


class ErreurInjection(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Type Odoo 17 d'un compte, par les règles du plan comptable général
# ---------------------------------------------------------------------------

def type_compte_pcg(code):
    """Type account.account Odoo 17 d'après le PCG (règles explicites, documentées).

    Jamais « equity_unaffected » : Odoo n'en admet qu'un (résultat de l'exercice).
    """
    c = (code or "").strip()
    regles = (
        (("16", "17"), "liability_non_current"),
        (("1",), "equity"),
        (("28", "29"), "asset_non_current"),
        (("2",), "asset_non_current"),
        (("3",), "asset_current"),
        (("409",), "asset_current"),          # fournisseurs débiteurs (avant « 40 »)
        (("40",), "liability_payable"),
        (("41",), "asset_receivable"),
        (("486",), "asset_prepayments"),
        (("4456", "4458", "46", "47", "48"), "asset_current"),
        (("4",), "liability_current"),
        (("51", "53"), "asset_cash"),
        (("5",), "asset_current"),
        (("68",), "expense_depreciation"),
        (("6",), "expense"),
        (("7",), "income"),
        (("8", "9"), "off_balance"),
    )
    for prefixes, t in regles:
        if c.startswith(prefixes):
            return t
    return "asset_current"


def euros(c):
    return float(Decimal(int(c)) / 100)


# ---------------------------------------------------------------------------
# Client d'écriture, limité à la base de test
# ---------------------------------------------------------------------------

class CibleTest:
    """Client XML-RPC vers la base de test locale. Méthodes limitées (liste blanche)."""

    def __init__(self, url, base, utilisateur, mot_de_passe, proxy_commun=None,
                 proxy_objet=None):
        attendu = os.environ.get("CONCORDE_TEST_BASE")
        if not attendu or base != attendu:
            raise ErreurInjection("Porte 6 : seule la base de test configurée (%r) est "
                                  "autorisée, pas %r." % (attendu, base))
        if proxy_objet is None and not url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ErreurInjection("Porte 6 : la base de test doit être sur ce serveur (%s)." % url)
        self.base, self._mdp, self._url = base, mot_de_passe, url
        self._objet_fixe = proxy_objet          # tests : un faux Odoo partagé
        self._local = threading.local()         # un client XML-RPC par fil (non partageable)
        commun = proxy_commun or xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common",
                                                           allow_none=True)
        self.version = commun.version().get("server_version", "?")
        self.uid = commun.authenticate(base, utilisateur, mot_de_passe, {})
        if not self.uid:
            raise ErreurInjection("Authentification refusée sur la base de test %s." % base)

    def _objet(self):
        if self._objet_fixe is not None:
            return self._objet_fixe
        if not hasattr(self._local, "objet"):
            self._local.objet = xmlrpc.client.ServerProxy(self._url + "/xmlrpc/2/object",
                                                          allow_none=True)
        return self._local.objet

    def appel(self, modele, methode, args, kwargs=None):
        if methode not in METHODES_AUTORISEES:
            raise PermissionError("Méthode %r interdite à la porte 6." % methode)
        kw = dict(kwargs or {})
        kw["context"] = dict(CONTEXTE_IMPORT, **kw.get("context", {}))
        return self._objet().execute_kw(self.base, self.uid, self._mdp, modele, methode, args,
                                        kw)


def en_parallele(fonction, elements, paralleles=None):
    """Applique `fonction` à chaque élément, `paralleles` requêtes à la fois. Ordre conservé."""
    n = paralleles or _paralleles()
    if n <= 1 or len(elements) <= 1:
        return [fonction(e) for e in elements]
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fonction, elements))


def cible_depuis_env():
    return CibleTest(os.environ.get("CONCORDE_TEST_URL", "http://127.0.0.1:8017"),
                     os.environ.get("CONCORDE_TEST_BASE", ""),
                     os.environ.get("CONCORDE_TEST_USER", "admin"),
                     os.environ.get("CONCORDE_TEST_MDP", ""))


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------

def lot_id(lot):
    return lot.source["empreinte"][:10]


def _ref(lid, cle):
    return "CONCORDE/%s/%s/%s" % (lid, cle[0], cle[1])


def _erreur_odoo(exc):
    texte = getattr(exc, "faultString", None) or str(exc)
    lignes = [l for l in texte.strip().splitlines() if l.strip()]
    return lignes[-1][:300] if lignes else type(exc).__name__


def preparer(cible, lot, j):
    """Crée comptes, journaux et tiers manquants. Retourne les tables {code: id}."""
    with j.etape("Préparation : comptes, journaux et tiers de la base de test") as e:
        codes = OrderedDict()
        for l in lot.lignes:
            codes.setdefault(l["compte_cible"], l["compte_lib"])
        comptes = {c["code"]: (c["id"], c["reconcile"]) for c in cible.appel(
            "account.account", "search_read", [[["code", "in", list(codes)]]],
            {"fields": ["code", "reconcile"], "context": {"active_test": False}})}
        a_creer = [c for c in codes if c not in comptes]
        for c in a_creer:
            t = type_compte_pcg(c)
            ident = cible.appel("account.account", "create", [{
                "code": c, "name": codes[c] or c, "account_type": t,
                "reconcile": t in ("asset_receivable", "liability_payable")}])
            comptes[c] = (ident, t in ("asset_receivable", "liability_payable"))
        journaux_lot = OrderedDict()
        for l in lot.lignes:
            journaux_lot.setdefault(l["journal_code"], l["journal_lib"])
        journaux = {jr["code"]: jr["id"] for jr in cible.appel(
            "account.journal", "search_read", [[["code", "in", list(journaux_lot)]]],
            {"fields": ["code"], "context": {"active_test": False}})}
        jr_crees = []
        for code, lib in journaux_lot.items():
            if code not in journaux:
                if len(code) > 5:
                    raise ErreurInjection("Code journal %r trop long pour Odoo 17 (5 caractères "
                                          "au plus) : à faire arbitrer." % code)
                journaux[code] = cible.appel("account.journal", "create", [{
                    "code": code, "name": lib or "Journal %s" % code, "type": "general"}])
                jr_crees.append(code)
        tiers_lot = OrderedDict()
        for l in lot.lignes:
            if l["tiers_ref"]:
                tiers_lot.setdefault(l["tiers_ref"], l["tiers_nom"])
        tiers = {}
        refs = list(tiers_lot)
        for i in range(0, len(refs), 500):
            for p in cible.appel("res.partner", "search_read",
                                 [[["ref", "in", refs[i:i + 500]]]],
                                 {"fields": ["ref"], "context": {"active_test": False}}):
                tiers.setdefault(p["ref"], p["id"])
        t_crees = [r for r in refs if r not in tiers]
        for i in range(0, len(t_crees), 200):
            lot_t = t_crees[i:i + 200]
            ids = cible.appel("res.partner", "create", [[
                {"name": tiers_lot[r] or r, "ref": r, "is_company": True} for r in lot_t]])
            tiers.update(zip(lot_t, ids))
        e.conclure("%s compte(s) créé(s), %s journal(aux) créé(s), %s tiers créé(s)" % (
            nombre_texte(len(a_creer)), nombre_texte(len(jr_crees)), nombre_texte(len(t_crees))))
    if jr_crees:
        j.dire("Journaux créés en type « divers » : %s" % ", ".join(jr_crees), "detail")
    return comptes, journaux, tiers, {"comptes_crees": a_creer, "journaux_crees": jr_crees,
                                      "tiers_crees": len(t_crees)}


def envoyer(cible, lot, j=None):
    """Porte 6 complète. Retourne un dict de résultat (statut, erreurs, relecture...)."""
    j = ou_muet(j)
    debut = time.monotonic()
    lid = lot_id(lot)
    j.dire("Base de test %s (Odoo %s) — lot %s" % (cible.base, cible.version, lid), "info")
    devises = {l["devise"] for l in lot.lignes if l["devise"] and l["devise"] != "EUR"}
    if devises:
        raise ErreurInjection("Lignes en devise (%s) : non gérées à la porte 6 pour l'instant."
                              % ", ".join(sorted(devises)))
    comptes, journaux, tiers, prep = preparer(cible, lot, j)

    ecritures = lot.ecritures()
    refs = {cle: _ref(lid, cle) for cle in ecritures}
    deja = set()
    toutes = list(refs.values())
    for i in range(0, len(toutes), 1000):
        deja |= {m["ref"] for m in cible.appel("account.move", "search_read",
                                               [[["ref", "in", toutes[i:i + 1000]]]],
                                               {"fields": ["ref"]})}
    if deja:
        j.dire("%s écriture(s) déjà présentes (envoi précédent) : elles ne sont pas renvoyées"
               % nombre_texte(len(deja)), "info")

    def payload(cle, lignes):
        return {"move_type": "entry", "journal_id": journaux[cle[0]],
                "date": str(lignes[0]["date"]),
                "ref": refs[cle], "line_ids": [(0, 0, {
                    "account_id": comptes[l["compte_cible"]][0],
                    "partner_id": tiers.get(l["tiers_ref"]) or False,
                    "name": l["libelle"] or l["piece"] or "/",
                    "debit": euros(l["debit"]), "credit": euros(l["credit"])})
                    for l in lignes]}

    a_envoyer = [(cle, ls) for cle, ls in ecritures.items() if refs[cle] not in deja]
    crees, erreurs = {}, []
    n = _paralleles()
    paquets = [a_envoyer[i:i + TAILLE_PAQUET] for i in range(0, len(a_envoyer), TAILLE_PAQUET)]
    avance = {"fait": 0}
    verrou = threading.Lock()

    def creer(paquet):
        """Un paquet -> ([(clé, id)], [erreurs]). Écriture refusée = isolée, une par une."""
        try:
            ids = cible.appel("account.move", "create", [[payload(c, ls) for c, ls in paquet]])
            res, errs = list(zip([c for c, _ in paquet], ids)), []
        except xmlrpc.client.Fault:
            res, errs = [], []
            for c, ls in paquet:
                try:
                    res.append((c, cible.appel("account.move", "create", [payload(c, ls)])))
                except xmlrpc.client.Fault as exc:
                    errs.append({"ecriture": "%s/%s" % c, "etape": "création",
                                 "erreur": _erreur_odoo(exc)})
        with verrou:
            avance["fait"] += len(paquet)
            if avance["fait"] // 1000 != (avance["fait"] - len(paquet)) // 1000:
                j.dire("… %s / %s écritures envoyées" % (
                    nombre_texte(avance["fait"]), nombre_texte(len(a_envoyer))), "detail")
        return res, errs

    with j.etape("Envoi en brouillon : %s écritures, paquets de %d, %d requête(s) à la fois"
                 % (nombre_texte(len(a_envoyer)), TAILLE_PAQUET, n)) as e:
        for res, errs in en_parallele(creer, paquets, n):
            crees.update(res)
            erreurs.extend(errs)
        e.conclure("%s créées, %s en erreur" % (nombre_texte(len(crees)),
                                                nombre_texte(len(erreurs))))

    # Validation : en parallèle PAR JOURNAL (deux validations dans un même journal se
    # disputeraient la numérotation des pièces).
    par_journal = defaultdict(list)
    for c, m in crees.items():
        par_journal[c[0]].append((c, m))

    def valider(liste):
        ok, errs = 0, []
        for i in range(0, len(liste), 200):
            paquet = liste[i:i + 200]
            try:
                cible.appel("account.move", "action_post", [[m for _, m in paquet]])
                ok += len(paquet)
            except xmlrpc.client.Fault:
                for c, m in paquet:
                    try:
                        cible.appel("account.move", "action_post", [[m]])
                        ok += 1
                    except xmlrpc.client.Fault as exc:
                        errs.append({"ecriture": "%s/%s" % c, "etape": "validation",
                                     "erreur": _erreur_odoo(exc)})
        return ok, errs

    with j.etape("Validation des écritures (%d journaux, %d à la fois)"
                 % (len(par_journal), n)) as e:
        # Les plus gros journaux d'abord : la charge se répartit mieux.
        journaux_tries = sorted(par_journal.values(), key=len, reverse=True)
        valides = 0
        for ok, errs in en_parallele(valider, journaux_tries, n):
            valides += ok
            erreurs.extend(errs)
        e.conclure("%s validées" % nombre_texte(valides))

    lettrage = lettrer(cible, lot, crees, comptes, j, erreurs)
    for err in erreurs[:10]:
        j.dire("Erreur Odoo — %s (%s) : %s" % (err["ecriture"], err["etape"], err["erreur"]),
               "erreur")
    if len(erreurs) > 10:
        j.dire("… et %d autre(s) erreur(s) (détail dans le rapport)" % (len(erreurs) - 10),
               "erreur")
    return {"lot": lid, "base": cible.base, "preparation": prep,
            "deja_presentes": len(deja), "creees": len(crees), "erreurs": erreurs,
            "lettrage": lettrage, "duree_s": round(time.monotonic() - debut, 1)}


def lettrer(cible, lot, crees, comptes, j, erreurs):
    """Refait le lettrage du FEC : une lettre = les lignes (compte, tiers, lettre) du lot."""
    groupes = defaultdict(list)
    for l in lot.lignes:
        if l["lettrage"] and cle_ecriture(l) in crees:
            groupes[(l["compte_cible"], l["tiers_ref"], l["lettrage"])].append(l)
    if not groupes:
        return {"lettres": 0, "faites": 0, "ignorees": 0}
    with j.etape("Lettrage : %s lettre(s) à refaire" % nombre_texte(len(groupes))) as e:
        # Lignes Odoo créées, dans l'ordre d'envoi de chaque écriture.
        ids_moves = list(crees.values())
        lignes_odoo = defaultdict(list)
        for i in range(0, len(ids_moves), 500):
            for ml in cible.appel("account.move.line", "search_read",
                                  [[["move_id", "in", ids_moves[i:i + 500]]]],
                                  {"fields": ["move_id", "debit", "credit"], "order": "id"}):
                lignes_odoo[ml["move_id"][0]].append(ml)
        ident = {}
        for cle, lignes in lot.ecritures().items():
            mid = crees.get(cle)
            if mid is None:
                continue
            odoo = lignes_odoo.get(mid, [])
            if len(odoo) != len(lignes):
                continue
            for l, ml in zip(lignes, odoo):
                montants = (round(ml["debit"] * 100), round(ml["credit"] * 100))
                if montants == (l["debit"], l["credit"]):
                    ident[id(l)] = ml["id"]
        tentees = {}
        ignorees = {"ligne_seule": [], "compte_non_lettrable": []}
        for (compte, tiers_ref, lettre), lignes in groupes.items():
            ids = [ident.get(id(l)) for l in lignes]
            nom = "lettre %s sur %s%s" % (lettre, compte, " (%s)" % tiers_ref if tiers_ref else "")
            if len(lignes) < 2:
                ignorees["ligne_seule"].append(nom)
                continue
            if not comptes[compte][1]:
                ignorees["compte_non_lettrable"].append(nom)
                continue
            if None in ids:
                erreurs.append({"ecriture": nom, "etape": "lettrage",
                                "erreur": "lignes non retrouvées dans Odoo après l'envoi"})
                continue
            tentees[nom] = ids

        def lettrer_un(element):
            nom, ids = element
            try:
                cible.appel("account.move.line", "reconcile", [ids])
            except xmlrpc.client.Fault as exc:
                # reconcile() ne renvoie rien : XML-RPC ne sait pas transmettre ce « rien »
                # (allow_none). Le lettrage est fait ; on le VÉRIFIE ci-dessous de toute façon.
                if "cannot marshal None" not in str(exc.faultString):
                    return nom, _erreur_odoo(exc)
            return nom, None

        for nom, err in en_parallele(lettrer_un, list(tentees.items())):
            if err:
                erreurs.append({"ecriture": nom, "etape": "lettrage", "erreur": err})
                del tentees[nom]
        # Vérification dans la base : chaque lettre tentée a-t-elle bien un rapprochement ?
        tous = [i for ids in tentees.values() for i in ids]
        lettrees = set()
        for i in range(0, len(tous), 1000):
            lettrees |= {ml["id"] for ml in cible.appel(
                "account.move.line", "read", [tous[i:i + 1000]], {"fields": ["matching_number"]})
                if ml["matching_number"]}
        faites = 0
        for nom, ids in tentees.items():
            if all(i in lettrees for i in ids):
                faites += 1
            else:
                erreurs.append({"ecriture": nom, "etape": "lettrage",
                                "erreur": "lettrage demandé mais absent de la base"})
        e.conclure("%s faites et vérifiées ; écartées : %s ligne(s) seule(s) (contrepartie "
                   "hors du lot), %s sur compte non lettrable" % (
                       nombre_texte(faites), nombre_texte(len(ignorees["ligne_seule"])),
                       nombre_texte(len(ignorees["compte_non_lettrable"]))))
    return {"lettres": len(groupes), "faites": faites,
            "ignorees": {k: len(v) for k, v in ignorees.items()},
            "ignorees_detail": {k: v[:200] for k, v in ignorees.items()}}


# ---------------------------------------------------------------------------
# Relecture : la base de test contient-elle exactement le lot ?
# ---------------------------------------------------------------------------

def relire(lot, connexion=None, base=None, j=None):
    """Relit en SQL (lecture seule) les écritures du lot dans la base de test et compare."""
    j = ou_muet(j)
    lid = lot_id(lot)
    if connexion is None:
        import psycopg2
        connexion = psycopg2.connect(dbname=base or os.environ.get("CONCORDE_TEST_BASE"))
        connexion.set_session(readonly=True, autocommit=True)
        fermer = True
    else:
        fermer = False
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "SELECT am.ref, am.state, aa.code, rp.ref, aml.debit, aml.credit, "
                "aml.matching_number FROM account_move_line aml "
                "JOIN account_move am ON am.id = aml.move_id "
                "JOIN account_account aa ON aa.id = aml.account_id "
                "LEFT JOIN res_partner rp ON rp.id = aml.partner_id "
                "WHERE am.ref LIKE %s", ("CONCORDE/%s/%%" % lid,))
            rangs = cur.fetchall()
    finally:
        if fermer:
            connexion.close()
    r = Rapport()

    def c(v):
        return int((Decimal(str(v)) * 100).to_integral_value())
    sortie = {"lignes": len(rangs), "ecritures": len({x[0] for x in rangs}),
              "debit": sum(c(x[4]) for x in rangs), "credit": sum(c(x[5]) for x in rangs)}
    entree = lot.totaux()
    r.info("entree", entree)
    r.info("sortie", sortie)
    for k, nom in (("ecritures", "écritures"), ("lignes", "lignes"), ("debit", "débit"),
                   ("credit", "crédit")):
        if entree[k] != sortie[k]:
            r.constat("BLOQUANT", "TEST_ECART", "Écart lot / base de test",
                      ["%s : lot %s, base de test %s" % (nom, entree[k], sortie[k])])
    r.constat("BLOQUANT", "TEST_NON_VALIDEE", "Écritures restées en brouillon",
              sorted({x[0] for x in rangs if x[1] != "posted"}))
    sa = lot.balance_par_compte(cible=True)
    sb = defaultdict(int)
    for x in rangs:
        sb[x[2]] += c(x[4]) - c(x[5])
    r.constat("BLOQUANT", "TEST_ECART_COMPTE", "Soldes de comptes différents",
              ["%s : lot %s, base %s" % (k, euros_texte(sa.get(k, 0), ","),
                                         euros_texte(sb.get(k, 0), ","))
               for k in sorted(set(sa) | set(sb)) if sa.get(k, 0) != sb.get(k, 0)])
    ta, tb = defaultdict(int), defaultdict(int)
    for l in lot.lignes:
        if l["tiers_ref"]:
            ta[l["tiers_ref"]] += 1
    for x in rangs:
        if x[3]:
            tb[x[3]] += 1
    r.constat("BLOQUANT", "TEST_ECART_TIERS", "Lignes de tiers différentes",
              ["%s : lot %d, base %d" % (k, ta[k], tb[k]) for k in sorted(set(ta) | set(tb))
               if ta[k] != tb[k]])
    r.info("lignes_lettrees", sum(1 for x in rangs if x[6]))
    for k in r.constats:
        j.dire("%s : %s" % (k["message"], nombre_texte(k["nombre"])), "erreur")
    if not r.constats:
        j.dire("Relecture conforme : %s écritures, %s lignes, D = C = %s €, soldes et tiers "
               "identiques au centime" % (nombre_texte(sortie["ecritures"]),
                                          nombre_texte(sortie["lignes"]),
                                          euros_texte(sortie["debit"], ",")), "ok")
    return r
