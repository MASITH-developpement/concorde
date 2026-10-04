# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""WEBHOOK GITHUB — DÉPLOIEMENT AUTOMATIQUE DE CONCORDE.

Principe : à chaque `git push` sur la branche main du dépôt
MASITH-developpement/concorde, GitHub appelle ce service sur le VPS :

    POST http://<IP_VPS>:9000/webhook

Le service vérifie la signature HMAC-SHA256 (en-tête X-Hub-Signature-256,
secret partagé), puis exécute séquentiellement :

    git pull origin main
    docker compose up -d --build
    docker image prune -f   (optionnel, via NETTOYER_IMAGES)

Sécurités :
- Signature HMAC-SHA256 obligatoire : toute requête non signée (ou mal
  signée) est refusée en 403. Le secret ne circule jamais en clair.
- Refus hors branche main (payload "ref" contrôlé).
- Journal déterministe local (deploy/log/webhook.log), zéro LLM.
- Aucune commande arbitraire : le script n'exécute que la séquence fixée.
- Secret lu depuis la variable d'environnement CONCORDE_WEBHOOK_SECRET ;
  jamais en dur dans le dépôt (jamais sur GitHub).

Lancement manuel :
    CONCORDE_WEBHOOK_SECRET="votre-secret" python3 deploy/webhook.py

Lancement systemd (recommandé, voir INSTALL.md) :
    systemctl enable --now concorde-webhook
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("CONCORDE_WEBHOOK_PORT", "9000"))
SECRET = os.environ.get("CONCORDE_WEBHOOK_SECRET", "")
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER_LOG = os.path.join(RACINE, "deploy", "log", "webhook.log")
NETTOYER_IMAGES = os.environ.get("CONCORDE_WEBHOOK_NETTOYER", "") == "1"


def journaliser(message: str):
    os.makedirs(os.path.dirname(FICHIER_LOG), exist_ok=True)
    with open(FICHIER_LOG, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def signature_valable(corps: bytes, entete: str) -> bool:
    """Vérifie X-Hub-Signature-256 : 'sha256=<hmac_hex>'."""
    if not SECRET or not entete or not entete.startswith("sha256="):
        return False
    attendu = hmac.new(SECRET.encode("utf-8"), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, entete.split("=", 1)[1].strip())


def deployer() -> tuple:
    """Séquence fixe de déploiement. Retourne (ok, sortie)."""
    etapes = [
        ["git", "pull", "origin", "main"],
        ["docker", "compose", "up", "-d", "--build"],
    ]
    if NETTOYER_IMAGES:
        etapes.append(["docker", "image", "prune", "-f"])
    sortie = []
    for etape in etapes:
        r = subprocess.run(etape, cwd=RACINE, capture_output=True, text=True, timeout=600)
        sortie.append("$ %s\n%s%s" % (" ".join(etape), r.stdout, r.stderr))
        if r.returncode != 0:
            return False, "\n".join(sortie)
    return True, "\n".join(sortie)


class Gestionnaire(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return
        longueur = int(self.headers.get("Content-Length", "0"))
        corps = self.rfile.read(longueur)
        if not signature_valable(corps, self.headers.get("X-Hub-Signature-256", "")):
            journaliser("REFUS : signature HMAC invalide ou absente")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"signature invalide")
            return
        try:
            payload = json.loads(corps.decode("utf-8"))
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        if payload.get("ref") not in (None, "refs/heads/main"):
            journaliser("IGNORÉ : ref=%s (seule main déploie)" % payload.get("ref"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ignorer: hors main")
            return
        ok, sortie = deployer()
        journaliser("PUSH main — déploiement %s\n%s" % ("OK" if ok else "ÉCHEC", sortie))
        self.send_response(200 if ok else 500)
        self.end_headers()
        self.wfile.write(b"deploiement ok" if ok else b"deploiement echec")

    def do_GET(self):
        # sonde simple, sans information sensible
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"concorde-webhook actif")

    def log_message(self, fmt, *args):
        pass  # journalisation maison uniquement, pas de bruit stderr


def main():
    if not SECRET:
        print("ERREUR : CONCORDE_WEBHOOK_SECRET manquant. "
              "Générez un secret (ex. `openssl rand -hex 32`) et exportez-le.")
        sys.exit(1)
    journaliser("concorde-webhook démarré sur le port %d" % PORT)
    print("concorde-webhook actif sur le port %d (racine: %s)" % (PORT, RACINE))
    HTTPServer(("0.0.0.0", PORT), Gestionnaire).serve_forever()


if __name__ == "__main__":
    main()
