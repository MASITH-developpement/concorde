# Sommaire des variables — CONCORDE

Toute nouvelle variable est déclarée ici dans la même modification (protocole CONCORDE, § E).
Avant d'en créer une, vérifier (casse ignorée) qu'elle n'existe pas déjà.

> Sommaire commencé le 07/11/2026 (version 1.4.10) : il ne liste que les variables
> créées ou renommées depuis (passe qualité 1.5.0 comprise). Les variables plus anciennes
> restent à y reporter.

| Variable | Fichier | Rôle |
|---|---|---|
| `__enter__` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : ouverture d'un bloc with (curseurs) |
| `__exit__` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : fermeture d'un bloc with (curseurs) |
| `_acces` | `core/montee_version/montee.py` | Méthode : mot de passe du PostgreSQL jetable (fichier 600) |
| `_afficher_etat` | `scripts/concorde_montee.py` | Routine : affiche l'état d'une montée |
| `_analyser` | `interface/serveur.py` | Méthode de Taches : exécution d'une analyse |
| `_arguments` | `tests/test_assistant_import.py` | Paramètres ignorés de `champ_bouchon` |
| `_attendre` | `core/connecteurs/http_json.py` | Fonction d'attente du client (time.sleep par défaut) |
| `_attendre_postgres` | `core/montee_version/montee.py` | Méthode : attend que PostgreSQL réponde |
| `_attente` | `core/connecteurs/http_json.py` | Routine : secondes à attendre d'après Retry-After |
| `_avec_delai` | `core/odoo_source.py` | Routine : applique le délai d'attente à une connexion HTTP |
| `_bilan_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : dict produit par une étape du pipeline |
| `_BLOC` | `interface/transferts.py` | Taille d'un bloc de réception (64 Kio) |
| `_bloquer` | `core/connecteurs/transfert.py` | Routine : arrête une destination à une étape, motif au journal |
| `_centimes_base` | `core/migration/injection.py` | Montant SQL en euros -> centimes (remplace la fonction locale `c`) |
| `_centimes_ou_rien` | `core/migration/filtres.py` | Routine : montant en euros -> centimes, ou None |
| `_CHAMPS_TEXTE_LIGNE` | `core/odoo_source.py` | Champs texte d'une ligne SQL ramenés de NULL à '' |
| `_chemin_executable` | `core/bases_locales.py` | Routine partagée : chemin absolu de pg_dump / pg_restore (FileNotFoundError si absent) |
| `_chemin_fec` | `core/connecteurs/fec.py` | Méthode de ConnecteurFec : chemin du FEC d'une référence |
| `_chemins_cible_feuille` | `core/mapping.py` | Routine : chemins candidats d'une cible de relation (absolue ou relative) |
| `_cible` | `core/connecteurs/odoo.py` | Méthode de ConnecteurOdoo : cible d'écriture |
| `_codes_html` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : liste de codes de comptes échappée (au plus 30) |
| `_colonne_entete_unique` | `core/mapping.py` | Routine : colonne unique d'un intitulé d'en-tête, ErreurMapping si ambiguë |
| `_colonnes_reconnues` | `core/xlsx_vers_fec.py` | Reconnaît les colonnes (synonymes) d'une ligne candidate à l'en-tête |
| `_compter` | `core/connecteurs/azalplus.py` | Méthode d'AzalPlus : compte les lignes lues et écartées, et signale |
| `_comptes` | `core/connecteurs/pennylane.py` | Méthode Pennylane : identifiants actifs par numéro de compte |
| `_comptes_de_cle` | `core/odoo_source.py` | Routine : clé de répartition analytique -> codes/noms de comptes |
| `_comptes_des_lignes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : parcourt les lignes FEC portant un numéro de compte |
| `_connecter` | `core/connecteurs/azalplus.py` | Méthode d'AzalPlus : connexion PostgreSQL en lecture seule |
| `_connexion` | `injectors/socle_odoo.py`, `injectors/odoo_conversion.py` | Connexion Odoo ouverte (None tant que non connecté) |
| `_connexion_active` | `injectors/socle_odoo.py` | Rend la connexion ouverte ou lève ErreurInjecteur |
| `_connexion_ou_nouvelle` | `core/bases_locales.py` | Routine partagée : connexion fournie, ou nouvelle fermée en fin de bloc |
| `_ConnexionHttp` | `core/odoo_source.py` | TypeVar (HTTPConnection ou HTTPSConnection) de `_avec_delai` |
| `_constat_explique` | `interface/serveur.py` | Routine : constat allégé (sans éléments) et expliqué |
| `_construire_ligne_fec` | `core/xlsx_vers_fec.py` | Construit une ligne FEC complète (CHAMPS_FEC) |
| `_continue_le_bloc` | `core/yaml_min.py` | Routine : la ligne continue-t-elle le bloc (erreur si trop indentée) |
| `_cookie_session` | `interface/serveur.py` | Routine : en-tête Set-Cookie de session (None = effacement) |
| `_corps` | `tests/test_connecteurs.py` | Corps d'une réponse simulée |
| `_couche_superflue` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Compteur (non utilisé) des couches base64 en trop retirées par `_lire_binaire`, 3 au maximum |
| `_creer` | `tests/test_connecteurs.py` | Méthode de test : création d'une écriture simulée |
| `_creer_fiche_erreur` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : crée la fiche d'import en erreur et rend son action |
| `_creer_manquants` | `core/connecteurs/odoo.py` | Méthode de ConnecteurOdoo : vrai pour une base de test vierge |
| `_date` | `core/connecteurs/pennylane.py` | Routine Pennylane : date ISO -> date |
| `_date_ou_rien` | `core/migration/filtres.py` | Routine : date ISO -> date, ou None |
| `_decoder` | `core/connecteurs/http_json.py` | Routine : réponse HTTP -> JSON, ou erreur nommée sans jeton |
| `_decouper_liste_en_ligne` | `core/yaml_min.py` | Routine : éléments d'une liste en ligne [a, b] |
| `_decrire` | `interface/transferts.py` | Méthode : description d'une connexion pour l'écran (sans secret) |
| `_DEMANDE` | `core/montee_version/demandes.py` | Nom de fichier d'une demande |
| `_depot` | `interface/transferts.py` | Méthode : fiche du dernier FEC déposé |
| `_derniere_empreinte_valide` | `core/guardian.py` | Méthode partagée : recalcule la chaîne d'audit, None si un maillon est altéré |
| `_description_sql` | `interface/serveur.py` | Méthode de Bases : fiche d'une base du serveur |
| `_disposition_piece_jointe` | `interface/serveur.py` | Routine : valeur de l'en-tête Content-Disposition |
| `_DOC_OFFICE` | `core/xlsx_ecrire.py` | Espace de noms des relations officeDocument |
| `_docker` | `core/montee_version/montee.py` | Méthode : lance docker |
| `_Domaine` | `stubs/odoo/models.pyi` | Type d'un domaine de recherche Odoo (stub) |
| `_dossier` | `core/connecteurs/transfert.py` | Routine : dossier d'un transfert |
| `_ecran` | `interface/serveur.py` | Routine : exécute une action de l'écran Transferts, refus en HTTP 400 |
| `_ecrire_csv` | `core/export_odoo.py` | Routine partagée : CSV CRLF préfixé du BOM UTF-8 |
| `_ecrites` | `core/connecteurs/pennylane.py` | Identifiants Pennylane écrits sous chaque référence |
| `_ecritures_de` | `core/connecteurs/pennylane.py` | Méthode Pennylane : écritures répondant à des filtres |
| `_effacer_image` | `core/montee_version/montee.py` | Méthode : efface les images d'un saut |
| `_Element` | `core/demat.py` | TypeVar : élément d'une liste découpée par `_lots` |
| `_empreinte_maillon` | `core/guardian.py` | Routine partagée : empreinte SHA-256 d'un maillon chaînée à la précédente |
| `_encoder_fec` | `core/xlsx_vers_fec.py` | Sérialise en-tête + lignes FEC en UTF-8 |
| `_enregistrer_rapport` | `interface/serveur.py` | Méthode de Gestionnaire : POST /api/rapport |
| `_ENTETE_XML` | `core/xlsx_ecrire.py` | Déclaration XML commune aux parties du classeur |
| `_entetes` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | En-têtes HTTP ajoutés à chaque requête |
| `_erreur_fichier` | `core/mapping.py` | Routine partagée : lève l'erreur « Fichier <quoi> <nom> : <message> » |
| `_erreur_sans_ecriture` | `core/xlsx_vers_fec.py` | Routine : erreur « aucune ligne d'écriture exploitable » (standard et Quadra) |
| `_est_tiret` | `core/yaml_min.py` | Routine : la ligne est-elle un élément de liste |
| `_etape` | `core/montee_version/montee.py` | Méthode : remplace l'état d'une étape |
| `_etat_etape` | `core/connecteurs/transfert.py` | Routine : état d'une étape jugée sur ses constats |
| `_ETATS_TEXTE` | `core/odoo_source.py` | Libellé français des états d'écriture (journal) |
| `_evenement_info` | `interface/serveur.py` | Routine : constat INFO pour le centre d'alertes |
| `_executer` | `scripts/concorde_connexion.py` | Routine : exécute une sous-commande de concorde_connexion |
| `_executer_pipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : prépare mapping et plan puis exécute le moteur |
| `_existe` | `core/montee_version/montee.py` | Méthode : conteneur ou réseau existant |
| `_explication` | `interface/serveur.py` | Routine : explication Marceau d'un constat |
| `_feuille` | `tests/test_mapping.py` | Paramètre ignoré d'un lecteur de feuille simulé |
| `_fiches` | `core/connecteurs/connexions.py` | Connexions de l'annuaire, par identifiant |
| `_fichier` | `core/montee_version/montee.py` | Méthode : chemin dans le dossier de la montée |
| `_fichier_acces` | `core/montee_version/montee.py` | Méthode : fichier env du PostgreSQL jetable |
| `_fichier_instantane` | `interface/serveur.py` | Routine : chemin de la photo de surveillance d'une base |
| `_garde` | `tests/test_connecteurs.py` | Méthode de test : un élément passe-t-il un filtre Pennylane |
| `_get_montees` | `interface/serveur.py` | Routes GET de l'écran Montée |
| `_get_transferts` | `interface/serveur.py` | Routes GET de l'écran Transferts |
| `_groupes_date` | `core/xlsx_vers_fec.py` | Routine : découpe une date texte en groupes selon ses séparateurs |
| `_IDENT_DEMANDE` | `interface/montees.py` | Forme de l'identifiant d'une demande |
| `_IDENT_TRANSFERT` | `interface/transferts.py` | Forme d'un identifiant de transfert (T + date + 4 hex) |
| `_identifiant_sql` | `core/bases_locales.py` | Routine : vérifie un nom de base (`_NOM_VALIDE`) et le rend entre guillemets pour le SQL |
| `_identifiants` | `tests/outils.py` | Paramètres ignorés de `FauxCommun.authenticate` |
| `_ids_par_code` | `injectors/socle_odoo.py` | {code: id} d'un modèle Odoo pour une liste de codes |
| `_image_saut` | `core/montee_version/montee.py` | Méthode : image Odoo d'un saut, avec openupgradelib |
| `_jeton` | `core/connecteurs/http_json.py` | Jeton Bearer, gardé en mémoire seulement |
| `_JETON_DEPOT` | `interface/montees.py` | Forme du nom d'une sauvegarde déposée |
| `_JETON_TABLE` | `interface/transferts.py` | Forme du jeton d'une table reçue (32 hex) |
| `_jour_valide` | `interface/serveur.py` | Routine : vrai si le texte est une date AAAA-MM-JJ |
| `_journaux` | `core/connecteurs/pennylane.py` | Méthode Pennylane : {id de journal: code} |
| `_json` | `tests/test_connecteurs.py` | Méthode de test : réponse JSON simulée |
| `_lecteur` | `tests/test_mapping.py` | Paramètre ignoré d'un lecteur de valeur simulé |
| `_libelle` | `interface/transferts.py` | Méthode : libellé d'une connexion, ou « (retirée) » |
| `_libelle_action` | `core/rapport_jour.py` | Libellé français d'une action de tâche |
| `_LIGNE_MODULE` | `core/montee_version/openupgrade.py` | Ligne d'un module dans la table de couverture |
| `_lignes_a_retirer` | `core/migration/filtres.py` | Lignes retirées par un filtre selon sa portée |
| `_lignes_problemes` | `core/migration/circuit.py` | Lignes de problemes.xlsx (explication calculée une fois par constat) |
| `_lignes_sans` | `core/connecteurs/secrets.py` | Routine : lignes du fichier env sans certaines variables |
| `_lignes_seulement` | `core/comparaison.py` | Routine : décrit les lignes présentes d'un seul côté (A ou B) |
| `_lignes_utiles` | `core/yaml_min.py` | Routine : lignes non vides avec numéro d'origine et retrait |
| `_limites` | `core/montee_version/montee.py` | Méthode : bridage mémoire et processeur |
| `_lire` | `core/connecteurs/azalplus.py` | Méthode d'AzalPlus : exécute une requête de lecture |
| `_lire_bloc` | `core/yaml_min.py` | Routine : lit un bloc (table ou liste) à un retrait donné |
| `_lire_enfant` | `core/yaml_min.py` | Routine : bloc indenté sous un parent, ou None |
| `_lire_json` | `interface/serveur.py` | Routine : contenu d'un fichier JSON UTF-8 |
| `_lire_liste` | `core/yaml_min.py` | Routine : lit une liste YAML |
| `_lire_par_lots` | `core/odoo_source.py` | Routine : `read` XML-RPC par lots de TAILLE_LOT |
| `_lire_parametres` | `scripts/concorde_connexion.py` | Routine : paires « nom=valeur » de la ligne de commande -> dict |
| `_lire_partie` | `core/mapping.py` | Routine : lit une partie XML de l'archive, ErreurMapping si illisible |
| `_lire_rangs` | `core/migration/injection.py` | Routine : requête SQL de relecture du lot |
| `_lire_societe` | `core/odoo_source.py` | Routine : lecture XML-RPC de champs de la société (societe_info, verrous) |
| `_lire_table` | `core/yaml_min.py` | Routine : lit une table YAML |
| `_liste_textes` | `core/migration/filtres.py` | Routine : critère liste ou texte à virgules -> liste de textes |
| `_lot` | `core/connecteurs/odoo.py`, `core/connecteurs/pennylane.py` | Méthode de ConnecteurOdoo : lignes Odoo -> Lot |
| `_maintenant` | `core/montee_version/demandes.py` | Routine : date et heure à la seconde |
| `_mapping_depuis_json` | `core/mapping.py` | Routine : JSON décodé (objet ou liste) -> mapping validé |
| `_membres_surs` | `core/montee_version/sauvegarde.py` | Routine : membres utiles, chemins vérifiés |
| `_Methode` | `stubs/odoo/api.pyi` | Type d'une méthode décorée par api.model (stub) |
| `_montee` | `scripts/concorde_montee.py` | Sous-commandes de conduite d'une montée |
| `_motif_erreur` | `interface/serveur.py` | Routine : texte « Type : message » d'une exception |
| `_NOM_VALIDE` | `core/connecteurs/secrets.py` | Motif d'un nom de variable de secret (majuscules) |
| `_noms_bases_locales` | `interface/serveur.py` | Routine : noms des bases du serveur (SQL) |
| `_NOTE_FUSION` | `core/montee_version/openupgrade.py` | Note « Merged into » / « Renamed to » |
| `_OPENPYXL_DISPONIBLE` | `core/xlsx_vers_fec.py` | Vrai si openpyxl est importable |
| `_options` | `tests/test_assistant_import.py` | Paramètres ignorés de `champ_bouchon` |
| `_ouvre_guillemet` | `core/yaml_min.py` | Routine : ce caractère ouvre-t-il une chaîne entre guillemets |
| `_ouvreur_https` | `core/marceau.py` | Ouvreur d'URL limité au schéma https |
| `_ouvrir` | `core/connecteurs/http_json.py` | Fabrique de connexion HTTP du client |
| `_paire_mapping` | `core/mapping.py` | Routine : paire (compte Quadra, compte Odoo) validée |
| `_Parametres` | `core/guardian.py` | ParamSpec des arguments de l'étape enveloppée |
| `_parametres_sql` | `core/connecteurs/azalplus.py` | Méthode d'AzalPlus : entreprise, société et statuts des requêtes |
| `_parties` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Colonnes de la ligne FEC, inutilisées lors des correspondances |
| `_perimetre` | `core/connecteurs/transfert.py` | Routine : période d'une demande, en dates |
| `_photo_source` | `core/connecteurs/transfert.py` | Routine : photo FEC de la source lue |
| `_plan` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Plan comptable rendu par `_executer_pipeline`, inutile à l'export |
| `_post_montees` | `interface/serveur.py` | Routes POST de l'écran Montée |
| `_post_transferts` | `interface/serveur.py` | Routes POST (JSON) de l'écran Transferts |
| `_preparer_destination` | `core/connecteurs/transfert.py` | Routine partagée : étapes 1 à 4 d'une destination (rapport et nouveau test) |
| `_pret` | `interface/montees.py` | Méthode : refuse si le service n'est pas prêt |
| `_proprietaire_odoo` | `core/montee_version/montee.py` | Méthode : pièces jointes au compte odoo de l'image |
| `_psql` | `core/montee_version/montee.py` | Méthode : outil PostgreSQL dans le conteneur jetable |
| `_publication` | `core/montee_version/demandes.py` | Méthode : republie une montée pendant un bloc |
| `_quand_borne` | `core/rapport_jour.py` | Borne un horodatage ISO à la seconde (champ « quand ») |
| `_racine` | `tests/test_mapping.py` | Paramètre ignoré (racine XML) d'un lecteur simulé |
| `_reecrire` | `core/connecteurs/secrets.py` | Routine : réécriture atomique du fichier de secrets, en 600 |
| `_refus` | `core/connecteurs/pennylane.py` | Méthode Pennylane : motifs de refus et comptes uniques |
| `_requete` | `tests/test_injection.py`, `tests/test_connecteurs.py` | Paramètres ignorés de `CurseurRelecture.execute` |
| `_Resultat` | `core/guardian.py` | TypeVar du résultat de l'étape enveloppée |
| `_retirer_commentaire` | `core/yaml_min.py` | Routine : retire le commentaire de fin de ligne (hors guillemets) |
| `_revoquer_cle` | `interface/serveur.py` | Méthode de Gestionnaire : POST /api/cles/revoquer |
| `_sauver` | `core/connecteurs/connexions.py`, `core/connecteurs/transfert.py` | Méthode de l'annuaire / routine du transfert : écriture du fichier JSON |
| `_SCHEMAS_OPENXML` | `core/xlsx_ecrire.py` | Préfixe d'URL des espaces de noms Office Open XML |
| `_secrets` | `core/connecteurs/base.py` | Secrets d'un connecteur, gardés en mémoire seulement |
| `_separer_cle` | `core/yaml_min.py` | Routine : sépare la clé et la valeur d'une ligne de table |
| `_serveur_xmlrpc` | `core/migration/injection.py` | Routine : client XML-RPC (allow_none) |
| `_SIREN_DANS_NOM` | `core/connecteurs/fec.py` | Motif du SIREN dans un nom de FEC DGFiP |
| `_source` | `core/connecteurs/odoo.py` | Méthode de ConnecteurOdoo : source de lecture (lecture seule) |
| `_SQL_LIGNES_AZALPLUS` | `core/connecteurs/azalplus.py` | Requête : lignes validées d'une société AzalPlus |
| `_SQL_MODULES_INSTALLES` | `core/montee_version/inventaire.py` | Requête : modules installés |
| `_SQL_SOCIETE_AZALPLUS` | `core/connecteurs/azalplus.py` | Requête : lignes de la société, sans société, autres statuts |
| `_SQL_TIERS_AZALPLUS` | `core/connecteurs/azalplus.py` | Requête : noms et codes des clients et fournisseurs actifs |
| `_statut` | `core/montee_version/montee.py` | Méthode : statut de la montée |
| `_surveiller_disque` | `core/montee_version/montee.py` | Méthode : arrête un saut si le disque se remplit |
| `_table` | `interface/transferts.py` | Méthode : table reçue, par son jeton |
| `_telecharger` | `interface/serveur.py` | Méthode de Taches : exécution d'un export |
| `_televerser` | `interface/serveur.py` | Route d'un fichier envoyé brut (FEC déposé, table) |
| `_tester` | `core/connecteurs/transfert.py` | Routine : écriture dans l'environnement de test, relecture, comparaison |
| `_texte_compte_mapping` | `core/mapping.py` | Routine : compte JSON validé et mis en texte |
| `_tmp` | `tests/test_connecteurs.py` | Dossier temporaire d'un test |
| `_TransportDelai` | `core/odoo_source.py` | Transport XML-RPC HTTP avec délai |
| `_TransportSurDelai` | `core/odoo_source.py` | Transport XML-RPC HTTPS avec délai |
| `_travail_feu_vert` | `interface/transferts.py` | Tâche « feu vert » : étapes 6 et 7 |
| `_travail_transfert` | `interface/transferts.py` | Tâche « transfert » : étapes 1 à 4 |
| `_TYPE_OFFICE` | `core/xlsx_ecrire.py` | Préfixe des types de contenu officedocument |
| `_usage_fec` | `interface/transferts.py` | Méthode : FEC source (dépôt) ou destination (produit) |
| `_Valeur` | `stubs/odoo/fields.pyi` | Type de la valeur d'un champ (paramètre générique du stub Field) |
| `_valeur_colonne` | `core/xlsx_vers_fec.py` | Lit la cellule d'un champ dans une ligne (None si absente) |
| `_valeur_en_ligne` | `core/yaml_min.py` | Routine : scalaire ou liste en ligne |
| `_valeurs_fichier_fec` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : valeurs name / fec_filename / fec_file d'une fiche d'import |
| `_verifier_ident` | `interface/transferts.py` | Méthode : refuse un identifiant de transfert mal formé |
| `_verifier_valeur` | `core/montee_version/demandes.py` | Routine : refuse une valeur de demande mal formée |
| `a_verifier` | `core/montee_version/inventaire.py` | Modules à vérifier d'un saut |
| `acces` | `core/odoo_source.py`, `tests/test_montee_pilotee.py` | Accès à un PostgreSQL jetable (host, user, password) |
| `ACTIONS_BASE` | `interface/serveur.py` | Actions de POST /api/taches (sur une base de l'écran Bases) |
| `ACTIONS_MONTEE` | `core/montee_version/demandes.py` | Action d'une demande -> champs attendus |
| `afficher_evenement` | `scripts/outils_cli.py` | Routine partagée : affiche un événement du journal |
| `afficherConnexions` | `interface/static/transferts.js` | Tableau des connexions |
| `afficherMontees` | `interface/static/montees.js` | Liste des montées |
| `app` | `tests/test_ecran_transferts.py` | Application de l'interface dans un test |
| `appels` | `tests/test_montee_pilotee.py` | Appels git simulés |
| `arreter` | `core/montee_version/montee.py` | Méthode : retire PostgreSQL et le réseau |
| `arrivee` | `core/montee_version/inventaire.py`, `core/montee_version/montee.py`, `core/montee_version/openupgrade.py`, `scripts/concorde_montee.py` | Version d'Odoo voulue à la fin de la montée |
| `Atelier` | `tests/test_montee_pilotee.py` | Classe de test : montée simulée |
| `autres` | `tests/test_montee_pilotee.py` | Autres arguments du lanceur |
| `base_client` | `core/montee_version/montee.py` | Nom de la base chez le client (à retaper au feu vert) |
| `bavard` | `tests/test_montee_pilotee.py` | Lanceur simulé qui rend du texte |
| `besoin` | `core/montee_version/montee.py` | Place nécessaire au départ |
| `bloc` | `interface/transferts.py` | Bloc d'octets reçu |
| `bloquant` | `core/montee_version/montee.py` | Module bloquant parcouru |
| `bloquants` | `core/montee_version/inventaire.py`, `core/montee_version/montee.py` | Modules qui bloquent un saut |
| `bloque` | `core/montee_version/inventaire.py` | Vrai si un module bloque un saut |
| `brut_chemin` | `interface/transferts.py` | Fichier brut d'une table reçue (effacé après lecture) |
| `cadre` | `scripts/concorde_montee_service.py` | Cadre reçu avec un signal |
| `calcul` | `core/montee_version/sauvegarde.py` | Calcul SHA-256 en cours |
| `carteDestination` | `interface/static/transferts.js` | Carte d'une destination : 7 étapes, fichiers, feu vert |
| `carteMontee` | `interface/static/montees.js` | Carte d'une montée |
| `cause` | `tests/test_ecran_transferts.py` | Cause d'un refus |
| `causes` | `core/montee_version/montee.py` | Cause d'arrêt d'un saut par le guetteur |
| `champLibre` | `interface/static/transferts.js` | Routine JS : nom de paramètre lisible |
| `chargerEcranMontees` | `interface/static/montees.js` | Charge l'écran Montée |
| `chargerEcranTransferts` | `interface/static/transferts.js` | Charge l'écran Transferts |
| `chargerListeTransferts` | `interface/static/transferts.js` | Tableau des transferts enregistrés |
| `CHEMIN_CLE` | `core/montee_version/volume.py` | Clé du volume chiffré (root, 600) |
| `chemin_dans` | `interface/transferts.py` | Routine partagée : vrai si un chemin reste dans un dossier |
| `CHEMIN_ETATS` | `scripts/concorde_montee_service.py` | Dossier des résumés publiés |
| `CHEMIN_IMAGE` | `core/montee_version/volume.py` | Fichier du volume chiffré |
| `CHEMIN_MONTAGE` | `core/montee_version/volume.py` | Dossier où le volume est monté |
| `CHEMIN_MONTEES` | `core/montee_version/montee.py` | Dossier des montées (CONCORDE_MONTEES) |
| `CHEMIN_OPENUPGRADE` | `core/montee_version/montee.py` | Dossier des copies d'OpenUpgrade (CONCORDE_OPENUPGRADE) |
| `cible_patch` | `tests/test_montee_pilotee.py` | Remplacement actif pendant un test |
| `circuit` | `core/montee_version/montee.py`, `scripts/concorde_montee.py` | Étapes 1 à 4 d'une montée |
| `classer_module` | `core/montee_version/inventaire.py` | Routine : règle de l'inventaire (couvert, à vérifier, bloquant) |
| `classes` | `core/montee_version/inventaire.py` | Modules rangés par classe |
| `cliche` | `core/montee_version/montee.py` | Photo comptable prise |
| `code_ou` | `core/montee_version/montee.py` | Copie d'OpenUpgrade d'un saut |
| `commandes` | `tests/test_montee_pilotee.py` | Commandes docker reçues |
| `commandes_texte` | `tests/test_montee_pilotee.py` | Commandes docker en texte |
| `commit` | `core/montee_version/openupgrade.py` | Commit figé attendu |
| `COMMITS_OPENUPGRADE` | `core/montee_version/openupgrade.py` | Commit figé d'OpenUpgrade par version visée |
| `complet` | `core/montee_version/sauvegarde.py` | Chemin complet d'une pièce jointe |
| `COMPTES_MONTEE` | `tests/test_montee_pilotee.py` | Comptes de la base simulée |
| `conduite` | `scripts/concorde_montee.py`, `tests/test_montee_pilotee.py` | Montée conduite |
| `connexion_fec` | `tests/test_ecran_transferts.py` | Méthode de test : ajoute une connexion FEC |
| `conteneur` | `core/montee_version/montee.py` | Nom d'un conteneur Odoo de saut |
| `conteneur_pg` | `core/montee_version/montee.py` | Nom du PostgreSQL jetable |
| `conteneurs` | `core/montee_version/montee.py` | Méthode : conteneurs prêts pendant un bloc |
| `continuer` | `scripts/concorde_montee_service.py` | Le service doit-il continuer |
| `controler_feu_vert` | `core/connecteurs/transfert.py` | Routine partagée : vérifie qu'un feu vert peut être donné (écran et donner_feu_vert) |
| `cookie` | `tests/test_ecran_transferts.py` | Cookie de session d'un test |
| `couverts` | `core/montee_version/inventaire.py` | Nombre de modules couverts d'un saut |
| `couverture` | `core/montee_version/inventaire.py` | Couverture d'un saut |
| `couverture_saut` | `core/montee_version/inventaire.py` | Routine : table de couverture d'un saut, lue sur le disque |
| `couvertures` | `core/montee_version/inventaire.py`, `core/montee_version/montee.py`, `tests/test_montee_pilotee.py` | Tables de couverture par version visée |
| `CouvertureSaut` | `core/montee_version/inventaire.py` | Type : table et fusions d'un saut |
| `cx` | `tests/test_ecran_transferts.py` | Connexion parcourue dans un test |
| `defaut_mo` | `interface/transferts.py` | Plafond par défaut, en Mo |
| `DELAI_BASE_S` | `tests/integration/base_odoo.py` | Délai d'un appel au service db d'Odoo |
| `DemandeMontee` | `core/montee_version/demandes.py` | Type : demande vérifiée |
| `demander` | `interface/montees.py` | Méthode : dépose une demande au service |
| `demanderMontee` | `interface/static/montees.js` | Dépose une demande et attend son résultat |
| `demandes` | `core/montee_version/demandes.py`, `interface/montees.py` | File des demandes |
| `deposer_demande` | `core/montee_version/demandes.py` | Routine : dépose une demande vérifiée |
| `deposer_zip` | `tests/test_montee_pilotee.py` | Méthode de test : sauvegarde déposée |
| `deposerSauvegarde` | `interface/static/montees.js` | Envoie une sauvegarde .zip |
| `depot` | `interface/transferts.py`, `tests/test_ecran_transferts.py` | Fiche d'un FEC déposé (nom, taille, lignes, totaux) |
| `depot_max` | `interface/transferts.py` | Plafond d'un FEC déposé, en octets |
| `DEPOT_MAX_MO_DEFAUT` | `interface/transferts.py` | Plafond par défaut d'un FEC déposé (200 Mo) |
| `DEPOT_OPENUPGRADE` | `core/montee_version/openupgrade.py` | Dépôt OCA d'OpenUpgrade |
| `depots` | `interface/transferts.py`, `tests/test_ecran_transferts.py` | Dossier des FEC déposés |
| `derniere_purge` | `scripts/concorde_montee_service.py` | Moment du dernier effacement |
| `description` | `interface/transferts.py` | Fichier depot.json ; aussi : description d'une connexion |
| `detail_transfert` | `interface/transferts.py` | Méthode : état complet d'un transfert, libellés et fichiers |
| `detailsEcarts` | `interface/static/montees.js` | Détail des écarts |
| `detailsInventaire` | `interface/static/montees.js` | Détail de l'inventaire |
| `detailsSauts` | `interface/static/montees.js` | Détail des sauts |
| `dialogueDepot` | `interface/static/transferts.js` | Dépôt d'un FEC |
| `dialogueSecret` | `interface/static/transferts.js` | Saisie masquée d'un secret |
| `DISQUE_HOTE` | `core/montee_version/montee.py` | Disque réel du serveur (CONCORDE_DISQUE_HOTE) |
| `docker` | `tests/test_montee_pilotee.py` | Docker simulé d'un test |
| `DONNEES_MONTEE` | `interface/montees.py` | Volume du service de montée, vu de l'interface |
| `donnees_pg` | `tests/test_montee_pilotee.py` | Dossier pgdata simulé |
| `dossier_depot` | `interface/transferts.py` | Dossier du FEC déposé d'une connexion |
| `dossier_fec` | `interface/transferts.py` | Nom du dossier choisi par CONCORDE pour un FEC |
| `dossier_montee` | `core/montee_version/montee.py` | Routine : dossier d'une montée (identifiant vérifié) |
| `dossier_openupgrade` | `core/montee_version/inventaire.py` | Copie d'OpenUpgrade d'un saut |
| `DOSSIER_PIECES` | `core/montee_version/sauvegarde.py` | Dossier des pièces jointes dans une sauvegarde |
| `dossiers` | `core/montee_version/montee.py` | Sous-dossiers parcourus |
| `DOSSIERS_INTERFACE` | `scripts/concorde_montee_service.py` | Dossiers du volume confiés à l'interface |
| `dump` | `core/montee_version/montee.py`, `core/montee_version/sauvegarde.py`, `tests/test_montee_pilotee.py` | Fichier dump.sql |
| `duree` | `tests/test_montee_pilotee.py` | Durée ignorée (sleep simulé) |
| `duree_s` | `core/montee_version/montee.py` | Durée d'une étape, en secondes |
| `duree_saut` | `tests/test_montee_pilotee.py` | Durée simulée d'un saut |
| `ECARTS_GARDES` | `core/montee_version/montee.py` | Écarts gardés dans l'état d'une montée |
| `ecran` | `interface/serveur.py` | L'écran Transferts de l'application, dans une route |
| `EcranMontees` | `interface/montees.py` | Classe : écran Montée de version |
| `EcranTransferts` | `interface/transferts.py` | Classe : ce que fait l'écran Transferts (ADR-0011) |
| `ecrire_sauvegarde` | `core/montee_version/sauvegarde.py` | Routine : sauvegarde Odoo de la base montée |
| `ecrire_secret` | `interface/transferts.py` | Méthode : écrit un secret saisi, rend « renseigné ou non » |
| `effacees` | `core/montee_version/demandes.py` | Montées effacées |
| `emballer` | `tests/integration/base_odoo.py` | Routine : sauvegarde .zip au format d'Odoo |
| `empreinte_fichier` | `core/montee_version/sauvegarde.py` | Routine partagée : SHA-256 d'un fichier |
| `EN_COURS` | `core/montee_version/montee.py` | Statut : étape ou montée en cours |
| `EntreeCouverture` | `core/montee_version/openupgrade.py` | Type : ligne d'un module dans la table |
| `environnement` | `interface/transferts.py` | Variables d'environnement lues |
| `envoyer` | `tests/test_ecran_transferts.py` | Méthode de test : requête JSON ou fichier brut |
| `envoyerFichier` | `interface/static/transferts.js` | Routine JS : envoie un fichier brut (FEC, table) |
| `ErreurCommande` | `core/montee_version/commandes.py` | Programme en échec : code et fin de sortie |
| `ErreurDemande` | `core/montee_version/demandes.py` | Demande mal formée, refusée |
| `ErreurEcran` | `interface/transferts.py` | Demande refusée par l'écran Transferts |
| `ErreurMontee` | `core/montee_version/montee.py` | Montée refusée ou arrêtée |
| `ErreurOpenUpgrade` | `core/montee_version/openupgrade.py` | Saut impossible ou table illisible |
| `ERREURS_ECRAN` | `interface/transferts.py` | Refus rendus au navigateur avec leur cause (HTTP 400) |
| `ERREURS_MONTEE` | `core/montee_version/demandes.py` | Erreurs d'une montée, rendues comme refus |
| `ERREURS_MONTEE_ECRAN` | `interface/montees.py` | Refus de l'écran Montée (HTTP 400) |
| `ErreurSauvegarde` | `core/montee_version/sauvegarde.py` | Sauvegarde Odoo refusée |
| `ErreurVolume` | `core/montee_version/volume.py` | Volume impossible à ouvrir, clé mal protégée |
| `essai_lanceur` | `tests/test_montee_pilotee.py` | Lanceur du nouvel essai |
| `ESSAIS_ODOO` | `tests/integration/attendre_odoo.py` | Essais avant d'abandonner l'attente d'Odoo |
| `EtapeMontee` | `core/montee_version/montee.py` | Type : état d'une étape de montée |
| `ETAPES_MONTEE` | `core/montee_version/montee.py` | Étapes d'une montée, dans l'ordre |
| `ETAPES_MONTEE_ECRAN` | `interface/static/montees.js` | Étapes affichées d'une montée |
| `ETAPES_TRANSFERT` | `interface/static/transferts.js` | Les 7 étapes d'une destination, avec leur nom affiché |
| `etat_couvert` | `core/montee_version/openupgrade.py` | Routine : état de table « couvert » |
| `EtatMontee` | `core/montee_version/montee.py` | Type : état complet d'une montée (montee.json) |
| `etatMontees` | `interface/static/montees.js` | État de l'écran Montée |
| `etats` | `core/montee_version/openupgrade.py` | États lus dans la table |
| `ETATS_COUVERTS` | `core/montee_version/openupgrade.py` | États de la table qui valent « couvert » |
| `ETATS_MONTEE` | `interface/montees.py` | Résumés publiés par le service |
| `etatTransferts` | `interface/static/transferts.js` | État de l'écran : logiciels, plafond de dépôt, connexions |
| `examiner_sauvegarde` | `core/montee_version/sauvegarde.py` | Routine : relit une sauvegarde sans l'extraire |
| `exc` | `interface/transferts.py` | Erreur attrapée |
| `extraction` | `core/montee_version/montee.py` | Dossier d'extraction de la sauvegarde |
| `extraire_sauvegarde` | `core/montee_version/sauvegarde.py` | Routine : extrait dump et pièces jointes |
| `faire` | `tests/test_ecran_montees.py` | Méthode de test : demande traitée par le service |
| `faire_inventaire` | `core/montee_version/montee.py` | Méthode : étape 1 de la montée |
| `FauxDocker` | `tests/test_montee_pilotee.py` | Docker simulé |
| `FEC_VENTES` | `tests/test_ecran_transferts.py` | FEC d'essai : à-nouveaux et une vente |
| `fermer_volume` | `core/montee_version/volume.py` | Routine : démonte et referme le volume |
| `fichier_apriori` | `core/montee_version/openupgrade.py` | Routine : chemin d'apriori.py |
| `fichier_couverture` | `core/montee_version/openupgrade.py` | Routine : chemin de la table d'un saut |
| `filestore` | `core/montee_version/montee.py` | Pièces jointes de la base restaurée |
| `fin_de_journal` | `core/montee_version/montee.py` | Routine : fin d'un journal de montée |
| `fin_de_sortie` | `core/montee_version/commandes.py` | Routine partagée : dernières lignes d'une sortie ou d'un journal |
| `fini` | `core/montee_version/commandes.py`, `core/montee_version/montee.py` | Programme terminé ; aussi : signal de fin du guetteur de disque |
| `flux` | `interface/transferts.py` | Corps de requête à lire |
| `FluxEntrant` | `interface/transferts.py` | Protocole : corps de requête lisible par blocs |
| `formulaireFeuVert` | `interface/static/transferts.js` | Feu vert : libellé retapé et date de sauvegarde |
| `formulaireFeuVertMontee` | `interface/static/montees.js` | Feu vert d'une montée |
| `formulaireNouvelEssai` | `interface/static/montees.js` | Nouvel essai sur une copie fraîche |
| `fraiche` | `tests/test_montee_pilotee.py` | Sauvegarde fraîche |
| `fusion` | `core/montee_version/inventaire.py` | Module qui en reprend un autre |
| `fusion_notee` | `core/montee_version/openupgrade.py` | Routine : module repreneur d'après la note |
| `fusions` | `core/montee_version/inventaire.py`, `core/montee_version/openupgrade.py` | Fusions et renommages d'un saut |
| `FUSIONS_APRIORI` | `core/montee_version/openupgrade.py` | Dictionnaires lus dans apriori.py |
| `git` | `tests/test_montee_pilotee.py` | git simulé |
| `GO` | `core/montee_version/montee.py` | Un gigaoctet, en octets |
| `guetter` | `core/montee_version/montee.py` | Fonction du guetteur de disque |
| `guetteur` | `core/montee_version/montee.py` | Fil qui mesure le disque pendant un saut |
| `ident_connexion` | `interface/serveur.py` | Identifiant de connexion lu dans l'URL |
| `ident_cx` | `interface/transferts.py` | Identifiant d'une connexion d'un transfert |
| `ident_tache` | `interface/transferts.py` | Identifiant de la tâche lancée |
| `identite` | `core/montee_version/montee.py` | Sortie de « id -u » de l'image |
| `image` | `core/montee_version/montee.py` | Image Docker d'un saut |
| `IMAGE_POSTGRES` | `core/montee_version/montee.py` | Image du PostgreSQL jetable |
| `inconnus` | `core/connecteurs/connexions.py` | Paramètres reçus inconnus du connecteur |
| `InfoSauvegarde` | `core/montee_version/sauvegarde.py` | Type : ce que dit une sauvegarde |
| `Inventaire` | `core/montee_version/inventaire.py` | Type : résultat de l'inventaire d'une base |
| `inventorier` | `core/montee_version/inventaire.py` | Routine : classe chaque module, saut par saut |
| `ip` | `interface/transferts.py` | Adresse IP de la session qui donne le feu vert |
| `JOURS_CONSERVATION` | `core/montee_version/demandes.py` | Jours avant l'effacement d'une montée (30) |
| `json_ok` | `tests/test_ecran_transferts.py` | Méthode de test : requête qui doit réussir |
| `lancements` | `tests/test_montee_pilotee.py` | Commandes docker run |
| `lancer_transfert` | `interface/transferts.py` | Méthode : valide puis lance les étapes 1 à 4 |
| `lanceur` | `core/montee_version/montee.py` | Paramètre : lanceur de programmes |
| `LanceurProgramme` | `core/montee_version/montee.py` | Type : lance un programme (simulé dans les tests) |
| `libelleConnexion` | `interface/static/transferts.js` | Libellé d'une connexion par son identifiant |
| `libre` | `core/montee_version/montee.py`, `tests/test_montee_pilotee.py` | Place libre mesurée |
| `LIBRE_MINIMUM` | `core/montee_version/montee.py` | Garde-fou : place libre minimale pendant un saut (2 Go) |
| `libres` | `tests/test_montee_pilotee.py` | Places libres successives simulées |
| `ligneEtapeMontee` | `interface/static/montees.js` | Ligne d'une étape |
| `LIGNES_ERREUR` | `core/montee_version/commandes.py` | Lignes de sortie gardées dans un message d'échec |
| `lire_apriori` | `core/montee_version/openupgrade.py` | Routine : fusions lues dans apriori.py, sans exécution |
| `lire_couverture` | `core/montee_version/openupgrade.py` | Routine : table de couverture -> {module: état} |
| `lire_demande` | `core/montee_version/demandes.py` | Routine : relit et vérifie une demande |
| `lire_modules` | `core/montee_version/inventaire.py` | Routine : version et modules installés d'une base |
| `liste_sauts` | `core/montee_version/inventaire.py` | Sauts de l'inventaire |
| `listeModules` | `interface/static/montees.js` | Liste de modules d'un saut |
| `lister_transferts` | `interface/transferts.py` | Méthode : transferts enregistrés, plus récent d'abord |
| `livraison` | `core/montee_version/demandes.py`, `interface/montees.py` | Date de livraison ; aussi : méthode, chemin de la sauvegarde livrée |
| `livraisons` | `core/montee_version/demandes.py`, `interface/montees.py` | Dossier des sauvegardes livrées |
| `LIVREE` | `core/montee_version/montee.py` | Statut : montée livrée |
| `livrer` | `core/montee_version/montee.py` | Méthode : étape 7, sauvegarde livrée |
| `logicielBranche` | `interface/static/transferts.js` | Routine JS : description d'un logiciel branché |
| `logiciels` | `interface/transferts.py` | Méthode : logiciels branchés et ce que chacun demande |
| `maintenant` | `core/montee_version/demandes.py` | Date de référence de l'effacement |
| `majDestinations` | `interface/static/transferts.js` | Destinations possibles (jamais la source) |
| `majeure` | `core/montee_version/sauvegarde.py` | Version majeure lue |
| `majFormulaireAjout` | `interface/static/transferts.js` | Champs du formulaire d'ajout selon le logiciel |
| `manifeste` | `core/montee_version/sauvegarde.py` | Contenu de manifest.json |
| `MARGE_DEPART` | `core/montee_version/montee.py` | Garde-fou : marge de départ (3 Go) |
| `marque` | `core/montee_version/montee.py` | Fichier qui marque la restauration faite |
| `mauvaise` | `tests/test_ecran_transferts.py` | Valeur refusée de CONCORDE_DEPOT_MAX_MO |
| `mauvaise_version` | `tests/test_montee_pilotee.py` | Version de PostgreSQL refusée |
| `membre` | `core/montee_version/sauvegarde.py` | Membre d'une archive zip |
| `membres` | `core/montee_version/sauvegarde.py` | Membres utiles d'une archive |
| `MEMOIRE_CONTENEUR` | `core/montee_version/montee.py` | Mémoire maximale d'un conteneur de montée |
| `module` | `core/montee_version/inventaire.py`, `tests/test_montee_pilotee.py` | Nom d'un module Odoo |
| `module_ancien` | `core/montee_version/openupgrade.py` | Ancien nom de module |
| `module_repreneur` | `core/montee_version/openupgrade.py` | Module qui reprend l'ancien |
| `ModuleBloquant` | `core/montee_version/inventaire.py` | Type : module et cause (bloquant ou à vérifier) |
| `modules` | `core/montee_version/inventaire.py`, `core/montee_version/montee.py` | Modules installés d'une base |
| `MODULES_CLIENT` | `tests/test_montee_pilotee.py` | Modules de la base simulée |
| `MODULES_ODOO` | `core/montee_version/montee.py` | Dossier des modules d'Odoo dans l'image officielle |
| `montage` | `core/montee_version/volume.py`, `tests/test_montee_pilotee.py` | Dossier monté |
| `Montee` | `core/montee_version/montee.py` | Classe : conduite d'une montée |
| `montee_id` | `tests/test_montee_pilotee.py` | Montée créée par la file |
| `montee_photo_sql` | `tests/test_montee_pilotee.py` | Requête des lignes de la photo |
| `montees` | `interface/montees.py`, `interface/serveur.py` | Résumés des montées ; aussi : écran de l'application |
| `monter` | `core/montee_version/montee.py` | Méthode : étape 3, saut par saut |
| `muet` | `tests/test_montee_pilotee.py` | Lanceur simulé où PostgreSQL ne répond pas |
| `neuf` | `core/montee_version/volume.py` | Volume à créer |
| `noeud` | `core/montee_version/openupgrade.py` | Nœud de l'arbre d'apriori.py |
| `NOM_DUMP` | `core/montee_version/sauvegarde.py` | Nom du dump dans une sauvegarde |
| `NOM_MANIFESTE` | `core/montee_version/sauvegarde.py` | Nom du manifeste dans une sauvegarde |
| `NOM_VOLUME` | `core/montee_version/volume.py` | Nom du volume ouvert |
| `NOMS_FICHIERS` | `interface/static/transferts.js` | Nom affiché des fichiers d'un transfert |
| `note` | `core/montee_version/openupgrade.py`, `tests/test_montee_pilotee.py` | Note d'un module dans la table |
| `NOTE_SANS_CHANGEMENT` | `core/montee_version/openupgrade.py` | Note « No DB layout changes » |
| `noter` | `tests/test_montee_pilotee.py` | Lanceur simulé qui garde les commandes |
| `nouvel_essai` | `core/montee_version/montee.py` | Routine : étape 6, copie fraîche |
| `obtenu` | `core/montee_version/openupgrade.py` | Commit obtenu après récupération |
| `octets` | `core/montee_version/sauvegarde.py` | Taille d'un fichier, en octets |
| `octets_base` | `core/montee_version/montee.py` | Taille décompressée de la base |
| `octets_decompresses` | `core/montee_version/sauvegarde.py` | Taille décompressée d'une sauvegarde |
| `odoo_repond` | `tests/integration/attendre_odoo.py` | Routine : Odoo répond-il ? |
| `ok` | `tests/test_ecran_montees.py` | Méthode de test : requête qui doit réussir |
| `openupgrade` | `core/montee_version/montee.py`, `tests/test_montee_pilotee.py` | Dossier des copies d'OpenUpgrade |
| `OPENUPGRADELIB` | `core/montee_version/openupgrade.py` | Bibliothèque installée dans l'image (figée) |
| `ouvrir_volume` | `core/montee_version/volume.py` | Routine : crée, ouvre et monte le volume |
| `ouvrirTransfert` | `interface/static/transferts.js` | Détail d'un transfert |
| `par_nom` | `tests/test_ecran_transferts.py` | Logiciels rangés par nom |
| `parametres_facultatifs` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Paramètres acceptés en plus des requis ; l'annuaire refuse tout autre nom |
| `parent` | `interface/transferts.py` | Dossier parcouru (os.walk) |
| `PART_PROCESSEUR` | `core/montee_version/montee.py` | Priorité processeur basse des conteneurs |
| `pas_zip` | `tests/test_montee_pilotee.py` | Fichier qui n'est pas un zip |
| `PAUSE_FILE_S` | `scripts/concorde_montee_service.py` | Pause entre deux passages de la file |
| `PAUSE_S` | `tests/integration/attendre_odoo.py` | Pause entre deux essais |
| `peripherique` | `core/montee_version/volume.py` | Périphérique du volume ouvert |
| `PG_DEFAUT` | `core/montee_version/sauvegarde.py` | Version de PostgreSQL sans manifeste |
| `PG_MAX` | `core/montee_version/sauvegarde.py` | Version de PostgreSQL la plus haute acceptée |
| `PG_MIN` | `core/montee_version/sauvegarde.py` | Version de PostgreSQL la plus basse acceptée |
| `pg_version` | `core/montee_version/sauvegarde.py`, `tests/integration/base_odoo.py` | Version de PostgreSQL du client |
| `photos` | `tests/test_montee_pilotee.py` | Photos prises (avant ou après) |
| `place_libre` | `core/montee_version/montee.py`, `tests/test_montee_pilotee.py` | Routine : octets libres sur un disque |
| `plus_tard` | `tests/test_montee_pilotee.py` | Date 31 jours plus tard |
| `PREFIXE_LOCALISATION` | `core/montee_version/inventaire.py` | Préfixe des modules de localisation (l10n_) |
| `premier` | `tests/test_montee_pilotee.py` | Premier saut de l'inventaire |
| `preparer` | `core/montee_version/montee.py` | Méthode : place, réseau, PostgreSQL, restauration |
| `preparer_dossiers` | `scripts/concorde_montee_service.py` | Routine : dossiers de l'interface dans le volume |
| `preparerAjout` | `interface/static/transferts.js` | Prépare le formulaire d'ajout |
| `preparerTransfert` | `interface/static/transferts.js` | Prépare le formulaire de nouveau transfert |
| `pret` | `interface/montees.py` | Service de montée prêt |
| `PROCESSEURS_CONTENEUR` | `core/montee_version/montee.py` | Processeurs au plus par conteneur |
| `programme` | `core/montee_version/montee.py` | Outil PostgreSQL lancé |
| `proprietaire` | `core/montee_version/demandes.py`, `scripts/concorde_montee_service.py` | (uid, gid) du compte de l'interface |
| `public` | `core/montee_version/demandes.py`, `tests/test_montee_pilotee.py` | Fichier publié d'une montée |
| `PUBLICATION_S` | `core/montee_version/demandes.py` | Intervalle de republication pendant une demande |
| `publier` | `core/montee_version/demandes.py` | Méthode : résumé d'une montée pour l'écran |
| `PURGE_S` | `scripts/concorde_montee_service.py` | Intervalle entre deux effacements |
| `purger` | `core/montee_version/demandes.py` | Méthode : efface les montées de plus de 30 jours |
| `quoi` | `core/montee_version/montee.py` | Conteneur ou réseau |
| `racine_copie` | `tests/test_montee_pilotee.py` | Copie d'OpenUpgrade simulée |
| `recette` | `core/montee_version/montee.py` | Dockerfile d'un saut |
| `recevoir_fichier` | `interface/transferts.py` | Routine partagée : corps de requête -> fichier, par blocs, plafonné |
| `recevoir_table` | `interface/transferts.py` | Méthode : reçoit une table de correspondance, rend un jeton |
| `rechargerConnexions` | `interface/static/transferts.js` | Relit les connexions et met l'écran à jour |
| `recu` | `interface/transferts.py` | Fichier reçu avant sa relecture |
| `recuperer` | `core/montee_version/openupgrade.py`, `tests/test_montee_pilotee.py` | Routine : copie d'OpenUpgrade au commit figé |
| `recus` | `interface/transferts.py` | Paramètres reçus du navigateur |
| `relatif` | `interface/transferts.py` | Chemin d'un fichier relatif au dossier d'un transfert |
| `rendreTacheTransfert` | `interface/static/transferts.js` | Résultat d'une tâche de transfert ou de feu vert |
| `repere` | `core/montee_version/demandes.py` | Date de référence d'une montée |
| `reponses_apres` | `tests/test_montee_pilotee.py` | Base simulée après la montée |
| `reponses_avant` | `tests/test_montee_pilotee.py` | Base simulée avant la montée |
| `republier` | `core/montee_version/demandes.py` | Fonction du fil de republication |
| `requete_lecture` | `core/montee_version/photo.py` | Routine partagée : requête de lecture SQL (photo, inventaire) |
| `reseau` | `core/montee_version/montee.py` | Réseau Docker interne d'une montée |
| `restant` | `interface/transferts.py` | Octets restant à recevoir |
| `restauree` | `core/montee_version/montee.py` | Marque de restauration faite |
| `restaurer` | `tests/integration/base_odoo.py` | Routine : restaure une sauvegarde dans Odoo |
| `resultat_demande` | `interface/montees.py` | Méthode : résultat d'une demande |
| `resumes` | `interface/transferts.py` | Résumés des transferts |
| `retire` | `core/montee_version/openupgrade.py`, `tests/test_montee_pilotee.py` | Module retiré (marque del) |
| `retirerConnexion` | `interface/static/transferts.js` | Retire une connexion après confirmation |
| `ROUTES_MONTEE` | `interface/serveur.py` | Route -> action de montée |
| `SAISIE_PENNYLANE` | `tests/test_ecran_transferts.py` | Valeur de secret saisie dans un test (jamais renvoyée) |
| `sans_changement` | `core/montee_version/openupgrade.py` | Routine : note « aucun changement de base » |
| `saut` | `core/montee_version/inventaire.py`, `core/montee_version/montee.py`, `tests/test_montee_pilotee.py` | Saut de version parcouru |
| `saut_en_echec` | `tests/test_montee_pilotee.py` | Saut simulé en échec |
| `SautInventaire` | `core/montee_version/inventaire.py` | Type : un saut de l'inventaire |
| `sauts` | `core/montee_version/openupgrade.py`, `core/montee_version/inventaire.py` | Routine : versions visées une à une ; aussi : sauts d'un inventaire |
| `sauvegarde` | `core/montee_version/montee.py` | Sauvegarde .zip d'une montée |
| `sauvegarde_livree` | `tests/test_montee_pilotee.py` | Sauvegarde livrée |
| `SAUVEGARDE_MAX_MO_DEFAUT` | `interface/montees.py` | Plafond d'une sauvegarde déposée (4 Go) |
| `sauvegarde_zip` | `tests/test_montee_pilotee.py` | Routine de test : petite sauvegarde Odoo |
| `sauver` | `core/montee_version/montee.py` | Routine : écrit montee.json |
| `SCRIPTS_MONTEE` | `core/montee_version/montee.py` | Dossier des scripts de montée dans OpenUpgrade |
| `second` | `tests/test_montee_pilotee.py` | Second saut de l'inventaire |
| `sertDe` | `interface/static/transferts.js` | Routine JS : rôle d'une connexion (source, destination) |
| `serveur` | `tests/test_ecran_transferts.py` | Serveur HTTP d'un test |
| `service` | `scripts/concorde_montee_service.py`, `tests/test_montee_pilotee.py`, `tests/test_ecran_montees.py` | Service de montée |
| `service_bases` | `tests/integration/base_odoo.py` | Routine : service db d'Odoo |
| `ServiceMontee` | `core/montee_version/demandes.py` | Classe : ce que fait le service de montée |
| `sha256` | `core/montee_version/sauvegarde.py` | Empreinte d'un fichier |
| `signal_recu` | `scripts/concorde_montee_service.py` | Signal reçu |
| `sorties` | `interface/transferts.py` | Dossier des FEC produits |
| `suivants` | `core/montee_version/inventaire.py` | Modules présents après un saut |
| `suivreTransfert` | `interface/static/transferts.js` | Suit une tâche de transfert puis ouvre le transfert |
| `SURVEILLANCE_S` | `core/montee_version/montee.py` | Intervalle de mesure du disque pendant un saut |
| `table_couverture` | `tests/test_montee_pilotee.py` | Routine de test : table de couverture |
| `TABLE_MAX_OCTETS` | `interface/transferts.py` | Plafond d'une table de correspondance (5 Mo) |
| `taches` | `interface/transferts.py` | Tâches de l'interface, dans l'écran Transferts |
| `taille_depot_max` | `interface/transferts.py` | Routine : plafond d'un FEC déposé (CONCORDE_DEPOT_MAX_MO) |
| `taille_max` | `interface/transferts.py` | Plafond de réception, en octets |
| `TAILLE_VOLUME` | `core/montee_version/volume.py` | Taille maximale du volume (fichier creux) |
| `TestCasLimites` | `tests/test_montee_pilotee.py` | Classe de test : pannes nommées |
| `TestCircuit` | `tests/test_montee_pilotee.py` | Classe de test : étapes 1 à 4 |
| `TestCommandeMonteePilotee` | `tests/test_montee_pilotee.py` | Classe de test : sous-commandes |
| `TestCommandes` | `tests/test_montee_pilotee.py` | Classe de test : lancement des programmes |
| `TestCreation` | `tests/test_montee_pilotee.py` | Classe de test : création d'une montée |
| `TestEcranMontees` | `tests/test_ecran_montees.py` | Classe de test : écran Montée |
| `TestEcranTransferts` | `tests/test_ecran_transferts.py` | Classe de test : écran Transferts par HTTP |
| `testerConnexion` | `interface/static/transferts.js` | Teste une connexion et montre le résultat |
| `TestFeuVertEtLivraison` | `tests/test_montee_pilotee.py` | Classe de test : étapes 5 à 7 |
| `TestFileDeDemandes` | `tests/test_montee_pilotee.py` | Classe de test : service de montée |
| `TestOpenUpgradeEtInventaire` | `tests/test_montee_pilotee.py` | Classe de test : OpenUpgrade et inventaire |
| `TestOutilsEcran` | `tests/test_ecran_transferts.py` | Classe de test : routines de l'écran |
| `TestSauvegarde` | `tests/test_montee_pilotee.py` | Classe de test : sauvegarde Odoo |
| `TestVolume` | `tests/test_montee_pilotee.py` | Classe de test : volume chiffré |
| `texte_corps` | `interface/transferts.py` | Routine partagée : champ texte du corps d'une requête |
| `texte_date` | `interface/transferts.py` | Date de sauvegarde reçue, en texte |
| `TEXTE_MAX` | `core/montee_version/demandes.py` | Longueur maximale d'un texte de demande |
| `tiroir` | `interface/static/transferts.js` | Routine JS : ouvre le tiroir avec un titre et un contenu |
| `traiter` | `core/montee_version/demandes.py` | Méthode : exécute une demande |
| `traiter_file` | `core/montee_version/demandes.py` | Méthode : traite les demandes en attente |
| `Travail` | `interface/serveur.py` | Type : travail d'une tâche branchée par un autre module |
| `travaux` | `interface/serveur.py` | Taches : action -> travail branché (transfert, feu vert) |
| `url_feu_vert` | `tests/test_ecran_transferts.py` | Route du feu vert d'un transfert |
| `usage` | `interface/transferts.py`, `tests/test_ecran_transferts.py` | Rôle d'un FEC : source ou destination |
| `_verifier_version` | `core/export_odoo.py` | Routine partagée : refuse une version Odoo inconnue |
| `_verrou` | `core/connecteurs/connexions.py` | Verrou de l'annuaire entre les fils |
| `_verrou_des_verrous` | `core/connecteurs/transfert.py` | Verrou qui protège le dictionnaire des verrous par connexion |
| `_verrous` | `core/connecteurs/transfert.py` | Verrous par connexion (une écriture à la fois) |
| `_verrous_texte` | `core/odoo_source.py` | Routine : dates de verrouillage -> texte ISO (instantanés SQL et XML-RPC) |
| `_vers_json` | `core/migration/circuit.py` | Valeur non JSON -> texte (remplace le lambda `default`) |
| `a_arbitrer` | `core/connecteurs/transfert.py` | Comptes absents de la table, à faire traduire |
| `absents` | `core/connecteurs/base.py`, `core/connecteurs/odoo.py`, `core/migration/injection.py`, `core/connecteurs/pennylane.py` | Paramètres ou secrets manquants d'un connecteur ; aussi : Paramètres ou secrets manquants ; éléments absents d'Odoo |
| `action` | `tests/test_xlsx_vers_fec.py`, `tests/test_connecteurs.py` | Action simulée levant une erreur de lecture |
| `ActionOdoo` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type d'une action Odoo rendue au client web |
| `adresse` | `core/migration/injection.py`, `core/connecteurs/http_json.py` | Paramètre : URL du service XML-RPC |
| `ADRESSE_PENNYLANE` | `core/connecteurs/pennylane.py` | Adresse de l'API v2 de Pennylane |
| `ajouter` | `core/connecteurs/connexions.py`, `scripts/concorde_connexion.py`, `interface/transferts.py` | Méthode de l'annuaire : enregistre une connexion ; aussi : méthode de l'écran Transferts : ajoute une connexion (chemins FEC choisis par CONCORDE) |
| `AlerteEnregistree` | `core/surveillance.py` | Type : alerte mémorisée dans le fichier JSON du centre |
| `analyseur` | `scripts/concorde_connexion.py` | Analyseur argparse de concorde_connexion |
| `analytique` | `core/migration/filtres.py`, `core/connecteurs/azalplus.py` | Critères du filtre en cours de normalisation |
| `analytiques_choisis` | `core/comparaison.py` | Ensemble des comptes analytiques du filtre |
| `ancien` | `core/connecteurs/secrets.py` | Masque umask d'avant l'écriture du fichier de secrets |
| `ANNEE_MAX` | `core/xlsx_vers_fec.py` | Année maximale plausible d'une date (2100) |
| `ANNEE_MIN` | `core/xlsx_vers_fec.py` | Année minimale plausible d'une date (1900) |
| `annoncer_constats` | `core/migration/lot.py` | Routine partagée : écrit les constats d'un rapport dans le journal |
| `Annuaire` | `core/connecteurs/connexions.py` | Classe : connexions enregistrées (connexions.json, sans secret) |
| `annuaire_connexions` | `core/connecteurs/transfert.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py` | Annuaire des connexions utilisé par le transfert |
| `Anomalie` | `core/demat.py` | TypedDict : anomalie regroupée par code |
| `appliquer` | `tests/test_connecteurs.py` | Fonction filtres.appliquer d'origine, dans un test |
| `appliquer_cascade` | `core/xlsx_vers_fec.py` | Regroupe les lignes Quadra non rattachées et rattache les groupes soldés |
| `apres` | `core/connecteurs/transfert.py` | Totaux du lot + lignes retirées par les filtres |
| `arbre` | `tests/test_yaml_min.py` | Paramètre : table YAML lue dont on extrait une section |
| `archive` | `deploy/addons/concorde/wizard/concorde_import_wizard.py`, `interface/serveur.py`, `tests/test_assistant_import.py` | Archive zip ouverte (écriture ou lecture) |
| `archive_cassee` | `tests/test_xlsx_vers_fec.py` | Octets d'un zip tronqué (illisible) |
| `archive_complete` | `tests/test_mapping.py` | Classeur de mapping complet en octets |
| `archive_sans_feuille` | `tests/test_xlsx_vers_fec.py` | Classeur de test sans feuille trouvable |
| `archive_vide` | `tests/test_mapping.py` | Zip sans partie de classeur |
| `archive_xlsx` | `tests/classeurs_xlsx.py` | Routine : zip en mémoire à partir de {chemin: xml} |
| `args` | `scripts/concorde_connexion.py` | Arguments lus par argparse |
| `arguments` | `injectors/socle_odoo.py`, `tests/test_connecteurs.py` | Arguments positionnels de la méthode ORM ; aussi : arguments de la commande simulée (test_connecteurs) |
| `argv` | `tests/test_connecteurs.py` | Ligne de commande simulée d'un test |
| `ascii_seul` | `core/fichier_json.py` | Paramètre de ecrire_json_atomique (ensure_ascii) |
| `assistant` | `tests/test_assistant_import.py` | Assistant d'import chargé hors d'Odoo |
| `AssistantImport` | `tests/test_assistant_import.py` | Protocole : partie de l'assistant d'import vérifiée (`_lire_binaire`) |
| `attendre` | `core/connecteurs/http_json.py`, `tests/test_ecran_transferts.py` | Paramètre : fonction d'attente ; aussi : méthode de test : attend la fin d'une tâche |
| `attendu` | `core/migration/filtres.py`, `tests/test_connecteurs.py` | Valeur attendue par une condition libre |
| `attendus` | `tests/test_mapping.py`, `tests/test_plan_comptable.py`, `scripts/concorde_connexion.py` | Valeurs attendues d'un test ; aussi : secrets attendus par le connecteur ajouté (concorde_connexion) |
| `ATTENTE` | `core/connecteurs/transfert.py` | Statut d'une destination : rapport prêt, en attente du feu vert |
| `ATTENTE_MAX_S` | `core/connecteurs/http_json.py` | Attente maximale après une limite d'appels (secondes) |
| `attentes` | `tests/test_connecteurs.py` | Attentes demandées, dans un test |
| `attribut_reference` | `tests/classeurs_xlsx.py` | Attribut r="..." d'une cellule (vide si absent) |
| `attribut_type` | `tests/classeurs_xlsx.py` | Attribut t="..." d'une cellule (vide si absent) |
| `attributs` | `tests/test_assistant_import.py` | Paramètre : noms et valeurs exposés par un module simulé |
| `au` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Fin de période (comprise), None = sans borne |
| `audit` | `core/connecteurs/transfert.py` | Guardian du transfert (audit chaîné) |
| `AUJ` | `tests/test_connecteurs.py` | Date des contrôles dans les tests de transfert (08/11/2026) |
| `aujourd_hui` | `core/connecteurs/transfert.py` | Date des contrôles (dates futures) |
| `autocommit` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Paramètre de set_session (DB-API) |
| `automatique` | `interface/serveur.py` | Rapport du jour construit automatiquement |
| `autre` | `core/plan_comptable.py` | Clé de correspondance comparée aux autres clés trouvées |
| `autres_statuts` | `core/connecteurs/azalplus.py` | Lignes d'un statut ni VALIDEE ni VALIDE |
| `avant` | `core/connecteurs/transfert.py` | Totaux de la source lue |
| `avertir_si_non_chiffre` | `scripts/outils_cli.py` | Avertit si l'URL Odoo est en http hors machine locale |
| `azalplus` | `tests/test_connecteurs.py` | Méthode de test : connecteur AzalPlus |
| `Bac` | `tests/test_connecteurs.py` | Classe de test : dossier, annuaire et secrets temporaires |
| `banque` | `tests/test_connecteurs.py` | Ligne de banque lue, dans un test |
| `base` | `tests/test_connecteurs.py` | Nom de la base Odoo |
| `base_pg` | `tests/test_connecteurs.py` | Base AzalPlus simulée d'un test |
| `bases_ignorees` | `interface/serveur.py` | Attribut de Bases : {nom : motif} des bases du serveur écartées au dernier passage |
| `bilan` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Résultat brut d'une étape lu par _bilan_etape |
| `BilanEquilibre` | `core/moteur.py` | TypedDict du résultat de `verifier_equilibre` |
| `BilanMapping` | `core/mapping.py` | TypedDict du résultat de `mapper_comptes` |
| `BLOQUEE` | `core/connecteurs/transfert.py` | Statut d'une destination ou d'une étape arrêtée |
| `body` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Paramètre : corps de la requête (http.client) |
| `bon_test` | `tests/test_connecteurs.py` | Connexion de test qui accepte l'écriture, dans un test |
| `bonne` | `tests/test_connecteurs.py` | Destination qui passe, dans un test |
| `brut` | `core/migration/filtres.py`, `core/connecteurs/fec.py`, `core/connecteurs/http_json.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni ; aussi : contenu du FEC déposé (connecteurs/fec) |
| `candidat` | `interface/serveur.py` | Constat examiné lors d'une recherche |
| `candidats` | `core/comparaison.py` | Écritures de B candidates au rapprochement par contenu (ex-`cands` réaffecté) |
| `canon` | `tests/test_assistant_import.py` | Journal canonique de test (FEC synthétique) |
| `canon_trouve` | `core/canonical.py` | Canonique lu dans le dict de pipeline par `extraire_canon` |
| `canon_vide` | `tests/test_mapping.py` | Canonique vide fourni à extraire_canon |
| `capacites` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Capacités d'un connecteur (classe ou instance) |
| `CapacitesConnecteur` | `core/connecteurs/base.py` | TypedDict : ce qu'un connecteur sait lire et écrire (api, fichier, None) |
| `caractere` | `core/xlsx_ecrire.py` | Couple (caractère, entité) de `entites` |
| `cas` | `tests/test_connecteurs.py` | Cas d'erreur testés |
| `cas_acceptes` | `tests/test_xlsx_vers_fec.py` | Entrées acceptées et sortie attendue |
| `cas_de_test` | `tests/test_xlsx_vers_fec.py` | Paramètre : TestCase qui vérifie le refus |
| `cas_refuses` | `tests/test_xlsx_vers_fec.py` | Entrées qui doivent être refusées |
| `cellule_brute` | `tests/classeurs_xlsx.py` | Routine : cellule <c t><v> brute |
| `cellule_texte` | `tests/classeurs_xlsx.py` | Routine : cellule inlineStr (texte échappé) |
| `cellule_xml` | `tests/classeurs_xlsx.py` | Routine : cellule selon le type Python de la valeur |
| `cellules` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py` | Fragments XML des cellules d'une ligne |
| `CelluleXlsx` | `core/xlsx_vers_fec.py` | Type : valeur d'une cellule lue (texte, nombre, date, vide) |
| `centimes` | `core/migration/connecteur_fec.py`, `injection.py` | Paramètre : montant en centimes (`_euros`, `euros`) |
| `CHAINES_PARTAGEES` | `tests/test_xlsx_vers_fec.py` | sharedStrings : « Compte » et un texte riche en deux morceaux |
| `chaines_partagees_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de xl/sharedStrings.xml (None = absent) |
| `chaines_presentes` | `tests/test_xlsx_vers_fec.py` | Vrai si le classeur de test a des sharedStrings |
| `champ` | `core/connecteurs/secrets.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py` | Nom d'un secret attendu par un connecteur |
| `champ_bouchon` | `tests/test_assistant_import.py` | Remplace un constructeur de champ Odoo |
| `champ_entete` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Colonne d'une ligne FEC lue pour trouver l'en-tête |
| `champs` | `core/connecteurs/secrets.py` | Noms des secrets attendus par un connecteur |
| `champs_ligne` | `core/migration/filtres.py` | Vue {champ: valeur} d'une ligne pour une condition libre |
| `charger` | `core/connecteurs/transfert.py` | Routine : état d'un transfert enregistré |
| `charger_assistant_import` | `tests/test_assistant_import.py` | Charge l'assistant d'import hors d'Odoo |
| `chemin` | `tests/classeurs_xlsx.py`, `tests/test_plan_comptable.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/secrets.py`, `core/connecteurs/transfert.py`, `core/fichier_json.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Chemin d'un fichier ou d'une partie de classeur ; aussi : fichier FEC, annuaire ou secrets (connecteurs) |
| `chemin_absent` | `tests/test_mapping.py` | Chemin d'un fichier de mapping inexistant |
| `chemin_assistant` | `tests/test_assistant_import.py` | Chemin du fichier de l'assistant |
| `chemin_classeur` | `tests/test_mapping.py` | Chemin du classeur de mapping temporaire |
| `CHEMIN_CONFIGURATION` | `tests/test_yaml_min.py` | Chemin du vrai concorde.yaml du dépôt |
| `CHEMIN_CONNEXIONS` | `core/connecteurs/connexions.py` | Fichier de l'annuaire des connexions (CONCORDE_CONNEXIONS) |
| `chemin_executable` | `securite/concorde_securite.py` | Chemin absolu d'un programme (FileNotFoundError si absent) |
| `chemin_feuille` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Chemin de la feuille dans l'archive |
| `chemin_fichier` | `interface/serveur.py`, `interface/transferts.py` | Chemin d'un fichier produit ; aussi : fichier d'un transfert, sans sortir de son dossier (écran Transferts) |
| `chemin_mapping` | `tests/test_moteur.py` | Chemin du fichier JSON de mapping synthétique |
| `CHEMIN_PREMIERE_FEUILLE` | `tests/classeurs_xlsx.py` | Chemin xl/worksheets/sheet1.xml |
| `chemin_rapport` | `interface/serveur.py` | Chemin du rapport.json d'une tâche |
| `CHEMIN_SECRETS` | `core/connecteurs/secrets.py` | Fichier des secrets des connexions (CONCORDE_SECRETS) |
| `chemin_ss` | `securite/concorde_securite.py` | Chemin absolu de `ss` lancé via nsenter |
| `CHEMIN_TRANSFERTS` | `core/connecteurs/transfert.py` | Dossier des transferts (CONCORDE_TRANSFERTS) |
| `chemins_paquet` | `tests/test_assistant_import.py` | Paramètre : dossiers d'un paquet simulé |
| `chiffre` | `core/xlsx_ecrire.py` | Rang d'une lettre de colonne (0 = A) |
| `choix` | `interface/serveur.py` | Format ou objet demandé |
| `cible` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py`, `core/connecteurs/transfert.py`, `core/connecteurs/odoo.py`, `tests/test_connecteurs.py` | Cible d'une relation de classeur ; aussi : connecteur de l'environnement de test (connecteurs/transfert) |
| `cible_reelle` | `tests/test_connecteurs.py` | Classe CibleOdoo d'origine, dans un test |
| `CibleOdoo` | `core/migration/injection.py` | Classe : client XML-RPC vers une base Odoo 17 quelconque (https exigé hors serveur) |
| `cibles_feuilles` | `tests/test_mapping.py` | Paramètre : cibles des feuilles déclarées |
| `cibles_par_identifiant` | `tests/classeurs_xlsx.py` | Paramètre : {identifiant de relation: cible} |
| `classe` | `core/connecteurs/connexions.py` | Classe du connecteur d'un logiciel |
| `classe_connecteur` | `core/connecteurs/registre.py` | Routine : classe du connecteur d'un logiciel branché |
| `classe_erreur` | `core/mapping.py`, `injectors/socle_odoo.py` | Paramètre : classe d'exception levée par `_erreur_fichier` |
| `classer_connexion` | `securite/concorde_securite.py` | « attaquant », « minage » ou "" pour une adresse distante |
| `classeur` | `tests/test_xlsx_vers_fec.py` | Octets d'un classeur de test |
| `classeur_feuilles` | `tests/test_mapping.py` | Routine : classeur à plusieurs feuilles |
| `classeur_feuilles_xml` | `tests/classeurs_xlsx.py` | Routine : xl/workbook.xml avec feuilles rIdn |
| `classeur_lignes` | `tests/test_mapping.py` | Routine : classeur d'une feuille (+ sharedStrings) |
| `classeur_plan` | `tests/test_plan_comptable.py` | Routine : plan comptable .xlsx d'une feuille, en octets |
| `CLASSEUR_SANS_FEUILLE` | `tests/test_xlsx_vers_fec.py` | workbook.xml sans feuille déclarée |
| `classeur_tableau` | `tests/test_mapping.py` | Routine : classeur d'une feuille de tuples texte |
| `CLASSEUR_UNE_FEUILLE` | `tests/test_xlsx_vers_fec.py` | workbook.xml à une feuille |
| `classeur_xlsx` | `tests/test_xlsx_vers_fec.py` | Routine : construit un .xlsx minimal avec les styles donnés |
| `classeur_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de xl/workbook.xml |
| `cle` | `tests/test_yaml_min.py`, `core/connecteurs/transfert.py`, `core/connecteurs/odoo.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py` | Paramètre : clé de la section à extraire ; aussi : clé des totaux comparés (connecteurs/transfert) |
| `cle_et_reste` | `core/yaml_min.py` | Résultat de _separer_cle (clé, valeur brute) |
| `cle_texte` | `core/migration/lot.py` | Routine partagée : clé d'écriture -> « journal/numéro » |
| `CleApi` | `core/bases_locales.py` | TypedDict d'une clé API listée (jamais sa valeur) |
| `CleEcriture` | `core/migration/lot.py` | Type de la clé d'écriture (journal_code, ecriture) |
| `cles` | `tests/test_bases_locales.py`, `core/connecteurs/odoo.py` | Clés API de la base simulée (`FausseBaseCles.cles`) |
| `CLES_TOTAUX` | `core/connecteurs/transfert.py` | Clés des totaux comparées entre la source et le lot |
| `cles_trouvees` | `core/plan_comptable.py` | Clés de correspondance contenues dans le texte du type |
| `CleSolde` | `core/comparaison.py` | Clé d'agrégation des soldes : compte, journal ou (compte, tiers) |
| `CleTotaux` | `core/migration/lot.py` | Clés littérales de `TotauxLot` |
| `client` | `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Ligne client lue, dans un test |
| `ClientJson` | `core/connecteurs/http_json.py` | Classe : client REST JSON commun aux connecteurs par API |
| `close` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Méthode : fermeture de la connexion (DB-API) |
| `code` | `tests/test_plan_comptable.py`, `tests/test_connecteurs.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Code de compte lu ; aussi : code de sortie de la commande (test_connecteurs) |
| `code_journal` | `core/connecteurs/azalplus.py` | Code du journal d'une ligne AzalPlus |
| `code_sans_zeros` | `core/plan_comptable.py` | Code de compte sans zéros de tête (remplace `c`) |
| `code_tiers` | `core/connecteurs/azalplus.py` | Code du tiers trouvé par son nom |
| `code_trace` | `injectors/socle_odoo.py` | Étape inscrite dans le journal Guardian (ex. « odoo17 ») |
| `codes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py` | Paramètre de _codes_html : codes de comptes à citer ; aussi : codes TRF_ du paquet connecteurs (test_connecteurs) |
| `codes_affiches` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Texte HTML des codes cités par _codes_html |
| `codes_journaux` | `core/connecteurs/pennylane.py` | {code de journal: id Pennylane} |
| `colonne` | `core/yaml_min.py` | Colonne du contenu après le tiret |
| `colonnes` | `tests/test_xlsx_vers_fec.py` | Colonnes reconnues d'un en-tête |
| `cols_numero` | `core/mapping.py` | Colonnes « Numéro » trouvées sur la ligne d'en-tête |
| `cols_odoo` | `core/mapping.py` | Colonnes « Odoo Acct » trouvées sur la ligne d'en-tête |
| `compte` | `core/migration/lot.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Compte (source ou cible) dans `balance_par_compte` |
| `compte_a_arbitrer` | `core/migration/correspondance.py` | Cumul d'un compte à arbitrer (remplace `a`) |
| `compte_api` | `tests/test_connecteurs.py` | Compte Pennylane simulé parcouru |
| `compte_attendu` | `tests/test_plan_comptable.py` | Routine : compte attendu {code, nom, type} |
| `compte_lib` | `tests/test_xlsx_vers_fec.py` | Paramètre : intitulé de compte d'une ligne FEC attendue |
| `compte_libelle` | `core/connecteurs/azalplus.py` | Libellé du compte d'une ligne AzalPlus |
| `compte_odoo` | `tests/test_mapping.py` | Compte Odoo cible d'une correspondance |
| `compte_par_tiers` | `core/migration/lot.py` | Dictionnaire résultat de `lignes_par_tiers` |
| `compte_quadra` | `tests/test_mapping.py` | Compte Quadra source d'une correspondance |
| `CompteAArbitrer` | `core/migration/correspondance.py` | Type d'un compte absent de la table (libellé, lignes, montants) |
| `CompteLu` | `core/plan_comptable.py` | TypedDict d'un compte lu dans le plan comptable (code, nom, type) |
| `comptes` | `core/migration/filtres.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Critères du filtre en cours de normalisation |
| `comptes_attendus` | `tests/test_moteur.py` | Comptes Odoo attendus après mapping |
| `comptes_choisis` | `core/comparaison.py` | Ensemble des comptes du filtre (ex-réaffectation de `comptes`) |
| `comptes_crees` | `core/migration/injection.py` | Comptes créés par la préparation |
| `comptes_lot` | `core/migration/injection.py` | Comptes demandés par le lot, avec leur libellé |
| `concordance` | `tests/test_connecteurs.py` | État de l'étape 2, dans un test |
| `condition` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `ConditionDomaine` | `tests/test_demat.py` | Alias : condition de domaine Odoo (champ, opérateur, valeur) |
| `ConditionFiltre` | `core/migration/filtres.py` | Type d'une condition libre normalisée |
| `ConditionOdoo` | `core/demat.py` | Type : condition de domaine Odoo (champ, opérateur, valeur) |
| `conditions` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `config_guardian` | `core/moteur.py` | Section noyau.guardian de la configuration du moteur |
| `ConfigMapping` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type (TypedDict) de la configuration du mapping passée au moteur |
| `configuration` | `tests/test_yaml_min.py` | concorde.yaml chargé |
| `confirmation` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Libellé de la destination retapé pour le feu vert |
| `connecter` | `tests/test_connecteurs.py` | Doublure de psycopg2.connect, dans un test |
| `connecter_odoo` | `injectors/socle_odoo.py` | Ouvre une session XML-RPC v2 et trace un écart de version |
| `Connecteur` | `core/connecteurs/base.py`, `tests/test_connecteurs.py` | Classe de base : prise vers un logiciel (tester, lire, écrire, relire) |
| `ConnecteurAzalPlus` | `core/connecteurs/azalplus.py` | Connecteur AzalPlus : lecture seule de la base PostgreSQL (ADR-0009) |
| `ConnecteurFaux` | `tests/test_connecteurs.py` | Doublure de test : logiciel à API simulé, écriture en mémoire |
| `ConnecteurFec` | `core/connecteurs/fec.py` | Connecteur FEC : fichier déposé (lecture) ou FEC produit (écriture) |
| `ConnecteurOdoo` | `core/connecteurs/odoo.py` | Connecteur Odoo 17 : lecture et écriture par l'API XML-RPC |
| `ConnecteurPennylane` | `core/connecteurs/pennylane.py` | Connecteur Pennylane par l'API v2 |
| `ConnecteurRefusFinal` | `tests/test_connecteurs.py` | Doublure de test : refuse seulement l'écriture réelle finale |
| `connexion` | `injectors/odoo_conversion.py`, `tests/test_bases_locales.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Connexion Odoo utilisée par `extraire` |
| `connexion_a` | `tests/test_connecteurs.py` | Première connexion d'un test |
| `connexion_b` | `tests/test_connecteurs.py` | Seconde connexion d'un test |
| `connexion_base` | `core/migration/injection.py` | Connexion PostgreSQL ouverte par `relire` |
| `connexion_brute` | `core/bases_locales.py` | Connexion psycopg2 avant typage par Protocol |
| `connexion_espion` | `tests/test_bases_locales.py` | Fausse connexion qui enregistre le SQL exécuté |
| `connexion_https` | `core/connecteurs/http_json.py` | Routine : connexion HTTPS avec certificat vérifié |
| `connexion_test` | `core/connecteurs/connexions.py` | Connexion qui sert d'environnement de test à une autre |
| `ConnexionAzalPlus` | `core/connecteurs/azalplus.py` | Protocole : connexion PostgreSQL utilisée par le connecteur AzalPlus |
| `ConnexionHttp` | `core/connecteurs/http_json.py` | Protocole : connexion HTTP (http.client ou doublure) |
| `ConnexionLecture` | `core/migration/injection.py` | Protocoles du curseur et de la connexion SQL de relecture |
| `ConnexionOdoo` | `injectors/socle_odoo.py` | Session XML-RPC authentifiée (db, uid, mot_de_passe, modeles) |
| `ConnexionPg` | `core/bases_locales.py` | Protocol d'une connexion PostgreSQL fournie par l'appelant |
| `ConnexionPgFermable` | `core/bases_locales.py` | Protocol d'une connexion ouverte (et fermée) par le module |
| `connexions` | `securite/concorde_securite.py`, `tests/test_connecteurs.py`, `interface/transferts.py` | Liste des connexions lues dans les conteneurs ; aussi : méthode de test : source et destination FEC (test_connecteurs) ; aussi : méthode de l'écran Transferts : connexions décrites, sans secret |
| `connexions_conteneurs` | `securite/concorde_securite.py` | (pid, adresse distante) des connexions des espaces réseau des conteneurs |
| `ConnexionSql` | `core/odoo_source.py` | Protocol : connexion PostgreSQL (psycopg2) de la source SQL |
| `Constat` | `core/analyser.py`, `core/migration/lot.py`, `interface/serveur.py` | Alias `dict[str, Any]` : constat d'un Rapport (JSON) |
| `constat_lu` | `tests/test_connecteurs.py` | Constat parcouru dans un test |
| `ConstatLu` | `core/surveillance.py` | Type : constat produit par Rapport ou relu d'un JSON de sécurité |
| `constats` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Constats d'une étape |
| `constats_expliques` | `core/migration/circuit.py` | Routine partagée : constats d'un rapport expliqués par Marceau |
| `contenu` | `core/marceau.py`, `core/xml_sur.py` | Texte de la réponse Mistral, vérifié avant retour |
| `contenu_element` | `core/yaml_min.py` | Texte d'un élément de liste après le tiret |
| `contenu_feuille` | `tests/test_xlsx_vers_fec.py` | Paramètre : XML de la feuille du classeur de test |
| `contenu_journal` | `securite/concorde_securite.py` | Texte du journal clamscan.log |
| `contenu_json` | `core/migration/correspondance.py` | Contenu JSON décodé de la table (remplace `d`) |
| `contenu_lignes` | `tests/test_xlsx_vers_fec.py` | XML des lignes d'une feuille |
| `contenu_lu` | `tests/test_assistant_import.py` | Octets rendus par `_lire_binaire` |
| `contenu_xls` | `tests/test_mapping.py` | Octets d'un vieux .xls (OLE2) |
| `contenu_zip` | `tests/test_assistant_import.py` | Octets du zip exporté |
| `contenus_illisibles` | `tests/test_mapping.py` | Contenus de cellule illisibles testés |
| `contexte` | `tests/test_plan_comptable.py`, `tests/test_connecteurs.py` | Contexte assertRaises ; aussi : exception attendue par assertRaises (test_connecteurs) |
| `contexte_erreur` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Contexte assertRaises |
| `contexte_rapport` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Données du rapport HTML de l'import (ContexteRapport) |
| `contexte_simule` | `tests/test_assistant_import.py` | Bilan de moteur simulé (étape 2 = canon) |
| `ContexteExecution` | `core/moteur.py` | TypedDict du bilan de `MoteurConcorde.executer` |
| `ContexteRapport` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type (TypedDict) des données du rapport HTML de l'assistant |
| `conversion` | `core/fichier_json.py` | Paramètre de ecrire_json_atomique (default) |
| `convertir_lignes` | `tests/test_xlsx_vers_fec.py` | Routine : lignes -> classeur -> xlsx_vers_fec |
| `cookies` | `interface/serveur.py` | Cookies de la requête |
| `copie` | `tests/test_connecteurs.py` | Copie modifiable d'une ligne simulée |
| `copie_texte` | `core/comparaison.py` | `date_copie` normalisée « AAAA-MM-JJ HH:MM:SS » (ex-réaffectation) |
| `corps` | `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Corps JSON d'une requête ou d'une réponse |
| `correctif` | `tests/test_connecteurs.py` | Remplacement mock posé pour un test |
| `CORRESP_TYPE_NORMALISE` | `core/plan_comptable.py` | Texte normalisé -> account_type : types Odoo tels quels puis libellés |
| `correspondance` | `interface/serveur.py` | Résultat d'une expression régulière sur le chemin |
| `correspondance_version` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Résultat de la recherche du numéro majeur dans le texte de version |
| `correspondances` | `tests/test_moteur.py` | Lignes {quadra, odoo} du mapping synthétique écrit en JSON |
| `cote` | `core/comparaison.py` | Paramètre de `_lignes_seulement` : « A » ou « B » |
| `coupe_au_transfert` | `tests/test_connecteurs.py` | Doublure : relecture coupée au vrai transfert seulement |
| `credit` | `core/migration/connecteur_fec.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Montants de la ligne en centimes |
| `cree` | `core/connecteurs/pennylane.py` | Écriture créée par Pennylane |
| `cree_le` | `core/connecteurs/connexions.py`, `core/connecteurs/transfert.py` | Date de création d'une connexion ou d'un transfert |
| `creer` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Routine : crée un transfert et joue les étapes 1 à 4 |
| `creer_manquants` | `core/migration/injection.py` | Créer comptes, journaux et tiers absents (base de test) ou refuser |
| `creer_module_bouchon` | `tests/test_assistant_import.py` | Crée et enregistre un module odoo simulé |
| `CritereDomaine` | `core/odoo_source.py` | Critère d'un domaine Odoo : « \ | » ou (champ, opérateur, valeur) |
| `criteres_retenus` | `core/migration/filtres.py` | Critères qui retiennent des lignes (tous sauf `sauf_comptes`) |
| `csv_comptes` | `tests/test_assistant_import.py`, `deploy/addons/concorde/wizard/concorde_import_wizard.py` | CSV des comptes du zip d'export |
| `curseur` | `core/migration/injection.py`, `interface/serveur.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/http_json.py` | Curseur SQL de relecture |
| `CurseurAvecContexte` | `tests/outils.py` | Type du faux curseur rendu par `with` |
| `CurseurAzalPlus` | `core/connecteurs/azalplus.py` | Protocole : curseur PostgreSQL utilisé par le connecteur AzalPlus |
| `CurseurCles` | `tests/test_bases_locales.py` | Curseur simulé de `FausseBaseCles` (SELECT puis DELETE d'une clé API) |
| `CurseurEnregistreur` | `tests/test_bases_locales.py` | Curseur simulé de `FausseConnexion` : consigne les ordres SQL |
| `CurseurLecture` | `core/migration/injection.py` | Protocoles du curseur et de la connexion SQL de relecture |
| `CurseurPg` | `core/bases_locales.py` | Protocol du curseur PostgreSQL utilisé par le module |
| `CurseurPgSimule` | `tests/test_bases_locales.py` | Faux curseur conforme à `bases_locales.CurseurPg` |
| `CurseurRelecture` | `tests/test_injection.py` | Faux curseur (hérite `CurseurSimule`) rendant des rangs fixés |
| `curseurs` | `tests/test_connecteurs.py` | Requêtes avec curseur, dans un test |
| `CurseurSimule` | `tests/outils.py` | Base des faux curseurs PostgreSQL (protocole `with`) |
| `cursor` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : ouverture d'un curseur (DB-API) |
| `date_copie` | `interface/serveur.py` | Date de copie saisie (comparaison) |
| `date_ecriture` | `core/migration/connecteur_fec.py` | EcritureDate convertie |
| `date_facture` | `core/demat.py` | Date de facture lue une fois par facture en émission |
| `date_lettrage` | `core/migration/connecteur_fec.py` | DateLet convertie |
| `date_lue` | `core/xlsx_vers_fec.py` | Date validée par _date_fec |
| `date_piece` | `core/migration/connecteur_fec.py` | PieceDate convertie |
| `date_validation` | `core/migration/connecteur_fec.py` | ValidDate convertie |
| `dates` | `core/connecteurs/pennylane.py` | Dates des lignes du lot |
| `de_la_societe` | `core/connecteurs/azalplus.py` | Lignes de la société lue |
| `debit` | `core/migration/connecteur_fec.py`, `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Montants de la ligne en centimes |
| `debut` | `core/migration/injection.py`, `core/migration/circuit.py`, `core/odoo_source.py`, `tests/test_connecteurs.py` | Résultat et bornes d'un paquet dans `decouper` ; aussi : Début de la référence d'une écriture |
| `debut_donnees` | `core/fec_parser.py`, `core/mapping.py`, `core/migration/connecteur_fec.py`, `core/plan_comptable.py`, `core/xlsx_vers_fec.py` | Index de la première ligne de données (après l'en-tête) |
| `debut_element` | `core/yaml_min.py` | Position de début d'un élément de liste en ligne |
| `debut_lot` | `core/demat.py`, `core/odoo_source.py` | Indice de début d'une tranche dans `_lots` (ex-`i`) |
| `debut_periode` | `core/migration/filtres.py` | Bornes `du` / `au` converties |
| `debut_ref` | `core/migration/injection.py` | Début des références des écritures envoyées |
| `debut_valeur` | `core/yaml_min.py` | Position du début de la valeur après la clé |
| `decalage` | `interface/serveur.py` | Décalage de page du grand livre |
| `declarations` | `tests/test_xlsx_vers_fec.py` | Déclarations de types de contenu |
| `declarations_feuilles` | `tests/classeurs_xlsx.py` | Éléments <sheet> du classeur |
| `decouper` | `core/migration/injection.py` | Routine partagée : découpe une liste en paquets |
| `deja` | `core/connecteurs/odoo.py` | Références déjà présentes dans Odoo |
| `deja_retirees` | `core/connecteurs/transfert.py` | Lignes déjà retirées par le connecteur source (hors période) |
| `delai` | `core/odoo_source.py`, `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Délai d'attente (secondes) d'un transport XML-RPC |
| `demande` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Demande de transfert |
| `DemandeTransfert` | `core/connecteurs/transfert.py` | TypedDict : source, destinations, période, filtres, correspondances |
| `depart` | `interface/serveur.py` | Instant de départ d'une mesure de durée |
| `deposer` | `tests/test_connecteurs.py`, `interface/transferts.py`, `tests/test_ecran_transferts.py` | Méthode de test : dépose un FEC ; aussi : méthode de l'écran Transferts : reçoit et relit un FEC déposé |
| `dernier_test` | `core/connecteurs/connexions.py` | Date du dernier test d'une connexion |
| `derniere` | `core/guardian.py` | Dernière empreinte recalculée (`verifier_chaine`) |
| `derniere_info` | `core/connecteurs/connexions.py` | Ce que le dernier test de connexion a lu |
| `derniere_piece` | `tests/test_assistant_import.py` | Dernière pièce jointe simulée créée |
| `desequilibre` | `tests/test_connecteurs.py` | Lot déséquilibré, dans un test |
| `desequilibree` | `interface/serveur.py` | Vrai si la balance est déséquilibrée |
| `dest` | `tests/test_connecteurs.py` | État d'une destination, dans un test |
| `destination` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Connecteur ou identifiant de la destination |
| `destination_bloquee` | `tests/test_connecteurs.py` | État d'une destination bloquée, dans un test |
| `destinations` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Connexions destination d'un transfert |
| `detail` | `core/connecteurs/transfert.py` | Détail d'une étape (statut, erreur, infos) |
| `details` | `tests/test_connecteurs.py` | Paramètres ignorés de __exit__ (doublure) |
| `DetailsComparaison` | `core/comparaison.py` | Détails de comparaison par catégorie (classeur xlsx) |
| `devise` | `core/connecteurs/base.py`, `tests/test_connecteurs.py`, `core/connecteurs/azalplus.py` | Devise de la société lue |
| `dimensions` | `core/comparaison.py` | (code, nom, clé) des agrégations de soldes comparées |
| `distant` | `interface/serveur.py` | Fiche d'un Odoo distant |
| `Domaine` | `core/odoo_source.py` | Liste de critères d'un domaine Odoo (XML-RPC) |
| `DomaineOdoo` | `core/demat.py`, `tests/test_demat.py` | Type : domaine Odoo (même sens que dans `tests/test_demat.py`) |
| `donnees` | `tests/test_mapping.py`, `core/fichier_json.py`, `core/connecteurs/http_json.py` | Données JSON du mapping de test ; aussi : valeur écrite en JSON (fichier_json) |
| `DonneesJson` | `core/rapport_jour.py` | Type : données JSON (alertes, tâches, sécurité, rapports, saisie) |
| `donner_feu_vert` | `core/connecteurs/transfert.py` | Routine : feu vert, nouveau test, puis transfert (étapes 5 à 7) |
| `dossier` | `securite/concorde_securite.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/secrets.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Dossier temporaire courant (construction de PREFIXES_TEMP) ; aussi : dossier d'une connexion, d'un transfert ou d'un test (connecteurs) |
| `dossier_dest` | `core/connecteurs/transfert.py` | Dossier des fichiers d'une destination |
| `DOSSIER_ESSAIS` | `core/connecteurs/fec.py` | Sous-dossier d'essais d'une destination FEC (environnement de test) |
| `dossier_journal` | `tests/test_moteur.py` | Dossier temporaire du journal Guardian |
| `DOSSIER_MODULE` | `tests/test_assistant_import.py` | Dossier du module Odoo `deploy/addons/concorde` |
| `dossier_reference` | `core/connecteurs/fec.py` | Routine : dossier sûr d'une référence de transfert |
| `dossier_secrets` | `tests/test_connecteurs.py` | Dossier du fichier de secrets dans un test |
| `dossier_temporaire` | `tests/test_moteur.py` | Dossier temporaire du mapping synthétique |
| `du` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Début de période (compris), None = sans borne |
| `ecart` | `core/connecteurs/transfert.py` | Rapport de comparaison lot / relecture |
| `EcartSolde` | `core/comparaison.py` | TypedDict : écart de solde A/B pour une clé |
| `echapper_xml` | `core/xlsx_ecrire.py` | Routine : échappe un texte pour l'écrire en XML |
| `echec_pipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | EchecPipeline intercepté par les actions de l'assistant |
| `EchecPipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Exception : échec du pipeline avec le libellé du mapping connu |
| `ecrire` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/pennylane.py` | Méthode d'un connecteur : écrit un lot (essai à blanc par défaut) |
| `ecrire_fec_lot` | `core/migration/export.py` | Routine partagée : écrit un lot en FEC DGFiP |
| `ecrire_json_atomique` | `core/fichier_json.py` | Routine partagée : écriture JSON via fichier .tmp puis renommage (ex-`_ecrire_json_atomique`) |
| `ecrire_rapport_json` | `scripts/outils_cli.py` | Écrit un rapport JSON lisible (option --json) |
| `ecrire_variable` | `core/connecteurs/secrets.py` | Routine partagée : ajoute ou remplace NOM=valeur dans un fichier env (600) |
| `ecrit` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Résultat d'une écriture réelle |
| `ecrits` | `tests/test_connecteurs.py` | Lots écrits en mémoire par la doublure, par référence |
| `ecriture` | `core/connecteurs/base.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Bilan d'écriture rangé dans les infos d'une étape |
| `ecriture_odoo` | `tests/test_connecteurs.py` | Écriture Odoo simulée, dans un test |
| `EcritureDifferente` | `core/comparaison.py` | TypedDict : couple d'écritures rapprochées qui diffèrent |
| `EcritureGroupee` | `core/comparaison.py` | TypedDict : écriture reconstituée avec ses lignes |
| `EcritureRegroupee` | `injectors/socle_odoo.py` | Type d'une écriture regroupée : ref_ext, journal, numero, date, libelle, lignes, total (centimes) |
| `ecritures` | `core/connecteurs/fec.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Nombre d'écritures du lot |
| `ecritures_a_creer` | `core/connecteurs/base.py` | Écritures qui seraient (ou ont été) créées |
| `ecritures_deja_presentes` | `core/connecteurs/base.py` | Écritures déjà présentes sous la référence |
| `ecrivain` | `interface/serveur.py` | Écrivain CSV |
| `effacer_secrets_connexion` | `core/connecteurs/secrets.py` | Routine : efface les secrets d'une connexion retirée |
| `egal` | `core/connecteurs/secrets.py`, `scripts/concorde_connexion.py` | Signe « = » trouvé dans une ligne NOM=valeur |
| `element` | `core/migration/circuit.py`, `interface/serveur.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Explication Marceau d'un constat / élément du constat |
| `element_api` | `tests/test_connecteurs.py` | Élément de l'API simulée parcouru |
| `element_brut` | `core/yaml_min.py` | Élément brut d'une liste en ligne |
| `elements` | `core/migration/filtres.py`, `injection.py`, `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Valeur du critère liste / éléments à traiter |
| `elements_bruts` | `core/yaml_min.py` | Éléments bruts d'une liste en ligne |
| `elements_liste` | `core/yaml_min.py` | Éléments d'une liste YAML en cours de lecture dans `_lire_liste` |
| `ElementTraite` | `core/migration/injection.py` | Variables de type de `en_parallele` / `decouper` |
| `ElementXml` | `core/xml_sur.py` | Élément XML lu (protocole : find, iter, get, text) |
| `empreinte_brute` | `interface/auth.py` | Empreinte scrypt (octets) |
| `empreinte_lot` | `core/connecteurs/transfert.py` | Routine / champ : empreinte SHA-256 des lignes du lot |
| `en_devise` | `core/connecteurs/azalplus.py` | Montant en devise (centimes), ou None |
| `en_dollars` | `tests/test_connecteurs.py` | Ligne simulée en dollars, dans un test |
| `EN_TETE_FEC_TEXTE` | `tests/test_assistant_import.py` | En-tête de FEC texte (octets) pour les tests de `_lire_binaire` |
| `encore` | `tests/test_connecteurs.py` | Seconde écriture de la même référence, dans un test |
| `enfant` | `core/yaml_min.py` | Bloc enfant lu, ou None |
| `enregistre` | `core/connecteurs/transfert.py` | État de la destination relu après écriture |
| `Enregistrement` | `core/comptes.py`, `core/odoo_source.py`, `injectors/socle_odoo.py`, `tests/outils.py`, `core/connecteurs/odoo.py` | Alias `dict[str, Any]` : enregistrement rendu par une source (ligne, compte, journal, tiers, facture) ; aussi : Ligne Odoo au format commun de odoo_source |
| `EnregistrementLu` | `core/telecharger.py` | Alias `Mapping[str, Any]` : enregistrement reçu d'une source |
| `EnregistrementOdoo` | `core/demat.py` | Type : enregistrement Odoo lu (XML-RPC ou ORM) |
| `enregistrements` | `core/demat.py` | Résultat de search_read dans `SourceXmlRpc.lire` |
| `entete` | `core/xlsx_vers_fec.py` | En-tête FEC standard trouvé (index, colonnes) ou None |
| `entete_code` | `tests/test_plan_comptable.py` | Intitulé de la colonne code testé |
| `ENTETE_FEC_ATTENDUE` | `tests/test_xlsx_vers_fec.py` | En-tête FEC attendu (18 champs) |
| `entete_intitule` | `tests/test_plan_comptable.py` | Intitulé de la colonne intitulé testé |
| `ENTETE_MAPPING_CLIENT` | `tests/test_mapping.py` | En-tête (Numéro, Intitulé, Odoo Acct) du fichier client |
| `ENTETE_MINIMALE` | `tests/test_xlsx_vers_fec.py` | Les 5 colonnes obligatoires d'un FEC standard |
| `entete_obligatoire` | `tests/test_interface.py` | Valeur d'un en-tête HTTP qui doit être présent (échec sinon) |
| `entete_quadra` | `core/xlsx_vers_fec.py` | En-tête Cegid Quadra trouvé (index, colonnes) ou None |
| `ENTETE_STANDARD` | `tests/test_xlsx_vers_fec.py` | En-tête Excel standard avec synonymes |
| `entetes` | `tests/test_plan_comptable.py`, `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Paramètre : en-têtes du plan de test |
| `ENTETES_PLAN` | `tests/test_plan_comptable.py` | En-têtes usuels d'un plan de test |
| `entite` | `core/xlsx_ecrire.py` | Couple (caractère, entité) de `entites` |
| `entites` | `core/xlsx_ecrire.py` | Remplacements supplémentaires de `echapper_xml` |
| `entree` | `interface/serveur.py` | Entrée d'un compte ou d'un analytique (choix de comparaison) |
| `environnement_test` | `core/connecteurs/base.py`, `core/connecteurs/fec.py` | Méthode d'un connecteur : connecteur vers sa copie de test |
| `envoi` | `core/connecteurs/odoo.py` | Résultat de l'envoi vers Odoo |
| `erreur` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Motif d'arrêt d'une étape |
| `erreur_lancement` | `securite/concorde_securite.py` | Message si nice / ionice / clamscan est introuvable |
| `erreur_lecture` | `tests/test_xlsx_vers_fec.py` | Erreur simulée d'openpyxl |
| `erreur_levee` | `tests/test_assistant_import.py` | Erreur capturée par le test |
| `erreur_odoo` | `core/connecteurs/odoo.py` | Erreur d'Odoo gardée avec l'écriture en cause |
| `erreur_origine` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Exception d'origine portée par EchecPipeline |
| `ErreurAnnuaire` | `core/connecteurs/connexions.py` | Exception : connexion inconnue, paramètre refusé, retrait impossible |
| `ErreurConnexion` | `core/connecteurs/base.py` | Exception : le logiciel ne répond pas comme attendu (sans secret) |
| `ErreurConservation` | `core/migration/filtres.py` | Exception : totaux après filtres ≠ avant − retraits (remplace les `assert`) |
| `ErreurLectureXml` | `core/xml_sur.py` | XML mal formé |
| `ErreurOdoo` | `core/migration/injection.py` | Type d'une erreur Odoo gardée (écriture, étape, erreur) |
| `erreurs` | `core/connecteurs/base.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py` | Erreurs rendues par le logiciel |
| `ERREURS_CONNEXION` | `core/connecteurs/transfert.py` | Erreurs d'un logiciel ou de l'annuaire rapportées dans l'étape en cause |
| `ERREURS_MISTRAL` | `core/marceau.py` | Exceptions d'un appel Mistral qui déclenchent le repli à règles |
| `ERREURS_ODOO` | `core/connecteurs/odoo.py` | Erreurs d'Odoo ou du réseau rendues en ErreurConnexion |
| `ErreurSecrets` | `core/connecteurs/secrets.py` | Exception : fichier de secrets refusé (droits, ligne invalide) |
| `ErreurTransfert` | `core/connecteurs/transfert.py` | Exception : demande invalide ou feu vert refusé |
| `ErreurUtilisateurBouchon` | `tests/test_assistant_import.py` | Remplace `odoo.exceptions.UserError` |
| `ErreurXmlRpc` | `core/xml_sur.py` | Base des erreurs XML-RPC |
| `ErreurYaml` | `core/yaml_min.py` | Exception : construction YAML non gérée (ligne citée) |
| `ESPACE_PAQUET` | `tests/classeurs_xlsx.py` | Racine des espaces de noms du paquet OPC |
| `ESPACE_RELATIONS` | `tests/test_xlsx_vers_fec.py` | Espace de noms des relations Office |
| `ESPACE_RELATIONS_PAQUET` | `tests/classeurs_xlsx.py` | Espace de noms des fichiers .rels |
| `ESPACE_TABLEUR` | `tests/test_xlsx_vers_fec.py` | Espace de noms SpreadsheetML |
| `essai` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py` | Vrai : essai à blanc, rien n'est écrit |
| `essais` | `core/connecteurs/http_json.py` | Nombre d'essais sur une limite d'appels |
| `etape` | `tests/test_yaml_min.py`, `core/connecteurs/transfert.py` | Étape du pipeline lue dans concorde.yaml ; aussi : étape d'un transfert (connecteurs/transfert) |
| `EtapeConversion` | `injectors/odoo_conversion.py` | Type du compte rendu d'un saut de version |
| `etapes` | `injectors/odoo_conversion.py`, `core/connecteurs/transfert.py` | Comptes rendus des sauts de version ; aussi : états des étapes d'une destination (connecteurs/transfert) |
| `etat` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | État d'un transfert ou d'une destination |
| `etat_dest` | `core/connecteurs/transfert.py` | État d'une destination |
| `etat_secrets` | `core/connecteurs/secrets.py` | Routine : pour chaque secret attendu, renseigné ou non (jamais la valeur) |
| `EtatDestination` | `core/connecteurs/transfert.py` | TypedDict : statut, étapes, empreinte et feu vert d'une destination |
| `EtatEtape` | `core/connecteurs/transfert.py` | TypedDict : résultat d'une étape (statut, erreur, infos, constats) |
| `EtatPorte` | `core/migration/circuit.py` | Type de l'état d'une porte dans le rapport |
| `EtatTransfert` | `core/connecteurs/transfert.py` | TypedDict : état complet d'un transfert (transfert.json) |
| `Evenement` | `core/journal.py`, `tests/test_connecteurs.py` | TypedDict d'un événement du journal (t, niveau, message) ; aussi : Événement du journal parcouru |
| `evenements` | `interface/serveur.py` | Événements du journal |
| `exception` | `tests/outils.py`, `core/connecteurs/azalplus.py` | Paramètres de `CurseurSimule.__exit__` |
| `executable` | `deploy/webhook.py` | Chemin absolu de git / docker |
| `execute` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : exécution d'une requête (DB-API) |
| `executer` | `injectors/socle_odoo.py` | Appel `execute_kw` unique sur la base connectée |
| `Existants` | `core/migration/injection.py` | TypedDict : comptes, journaux, tiers demandés par le lot et trouvés dans Odoo |
| `explication` | `core/migration/circuit.py` | Explication Marceau d'un constat / élément du constat |
| `extraire_canon` | `core/canonical.py` | Routine partagée : Canonique porté par une donnée du pipeline (Canonique ou dict 'canon' / 'resultat'→'canon'), None sinon |
| `extrait_message` | `tests/test_plan_comptable.py` | Paramètre : extrait attendu du message d'erreur |
| `f_fec` | `core/migration/export.py` | Fichier FEC produit, ouvert en lecture binaire |
| `FausseReponse` | `tests/test_connecteurs.py` | Doublure de test : réponse HTTP simulée |
| `FauteXmlRpc` | `core/migration/injection.py`, `core/xml_sur.py` | Nom public de `xmlrpc.client.Fault` (erreur renvoyée par Odoo), utilisable par les tests |
| `faux` | `tests/test_connecteurs.py` | Connexion simulée, dans un test |
| `FauxCommun` | `tests/outils.py` | Point d'entrée XML-RPC « common » Odoo 17 simulé (déplacé, partagé) |
| `FauxCurseurPg` | `tests/test_connecteurs.py` | Doublure de test : curseur PostgreSQL d'AzalPlus simulé |
| `FauxPennylane` | `tests/test_connecteurs.py` | Doublure de test : API v2 de Pennylane simulée |
| `FauxPg` | `tests/test_connecteurs.py` | Doublure de test : base AzalPlus simulée |
| `fec_attendu` | `tests/test_xlsx_vers_fec.py` | Routine : FEC complet attendu en octets |
| `fec_interne` | `tests/test_xlsx_vers_fec.py` | FEC produit par le lecteur interne |
| `FEC_MINIMAL` | `tests/test_moteur.py` | FEC minimal équilibré (sorti de `TestParseurFEC`, partagé par le fichier) |
| `fec_openpyxl` | `tests/test_xlsx_vers_fec.py` | FEC produit via openpyxl |
| `fec_produit` | `tests/test_xlsx_vers_fec.py` | FEC produit par xlsx_vers_fec |
| `FEC_SIMPLE` | `tests/test_connecteurs.py` | FEC de test sans tiers ni lettrage |
| `fermee` | `tests/test_connecteurs.py` | Nombre de fermetures de la base simulée |
| `fetchall` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : toutes les lignes lues (DB-API) |
| `feu_vert` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `interface/transferts.py` | Étape 5 : qui, quand, date de sauvegarde ; aussi : méthode de l'écran Transferts : contrôle puis lance les étapes 6 et 7 |
| `Feuille` | `core/xlsx_ecrire.py` | Type : (nom, entêtes, lignes) d'une feuille à écrire |
| `FEUILLE_DATE_ET_NOMBRE` | `tests/test_xlsx_vers_fec.py` | Feuille : une date (série 45296) et un nombre |
| `feuille_depuis_lignes` | `tests/classeurs_xlsx.py` | Routine : feuille à partir de lignes de valeurs |
| `feuille_tableau` | `tests/test_mapping.py` | Routine : feuille à partir de tuples de textes |
| `FEUILLE_TROIS_STYLES` | `tests/test_xlsx_vers_fec.py` | Feuille : date personnalisée, format littéral, sans style |
| `FEUILLE_UN_TEXTE` | `tests/test_xlsx_vers_fec.py` | Feuille d'une seule cellule texte |
| `feuille_xml` | `tests/classeurs_xlsx.py` | Routine : enveloppe <worksheet> autour de lignes <row> |
| `fiche` | `interface/serveur.py`, `core/connecteurs/connexions.py`, `core/connecteurs/transfert.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py` | Fiche d'une base de l'annuaire ; aussi : fiche d'une connexion (connecteurs) |
| `fiche_lue` | `core/connecteurs/connexions.py` | Fiche de connexion parcourue |
| `FicheConnexion` | `core/connecteurs/connexions.py` | TypedDict : une connexion de l'annuaire |
| `fichier` | `tests/test_moteur.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/secrets.py`, `core/connecteurs/transfert.py`, `core/fichier_json.py`, `tests/test_connecteurs.py` | Fichier JSON ouvert en écriture ; aussi : fichier ouvert (fichier_json, connecteurs) |
| `fichier_journal` | `securite/concorde_securite.py` | Fichier clamscan.log ouvert en lecture |
| `fichier_mapping` | `scripts/export_odoo_online.py` | Fichier de mapping xlsx ouvert en lecture |
| `fichier_secrets` | `core/connecteurs/connexions.py` | Fichier des secrets lu par l'annuaire |
| `fichier_source` | `scripts/export_odoo_online.py` | Fichier FEC / xlsx ouvert en lecture |
| `fichiers` | `core/connecteurs/base.py`, `core/connecteurs/transfert.py` | Fichiers produits par une étape |
| `fil` | `tests/test_connecteurs.py` | Fil d'exécution concurrent, dans un test |
| `filtre` | `core/migration/filtres.py`, `tests/test_connecteurs.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni |
| `filtre_api` | `tests/test_connecteurs.py` | Filtre Pennylane parcouru |
| `filtre_brut` | `core/migration/filtres.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni |
| `FiltreNormalise` | `core/migration/filtres.py` | Type d'un filtre validé |
| `filtres` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Règles de filtres d'une demande |
| `fin` | `core/migration/injection.py`, `interface/serveur.py`, `tests/test_demat.py`, `tests/test_connecteurs.py` | Résultat et bornes d'un paquet dans `decouper` ; aussi : état final d'une destination (test_connecteurs) |
| `fin_attendue` | `tests/test_xlsx_vers_fec.py` | Fin de message d'erreur attendue |
| `fin_lot` | `core/demat.py`, `core/odoo_source.py` | Indice de fin d'une tranche dans `_lots` |
| `fin_page` | `core/comptes.py` | Rang de fin (exclu) de la page du grand livre |
| `fin_periode` | `core/migration/filtres.py` | Bornes `du` / `au` converties |
| `final` | `tests/test_connecteurs.py` | Vrai pour l'écriture réelle finale (hors test) |
| `finir` | `core/connecteurs/transfert.py` | Routine locale : termine une destination après le feu vert |
| `fonction_interne` | `core/moteur.py` | Fonction d'étape interne au moteur (`_<fonction>`) |
| `fonction_module` | `core/moteur.py` | Fonction d'étape résolue dans un module |
| `FonctionSauvegarde` | `core/bases_locales.py` | Protocol de la fonction de sauvegarde injectable |
| `forcee` | `tests/test_connecteurs.py` | Réponse imposée à l'API simulée |
| `forcees` | `tests/test_connecteurs.py` | Réponses imposées à l'API simulée |
| `format_inconnu` | `tests/test_xlsx_vers_fec.py` | Fin du message pour un format de date inconnu |
| `gardees` | `core/connecteurs/fec.py` | Lignes dans la période |
| `gestionnaire` | `core/marceau.py` | Gestionnaire urllib ajouté à l'ouvreur https |
| `GestionnaireConcorde` | `interface/serveur.py` | Sous-classe de Gestionnaire liée à une application (creer_serveur) |
| `getheader` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Méthode : valeur d'un en-tête HTTP |
| `getresponse` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Méthode : lecture de la réponse HTTP |
| `groupe` | `core/xlsx_vers_fec.py` | Lignes Quadra d'un même groupe / d'une même écriture |
| `groupes` | `core/xlsx_vers_fec.py` | Groupes de lignes Quadra par clé de cascade |
| `guardian` | `tests/test_yaml_min.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Section noyau.guardian de concorde.yaml ; aussi : audit passé au transfert (connecteurs/transfert) |
| `guillemet_fermant` | `core/yaml_min.py` | Position du guillemet fermant d'une clé |
| `guillemet_ouvert` | `core/yaml_min.py` | Guillemet actuellement ouvert |
| `GUILLEMETS_YAML` | `core/yaml_min.py` | Guillemets reconnus par le lecteur YAML |
| `headers` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Paramètre : en-têtes de la requête (http.client) |
| `hote` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Nom d'hôte de l'API |
| `HoteXmlRpc` | `core/odoo_source.py` | Type de l'hôte reçu par `Transport.make_connection` |
| `id` | `core/connecteurs/connexions.py`, `core/connecteurs/transfert.py` | Identifiant d'une connexion ou d'un transfert |
| `ident` | `core/demat.py`, `core/connecteurs/connexions.py`, `core/connecteurs/secrets.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Id de partenaire dans la compréhension de `_lire_partenaires` ; aussi : identifiant d'une connexion ou d'un transfert (connecteurs) |
| `ident_cible` | `core/connecteurs/transfert.py` | Connexion écrite pendant le test (verrou) |
| `ident_dest` | `core/connecteurs/transfert.py` | Identifiant de la connexion destination |
| `ident_destination` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Identifiant d'une destination parcourue |
| `ident_partenaire` | `core/demat.py` | Id du partenaire commercial d'une facture |
| `identifiant` | `tests/classeurs_xlsx.py` | Identifiant d'une relation (rIdn) |
| `identifiant_cle` | `core/bases_locales.py`, `tests/test_bases_locales.py` | Identifiant entier de la clé API à révoquer |
| `identifiant_modele` | `core/bases_locales.py` | Nom du modèle vierge vérifié, calculé avant toute suppression dans `reinitialiser` |
| `identique` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Comptes repris à l'identique, par destination |
| `ids` | `core/connecteurs/pennylane.py` | Identifiants d'écritures |
| `ids_odoo` | `core/migration/injection.py` | Identifiants Odoo d'une lettre (avec None) / retrouvés |
| `ids_trouves` | `core/migration/injection.py` | Identifiants Odoo d'une lettre (avec None) / retrouvés |
| `ignorees` | `interface/serveur.py` | Bases écartées pendant Bases._lister_sql |
| `illisibles` | `core/connecteurs/azalplus.py` | Lignes bloquées à la lecture (numéro, texte, motif) |
| `index` | `tests/classeurs_xlsx.py` | Rang d'une feuille ou d'une colonne |
| `index_attendu` | `tests/test_mapping.py` | Index de colonne attendu |
| `index_champs` | `core/migration/connecteur_fec.py` | {nom de colonne FEC: position} (remplace `idx`) |
| `index_colonne` | `core/xlsx_ecrire.py`, `core/mapping.py` | Paramètre : index de colonne à partir de 0 |
| `info` | `core/connecteurs/connexions.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py` | Société lue au test de connexion |
| `InfoConnexion` | `core/connecteurs/base.py` | TypedDict : société lue au test de connexion |
| `infos` | `interface/serveur.py`, `core/connecteurs/transfert.py` | Informations d'un contrôle de sécurité ; aussi : infos d'une étape (connecteurs/transfert) |
| `infos_securite` | `interface/serveur.py` | Derniers contrôles de sécurité par nature |
| `infos_version` | `core/demat.py`, `injectors/socle_odoo.py` | Réponse de version() du serveur (même sens que dans `injectors/socle_odoo.py`) |
| `InfosConteneur` | `securite/concorde_securite.py` | Type (image, ports publiés, environnement) d'un conteneur |
| `InfosProcessus` | `securite/concorde_securite.py` | Type (pid, utilisateur, % CPU, durée, nom, arguments, exécutable) |
| `InjecteurOdoo` | `injectors/socle_odoo.py` | Injecteur commun ; sous-classes InjecteurOdoo17 / InjecteurOdoo18 |
| `installer_bouchons_odoo` | `tests/test_assistant_import.py` | Installe tous les modules odoo simulés |
| `instance_fec` | `tests/test_connecteurs.py` | Connecteur FEC passé à une doublure de test |
| `instant` | `interface/auth.py` | Horodatage d'un échec de connexion |
| `instant_cache` | `interface/serveur.py` | Instant de la dernière lecture des bases SQL |
| `Instantane` | `core/surveillance.py` | TypedDict : photo légère d'une base (écritures, comptes, verrous) |
| `interieur` | `core/yaml_min.py` | Contenu entre crochets d'une liste en ligne |
| `intitule` | `core/mapping.py` | Paramètre : intitulé d'en-tête cherché |
| `jeton` | `core/connecteurs/http_json.py` | Jeton Bearer de l'API |
| `jour` | `tests/test_xlsx_vers_fec.py`, `core/connecteurs/transfert.py`, `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Paramètre : jour d'une ligne Quadra ; aussi : date du feu vert (connecteurs/transfert) |
| `journal` | `tests/test_xlsx_vers_fec.py`, `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Paramètre : code journal d'une ligne FEC attendue ; aussi : journal reçu par un connecteur ou le transfert (connecteurs) |
| `journal_actif` | `core/connecteurs/transfert.py` | Journal du transfert (muet si aucun) |
| `journal_canonique` | `core/lettrage.py` | Journal canonique à lettrer (extrait par `extraire_canon`) |
| `journal_desequilibre` | `tests/test_moteur.py` | Journal d'une ligne orpheline (refus attendu) |
| `JOURNAL_ESSAI` | `tests/test_xlsx_vers_fec.py` | Journal des lignes Quadra d'essai (VE) |
| `journal_lib` | `tests/test_xlsx_vers_fec.py` | Paramètre : libellé de journal d'une ligne FEC attendue |
| `journal_log` | `tests/test_xlsx_vers_fec.py` | Journal des messages de conversion Quadra |
| `journal_minimal` | `tests/test_moteur.py` | Journal canonique lu depuis `FEC_MINIMAL` |
| `journal_vente` | `tests/test_mapping.py` | Routine : canonique 411/706/445 de test |
| `journaux` | `core/migration/filtres.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Critères du filtre en cours de normalisation |
| `journaux_lot` | `core/migration/injection.py` | Journaux demandés par le lot, avec leur libellé |
| `lancer` | `tests/test_connecteurs.py`, `interface/serveur.py` | Méthode de test : lance concorde_connexion ; aussi : méthode Taches : crée et lance une tâche (routine partagée) |
| `lecteur` | `tests/test_xml_sur.py` | Racine lue ; lecteur de réponses XML-RPC |
| `lecteur_reponse_xmlrpc` | `core/xml_sur.py` | Fabrique du lecteur de réponses XML-RPC (protégé) |
| `lecteur_valeur` | `tests/test_mapping.py` | Lecteur de valeur de cellule testé |
| `lecteurs` | `core/passerelle.py` | {objet: fonction de lecture de la source} |
| `LecteurValeur` | `core/mapping.py` | Type du lecteur de valeur d'une cellule rendu par `lire_feuille_xlsx` |
| `lecture` | `core/xlsx_vers_fec.py`, `core/connecteurs/base.py`, `tests/test_connecteurs.py` | Ordre de lecture retenu pour une date ; aussi : mode de lecture d'un connecteur (connecteurs/base) |
| `lettrage` | `core/connecteurs/azalplus.py` | Code de lettrage d'une ligne |
| `lettrees` | `core/connecteurs/pennylane.py` | Lignes Pennylane lettrées avec une ligne |
| `lettres` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py` | Lettres d'une colonne Excel |
| `lettres_colonne` | `core/xlsx_ecrire.py` | Routine partagée : index de colonne -> lettres Excel (remplace `_col`, `_lettres_colonne`, `lettre_colonne`) |
| `libelle` | `core/migration/filtres.py`, `core/odoo_source.py`, `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Code ou nom d'un compte analytique (dans `analytique_comptes`) ; aussi : libellé d'une connexion ou d'un connecteur (connecteurs) |
| `libelle_journal` | `core/connecteurs/azalplus.py` | Libellé du journal d'une ligne AzalPlus |
| `libelle_ligne` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Libellé d'une ligne d'écriture Odoo (200 caractères au plus) |
| `libelle_mapping` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Libellé du mapping connu au moment de l'échec |
| `libelle_version` | `injectors/socle_odoo.py` | Mot du message d'avertissement de version (« cible » / « attendue ») |
| `libelles_totaux` | `core/migration/export.py`, `injection.py` | (clé de totaux, libellé) comparés entrée / sortie |
| `ligne` | `core/analyser.py`, `core/comparaison.py`, `core/comptes.py`, `core/migration/*.py`, `core/odoo_source.py`, `core/telecharger.py`, `tests/test_surveillance.py`, `core/connecteurs/fec.py`, `core/connecteurs/secrets.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Ligne d'écriture (ex-`l`) ; aussi : ligne du lot ou du fichier de secrets (connecteurs) |
| `ligne_api` | `tests/test_connecteurs.py` | Ligne d'écriture envoyée à l'API simulée |
| `ligne_base` | `tests/test_comparaison.py` | Ligne de la base de test parcourue/modifiée dans un test |
| `ligne_brute` | `core/yaml_min.py` | Ligne d'origine du document |
| `ligne_canon` | `tests/test_moteur.py` | Ligne de journal canonique parcourue |
| `ligne_canonique` | `tests/test_mapping.py` | Routine : LigneEcriture de test |
| `ligne_construite` | `tests/test_comparaison.py` | Ligne d'écriture en cours de construction dans `ligne` |
| `ligne_credit` | `core/lettrage.py` | Ligne au crédit candidate à l'appariement (ex-`lc`) |
| `ligne_debit` | `core/lettrage.py` | Ligne au débit en cours d'appariement (ex-`ld`) |
| `ligne_depuis_odoo` | `core/connecteurs/odoo.py` | Routine : ligne Odoo (odoo_source) -> ligne du Lot |
| `ligne_ecriture` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Ligne d'écriture canonique (LigneEcriture) parcourue |
| `ligne_fec` | `core/telecharger.py`, `tests/outils.py` | Texte d'une ligne du FEC (ex-`ligne`) |
| `ligne_fec_attendue` | `tests/test_xlsx_vers_fec.py` | Routine : ligne FEC attendue (oracle indépendant) |
| `ligne_lot` | `tests/test_injection.py` | Ligne du lot parcourue pour construire les rangs relus |
| `ligne_lue` | `tests/test_odoo_donnees.py`, `tests/test_connecteurs.py` | Ligne de texte du FEC relu dans `TestFec.lire` (remplace `l`) |
| `ligne_nettoyee` | `core/yaml_min.py` | Ligne sans commentaire |
| `ligne_odoo` | `tests/test_injection.py` | Ligne `account.move.line` du faux Odoo parcourue |
| `ligne_quadra` | `tests/test_xlsx_vers_fec.py` | Routine : ligne d'export Quadra |
| `ligne_quadra_attendue` | `tests/test_xlsx_vers_fec.py` | Routine : ligne FEC attendue pour une ligne Quadra |
| `ligne_refusee` | `tests/test_xlsx_vers_fec.py` | Ligne qui doit être refusée |
| `ligne_texte` | `core/migration/connecteur_fec.py` | Ligne de texte lue pendant la recherche de l'en-tête |
| `ligne_valeurs` | `tests/classeurs_xlsx.py` | Routine : <row> à partir de valeurs en colonnes A, B… |
| `ligne_xml` | `tests/classeurs_xlsx.py` | Routine : <row> à partir de fragments de cellules |
| `LigneIllisible` | `core/migration/lot.py` | Type d'une ligne illisible (numéro, texte, motif) |
| `LigneLot` | `core/migration/lot.py` | Type d'une ligne du lot (TypedDict, montants en centimes) |
| `LigneLue` | `core/comparaison.py` | Alias `Mapping[str, Any]` : ligne lue au format commun |
| `LignePayloadOdoo` | `injectors/socle_odoo.py` | Type d'une ligne account.move.line envoyée à Odoo (montants en euros) |
| `LignePayloadVersion` | `injectors/odoo_conversion.py` | Type d'une ligne du payload converti (centimes) |
| `LigneQuadra` | `core/xlsx_vers_fec.py` | TypedDict : ligne validée d'un export Cegid Quadra avant regroupement |
| `lignes` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py`, `tests/test_plan_comptable.py`, `tests/test_xlsx_vers_fec.py`, `core/connecteurs/secrets.py`, `tests/test_connecteurs.py`, `core/connecteurs/base.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Lignes d'une feuille ou d'un document de test ; aussi : lignes du fichier env réécrit (connecteurs/secrets) |
| `lignes_api` | `core/connecteurs/pennylane.py` | Lignes d'écriture lues dans Pennylane |
| `lignes_classeur` | `tests/test_xlsx_vers_fec.py` | Lignes écrites dans le classeur de test |
| `lignes_client` | `tests/test_mapping.py` | Lignes du fichier de mapping client |
| `lignes_fec` | `core/xlsx_vers_fec.py` | Lignes FEC produites avant encodage |
| `lignes_filtrables` | `tests/test_comparaison.py` | Lignes de test avec comptes analytiques, passées à `filtrer_lignes` (ex-`L`) |
| `lignes_lues` | `tests/test_xlsx_vers_fec.py` | Lignes rendues par `_lire_xlsx_stdlib` |
| `lignes_par_tiers` | `core/migration/lot.py` | Routine partagée : nombre de lignes par référence de tiers |
| `lignes_relues` | `core/migration/export.py` | Lignes d'une écriture du FEC relu (remplace `ls`) |
| `lignes_sortie` | `core/migration/export.py` | Routine partagée : lignes du lot au format des sorties fichier (ex-`_vers_format_sortie`) |
| `lignes_titre` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Lignes de titre avant l'en-tête |
| `lignes_yaml` | `tests/test_yaml_min.py` | Paramètre : lignes du document YAML |
| `LigneSortie` | `core/migration/export.py` | Type d'une ligne au format de core/telecharger |
| `LigneXlsx` | `core/xlsx_vers_fec.py` | Type : ligne de cellules du classeur (None toléré) |
| `LigneYaml` | `core/yaml_min.py` | Ligne utile (numéro, retrait, contenu) |
| `limite` | `tests/test_connecteurs.py` | Éléments par page, dans l'API simulée |
| `LIMITE_CODES_AFFICHES` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Nombre maximal de codes de comptes cités (30) |
| `lire` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Méthode d'un connecteur : données du périmètre -> Lot |
| `lire_feuille` | `tests/test_xlsx_vers_fec.py` | Méthode : lit une feuille faite de lignes <row> |
| `lire_feuille_deplacee` | `tests/test_xlsx_vers_fec.py` | Méthode : lit un classeur dont la feuille est rangée ailleurs |
| `lire_lignes` | `tests/test_yaml_min.py` | Routine : assemble des lignes YAML et les lit |
| `lire_plan` | `tests/test_plan_comptable.py` | Routine : construit puis lit un plan comptable |
| `lire_secrets` | `core/connecteurs/secrets.py` | Routine : lit le fichier de secrets (droits 600 exigés) |
| `lire_xml` | `core/xml_sur.py` | Routine : lecture XML sûre (defusedxml) |
| `liste` | `interface/serveur.py` | Liste reçue (comptes ou analytiques) |
| `lister` | `core/connecteurs/connexions.py` | Méthode de l'annuaire : connexions par libellé |
| `logiciel` | `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/registre.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Nom court du logiciel d'un connecteur |
| `longueur_suffixe` | `core/bases_locales.py` | Longueur du suffixe « _modele » retiré du nom du modèle |
| `lot` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Lot au format commun |
| `lot_pret` | `tests/test_connecteurs.py` | Méthode de test : FEC de référence, comptes à l'identique |
| `lot_source` | `core/connecteurs/transfert.py` | Lot lu dans la source (jamais modifié) |
| `maillon` | `core/guardian.py` | Maillon parcouru lors de la vérification de la chaîne |
| `MaillonAudit` | `core/guardian.py` | TypedDict d'un maillon de la chaîne d'audit (charge, empreinte) |
| `main` | `scripts/concorde_connexion.py` | Point d'entrée de concorde_connexion |
| `manquants` | `core/migration/injection.py`, `core/connecteurs/pennylane.py` | Routine : comptes, journaux, tiers du lot absents d'Odoo |
| `manque` | `tests/test_connecteurs.py` | Paramètre attendu dans un message d'erreur, dans un test |
| `mapping_enchaine` | `tests/test_mapping.py` | Mapping de test aux correspondances enchaînées |
| `mapping_lu` | `tests/test_mapping.py` | Mapping rendu par la fonction testée |
| `mapping_simule` | `tests/test_assistant_import.py` | Configuration de mapping simulée (intitulés) |
| `MAPPING_VENTE` | `tests/test_mapping.py` | Mapping complet du journal de vente de test |
| `marquer_coupure` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Paramètre de _codes_html : ajoute « … » si la liste est coupée |
| `message` | `tests/test_mapping.py`, `tests/test_plan_comptable.py`, `core/connecteurs/http_json.py` | Message d'erreur obtenu |
| `message_attendu` | `tests/test_xlsx_vers_fec.py` | Message d'erreur attendu |
| `message_erreur` | `tests/test_xlsx_vers_fec.py` | Routine : lance une conversion qui doit échouer, rend son message |
| `message_obtenu` | `tests/test_xlsx_vers_fec.py` | Message d'erreur obtenu |
| `messages` | `tests/test_connecteurs.py` | Messages du journal, dans un test |
| `method` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Paramètre : méthode HTTP (http.client) |
| `methode` | `injectors/socle_odoo.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Méthode ORM appelée (ex. search_read) |
| `mode` | `core/connecteurs/secrets.py` | Droits du fichier de secrets |
| `modele` | `injectors/socle_odoo.py`, `tests/test_connecteurs.py` | Modèle Odoo appelé (ex. account.move) |
| `MODELE_LISEZMOI` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Modèle du LISEZMOI joint au zip d'export |
| `ModelePiecesJointes` | `tests/test_assistant_import.py` | Modèle ir.attachment simulé |
| `modeles_connus` | `core/bases_locales.py` | Modèles vierges connus (`modeles or {}`) dans `supprimer` |
| `modeles_odoo` | `tests/test_assistant_import.py` | Espace `odoo.models` simulé |
| `modeles_pieges` | `tests/test_bases_locales.py` | Modèle au nom piégé (guillemet + DROP) |
| `modifie_depuis` | `securite/concorde_securite.py` | Vrai si un fichier a été modifié après une limite |
| `module_assistant` | `tests/test_assistant_import.py` | Module de l'assistant chargé |
| `module_bouchon` | `tests/test_assistant_import.py` | Module simulé en cours de création |
| `module_lu` | `deploy/addons/concorde/models/concorde_demat.py` | Un module installé lu (dict name) |
| `module_sans_openpyxl` | `tests/test_xlsx_vers_fec.py` | Module xlsx_vers_fec importé sans openpyxl |
| `modules_lus` | `deploy/addons/concorde/models/concorde_demat.py` | Modules installés lus dans ir.module.module |
| `montant` | `core/migration/injection.py` | Paramètre de `_centimes_base` |
| `montant_devise` | `core/migration/connecteur_fec.py`, `core/connecteurs/azalplus.py` | Montantdevise en centimes ou None |
| `montant_max` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `montant_min` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `montants` | `core/connecteurs/azalplus.py` | (débit, crédit) en centimes |
| `morceaux` | `core/connecteurs/http_json.py` | Adresse découpée (schéma, hôte, port, chemin) |
| `mot` | `core/connecteurs/connexions.py` | Fragment de nom de secret parcouru |
| `mot_de_passe` | `tests/test_connecteurs.py` | Mot de passe ou clé API d'Odoo |
| `motif` | `core/yaml_min.py`, `tests/test_connecteurs.py`, `core/connecteurs/azalplus.py` | Paramètre : raison de l'ErreurYaml ; aussi : motif de retrait d'une ligne (test_connecteurs) |
| `motifs` | `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Motifs des lignes bloquées, dans un test |
| `MOTS_SECRETS` | `core/connecteurs/connexions.py` | Fragments qui signalent un secret dans un nom de paramètre |
| `multiples` | `core/connecteurs/pennylane.py` | Comptes présents sous plusieurs identifiants |
| `name` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Paramètre de cursor (curseur côté serveur, non utilisé) |
| `nature` | `securite/concorde_securite.py`, `core/connecteurs/odoo.py`, `core/migration/injection.py`, `core/odoo_source.py` | Résultat de `classer_connexion` ; aussi : « comptes », « journaux » ou « tiers » |
| `niveau_cascade` | `core/xlsx_vers_fec.py` | Clé de LigneQuadra : cascade qui a rattaché la ligne (0 = aucune) |
| `nom` | `tests/test_interface.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `core/connecteurs/secrets.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py`, `core/connecteurs/base.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Paramètre de `entete_obligatoire` : nom de l'en-tête ; aussi : nom d'un secret, d'un paramètre ou d'un fichier (connecteurs) |
| `nom_base` | `core/bases_locales.py`, `core/migration/injection.py`, `interface/serveur.py` | Paramètre de `_identifiant_sql` : nom de base ou de modèle |
| `nom_champ` | `tests/test_assistant_import.py` | Paramètre : nom du champ lu sur la pièce jointe simulée |
| `nom_conforme` | `core/bases_locales.py` | Résultat de la vérification du nom dans `_identifiant_sql` |
| `nom_etape` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Nom d'une étape parcourue |
| `NOM_FEC` | `core/connecteurs/fec.py` | Nom du FEC écrit sous une référence de transfert |
| `NOM_FICHIER_ESSAI` | `tests/test_xlsx_vers_fec.py` | Nom de fichier des essais (essai.xlsx) |
| `nom_minuscule` | `core/migration/correspondance.py` | Nom de la table en minuscules (remplace `n`) |
| `nom_module` | `tests/test_assistant_import.py` | Paramètre : nom pointé du module simulé |
| `nom_parametre` | `core/connecteurs/base.py`, `core/connecteurs/connexions.py` | Nom d'un paramètre de connexion |
| `nom_secret` | `core/connecteurs/base.py` | Nom d'un secret attendu |
| `nom_variable` | `core/connecteurs/secrets.py` | Routine : nom CONCORDE_CNX_<ID>_<CHAMP> d'un secret |
| `nom_vu` | `core/plan_comptable.py` | Intitulé déjà lu pour un code répété |
| `nombre` | `core/journal.py` | Paramètre de `nombre_texte` (ex-`n`) : nombre à formater |
| `nombre_anomalies` | `interface/serveur.py` | Anomalies BLOQUANT/ALERTE d'une balance |
| `nombres` | `tests/test_surveillance.py` | Nombre de cas par code d'alerte |
| `noms` | `core/connecteurs/azalplus.py` | {nom de tiers : codes des clients et fournisseurs} |
| `noms_etapes` | `tests/test_yaml_min.py` | Noms des étapes du pipeline |
| `noms_feuilles` | `tests/classeurs_xlsx.py` | Paramètre : noms des feuilles du classeur |
| `nouveau` | `core/connecteurs/transfert.py` | État de la destination au nouveau test |
| `nouveau_lot` | `core/connecteurs/base.py` | Routine partagée : Lot à partir de lignes lues par API |
| `nouvelle` | `core/bases_locales.py`, `interface/serveur.py` | Connexion ouverte par `_connexion_ou_nouvelle` |
| `numero` | `interface/serveur.py`, `core/connecteurs/secrets.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Numéro d'un fichier produit dans une tâche ; aussi : numéro de ligne du fichier de secrets (connecteurs/secrets) ; aussi : Rang d'une ligne |
| `numero_attendu` | `tests/test_yaml_min.py` | Numéro de ligne attendu dans l'ErreurYaml |
| `numero_ligne` | `tests/classeurs_xlsx.py` | Numéro de ligne Excel (à partir de 1) |
| `numeros` | `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Numéros de comptes demandés |
| `numuniq` | `tests/test_xlsx_vers_fec.py` | Paramètre : numéro unique Quadra d'une ligne |
| `objet_fil` | `core/migration/injection.py` | Client « object » du fil courant |
| `ObjetJson` | `interface/serveur.py` | Alias dict[str, Any] : objet JSON dynamique (tâche, base, constat, corps de requête) |
| `objets_demandes` | `core/passerelle.py` | Ensemble des objets demandés (ex-réaffectation de `objets`) |
| `obligatoires` | `core/xlsx_vers_fec.py` | Paramètre de `_trouver_entete` : champs qui doivent tous être reconnus |
| `obtenir` | `core/connecteurs/connexions.py` | Méthode de l'annuaire : fiche d'une connexion |
| `OCTETS_DEBUT_ZIP` | `tests/test_assistant_import.py` | En-tête d'un fichier zip (.xlsx), attendu après décodage |
| `octets_fichier` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Octets du fichier rendus par _lire_binaire |
| `odoo` | `tests/test_connecteurs.py` | Méthode de test : connecteur Odoo, ou Odoo simulé |
| `operateur` | `tests/test_connecteurs.py` | Opérateur d'un filtre Pennylane |
| `operations` | `core/migration/filtres.py` | {opérateur: test} d'une condition libre |
| `options` | `injectors/socle_odoo.py` | Arguments nommés de la méthode ORM (omis si None) |
| `options_clamscan` | `securite/concorde_securite.py` | Options de la ligne de commande clamscan |
| `ordre` | `tests/test_connecteurs.py` | Ordre des passages, dans le test du verrou |
| `ORDRES_DATE` | `core/xlsx_vers_fec.py` | Longueurs des groupes -> (ordre, rangs année/mois/jour) |
| `origine` | `core/mapping.py` | Source citée dans les messages d'erreur |
| `outils_cli` | `scripts/outils_cli.py` | Module des routines communes aux scripts en ligne de commande |
| `ouvert` | `tests/test_connecteurs.py` | Connecteur ouvert, dans un test |
| `OUVRANTS_GUILLEMET` | `core/yaml_min.py` | Caractères après lesquels un guillemet ouvre une chaîne |
| `ouvreur` | `core/marceau.py` | OpenerDirector construit par `_ouvreur_https` |
| `ouvrir` | `core/connecteurs/connexions.py`, `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Méthode de l'annuaire : connecteur avec ses seuls secrets |
| `page` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Page d'une liste paginée |
| `paire` | `core/mapping.py`, `scripts/concorde_connexion.py` | Paramètre : paire de comptes à valider ; aussi : « nom=valeur » de la ligne de commande (concorde_connexion) |
| `PaireLettrage` | `core/lettrage.py` | TypedDict d'une paire lettrée (code, compte, montant, ligne_debit, ligne_credit) |
| `paires` | `scripts/concorde_connexion.py` | Paramètres nom=valeur de la ligne de commande |
| `paquet` | `core/connecteurs/pennylane.py` | Paquet de valeurs d'un filtre |
| `paquet_ids` | `core/migration/injection.py` | Paquet de références / d'identifiants lus ou envoyés |
| `paquet_refs` | `core/migration/injection.py` | Paquet de références / d'identifiants lus ou envoyés |
| `paquets` | `core/migration/injection.py` | Résultat et bornes d'un paquet dans `decouper` |
| `par` | `core/connecteurs/transfert.py` | Qui donne le feu vert |
| `par_id` | `core/connecteurs/pennylane.py` | Écritures Pennylane par identifiant |
| `parametres` | `core/bases_locales.py`, `injectors/socle_odoo.py`, `interface/serveur.py`, `tests/test_bases_locales.py`, `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `scripts/concorde_connexion.py`, `tests/test_connecteurs.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py` | Paramètre : valeurs SQL de `CurseurPg.execute` ; aussi : paramètres d'une connexion (connecteurs) |
| `parametres_requis` | `core/connecteurs/base.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py` | Paramètres attendus par un connecteur |
| `ParametresUrl` | `interface/serveur.py` | Alias dict[str, str] : paramètres d'URL, dernière valeur gardée |
| `partages` | `tests/test_mapping.py` | Paramètre : textes de sharedStrings |
| `partenaire` | `core/migration/injection.py` | Tiers Odoo trouvé par sa référence |
| `partie` | `tests/test_xlsx_vers_fec.py` | Partie du classeur de test |
| `parties` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Parties {chemin: xml} d'une archive |
| `PayloadOdoo` | `injectors/socle_odoo.py` | Type du payload account.move envoyé par `create` |
| `PayloadVersion` | `injectors/odoo_conversion.py` | Type du payload account.move d'une version cible |
| `pdf_inspectes` | `core/demat.py` | Nombre maximal de PDF inspectés (plafond max_pdf) |
| `pennylane` | `tests/test_connecteurs.py` | Méthode de test : connecteur Pennylane |
| `perdre_une_ligne` | `tests/test_connecteurs.py` | Doublure : filtres qui perdent une écriture sans trace |
| `perimetre` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Période d'un transfert |
| `PerimetreLecture` | `core/connecteurs/base.py` | TypedDict : période lue (du, au) |
| `periode` | `tests/test_xlsx_vers_fec.py` | Paramètre : période d'une ligne Quadra |
| `PERIODE_ESSAI` | `tests/test_xlsx_vers_fec.py` | Période des lignes Quadra d'essai |
| `photo_source` | `core/connecteurs/transfert.py` | Chemin de la photo FEC de la source |
| `piece` | `core/migration/filtres.py`, `core/connecteurs/azalplus.py` | Critères du filtre en cours de normalisation |
| `piece_creee` | `tests/test_assistant_import.py` | Pièce jointe créée par l'export (None si aucune) |
| `piece_origine` | `core/connecteurs/azalplus.py` | Pièce d'origine d'une ligne AzalPlus |
| `PieceJointeSimulee` | `tests/test_assistant_import.py` | ir.attachment simulé : valeurs reçues à la création |
| `pieces_jointes` | `tests/test_assistant_import.py` | Modèle ir.attachment simulé du test d'export |
| `pipeline` | `tests/test_yaml_min.py` | Liste pipeline de concorde.yaml |
| `PlanComptes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type du plan comptable uploadé {code: (intitulé, type ou None)} |
| `port` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Port de l'API (None = 443) |
| `portee` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `portes` | `core/migration/circuit.py` | Raccourci vers `rapport["portes"]` |
| `position` | `core/yaml_min.py` | Indice de ligne ou de caractère courant (remplace `i`) |
| `prefixe` | `interface/serveur.py`, `core/migration/injection.py` | Préfixe « base — » des lignes de journal ; aussi : Début des références choisi par le transfert |
| `prefixer_ref` | `injectors/socle_odoo.py` | Vrai : référence « CONCORDE/<journal>/<numéro> » ; faux : numéro seul |
| `prefixes_prives` | `securite/concorde_securite.py` | Débuts d'adresses privées exclus du contrôle des ports de minage |
| `PREFIXES_SURS` | `scripts/outils_cli.py` | Débuts d'URL où la clé API ne circule pas en clair |
| `PREFIXES_TEMP` | `securite/concorde_securite.py` | Dossiers temporaires suivis de « / » (test de préfixe) |
| `premiere` | `tests/test_connecteurs.py` | Première ligne lue, dans un test |
| `premiere_ligne` | `scripts/outils_cli.py` | Première ligne d'un texte (description argparse depuis `__doc__`) |
| `Preparation` | `core/migration/injection.py` | Type du bilan de `preparer` |
| `present` | `tests/test_connecteurs.py` | Valeur du champ filtré, dans l'API simulée |
| `presentes` | `core/connecteurs/pennylane.py` | Références déjà présentes dans Pennylane : {référence: id} |
| `presents` | `core/mapping.py` | Chemins présents dans l'archive |
| `produit` | `interface/serveur.py` | Fichier ou format produit par une tâche |
| `ProxyCommun` | `core/migration/injection.py` | Protocoles des services XML-RPC « common » et « object » |
| `ProxyObjet` | `core/migration/injection.py` | Protocoles des services XML-RPC « common » et « object » |
| `ProxyXmlRpc` | `core/xml_sur.py` | Client XML-RPC (ServerProxy) protégé par defusedxml |
| `PSQL_CONCORDE` | `scripts/install_module.sh` | Commande psql (tableau bash) sur la base concorde, arrêt à la première erreur |
| `racine` | `tests/test_xml_sur.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Racine lue ; lecteur de réponses XML-RPC ; aussi : dossier des transferts (connecteurs/transfert) |
| `RACINE_DEPOT` | `tests/outils.py` | Dossier racine du dépôt |
| `rang` | `tests/test_moteur.py`, `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Paramètre : rang de l'étape dans le pipeline |
| `rang_annee` | `core/xlsx_vers_fec.py` | Rang du groupe année |
| `rang_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Paramètre de _bilan_etape : rang de l'étape (2 mapping, 4 rapport) |
| `rang_jour` | `core/xlsx_vers_fec.py` | Rang du groupe jour |
| `rang_mois` | `core/xlsx_vers_fec.py` | Rang du groupe mois |
| `rangees` | `core/export_odoo.py` | Lignes de valeurs à écrire dans un CSV d'export |
| `RangRelu` | `tests/test_injection.py` | Alias : rang SQL relu dans la base de test |
| `rangs` | `core/connecteurs/azalplus.py` | Lignes rendues par une requête SQL |
| `rapport` | `tests/test_odoo_donnees.py` | Rapport d'analyse en dict dans `TestAnalyse.analyse` |
| `rapport_auto` | `tests/test_rapport_jour.py` | Rapport automatique du jour rendu par `construire` |
| `rapport_balance` | `interface/serveur.py` | Rapport d'alertes de la balance |
| `rapport_controle` | `deploy/addons/concorde/models/concorde_demat.py` | Rapport (dict) du contrôle de dématérialisation |
| `rapport_controles` | `core/connecteurs/transfert.py` | Rapport de la batterie de contrôles (étape 1) |
| `rapport_correspondance` | `core/connecteurs/transfert.py` | Rapport de la correspondance des comptes (étape 2) |
| `rapport_demat` | `tests/test_demat.py` | Rapport du contrôle de dématérialisation (dict) |
| `RapportCircuit` | `core/migration/circuit.py` | Type du rapport du lot (rapport.json) |
| `RapportCircuitInitial` | `core/migration/circuit.py` | Partie du rapport du lot présente dès le début |
| `RapportConversion` | `injectors/odoo_conversion.py` | Type du rapport de `convertir_chainee` |
| `RapportFec` | `core/telecharger.py` | TypedDict : résultat de `generer_fec` |
| `RapportInjection` | `injectors/socle_odoo.py` | Type du rapport rendu par `InjecteurOdoo.injecter` |
| `read` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py`, `interface/transferts.py` | Méthode : corps de la réponse HTTP ; aussi : méthode du protocole FluxEntrant (corps d'une requête) |
| `readonly` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Paramètre de set_session (lecture seule) |
| `rechercher_existants` | `core/migration/injection.py` | Routine : comptes, journaux, tiers du lot déjà dans Odoo |
| `reel` | `tests/test_connecteurs.py` | Résultat d'une écriture réelle, dans un test |
| `ref_ecriture` | `core/migration/injection.py` | Routine : référence Odoo <début>/<journal>/<n°> (ex-`_ref`) |
| `reference` | `tests/classeurs_xlsx.py`, `tests/test_xlsx_vers_fec.py`, `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/pennylane.py` | Référence de cellule (ex. B3) ; aussi : référence de transfert CONCORDE/<id> (connecteurs) ; aussi : Référence de transfert (CONCORDE/<id>) |
| `reference_prefixe` | `core/odoo_source.py` | Lire seulement les écritures dont la référence commence par ce début |
| `reference_test` | `core/connecteurs/transfert.py` | Référence d'un test de transfert |
| `references` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | (référence du transfert, référence du test) |
| `references_presentes` | `core/migration/injection.py` | Routine : références d'écritures déjà dans Odoo |
| `refs` | `core/connecteurs/odoo.py`, `tests/test_connecteurs.py`, `core/connecteurs/pennylane.py` | Références des écritures du lot |
| `refus` | `tests/test_connecteurs.py`, `tests/test_ecran_transferts.py` | Destination qui refuse le transfert, dans un test ; aussi : méthode de test : requête refusée, rend la cause |
| `refuses` | `core/connecteurs/connexions.py` | Paramètres au nom de secret refusés |
| `REGISTRE` | `core/connecteurs/registre.py` | Logiciels branchés : nom court -> classe du connecteur |
| `Regle` | `core/comptes.py` | Type : règle d'alerte (code, niveau, condition, message) |
| `regles` | `tests/test_yaml_min.py`, `tests/test_connecteurs.py` | Section regles de concorde.yaml ; aussi : règles de filtres passées à la doublure (test_connecteurs) |
| `regrouper_ecritures` | `injectors/socle_odoo.py` | Regroupe les lignes canoniques par écriture, équilibre vérifié |
| `relations` | `tests/classeurs_xlsx.py` | Éléments <Relationship> |
| `relations_absolues` | `tests/test_xlsx_vers_fec.py` | Relations à cible absolue |
| `relations_autres` | `tests/test_xlsx_vers_fec.py` | Relations ne visant pas la feuille |
| `RELATIONS_CLASSEUR` | `tests/test_xlsx_vers_fec.py` | Relations du classeur vers la feuille |
| `relations_classeur_xml` | `tests/classeurs_xlsx.py` | Routine : workbook.xml.rels à partir de {id: cible} |
| `RELATIONS_RACINE` | `tests/test_xlsx_vers_fec.py` | _rels/.rels vers xl/workbook.xml |
| `relations_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de workbook.xml.rels |
| `relire` | `core/connecteurs/base.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/pennylane.py` | Méthode d'un connecteur : relit ce qui a été écrit |
| `relu` | `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | Lot relu après écriture |
| `remplacement` | `tests/test_xlsx_vers_fec.py` | Remplacement simulé (mock) |
| `reponse` | `tests/test_interface.py`, `core/connecteurs/http_json.py` | Paramètre de `entete_obligatoire` : réponse HTTP reçue |
| `ReponseHttp` | `core/connecteurs/http_json.py` | Protocole : réponse HTTP (http.client ou doublure) |
| `reprise` | `tests/test_connecteurs.py` | Résultat d'une écriture reprise, dans un test |
| `request` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Méthode : envoi d'une requête HTTP |
| `requete` | `core/bases_locales.py`, `interface/serveur.py`, `tests/test_bases_locales.py`, `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Paramètre : ordre SQL de `CurseurPg.execute` |
| `requetes` | `tests/test_connecteurs.py` | Requêtes reçues par la base simulée |
| `resolue` | `interface/serveur.py` | Libellé « alerte résolue » |
| `resoudre_tiers` | `core/connecteurs/azalplus.py` | Routine : code d'un tiers AzalPlus d'après son nom (jamais deviné) |
| `restantes` | `core/xlsx_vers_fec.py` | Lignes Quadra des groupes non soldés après une cascade |
| `reste` | `core/xlsx_ecrire.py`, `core/yaml_min.py` | Reste de la conversion en lettres de colonne ; valeur brute après « clé: » (YAML) |
| `resultat` | `interface/serveur.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/pennylane.py` | Résultat d'une comparaison ; aussi : bilan d'écriture ou des filtres (connecteurs) |
| `resultat_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py`, `tests/test_moteur.py` | Rend le résultat d'une étape du pipeline, type vérifié |
| `ResultatEcriture` | `core/connecteurs/base.py` | TypedDict : bilan d'une écriture ou d'un essai à blanc |
| `ResultatEnvoi` | `core/migration/injection.py` | Type du résultat de `envoyer` |
| `ResultatEtape` | `core/moteur.py` | TypedDict d'une étape exécutée (etape, resultat, marceau) |
| `ResultatFiltres` | `core/migration/filtres.py` | Type du rapport de `filtres.appliquer` |
| `ResultatLettrage` | `core/migration/injection.py` | Type du bilan de `lettrer` |
| `ResultatLettrageCommun` | `core/migration/injection.py` | Partie toujours présente du bilan du lettrage |
| `resultats` | `core/moteur.py` | Liste des étapes exécutées par `executer` |
| `ResultatTraitement` | `core/migration/injection.py` | Variables de type de `en_parallele` / `decouper` |
| `resume` | `interface/serveur.py` | Résumé du centre d'alertes |
| `ResumeEcriture` | `core/analyser.py` | TypedDict : résumé d'une écriture pendant l'analyse |
| `retirees` | `core/connecteurs/fec.py` | Lignes retirées (hors période) |
| `retirees_filtres` | `core/connecteurs/transfert.py` | Lignes retirées par les filtres |
| `retirer` | `core/connecteurs/connexions.py`, `interface/transferts.py` | Méthode de l'annuaire : retire une connexion ; aussi : méthode de l'écran Transferts : retire connexion, secrets et FEC déposé |
| `retirer_hors_periode` | `core/connecteurs/fec.py` | Routine : retire les écritures hors période (gardées à part) |
| `retrait` | `core/migration/filtres.py`, `core/fichier_json.py` | Bilan du filtre en cours (remplace `t`) |
| `RetraitFiltre` | `core/migration/filtres.py` | Type du bilan d'un filtre |
| `retry_after` | `core/connecteurs/http_json.py` | Valeur de l'en-tête Retry-After |
| `role` | `core/connecteurs/transfert.py` | « source » ou « destination » |
| `roles` | `core/connecteurs/transfert.py` | Connexions d'une demande avec leur rôle |
| `sait_faire` | `core/connecteurs/transfert.py` | Mode de lecture ou d'écriture du connecteur |
| `sans_openpyxl` | `tests/test_xlsx_vers_fec.py` | Routine : simule l'absence d'openpyxl |
| `sans_societe` | `core/connecteurs/azalplus.py` | Lignes AzalPlus sans société |
| `sans_table` | `tests/test_connecteurs.py` | Destination sans table de correspondance, dans un test |
| `SANS_TEST` | `core/connecteurs/transfert.py` | Statut : arrêt après la simulation, faute d'environnement de test |
| `sauf_comptes` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `sauvegarde_du` | `core/connecteurs/transfert.py` | Date de la sauvegarde déclarée de la destination |
| `SauvegardeListee` | `core/bases_locales.py` | TypedDict d'une sauvegarde listée (fichier, taille, date, base) |
| `ScalaireYaml` | `core/yaml_min.py` | Type d'un scalaire YAML (str, int, bool) |
| `secret` | `scripts/concorde_connexion.py` | Sous-commande secret de concorde_connexion |
| `secrets` | `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `core/connecteurs/secrets.py`, `tests/test_connecteurs.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Secrets lus, ou secrets donnés à un connecteur |
| `secrets_connexion` | `core/connecteurs/secrets.py` | Routine : secrets d'une connexion, par champ |
| `secrets_renseignes` | `core/connecteurs/connexions.py` | Méthode Annuaire : secrets d'une connexion, renseignés ou non |
| `secrets_requis` | `core/connecteurs/base.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py` | Secrets attendus par un connecteur |
| `section` | `tests/test_yaml_min.py` | Routine : sous-table YAML vérifiée |
| `securite` | `interface/serveur.py` | Constats ou fichiers de sécurité |
| `separateur` | `tests/test_xlsx_vers_fec.py` | Séparateur de date testé |
| `SEPARATEURS_DATE` | `core/xlsx_vers_fec.py` | Regex des séparateurs de date (/ . - espace) |
| `session` | `interface/auth.py`, `tests/test_connecteurs.py` | (création, dernière activité) d'une session |
| `set_session` | `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Méthode : mode de la session (DB-API) |
| `signalements` | `core/migration/lot.py` | Ce que le connecteur source signale sans bloquer |
| `signature` | `core/migration/controles.py` | Signature de la ligne courante (remplace `k`) |
| `SIGNATURE_OLE2` | `tests/test_xlsx_vers_fec.py` | Signature d'un vieux .xls |
| `SignatureComparaison` | `core/comparaison.py` | Signature comparable d'une ligne (avec ou sans analytique) |
| `SignatureLigne` | `core/migration/controles.py` | Type de la signature d'une ligne pour la détection des doublons |
| `signatures` | `core/comparaison.py` | Paramètre de `_lignes_seulement` : signatures à décrire |
| `simulation` | `core/connecteurs/transfert.py` | Résultat de l'essai à blanc (étape 3) |
| `siren` | `core/connecteurs/base.py`, `core/connecteurs/fec.py` | SIREN de la société lue |
| `societe` | `core/odoo_source.py`, `core/connecteurs/base.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py` | Enregistrement XML-RPC brut de la société (`_lire_societe`) ; aussi : société lue au test de connexion (connecteurs/base) |
| `SOCIETE_TEST` | `tests/test_connecteurs.py` | Société AzalPlus des tests (UUID) |
| `socle_odoo` | `injectors/socle_odoo.py` | Module commun des injecteurs Odoo 17/18 et du convertisseur (regroupement, connexion XML-RPC, injecteur) |
| `sortie` | `tests/test_connecteurs.py` | Dossier ou texte de sortie, dans un test |
| `source` | `tests/test_mapping.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py` | Source de mapping testée ; aussi : connexion source d'un transfert (connecteurs) |
| `source_a` | `interface/serveur.py` | Source de la base A (comparaison) |
| `source_b` | `interface/serveur.py` | Source de la base B (comparaison) |
| `source_entiere` | `tests/test_mapping.py` | Source de mapping d'un type non supporté |
| `SourceDemat` | `core/demat.py` | Protocole : interface de lecture du contrôle (champs, lire, modules_installes) |
| `SourceLot` | `core/migration/lot.py` | Type de la description de la source lue (type, nom, empreinte, encodage…) |
| `SourceMapping` | `core/mapping.py` | Type des sources de mapping acceptées (JSON, chemin, dict, paires) |
| `SourceOdoo` | `core/odoo_source.py`, `interface/serveur.py`, `scripts/concorde_odoo.py` | Protocol : interface commune des sources SQL et XML-RPC |
| `sources` | `tests/test_connecteurs.py` | Données simulées par chemin d'API |
| `sous` | `scripts/concorde_connexion.py` | Sous-commandes argparse |
| `sous_table` | `tests/test_yaml_min.py` | Sous-table extraite |
| `spec_assistant` | `tests/test_assistant_import.py` | Spécification d'import de l'assistant |
| `spec_module` | `tests/test_xlsx_vers_fec.py` | Spécification d'import de core.xlsx_vers_fec |
| `StatsLettrage` | `core/lettrage.py` | TypedDict des statistiques du lettrage |
| `status` | `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Statut HTTP de la réponse |
| `statut` | `core/connecteurs/transfert.py`, `core/connecteurs/http_json.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Statut d'une destination ou d'une étape |
| `statut_constats` | `core/migration/circuit.py` | Routine partagée : « bloquee » si un constat est BLOQUANT (ex-`_statut`) |
| `StatutPorte` | `core/migration/circuit.py` | Partie toujours présente de l'état d'une porte |
| `statuts` | `core/connecteurs/pennylane.py` | Statuts d'écritures Pennylane lus |
| `STATUTS_VALIDES` | `core/connecteurs/azalplus.py` | Statuts AzalPlus lus comme validés (VALIDEE, VALIDE) |
| `style_cellule` | `core/xlsx_vers_fec.py` | Indice de style (attribut s) d'une cellule xlsx |
| `STYLE_NORMAL` | `tests/test_xlsx_vers_fec.py` | Style nommé Normal exigé par openpyxl |
| `STYLES_AVEC_STYLE_NOMME` | `tests/test_xlsx_vers_fec.py` | styles.xml : un style nommé avant cellXfs, style 1 = date |
| `styles_cellules` | `core/xlsx_vers_fec.py` | Élément cellXfs : styles indexés par l'attribut s des cellules |
| `STYLES_FORMATS_PERSONNALISES` | `tests/test_xlsx_vers_fec.py` | Styles : formats date 164 et texte littéral 165 |
| `STYLES_PAR_DEFAUT` | `tests/test_xlsx_vers_fec.py` | Police, remplissage, bordure par défaut (openpyxl) |
| `styles_presents` | `tests/test_xlsx_vers_fec.py` | Vrai si le classeur de test a des styles |
| `STYLES_SANS_CELLXFS` | `tests/test_xlsx_vers_fec.py` | Styles sans liste cellXfs |
| `styles_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de xl/styles.xml |
| `suite` | `tests/test_connecteurs.py` | Vrai s'il reste des pages |
| `suivant` | `tests/test_connecteurs.py` | Prochain identifiant de l'API simulée |
| `supprimee` | `interface/serveur.py` | Vrai si la tâche supprime la base (sinon réinitialise) |
| `table` | `core/yaml_min.py` | Table en cours de lecture (remplace `resultat`/`obj`) |
| `TABLE_PJ_PRESENTE` | `scripts/install_module.sh` | « t » si la table ir_attachment existe (sinon base neuve) |
| `tables` | `core/connecteurs/transfert.py` | Tables de correspondance, par destination |
| `tache` | `interface/serveur.py` | Fiche d'une tâche |
| `taille` | `interface/serveur.py` | Taille du corps de requête ou d'un fichier |
| `TAILLE_FILTRE` | `core/connecteurs/pennylane.py` | Valeurs au plus par filtre « in » de Pennylane |
| `tampon` | `interface/serveur.py` | Tampon mémoire (zip, CSV) |
| `tampon_zip` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Tampon mémoire du zip d'export |
| `techniques` | `interface/serveur.py` | Rapport des contrôles techniques |
| `temporaire` | `core/fichier_json.py` | Chemin du fichier .tmp d'une écriture atomique |
| `tenant` | `core/connecteurs/azalplus.py` | Entreprise AzalPlus (UUID) |
| `TENANT_TEST` | `tests/test_connecteurs.py` | Entreprise AzalPlus des tests (UUID) |
| `test` | `core/connecteurs/connexions.py`, `core/connecteurs/transfert.py`, `tests/test_connecteurs.py` | État de l'étape de test, ou connexion de test |
| `TestAnnuaire` | `tests/test_connecteurs.py` | Classe de test : annuaire des connexions |
| `TestCatalogue` | `tests/test_connecteurs.py` | Classe de test : codes TRF_ expliqués par Marceau |
| `TestCentimes` | `tests/test_xlsx_vers_fec.py` | Tests des montants en centimes |
| `TestChargementFichier` | `tests/test_yaml_min.py` | Tests de chargement d'un fichier YAML |
| `TestChargerMappingJson` | `tests/test_mapping.py` | Tests de charger_mapping (JSON) |
| `TestChargerMappingXlsx` | `tests/test_mapping.py` | Tests du classeur Mapping Quadra Odoo |
| `TestClientJson` | `tests/test_connecteurs.py` | Classe de test : client REST JSON |
| `TestCommande` | `tests/test_connecteurs.py` | Classe de test : scripts/concorde_connexion.py |
| `TestCommentairesEnFinDeLigne` | `tests/test_yaml_min.py` | Tests des commentaires de fin de ligne |
| `TestCompteTexte` | `tests/test_mapping.py` | Tests de _compte_txt |
| `TestConnecteurAzalPlus` | `tests/test_connecteurs.py` | Classe de test : connecteur AzalPlus |
| `TestConnecteurFec` | `tests/test_connecteurs.py` | Classe de test : connecteur FEC |
| `TestConnecteurOdoo` | `tests/test_connecteurs.py` | Classe de test : connecteur Odoo sur des Odoo simulés |
| `TestConnecteurPennylane` | `tests/test_connecteurs.py` | Classe de test : connecteur Pennylane |
| `TestConversionQuadra` | `tests/test_xlsx_vers_fec.py` | Tests de conversion d'un export Quadra |
| `TestConversionStandard` | `tests/test_xlsx_vers_fec.py` | Tests de conversion d'un classeur standard |
| `TestDateFec` | `tests/test_xlsx_vers_fec.py` | Tests de _date_fec |
| `TestDateQuadra` | `tests/test_xlsx_vers_fec.py` | Tests de _date_quadra |
| `TestDictionnairePlan` | `tests/test_plan_comptable.py` | Tests de dictionnaire_plan |
| `TestEntete` | `tests/test_xlsx_vers_fec.py` | Tests de détection de l'en-tête |
| `TestEnvoiOdoo` | `tests/test_connecteurs.py` | Classe de test : envoi vers une base Odoo quelconque |
| `tester` | `core/connecteurs/base.py`, `core/connecteurs/connexions.py`, `core/connecteurs/fec.py`, `tests/test_connecteurs.py`, `core/connecteurs/odoo.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/pennylane.py`, `interface/transferts.py` | Méthode : essaie la connexion et lit la société ; aussi : méthode de l'écran Transferts : teste et rend la connexion à jour |
| `TestErreursExplicites` | `tests/test_yaml_min.py` | Tests des erreurs YAML explicites |
| `TestErreursPlan` | `tests/test_plan_comptable.py` | Tests des refus du plan comptable |
| `TestExporter` | `tests/test_assistant_import.py` | Tests de `action_exporter` |
| `TestIndexColonne` | `tests/test_mapping.py` | Tests de _index_colonne |
| `TestLectureOpenpyxl` | `tests/test_xlsx_vers_fec.py` | Tests de lecture par openpyxl |
| `TestLecturePlan` | `tests/test_plan_comptable.py` | Tests de lecture du plan comptable |
| `TestLectureStdlib` | `tests/test_xlsx_vers_fec.py` | Tests du lecteur xlsx interne |
| `TestLectureXmlSure` | `tests/test_xml_sur.py` | Tests de la lecture XML protégée |
| `TestLireFeuilleXlsx` | `tests/test_mapping.py` | Tests d'ouverture et de lecture des cellules |
| `TestListesEnLigne` | `tests/test_yaml_min.py` | Tests des listes entre crochets |
| `TestListesImbriquees` | `tests/test_yaml_min.py` | Tests des listes et tables imbriquées |
| `TestMapperComptes` | `tests/test_mapping.py` | Tests de mapper_comptes |
| `TestNormalisation` | `tests/test_xlsx_vers_fec.py` | Tests de mise en forme des textes et montants |
| `TestNormalisationEntete` | `tests/test_mapping.py` | Tests de _norm_entete |
| `TestScalaires` | `tests/test_yaml_min.py` | Tests des valeurs YAML simples |
| `TestSecrets` | `tests/test_connecteurs.py` | Classe de test : fichier de secrets |
| `TestStructure` | `tests/test_yaml_min.py` | Tests de structure YAML (imbrication, listes) |
| `TestStylesDate` | `tests/test_xlsx_vers_fec.py` | Tests des styles date de la lecture xlsx sans openpyxl |
| `TestTransfert` | `tests/test_connecteurs.py` | Classe de test : procédure de transfert en 7 étapes |
| `TestTypesComptes` | `tests/test_plan_comptable.py` | Tests de déduction du type Odoo |
| `TestVraieConfiguration` | `tests/test_yaml_min.py` | Tests du vrai concorde.yaml |
| `texte` | `core/migration/connecteur_fec.py`, `interface/serveur.py`, `core/connecteurs/transfert.py`, `core/connecteurs/base.py`, `core/connecteurs/pennylane.py`, `tests/test_connecteurs.py` | Paramètre de `_date` (remplace `v`) ; aussi : lignes du lot en JSON pour l'empreinte (connecteurs/transfert) |
| `texte_normalise` | `core/plan_comptable.py` | Texte de type normalisé (remplace `t`) |
| `texte_valeur` | `core/yaml_min.py`, `tests/test_mapping.py` | Texte d'une valeur lue |
| `texte_yaml` | `tests/test_yaml_min.py` | Document YAML d'un sous-test |
| `textes` | `tests/test_mapping.py` | Textes d'une ligne de test |
| `tiers` | `core/migration/filtres.py`, `core/connecteurs/azalplus.py`, `tests/test_connecteurs.py` | Critères du filtre en cours de normalisation |
| `tiers_lot` | `core/migration/injection.py` | Tiers demandés par le lot, avec leur nom |
| `tirage` | `samples/generateur_fec_test.py` | Générateur pseudo-aléatoire local à graine fixe (2026) |
| `totaux` | `core/migration/lot.py`, `controles.py`, `connecteur_fec.py`, `core/connecteurs/transfert.py` | Totaux d'un lot (remplace `t`) ; aussi : totaux du lot d'une destination (connecteurs/transfert) |
| `TotauxLot` | `core/migration/lot.py` | Type des totaux d'un lot (lignes, écritures, débit, crédit) |
| `tout` | `tests/test_connecteurs.py` | Lot lu sans période, dans un test |
| `tout_lire` | `core/connecteurs/http_json.py` | Méthode : toutes les pages d'une liste (curseur) |
| `trace` | `tests/outils.py`, `core/connecteurs/azalplus.py` | Paramètres de `CurseurSimule.__exit__` |
| `traduction` | `core/odoo_source.py` | Traduction retenue d'un texte Odoo (jsonb) |
| `TRANSFEREE` | `core/connecteurs/transfert.py` | Statut : destination transférée et relue conforme |
| `transferts` | `tests/test_connecteurs.py` | Dossier des transferts d'un test |
| `transport_xmlrpc` | `core/odoo_source.py` | Routine partagée : transport XML-RPC HTTP/HTTPS avec délai d'attente |
| `TransportXmlRpc` | `core/xml_sur.py` | Transport XML-RPC HTTP |
| `TransportXmlRpcSur` | `core/xml_sur.py` | Transport XML-RPC HTTPS |
| `trouve` | `core/connecteurs/fec.py` | SIREN trouvé dans le nom du fichier |
| `trouves` | `core/connecteurs/secrets.py`, `core/connecteurs/pennylane.py` | Secrets trouvés pour une connexion |
| `trouves_par_nom` | `core/connecteurs/azalplus.py` | Tiers retrouvés par leur nom : {nom: code} |
| `typ_vu` | `core/plan_comptable.py` | Type déjà lu pour un code répété |
| `type_attendu` | `tests/test_moteur.py` | Paramètre : type que l'étape doit avoir produit |
| `type_cellule` | `tests/classeurs_xlsx.py` | Paramètre : attribut t d'une cellule |
| `type_champ` | `tests/test_assistant_import.py` | Élément de `TYPES_CHAMPS_ODOO` |
| `TYPE_CONTENU_TABLEUR` | `tests/test_xlsx_vers_fec.py` | Préfixe des types MIME officedocument |
| `type_erreur` | `tests/test_xlsx_vers_fec.py` | Paramètre : type d'erreur attendu |
| `type_exception` | `tests/outils.py`, `core/connecteurs/azalplus.py` | Paramètres de `CurseurSimule.__exit__` |
| `type_ligne` | `tests/test_xlsx_vers_fec.py` | Paramètre : TypeLigne d'une ligne Quadra |
| `type_lu` | `tests/test_plan_comptable.py` | Routine : type Odoo déduit d'un type texte |
| `type_odoo` | `tests/test_plan_comptable.py` | Type Odoo attendu |
| `type_partie` | `tests/test_xlsx_vers_fec.py` | Type de contenu d'une partie |
| `type_texte` | `tests/test_plan_comptable.py` | Type de compte écrit par le client |
| `TypeResultat` | `tests/test_moteur.py` | Variable de type : type attendu du résultat d'une étape |
| `TYPES_CHAMPS_ODOO` | `tests/test_assistant_import.py` | Types de champs Odoo simulés par `champ_bouchon` |
| `types_contenu` | `tests/test_xlsx_vers_fec.py` | Routine : [Content_Types].xml du classeur de test |
| `TYPES_ODOO_MESURES` | `tests/test_plan_comptable.py` | Les 18 account_type mesurés dans Odoo 17/18 |
| `types_specifiques` | `core/plan_comptable.py` | Types des clés les plus spécifiques trouvées |
| `uniques` | `core/connecteurs/pennylane.py` | Comptes à un seul identifiant : {numéro: id} |
| `url` | `tests/test_connecteurs.py`, `core/connecteurs/http_json.py` | Adresse du serveur Odoo |
| `utilisateur` | `tests/test_connecteurs.py` | Login Odoo |
| `UTILISATEUR_PG` | `core/montee_version/montee.py` | Utilisateur du PostgreSQL jetable |
| `utilisateurs` | `core/connecteurs/connexions.py` | Connexions qui utilisent une connexion de test |
| `valeur` | `core/migration/circuit.py`, `filtres.py`, `core/connecteurs/secrets.py`, `scripts/concorde_connexion.py`, `core/connecteurs/azalplus.py`, `core/connecteurs/http_json.py`, `tests/test_connecteurs.py` | Paramètre de `_vers_json` / des routines de normalisation ; aussi : valeur d'un secret (connecteurs/secrets) |
| `valeur_champ` | `core/migration/connecteur_fec.py` | Fonction : valeur nettoyée d'une colonne (remplace `val`) ; dans `filtres._condition` : valeur brute du champ testé |
| `valeur_element` | `core/yaml_min.py` | Valeur d'un élément de liste lu |
| `valeur_entete` | `tests/test_interface.py` | Valeur lue de l'en-tête dans `entete_obligatoire` |
| `valeur_lue` | `tests/test_yaml_min.py` | Valeur lue par parse_yaml |
| `valeur_parametre` | `core/connecteurs/connexions.py` | Valeur d'un paramètre de connexion |
| `valeur_si_vide` | `core/yaml_min.py` | Paramètre : valeur d'une clé sans valeur ni bloc |
| `ValeurBinaire` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type d'une valeur lue dans un champ Binary (toutes versions d'Odoo) |
| `ValeurCellule` | `core/mapping.py` | Type d'une valeur de cellule .xlsx (str, int, float, bool) |
| `ValeurParDefaut` | `core/xml_sur.py` | Type de la valeur par défaut de `ElementXml.get` |
| `valeurs` | `core/migration/connecteur_fec.py`, `interface/serveur.py` | Colonnes d'une ligne FEC (remplace `vals`) |
| `valeurs_cellules_ligne` | `core/mapping.py` | Routine partagée : valeurs non vides d'une ligne .xlsx indexées par colonne |
| `valeurs_ecriture` | `core/migration/injection.py` | Fonction : valeurs Odoo d'une écriture (remplace `payload`) |
| `valeurs_ligne` | `tests/test_injection.py` | Valeurs d'une ligne d'écriture créée dans le faux Odoo |
| `valeurs_lignes` | `tests/test_mapping.py` | Paramètre : lignes de valeurs d'une feuille |
| `valeurs_piece` | `tests/test_assistant_import.py` | Valeurs passées à create() d'une pièce jointe simulée |
| `valeurs_premiere_ligne` | `tests/test_mapping.py` | Routine : valeurs typées de la 1re ligne |
| `ValeursEcritureOdoo` | `core/migration/injection.py` | Types des valeurs account.move.line / account.move créées |
| `ValeursLigneOdoo` | `core/migration/injection.py` | Types des valeurs account.move.line / account.move créées |
| `ValeurYaml` | `core/yaml_min.py` | Type récursif d'une valeur YAML (scalaire, liste, dict) |
| `valider_demande` | `core/connecteurs/transfert.py` | Routine partagée : refuse une demande de transfert impossible (écran et creer) |
| `variable` | `interface/transferts.py` | Nom de la variable du plafond |
| `variable_docker` | `interface/serveur.py` | Nom de variable POSTGRES_* (docker) |
| `variable_pg` | `interface/serveur.py` | Nom de variable PG* (libpq) |
| `verifier_cle` | `core/montee_version/volume.py` | Routine : refuse une clé mal protégée |
| `verifier_demande` | `core/montee_version/demandes.py` | Routine : vérifie une demande champ par champ |
| `verifier_erreur` | `tests/test_yaml_min.py` | Routine : vérifie l'ErreurYaml et la ligne citée |
| `verifier_place` | `core/montee_version/montee.py` | Routine : garde-fou de départ |
| `verifier_refus` | `tests/test_plan_comptable.py` | Routine : refus avec le nom du fichier et la cause |
| `verrou` | `core/connecteurs/transfert.py` | Verrou d'une connexion |
| `verrou_connexion` | `core/connecteurs/transfert.py` | Routine : une seule écriture à la fois par connexion |
| `vers` | `core/montee_version/inventaire.py` | Version visée d'un saut |
| `version` | `core/odoo_source.py`, `core/connecteurs/base.py` | Version du module base lue en SQL (`_version`) ; aussi : version d'API ou de format lue au test (connecteurs/base) |
| `version_attendue` | `injectors/socle_odoo.py` | Préfixe de version Odoo attendu (ex. « 17 ») |
| `version_majeure` | `core/montee_version/openupgrade.py` | Routine : numéro majeur d'une version d'Odoo |
| `VERSION_MAX` | `core/montee_version/openupgrade.py` | Version d'Odoo la plus haute prise en charge |
| `VERSION_MIN` | `core/montee_version/openupgrade.py` | Version d'Odoo la plus basse prise en charge |
| `version_odoo` | `interface/serveur.py` | Réponse version() d'Odoo (XML-RPC) |
| `version_postgres` | `core/montee_version/sauvegarde.py` | Routine : version majeure de PostgreSQL du client |
| `version_texte_odoo` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Texte de version d'Odoo (odoo.release.version), repli de _version_majeure_odoo |
| `VERTE` | `core/montee_version/montee.py` | Statut : étape bonne |
| `vide` | `tests/test_connecteurs.py` | Fichier vide, dans un test |
| `vraie` | `tests/test_connecteurs.py` | Connexion destination réelle, dans un test |
| `VUE_ACTION` | `interface/static/app.js` | Vue qui affiche le résultat d'une action (transfert, feu vert -> transferts) |
| `XML_PIEGE` | `tests/test_xml_sur.py` | Document XML ordinaire / bombe d'entités |
| `XML_SAIN` | `tests/test_xml_sur.py` | Document XML ordinaire / bombe d'entités |
| `_action` | `tests/integration/verifier_photo.py` | Lance une action Odoo dont le retour ne passe pas par XML-RPC |
| `_code` | `core/montee_version/photo.py` | Code d'un compte pour une société |
| `_codes_comptes` | `core/montee_version/photo.py` | {(société, compte): code}, code commun ou par société |
| `_codes_par_societe` | `tests/integration/verifier_photo.py` | {(société, compte): code} lu par l'ORM |
| `_compte_analytique` | `tests/integration/verifier_photo.py` | Crée un compte analytique (avec plan à partir de 16) |
| `_dates_verrous` | `core/montee_version/photo.py` | Dates de verrouillage *_lock_date de chaque société |
| `_ecriture` | `tests/integration/verifier_photo.py` | Crée et valide une écriture dans la base de la CI |
| `_ident` | `tests/integration/verifier_photo.py` | Champ many2one XML-RPC -> identifiant ou None |
| `_lettrer` | `tests/integration/verifier_photo.py` | Lettre des lignes puis vérifie en relisant |
| `_mot_de_passe` | `tests/integration/verifier_photo.py` | Mot de passe de la base jetable de la CI |
| `_objet` | `tests/integration/verifier_photo.py`, `core/odoo_source.py`, `core/demat.py` | Proxy XML-RPC « object » d'Odoo |
| `_sections_lignes` | `core/montee_version/photo.py` | Balance, balance tiers et lettrage depuis les lignes |
| `_sections_pieces` | `core/montee_version/photo.py` | Journaux et analytique |
| `_SQL_ANALYTIQUE_PHOTO` | `core/montee_version/photo.py` | Requête : lignes analytiques liées à une écriture, par compte analytique |
| `_SQL_COMPTES_PHOTO` | `core/montee_version/photo.py` | Requête : code des comptes (code ou code_store) |
| `_SQL_JOURNAUX_PHOTO` | `core/montee_version/photo.py` | Requête : code des journaux |
| `_SQL_LIGNES_PHOTO` | `core/montee_version/photo.py` | Requête : lignes validées par société, année, compte, tiers |
| `_SQL_PIECES_PHOTO` | `core/montee_version/photo.py` | Requête : écritures et lignes validées par société, année, journal |
| `_SQL_SOCIETES_PHOTO` | `core/montee_version/photo.py` | Requête : sociétés en JSON (dates de verrouillage) |
| `_SQL_VERSION_PHOTO` | `core/montee_version/photo.py` | Requête : version du module base |
| `_verrous_orm` | `tests/integration/verifier_photo.py` | Dates de verrouillage stockées, lues par l'ORM |
| `acompte` | `tests/integration/verifier_photo.py` | Lignes de l'écriture de règlement partiel |
| `ajouter_valeurs` | `core/montee_version/photo.py` | Routine : cumule des valeurs terme à terme sous une clé |
| `annee` | `core/montee_version/photo.py`, `tests/integration/verifier_photo.py` | Année de la date d'une ligne |
| `annoncer` | `tests/integration/verifier_photo.py` | Écrit les écarts en annotations d'erreur de la CI |
| `annulations` | `tests/test_montee_version.py` | Nombre de fins de transaction de la base simulée |
| `appel` | `tests/integration/verifier_photo.py` | Méthode : execute_kw vers Odoo |
| `BasePhoto` | `tests/test_montee_version.py` | Doublure : connexion SQL simulée pour la photo |
| `cle_journal` | `tests/integration/verifier_photo.py` | Clé société|année|journal d'une ligne |
| `code_societe` | `core/montee_version/photo.py` | Code d'un compte pour une société (code_store) |
| `CODE_SORTIE` | `tests/integration/verifier_photo.py` | Code de sortie du script de vérification (0 = zéro écart) |
| `codes_societes` | `core/montee_version/photo.py` | code_store d'un compte : {société: code} |
| `commun` | `tests/integration/verifier_photo.py`, `tests/test_montee_version.py`, `core/demat.py` | Proxy XML-RPC « common » d'Odoo |
| `comparer_photos` | `core/montee_version/photo.py` | Routine : écarts entre deux photos, au centime |
| `COMPTES_CODE_COMMUN` | `tests/test_montee_version.py` | Comptes simulés avec code en colonne (Odoo 14 à 17) |
| `COMPTES_CODE_PAR_SOCIETE` | `tests/test_montee_version.py` | Comptes simulés avec code par société, code_store (Odoo 18) |
| `connexion_lecture_seule` | `core/odoo_source.py` | Routine : connexion PostgreSQL en lecture seule |
| `creance` | `tests/integration/verifier_photo.py` | Compte client (à recevoir) du tiers de test |
| `creer_donnees` | `tests/integration/verifier_photo.py` | Crée les écritures connues dans la base de la CI |
| `cumul` | `core/montee_version/photo.py` | Valeurs cumulées d'une clé |
| `cumuls` | `core/montee_version/photo.py`, `tests/integration/verifier_photo.py` | {section: {clé: valeurs}} en cours de calcul |
| `CurseurPhoto` | `tests/test_montee_version.py` | Doublure : curseur SQL qui rend les lignes prévues par requête |
| `divers` | `tests/integration/verifier_photo.py` | Journal des opérations diverses |
| `EcartPhoto` | `core/montee_version/photo.py` | TypedDict : une différence entre deux photos (section, clé, avant, après) |
| `ecarts` | `core/montee_version/photo.py`, `tests/integration/verifier_photo.py`, `tests/test_montee_version.py` | Liste des écarts entre deux photos |
| `empreinte` | `core/montee_version/photo.py` | Empreinte SHA-256 d'une photo |
| `empreinte_sections` | `core/montee_version/photo.py` | Routine : empreinte des sections d'une photo |
| `encaissement` | `tests/integration/verifier_photo.py` | Lignes de l'écriture d'encaissement |
| `ErreurPhoto` | `core/montee_version/photo.py` | Exception : base illisible comme Odoo 14 à 18 (cause nommée) |
| `extra` | `tests/integration/verifier_photo.py` | Champs supplémentaires d'une ligne d'écriture de test |
| `lien` | `tests/integration/verifier_photo.py` | Champ qui relie une ligne analytique à une ligne d'écriture |
| `lien_analytique` | `tests/integration/verifier_photo.py` | Champ analytique de la ligne (analytic_account_id ou analytic_distribution) |
| `objet` | `tests/test_montee_version.py` | Proxy XML-RPC « object » dans un test |
| `OdooVerif` | `tests/integration/verifier_photo.py` | Classe : appels ORM vers la base Odoo jetable de la CI |
| `photo_code_commun` | `tests/test_montee_version.py` | Photo d'une base avec code en colonne |
| `photo_code_societe` | `tests/test_montee_version.py` | Photo d'une base avec code par société |
| `photo_orm` | `tests/integration/verifier_photo.py` | Même photo calculée par l'ORM d'Odoo |
| `photo_sql` | `tests/integration/verifier_photo.py` | Photo prise en SQL |
| `PhotoComptable` | `core/montee_version/photo.py` | TypedDict : photo comptable d'une base (sections, version, empreinte) |
| `pieces` | `tests/integration/verifier_photo.py` | Identifiants des écritures d'une clé de journal |
| `plans` | `tests/integration/verifier_photo.py` | Plans analytiques existants |
| `prendre_photo` | `core/montee_version/photo.py` | Routine : photo comptable d'une base Odoo 14 à 18 |
| `proxys` | `tests/integration/verifier_photo.py` | Couple de proxys XML-RPC (common, object) |
| `proxys_xmlrpc` | `core/odoo_source.py` | Routine : proxys XML-RPC common et object d'Odoo |
| `relues` | `tests/integration/verifier_photo.py` | Lignes relues après lettrage |
| `reponses` | `tests/test_montee_version.py` | {requête SQL: lignes} de la base simulée |
| `reponses_odoo` | `tests/test_montee_version.py` | Réponses d'une petite base simulée |
| `rollback` | `tests/test_montee_version.py` | Méthode : fin de transaction de la base simulée |
| `sections` | `core/montee_version/photo.py`, `tests/integration/verifier_photo.py`, `tests/test_montee_version.py` | Sections d'une photo, en texte |
| `SECTIONS_PHOTO` | `core/montee_version/photo.py` | Sections d'une photo : balance, tiers, journaux, lettrage, analytique, verrous |
| `sections_texte` | `core/montee_version/photo.py` | Routine : cumuls -> sections en texte, clés triées |
| `societes` | `tests/integration/verifier_photo.py` | Identifiants des sociétés de la base |
| `sql` | `core/montee_version/photo.py`, `tests/test_montee_version.py` | Texte d'une requête SQL |
| `tailles` | `tests/integration/verifier_photo.py` | Nombre de clés par section |
| `TestComparer` | `tests/test_montee_version.py` | Tests de comparer_photos |
| `TestOuvertures` | `tests/test_montee_version.py` | Tests de connexion_lecture_seule et proxys_xmlrpc |
| `TestPhoto` | `tests/test_montee_version.py` | Tests de prendre_photo |
| `uid` | `tests/integration/verifier_photo.py` | Identifiant de l'utilisateur Odoo connecté |
| `valeurs_apres` | `core/montee_version/photo.py` | Valeurs d'une section après la montée |
| `valeurs_avant` | `core/montee_version/photo.py` | Valeurs d'une section avant la montée |
| `valeurs_section` | `core/montee_version/photo.py` | {clé: valeurs} d'une section |
| `vente` | `tests/integration/verifier_photo.py` | Lignes de l'écriture de vente 2023 |
| `vente_partielle` | `tests/integration/verifier_photo.py` | Lignes de la vente 2024 réglée en partie |
| `verrous` | `core/montee_version/photo.py`, `tests/integration/verifier_photo.py` | Dates de verrouillage d'une photo |
| `_comparer` | `scripts/concorde_montee.py` | Sous-commande comparer : écarts entre deux photos |
| `_photo` | `scripts/concorde_montee.py` | Sous-commande photo : prend et enregistre la photo d'une base |
| `charger_photo` | `core/montee_version/photo.py` | Routine : relit une photo et vérifie son empreinte |
| `chemin_apres` | `scripts/concorde_montee.py` | Fichier de la photo prise après la montée |
| `chemin_avant` | `scripts/concorde_montee.py` | Fichier de la photo prise avant la montée |
| `comparer` | `scripts/concorde_montee.py` | Analyseur de la sous-commande comparer |
| `lue` | `core/montee_version/photo.py` | Photo relue depuis un fichier |
| `photo` | `scripts/concorde_montee.py`, `tests/test_montee_version.py` | Photo comptable (ou analyseur de la sous-commande photo) |
| `relue` | `tests/test_montee_version.py` | Photo relue dans un test |
| `TestCommandeMontee` | `tests/test_montee_version.py` | Tests de charger_photo et de la commande concorde_montee |
| `zip_client` | `tests/test_montee_pilotee.py` | Sauvegarde du client simulée |
