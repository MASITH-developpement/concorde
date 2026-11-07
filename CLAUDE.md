# Protocole CONCORDE — orchestrateur multi-agents

Concorde (passerelle données Odoo 17) est servi sur https://concorde.57-129-168-243.sslip.io.
Dépôt : `/opt/concorde` (appartient à root → écrire via une copie puis `sudo install`).
Ce protocole s'applique à toutes les sessions. Méthode de travail : skill `dev-azal-odoo`.

## A. Multi-agents
- 1 agent = 1 branche = 1 issue GitHub (labels front / api / tests / bug), dépôt `MASITH-developpement/concorde`.
- Worktrees : `~/agents/concorde-front`, `~/agents/concorde-api`, `~/agents/concorde-tests` (git worktree ; préfixe `concorde-` pour ne pas croiser AzalPlus).
- Sessions : `tmux new-session -d -s concorde-<nom> 'cd ~/agents/concorde-<nom> && claude'`.
- File d'attente = issues ouvertes. « Lance les agents » = assigner chaque issue à l'agent de son label.
- Les agents ouvrent des PR ; seul l'orchestrateur merge, uniquement si CI verte + vérification en ligne OK.
- Conflit → la PR la plus ancienne rebase.
- **Rien en production sans l'accord explicite de Stéphane.**

## B. Skills
- Au démarrage, découvrir et lire les skills (`.claude/skills/*/SKILL.md`, et skills installés, dont `dev-azal-odoo`).
- Les appliquer à la lettre dans leur périmètre ; ne jamais modifier un skill.
- Rapport : SKILLS APPLIQUÉS.

## C. Versions
- Toute publication = bump sémantique (PATCH / MINOR / MAJOR ; doute → niveau supérieur).
- Fichier de version + `CHANGELOG.md` + tag git `vX.Y.Z`. Le module Odoo garde le format `17.0.X.Y.Z`
  dans `deploy/addons/concorde/__manifest__.py`, avec le même X.Y.Z.
- Jamais de numéro réutilisé ; vérifier la correspondance fichier / tag.
- Rapport : VERSION.

## D. Qualité du code (10/10 mesuré, zéro raccourci)
- Après chaque modification : mesure réelle (lint/format, types, sécurité, tests, doc), rapportée brute même si mauvaise.
- Boucle : corriger la cause réelle → re-mesurer → jusqu'à 100 % au vert.
- Interdit : désactiver une règle (`noqa`, `type: ignore`, `eslint-disable`), skipper un test, baisser un seuil, corriger le symptôme.
- Chaque point rouge = plan de correction concret. Jamais de score estimé.

## E. Sommaire des variables
- Toute variable est déclarée dans `SOMMAIRE_VARIABLES.md` (racine).
- Avant création : vérifier (casse ignorée) qu'elle n'existe pas.
- Pas de noms numérotés (`var1`, `var2`) ; snake_case explicite décrivant la fonction (`nom_client`).
- Mise à jour du sommaire dans la même modification. Aucun doublon.

## F. Factorisation en routines
- Toute action utilisée au moins 2 fois devient une sous-routine partagée (module commun), jamais recopiée.
- Chaque routine a une docstring : rôle, paramètres, retour, erreurs, usages.

## G. Explications dans le code
- Modifier une explication = REMPLACER l'ancien texte, pas ajouter à la suite.
- Décrire ce que fait l'action aujourd'hui. Max : explication d'origine + 2 notes de modification.
- Historique dans git, jamais dans le code. Pas de code de « 3 km » pour une petite action.

## H. Vérification en ligne (après chaque déploiement)
```bash
curl -sS -o /dev/null -w "HTTP %{http_code} | TLS %{ssl_verify_result}\n" https://concorde.57-129-168-243.sslip.io/
~/vibe-test/bin/python ~/vibe-test/tests/test_action.py "https://concorde.57-129-168-243.sslip.io/<page>" "<sélecteur>" "<texte attendu>"
```
Attendu : HTTP 200 et TLS 0, sinon ÉCHEC (jamais contourné par `-k`).
Si le venv manque : `python3 -m venv ~/vibe-test && ~/vibe-test/bin/pip install playwright && ~/vibe-test/bin/playwright install chromium && sudo ~/vibe-test/bin/playwright install-deps chromium`

## I. Checklist finale obligatoire
Avant de déclarer une tâche terminée, cocher chaque ligne (OK, ou non applicable justifié) :
- [ ] Qualité : tous contrôles mesurés au vert (itérations : <n>)
- [ ] Sommaire des variables : à jour, aucun doublon
- [ ] Factorisation : rien de répété non factorisé
- [ ] Explications : à jour, remplacées, max origine + 2
- [ ] Version : bump si publication
- [ ] Skills : appliqués ou « aucun applicable » justifié
- [ ] Site en ligne : HTTPS + parcours OK
- [ ] Régressions : suite complète OK

Toute case vide ou non justifiée = tâche non terminée.

## J. Rapport final
MODIFICATION / SKILLS / VERSION / QUALITÉ (par contrôle, itérations) / VARIABLES / FACTORISATION /
SITE EN LIGNE / RÉGRESSIONS / CHECKLIST / RÉSULTAT GLOBAL.
Aucun « terminé » avec un point ÉCHEC non validé.
