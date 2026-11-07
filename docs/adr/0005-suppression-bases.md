# ADR-0005 — Suppression de bases et de clés API : seulement en local, jamais chez un client

- **Statut** : Acceptée — arbitrage de Stéphane Moreau du 06/11/2026
- **Date** : 06/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Stéphane veut pouvoir supprimer des bases : les copies de bases client et les bases de
test de **notre** Odoo local, et les bases enregistrées dans CONCORDE. La suppression
complète d'une base **chez le client** est **interdite** : une fausse manipulation est
toujours possible, donc elle doit être **impossible par programmation**.

## Décision
1. **Base Odoo 17 de ce serveur** : suppression possible (`core/bases_locales.py`), écran
   Bases, bouton « Supprimer… ». Garde-fous, le premier qui échoue arrête tout :
   1. hôte PostgreSQL local (boucle locale, socket, réseau Docker 172.16.0.0/12) ;
   2. base présente dans la liste des bases Odoo 17 du serveur (`azalplus_v2` et les
      bases système sont donc exclues) ;
   3. base non protégée (`CONCORDE_BASES_PROTEGEES`, défaut : `concorde`, base du conteneur) ;
   4. aucune tâche CONCORDE en cours sur la base ;
   5. nom de la base retapé à l'identique ;
   6. **copie de base client** : sauvegarde pg_dump complète, relue (`pg_restore --list`),
      avant la suppression ; si la sauvegarde échoue, rien n'est supprimé. Sauvegardes
      gardées **7 jours** (`CONCORDE_SAUVEGARDE_JOURS`) dans
      `/var/lib/concorde-interface/sauvegardes`, puis effacées automatiquement.
      **Base de test** (celle qui a un modèle vierge `<nom>_modele`) : **pas de sauvegarde**,
      son contenu est jetable. C'est l'existence du modèle, lue côté serveur, qui en décide,
      jamais un paramètre venu de l'écran (arbitrage du 06/11/2026).
2. **Réinitialisation** d'une base de test : suppression (sans sauvegarde), puis recréation depuis
   son modèle vierge (base PostgreSQL TEMPLATE `<nom>_modele`, fermée aux connexions).
   `concorde_test_modele` a été créé le 06/11/2026 depuis `concorde_test` vierge.
3. **Base distante (client)** : seulement « Retirer de CONCORDE », qui l'enlève de la liste
   (la clé API est oubliée). **Aucune** suppression n'est possible :
   - l'API refuse toute suppression ou réinitialisation d'une base qui n'est pas `sql:` ;
   - le module refuse tout nom contenant « : » ou « / » et tout hôte non local ;
   - aucun code de CONCORDE n'appelle le service de gestion des bases d'Odoo
     (`/xmlrpc/2/db`, `/web/database`, `drop`). Un test (`tests/test_bases_locales.py`)
     parcourt tout le dépôt, module Odoo compris, et échoue si quelqu'un en ajoute un ;
   - seul `core/bases_locales.py` contient un `DROP DATABASE` (vérifié par le même test).

## Clés API (ajout du 06/11/2026)
- **Clés gardées par CONCORDE** (Odoo distants) : « Supprimer la clé » l'efface de CONCORDE ;
  la base reste listée, déconnectée, jusqu'à ce qu'on en ressaisisse une. Rien ne change chez
  le client.
- **Clés des bases Odoo 17 du serveur** : liste (nom, utilisateur, portée, date — jamais la
  valeur secrète) et révocation, avec les mêmes garde-fous (hôte local, base locale) et le nom
  de la clé retapé. Seule la ligne de la clé est supprimée de `res_users_apikeys` : c'est
  l'unique écriture SQL de CONCORDE dans une base Odoo, limitée à cette table technique et
  aux bases du serveur (les écritures comptables passent toujours par l'ORM, ADR-0001).
- Révoquer une clé **chez un client** n'est pas prévu.

## Conséquences
- Les pièces jointes (filestore) d'une base supprimée restent dans le volume Docker d'Odoo
  (le service tourne sans droits Docker) : à nettoyer par root si besoin.
- L'utilisateur PostgreSQL `odoo` est super-utilisateur : ce sont les garde-fous de
  CONCORDE, et non les droits PostgreSQL, qui limitent la suppression. Un rôle dédié aux
  bases Odoo, sans droit sur les autres, est une amélioration recommandée.

## Options écartées
- **Supprimer une base client par l'API d'Odoo** (service `db`, mot de passe maître) :
  interdit par Stéphane.
- **Suppression sans sauvegarde d'une copie client** : contraire à la règle MASITH
  « sauvegarde complète avant toute opération lourde ».
- **Sauvegarde gardée 30 jours** (premier choix de Claude) : ramené à 7 jours par Stéphane
  (place disque, et moins de copies de données client qui traînent).
