# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Lecture des données comptables d'un Odoo 17 — deux sources, un seul format.

  SourceSqlOdoo17     lecture directe PostgreSQL (rapide : ~150 000 lignes en
                      quelques secondes). Transaction en LECTURE SEULE.
                      psycopg2 est chargé uniquement pour cette source.
                      Identifiants : variables libpq (PGHOST, PGPORT, PGUSER,
                      PGPASSWORD) — jamais en argument.
  SourceXmlRpcOdoo17  passe par l'API d'Odoo (marche partout, Odoo Online
                      compris). Clé API dans ODOO_API_KEY. LECTURE SEULE :
                      seules search_read / read / fields_get sont autorisées.

Les deux sources rendent exactement les mêmes enregistrements (dict) :
le reste de CONCORDE ne sait pas d'où viennent les données.

Montants : TOUJOURS en centimes (int). Un montant Odoo qui ne tombe pas
juste au centime est refusé (ErreurMontant), jamais arrondi.

ÉCRITURE : aucune ici. Les écritures dans Odoo passent toujours par l'ORM
(XML-RPC, injectors/), jamais par SQL (ADR-0001).
"""

import time
from datetime import date, datetime
from decimal import Decimal

from .canonical import ErreurMontant
from .journal import duree_texte, nombre_texte, ou_muet

# Types de comptes Odoo 17 qui portent un compte auxiliaire (tiers).
TYPES_TIERS = ("asset_receivable", "liability_payable")

# Lignes de facture purement décoratives : jamais comptables.
TYPES_AFFICHAGE = ("line_section", "line_note")

TYPES_FACTURE = ("out_invoice", "out_refund", "in_invoice", "in_refund")

ETATS = ("posted", "draft", "cancel")


class ErreurSource(RuntimeError):
    """Erreur explicite de lecture (connexion, version, paramètre)."""


# ---------------------------------------------------------------------------
# Conversions strictes
# ---------------------------------------------------------------------------


def centimes(valeur):
    """Montant Odoo (Decimal SQL ou float XML-RPC) -> centimes int, sans arrondi.

    Refuse tout montant qui ne tombe pas juste au centime (arrondi silencieux
    interdit). repr() d'un float XML-RPC rend la valeur décimale stockée par
    Odoo (ex. 123.45 -> '123.45') : la conversion est exacte.
    """
    if valeur in (None, False):
        return 0
    d = valeur if isinstance(valeur, Decimal) else Decimal(repr(valeur))
    c = d * 100
    if c != c.to_integral_value():
        raise ErreurMontant("Montant Odoo non exact au centime : %s" % valeur)
    return int(c)


def _date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


def _texte(val):
    """Texte Odoo : False -> '' ; dict de traductions (jsonb) -> fr_FR puis en_US."""
    if val in (None, False):
        return ""
    if isinstance(val, dict):
        return (
            val.get("fr_FR")
            or val.get("en_US")
            or next(iter(val.values()), "")
        )
    return str(val)


def _m2o(val):
    """(id, nom) d'un many2one XML-RPC ; (None, '') si vide."""
    if isinstance(val, (list, tuple)) and val:
        return val[0], (val[1] if len(val) > 1 else "")
    return None, ""


def _lots(liste, taille):
    for i in range(0, len(liste), taille):
        yield liste[i : i + taille]


def _periode_texte(debut, fin):
    if debut and fin:
        return ", du %s au %s" % (
            debut.strftime("%d/%m/%Y"),
            fin.strftime("%d/%m/%Y"),
        )
    if debut:
        return ", depuis le %s" % debut.strftime("%d/%m/%Y")
    if fin:
        return ", jusqu'au %s" % fin.strftime("%d/%m/%Y")
    return ", toutes dates"


def balance_depuis_lignes(comptes, lignes):
    """Balance calculée en Python (source XML-RPC) : même format que la SQL."""
    par_code = {
        c["code"]: dict(c, debit=0, credit=0, lignes=0, non_lettrees=0)
        for c in comptes
    }
    for l in lignes:
        c = par_code.get(l["compte"])
        if c is None:
            continue
        c["debit"] += l["debit"]
        c["credit"] += l["credit"]
        c["lignes"] += 1
        if (
            c["lettrable"]
            and not l["lettrage"]
            and (l["debit"] or l["credit"])
        ):
            c["non_lettrees"] += 1
    return sorted(par_code.values(), key=lambda c: c["code"])


def balance_tiers_depuis_lignes(lignes):
    groupes = {}
    for l in lignes:
        if l["compte_type"] not in TYPES_TIERS:
            continue
        g = groupes.setdefault(
            (l["compte"], l["tiers_id"]),
            {
                "compte": l["compte"],
                "tiers_id": l["tiers_id"],
                "tiers_nom": l["tiers_nom"],
                "tiers_ref": l["tiers_ref"],
                "debit": 0,
                "credit": 0,
                "lignes": 0,
            },
        )
        g["debit"] += l["debit"]
        g["credit"] += l["credit"]
        g["lignes"] += 1
    return list(groupes.values())


def analytique_texte(distribution, noms):
    """Répartition Odoo 17 {"86,252": 98.76, ...} -> texte stable, comparable entre bases.

    Chaque clé combine un compte par plan ; les identifiants sont traduits en code (ou nom)
    par `noms` {id: libellé}. Pourcentages à 2 décimales, éléments triés.
    """
    if not distribution:
        return ""
    parts = []
    for cle, pct in distribution.items():
        comptes = "+".join(
            sorted(
                noms.get(int(i), "#%s" % i)
                for i in str(cle).split(",")
                if str(i).strip()
            )
        )
        parts.append(
            "%s %s %%"
            % (comptes, ("%.2f" % float(pct)).rstrip("0").rstrip("."))
        )
    return " ; ".join(sorted(parts))


def analytique_comptes(distribution, noms):
    """Comptes analytiques (code ou nom) touchés par une répartition, triés, sans doublon."""
    if not distribution:
        return []
    return sorted(
        {
            noms.get(int(i), "#%s" % i)
            for cle in distribution
            for i in str(cle).split(",")
            if str(i).strip()
        }
    )


def cle_tri(ligne):
    """Ordre stable : date, numéro, id d'écriture (brouillons « / »), id de ligne."""
    return (
        ligne["date"] or date.min,
        ligne["ecriture"],
        ligne["ecriture_id"],
        ligne["ligne_id"],
    )


# ---------------------------------------------------------------------------
# Format commun des enregistrements
# ---------------------------------------------------------------------------
#
# ligne d'écriture :
#   ligne_id, ecriture_id, ecriture (nom), type_piece (move_type), etat,
#   journal_code, journal_lib, date, piece_date, reference,
#   compte, compte_lib, compte_type, tiers_id, tiers_ref, tiers_nom,
#   libelle, debit, credit (centimes), lettrage, date_lettrage,
#   montant_devise (centimes, signé), devise, echeance, modifie_le,
#   auto_post ('no' ou planification : brouillon comptabilisé automatiquement),
#   analytique (texte stable : « CODE1+CODE2 98.76 % ; … », comptes par code ou nom —
#               comparable d'une base à l'autre ; '' si aucune répartition)
#
# compte  : id, code, libelle, type, lettrable, deprecie
# journal : id, code, libelle, type, actif
# tiers   : id, nom, ref, tva, siren, email, telephone, rue, cp, ville,
#           pays, societe, actif, client, fournisseur, parent_id
# facture : id, numero, type_piece, etat, etat_paiement, journal_code,
#           tiers_id, tiers_nom, date, date_facture, echeance, reference,
#           ht, tva, ttc, reste_du (centimes, signés comme Odoo), devise


# ---------------------------------------------------------------------------
# Source SQL (PostgreSQL, lecture seule)
# ---------------------------------------------------------------------------

_SQL_LIGNES = """
SELECT aml.id, am.id, am.name, am.move_type, am.state,
       aj.code, COALESCE(aj.name->>'fr_FR', aj.name->>'en_US'),
       am.date, am.invoice_date, am.ref,
       aa.code, COALESCE(aa.name->>'fr_FR', aa.name->>'en_US'), aa.account_type,
       rp.id, rp.ref, rp.name,
       aml.name, aml.debit, aml.credit,
       CASE WHEN aml.full_reconcile_id IS NOT NULL THEN aml.matching_number END,
       afr.create_date,
       CASE WHEN aml.currency_id <> aml.company_currency_id THEN aml.amount_currency END,
       CASE WHEN aml.currency_id <> aml.company_currency_id THEN cur.name END,
       aml.date_maturity, GREATEST(am.write_date, aml.write_date), am.auto_post,
       aml.analytic_distribution
  FROM account_move_line aml
  JOIN account_move am ON am.id = aml.move_id
  JOIN account_journal aj ON aj.id = am.journal_id
  LEFT JOIN account_account aa ON aa.id = aml.account_id
  LEFT JOIN res_partner rp ON rp.id = aml.partner_id
  LEFT JOIN account_full_reconcile afr ON afr.id = aml.full_reconcile_id
  LEFT JOIN res_currency cur ON cur.id = aml.currency_id
 WHERE aml.company_id = %(societe)s
   AND am.state = ANY(%(etats)s)
   AND (aml.display_type IS NULL OR aml.display_type <> ALL(%(affichage)s))
   AND (%(debut)s::date IS NULL OR am.date >= %(debut)s::date)
   AND (%(fin)s::date IS NULL OR am.date <= %(fin)s::date)
   AND (%(comptes)s::text[] IS NULL OR aa.code = ANY(%(comptes)s::text[]))
   AND (%(ecriture)s::int IS NULL OR am.id = %(ecriture)s::int)
 ORDER BY am.date, am.name, am.id, aml.id
"""

PAS_PROGRESSION = (
    25000  # le journal annonce l'avancement toutes les 25 000 lignes
)

_SQL_BALANCE = """
SELECT aa.id, aa.code, COALESCE(aa.name->>'fr_FR', aa.name->>'en_US'), aa.account_type,
       aa.reconcile, aa.deprecated,
       COALESCE(SUM(aml.debit), 0), COALESCE(SUM(aml.credit), 0), COUNT(aml.id),
       COUNT(aml.id) FILTER (WHERE aa.reconcile AND NOT aml.reconciled
                             AND aml.amount_residual <> 0)
  FROM account_account aa
  LEFT JOIN account_move_line aml ON aml.account_id = aa.id
       AND aml.company_id = %(societe)s
       AND aml.parent_state = ANY(%(etats)s)
       AND (aml.display_type IS NULL OR aml.display_type <> ALL(%(affichage)s))
       AND (%(debut)s::date IS NULL OR aml.date >= %(debut)s::date)
       AND (%(fin)s::date IS NULL OR aml.date <= %(fin)s::date)
 WHERE aa.company_id = %(societe)s
 GROUP BY aa.id
 ORDER BY aa.code
"""

_SQL_BALANCE_TIERS = """
SELECT aa.code, rp.id, rp.name, rp.ref,
       SUM(aml.debit), SUM(aml.credit), COUNT(*)
  FROM account_move_line aml
  JOIN account_account aa ON aa.id = aml.account_id
  LEFT JOIN res_partner rp ON rp.id = aml.partner_id
 WHERE aml.company_id = %(societe)s
   AND aml.parent_state = ANY(%(etats)s)
   AND aa.account_type = ANY(%(types)s)
   AND (%(debut)s::date IS NULL OR aml.date >= %(debut)s::date)
   AND (%(fin)s::date IS NULL OR aml.date <= %(fin)s::date)
 GROUP BY aa.code, rp.id, rp.name, rp.ref
"""

_CHAMPS_LIGNE = (
    "ligne_id",
    "ecriture_id",
    "ecriture",
    "type_piece",
    "etat",
    "journal_code",
    "journal_lib",
    "date",
    "piece_date",
    "reference",
    "compte",
    "compte_lib",
    "compte_type",
    "tiers_id",
    "tiers_ref",
    "tiers_nom",
    "libelle",
    "debit",
    "credit",
    "lettrage",
    "date_lettrage",
    "montant_devise",
    "devise",
    "echeance",
    "modifie_le",
    "auto_post",
    "analytique",
)


class SourceSqlOdoo17:
    """Lecture directe de la base PostgreSQL d'un Odoo 17 (lecture seule)."""

    nature = "sql"
    TAILLE_LOT = 5000

    def __init__(self, base, societe=None, connexion=None, journal=None):
        self.journal = ou_muet(journal)
        self.journal.dire(
            "Connexion à la base %s (PostgreSQL, lecture seule)" % base
        )
        if connexion is None:
            try:
                import psycopg2  # dépendance optionnelle (ADR-0001)
            except ImportError as exc:
                raise ErreurSource(
                    "Source SQL indisponible : psycopg2 n'est pas installé "
                    "(utilisez --source xmlrpc)."
                ) from exc
            # Hôte, port, utilisateur et mot de passe : variables PG* (libpq).
            connexion = psycopg2.connect(dbname=base)
        connexion.set_session(readonly=True, autocommit=False)
        self._cx = connexion
        self.base = base
        try:
            self.version_serveur = self._version()
            if not self.version_serveur.startswith("17."):
                raise ErreurSource(
                    "Base %s : Odoo %s, cette source ne lit que Odoo 17."
                    % (base, self.version_serveur)
                )
            self.societe = societe or self._societe_unique()
        except Exception:
            connexion.close()  # pas d'Odoo 17 ici : on ne laisse rien ouvert
            raise
        self.journal.dire(
            "Connecté : Odoo %s, société n° %s"
            % (self.version_serveur, self.societe),
            "detail",
        )

    def _requete(self, sql, params=None):
        with self._cx.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()

    def _version(self):
        lignes = self._requete(
            "SELECT latest_version FROM ir_module_module WHERE name = 'base'"
        )
        return lignes[0][0] if lignes else "?"

    def _societe_unique(self):
        ids = [
            r[0]
            for r in self._requete("SELECT id FROM res_company ORDER BY id")
        ]
        if len(ids) != 1:
            raise ErreurSource(
                "Base multi-sociétés (%s) : précisez --societe <id>." % ids
            )
        return ids[0]

    def societe_info(self):
        r = self._requete(
            "SELECT c.name, p.company_registry, p.vat, cur.name FROM res_company c "
            "JOIN res_partner p ON p.id = c.partner_id "
            "JOIN res_currency cur ON cur.id = c.currency_id WHERE c.id = %(s)s",
            {"s": self.societe},
        )[0]
        return {
            "id": self.societe,
            "nom": r[0],
            "siren": r[1] or "",
            "tva": r[2] or "",
            "devise": r[3],
        }

    def lignes(
        self,
        debut=None,
        fin=None,
        etats=("posted",),
        comptes=None,
        ecriture=None,
    ):
        """Lignes d'écritures, triées comme cle_tri. Générateur.

        comptes : liste de codes (grand livre) ; ecriture : id d'une écriture.
        """
        params = {
            "societe": self.societe,
            "etats": list(etats),
            "affichage": list(TYPES_AFFICHAGE),
            "debut": debut,
            "fin": fin,
            "comptes": list(comptes) if comptes else None,
            "ecriture": ecriture,
        }
        bavard = comptes is None and ecriture is None
        if bavard:
            self.journal.dire(
                "Lecture des lignes d'écritures (%s%s)"
                % (
                    ", ".join(
                        {
                            "posted": "validées",
                            "draft": "brouillons",
                            "cancel": "annulées",
                        }.get(e, e)
                        for e in etats
                    ),
                    _periode_texte(debut, fin),
                )
            )
        debut_t = time.monotonic()
        n = 0
        # Curseur nommé = côté serveur : la mémoire reste stable sur 150 000 lignes.
        with self._cx.cursor(name="concorde_lignes") as cur:
            cur.itersize = self.TAILLE_LOT
            cur.execute(_SQL_LIGNES, params)
            for r in cur:
                n += 1
                if bavard and n % PAS_PROGRESSION == 0:
                    self.journal.dire(
                        "… %s lignes lues" % nombre_texte(n), "detail"
                    )
                l = dict(zip(_CHAMPS_LIGNE, r))
                l["debit"] = centimes(l["debit"])
                l["credit"] = centimes(l["credit"])
                l["montant_devise"] = (
                    centimes(l["montant_devise"])
                    if l["montant_devise"] is not None
                    else None
                )
                l["date_lettrage"] = _date(l["date_lettrage"])
                repartition = l["analytique"]
                l["analytique"] = analytique_texte(
                    repartition, self.noms_analytiques()
                )
                l["analytique_comptes"] = analytique_comptes(
                    repartition, self.noms_analytiques()
                )
                for k in (
                    "ecriture",
                    "reference",
                    "compte",
                    "compte_lib",
                    "compte_type",
                    "tiers_ref",
                    "tiers_nom",
                    "libelle",
                    "lettrage",
                    "devise",
                    "journal_lib",
                    "auto_post",
                ):
                    l[k] = l[k] or ""
                yield l
        self._cx.rollback()
        if bavard:
            self.journal.dire(
                "%s lignes lues en %s"
                % (nombre_texte(n), duree_texte(time.monotonic() - debut_t)),
                "ok",
            )

    def noms_analytiques(self):
        """{id: code ou nom} des comptes analytiques (mis en cache)."""
        if getattr(self, "_noms_an", None) is None:
            self._noms_an = {
                r[0]: r[1] or ""
                for r in self._requete(
                    "SELECT id, COALESCE(NULLIF(code, ''), name->>'fr_FR', name->>'en_US') "
                    "FROM account_analytic_account"
                )
            }
        return self._noms_an

    def balance(self, debut=None, fin=None, etats=("posted",)):
        """Balance générale : tous les comptes du plan, mouvementés ou non."""
        t = time.monotonic()
        res = [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "lettrable": bool(r[4]),
                "deprecie": bool(r[5]),
                "debit": centimes(r[6]),
                "credit": centimes(r[7]),
                "lignes": r[8],
                "non_lettrees": r[9],
            }
            for r in self._requete(
                _SQL_BALANCE,
                {
                    "societe": self.societe,
                    "etats": list(etats),
                    "debut": debut,
                    "fin": fin,
                    "affichage": list(TYPES_AFFICHAGE),
                },
            )
        ]
        self.journal.dire(
            "Balance calculée : %s comptes, dont %s mouvementés (%s)"
            % (
                nombre_texte(len(res)),
                nombre_texte(sum(1 for c in res if c["lignes"])),
                duree_texte(time.monotonic() - t),
            ),
            "detail",
        )
        return res

    def balance_tiers(self, debut=None, fin=None, etats=("posted",)):
        """Soldes par compte client / fournisseur et par tiers."""
        return [
            {
                "compte": r[0],
                "tiers_id": r[1],
                "tiers_nom": r[2] or "",
                "tiers_ref": r[3] or "",
                "debit": centimes(r[4]),
                "credit": centimes(r[5]),
                "lignes": r[6],
            }
            for r in self._requete(
                _SQL_BALANCE_TIERS,
                {
                    "societe": self.societe,
                    "etats": list(etats),
                    "debut": debut,
                    "fin": fin,
                    "types": list(TYPES_TIERS),
                },
            )
        ]

    def ecriture(self, ident):
        """Une écriture et ses lignes (toutes états confondus)."""
        return list(self.lignes(etats=ETATS, ecriture=int(ident)))

    def verrous(self):
        r = self._requete(
            "SELECT period_lock_date, fiscalyear_lock_date, tax_lock_date "
            "FROM res_company WHERE id = %(s)s",
            {"s": self.societe},
        )[0]
        return {"periode": r[0], "exercice": r[1], "tva": r[2]}

    def instantane(self):
        """Photo légère de la base, pour repérer les changements entre deux passages."""
        ecritures = {
            str(r[0]): [r[1], str(r[2]), r[3] or ""]
            for r in self._requete(
                "SELECT am.id, am.state, am.write_date, am.name FROM account_move am "
                "WHERE am.company_id = %(s)s",
                {"s": self.societe},
            )
        }
        comptes = {
            str(r[0]): r[1]
            for r in self._requete(
                "SELECT id, code FROM account_account WHERE company_id = %(s)s",
                {"s": self.societe},
            )
        }
        v = self.verrous()
        return {
            "ecritures": ecritures,
            "comptes": comptes,
            "verrous": {
                k: (d.isoformat() if d else None) for k, d in v.items()
            },
        }

    def comptes(self):
        return [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "lettrable": bool(r[4]),
                "deprecie": bool(r[5]),
            }
            for r in self._requete(
                "SELECT id, code, COALESCE(name->>'fr_FR', name->>'en_US'), "
                "account_type, reconcile, deprecated FROM account_account "
                "WHERE company_id = %(s)s ORDER BY code",
                {"s": self.societe},
            )
        ]

    def journaux(self):
        return [
            {
                "id": r[0],
                "code": r[1],
                "libelle": r[2] or "",
                "type": r[3],
                "actif": bool(r[4]),
            }
            for r in self._requete(
                "SELECT id, code, COALESCE(name->>'fr_FR', name->>'en_US'), "
                "type, active FROM account_journal WHERE company_id = %(s)s "
                "ORDER BY code",
                {"s": self.societe},
            )
        ]

    def tiers(self):
        return [
            {
                "id": r[0],
                "nom": r[1] or "",
                "ref": r[2] or "",
                "tva": r[3] or "",
                "siren": r[4] or "",
                "email": r[5] or "",
                "telephone": r[6] or "",
                "rue": r[7] or "",
                "cp": r[8] or "",
                "ville": r[9] or "",
                "pays": r[10] or "",
                "societe": bool(r[11]),
                "actif": bool(r[12]),
                "client": (r[13] or 0) > 0,
                "fournisseur": (r[14] or 0) > 0,
                "parent_id": r[15],
            }
            for r in self._requete(
                "SELECT p.id, p.name, p.ref, p.vat, p.company_registry, p.email, "
                "p.phone, p.street, p.zip, p.city, c.code, p.is_company, p.active, "
                "p.customer_rank, p.supplier_rank, p.parent_id "
                "FROM res_partner p LEFT JOIN res_country c ON c.id = p.country_id "
                "WHERE p.company_id IS NULL OR p.company_id = %(s)s ORDER BY p.id",
                {"s": self.societe},
            )
        ]

    def factures(self, debut=None, fin=None, etats=ETATS):
        res = []
        for r in self._requete(
            "SELECT am.id, am.name, am.move_type, am.state, am.payment_state, "
            "aj.code, rp.id, rp.name, am.date, am.invoice_date, am.invoice_date_due, "
            "am.ref, am.amount_untaxed_signed, am.amount_tax_signed, "
            "am.amount_total_signed, am.amount_residual_signed, cur.name "
            "FROM account_move am JOIN account_journal aj ON aj.id = am.journal_id "
            "LEFT JOIN res_partner rp ON rp.id = am.partner_id "
            "LEFT JOIN res_currency cur ON cur.id = am.currency_id "
            "WHERE am.company_id = %(s)s AND am.move_type = ANY(%(t)s) "
            "AND am.state = ANY(%(e)s) "
            "AND (%(d)s::date IS NULL OR am.date >= %(d)s::date) "
            "AND (%(f)s::date IS NULL OR am.date <= %(f)s::date) "
            "ORDER BY am.date, am.name",
            {
                "s": self.societe,
                "t": list(TYPES_FACTURE),
                "e": list(etats),
                "d": debut,
                "f": fin,
            },
        ):
            res.append(
                {
                    "id": r[0],
                    "numero": r[1] or "",
                    "type_piece": r[2],
                    "etat": r[3],
                    "etat_paiement": r[4] or "",
                    "journal_code": r[5],
                    "tiers_id": r[6],
                    "tiers_nom": r[7] or "",
                    "date": r[8],
                    "date_facture": r[9],
                    "echeance": r[10],
                    "reference": r[11] or "",
                    "ht": centimes(r[12]),
                    "tva": centimes(r[13]),
                    "ttc": centimes(r[14]),
                    "reste_du": centimes(r[15]),
                    "devise": r[16] or "",
                }
            )
        return res

    def fermer(self):
        self._cx.close()


# ---------------------------------------------------------------------------
# Source XML-RPC (API Odoo, lecture seule)
# ---------------------------------------------------------------------------


class SourceXmlRpcOdoo17:
    """Lecture par l'API XML-RPC d'Odoo 17, avec une clé API."""

    nature = "xmlrpc"
    METHODES_AUTORISEES = ("search_read", "read", "fields_get", "search_count")
    TAILLE_LOT = 2000

    def __init__(
        self,
        url,
        base,
        utilisateur,
        cle_api,
        societe=None,
        timeout=120,
        proxy_commun=None,
        proxy_objet=None,
        journal=None,
    ):
        import xmlrpc.client

        self.journal = ou_muet(journal)
        self.journal.dire(
            "Connexion à %s, base %s (API XML-RPC, lecture seule)"
            % (url, base)
        )

        self.url = url.rstrip("/")
        self.base = base
        self._cle = cle_api
        if proxy_objet is None:

            class _Transport(
                xmlrpc.client.SafeTransport
                if self.url.startswith("https")
                else xmlrpc.client.Transport
            ):
                def make_connection(self, host):
                    conn = super().make_connection(host)
                    conn.timeout = timeout
                    return conn

            proxy_commun = xmlrpc.client.ServerProxy(
                self.url + "/xmlrpc/2/common",
                transport=_Transport(),
                allow_none=True,
            )
            proxy_objet = xmlrpc.client.ServerProxy(
                self.url + "/xmlrpc/2/object",
                transport=_Transport(),
                allow_none=True,
            )
        self._objet = proxy_objet
        self.version_serveur = proxy_commun.version().get(
            "server_version", "?"
        )
        if not str(self.version_serveur).startswith("17."):
            raise ErreurSource(
                "Odoo %s : cette source ne lit que Odoo 17."
                % self.version_serveur
            )
        self.uid = proxy_commun.authenticate(base, utilisateur, cle_api, {})
        if not self.uid:
            raise ErreurSource(
                "Authentification refusée : vérifiez l'URL, la base, le login et "
                "la clé API (Préférences > Sécurité du compte > Clés API)."
            )
        self.societe = societe or self._societe_unique()
        self.journal.dire(
            "Connecté : Odoo %s, utilisateur n° %s"
            % (self.version_serveur, self.uid),
            "detail",
        )

    def _appel(self, modele, methode, args, kwargs=None):
        if methode not in self.METHODES_AUTORISEES:
            raise PermissionError(
                "Méthode %r interdite : source en lecture seule." % methode
            )
        kw = dict(kwargs or {})
        kw.setdefault("context", {"lang": "fr_FR", "active_test": False})
        return self._objet.execute_kw(
            self.base, self.uid, self._cle, modele, methode, args, kw
        )

    def _tout_lire(self, modele, domaine, champs):
        """search_read paginé par id croissant (stable même si la base bouge)."""
        res, dernier = [], 0
        while True:
            lot = self._appel(
                modele,
                "search_read",
                [domaine + [("id", ">", dernier)]],
                {"fields": champs, "order": "id", "limit": self.TAILLE_LOT},
            )
            res.extend(lot)
            if len(lot) < self.TAILLE_LOT:
                return res
            dernier = lot[-1]["id"]

    def _societe_unique(self):
        ids = [
            s["id"]
            for s in self._appel(
                "res.company", "search_read", [[]], {"fields": ["id"]}
            )
        ]
        if len(ids) != 1:
            raise ErreurSource(
                "Base multi-sociétés (%s) : précisez --societe <id>." % ids
            )
        return ids[0]

    def societe_info(self):
        s = self._appel(
            "res.company",
            "read",
            [[self.societe]],
            {"fields": ["name", "company_registry", "vat", "currency_id"]},
        )[0]
        return {
            "id": self.societe,
            "nom": s["name"],
            "siren": _texte(s["company_registry"]),
            "tva": _texte(s["vat"]),
            "devise": _m2o(s["currency_id"])[1],
        }

    def lignes(
        self,
        debut=None,
        fin=None,
        etats=("posted",),
        comptes=None,
        ecriture=None,
    ):
        dom = [
            ("company_id", "=", self.societe),
            ("parent_state", "in", list(etats)),
            ("display_type", "not in", list(TYPES_AFFICHAGE)),
        ]
        if comptes:
            dom.append(("account_id.code", "in", list(comptes)))
        if ecriture:
            dom.append(("move_id", "=", int(ecriture)))
        bavard = comptes is None and ecriture is None
        debut_t = time.monotonic()
        if bavard:
            self.journal.dire(
                "Lecture des lignes d'écritures par l'API (%s) — "
                "plus lent qu'en SQL" % _periode_texte(debut, fin).lstrip(", ")
                or "tout"
            )
        if debut:
            dom.append(("date", ">=", str(debut)))
        if fin:
            dom.append(("date", "<=", str(fin)))
        brutes = self._tout_lire(
            "account.move.line",
            dom,
            [
                "move_id",
                "account_id",
                "partner_id",
                "name",
                "debit",
                "credit",
                "matching_number",
                "full_reconcile_id",
                "amount_currency",
                "currency_id",
                "company_currency_id",
                "date_maturity",
                "write_date",
                "analytic_distribution",
            ],
        )
        plan = {c["id"]: c for c in self.comptes()}
        journaux = {j["id"]: j for j in self.journaux()}
        pieces = {}
        for lot in _lots(
            sorted({_m2o(b["move_id"])[0] for b in brutes}), self.TAILLE_LOT
        ):
            for m in self._appel(
                "account.move",
                "read",
                [lot],
                {
                    "fields": [
                        "name",
                        "move_type",
                        "state",
                        "journal_id",
                        "date",
                        "invoice_date",
                        "ref",
                        "write_date",
                        "auto_post",
                    ]
                },
            ):
                pieces[m["id"]] = m
        ids_tiers = sorted({_m2o(b["partner_id"])[0] for b in brutes} - {None})
        tiers = {}
        for lot in _lots(ids_tiers, self.TAILLE_LOT):
            for p in self._appel(
                "res.partner", "read", [lot], {"fields": ["name", "ref"]}
            ):
                tiers[p["id"]] = p
        ids_rec = sorted(
            {_m2o(b["full_reconcile_id"])[0] for b in brutes} - {None}
        )
        rapprochements = {}
        for lot in _lots(ids_rec, self.TAILLE_LOT):
            for r in self._appel(
                "account.full.reconcile",
                "read",
                [lot],
                {"fields": ["create_date"]},
            ):
                rapprochements[r["id"]] = _date(r["create_date"])
        res = []
        for b in brutes:
            m = pieces[_m2o(b["move_id"])[0]]
            j = journaux.get(_m2o(m["journal_id"])[0], {})
            c = plan.get(_m2o(b["account_id"])[0], {})
            tid = _m2o(b["partner_id"])[0]
            t = tiers.get(tid, {})
            rec_id = _m2o(b["full_reconcile_id"])[0]
            devise_etr = (
                _m2o(b["currency_id"])[0] != _m2o(b["company_currency_id"])[0]
            )
            res.append(
                {
                    "ligne_id": b["id"],
                    "ecriture_id": m["id"],
                    "ecriture": _texte(m["name"]),
                    "type_piece": m["move_type"],
                    "etat": m["state"],
                    "journal_code": j.get("code", ""),
                    "journal_lib": j.get("libelle", ""),
                    "date": _date(m["date"]),
                    "piece_date": _date(m["invoice_date"]),
                    "reference": _texte(m["ref"]),
                    "compte": c.get("code", ""),
                    "compte_lib": c.get("libelle", ""),
                    "compte_type": c.get("type", ""),
                    "tiers_id": tid,
                    "tiers_ref": _texte(t.get("ref")),
                    "tiers_nom": _texte(t.get("name")),
                    "libelle": _texte(b["name"]),
                    "debit": centimes(b["debit"]),
                    "credit": centimes(b["credit"]),
                    "lettrage": _texte(b["matching_number"]) if rec_id else "",
                    "date_lettrage": (
                        rapprochements.get(rec_id) if rec_id else None
                    ),
                    "montant_devise": (
                        centimes(b["amount_currency"]) if devise_etr else None
                    ),
                    "devise": _m2o(b["currency_id"])[1] if devise_etr else "",
                    "echeance": _date(b["date_maturity"]),
                    "modifie_le": max(
                        str(m["write_date"]), str(b["write_date"])
                    ),
                    "auto_post": _texte(m.get("auto_post")),
                    "analytique": analytique_texte(
                        b.get("analytic_distribution"), self.noms_analytiques()
                    ),
                    "analytique_comptes": analytique_comptes(
                        b.get("analytic_distribution"), self.noms_analytiques()
                    ),
                }
            )
        # Filtre redondant côté CONCORDE : on ne fait pas aveuglément confiance au domaine.
        if comptes:
            res = [l for l in res if l["compte"] in set(comptes)]
        if ecriture:
            res = [l for l in res if l["ecriture_id"] == int(ecriture)]
        res.sort(key=cle_tri)
        if bavard:
            self.journal.dire(
                "%s lignes lues en %s"
                % (
                    nombre_texte(len(res)),
                    duree_texte(time.monotonic() - debut_t),
                ),
                "ok",
            )
        return res

    def noms_analytiques(self):
        if getattr(self, "_noms_an", None) is None:
            try:
                self._noms_an = {
                    a["id"]: _texte(a.get("code")) or _texte(a.get("name"))
                    for a in self._tout_lire(
                        "account.analytic.account", [], ["code", "name"]
                    )
                }
            except (
                Exception
            ) as exc:  # module absent ou droits insuffisants : on continue
                self._noms_an = {}
                self.journal.dire(
                    "Comptes analytiques illisibles (%s) : affichés par numéro"
                    % str(exc).splitlines()[-1][:120],
                    "alerte",
                )
        return self._noms_an

    def balance(self, debut=None, fin=None, etats=("posted",)):
        return balance_depuis_lignes(
            self.comptes(), self.lignes(debut, fin, etats)
        )

    def balance_tiers(self, debut=None, fin=None, etats=("posted",)):
        return balance_tiers_depuis_lignes(self.lignes(debut, fin, etats))

    def ecriture(self, ident):
        return self.lignes(etats=ETATS, ecriture=int(ident))

    def verrous(self):
        s = self._appel(
            "res.company",
            "read",
            [[self.societe]],
            {
                "fields": [
                    "period_lock_date",
                    "fiscalyear_lock_date",
                    "tax_lock_date",
                ]
            },
        )[0]
        return {
            "periode": _date(s["period_lock_date"]),
            "exercice": _date(s["fiscalyear_lock_date"]),
            "tva": _date(s["tax_lock_date"]),
        }

    def instantane(self):
        ecritures = {
            str(m["id"]): [m["state"], str(m["write_date"]), _texte(m["name"])]
            for m in self._tout_lire(
                "account.move",
                [("company_id", "=", self.societe)],
                ["state", "write_date", "name"],
            )
        }
        comptes = {str(c["id"]): c["code"] for c in self.comptes()}
        v = self.verrous()
        return {
            "ecritures": ecritures,
            "comptes": comptes,
            "verrous": {
                k: (d.isoformat() if d else None) for k, d in v.items()
            },
        }

    def comptes(self):
        return [
            {
                "id": c["id"],
                "code": c["code"],
                "libelle": _texte(c["name"]),
                "type": c["account_type"],
                "lettrable": bool(c["reconcile"]),
                "deprecie": bool(c["deprecated"]),
            }
            for c in self._tout_lire(
                "account.account",
                [("company_id", "=", self.societe)],
                ["code", "name", "account_type", "reconcile", "deprecated"],
            )
        ]

    def journaux(self):
        return [
            {
                "id": j["id"],
                "code": j["code"],
                "libelle": _texte(j["name"]),
                "type": j["type"],
                "actif": bool(j["active"]),
            }
            for j in self._tout_lire(
                "account.journal",
                [("company_id", "=", self.societe)],
                ["code", "name", "type", "active"],
            )
        ]

    def tiers(self):
        res = []
        for p in self._tout_lire(
            "res.partner",
            [
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.societe),
            ],
            [
                "name",
                "ref",
                "vat",
                "company_registry",
                "email",
                "phone",
                "street",
                "zip",
                "city",
                "country_code",
                "is_company",
                "active",
                "customer_rank",
                "supplier_rank",
                "parent_id",
            ],
        ):
            res.append(
                {
                    "id": p["id"],
                    "nom": _texte(p["name"]),
                    "ref": _texte(p["ref"]),
                    "tva": _texte(p["vat"]),
                    "siren": _texte(p["company_registry"]),
                    "email": _texte(p["email"]),
                    "telephone": _texte(p["phone"]),
                    "rue": _texte(p["street"]),
                    "cp": _texte(p["zip"]),
                    "ville": _texte(p["city"]),
                    "pays": _texte(p["country_code"]),
                    "societe": bool(p["is_company"]),
                    "actif": bool(p["active"]),
                    "client": (p["customer_rank"] or 0) > 0,
                    "fournisseur": (p["supplier_rank"] or 0) > 0,
                    "parent_id": _m2o(p["parent_id"])[0],
                }
            )
        return res

    def factures(self, debut=None, fin=None, etats=ETATS):
        dom = [
            ("company_id", "=", self.societe),
            ("move_type", "in", list(TYPES_FACTURE)),
            ("state", "in", list(etats)),
        ]
        if debut:
            dom.append(("date", ">=", str(debut)))
        if fin:
            dom.append(("date", "<=", str(fin)))
        journaux = {j["id"]: j["code"] for j in self.journaux()}
        res = []
        for f in self._tout_lire(
            "account.move",
            dom,
            [
                "name",
                "move_type",
                "state",
                "payment_state",
                "journal_id",
                "partner_id",
                "date",
                "invoice_date",
                "invoice_date_due",
                "ref",
                "amount_untaxed_signed",
                "amount_tax_signed",
                "amount_total_signed",
                "amount_residual_signed",
                "currency_id",
            ],
        ):
            tid, tnom = _m2o(f["partner_id"])
            res.append(
                {
                    "id": f["id"],
                    "numero": _texte(f["name"]),
                    "type_piece": f["move_type"],
                    "etat": f["state"],
                    "etat_paiement": _texte(f["payment_state"]),
                    "journal_code": journaux.get(_m2o(f["journal_id"])[0], ""),
                    "tiers_id": tid,
                    "tiers_nom": tnom,
                    "date": _date(f["date"]),
                    "date_facture": _date(f["invoice_date"]),
                    "echeance": _date(f["invoice_date_due"]),
                    "reference": _texte(f["ref"]),
                    "ht": centimes(f["amount_untaxed_signed"]),
                    "tva": centimes(f["amount_tax_signed"]),
                    "ttc": centimes(f["amount_total_signed"]),
                    "reste_du": centimes(f["amount_residual_signed"]),
                    "devise": _m2o(f["currency_id"])[1],
                }
            )
        res.sort(key=lambda f: (f["date"] or date.min, f["numero"]))
        return res

    def fermer(self):
        pass
