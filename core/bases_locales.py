# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Suppression et réinitialisation des bases Odoo LOCALES, révocation de clés API (ADR-0005).

Ce que ce module permet :
  - supprimer une base Odoo 17 du serveur local (copie de base client, base de test),
    APRÈS une sauvegarde complète vérifiée ;
  - réinitialiser une base de test depuis son modèle vierge (PostgreSQL TEMPLATE) ;
  - lister et révoquer les clés API d'une base Odoo 17 du serveur (la valeur secrète
    d'une clé n'est jamais lue ni affichée).

Ce qui est IMPOSSIBLE par construction (arbitrage de Stéphane, 06/11/2026) :
  supprimer une base chez un client. Aucune fonction ne prend une URL, une base
  distante (« xmlrpc:… ») ou un hôte PostgreSQL non local ; aucun code de CONCORDE
  n'appelle le service de gestion des bases d'un Odoo (tests/test_bases_locales.py
  le vérifie sur tout le dépôt).

Garde-fous, dans l'ordre — le premier qui échoue arrête tout :
  1. hôte PostgreSQL local (boucle locale, socket, réseau Docker 172.16.0.0/12) ;
  2. base présente dans la liste des bases Odoo 17 locales (pas une autre application) ;
  3. base non protégée (CONCORDE_BASES_PROTEGEES, défaut : « concorde ») ;
  4. aucune tâche CONCORDE en cours sur la base ;
  5. confirmation = nom exact de la base, retapé ;
  6. copie de base client : sauvegarde pg_dump complète, relue (pg_restore --list),
     avant de supprimer ; si elle échoue, rien n'est supprimé.
Base de TEST (celle qui a un modèle vierge « <nom>_modele ») : pas de sauvegarde, son
contenu est jetable par définition (arbitrage de Stéphane, 06/11/2026). C'est l'existence
du modèle, lue côté serveur, qui en décide — jamais un paramètre venu de l'écran.
Sauvegardes gardées 7 jours (CONCORDE_SAUVEGARDE_JOURS), puis effacées.
"""
import ipaddress
import os
import re
import subprocess
import time
from datetime import datetime

from .journal import duree_texte, ou_muet


def _retention():
    try:
        return max(1, int(os.environ.get("CONCORDE_SAUVEGARDE_JOURS", "7")))
    except ValueError:
        return 7


RETENTION_JOURS = _retention()
PROTEGEES_DEFAUT = ("concorde",)
SYSTEME = ("postgres", "template0", "template1")
_NOM_VALIDE = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")


class SuppressionInterdite(PermissionError):
    """Opération refusée par un garde-fou (jamais contournable par un paramètre)."""


def protegees():
    brut = os.environ.get("CONCORDE_BASES_PROTEGEES")
    noms = PROTEGEES_DEFAUT if brut is None else [n.strip() for n in brut.split(",")]
    return set(n for n in noms if n) | set(SYSTEME)


def verifier_hote_local(hote=None):
    """Refuse tout hôte PostgreSQL qui n'est pas ce serveur (ou son réseau Docker)."""
    hote = os.environ.get("PGHOST", "") if hote is None else hote
    if hote in ("", "localhost") or hote.startswith("/"):
        return
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        raise SuppressionInterdite(
            "Hôte PostgreSQL %r : nom non vérifiable, suppression refusée "
            "(seules les bases de ce serveur peuvent être supprimées)." % hote)
    if not (ip.is_loopback or ip in ipaddress.ip_network("172.16.0.0/12")):
        raise SuppressionInterdite(
            "Hôte PostgreSQL %s : ce n'est pas ce serveur. Supprimer une base ailleurs "
            "(chez un client) est interdit." % hote)


def _identifiant_sql(nom_base):
    """Nom de base vérifié et entre guillemets doubles, prêt pour le SQL.

    Rôle : seule façon d'insérer un nom de base dans une requête
    (DROP, CREATE).
    Paramètres : nom_base (str), nom de base ou de modèle.
    Retour : '"nom_base"'.
    Erreurs : SuppressionInterdite si le nom ne respecte pas _NOM_VALIDE
    (lettres, chiffres, « _ . - », 63 caractères au plus : jamais de
    guillemet).
    Usages : supprimer(), reinitialiser().
    """
    nom_conforme = isinstance(nom_base, str) and _NOM_VALIDE.match(nom_base)
    if not nom_conforme:
        raise SuppressionInterdite(
            "Nom de base invalide : %r." % (nom_base,))
    return '"%s"' % nom_base


def _verifier(nom, bases_locales, en_cours, confirmation):
    if not isinstance(nom, str) or ":" in nom or "/" in nom:
        raise SuppressionInterdite(
            "%r n'est pas une base locale : supprimer une base distante (chez un client) "
            "est interdit par conception. Pour la sortir de CONCORDE, utilisez « Retirer »."
            % (nom,))
    if not _NOM_VALIDE.match(nom):
        raise SuppressionInterdite("Nom de base invalide : %r." % nom)
    verifier_hote_local()
    if nom not in bases_locales:
        raise SuppressionInterdite(
            "« %s » n'est pas une base Odoo 17 de ce serveur : CONCORDE ne la supprimera pas."
            % nom)
    if nom in protegees():
        raise SuppressionInterdite("« %s » est protégée (CONCORDE_BASES_PROTEGEES)." % nom)
    if nom in en_cours:
        raise SuppressionInterdite("Une tâche CONCORDE travaille sur « %s » : attendez sa fin."
                                   % nom)
    if confirmation != nom:
        raise SuppressionInterdite("Confirmation incorrecte : retapez exactement « %s »." % nom)


def _connexion_admin():
    import psycopg2
    cx = psycopg2.connect(dbname="postgres", connect_timeout=10)
    cx.autocommit = True
    return cx


def sauvegarder(nom, dossier, journal=None):
    """pg_dump complet (format custom), relu par pg_restore --list. Retourne le chemin."""
    j = ou_muet(journal)
    os.makedirs(dossier, mode=0o700, exist_ok=True)
    chemin = os.path.join(dossier, "%s_%s.dump" % (nom, datetime.now().strftime("%Y%m%d-%H%M%S")))
    tmp = chemin + ".partiel"
    debut = time.monotonic()
    j.dire("Sauvegarde de « %s » (pg_dump)…" % nom, "etape")
    r = subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", tmp, "--dbname",
                        nom], capture_output=True, text=True, timeout=3600)
    if r.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("Sauvegarde échouée, rien n'est supprimé : %s"
                           % (r.stderr.strip()[-300:] or "fichier vide"))
    v = subprocess.run(["pg_restore", "--list", tmp], capture_output=True, text=True,
                       timeout=600)
    objets = sum(1 for l in v.stdout.splitlines() if l and not l.startswith(";"))
    if v.returncode != 0 or objets == 0:
        os.remove(tmp)
        raise RuntimeError("Sauvegarde illisible (pg_restore --list), rien n'est supprimé.")
    os.replace(tmp, chemin)
    j.dire("✓ Sauvegarde vérifiée : %s (%.1f Mo, %d objets, %s)" % (
        os.path.basename(chemin), os.path.getsize(chemin) / 1e6, objets,
        duree_texte(time.monotonic() - debut)), "ok")
    return chemin


def supprimer(nom, confirmation, bases_locales, dossier_sauvegardes, en_cours=(),
              journal=None, connexion=None, fonction_sauvegarde=sauvegarder, modeles=None):
    """Supprime une base Odoo 17 LOCALE. Retourne le chemin de la sauvegarde (None pour
    une base de test, c'est-à-dire une base qui a un modèle vierge dans `modeles`)."""
    j = ou_muet(journal)
    _verifier(nom, set(bases_locales), set(en_cours), confirmation)
    j.dire("Garde-fous passés pour « %s » : base locale, non protégée, confirmation exacte"
           % nom, "detail")
    base_de_test = nom in (modeles or {})
    if base_de_test:
        chemin = None
        j.dire("Base de test (modèle vierge « %s ») : pas de sauvegarde" % modeles[nom],
               "detail")
    else:
        chemin = fonction_sauvegarde(nom, dossier_sauvegardes, journal=j)
    cx = connexion or _connexion_admin()
    try:
        with cx.cursor() as cur:
            j.dire("Suppression de « %s » (connexions ouvertes fermées)…" % nom, "etape")
            cur.execute("DROP DATABASE %s WITH (FORCE)" % _identifiant_sql(nom))
    finally:
        if connexion is None:
            cx.close()
    j.dire("✓ Base « %s » supprimée. %s" % (nom, "Sauvegarde : %s (gardée %d jours)" % (
        os.path.basename(chemin), _retention()) if chemin else "Pas de sauvegarde (base de test)."),
        "ok")
    j.dire("Les pièces jointes (filestore) de « %s » restent dans le volume Docker d'Odoo ; "
           "à nettoyer par root si besoin." % nom, "detail")
    return chemin


def reinitialiser(nom, confirmation, bases_locales, modeles, dossier_sauvegardes,
                  en_cours=(), journal=None, connexion=None, fonction_sauvegarde=sauvegarder):
    """Supprime la base de test (sans sauvegarde) puis la recrée vierge depuis son modèle.

    modeles : {base : modèle}, lu côté serveur (lister_modeles()).
    """
    j = ou_muet(journal)
    modele = (modeles or {}).get(nom)
    if not modele:
        raise SuppressionInterdite("« %s » n'a pas de modèle vierge : ce n'est pas une base de "
                                   "test, elle ne se réinitialise pas." % nom)
    # Modèle vérifié AVANT la suppression : un refus ne laisse jamais
    # la base supprimée sans recréation.
    identifiant_modele = _identifiant_sql(modele)
    cx = connexion or _connexion_admin()
    try:
        chemin = supprimer(nom, confirmation, bases_locales, dossier_sauvegardes, en_cours,
                           j, cx, fonction_sauvegarde, modeles)
        with cx.cursor() as cur:
            j.dire("Recréation de « %s » depuis le modèle vierge « %s »…" % (nom, modele), "etape")
            cur.execute("CREATE DATABASE %s TEMPLATE %s"
                        % (_identifiant_sql(nom), identifiant_modele))
        j.dire("✓ « %s » est de nouveau vierge" % nom, "ok")
    finally:
        if connexion is None:
            cx.close()
    return chemin


def lister_modeles():
    """Bases modèles (PostgreSQL TEMPLATE) : {nom de base : nom du modèle}."""
    cx = _connexion_admin()
    try:
        with cx.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate "
                        "AND datname LIKE '%%\\_modele'")
            noms = [r[0] for r in cur.fetchall()]
    finally:
        cx.close()
    return {n[:-len("_modele")]: n for n in noms}


def purger_sauvegardes(dossier, jours=None, journal=None):
    j = ou_muet(journal)
    jours = jours or _retention()
    if not os.path.isdir(dossier):
        return []
    limite = time.time() - jours * 86400
    retirees = []
    for f in sorted(os.listdir(dossier)):
        chemin = os.path.join(dossier, f)
        if f.endswith(".dump") and os.path.getmtime(chemin) < limite:
            os.remove(chemin)
            retirees.append(f)
            j.dire("Sauvegarde de plus de %d jours effacée : %s" % (jours, f), "detail")
    return retirees


def lister_sauvegardes(dossier):
    if not os.path.isdir(dossier):
        return []
    res = []
    for f in sorted(os.listdir(dossier), reverse=True):
        if f.endswith(".dump"):
            chemin = os.path.join(dossier, f)
            res.append({"fichier": f, "taille": os.path.getsize(chemin),
                        "date": datetime.fromtimestamp(os.path.getmtime(chemin))
                        .isoformat(timespec="seconds"),
                        "base": f.rsplit("_", 2)[0]})
    return res


# ---------------------------------------------------------------------------
# Clés API des bases Odoo 17 du serveur
# ---------------------------------------------------------------------------

def _connexion_base(nom, ecriture=False):
    import psycopg2
    cx = psycopg2.connect(dbname=nom, connect_timeout=10)
    if ecriture:
        cx.autocommit = True
    else:
        cx.set_session(readonly=True, autocommit=True)
    return cx


def lister_cles_api(bases_locales, connexion=None):
    """Clés API de chaque base locale : nom, utilisateur, portée, date. Jamais la clé."""
    verifier_hote_local()
    res = []
    for nom in bases_locales:
        cx = connexion or _connexion_base(nom)
        try:
            with cx.cursor() as cur:
                cur.execute("SELECT k.id, k.name, u.login, k.scope, k.create_date "
                            "FROM res_users_apikeys k JOIN res_users u ON u.id = k.user_id "
                            "ORDER BY k.create_date")
                for r in cur.fetchall():
                    res.append({"base": nom, "id": r[0], "nom": r[1] or "", "login": r[2],
                                "portee": r[3] or "toutes", "cree_le": r[4]})
        finally:
            if connexion is None:
                cx.close()
    return res


def revoquer_cle_api(base, ident, confirmation, bases_locales, journal=None, connexion=None):
    """Révoque UNE clé API d'une base Odoo 17 du serveur. Retourne son nom.

    Garde-fous : hôte local, base locale, clé existante, nom de la clé retapé.
    Seule la ligne de cette clé est supprimée (res_users_apikeys) : Odoo la refuse
    dès la requête suivante. Jamais sur une base distante (chez un client).
    """
    j = ou_muet(journal)
    if not isinstance(base, str) or ":" in base or "/" in base:
        raise SuppressionInterdite("%r n'est pas une base de ce serveur : CONCORDE ne révoque "
                                   "pas de clé chez un client." % (base,))
    verifier_hote_local()
    if base not in set(bases_locales):
        raise SuppressionInterdite("« %s » n'est pas une base Odoo 17 de ce serveur." % base)
    try:
        ident = int(ident)
    except (TypeError, ValueError):
        raise SuppressionInterdite("Identifiant de clé invalide : %r." % (ident,))
    cx = connexion or _connexion_base(base, ecriture=True)
    try:
        with cx.cursor() as cur:
            cur.execute("SELECT name FROM res_users_apikeys WHERE id = %s", (ident,))
            ligne = cur.fetchone()
            if not ligne:
                raise SuppressionInterdite("Clé n° %d introuvable dans « %s »." % (ident, base))
            nom_cle = ligne[0] or ""
            if confirmation != nom_cle:
                raise SuppressionInterdite("Confirmation incorrecte : retapez exactement « %s »."
                                           % nom_cle)
            cur.execute("DELETE FROM res_users_apikeys WHERE id = %s", (ident,))
            if cur.rowcount != 1:
                raise RuntimeError("Révocation incertaine (%d ligne(s)) : vérifiez dans Odoo."
                                   % cur.rowcount)
    finally:
        if connexion is None:
            cx.close()
    j.dire("✓ Clé API « %s » révoquée dans la base « %s »" % (nom_cle, base), "ok")
    return nom_cle
