# CONCORDE · Dossier projet
Passerelle de liaison comptable : migration Quadra → Odoo, et passerelle de données Odoo 17 (télécharger, analyser, envoyer, modifier). Détail technique dans `README.md`.

| Dossier | Contenu |
|---|---|
| `core/` | Moteur, en Python standard. Pipeline FEC (`fec_parser`, `mapping`, `lettrage`, `moteur`), contrôle dématérialisation (`demat`), **passerelle Odoo 17** : `odoo_source` (lecture SQL / XML-RPC), `telecharger` (FEC, xlsx, CSV), `analyser`, `xlsx_ecrire`. **Comptes et surveillance** : `comptes` (balance, grand livre, règles par compte), `surveillance` (changements, techniques, centre d'alertes), `journal` (CONCORDE raconte), `explications` (catalogue de Marceau). |
| `core/rapport_jour.py` | **Rapport du jour** : conclusions automatiques (sécurité, alertes, changements dans Odoo, travaux), modifiables (masquer, corriger, commenter, ajouter) ; choix gardés dans `/var/lib/concorde-interface/rapports/AAAA-MM-JJ.json` ; export en page imprimable. Écran « Rapport du jour ». |
| `core/comparaison.py` | **Comparer deux bases** sur une période (lecture seule) : vérification et analyse de chacune, puis totaux, soldes par compte / journal / tiers, écriture par écriture (rapprochement par numéro puis par contenu), analytique, conflits avec la date de copie. Écran « Comparer » et `scripts/concorde_comparer.py`. |
| `core/bases_locales.py` | Suppression / réinitialisation des bases Odoo **du serveur** après sauvegarde vérifiée pour une copie client, gardée 7 jours ; sans sauvegarde pour une base de test (ADR-0005). Clés API : révocation dans les bases du serveur, effacement des clés gardées par CONCORDE. Suppression chez un client : impossible par construction. Modèle vierge : `concorde_test_modele`. |
| `core/migration/` | **Migration ERP → Odoo** (ADR-0004), étapes 1 à 5 : `connecteur_fec` (lecture stricte), `filtres` (retrait d'écritures : journal, comptes, analytique, tiers, libellé, montants, période, conditions libres), `controles`, `correspondance` (table arbitrée, `a_arbitrer.xlsx`), `export` (FEC et CSV de contrôle, conformité au centime), `injection` (étape 6 : envoi dans `concorde_test` par l'API, lettrage vérifié, relecture au centime). Commande : `scripts/concorde_migrer.py` (`--tester`). |
| `securite/` | **Sécurité du serveur** (ADR-0007) : `concorde_securite.py controle` (mineur / rançongiciel, toutes les 15 min) et `antivirus` (ClamAV chaque nuit). Résultats dans `/var/lib/concorde-securite`, repris en alertes par l'interface. Signatures de la campagne du 01/11/2026 : `deploy/clamav/`. |
| `injectors/` | Envoi vers Odoo par XML-RPC (`odoo17`, `odoo18`) et chaîne de conversion 14→19. |
| `interface/` | **Interface web** (ADR-0002, 0003) : Alertes, Comptes, Analyser, Télécharger, Journal, Historique, Bases ; surveillance automatique toutes les 15 min : `serveur.py` (Python standard), `auth.py`, `static/` (HTML, CSS, JS). En ligne sur https://concorde.57-129-168-243.sslip.io, service `concorde-interface`. |
| `scripts/` | Commandes. `concorde_odoo.py` : `telecharger` et `analyser` (voir README). `concorde_interface_mdp.py` : changer le mot de passe de l'interface. |
| `tests/` | `python3 -m unittest tests.test_moteur tests.test_demat tests.test_odoo_donnees tests.test_interface tests.test_surveillance tests.test_migration tests.test_bases_locales tests.test_injection tests.test_comparaison tests.test_rapport_jour` (165 tests). |
| `deploy/` | Docker (Odoo 17 + PostgreSQL), modules Odoo 17 à 20, webhook de déploiement, service `concorde-interface.service`. |
| `docs/adr/` | Décisions d'architecture. ADR-0001 : passerelle de données Odoo 17. ADR-0002 : interface web. ADR-0003 : comptes, alertes, journal. ADR-0004 : migration ERP → Odoo. ADR-0005 : suppression de bases (local seulement). ADR-0006 : alignement prod sur test. ADR-0007 : sécurité du serveur. |
| `samples/` | FEC synthétique de test. |

## À lire en premier
1. `docs/adr/README.md`
2. `README.md`, sections « Principes fondateurs » et « Passerelle de données Odoo 17 »

## Points ouverts
1. ~~Corriger l'injecteur~~ : fait le 06/11/2026 (`injectors/odoo17.py` et `odoo18.py` : euros et identifiants Odoo). L'envoi de la migration passe par `core/migration/injection.py`.
2. **Phase 3 — modifier** : corrections en masse et réintégration d'un xlsx modifié, avec remise en brouillon des écritures validées (ADR-0001).
3. **Tester la source XML-RPC sur un vrai Odoo** : il faut un login et une clé API sur l'instance du port 8017.
4. **Créer un rôle PostgreSQL en lecture seule** pour `--source sql`. Aujourd'hui, c'est l'utilisateur `odoo` qui sert.
5. **Base `concorde` en USD** (société « My Company ») : impossible d'en tirer un FEC. Passer la société en EUR, ou confirmer que cette base ne sert qu'aux essais.
6. **SIREN de la société Albhades absent dans `testalbhade`** : le FEC sort sous le nom `SIRENFEC…`. Le renseigner dans Odoo.
7. **`deploy/docker-compose.yml`** : modification non commitée qui retire les services Odoo 18, 19 et 20. À confirmer avant commit, car le webhook redéploie à chaque push sur `main`.
8. **Adresse du PostgreSQL** : l'interface joint le conteneur par son adresse Docker (172.18.0.2), qui peut changer quand le conteneur est recréé. Mieux : publier le port sur 127.0.0.1 dans `docker-compose.yml`.
9. **Brancher les écrans Envoyer et Modifier** de l'interface, une fois les phases 2 et 3 faites.
10. **Migration ERP → Odoo, étapes 7 et 8** (étape 6 faite le 06/11/2026) : test d'une écriture chez le client, envoi complet. Puis : écran « Migrer », connecteurs Excel/CSV à profils, AzalPlus (API), balance + tiers + plan, Sage et Quadra. Puis l'alignement prod sur test (ADR-0006).
11. **Filestore des bases supprimées** : il reste dans le volume Docker d'Odoo ; prévoir un nettoyage par root (`docker exec concorde-odoo rm -rf /var/lib/odoo/filestore/<base>`).
12. **Rôle PostgreSQL dédié** pour CONCORDE (lecture et suppression des seules bases Odoo), à la place du super-utilisateur `odoo`.
13. **Clés API de la base `concorde`** : trois clés admin à accès complet (`concorde`, `vibe`, `chatgpt`). À révoquer si elles ne servent plus (écran Bases > Clés API).
14. **`testalbhade` restaurée le 06/11/2026** depuis sa sauvegarde Concorde ; date de copie (14/10/2026 18 h 01 UTC) enregistrée dans `/var/lib/concorde-interface/bases_test.json`.
15. **Vitesse de l'étape 6** : environ 8 minutes pour 2 674 écritures (validation et lettrage un par un). À accélérer avant de traiter 45 000 écritures.
