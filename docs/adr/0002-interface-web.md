# ADR-0002 — Interface web de CONCORDE : Python standard, un utilisateur, derrière Caddy

- **Statut** : Acceptée — arbitrages de Stéphane Moreau en séance du 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
La passerelle Odoo 17 (ADR-0001) ne s'utilisait qu'en ligne de commande. Stéphane
veut une interface, pour son seul usage (MASITH), accessible depuis un navigateur.

## Décision
1. **Serveur en Python standard** (`http.server`), pages HTML/CSS/JS sans framework :
   aucune nouvelle dépendance. Les actions passent par `core/passerelle.py`, comme la
   ligne de commande.
2. **Un seul utilisateur.** Mot de passe haché en scrypt dans `/etc/concorde/interface.env`
   (root, 600). Session de 1 h d'inactivité et 10 h au plus, cookie `HttpOnly`, `Secure`,
   `SameSite=Strict`. 5 échecs en 15 min bloquent l'adresse IP. Anti-CSRF par en-tête
   `X-Concorde`. Les en-têtes CSP et anti-iframe sont posés.
3. **Accès en HTTPS par Caddy** (`concorde.57-129-168-243.sslip.io`, certificat
   Let's Encrypt). Le service n'écoute que sur 127.0.0.1:18090.
4. **Service systemd** `concorde-interface`, sous l'utilisateur `ubuntu`, avec un système
   de fichiers en lecture seule sauf `/var/lib/concorde-interface` (résultats et historique).
5. **Première version** : Analyser, Télécharger, Historique, Bases (bases SQL du serveur
   et Odoo distants par l'API ; clé API en mémoire uniquement). Envoyer et Modifier
   restent affichés en grisé jusqu'aux phases 2 et 3.
6. Les tâches tournent en arrière-plan, 2 à la fois au plus. L'écran suit leur avancement.

## Conséquences
- L'interface donne accès en lecture à toute la comptabilité des bases du serveur :
  le mot de passe doit être long, et on peut ajouter une restriction par IP dans Caddy.
- Un redémarrage du service déconnecte la session et oublie les Odoo distants.
- Pour passer en multi-clients, il faudra des comptes, des droits par base et un
  cloisonnement : ce sera une nouvelle ADR.

## Options écartées
- **FastAPI** (comme AzalPlus) : nouvelle dépendance, pas nécessaire pour quelques écrans.
- **Accès par tunnel SSH seulement** : plus sûr, mais moins pratique. Écarté par Stéphane.
- **Écrans dans le module Odoo** : Concorde doit travailler hors d'Odoo (ADR-0001).
