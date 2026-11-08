# Sommaire des variables — CONCORDE

Toute nouvelle variable est déclarée ici dans la même modification (protocole CONCORDE, § E).
Avant d'en créer une, vérifier (casse ignorée) qu'elle n'existe pas déjà.

> Sommaire commencé le 07/11/2026 (version 1.4.10) : il ne liste que les variables
> créées ou renommées depuis (passe qualité 1.5.0 comprise). Les variables plus anciennes
> restent à y reporter.

| Variable | Fichier | Rôle |
|---|---|---|
| `_analyser` | `interface/serveur.py` | Méthode de Taches : exécution d'une analyse |
| `_arguments` | `tests/test_assistant_import.py` | Paramètres ignorés de `champ_bouchon` |
| `_avec_delai` | `core/odoo_source.py` | Routine : applique le délai d'attente à une connexion HTTP |
| `_bilan_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : dict produit par une étape du pipeline |
| `_centimes_base` | `core/migration/injection.py` | Montant SQL en euros -> centimes (remplace la fonction locale `c`) |
| `_centimes_ou_rien` | `core/migration/filtres.py` | Routine : montant en euros -> centimes, ou None |
| `_CHAMPS_TEXTE_LIGNE` | `core/odoo_source.py` | Champs texte d'une ligne SQL ramenés de NULL à '' |
| `_chemin_executable` | `core/bases_locales.py` | Routine partagée : chemin absolu de pg_dump / pg_restore (FileNotFoundError si absent) |
| `_codes_html` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : liste de codes de comptes échappée (au plus 30) |
| `_colonnes_reconnues` | `core/xlsx_vers_fec.py` | Reconnaît les colonnes (synonymes) d'une ligne candidate à l'en-tête |
| `_comptes_de_cle` | `core/odoo_source.py` | Routine : clé de répartition analytique -> codes/noms de comptes |
| `_comptes_des_lignes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : parcourt les lignes FEC portant un numéro de compte |
| `_connexion` | `injectors/socle_odoo.py`, `injectors/odoo_conversion.py` | Connexion Odoo ouverte (None tant que non connecté) |
| `_connexion_active` | `injectors/socle_odoo.py` | Rend la connexion ouverte ou lève ErreurInjecteur |
| `_connexion_ou_nouvelle` | `core/bases_locales.py` | Routine partagée : connexion fournie, ou nouvelle fermée en fin de bloc |
| `_ConnexionHttp` | `core/odoo_source.py` | TypeVar (HTTPConnection ou HTTPSConnection) de `_avec_delai` |
| `_constat_explique` | `interface/serveur.py` | Routine : constat allégé (sans éléments) et expliqué |
| `_construire_ligne_fec` | `core/xlsx_vers_fec.py` | Construit une ligne FEC complète (CHAMPS_FEC) |
| `_cookie_session` | `interface/serveur.py` | Routine : en-tête Set-Cookie de session (None = effacement) |
| `_couche_superflue` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Compteur (non utilisé) des couches base64 en trop retirées par `_lire_binaire`, 3 au maximum |
| `_creer_fiche_erreur` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : crée la fiche d'import en erreur et rend son action |
| `_date_ou_rien` | `core/migration/filtres.py` | Routine : date ISO -> date, ou None |
| `_derniere_empreinte_valide` | `core/guardian.py` | Méthode partagée : recalcule la chaîne d'audit, None si un maillon est altéré |
| `_description_sql` | `interface/serveur.py` | Méthode de Bases : fiche d'une base du serveur |
| `_disposition_piece_jointe` | `interface/serveur.py` | Routine : valeur de l'en-tête Content-Disposition |
| `_DOC_OFFICE` | `core/xlsx_ecrire.py` | Espace de noms des relations officeDocument |
| `_Domaine` | `stubs/odoo/models.pyi` | Type d'un domaine de recherche Odoo (stub) |
| `_ecrire_csv` | `core/export_odoo.py` | Routine partagée : CSV CRLF préfixé du BOM UTF-8 |
| `_ecrire_json_atomique` | `interface/serveur.py` | Routine : écriture JSON via fichier .tmp puis renommage |
| `_Element` | `core/demat.py` | TypeVar : élément d'une liste découpée par `_lots` |
| `_empreinte_maillon` | `core/guardian.py` | Routine partagée : empreinte SHA-256 d'un maillon chaînée à la précédente |
| `_encoder_fec` | `core/xlsx_vers_fec.py` | Sérialise en-tête + lignes FEC en UTF-8 |
| `_enregistrer_rapport` | `interface/serveur.py` | Méthode de Gestionnaire : POST /api/rapport |
| `_ENTETE_XML` | `core/xlsx_ecrire.py` | Déclaration XML commune aux parties du classeur |
| `_erreur_fichier` | `core/mapping.py` | Routine partagée : lève l'erreur « Fichier <quoi> <nom> : <message> » |
| `_ETATS_TEXTE` | `core/odoo_source.py` | Libellé français des états d'écriture (journal) |
| `_evenement_info` | `interface/serveur.py` | Routine : constat INFO pour le centre d'alertes |
| `_executer_pipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : prépare mapping et plan puis exécute le moteur |
| `_explication` | `interface/serveur.py` | Routine : explication Marceau d'un constat |
| `_feuille` | `tests/test_mapping.py` | Paramètre ignoré d'un lecteur de feuille simulé |
| `_fichier_instantane` | `interface/serveur.py` | Routine : chemin de la photo de surveillance d'une base |
| `_identifiant_sql` | `core/bases_locales.py` | Routine : vérifie un nom de base (`_NOM_VALIDE`) et le rend entre guillemets pour le SQL |
| `_identifiants` | `tests/outils.py` | Paramètres ignorés de `FauxCommun.authenticate` |
| `_ids_par_code` | `injectors/socle_odoo.py` | {code: id} d'un modèle Odoo pour une liste de codes |
| `_jour_valide` | `interface/serveur.py` | Routine : vrai si le texte est une date AAAA-MM-JJ |
| `_lecteur` | `tests/test_mapping.py` | Paramètre ignoré d'un lecteur de valeur simulé |
| `_libelle_action` | `core/rapport_jour.py` | Libellé français d'une action de tâche |
| `_lignes_a_retirer` | `core/migration/filtres.py` | Lignes retirées par un filtre selon sa portée |
| `_lignes_problemes` | `core/migration/circuit.py` | Lignes de problemes.xlsx (explication calculée une fois par constat) |
| `_lignes_seulement` | `core/comparaison.py` | Routine : décrit les lignes présentes d'un seul côté (A ou B) |
| `_lire_json` | `interface/serveur.py` | Routine : contenu d'un fichier JSON UTF-8 |
| `_lire_par_lots` | `core/odoo_source.py` | Routine : `read` XML-RPC par lots de TAILLE_LOT |
| `_lire_rangs` | `core/migration/injection.py` | Routine : requête SQL de relecture du lot |
| `_lire_societe` | `core/odoo_source.py` | Routine : lecture XML-RPC de champs de la société (societe_info, verrous) |
| `_liste_textes` | `core/migration/filtres.py` | Routine : critère liste ou texte à virgules -> liste de textes |
| `_mapping_depuis_lignes` | `core/mapping.py` | Routine partagée : lignes JSON {quadra, odoo} → dict de correspondances |
| `_Methode` | `stubs/odoo/api.pyi` | Type d'une méthode décorée par api.model (stub) |
| `_motif_erreur` | `interface/serveur.py` | Routine : texte « Type : message » d'une exception |
| `_noms_bases_locales` | `interface/serveur.py` | Routine : noms des bases du serveur (SQL) |
| `_OPENPYXL_DISPONIBLE` | `core/xlsx_vers_fec.py` | Vrai si openpyxl est importable |
| `_options` | `tests/test_assistant_import.py` | Paramètres ignorés de `champ_bouchon` |
| `_ouvreur_https` | `core/marceau.py` | Ouvreur d'URL limité au schéma https |
| `_Parametres` | `core/guardian.py` | ParamSpec des arguments de l'étape enveloppée |
| `_parties` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Colonnes de la ligne FEC, inutilisées lors des correspondances |
| `_plan` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Plan comptable rendu par `_executer_pipeline`, inutile à l'export |
| `_quand_borne` | `core/rapport_jour.py` | Borne un horodatage ISO à la seconde (champ « quand ») |
| `_racine` | `tests/test_mapping.py` | Paramètre ignoré (racine XML) d'un lecteur simulé |
| `_requete` | `tests/test_injection.py` | Paramètres ignorés de `CurseurRelecture.execute` |
| `_Resultat` | `core/guardian.py` | TypeVar du résultat de l'étape enveloppée |
| `_revoquer_cle` | `interface/serveur.py` | Méthode de Gestionnaire : POST /api/cles/revoquer |
| `_SCHEMAS_OPENXML` | `core/xlsx_ecrire.py` | Préfixe d'URL des espaces de noms Office Open XML |
| `_serveur_xmlrpc` | `core/migration/injection.py` | Routine : client XML-RPC (allow_none) |
| `_telecharger` | `interface/serveur.py` | Méthode de Taches : exécution d'un export |
| `_TransportDelai` | `core/odoo_source.py` | Transport XML-RPC HTTP avec délai |
| `_TransportSurDelai` | `core/odoo_source.py` | Transport XML-RPC HTTPS avec délai |
| `_TYPE_OFFICE` | `core/xlsx_ecrire.py` | Préfixe des types de contenu officedocument |
| `_Valeur` | `stubs/odoo/fields.pyi` | Type de la valeur d'un champ (paramètre générique du stub Field) |
| `_valeur_colonne` | `core/xlsx_vers_fec.py` | Lit la cellule d'un champ dans une ligne (None si absente) |
| `_valeurs_fichier_fec` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Routine : valeurs name / fec_filename / fec_file d'une fiche d'import |
| `_verifier_version` | `core/export_odoo.py` | Routine partagée : refuse une version Odoo inconnue |
| `_verrous_texte` | `core/odoo_source.py` | Routine : dates de verrouillage -> texte ISO (instantanés SQL et XML-RPC) |
| `_vers_json` | `core/migration/circuit.py` | Valeur non JSON -> texte (remplace le lambda `default`) |
| `action` | `tests/test_xlsx_vers_fec.py` | Action simulée levant une erreur de lecture |
| `ActionOdoo` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type d'une action Odoo rendue au client web |
| `adresse` | `core/migration/injection.py` | Paramètre : URL du service XML-RPC |
| `AlerteEnregistree` | `core/surveillance.py` | Type : alerte mémorisée dans le fichier JSON du centre |
| `analytique` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `analytiques_choisis` | `core/comparaison.py` | Ensemble des comptes analytiques du filtre |
| `annoncer_constats` | `core/migration/lot.py` | Routine partagée : écrit les constats d'un rapport dans le journal |
| `Anomalie` | `core/demat.py` | TypedDict : anomalie regroupée par code |
| `appliquer_cascade` | `core/xlsx_vers_fec.py` | Regroupe les lignes Quadra non rattachées et rattache les groupes soldés |
| `arbre` | `tests/test_yaml_min.py` | Paramètre : table YAML lue dont on extrait une section |
| `archive` | `deploy/addons/concorde/wizard/concorde_import_wizard.py`, `interface/serveur.py`, `tests/test_assistant_import.py` | Archive zip ouverte (écriture ou lecture) |
| `archive_cassee` | `tests/test_xlsx_vers_fec.py` | Octets d'un zip tronqué (illisible) |
| `archive_complete` | `tests/test_mapping.py` | Classeur de mapping complet en octets |
| `archive_sans_feuille` | `tests/test_xlsx_vers_fec.py` | Classeur de test sans feuille trouvable |
| `archive_vide` | `tests/test_mapping.py` | Zip sans partie de classeur |
| `archive_xlsx` | `tests/classeurs_xlsx.py` | Routine : zip en mémoire à partir de {chemin: xml} |
| `arguments` | `injectors/socle_odoo.py` | Arguments positionnels de la méthode ORM |
| `ascii_seul` | `interface/serveur.py` | Paramètre de _ecrire_json_atomique (ensure_ascii) |
| `assistant` | `tests/test_assistant_import.py` | Assistant d'import chargé hors d'Odoo |
| `AssistantImport` | `tests/test_assistant_import.py` | Protocole : partie de l'assistant d'import vérifiée (`_lire_binaire`) |
| `attendu` | `core/migration/filtres.py` | Valeur attendue par une condition libre |
| `attendus` | `tests/test_mapping.py`, `tests/test_plan_comptable.py` | Valeurs attendues d'un test |
| `attribut_reference` | `tests/classeurs_xlsx.py` | Attribut r="..." d'une cellule (vide si absent) |
| `attribut_type` | `tests/classeurs_xlsx.py` | Attribut t="..." d'une cellule (vide si absent) |
| `attributs` | `tests/test_assistant_import.py` | Paramètre : noms et valeurs exposés par un module simulé |
| `automatique` | `interface/serveur.py` | Rapport du jour construit automatiquement |
| `avertir_si_non_chiffre` | `scripts/outils_cli.py` | Avertit si l'URL Odoo est en http hors machine locale |
| `bases_ignorees` | `interface/serveur.py` | Attribut de Bases : {nom : motif} des bases du serveur écartées au dernier passage |
| `bilan` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Résultat brut d'une étape lu par _bilan_etape |
| `BilanEquilibre` | `core/moteur.py` | TypedDict du résultat de `verifier_equilibre` |
| `BilanMapping` | `core/mapping.py` | TypedDict du résultat de `mapper_comptes` |
| `brut` | `core/migration/filtres.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni |
| `candidat` | `interface/serveur.py` | Constat examiné lors d'une recherche |
| `candidats` | `core/comparaison.py` | Écritures de B candidates au rapprochement par contenu (ex-`cands` réaffecté) |
| `canon` | `tests/test_assistant_import.py` | Journal canonique de test (FEC synthétique) |
| `canon_trouve` | `core/canonical.py` | Canonique lu dans le dict de pipeline par `extraire_canon` |
| `caractere` | `core/xlsx_ecrire.py` | Couple (caractère, entité) de `entites` |
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
| `champ_bouchon` | `tests/test_assistant_import.py` | Remplace un constructeur de champ Odoo |
| `champ_entete` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Colonne d'une ligne FEC lue pour trouver l'en-tête |
| `champs_ligne` | `core/migration/filtres.py` | Vue {champ: valeur} d'une ligne pour une condition libre |
| `charger_assistant_import` | `tests/test_assistant_import.py` | Charge l'assistant d'import hors d'Odoo |
| `chemin` | `tests/classeurs_xlsx.py`, `tests/test_plan_comptable.py` | Chemin d'un fichier ou d'une partie de classeur |
| `chemin_assistant` | `tests/test_assistant_import.py` | Chemin du fichier de l'assistant |
| `chemin_classeur` | `tests/test_mapping.py` | Chemin du classeur de mapping temporaire |
| `CHEMIN_CONFIGURATION` | `tests/test_yaml_min.py` | Chemin du vrai concorde.yaml du dépôt |
| `chemin_executable` | `securite/concorde_securite.py` | Chemin absolu d'un programme (FileNotFoundError si absent) |
| `chemin_feuille` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Chemin de la feuille dans l'archive |
| `chemin_fichier` | `interface/serveur.py` | Chemin d'un fichier produit |
| `chemin_mapping` | `tests/test_moteur.py` | Chemin du fichier JSON de mapping synthétique |
| `CHEMIN_PREMIERE_FEUILLE` | `tests/classeurs_xlsx.py` | Chemin xl/worksheets/sheet1.xml |
| `chemin_rapport` | `interface/serveur.py` | Chemin du rapport.json d'une tâche |
| `chemin_ss` | `securite/concorde_securite.py` | Chemin absolu de `ss` lancé via nsenter |
| `chemins_paquet` | `tests/test_assistant_import.py` | Paramètre : dossiers d'un paquet simulé |
| `chiffre` | `tests/classeurs_xlsx.py` | Rang d'une lettre de colonne (0 = A) |
| `choix` | `interface/serveur.py` | Format ou objet demandé |
| `cible` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py` | Cible d'une relation de classeur |
| `cibles_feuilles` | `tests/test_mapping.py` | Paramètre : cibles des feuilles déclarées |
| `cibles_par_identifiant` | `tests/classeurs_xlsx.py` | Paramètre : {identifiant de relation: cible} |
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
| `cle` | `tests/test_yaml_min.py` | Paramètre : clé de la section à extraire |
| `cle_texte` | `core/migration/lot.py` | Routine partagée : clé d'écriture -> « journal/numéro » |
| `CleApi` | `core/bases_locales.py` | TypedDict d'une clé API listée (jamais sa valeur) |
| `CleEcriture` | `core/migration/lot.py` | Type de la clé d'écriture (journal_code, ecriture) |
| `cles` | `tests/test_bases_locales.py` | Clés API de la base simulée (`FausseBaseCles.cles`) |
| `CleSolde` | `core/comparaison.py` | Clé d'agrégation des soldes : compte, journal ou (compte, tiers) |
| `CleTotaux` | `core/migration/lot.py` | Clés littérales de `TotauxLot` |
| `code` | `tests/test_plan_comptable.py` | Code de compte lu |
| `code_trace` | `injectors/socle_odoo.py` | Étape inscrite dans le journal Guardian (ex. « odoo17 ») |
| `codes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Paramètre de _codes_html : codes de comptes à citer |
| `codes_affiches` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Texte HTML des codes cités par _codes_html |
| `colonnes` | `tests/test_xlsx_vers_fec.py` | Colonnes reconnues d'un en-tête |
| `compte` | `core/migration/lot.py` | Compte (source ou cible) dans `balance_par_compte` |
| `compte_a_arbitrer` | `core/migration/correspondance.py` | Cumul d'un compte à arbitrer (remplace `a`) |
| `compte_attendu` | `tests/test_plan_comptable.py` | Routine : compte attendu {code, nom, type} |
| `compte_lib` | `tests/test_xlsx_vers_fec.py` | Paramètre : intitulé de compte d'une ligne FEC attendue |
| `compte_odoo` | `tests/test_mapping.py` | Compte Odoo cible d'une correspondance |
| `compte_par_tiers` | `core/migration/lot.py` | Dictionnaire résultat de `lignes_par_tiers` |
| `compte_quadra` | `tests/test_mapping.py` | Compte Quadra source d'une correspondance |
| `CompteAArbitrer` | `core/migration/correspondance.py` | Type d'un compte absent de la table (libellé, lignes, montants) |
| `CompteLu` | `core/plan_comptable.py` | TypedDict d'un compte lu dans le plan comptable (code, nom, type) |
| `comptes` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `comptes_attendus` | `tests/test_moteur.py` | Comptes Odoo attendus après mapping |
| `comptes_choisis` | `core/comparaison.py` | Ensemble des comptes du filtre (ex-réaffectation de `comptes`) |
| `condition` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `ConditionDomaine` | `tests/test_demat.py` | Alias : condition de domaine Odoo (champ, opérateur, valeur) |
| `ConditionFiltre` | `core/migration/filtres.py` | Type d'une condition libre normalisée |
| `ConditionOdoo` | `core/demat.py` | Type : condition de domaine Odoo (champ, opérateur, valeur) |
| `conditions` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `config_guardian` | `core/moteur.py` | Section noyau.guardian de la configuration du moteur |
| `ConfigMapping` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type (TypedDict) de la configuration du mapping passée au moteur |
| `configuration` | `tests/test_yaml_min.py` | concorde.yaml chargé |
| `connecter_odoo` | `injectors/socle_odoo.py` | Ouvre une session XML-RPC v2 et trace un écart de version |
| `connexion` | `injectors/odoo_conversion.py`, `tests/test_bases_locales.py` | Connexion Odoo utilisée par `extraire` |
| `connexion_base` | `core/migration/injection.py` | Connexion PostgreSQL ouverte par `relire` |
| `connexion_brute` | `core/bases_locales.py` | Connexion psycopg2 avant typage par Protocol |
| `connexion_espion` | `tests/test_bases_locales.py` | Fausse connexion qui enregistre le SQL exécuté |
| `ConnexionLecture` | `core/migration/injection.py` | Protocoles du curseur et de la connexion SQL de relecture |
| `ConnexionOdoo` | `injectors/socle_odoo.py` | Session XML-RPC authentifiée (db, uid, mot_de_passe, modeles) |
| `ConnexionPg` | `core/bases_locales.py` | Protocol d'une connexion PostgreSQL fournie par l'appelant |
| `ConnexionPgFermable` | `core/bases_locales.py` | Protocol d'une connexion ouverte (et fermée) par le module |
| `connexions` | `securite/concorde_securite.py` | Liste des connexions lues dans les conteneurs |
| `connexions_conteneurs` | `securite/concorde_securite.py` | (pid, adresse distante) des connexions des espaces réseau des conteneurs |
| `ConnexionSql` | `core/odoo_source.py` | Protocol : connexion PostgreSQL (psycopg2) de la source SQL |
| `Constat` | `core/analyser.py`, `core/migration/lot.py`, `interface/serveur.py` | Alias `dict[str, Any]` : constat d'un Rapport (JSON) |
| `ConstatLu` | `core/surveillance.py` | Type : constat produit par Rapport ou relu d'un JSON de sécurité |
| `contenu` | `core/marceau.py`, `core/xml_sur.py` | Texte de la réponse Mistral, vérifié avant retour |
| `contenu_feuille` | `tests/test_xlsx_vers_fec.py` | Paramètre : XML de la feuille du classeur de test |
| `contenu_journal` | `securite/concorde_securite.py` | Texte du journal clamscan.log |
| `contenu_json` | `core/migration/correspondance.py` | Contenu JSON décodé de la table (remplace `d`) |
| `contenu_lignes` | `tests/test_xlsx_vers_fec.py` | XML des lignes d'une feuille |
| `contenu_lu` | `tests/test_assistant_import.py` | Octets rendus par `_lire_binaire` |
| `contenu_xls` | `tests/test_mapping.py` | Octets d'un vieux .xls (OLE2) |
| `contenu_zip` | `tests/test_assistant_import.py` | Octets du zip exporté |
| `contexte` | `tests/test_plan_comptable.py` | Contexte assertRaises |
| `contexte_erreur` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Contexte assertRaises |
| `contexte_rapport` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Données du rapport HTML de l'import (ContexteRapport) |
| `contexte_simule` | `tests/test_assistant_import.py` | Bilan de moteur simulé (étape 2 = canon) |
| `ContexteExecution` | `core/moteur.py` | TypedDict du bilan de `MoteurConcorde.executer` |
| `ContexteRapport` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type (TypedDict) des données du rapport HTML de l'assistant |
| `conversion` | `interface/serveur.py` | Paramètre de _ecrire_json_atomique (default) |
| `convertir_lignes` | `tests/test_xlsx_vers_fec.py` | Routine : lignes -> classeur -> xlsx_vers_fec |
| `cookies` | `interface/serveur.py` | Cookies de la requête |
| `copie_texte` | `core/comparaison.py` | `date_copie` normalisée « AAAA-MM-JJ HH:MM:SS » (ex-réaffectation) |
| `correspondance` | `interface/serveur.py` | Résultat d'une expression régulière sur le chemin |
| `correspondance_version` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Résultat de la recherche du numéro majeur dans le texte de version |
| `correspondances` | `tests/test_moteur.py` | Lignes {quadra, odoo} du mapping synthétique écrit en JSON |
| `cote` | `core/comparaison.py` | Paramètre de `_lignes_seulement` : « A » ou « B » |
| `credit` | `core/migration/connecteur_fec.py` | Montants de la ligne en centimes |
| `creer_module_bouchon` | `tests/test_assistant_import.py` | Crée et enregistre un module odoo simulé |
| `CritereDomaine` | `core/odoo_source.py` | Critère d'un domaine Odoo : « \ | » ou (champ, opérateur, valeur) |
| `criteres_retenus` | `core/migration/filtres.py` | Critères qui retiennent des lignes (tous sauf `sauf_comptes`) |
| `csv_comptes` | `tests/test_assistant_import.py`, `deploy/addons/concorde/wizard/concorde_import_wizard.py` | CSV des comptes du zip d'export |
| `curseur` | `core/migration/injection.py`, `interface/serveur.py` | Curseur SQL de relecture |
| `CurseurAvecContexte` | `tests/outils.py` | Type du faux curseur rendu par `with` |
| `CurseurCles` | `tests/test_bases_locales.py` | Curseur simulé de `FausseBaseCles` (SELECT puis DELETE d'une clé API) |
| `CurseurEnregistreur` | `tests/test_bases_locales.py` | Curseur simulé de `FausseConnexion` : consigne les ordres SQL |
| `CurseurLecture` | `core/migration/injection.py` | Protocoles du curseur et de la connexion SQL de relecture |
| `CurseurPg` | `core/bases_locales.py` | Protocol du curseur PostgreSQL utilisé par le module |
| `CurseurPgSimule` | `tests/test_bases_locales.py` | Faux curseur conforme à `bases_locales.CurseurPg` |
| `CurseurRelecture` | `tests/test_injection.py` | Faux curseur (hérite `CurseurSimule`) rendant des rangs fixés |
| `CurseurSimule` | `tests/outils.py` | Base des faux curseurs PostgreSQL (protocole `with`) |
| `date_copie` | `interface/serveur.py` | Date de copie saisie (comparaison) |
| `date_ecriture` | `core/migration/connecteur_fec.py` | EcritureDate convertie |
| `date_facture` | `core/demat.py` | Date de facture lue une fois par facture en émission |
| `date_lettrage` | `core/migration/connecteur_fec.py` | DateLet convertie |
| `date_piece` | `core/migration/connecteur_fec.py` | PieceDate convertie |
| `date_validation` | `core/migration/connecteur_fec.py` | ValidDate convertie |
| `debit` | `core/migration/connecteur_fec.py` | Montants de la ligne en centimes |
| `debut` | `core/migration/injection.py` | Résultat et bornes d'un paquet dans `decouper` |
| `debut_donnees` | `core/fec_parser.py`, `core/mapping.py`, `core/migration/connecteur_fec.py`, `core/plan_comptable.py`, `core/xlsx_vers_fec.py` | Index de la première ligne de données (après l'en-tête) |
| `debut_lot` | `core/demat.py`, `core/odoo_source.py` | Indice de début d'une tranche dans `_lots` (ex-`i`) |
| `debut_periode` | `core/migration/filtres.py` | Bornes `du` / `au` converties |
| `decalage` | `interface/serveur.py` | Décalage de page du grand livre |
| `declarations` | `tests/test_xlsx_vers_fec.py` | Déclarations de types de contenu |
| `declarations_feuilles` | `tests/classeurs_xlsx.py` | Éléments <sheet> du classeur |
| `decouper` | `core/migration/injection.py` | Routine partagée : découpe une liste en paquets |
| `delai` | `core/odoo_source.py` | Délai d'attente (secondes) d'un transport XML-RPC |
| `depart` | `interface/serveur.py` | Instant de départ d'une mesure de durée |
| `derniere` | `core/guardian.py` | Dernière empreinte recalculée (`verifier_chaine`) |
| `derniere_piece` | `tests/test_assistant_import.py` | Dernière pièce jointe simulée créée |
| `desequilibree` | `interface/serveur.py` | Vrai si la balance est déséquilibrée |
| `DetailsComparaison` | `core/comparaison.py` | Détails de comparaison par catégorie (classeur xlsx) |
| `dimensions` | `core/comparaison.py` | (code, nom, clé) des agrégations de soldes comparées |
| `distant` | `interface/serveur.py` | Fiche d'un Odoo distant |
| `Domaine` | `core/odoo_source.py` | Liste de critères d'un domaine Odoo (XML-RPC) |
| `DomaineOdoo` | `core/demat.py`, `tests/test_demat.py` | Type : domaine Odoo (même sens que dans `tests/test_demat.py`) |
| `donnees` | `tests/test_mapping.py` | Données JSON du mapping de test |
| `DonneesJson` | `core/rapport_jour.py` | Type : données JSON (alertes, tâches, sécurité, rapports, saisie) |
| `dossier` | `securite/concorde_securite.py` | Dossier temporaire courant (construction de PREFIXES_TEMP) |
| `dossier_journal` | `tests/test_moteur.py` | Dossier temporaire du journal Guardian |
| `DOSSIER_MODULE` | `tests/test_assistant_import.py` | Dossier du module Odoo `deploy/addons/concorde` |
| `dossier_temporaire` | `tests/test_moteur.py` | Dossier temporaire du mapping synthétique |
| `EcartSolde` | `core/comparaison.py` | TypedDict : écart de solde A/B pour une clé |
| `echapper_xml` | `core/xlsx_ecrire.py` | Routine : échappe un texte pour l'écrire en XML |
| `echec_pipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | EchecPipeline intercepté par les actions de l'assistant |
| `EchecPipeline` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Exception : échec du pipeline avec le libellé du mapping connu |
| `ecrire_rapport_json` | `scripts/outils_cli.py` | Écrit un rapport JSON lisible (option --json) |
| `EcritureDifferente` | `core/comparaison.py` | TypedDict : couple d'écritures rapprochées qui diffèrent |
| `EcritureGroupee` | `core/comparaison.py` | TypedDict : écriture reconstituée avec ses lignes |
| `EcritureRegroupee` | `injectors/socle_odoo.py` | Type d'une écriture regroupée : ref_ext, journal, numero, date, libelle, lignes, total (centimes) |
| `ecrivain` | `interface/serveur.py` | Écrivain CSV |
| `element` | `core/migration/circuit.py`, `interface/serveur.py` | Explication Marceau d'un constat / élément du constat |
| `elements` | `core/migration/filtres.py`, `injection.py` | Valeur du critère liste / éléments à traiter |
| `elements_liste` | `core/yaml_min.py` | Éléments d'une liste YAML en cours de lecture dans `_bloc` |
| `ElementTraite` | `core/migration/injection.py` | Variables de type de `en_parallele` / `decouper` |
| `ElementXml` | `core/xml_sur.py` | Élément XML lu (protocole : find, iter, get, text) |
| `empreinte_brute` | `interface/auth.py` | Empreinte scrypt (octets) |
| `EN_TETE_FEC_TEXTE` | `tests/test_assistant_import.py` | En-tête de FEC texte (octets) pour les tests de `_lire_binaire` |
| `Enregistrement` | `core/comptes.py`, `core/odoo_source.py`, `injectors/socle_odoo.py`, `tests/outils.py` | Alias `dict[str, Any]` : enregistrement rendu par une source (ligne, compte, journal, tiers, facture) |
| `EnregistrementLu` | `core/telecharger.py` | Alias `Mapping[str, Any]` : enregistrement reçu d'une source |
| `EnregistrementOdoo` | `core/demat.py` | Type : enregistrement Odoo lu (XML-RPC ou ORM) |
| `enregistrements` | `core/demat.py` | Résultat de search_read dans `SourceXmlRpc.lire` |
| `entete` | `core/xlsx_vers_fec.py` | En-tête FEC standard trouvé (index, colonnes) ou None |
| `ENTETE_FEC_ATTENDUE` | `tests/test_xlsx_vers_fec.py` | En-tête FEC attendu (18 champs) |
| `ENTETE_MAPPING_CLIENT` | `tests/test_mapping.py` | En-tête (Numéro, Intitulé, Odoo Acct) du fichier client |
| `ENTETE_MINIMALE` | `tests/test_xlsx_vers_fec.py` | Les 5 colonnes obligatoires d'un FEC standard |
| `entete_obligatoire` | `tests/test_interface.py` | Valeur d'un en-tête HTTP qui doit être présent (échec sinon) |
| `entete_quadra` | `core/xlsx_vers_fec.py` | En-tête Cegid Quadra trouvé (index, colonnes) ou None |
| `ENTETE_STANDARD` | `tests/test_xlsx_vers_fec.py` | En-tête Excel standard avec synonymes |
| `entetes` | `tests/test_plan_comptable.py` | Paramètre : en-têtes du plan de test |
| `ENTETES_PLAN` | `tests/test_plan_comptable.py` | En-têtes usuels d'un plan de test |
| `entite` | `core/xlsx_ecrire.py` | Couple (caractère, entité) de `entites` |
| `entites` | `core/xlsx_ecrire.py` | Remplacements supplémentaires de `echapper_xml` |
| `entree` | `interface/serveur.py` | Entrée d'un compte ou d'un analytique (choix de comparaison) |
| `erreur_lancement` | `securite/concorde_securite.py` | Message si nice / ionice / clamscan est introuvable |
| `erreur_lecture` | `tests/test_xlsx_vers_fec.py` | Erreur simulée d'openpyxl |
| `erreur_levee` | `tests/test_assistant_import.py` | Erreur capturée par le test |
| `erreur_origine` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Exception d'origine portée par EchecPipeline |
| `ErreurConservation` | `core/migration/filtres.py` | Exception : totaux après filtres ≠ avant − retraits (remplace les `assert`) |
| `ErreurLectureXml` | `core/xml_sur.py` | XML mal formé |
| `ErreurOdoo` | `core/migration/injection.py` | Type d'une erreur Odoo gardée (écriture, étape, erreur) |
| `ERREURS_MISTRAL` | `core/marceau.py` | Exceptions d'un appel Mistral qui déclenchent le repli à règles |
| `ErreurUtilisateurBouchon` | `tests/test_assistant_import.py` | Remplace `odoo.exceptions.UserError` |
| `ErreurXmlRpc` | `core/xml_sur.py` | Base des erreurs XML-RPC |
| `ESPACE_PAQUET` | `tests/classeurs_xlsx.py` | Racine des espaces de noms du paquet OPC |
| `ESPACE_RELATIONS` | `tests/test_xlsx_vers_fec.py` | Espace de noms des relations Office |
| `ESPACE_RELATIONS_PAQUET` | `tests/classeurs_xlsx.py` | Espace de noms des fichiers .rels |
| `ESPACE_TABLEUR` | `tests/test_xlsx_vers_fec.py` | Espace de noms SpreadsheetML |
| `etape` | `tests/test_yaml_min.py` | Étape du pipeline lue dans concorde.yaml |
| `EtapeConversion` | `injectors/odoo_conversion.py` | Type du compte rendu d'un saut de version |
| `etapes` | `injectors/odoo_conversion.py` | Comptes rendus des sauts de version |
| `EtatPorte` | `core/migration/circuit.py` | Type de l'état d'une porte dans le rapport |
| `Evenement` | `core/journal.py` | TypedDict d'un événement du journal (t, niveau, message) |
| `evenements` | `interface/serveur.py` | Événements du journal |
| `exception` | `tests/outils.py` | Paramètres de `CurseurSimule.__exit__` |
| `executable` | `deploy/webhook.py` | Chemin absolu de git / docker |
| `executer` | `injectors/socle_odoo.py` | Appel `execute_kw` unique sur la base connectée |
| `explication` | `core/migration/circuit.py` | Explication Marceau d'un constat / élément du constat |
| `extraire_canon` | `core/canonical.py` | Routine partagée : Canonique porté par une donnée du pipeline (Canonique ou dict 'canon' / 'resultat'→'canon'), None sinon |
| `extrait_message` | `tests/test_plan_comptable.py` | Paramètre : extrait attendu du message d'erreur |
| `f_fec` | `core/migration/export.py` | Fichier FEC produit, ouvert en lecture binaire |
| `FauteXmlRpc` | `core/migration/injection.py`, `core/xml_sur.py` | Nom public de `xmlrpc.client.Fault` (erreur renvoyée par Odoo), utilisable par les tests |
| `FauxCommun` | `tests/outils.py` | Point d'entrée XML-RPC « common » Odoo 17 simulé (déplacé, partagé) |
| `fec_attendu` | `tests/test_xlsx_vers_fec.py` | Routine : FEC complet attendu en octets |
| `fec_interne` | `tests/test_xlsx_vers_fec.py` | FEC produit par le lecteur interne |
| `FEC_MINIMAL` | `tests/test_moteur.py` | FEC minimal équilibré (sorti de `TestParseurFEC`, partagé par le fichier) |
| `fec_openpyxl` | `tests/test_xlsx_vers_fec.py` | FEC produit via openpyxl |
| `fec_produit` | `tests/test_xlsx_vers_fec.py` | FEC produit par xlsx_vers_fec |
| `Feuille` | `core/xlsx_ecrire.py` | Type : (nom, entêtes, lignes) d'une feuille à écrire |
| `FEUILLE_DATE_ET_NOMBRE` | `tests/test_xlsx_vers_fec.py` | Feuille : une date (série 45296) et un nombre |
| `feuille_depuis_lignes` | `tests/classeurs_xlsx.py` | Routine : feuille à partir de lignes de valeurs |
| `feuille_tableau` | `tests/test_mapping.py` | Routine : feuille à partir de tuples de textes |
| `FEUILLE_TROIS_STYLES` | `tests/test_xlsx_vers_fec.py` | Feuille : date personnalisée, format littéral, sans style |
| `FEUILLE_UN_TEXTE` | `tests/test_xlsx_vers_fec.py` | Feuille d'une seule cellule texte |
| `feuille_xml` | `tests/classeurs_xlsx.py` | Routine : enveloppe <worksheet> autour de lignes <row> |
| `fiche` | `interface/serveur.py` | Fiche d'une base de l'annuaire |
| `fichier` | `tests/test_moteur.py` | Fichier JSON ouvert en écriture |
| `fichier_journal` | `securite/concorde_securite.py` | Fichier clamscan.log ouvert en lecture |
| `fichier_mapping` | `scripts/export_odoo_online.py` | Fichier de mapping xlsx ouvert en lecture |
| `fichier_source` | `scripts/export_odoo_online.py` | Fichier FEC / xlsx ouvert en lecture |
| `filtre` | `core/migration/filtres.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni |
| `filtre_brut` | `core/migration/filtres.py` | Filtre normalisé / filtre fourni / copie modifiable du filtre fourni |
| `FiltreNormalise` | `core/migration/filtres.py` | Type d'un filtre validé |
| `fin` | `core/migration/injection.py`, `interface/serveur.py`, `tests/test_demat.py` | Résultat et bornes d'un paquet dans `decouper` |
| `fin_lot` | `core/demat.py`, `core/odoo_source.py` | Indice de fin d'une tranche dans `_lots` |
| `fin_page` | `core/comptes.py` | Rang de fin (exclu) de la page du grand livre |
| `fin_periode` | `core/migration/filtres.py` | Bornes `du` / `au` converties |
| `fonction_interne` | `core/moteur.py` | Fonction d'étape interne au moteur (`_<fonction>`) |
| `fonction_module` | `core/moteur.py` | Fonction d'étape résolue dans un module |
| `FonctionSauvegarde` | `core/bases_locales.py` | Protocol de la fonction de sauvegarde injectable |
| `gestionnaire` | `core/marceau.py` | Gestionnaire urllib ajouté à l'ouvreur https |
| `GestionnaireConcorde` | `interface/serveur.py` | Sous-classe de Gestionnaire liée à une application (creer_serveur) |
| `groupe` | `core/xlsx_vers_fec.py` | Lignes Quadra d'un même groupe / d'une même écriture |
| `groupes` | `core/xlsx_vers_fec.py` | Groupes de lignes Quadra par clé de cascade |
| `guardian` | `tests/test_yaml_min.py` | Section noyau.guardian de concorde.yaml |
| `HoteXmlRpc` | `core/odoo_source.py` | Type de l'hôte reçu par `Transport.make_connection` |
| `ident` | `core/demat.py` | Id de partenaire dans la compréhension de `_lire_partenaires` |
| `ident_partenaire` | `core/demat.py` | Id du partenaire commercial d'une facture |
| `identifiant` | `tests/classeurs_xlsx.py` | Identifiant d'une relation (rIdn) |
| `identifiant_cle` | `core/bases_locales.py`, `tests/test_bases_locales.py` | Identifiant entier de la clé API à révoquer |
| `identifiant_modele` | `core/bases_locales.py` | Nom du modèle vierge vérifié, calculé avant toute suppression dans `reinitialiser` |
| `ids_odoo` | `core/migration/injection.py` | Identifiants Odoo d'une lettre (avec None) / retrouvés |
| `ids_trouves` | `core/migration/injection.py` | Identifiants Odoo d'une lettre (avec None) / retrouvés |
| `ignorees` | `interface/serveur.py` | Bases écartées pendant Bases._lister_sql |
| `index` | `tests/classeurs_xlsx.py` | Rang d'une feuille ou d'une colonne |
| `index_attendu` | `tests/test_mapping.py` | Index de colonne attendu |
| `index_champs` | `core/migration/connecteur_fec.py` | {nom de colonne FEC: position} (remplace `idx`) |
| `index_colonne` | `tests/classeurs_xlsx.py` | Paramètre : index de colonne à partir de 0 |
| `infos` | `interface/serveur.py` | Informations d'un contrôle de sécurité |
| `infos_securite` | `interface/serveur.py` | Derniers contrôles de sécurité par nature |
| `infos_version` | `core/demat.py`, `injectors/socle_odoo.py` | Réponse de version() du serveur (même sens que dans `injectors/socle_odoo.py`) |
| `InfosConteneur` | `securite/concorde_securite.py` | Type (image, ports publiés, environnement) d'un conteneur |
| `InfosProcessus` | `securite/concorde_securite.py` | Type (pid, utilisateur, % CPU, durée, nom, arguments, exécutable) |
| `InjecteurOdoo` | `injectors/socle_odoo.py` | Injecteur commun ; sous-classes InjecteurOdoo17 / InjecteurOdoo18 |
| `installer_bouchons_odoo` | `tests/test_assistant_import.py` | Installe tous les modules odoo simulés |
| `instant` | `interface/auth.py` | Horodatage d'un échec de connexion |
| `instant_cache` | `interface/serveur.py` | Instant de la dernière lecture des bases SQL |
| `Instantane` | `core/surveillance.py` | TypedDict : photo légère d'une base (écritures, comptes, verrous) |
| `jour` | `tests/test_xlsx_vers_fec.py` | Paramètre : jour d'une ligne Quadra |
| `journal` | `tests/test_xlsx_vers_fec.py` | Paramètre : code journal d'une ligne FEC attendue |
| `journal_canonique` | `core/lettrage.py` | Journal canonique à lettrer (extrait par `extraire_canon`) |
| `journal_desequilibre` | `tests/test_moteur.py` | Journal d'une ligne orpheline (refus attendu) |
| `JOURNAL_ESSAI` | `tests/test_xlsx_vers_fec.py` | Journal des lignes Quadra d'essai (VE) |
| `journal_lib` | `tests/test_xlsx_vers_fec.py` | Paramètre : libellé de journal d'une ligne FEC attendue |
| `journal_log` | `tests/test_xlsx_vers_fec.py` | Journal des messages de conversion Quadra |
| `journal_minimal` | `tests/test_moteur.py` | Journal canonique lu depuis `FEC_MINIMAL` |
| `journal_vente` | `tests/test_mapping.py` | Routine : canonique 411/706/445 de test |
| `journaux` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `lecteur` | `tests/test_xml_sur.py` | Racine lue ; lecteur de réponses XML-RPC |
| `lecteur_reponse_xmlrpc` | `core/xml_sur.py` | Fabrique du lecteur de réponses XML-RPC (protégé) |
| `lecteur_valeur` | `tests/test_mapping.py` | Lecteur de valeur de cellule testé |
| `lecteurs` | `core/passerelle.py` | {objet: fonction de lecture de la source} |
| `LecteurValeur` | `core/mapping.py` | Type du lecteur de valeur d'une cellule rendu par `lire_feuille_xlsx` |
| `lettre_colonne` | `tests/classeurs_xlsx.py` | Routine : index de colonne -> lettres Excel |
| `lettres` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py` | Lettres d'une colonne Excel |
| `libelle` | `core/migration/filtres.py`, `core/odoo_source.py` | Code ou nom d'un compte analytique (dans `analytique_comptes`) |
| `libelle_ligne` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Libellé d'une ligne d'écriture Odoo (200 caractères au plus) |
| `libelle_mapping` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Libellé du mapping connu au moment de l'échec |
| `libelle_version` | `injectors/socle_odoo.py` | Mot du message d'avertissement de version (« cible » / « attendue ») |
| `libelles_totaux` | `core/migration/export.py`, `injection.py` | (clé de totaux, libellé) comparés entrée / sortie |
| `ligne` | `core/analyser.py`, `core/comparaison.py`, `core/comptes.py`, `core/migration/*.py`, `core/odoo_source.py`, `core/telecharger.py`, `tests/test_surveillance.py` | Ligne d'écriture (ex-`l`) |
| `ligne_base` | `tests/test_comparaison.py` | Ligne de la base de test parcourue/modifiée dans un test |
| `ligne_canon` | `tests/test_moteur.py` | Ligne de journal canonique parcourue |
| `ligne_canonique` | `tests/test_mapping.py` | Routine : LigneEcriture de test |
| `ligne_construite` | `tests/test_comparaison.py` | Ligne d'écriture en cours de construction dans `ligne` |
| `ligne_credit` | `core/lettrage.py` | Ligne au crédit candidate à l'appariement (ex-`lc`) |
| `ligne_debit` | `core/lettrage.py` | Ligne au débit en cours d'appariement (ex-`ld`) |
| `ligne_ecriture` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Ligne d'écriture canonique (LigneEcriture) parcourue |
| `ligne_fec` | `core/telecharger.py`, `tests/test_migration.py` | Texte d'une ligne du FEC (ex-`ligne`) |
| `ligne_fec_attendue` | `tests/test_xlsx_vers_fec.py` | Routine : ligne FEC attendue (oracle indépendant) |
| `ligne_lot` | `tests/test_injection.py` | Ligne du lot parcourue pour construire les rangs relus |
| `ligne_lue` | `tests/test_odoo_donnees.py` | Ligne de texte du FEC relu dans `TestFec.lire` (remplace `l`) |
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
| `lignes` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py`, `tests/test_plan_comptable.py`, `tests/test_xlsx_vers_fec.py` | Lignes d'une feuille ou d'un document de test |
| `lignes_classeur` | `tests/test_xlsx_vers_fec.py` | Lignes écrites dans le classeur de test |
| `lignes_client` | `tests/test_mapping.py` | Lignes du fichier de mapping client |
| `lignes_fec` | `core/xlsx_vers_fec.py` | Lignes FEC produites avant encodage |
| `lignes_filtrables` | `tests/test_comparaison.py` | Lignes de test avec comptes analytiques, passées à `filtrer_lignes` (ex-`L`) |
| `lignes_lues` | `tests/test_xlsx_vers_fec.py` | Lignes rendues par `_lire_xlsx_stdlib` |
| `lignes_par_tiers` | `core/migration/lot.py` | Routine partagée : nombre de lignes par référence de tiers |
| `lignes_relues` | `core/migration/export.py` | Lignes d'une écriture du FEC relu (remplace `ls`) |
| `lignes_titre` | `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Lignes de titre avant l'en-tête |
| `lignes_yaml` | `tests/test_yaml_min.py` | Paramètre : lignes du document YAML |
| `LigneSortie` | `core/migration/export.py` | Type d'une ligne au format de core/telecharger |
| `LigneXlsx` | `core/xlsx_vers_fec.py` | Type : ligne de cellules du classeur (None toléré) |
| `LIMITE_CODES_AFFICHES` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Nombre maximal de codes de comptes cités (30) |
| `lire_feuille` | `tests/test_xlsx_vers_fec.py` | Méthode : lit une feuille faite de lignes <row> |
| `lire_feuille_deplacee` | `tests/test_xlsx_vers_fec.py` | Méthode : lit un classeur dont la feuille est rangée ailleurs |
| `lire_lignes` | `tests/test_yaml_min.py` | Routine : assemble des lignes YAML et les lit |
| `lire_plan` | `tests/test_plan_comptable.py` | Routine : construit puis lit un plan comptable |
| `lire_xml` | `core/xml_sur.py` | Routine : lecture XML sûre (defusedxml) |
| `liste` | `interface/serveur.py` | Liste reçue (comptes ou analytiques) |
| `longueur_suffixe` | `core/bases_locales.py` | Longueur du suffixe « _modele » retiré du nom du modèle |
| `maillon` | `core/guardian.py` | Maillon parcouru lors de la vérification de la chaîne |
| `MaillonAudit` | `core/guardian.py` | TypedDict d'un maillon de la chaîne d'audit (charge, empreinte) |
| `mapping_enchaine` | `tests/test_mapping.py` | Mapping de test aux correspondances enchaînées |
| `mapping_lu` | `tests/test_mapping.py` | Mapping rendu par la fonction testée |
| `mapping_simule` | `tests/test_assistant_import.py` | Configuration de mapping simulée (intitulés) |
| `MAPPING_VENTE` | `tests/test_mapping.py` | Mapping complet du journal de vente de test |
| `marquer_coupure` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Paramètre de _codes_html : ajoute « … » si la liste est coupée |
| `message` | `tests/test_mapping.py`, `tests/test_plan_comptable.py` | Message d'erreur obtenu |
| `message_attendu` | `tests/test_xlsx_vers_fec.py` | Message d'erreur attendu |
| `message_erreur` | `tests/test_xlsx_vers_fec.py` | Routine : lance une conversion qui doit échouer, rend son message |
| `message_obtenu` | `tests/test_xlsx_vers_fec.py` | Message d'erreur obtenu |
| `methode` | `injectors/socle_odoo.py` | Méthode ORM appelée (ex. search_read) |
| `modele` | `injectors/socle_odoo.py` | Modèle Odoo appelé (ex. account.move) |
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
| `montant_devise` | `core/migration/connecteur_fec.py` | Montantdevise en centimes ou None |
| `montant_max` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `montant_min` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `nature` | `securite/concorde_securite.py` | Résultat de `classer_connexion` |
| `niveau_cascade` | `core/xlsx_vers_fec.py` | Clé de LigneQuadra : cascade qui a rattaché la ligne (0 = aucune) |
| `nom` | `tests/test_interface.py` | Paramètre de `entete_obligatoire` : nom de l'en-tête |
| `nom_base` | `core/bases_locales.py`, `core/migration/injection.py`, `interface/serveur.py` | Paramètre de `_identifiant_sql` : nom de base ou de modèle |
| `nom_champ` | `tests/test_assistant_import.py` | Paramètre : nom du champ lu sur la pièce jointe simulée |
| `nom_conforme` | `core/bases_locales.py` | Résultat de la vérification du nom dans `_identifiant_sql` |
| `NOM_FICHIER_ESSAI` | `tests/test_xlsx_vers_fec.py` | Nom de fichier des essais (essai.xlsx) |
| `nom_minuscule` | `core/migration/correspondance.py` | Nom de la table en minuscules (remplace `n`) |
| `nom_module` | `tests/test_assistant_import.py` | Paramètre : nom pointé du module simulé |
| `nombre` | `core/journal.py` | Paramètre de `nombre_texte` (ex-`n`) : nombre à formater |
| `nombre_anomalies` | `interface/serveur.py` | Anomalies BLOQUANT/ALERTE d'une balance |
| `nombres` | `tests/test_surveillance.py` | Nombre de cas par code d'alerte |
| `noms_etapes` | `tests/test_yaml_min.py` | Noms des étapes du pipeline |
| `noms_feuilles` | `tests/classeurs_xlsx.py` | Paramètre : noms des feuilles du classeur |
| `nouvelle` | `core/bases_locales.py`, `interface/serveur.py` | Connexion ouverte par `_connexion_ou_nouvelle` |
| `numero` | `interface/serveur.py` | Numéro d'un fichier produit dans une tâche |
| `numero_ligne` | `tests/classeurs_xlsx.py` | Numéro de ligne Excel (à partir de 1) |
| `numuniq` | `tests/test_xlsx_vers_fec.py` | Paramètre : numéro unique Quadra d'une ligne |
| `objet_fil` | `core/migration/injection.py` | Client « object » du fil courant |
| `ObjetJson` | `interface/serveur.py` | Alias dict[str, Any] : objet JSON dynamique (tâche, base, constat, corps de requête) |
| `objets_demandes` | `core/passerelle.py` | Ensemble des objets demandés (ex-réaffectation de `objets`) |
| `obligatoires` | `core/xlsx_vers_fec.py` | Paramètre de `_trouver_entete` : champs qui doivent tous être reconnus |
| `OCTETS_DEBUT_ZIP` | `tests/test_assistant_import.py` | En-tête d'un fichier zip (.xlsx), attendu après décodage |
| `octets_fichier` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Octets du fichier rendus par _lire_binaire |
| `operations` | `core/migration/filtres.py` | {opérateur: test} d'une condition libre |
| `options` | `injectors/socle_odoo.py` | Arguments nommés de la méthode ORM (omis si None) |
| `options_clamscan` | `securite/concorde_securite.py` | Options de la ligne de commande clamscan |
| `outils_cli` | `scripts/outils_cli.py` | Module des routines communes aux scripts en ligne de commande |
| `ouvreur` | `core/marceau.py` | OpenerDirector construit par `_ouvreur_https` |
| `PaireLettrage` | `core/lettrage.py` | TypedDict d'une paire lettrée (code, compte, montant, ligne_debit, ligne_credit) |
| `paquet_ids` | `core/migration/injection.py` | Paquet de références / d'identifiants lus ou envoyés |
| `paquet_refs` | `core/migration/injection.py` | Paquet de références / d'identifiants lus ou envoyés |
| `paquets` | `core/migration/injection.py` | Résultat et bornes d'un paquet dans `decouper` |
| `parametres` | `core/bases_locales.py`, `injectors/socle_odoo.py`, `interface/serveur.py`, `tests/test_bases_locales.py` | Paramètre : valeurs SQL de `CurseurPg.execute` |
| `ParametresUrl` | `interface/serveur.py` | Alias dict[str, str] : paramètres d'URL, dernière valeur gardée |
| `partages` | `tests/test_mapping.py` | Paramètre : textes de sharedStrings |
| `partie` | `tests/test_xlsx_vers_fec.py` | Partie du classeur de test |
| `parties` | `tests/classeurs_xlsx.py`, `tests/test_mapping.py`, `tests/test_xlsx_vers_fec.py` | Parties {chemin: xml} d'une archive |
| `PayloadOdoo` | `injectors/socle_odoo.py` | Type du payload account.move envoyé par `create` |
| `PayloadVersion` | `injectors/odoo_conversion.py` | Type du payload account.move d'une version cible |
| `pdf_inspectes` | `core/demat.py` | Nombre maximal de PDF inspectés (plafond max_pdf) |
| `periode` | `tests/test_xlsx_vers_fec.py` | Paramètre : période d'une ligne Quadra |
| `PERIODE_ESSAI` | `tests/test_xlsx_vers_fec.py` | Période des lignes Quadra d'essai |
| `piece` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `piece_creee` | `tests/test_assistant_import.py` | Pièce jointe créée par l'export (None si aucune) |
| `PieceJointeSimulee` | `tests/test_assistant_import.py` | ir.attachment simulé : valeurs reçues à la création |
| `pieces_jointes` | `tests/test_assistant_import.py` | Modèle ir.attachment simulé du test d'export |
| `pipeline` | `tests/test_yaml_min.py` | Liste pipeline de concorde.yaml |
| `PlanComptes` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Type du plan comptable uploadé {code: (intitulé, type ou None)} |
| `portee` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `portes` | `core/migration/circuit.py` | Raccourci vers `rapport["portes"]` |
| `prefixe` | `interface/serveur.py` | Préfixe « base — » des lignes de journal |
| `prefixer_ref` | `injectors/socle_odoo.py` | Vrai : référence « CONCORDE/<journal>/<numéro> » ; faux : numéro seul |
| `prefixes_prives` | `securite/concorde_securite.py` | Débuts d'adresses privées exclus du contrôle des ports de minage |
| `PREFIXES_SURS` | `scripts/outils_cli.py` | Débuts d'URL où la clé API ne circule pas en clair |
| `PREFIXES_TEMP` | `securite/concorde_securite.py` | Dossiers temporaires suivis de « / » (test de préfixe) |
| `premiere_ligne` | `scripts/outils_cli.py` | Première ligne d'un texte (description argparse depuis `__doc__`) |
| `Preparation` | `core/migration/injection.py` | Type du bilan de `preparer` |
| `produit` | `interface/serveur.py` | Fichier ou format produit par une tâche |
| `ProxyCommun` | `core/migration/injection.py` | Protocoles des services XML-RPC « common » et « object » |
| `ProxyObjet` | `core/migration/injection.py` | Protocoles des services XML-RPC « common » et « object » |
| `ProxyXmlRpc` | `core/xml_sur.py` | Client XML-RPC (ServerProxy) protégé par defusedxml |
| `PSQL_CONCORDE` | `scripts/install_module.sh` | Commande psql (tableau bash) sur la base concorde, arrêt à la première erreur |
| `racine` | `tests/test_xml_sur.py` | Racine lue ; lecteur de réponses XML-RPC |
| `RACINE_DEPOT` | `tests/outils.py` | Dossier racine du dépôt |
| `rang` | `tests/test_moteur.py` | Paramètre : rang de l'étape dans le pipeline |
| `rang_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Paramètre de _bilan_etape : rang de l'étape (2 mapping, 4 rapport) |
| `rangees` | `core/export_odoo.py` | Lignes de valeurs à écrire dans un CSV d'export |
| `RangRelu` | `tests/test_injection.py` | Alias : rang SQL relu dans la base de test |
| `rapport` | `tests/test_odoo_donnees.py` | Rapport d'analyse en dict dans `TestAnalyse.analyse` |
| `rapport_auto` | `tests/test_rapport_jour.py` | Rapport automatique du jour rendu par `construire` |
| `rapport_balance` | `interface/serveur.py` | Rapport d'alertes de la balance |
| `rapport_controle` | `deploy/addons/concorde/models/concorde_demat.py` | Rapport (dict) du contrôle de dématérialisation |
| `rapport_demat` | `tests/test_demat.py` | Rapport du contrôle de dématérialisation (dict) |
| `RapportCircuit` | `core/migration/circuit.py` | Type du rapport du lot (rapport.json) |
| `RapportCircuitInitial` | `core/migration/circuit.py` | Partie du rapport du lot présente dès le début |
| `RapportConversion` | `injectors/odoo_conversion.py` | Type du rapport de `convertir_chainee` |
| `RapportFec` | `core/telecharger.py` | TypedDict : résultat de `generer_fec` |
| `RapportInjection` | `injectors/socle_odoo.py` | Type du rapport rendu par `InjecteurOdoo.injecter` |
| `reference` | `tests/classeurs_xlsx.py`, `tests/test_xlsx_vers_fec.py` | Référence de cellule (ex. B3) |
| `Regle` | `core/comptes.py` | Type : règle d'alerte (code, niveau, condition, message) |
| `regles` | `tests/test_yaml_min.py` | Section regles de concorde.yaml |
| `regrouper_ecritures` | `injectors/socle_odoo.py` | Regroupe les lignes canoniques par écriture, équilibre vérifié |
| `relations` | `tests/classeurs_xlsx.py` | Éléments <Relationship> |
| `relations_absolues` | `tests/test_xlsx_vers_fec.py` | Relations à cible absolue |
| `relations_autres` | `tests/test_xlsx_vers_fec.py` | Relations ne visant pas la feuille |
| `RELATIONS_CLASSEUR` | `tests/test_xlsx_vers_fec.py` | Relations du classeur vers la feuille |
| `relations_classeur_xml` | `tests/classeurs_xlsx.py` | Routine : workbook.xml.rels à partir de {id: cible} |
| `RELATIONS_RACINE` | `tests/test_xlsx_vers_fec.py` | _rels/.rels vers xl/workbook.xml |
| `relations_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de workbook.xml.rels |
| `remplacement` | `tests/test_xlsx_vers_fec.py` | Remplacement simulé (mock) |
| `reponse` | `tests/test_interface.py` | Paramètre de `entete_obligatoire` : réponse HTTP reçue |
| `requete` | `core/bases_locales.py`, `interface/serveur.py`, `tests/test_bases_locales.py` | Paramètre : ordre SQL de `CurseurPg.execute` |
| `resolue` | `interface/serveur.py` | Libellé « alerte résolue » |
| `restantes` | `core/xlsx_vers_fec.py` | Lignes Quadra des groupes non soldés après une cascade |
| `reste` | `tests/classeurs_xlsx.py` | Reste de la conversion en lettres de colonne |
| `resultat` | `interface/serveur.py` | Résultat d'une comparaison |
| `resultat_etape` | `deploy/addons/concorde/wizard/concorde_import_wizard.py`, `tests/test_moteur.py` | Rend le résultat d'une étape du pipeline, type vérifié |
| `ResultatEnvoi` | `core/migration/injection.py` | Type du résultat de `envoyer` |
| `ResultatEtape` | `core/moteur.py` | TypedDict d'une étape exécutée (etape, resultat, marceau) |
| `ResultatFiltres` | `core/migration/filtres.py` | Type du rapport de `filtres.appliquer` |
| `ResultatLettrage` | `core/migration/injection.py` | Type du bilan de `lettrer` |
| `ResultatLettrageCommun` | `core/migration/injection.py` | Partie toujours présente du bilan du lettrage |
| `resultats` | `core/moteur.py` | Liste des étapes exécutées par `executer` |
| `ResultatTraitement` | `core/migration/injection.py` | Variables de type de `en_parallele` / `decouper` |
| `resume` | `interface/serveur.py` | Résumé du centre d'alertes |
| `ResumeEcriture` | `core/analyser.py` | TypedDict : résumé d'une écriture pendant l'analyse |
| `retrait` | `core/migration/filtres.py`, `interface/serveur.py` | Bilan du filtre en cours (remplace `t`) |
| `RetraitFiltre` | `core/migration/filtres.py` | Type du bilan d'un filtre |
| `sans_openpyxl` | `tests/test_xlsx_vers_fec.py` | Routine : simule l'absence d'openpyxl |
| `sauf_comptes` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `SauvegardeListee` | `core/bases_locales.py` | TypedDict d'une sauvegarde listée (fichier, taille, date, base) |
| `ScalaireYaml` | `core/yaml_min.py` | Type d'un scalaire YAML (str, int, bool) |
| `section` | `tests/test_yaml_min.py` | Routine : sous-table YAML vérifiée |
| `securite` | `interface/serveur.py` | Constats ou fichiers de sécurité |
| `session` | `interface/auth.py` | (création, dernière activité) d'une session |
| `signature` | `core/migration/controles.py` | Signature de la ligne courante (remplace `k`) |
| `SIGNATURE_OLE2` | `tests/test_xlsx_vers_fec.py` | Signature d'un vieux .xls |
| `SignatureComparaison` | `core/comparaison.py` | Signature comparable d'une ligne (avec ou sans analytique) |
| `SignatureLigne` | `core/migration/controles.py` | Type de la signature d'une ligne pour la détection des doublons |
| `signatures` | `core/comparaison.py` | Paramètre de `_lignes_seulement` : signatures à décrire |
| `societe` | `core/odoo_source.py` | Enregistrement XML-RPC brut de la société (`_lire_societe`) |
| `socle_odoo` | `injectors/socle_odoo.py` | Module commun des injecteurs Odoo 17/18 et du convertisseur (regroupement, connexion XML-RPC, injecteur) |
| `source` | `tests/test_mapping.py` | Source de mapping testée |
| `source_a` | `interface/serveur.py` | Source de la base A (comparaison) |
| `source_b` | `interface/serveur.py` | Source de la base B (comparaison) |
| `source_entiere` | `tests/test_mapping.py` | Source de mapping d'un type non supporté |
| `SourceDemat` | `core/demat.py` | Protocole : interface de lecture du contrôle (champs, lire, modules_installes) |
| `SourceLot` | `core/migration/lot.py` | Type de la description de la source lue (type, nom, empreinte, encodage…) |
| `SourceMapping` | `core/mapping.py` | Type des sources de mapping acceptées (JSON, chemin, dict, paires) |
| `SourceOdoo` | `core/odoo_source.py`, `interface/serveur.py`, `scripts/concorde_odoo.py` | Protocol : interface commune des sources SQL et XML-RPC |
| `sous_table` | `tests/test_yaml_min.py` | Sous-table extraite |
| `spec_assistant` | `tests/test_assistant_import.py` | Spécification d'import de l'assistant |
| `spec_module` | `tests/test_xlsx_vers_fec.py` | Spécification d'import de core.xlsx_vers_fec |
| `StatsLettrage` | `core/lettrage.py` | TypedDict des statistiques du lettrage |
| `StatutPorte` | `core/migration/circuit.py` | Partie toujours présente de l'état d'une porte |
| `style_cellule` | `core/xlsx_vers_fec.py` | Indice de style (attribut s) d'une cellule xlsx |
| `STYLE_NORMAL` | `tests/test_xlsx_vers_fec.py` | Style nommé Normal exigé par openpyxl |
| `STYLES_AVEC_STYLE_NOMME` | `tests/test_xlsx_vers_fec.py` | styles.xml : un style nommé avant cellXfs, style 1 = date |
| `styles_cellules` | `core/xlsx_vers_fec.py` | Élément cellXfs : styles indexés par l'attribut s des cellules |
| `STYLES_FORMATS_PERSONNALISES` | `tests/test_xlsx_vers_fec.py` | Styles : formats date 164 et texte littéral 165 |
| `STYLES_PAR_DEFAUT` | `tests/test_xlsx_vers_fec.py` | Police, remplissage, bordure par défaut (openpyxl) |
| `styles_presents` | `tests/test_xlsx_vers_fec.py` | Vrai si le classeur de test a des styles |
| `STYLES_SANS_CELLXFS` | `tests/test_xlsx_vers_fec.py` | Styles sans liste cellXfs |
| `styles_xml` | `tests/test_xlsx_vers_fec.py` | Paramètre : contenu de xl/styles.xml |
| `supprimee` | `interface/serveur.py` | Vrai si la tâche supprime la base (sinon réinitialise) |
| `TABLE_PJ_PRESENTE` | `scripts/install_module.sh` | « t » si la table ir_attachment existe (sinon base neuve) |
| `tache` | `interface/serveur.py` | Fiche d'une tâche |
| `taille` | `interface/serveur.py` | Taille du corps de requête ou d'un fichier |
| `tampon` | `interface/serveur.py` | Tampon mémoire (zip, CSV) |
| `tampon_classeur` | `tests/test_xlsx_vers_fec.py` | Tampon mémoire du classeur construit |
| `tampon_zip` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Tampon mémoire du zip d'export |
| `techniques` | `interface/serveur.py` | Rapport des contrôles techniques |
| `temporaire` | `interface/serveur.py` | Chemin du fichier .tmp d'une écriture atomique |
| `TestCentimes` | `tests/test_xlsx_vers_fec.py` | Tests des montants en centimes |
| `TestChargementFichier` | `tests/test_yaml_min.py` | Tests de chargement d'un fichier YAML |
| `TestChargerMappingJson` | `tests/test_mapping.py` | Tests de charger_mapping (JSON) |
| `TestChargerMappingXlsx` | `tests/test_mapping.py` | Tests du classeur Mapping Quadra Odoo |
| `TestCompteTexte` | `tests/test_mapping.py` | Tests de _compte_txt |
| `TestConversionQuadra` | `tests/test_xlsx_vers_fec.py` | Tests de conversion d'un export Quadra |
| `TestConversionStandard` | `tests/test_xlsx_vers_fec.py` | Tests de conversion d'un classeur standard |
| `TestDateFec` | `tests/test_xlsx_vers_fec.py` | Tests de _date_fec |
| `TestDateQuadra` | `tests/test_xlsx_vers_fec.py` | Tests de _date_quadra |
| `TestDictionnairePlan` | `tests/test_plan_comptable.py` | Tests de dictionnaire_plan |
| `TestEntete` | `tests/test_xlsx_vers_fec.py` | Tests de détection de l'en-tête |
| `TestErreursPlan` | `tests/test_plan_comptable.py` | Tests des refus du plan comptable |
| `TestExporter` | `tests/test_assistant_import.py` | Tests de `action_exporter` |
| `TestIndexColonne` | `tests/test_mapping.py` | Tests de _index_colonne |
| `TestLectureOpenpyxl` | `tests/test_xlsx_vers_fec.py` | Tests de lecture par openpyxl |
| `TestLecturePlan` | `tests/test_plan_comptable.py` | Tests de lecture du plan comptable |
| `TestLectureStdlib` | `tests/test_xlsx_vers_fec.py` | Tests du lecteur xlsx interne |
| `TestLectureXmlSure` | `tests/test_xml_sur.py` | Tests de la lecture XML protégée |
| `TestLireFeuilleXlsx` | `tests/test_mapping.py` | Tests d'ouverture et de lecture des cellules |
| `TestMapperComptes` | `tests/test_mapping.py` | Tests de mapper_comptes |
| `TestNormalisation` | `tests/test_xlsx_vers_fec.py` | Tests de mise en forme des textes et montants |
| `TestNormalisationEntete` | `tests/test_mapping.py` | Tests de _norm_entete |
| `TestScalaires` | `tests/test_yaml_min.py` | Tests des valeurs YAML simples |
| `TestStructure` | `tests/test_yaml_min.py` | Tests de structure YAML (imbrication, listes) |
| `TestStylesDate` | `tests/test_xlsx_vers_fec.py` | Tests des styles date de la lecture xlsx sans openpyxl |
| `TestTypesComptes` | `tests/test_plan_comptable.py` | Tests de déduction du type Odoo |
| `TestVraieConfiguration` | `tests/test_yaml_min.py` | Tests du vrai concorde.yaml |
| `texte` | `core/migration/connecteur_fec.py`, `interface/serveur.py` | Paramètre de `_date` (remplace `v`) |
| `textes` | `tests/test_mapping.py` | Textes d'une ligne de test |
| `tiers` | `core/migration/filtres.py` | Critères du filtre en cours de normalisation |
| `tirage` | `samples/generateur_fec_test.py` | Générateur pseudo-aléatoire local à graine fixe (2026) |
| `totaux` | `core/migration/lot.py`, `controles.py`, `connecteur_fec.py` | Totaux d'un lot (remplace `t`) |
| `TotauxLot` | `core/migration/lot.py` | Type des totaux d'un lot (lignes, écritures, débit, crédit) |
| `trace` | `tests/outils.py` | Paramètres de `CurseurSimule.__exit__` |
| `traduction` | `core/odoo_source.py` | Traduction retenue d'un texte Odoo (jsonb) |
| `transport_xmlrpc` | `core/odoo_source.py` | Routine partagée : transport XML-RPC HTTP/HTTPS avec délai d'attente |
| `TransportXmlRpc` | `core/xml_sur.py` | Transport XML-RPC HTTP |
| `TransportXmlRpcSur` | `core/xml_sur.py` | Transport XML-RPC HTTPS |
| `type_attendu` | `tests/test_moteur.py` | Paramètre : type que l'étape doit avoir produit |
| `type_cellule` | `tests/classeurs_xlsx.py` | Paramètre : attribut t d'une cellule |
| `type_champ` | `tests/test_assistant_import.py` | Élément de `TYPES_CHAMPS_ODOO` |
| `TYPE_CONTENU_TABLEUR` | `tests/test_xlsx_vers_fec.py` | Préfixe des types MIME officedocument |
| `type_erreur` | `tests/test_xlsx_vers_fec.py` | Paramètre : type d'erreur attendu |
| `type_exception` | `tests/outils.py` | Paramètres de `CurseurSimule.__exit__` |
| `type_ligne` | `tests/test_xlsx_vers_fec.py` | Paramètre : TypeLigne d'une ligne Quadra |
| `type_lu` | `tests/test_plan_comptable.py` | Routine : type Odoo déduit d'un type texte |
| `type_odoo` | `tests/test_plan_comptable.py` | Type Odoo attendu |
| `type_partie` | `tests/test_xlsx_vers_fec.py` | Type de contenu d'une partie |
| `type_texte` | `tests/test_plan_comptable.py` | Type de compte écrit par le client |
| `TypeResultat` | `tests/test_moteur.py` | Variable de type : type attendu du résultat d'une étape |
| `TYPES_CHAMPS_ODOO` | `tests/test_assistant_import.py` | Types de champs Odoo simulés par `champ_bouchon` |
| `types_contenu` | `tests/test_xlsx_vers_fec.py` | Routine : [Content_Types].xml du classeur de test |
| `valeur` | `core/migration/circuit.py`, `filtres.py` | Paramètre de `_vers_json` / des routines de normalisation |
| `valeur_champ` | `core/migration/connecteur_fec.py` | Fonction : valeur nettoyée d'une colonne (remplace `val`) ; dans `filtres._condition` : valeur brute du champ testé |
| `valeur_entete` | `tests/test_interface.py` | Valeur lue de l'en-tête dans `entete_obligatoire` |
| `valeur_lue` | `tests/test_yaml_min.py` | Valeur lue par parse_yaml |
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
| `variable_docker` | `interface/serveur.py` | Nom de variable POSTGRES_* (docker) |
| `variable_pg` | `interface/serveur.py` | Nom de variable PG* (libpq) |
| `verifier_refus` | `tests/test_plan_comptable.py` | Routine : refus avec le nom du fichier et la cause |
| `version` | `core/odoo_source.py` | Version du module base lue en SQL (`_version`) |
| `version_attendue` | `injectors/socle_odoo.py` | Préfixe de version Odoo attendu (ex. « 17 ») |
| `version_odoo` | `interface/serveur.py` | Réponse version() d'Odoo (XML-RPC) |
| `version_texte_odoo` | `deploy/addons/concorde/wizard/concorde_import_wizard.py` | Texte de version d'Odoo (odoo.release.version), repli de _version_majeure_odoo |
| `XML_PIEGE` | `tests/test_xml_sur.py` | Document XML ordinaire / bombe d'entités |
| `XML_SAIN` | `tests/test_xml_sur.py` | Document XML ordinaire / bombe d'entités |
