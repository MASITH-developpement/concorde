#!/usr/bin/env python3
# CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Surveillance de sécurité du serveur : mineurs, rançongiciels, antivirus (ADR-0007).

Deux commandes, lancées par systemd en ROOT (il faut lire tous les processus, les
conteneurs Docker et les bases PostgreSQL) :

  controle   toutes les 15 minutes — contrôle ciblé, léger :
             processus lancés depuis /tmp, /var/tmp, /dev/shm ou dont le fichier a été
             effacé ; noms et arguments de mineurs connus ; processus qui saturent le
             processeur ; connexions vers des ports de minage ou des adresses d'attaquants
             connues ; PostgreSQL : super-utilisateurs inconnus, bases de rançon,
             accès réseau sans mot de passe ; base de données exposée sur Internet ;
             persistance (ld.so.preload, tâches planifiées, clés SSH récentes) ;
             notes de rançon et fichiers chiffrés récents ; fraîcheur des signatures ClamAV.
  antivirus  chaque nuit — analyse ClamAV (détection des mineurs « PUA » activée) des
             zones sensibles, y compris les couches modifiables et les volumes des
             conteneurs Docker (le mineur du 01/11/2026 était dans le /tmp d'un conteneur).

Résultats : /var/lib/concorde-securite/{controle,antivirus}.json (lisibles par l'interface
CONCORDE, qui en fait des alertes « techniques » expliquées par Marceau). Aucun secret
n'y est écrit. Lecture seule : ce programme ne tue rien et n'efface rien.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from core.analyser import Rapport                                   # noqa: E402

SORTIE = os.environ.get("CONCORDE_SECURITE_DOSSIER", "/var/lib/concorde-securite")
CONFIG = os.environ.get("CONCORDE_SECURITE_CONFIG", "/etc/concorde/securite.json")

DEFAUTS = {
    # Super-utilisateurs PostgreSQL attendus, par conteneur. Tout autre = alerte.
    "superutilisateurs_autorises": {
        "concorde-postgres": ["odoo"],
        "azalplus-v2-postgres-1": ["postgres", "azalplus_admin", "azalplus"],
    },
    # Ports publiés par Docker sur Internet, connus et acceptés (Odoo, aperçu AzalPlus).
    "ports_publics_acceptes": [8017, 8021, 8080],
    # Processus autorisés à beaucoup consommer (nom de l'exécutable).
    "processus_gourmands_autorises": ["clamscan", "freshclam", "claude", "node", "apt",
                                      "dpkg", "pg_dump", "pg_restore", "python3", "postgres"],
    "seuil_cpu": 80,
    "duree_min_s": 600,
}
PORTS_BASES = {5432: "PostgreSQL", 3306: "MySQL/MariaDB", 6379: "Redis", 27017: "MongoDB",
               9200: "Elasticsearch", 5984: "CouchDB", 11211: "Memcached"}
PORTS_MINAGE = {3333, 4444, 5555, 7777, 14433, 14444, 45560, 45700, 44999, 48996}
# Indicateurs de l'attaque du 01/11/2026 (rapport /root/quarantaine_mineur_20261106).
IP_ATTAQUANTS = {"91.188.254.62", "5.255.109.74", "5.255.115.190"}
MOTS_MINEUR = re.compile(r"xmrig|minerd|cpuminer|kinsing|kdevtmpfsi|stratum\+(tcp|ssl)|"
                         r"cryptonight|randomx|--donate-level|nicehash|anondns\.net", re.I)
DOSSIERS_TEMP = ("/tmp/", "/var/tmp/", "/dev/shm/")
NOMS_RANCON = re.compile(r"(readme|read_me|how_to|restore|recover|decrypt|warning|ransom|"
                         r"bitcoin|pay_?me|backup_?your)", re.I)
FICHIERS_RANCON = re.compile(r"(readme.*(decrypt|recover|restore)|how_to_(decrypt|recover|"
                             r"restore)|_readme\.txt$|restore_files|\.(locked|encrypted|"
                             r"crypted|enc|ransom)$)", re.I)
ZONES_RANCON = ["/home", "/root", "/opt", "/var/lib/docker/volumes", "/var/www", "/srv"]


def config():
    c = json.loads(json.dumps(DEFAUTS))
    if os.path.isfile(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            c.update(json.load(f))
    return c


def cmd(args, timeout=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ecrire(nom, rapport, debut):
    os.makedirs(SORTIE, mode=0o755, exist_ok=True)
    d = rapport.en_dict(complet=False)
    d["date"] = datetime.now().isoformat(timespec="seconds")
    d["duree_s"] = round(time.monotonic() - debut, 1)
    tmp = os.path.join(SORTIE, nom + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, default=str)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(SORTIE, nom + ".json"))
    print("%s : %s — %d bloquant, %d alerte, %d info (%s s)" % (
        nom, d["statut"], d["synthese"]["BLOQUANT"], d["synthese"]["ALERTE"],
        d["synthese"]["INFO"], d["duree_s"]))
    for c in d["constats"]:
        print("  [%s] %s : %s" % (c["niveau"], c["message"], "; ".join(c["exemples"][:3])))
    return d


# ---------------------------------------------------------------------------
# Contrôle ciblé (15 min)
# ---------------------------------------------------------------------------

def processus():
    """[(pid, user, pcpu, etime_s, comm, args, exe)] de tous les processus (hôte + conteneurs)."""
    res = []
    for ligne in cmd(["ps", "-eo", "pid=,user=,pcpu=,etimes=,comm=,args="]).splitlines():
        p = ligne.split(None, 5)
        if len(p) < 5:
            continue
        pid = p[0]
        try:
            exe = os.readlink("/proc/%s/exe" % pid)
        except OSError:
            exe = ""
        res.append((int(pid), p[1], float(p[2]), int(p[3]), p[4], p[5] if len(p) > 5 else "",
                    exe))
    return res


def controler_processus(r, c):
    procs = processus()
    soi = os.getpid()
    temp, efface, mineurs, gourmands = [], [], [], []
    for pid, user, cpu, duree, comm, args, exe in procs:
        if pid == soi:
            continue
        nom = "pid %d %s (%s) : %s" % (pid, comm, user, (args or exe)[:120])
        chemin = exe.replace(" (deleted)", "")
        if chemin.startswith(DOSSIERS_TEMP) and "/claude-" not in chemin:
            temp.append(nom + " — exécutable " + exe)
        elif exe.endswith(" (deleted)") and comm not in ("claude", "node") and \
                not exe.startswith(("/usr/", "/lib", "/opt/")):
            efface.append(nom + " — exécutable effacé " + exe)
        if MOTS_MINEUR.search(args) or MOTS_MINEUR.search(comm) or MOTS_MINEUR.search(exe):
            mineurs.append(nom)
        if cpu >= c["seuil_cpu"] and duree >= c["duree_min_s"] and \
                comm not in c["processus_gourmands_autorises"]:
            gourmands.append("%s — %.0f %% du processeur depuis %d min" % (nom, cpu, duree // 60))
    r.info("processus", len(procs))
    r.constat("BLOQUANT", "SEC_PROCESSUS_TEMP", "Programme lancé depuis un dossier temporaire",
              temp)
    r.constat("ALERTE", "SEC_EXECUTABLE_EFFACE", "Programme dont le fichier a été effacé",
              efface)
    r.constat("BLOQUANT", "SEC_MINEUR_CONNU", "Signature de mineur dans un processus", mineurs)
    r.constat("ALERTE", "SEC_PROCESSEUR_SATURE", "Processus qui sature le processeur", gourmands)
    charge = os.getloadavg()[1]
    r.info("charge_5min", round(charge, 2))
    if charge > 2 * (os.cpu_count() or 1):
        r.constat("ALERTE", "SEC_PROCESSEUR_SATURE", "Serveur surchargé",
                  ["charge moyenne 5 min : %.2f pour %d cœur(s)" % (charge, os.cpu_count() or 1)])


def controler_reseau(r):
    minage, attaquants = [], []
    for ligne in cmd(["ss", "-tnpH", "state", "established"]).splitlines():
        p = ligne.split()
        if len(p) < 4:
            continue
        distant = p[3]
        ip, _, port = distant.rpartition(":")
        ip = ip.strip("[]")
        proc = re.search(r'"([^"]+)",pid=(\d+)', ligne)
        qui = "%s (pid %s)" % proc.groups() if proc else "?"
        if ip in IP_ATTAQUANTS:
            attaquants.append("%s vers %s" % (qui, distant))
        elif port.isdigit() and int(port) in PORTS_MINAGE and not ip.startswith(("127.", "172.")):
            minage.append("%s vers %s" % (qui, distant))
    # Les connexions des conteneurs sont dans leurs propres espaces réseau : on les lit via /proc.
    vus = set()
    for pid in [d for d in os.listdir("/proc") if d.isdigit()]:
        try:
            ns = os.readlink("/proc/%s/ns/net" % pid)
        except OSError:
            continue
        if ns in vus:
            continue
        vus.add(ns)
        for ligne in cmd(["nsenter", "-t", pid, "-n", "ss", "-tnH", "state", "established"],
                         timeout=10).splitlines():
            p = ligne.split()
            if len(p) < 4:
                continue
            ip, _, port = p[3].rpartition(":")
            ip = ip.strip("[]")
            if ip in IP_ATTAQUANTS:
                attaquants.append("espace réseau du pid %s vers %s" % (pid, p[3]))
            elif port.isdigit() and int(port) in PORTS_MINAGE and \
                    not ip.startswith(("127.", "172.", "10.", "192.168.")):
                minage.append("espace réseau du pid %s vers %s" % (pid, p[3]))
    r.constat("BLOQUANT", "SEC_CONNEXION_ATTAQUANT",
              "Connexion vers une adresse d'attaquant connue", sorted(set(attaquants)))
    r.constat("ALERTE", "SEC_PORT_MINAGE", "Connexion vers un port de minage",
              sorted(set(minage)))


def conteneurs():
    """{nom: (image, ports publiés [(hôte, port_hôte, port_conteneur)], env)}"""
    res = {}
    for nom in cmd(["docker", "ps", "--format", "{{.Names}}"]).split():
        brut = cmd(["docker", "inspect", nom])
        try:
            d = json.loads(brut)[0]
        except (ValueError, IndexError):
            continue
        ports = []
        for cport, liens in (d["HostConfig"].get("PortBindings") or {}).items():
            for lien in liens or []:
                ports.append((lien.get("HostIp") or "0.0.0.0", int(lien.get("HostPort") or 0),
                              int(cport.split("/")[0])))
        env = dict(e.split("=", 1) for e in d["Config"].get("Env") or [] if "=" in e)
        res[nom] = (d["Config"]["Image"], ports, env)
    return res


def controler_exposition(r, c, ctrs):
    bases, autres = [], []
    for nom, (image, ports, _) in ctrs.items():
        for hote, port_h, port_c in ports:
            public = hote in ("0.0.0.0", "::", "")
            if not public:
                continue
            if port_c in PORTS_BASES or port_h in PORTS_BASES:
                bases.append("%s : %s publié sur Internet (port %d) — Docker passe devant UFW" % (
                    nom, PORTS_BASES.get(port_c, PORTS_BASES.get(port_h)), port_h))
            elif port_h not in c["ports_publics_acceptes"]:
                autres.append("%s : port %d publié sur Internet" % (nom, port_h))
    r.constat("BLOQUANT", "SEC_BASE_EXPOSEE", "Base de données ouverte sur Internet", bases)
    r.constat("ALERTE", "SEC_PORT_PUBLIC_INCONNU", "Port Docker publié sur Internet, non prévu",
              autres)


def psql(conteneur, user, sql, base="postgres"):
    return cmd(["docker", "exec", conteneur, "psql", "-U", user, "-d", base, "-AtXq", "-c", sql],
               timeout=20)


def controler_postgresql(r, c, ctrs):
    supers, rancons, trust, tables = [], [], [], []
    autorises = c["superutilisateurs_autorises"]
    for nom, (image, _, env) in ctrs.items():
        if not image.startswith("postgres"):
            continue
        user = env.get("POSTGRES_USER", "postgres")
        roles = psql(nom, user, "SELECT rolname FROM pg_roles WHERE rolsuper "
                                "AND rolname !~ '^pg_'").split()
        for role in roles:
            if role not in autorises.get(nom, [user]):
                supers.append("%s : super-utilisateur « %s » inconnu" % (nom, role))
        bases = psql(nom, user, "SELECT datname FROM pg_database WHERE datallowconn").split()
        for b in bases:
            if NOMS_RANCON.search(b):
                rancons.append("%s : base « %s »" % (nom, b))
            t = psql(nom, user, "SELECT schemaname||'.'||tablename FROM pg_tables WHERE "
                                "tablename ~* '^(readme|read_me|readme_to_recover|recover|"
                                "warning|ransom|cmd_exec|tests)$' AND schemaname NOT IN "
                                "('pg_catalog','information_schema')", b).split()
            tables += ["%s / %s : table « %s »" % (nom, b, x) for x in t]
        for ligne in psql(nom, user, "SELECT type||' '||array_to_string(database,',')||' '||"
                                     "array_to_string(user_name,',')||' '||coalesce(address,'')"
                                     " FROM pg_hba_file_rules WHERE auth_method='trust' AND "
                                     "type LIKE 'host%' AND coalesce(address,'') NOT IN "
                                     "('127.0.0.1','::1')").splitlines():
            trust.append("%s : « %s trust » (connexion réseau sans mot de passe)" % (nom, ligne))
    r.constat("BLOQUANT", "SEC_PG_SUPERUTILISATEUR", "Super-utilisateur PostgreSQL inconnu",
              supers)
    r.constat("BLOQUANT", "SEC_PG_BASE_RANCON", "Base PostgreSQL au nom de rançon", rancons)
    r.constat("ALERTE", "SEC_PG_TABLE_SUSPECTE",
              "Table PostgreSQL suspecte (note de rançon, sortie de commandes)", tables)
    r.constat("BLOQUANT", "SEC_PG_SANS_MOT_DE_PASSE", "PostgreSQL accessible sans mot de passe",
              trust)


def controler_persistance(r):
    elements = []
    if os.path.isfile("/etc/ld.so.preload") and os.path.getsize("/etc/ld.so.preload"):
        elements.append("/etc/ld.so.preload n'est pas vide (préchargement de bibliothèque)")
    r.constat("BLOQUANT", "SEC_PERSISTANCE", "Mécanisme de persistance suspect", elements)
    recents = []
    limite = time.time() - 86400
    for motif in ("/etc/cron.d/*", "/etc/crontab", "/var/spool/cron/crontabs/*",
                  "/root/.ssh/authorized_keys", "/home/*/.ssh/authorized_keys",
                  "/etc/systemd/system/*.service", "/etc/systemd/system/*.timer"):
        for f in glob.glob(motif):
            try:
                if os.path.getmtime(f) > limite:
                    recents.append(f)
            except OSError:
                pass
    r.constat("INFO", "SEC_FICHIER_SENSIBLE_MODIFIE",
              "Tâches planifiées, services ou clés SSH modifiés depuis 24 h", sorted(recents))


def controler_fichiers_rancon(r, jours=2):
    trouves = []
    limite = time.time() - jours * 86400
    for zone in ZONES_RANCON:
        for racine, dossiers, fichiers in os.walk(zone):
            # Pas de descente dans les données internes de PostgreSQL ni dans node_modules / .git.
            dossiers[:] = [d for d in dossiers if d not in ("node_modules", ".git", "base",
                                                            "pg_wal", "__pycache__", ".venv")]
            if racine.count(os.sep) - zone.count(os.sep) > 6:
                dossiers[:] = []
            for f in fichiers:
                if FICHIERS_RANCON.search(f):
                    chemin = os.path.join(racine, f)
                    try:
                        if os.path.getmtime(chemin) > limite:
                            trouves.append(chemin)
                    except OSError:
                        pass
    r.constat("BLOQUANT", "SEC_FICHIER_RANCON",
              "Note de rançon ou fichier chiffré récent", sorted(trouves)[:200])


def controler_signatures(r):
    fichiers = glob.glob("/var/lib/clamav/daily.c[lv]d")
    if not fichiers:
        r.constat("ALERTE", "SEC_ANTIVIRUS_PERIME", "Signatures ClamAV absentes",
                  ["/var/lib/clamav/daily.cvd introuvable"])
        return
    age_h = (time.time() - os.path.getmtime(fichiers[0])) / 3600
    r.info("signatures_age_h", round(age_h, 1))
    if age_h > 48:
        r.constat("ALERTE", "SEC_ANTIVIRUS_PERIME", "Signatures ClamAV de plus de 48 h",
                  ["daily : %.0f h — vérifier le service clamav-freshclam" % age_h])


def controle():
    debut = time.monotonic()
    c = config()
    r = Rapport()
    controler_processus(r, c)
    controler_reseau(r)
    ctrs = conteneurs()
    r.info("conteneurs", len(ctrs))
    controler_exposition(r, c, ctrs)
    controler_postgresql(r, c, ctrs)
    controler_persistance(r)
    controler_fichiers_rancon(r)
    controler_signatures(r)
    d = ecrire("controle", r, debut)
    return 2 if d["statut"] == "bloquant" else 0


# ---------------------------------------------------------------------------
# Antivirus (nuit)
# ---------------------------------------------------------------------------

def zones_antivirus():
    zones = ["/tmp", "/var/tmp", "/dev/shm", "/home", "/root", "/opt", "/etc", "/usr/local",
             "/var/www", "/srv"]
    # Couches modifiables des conteneurs (où un attaquant dépose ses fichiers) et volumes.
    zones += glob.glob("/var/lib/docker/overlay2/*/diff")
    zones += glob.glob("/var/lib/docker/volumes/*/_data")
    return [z for z in zones if os.path.isdir(z)]


def antivirus():
    debut = time.monotonic()
    r = Rapport()
    controler_signatures(r)
    zones = zones_antivirus()
    r.info("zones", len(zones))
    liste = os.path.join(SORTIE, "zones_antivirus.txt")
    os.makedirs(SORTIE, mode=0o755, exist_ok=True)
    with open(liste, "w") as f:
        f.write("\n".join(zones) + "\n")
    journal = os.path.join(SORTIE, "clamscan.log")
    args = ["nice", "-n", "19", "ionice", "-c", "3", "clamscan", "--recursive", "--infected",
            "--detect-pua=yes", "--cross-fs=no", "--max-filesize=200M", "--max-scansize=400M",
            # Données internes de PostgreSQL : volumineuses et sans exécutable.
            "--exclude-dir=/var/lib/postgresql/data/base", "--exclude-dir=/base/[0-9]+$",
            "--exclude-dir=/pg_wal$", "--exclude-dir=/node_modules$", "--exclude-dir=/\\.git$",
            "--exclude-dir=^/root/quarantaine_",
            "--log=" + journal, "--file-list=" + liste]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=6 * 3600)
        sortie, code = p.stdout, p.returncode
    except subprocess.TimeoutExpired:
        sortie, code = "", -1
    infectes = [l for l in sortie.splitlines() if l.endswith(" FOUND")]
    resume = re.search(r"Scanned files: (\d+)", open(journal).read() if os.path.isfile(journal)
                       else "")
    r.info("fichiers_analyses", int(resume.group(1)) if resume else None)
    r.constat("BLOQUANT", "SEC_ANTIVIRUS_DETECTION", "Fichier malveillant détecté par ClamAV",
              infectes)
    if code not in (0, 1):
        r.constat("ALERTE", "SEC_ANTIVIRUS_ERREUR", "L'analyse ClamAV n'a pas abouti",
                  ["code retour %s — voir %s" % (code, journal)])
    d = ecrire("antivirus", r, debut)
    return 2 if d["statut"] == "bloquant" else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("controle", "antivirus"):
        print(__doc__)
        sys.exit(1)
    sys.exit(controle() if sys.argv[1] == "controle" else antivirus())
