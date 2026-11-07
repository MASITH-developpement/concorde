# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Contrôle de la dématérialisation des factures dans Odoo (14 à 20).

100 % déterministe, zéro LLM, LECTURE SEULE : aucune écriture en base.

Le moteur ne parle jamais directement à Odoo : il reçoit une « source »
qui expose quatre méthodes (voir SourceXmlRpc ci-dessous et SourceEnv
dans le module Odoo) :

    champs(modele)                        -> dict des champs ({} si modèle absent)
    lire(modele, domaine, champs, offset, limit, ordre) -> list[dict]
    modules_installes(noms)               -> set des modules installés

Le même contrôle tourne donc :
  - hors d'Odoo, en XML-RPC avec une clé API (scripts/check_dematerialisation.py) ;
  - dans Odoo, depuis le menu CONCORDE > Contrôle dématérialisation.

Contrôles :
  CONFIGURATION — modules de facturation électronique, formats EDI, proxies
                  (Peppol / PPF / plateformes agréées), SIREN et TVA de la société.
  ÉMISSION      — factures clients validées : erreurs EDI / Peppol, envois en
                  attente, présence du XML (Factur-X / UBL / CII, y compris
                  embarqué dans le PDF), SIREN / TVA des clients B2B français.
  RÉCEPTION     — factures fournisseurs : part reçue en XML, doublons probables,
                  brouillons en attente de validation.

Niveaux : BLOQUANT (la chaîne est cassée), ALERTE (à corriger), INFO.
Jamais muet : une analyse tronquée ou un champ illisible est signalé.
Montants en centimes (int) — jamais de float dans les comparaisons.
"""
import hashlib
import html
import json
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

VERSION = "1.0"

BLOQUANT = "BLOQUANT"
ALERTE = "ALERTE"
INFO = "INFO"
NIVEAUX = (BLOQUANT, ALERTE, INFO)

TAILLE_LOT = 500
MAX_FACTURES_DEFAUT = 10000
MAX_EXEMPLES = 20
MAX_PDF_INSPECTES_DEFAUT = 200

# Modules Odoo liés à la facture électronique (présents ou non selon version).
MODULES_EINVOICE = (
    "account_edi",                 # framework EDI (14-16, encore présent ensuite)
    "account_edi_ubl_cii",         # Factur-X / UBL / CII
    "account_edi_facturx",         # Factur-X (14-15)
    "account_edi_proxy_client",    # proxy Odoo (Peppol, PDP…)
    "account_peppol",              # Peppol (17+)
    "l10n_fr",                     # localisation française
    "l10n_fr_account",             # localisation française comptable (18+)
    "l10n_fr_facturx_chorus_pro",  # Chorus Pro (secteur public)
)
MODULES_FORMAT = ("account_edi_ubl_cii", "account_edi_facturx", "account_edi")

# Noms de fichiers XML embarqués dans un PDF Factur-X / ZUGFeRD.
MARQUEURS_PDF = (b"factur-x.xml", b"zugferd-invoice.xml", b"xrechnung.xml")


# ---------------------------------------------------------------------------
# Identifiants français : SIREN / SIRET (Luhn) et TVA intracommunautaire
# ---------------------------------------------------------------------------

def _chiffres(texte):
    return re.sub(r"\D", "", texte or "")


def _luhn_ok(numero):
    total = 0
    for i, c in enumerate(reversed(numero)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def siren_valide(siren):
    """SIREN : 9 chiffres, clé de Luhn (exception La Poste 356000000)."""
    s = _chiffres(siren)
    return len(s) == 9 and (_luhn_ok(s) or s == "356000000")


def siret_valide(siret):
    """SIRET : 14 chiffres, clé de Luhn (exception La Poste : somme % 5)."""
    s = _chiffres(siret)
    if len(s) != 14:
        return False
    if s.startswith("356000000"):
        return sum(int(c) for c in s) % 5 == 0
    return _luhn_ok(s)


def tva_fr_valide(tva):
    """TVA intracom FR : FR + clé (2 chiffres) + SIREN, clé = (12 + 3*(SIREN % 97)) % 97."""
    t = re.sub(r"\s", "", (tva or "")).upper()
    m = re.fullmatch(r"FR([0-9A-Z]{2})(\d{9})", t)
    if not m:
        return False
    cle, siren = m.groups()
    if not siren_valide(siren):
        return False
    if cle.isdigit():
        return int(cle) == (12 + 3 * (int(siren) % 97)) % 97
    return True  # ancien format alphanumérique : non vérifiable par clé


def extraire_siren(enreg):
    """SIREN d'un partenaire / d'une société : champ siret (l10n_fr),
    company_registry (17+), sinon déduit d'un n° de TVA FR."""
    for champ in ("siret", "company_registry"):
        val = _chiffres(enreg.get(champ) or "")
        if len(val) in (9, 14):
            return val[:9]
    tva = re.sub(r"\s", "", (enreg.get("vat") or "")).upper()
    m = re.fullmatch(r"FR[0-9A-Z]{2}(\d{9})", tva)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def centimes_odoo(valeur):
    """Montant Odoo (float JSON / XML-RPC) -> centimes int, arrondi bancaire
    au centime (Odoo stocke déjà des montants arrondis à la devise)."""
    if valeur in (None, False):
        return 0
    return int((Decimal(str(valeur)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _m2o_id(val):
    return val[0] if isinstance(val, (list, tuple)) and val else (val or None)


def _m2o_nom(val):
    return val[1] if isinstance(val, (list, tuple)) and len(val) > 1 else ""


def _date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


def _lots(liste, taille=1000):
    for i in range(0, len(liste), taille):
        yield liste[i:i + taille]


# ---------------------------------------------------------------------------
# Source XML-RPC (hors Odoo, clé API) — lecture seule
# ---------------------------------------------------------------------------

class SourceXmlRpc:
    """Client XML-RPC Odoo en lecture seule (search_read / fields_get uniquement)."""

    METHODES_AUTORISEES = ("search_read", "fields_get", "search_count")

    def __init__(self, url, db, utilisateur, cle_api, timeout=60):
        import xmlrpc.client

        self.url = url.rstrip("/")
        self.db = db
        self._cle = cle_api
        self._fault = xmlrpc.client.Fault

        class _Transport(xmlrpc.client.SafeTransport if self.url.startswith("https")
                         else xmlrpc.client.Transport):
            def make_connection(self, host):
                conn = super().make_connection(host)
                conn.timeout = timeout
                return conn

        commun = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/common", transport=_Transport(), allow_none=True)
        self._objet = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/object", transport=_Transport(), allow_none=True)
        try:
            self.version_serveur = commun.version().get("server_version", "?")
        except Exception:
            self.version_serveur = "?"
        self.uid = commun.authenticate(db, utilisateur, cle_api, {})
        if not self.uid:
            raise ConnectionError(
                "Authentification refusée : vérifiez l'URL, la base, le login et "
                "la clé API (Préférences > Sécurité du compte > Clés API).")
        self._champs = {}

    def _appel(self, modele, methode, args, kwargs=None):
        if methode not in self.METHODES_AUTORISEES:
            raise PermissionError("Méthode %r interdite : client en lecture seule." % methode)
        return self._objet.execute_kw(self.db, self.uid, self._cle,
                                      modele, methode, args, kwargs or {})

    def champs(self, modele):
        if modele not in self._champs:
            try:
                self._champs[modele] = self._appel(
                    modele, "fields_get", [], {"attributes": ["type", "string"]})
            except self._fault:
                self._champs[modele] = {}  # modèle absent ou non accessible
        return self._champs[modele]

    def lire(self, modele, domaine, champs, offset=0, limit=None, ordre="id"):
        kw = {"fields": list(champs), "offset": offset, "order": ordre}
        if limit:
            kw["limit"] = limit
        return self._appel(modele, "search_read", [domaine], kw)

    def modules_installes(self, noms):
        try:
            mods = self.lire("ir.module.module",
                             [["name", "in", list(noms)], ["state", "=", "installed"]],
                             ["name"])
        except self._fault:
            return None  # droits insuffisants : signalé dans le rapport
        return {m["name"] for m in mods}


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

class Rapport:
    def __init__(self, depuis, jours):
        self.depuis = depuis
        self.jours = jours
        self.infos = OrderedDict()
        self._anomalies = OrderedDict()  # code -> dict

    def info(self, cle, valeur):
        self.infos[cle] = valeur

    def anomalie(self, niveau, sens, code, message, facture=None):
        """Regroupe les anomalies par code : un message, N factures concernées."""
        assert niveau in NIVEAUX
        a = self._anomalies.get(code)
        if a is None:
            a = self._anomalies[code] = {
                "niveau": niveau, "sens": sens, "code": code,
                "message": message, "nombre": 0, "exemples": []}
        a["nombre"] += 1
        if facture and len(a["exemples"]) < MAX_EXEMPLES:
            a["exemples"].append(facture)

    @property
    def anomalies(self):
        ordre = {n: i for i, n in enumerate(NIVEAUX)}
        return sorted(self._anomalies.values(), key=lambda a: ordre[a["niveau"]])

    def compte(self, niveau):
        return sum(1 for a in self._anomalies.values() if a["niveau"] == niveau)

    @property
    def statut(self):
        if self.compte(BLOQUANT):
            return "non_conforme"
        if self.compte(ALERTE):
            return "a_verifier"
        return "conforme"

    def en_dict(self):
        d = OrderedDict()
        d["moteur"] = "CONCORDE demat v%s" % VERSION
        d["depuis"] = str(self.depuis)
        d["jours"] = self.jours
        d["statut"] = self.statut
        d["bloquants"] = self.compte(BLOQUANT)
        d["alertes"] = self.compte(ALERTE)
        d["infos_anomalies"] = self.compte(INFO)
        d["infos"] = self.infos
        d["anomalies"] = self.anomalies
        charge = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
        d["empreinte"] = hashlib.sha256(charge.encode("utf-8")).hexdigest()
        return d


# ---------------------------------------------------------------------------
# Contrôleur
# ---------------------------------------------------------------------------

class ControleDemat:
    def __init__(self, source, jours=30, aujourd_hui=None,
                 max_factures=MAX_FACTURES_DEFAUT,
                 inspecter_pdf=True, max_pdf=MAX_PDF_INSPECTES_DEFAUT):
        if jours < 1:
            raise ValueError("La fenêtre d'analyse doit être d'au moins 1 jour.")
        self.src = source
        self.jours = jours
        self.aujourd_hui = aujourd_hui or date.today()
        self.depuis = self.aujourd_hui - timedelta(days=jours)
        self.max_factures = max_factures
        self.inspecter_pdf = inspecter_pdf
        self.max_pdf = max_pdf
        self.r = Rapport(self.depuis, jours)
        self._champs_move = {}

    # --- lecture ------------------------------------------------------------
    def _filtrer(self, modele, candidats):
        dispo = self.src.champs(modele)
        return [c for c in candidats if c in dispo]

    def _lire_tout(self, modele, domaine, champs, etiquette):
        """Lecture paginée ; jamais de troncature silencieuse."""
        res, offset = [], 0
        while len(res) < self.max_factures:
            demande = min(TAILLE_LOT, self.max_factures - len(res))
            lot = self.src.lire(modele, domaine, champs, offset=offset, limit=demande)
            res.extend(lot)
            if len(lot) < demande:
                return res
            offset += len(lot)
        reste = self.src.lire(modele, domaine, ["id"], offset=offset, limit=1)
        if reste:
            self.r.anomalie(ALERTE, "général", "analyse_tronquee",
                            "Analyse %s limitée aux %d premières factures : relancez avec "
                            "une fenêtre plus courte ou un plafond plus élevé."
                            % (etiquette, self.max_factures))
        return res

    # --- point d'entrée -----------------------------------------------------
    def executer(self):
        self._champs_move = self.src.champs("account.move")
        if not self._champs_move:
            raise RuntimeError("Modèle account.move inaccessible : module Comptabilité "
                               "absent ou droits insuffisants.")
        self.controler_configuration()
        self.controler_emission()
        self.controler_reception()
        return self.r

    # --- 1. Configuration ---------------------------------------------------
    def controler_configuration(self):
        r = self.r
        mods = self.src.modules_installes(MODULES_EINVOICE)
        if mods is None:
            r.info("modules", "illisibles (droits insuffisants sur ir.module.module)")
            r.anomalie(INFO, "configuration", "modules_illisibles",
                       "Liste des modules illisible avec ce compte : contrôle de "
                       "configuration partiel.")
        else:
            r.info("modules", sorted(mods))
            if not mods.intersection(MODULES_FORMAT):
                r.anomalie(BLOQUANT, "configuration", "aucun_module_einvoice",
                           "Aucun module de facture électronique installé "
                           "(account_edi_ubl_cii / account_edi) : Odoo ne produit "
                           "ni ne lit de Factur-X / UBL / CII.")
            if "account_edi_proxy_client" not in mods and "account_peppol" not in mods:
                r.anomalie(INFO, "configuration", "aucun_proxy",
                           "Aucun connecteur de transmission (Peppol / proxy EDI) : "
                           "l'émission et la réception passent par une plateforme "
                           "externe ou par e-mail — à vérifier.")

        # Formats EDI (account.edi.format n'a ni 'active' ni 'company_id')
        champs_fmt = self._filtrer("account.edi.format", ["name", "code"])
        formats = self.src.lire("account.edi.format", [], champs_fmt, limit=200) \
            if champs_fmt else []
        r.info("formats_edi", ["%s (%s)" % (f.get("name"), f.get("code")) for f in formats])

        # Proxies EDI (Peppol, PDP…) — champs variables selon la version
        champs_px = self._filtrer("account.edi.proxy.client",
                                  ["proxy_type", "edi_mode", "edi_identification",
                                   "company_id", "active"])
        if champs_px:
            proxies = self.src.lire("account.edi.proxy.client", [], champs_px, limit=50)
            r.info("proxies", [
                "%s %s %s (%s)" % (p.get("proxy_type", ""), p.get("edi_identification", ""),
                                   p.get("edi_mode", ""), _m2o_nom(p.get("company_id")))
                for p in proxies])
            for p in proxies:
                if p.get("edi_mode") in ("test", "demo"):
                    r.anomalie(ALERTE, "configuration", "proxy_mode_test",
                               "Connecteur EDI en mode test / démo : aucune facture "
                               "n'est réellement transmise.",
                               _m2o_nom(p.get("company_id")) or p.get("edi_identification"))

        # Société(s) : SIREN obligatoire (annuaire de la réforme), TVA valide
        champs_soc = self._filtrer("res.company",
                                   ["name", "country_code", "vat", "company_registry", "siret"])
        for soc in self.src.lire("res.company", [], champs_soc):
            if soc.get("country_code") not in (None, False, "FR"):
                continue
            siren = extraire_siren(soc)
            if not siren:
                r.anomalie(BLOQUANT, "configuration", "societe_sans_siren",
                           "Société sans SIREN/SIRET : impossible d'être identifiée "
                           "dans l'annuaire de la facturation électronique.", soc["name"])
            elif not siren_valide(siren):
                r.anomalie(BLOQUANT, "configuration", "societe_siren_invalide",
                           "SIREN de la société invalide (clé de contrôle).",
                           "%s : %s" % (soc["name"], siren))
            if not soc.get("vat"):
                r.anomalie(ALERTE, "configuration", "societe_sans_tva",
                           "Société sans n° de TVA intracommunautaire.", soc["name"])
            elif soc["vat"].upper().startswith("FR") and not tva_fr_valide(soc["vat"]):
                r.anomalie(BLOQUANT, "configuration", "societe_tva_invalide",
                           "N° de TVA de la société invalide (clé FR).",
                           "%s : %s" % (soc["name"], soc["vat"]))

    # --- 2. Émission ----------------------------------------------------------
    def controler_emission(self):
        r = self.r
        champs = self._filtrer("account.move", [
            "name", "invoice_date", "amount_total", "partner_id", "commercial_partner_id",
            "edi_state", "edi_blocking_level", "edi_error_message",
            "peppol_move_state", "is_move_sent", "move_sent_values",
            "ubl_cii_xml_id", "invoice_pdf_report_id", "message_main_attachment_id"])
        domaine = [["move_type", "in", ["out_invoice", "out_refund"]],
                   ["state", "=", "posted"],
                   ["invoice_date", ">=", str(self.depuis)]]
        factures = self._lire_tout("account.move", domaine, champs, "émission")
        r.info("emission_total", len(factures))
        if not factures:
            return

        etats = {}
        non_envoyees = 0
        for f in factures:
            nom = f.get("name") or "#%s" % f["id"]
            st = f.get("edi_state") or f.get("peppol_move_state") or "n/a"
            etats[st] = etats.get(st, 0) + 1

            if f.get("edi_blocking_level") == "error":
                r.anomalie(BLOQUANT, "émission", "edi_erreur",
                           "Document EDI en erreur bloquante.",
                           "%s — %s" % (nom, _texte(f.get("edi_error_message"))))
            elif f.get("edi_blocking_level") == "warning":
                r.anomalie(ALERTE, "émission", "edi_avertissement",
                           "Document EDI en avertissement.",
                           "%s — %s" % (nom, _texte(f.get("edi_error_message"))))
            if f.get("edi_state") == "to_send" and \
                    _date(f.get("invoice_date")) < self.aujourd_hui - timedelta(days=1):
                r.anomalie(ALERTE, "émission", "edi_a_envoyer",
                           "Facture validée depuis plus d'un jour, envoi EDI non effectué "
                           "(edi_state = to_send : vérifier la tâche planifiée EDI).", nom)
            if f.get("edi_state") == "to_cancel":
                r.anomalie(ALERTE, "émission", "edi_a_annuler",
                           "Annulation EDI demandée mais non traitée.", nom)

            ps = f.get("peppol_move_state")
            if ps == "error":
                r.anomalie(BLOQUANT, "émission", "peppol_erreur",
                           "Envoi Peppol en erreur.", nom)
            elif ps in ("to_send", "processing") and \
                    _date(f.get("invoice_date")) < self.aujourd_hui - timedelta(days=2):
                r.anomalie(ALERTE, "émission", "peppol_en_attente",
                           "Envoi Peppol en attente depuis plus de 2 jours.", nom)

            envoyee = f.get("is_move_sent")
            if envoyee is None and "move_sent_values" in f:
                envoyee = f.get("move_sent_values") == "sent"
            if envoyee is False:
                non_envoyees += 1
        r.info("emission_etats_edi", etats)
        if non_envoyees:
            r.info("emission_non_envoyees", non_envoyees)
            r.anomalie(INFO, "émission", "non_envoyees",
                       "%d facture(s) validée(s) jamais envoyée(s) au client."
                       % non_envoyees)

        avec_xml = self._factures_avec_xml(factures)
        r.info("emission_avec_xml", len(avec_xml))

        # Clients B2B français : SIREN obligatoire, TVA valide, XML attendu
        partenaires = self._lire_partenaires(factures)
        for f in factures:
            p = partenaires.get(_m2o_id(f.get("commercial_partner_id") or f.get("partner_id")))
            if not p or not p.get("is_company") or p.get("country_code") != "FR":
                continue
            nom = "%s (%s)" % (f.get("name"), p.get("name"))
            siren = extraire_siren(p)
            if not siren:
                r.anomalie(ALERTE, "émission", "client_sans_siren",
                           "Client professionnel français sans SIREN : mention obligatoire "
                           "de la facture électronique (rejet par la plateforme).", nom)
            elif not siren_valide(siren):
                r.anomalie(ALERTE, "émission", "client_siren_invalide",
                           "SIREN client invalide (clé de contrôle).", "%s : %s" % (nom, siren))
            if p.get("vat") and p["vat"].upper().startswith("FR") \
                    and not tva_fr_valide(p["vat"]):
                r.anomalie(ALERTE, "émission", "client_tva_invalide",
                           "N° de TVA client invalide (clé FR).", "%s : %s" % (nom, p["vat"]))
            if f["id"] not in avec_xml:
                r.anomalie(ALERTE, "émission", "b2b_sans_xml",
                           "Facture B2B France sans XML structuré détecté "
                           "(Factur-X / UBL / CII) : PDF simple, non conforme à la réforme.",
                           nom)

    # --- 3. Réception ---------------------------------------------------------
    def controler_reception(self):
        r = self.r
        champs = self._filtrer("account.move", [
            "name", "ref", "state", "invoice_date", "create_date", "amount_total",
            "partner_id", "commercial_partner_id", "ubl_cii_xml_id",
            "invoice_pdf_report_id", "message_main_attachment_id"])
        domaine = [["move_type", "in", ["in_invoice", "in_refund"]],
                   ["state", "!=", "cancel"],
                   "|", ["invoice_date", ">=", str(self.depuis)],
                   ["create_date", ">=", str(self.depuis)]]
        factures = self._lire_tout("account.move", domaine, champs, "réception")
        r.info("reception_total", len(factures))
        if not factures:
            r.anomalie(INFO, "réception", "aucune_reception",
                       "Aucune facture fournisseur sur la période : vérifier que le "
                       "canal de réception (plateforme, Peppol, alias e-mail) fonctionne.")
            return

        avec_xml = self._factures_avec_xml(factures)
        r.info("reception_avec_xml", len(avec_xml))
        taux = len(avec_xml) * 100 // len(factures)
        r.info("reception_taux_electronique", "%d %%" % taux)
        if taux < 50:
            r.anomalie(ALERTE, "réception", "reception_peu_electronique",
                       "Seulement %d %% des factures fournisseurs sont reçues avec un XML "
                       "structuré : depuis le 1er septembre 2026 toute entreprise doit "
                       "pouvoir recevoir des factures électroniques (plateforme agréée)."
                       % taux)

        # Doublons probables : même fournisseur + même référence + même montant
        vus = {}
        for f in factures:
            ref = re.sub(r"\s", "", (f.get("ref") or "")).upper()
            if not ref:
                continue
            cle = (_m2o_id(f.get("commercial_partner_id") or f.get("partner_id")),
                   ref, centimes_odoo(f.get("amount_total")))
            vus.setdefault(cle, []).append(f.get("name") or "#%s" % f["id"])
        for (pid, ref, cts), noms in vus.items():
            if len(noms) > 1:
                r.anomalie(ALERTE, "réception", "doublon_probable",
                           "Factures fournisseurs probablement importées en double "
                           "(même fournisseur, référence et montant).",
                           "%s : %s" % (ref, ", ".join(noms)))

        # Brouillons qui traînent (réception automatique non traitée)
        limite = self.aujourd_hui - timedelta(days=15)
        anciens = [f for f in factures if f.get("state") == "draft"
                   and (_date(f.get("create_date")) or self.aujourd_hui) < limite]
        if anciens:
            for f in anciens:
                r.anomalie(INFO, "réception", "brouillons_anciens",
                           "Factures fournisseurs en brouillon depuis plus de 15 jours.",
                           f.get("name") or f.get("ref") or "#%s" % f["id"])

    # --- détection du XML -----------------------------------------------------
    def _factures_avec_xml(self, factures):
        """IDs des factures portant un XML structuré :
        1. champ ubl_cii_xml_id (17+, pièce jointe masquée des recherches) ;
        2. pièce jointe XML visible (Factur-X / UBL / CII / XRechnung) ;
        3. XML embarqué dans le PDF (Factur-X), détection par nom de fichier."""
        trouves = {f["id"] for f in factures if f.get("ubl_cii_xml_id")}
        reste = [f["id"] for f in factures if f["id"] not in trouves]
        for lot in _lots(reste):
            atts = self.src.lire("ir.attachment", [
                ["res_model", "=", "account.move"], ["res_id", "in", lot],
                "|", "|", ["mimetype", "ilike", "xml"], ["name", "=ilike", "%.xml"],
                ["name", "ilike", "factur"]], ["res_id"])
            trouves.update(a["res_id"] for a in atts)

        if self.inspecter_pdf:
            pdf_par_facture = {}
            for f in factures:
                if f["id"] in trouves:
                    continue
                aid = _m2o_id(f.get("invoice_pdf_report_id")) or \
                    _m2o_id(f.get("message_main_attachment_id"))
                if aid:
                    pdf_par_facture[aid] = f["id"]
            ids = list(pdf_par_facture)[:self.max_pdf]
            if len(pdf_par_facture) > self.max_pdf:
                self.r.anomalie(INFO, "général", "pdf_non_inspectes",
                                "%d PDF non inspectés (plafond %d) : le taux XML peut "
                                "être sous-estimé." % (len(pdf_par_facture) - self.max_pdf,
                                                       self.max_pdf))
            for lot in _lots(ids, 20):
                for a in self.src.lire("ir.attachment", [["id", "in", lot]],
                                       ["id", "mimetype", "datas"]):
                    if pdf_contient_xml(a.get("datas")):
                        trouves.add(pdf_par_facture[a["id"]])
        return trouves

    def _lire_partenaires(self, factures):
        ids = sorted({_m2o_id(f.get("commercial_partner_id") or f.get("partner_id"))
                      for f in factures} - {None})
        champs = self._filtrer("res.partner", ["name", "is_company", "country_code",
                                               "vat", "company_registry", "siret"])
        res = {}
        for lot in _lots(ids):
            for p in self.src.lire("res.partner", [["id", "in", lot]], champs):
                res[p["id"]] = p
        return res


def pdf_contient_xml(datas_b64):
    """Vrai si le PDF (base64) embarque un XML Factur-X / ZUGFeRD / XRechnung."""
    if not datas_b64:
        return False
    import base64
    if isinstance(datas_b64, bytes) and datas_b64.startswith(b"%PDF"):
        brut = datas_b64  # déjà décodé (certaines versions d'Odoo)
    else:
        try:
            brut = base64.b64decode(datas_b64)
        except (ValueError, TypeError):
            return False
    if not brut.startswith(b"%PDF"):
        return False
    bas = brut.lower()
    return any(m in bas for m in MARQUEURS_PDF)


def _texte(val):
    """edi_error_message peut être du HTML : texte brut, 200 caractères max."""
    t = re.sub(r"<[^>]+>", " ", str(val or ""))
    return re.sub(r"\s+", " ", html.unescape(t)).strip()[:200]


# ---------------------------------------------------------------------------
# Rendus
# ---------------------------------------------------------------------------

LIBELLES = OrderedDict([
    ("modules", "Modules facture électronique"),
    ("formats_edi", "Formats EDI"),
    ("proxies", "Connecteurs EDI / Peppol"),
    ("emission_total", "Émission — factures validées"),
    ("emission_etats_edi", "Émission — états EDI / Peppol"),
    ("emission_avec_xml", "Émission — avec XML structuré"),
    ("emission_non_envoyees", "Émission — jamais envoyées"),
    ("reception_total", "Réception — factures fournisseurs"),
    ("reception_avec_xml", "Réception — avec XML structuré"),
    ("reception_taux_electronique", "Réception — taux électronique"),
])
STATUTS = {"conforme": "CONFORME", "a_verifier": "À VÉRIFIER",
           "non_conforme": "NON CONFORME"}


def _valeur(v):
    if isinstance(v, dict):
        return ", ".join("%s : %s" % kv for kv in v.items()) or "—"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) or "aucun"
    return str(v)


def rendu_texte(d):
    lignes = ["=" * 70, "CONCORDE — CONTRÔLE DE LA DÉMATÉRIALISATION DES FACTURES",
              "=" * 70, "Période : depuis le %s (%s jours)" % (d["depuis"], d["jours"]), ""]
    for cle, lib in LIBELLES.items():
        if cle in d["infos"]:
            lignes.append("  %-38s %s" % (lib, _valeur(d["infos"][cle])))
    lignes.append("")
    if d["anomalies"]:
        lignes.append("ANOMALIES : %d bloquante(s), %d alerte(s), %d info(s)"
                      % (d["bloquants"], d["alertes"], d["infos_anomalies"]))
        for a in d["anomalies"]:
            lignes.append("  [%s] [%s] %s (%d)" % (a["niveau"], a["sens"].upper(),
                                                   a["message"], a["nombre"]))
            for ex in a["exemples"]:
                lignes.append("        - %s" % ex)
            if a["nombre"] > len(a["exemples"]) and a["exemples"]:
                lignes.append("        … et %d autre(s)" % (a["nombre"] - len(a["exemples"])))
    else:
        lignes.append("Aucune anomalie détectée sur la période.")
    lignes += ["", "Résultat : %s" % STATUTS[d["statut"]],
               "Empreinte SHA-256 : %s" % d["empreinte"]]
    return "\n".join(lignes)


def rendu_html(d):
    e = html.escape
    couleurs = {BLOQUANT: "#b00020", ALERTE: "#b26a00", INFO: "#555"}
    statut_coul = {"conforme": "#1b7f3b", "a_verifier": "#b26a00",
                   "non_conforme": "#b00020"}[d["statut"]]
    h = ['<div class="concorde-demat">',
         '<h3 style="color:%s">%s</h3>' % (statut_coul, e(STATUTS[d["statut"]])),
         '<p>Période : depuis le %s (%s jours) — %d bloquante(s), %d alerte(s), '
         '%d info(s)</p>' % (e(d["depuis"]), d["jours"], d["bloquants"],
                             d["alertes"], d["infos_anomalies"]),
         '<table class="table table-sm"><tbody>']
    for cle, lib in LIBELLES.items():
        if cle in d["infos"]:
            h.append("<tr><th>%s</th><td>%s</td></tr>"
                     % (e(lib), e(_valeur(d["infos"][cle]))))
    h.append("</tbody></table>")
    if d["anomalies"]:
        h.append('<table class="table table-sm table-bordered"><thead><tr>'
                 '<th>Niveau</th><th>Sens</th><th>Anomalie</th><th>Nb</th>'
                 '<th>Factures / détails</th></tr></thead><tbody>')
        for a in d["anomalies"]:
            ex = "<br/>".join(e(str(x)) for x in a["exemples"])
            if a["nombre"] > len(a["exemples"]) and a["exemples"]:
                ex += "<br/>… et %d autre(s)" % (a["nombre"] - len(a["exemples"]))
            h.append('<tr><td style="color:%s;font-weight:bold">%s</td><td>%s</td>'
                     '<td>%s</td><td>%d</td><td>%s</td></tr>'
                     % (couleurs[a["niveau"]], e(a["niveau"]), e(a["sens"]),
                        e(a["message"]), a["nombre"], ex))
        h.append("</tbody></table>")
    else:
        h.append("<p>Aucune anomalie détectée sur la période.</p>")
    h.append('<p style="color:#888;font-size:smaller">Empreinte SHA-256 : %s</p></div>'
             % e(d["empreinte"]))
    return "".join(h)
