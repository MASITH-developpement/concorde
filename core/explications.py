# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Catalogue des explications de Marceau.

Pour chaque alerte : POURQUOI et QUOI FAIRE.

100 % déterministe : ces textes ne passent jamais par une IA externe, quelle
que soit la configuration de Marceau (aucune donnée comptable ne sort du
serveur).
Un code absent du catalogue reçoit quand même une explication générique :
Marceau n'est jamais muet.
"""

# Code d'alerte -> (titre, pourquoi, que faire).
CATALOGUE: dict[str, tuple[str, str, str]] = {
    # --- Analyse des écritures -----------------------------------------------
    "ECRITURE_DESEQUILIBREE": (
        "Écriture déséquilibrée",
        "Une écriture doit avoir autant au débit qu'au crédit, au centime "
        "près. Un écart "
        "fausse la balance, bloque le FEC et signale une donnée corrompue ou "
        "un import raté.",
        "Ouvrir l'écriture dans Odoo, retrouver la ligne manquante ou "
        "erronée, corriger. "
        "Si l'écriture vient d'un import, vérifier le fichier source.",
    ),
    "TOTAL_DESEQUILIBRE": (
        "Total débit ≠ total crédit",
        "La comptabilité entière n'est pas équilibrée : aucun état (balance, "
        "bilan, FEC) "
        "n'est fiable tant que l'écart subsiste.",
        "Traiter d'abord les écritures déséquilibrées listées ; l'écart "
        "total doit "
        "disparaître avec elles.",
    ),
    "LIGNE_SANS_COMPTE": (
        "Ligne sans compte",
        "Une ligne comptable sans compte n'apparaît dans aucun état et ne "
        "peut pas être "
        "exportée.",
        "Affecter un compte à la ligne dans Odoo (ou supprimer la ligne si "
        "elle est vide).",
    ),
    "DATE_FUTURE": (
        "Écritures datées dans le futur",
        "Une date dans plusieurs années est presque toujours une faute de "
        "frappe "
        "(2032 au lieu de 2023). Ces écritures faussent les échéances et "
        "sortiront dans "
        "le mauvais exercice.",
        "Vérifier la date de chaque écriture listée et la corriger dans Odoo.",
    ),
    "ECRITURE_UNE_LIGNE": (
        "Écriture d'une seule ligne",
        "Une écriture comptable a toujours au moins deux lignes (partie "
        "double). Une ligne "
        "seule est soit à zéro, soit déséquilibrée.",
        "Compléter la contrepartie ou supprimer l'écriture si elle est vide.",
    ),
    "LIGNE_MONTANT_NUL": (
        "Lignes à montant nul",
        "Sans gravité comptable, mais ces lignes encombrent les états et le "
        "FEC. Elles "
        "viennent souvent de lignes de facture à 0 € ou d'imports.",
        "Rien d'obligatoire. Les nettoyer si elles gênent la lecture.",
    ),
    "TIERS_MANQUANT": (
        "Compte client ou fournisseur sans tiers",
        "Un mouvement sur un compte 411 ou 401 sans tiers n'apparaît dans "
        "aucun compte "
        "auxiliaire : la balance âgée et les relances seront fausses, et le "
        "FEC aura un "
        "compte auxiliaire vide.",
        "Renseigner le tiers sur chaque ligne listée dans Odoo.",
    ),
    "COMPTE_DEPRECIE": (
        "Mouvements sur un compte déprécié",
        "Le compte a été retiré du plan mais reçoit encore des écritures.",
        "Reclasser les lignes vers le compte qui le remplace, ou réactiver "
        "le compte.",
    ),
    "COMPTE_HORS_PLAN": (
        "Compte absent du plan",
        "Des lignes utilisent un compte qui n'existe pas (ou plus) dans le "
        "plan de la "
        "société.",
        "Créer le compte ou reclasser les lignes.",
    ),
    "JOURNAL_INACTIF": (
        "Journal archivé encore utilisé",
        "Le journal est archivé mais porte des écritures sur la période.",
        "Vérifier si ces écritures sont récentes ; réactiver le journal ou "
        "reclasser.",
    ),
    "DOUBLON_PROBABLE": (
        "Doublons probables",
        "Deux écritures du même journal, à la même date, avec la même "
        "référence et le "
        "même montant : souvent une facture saisie ou importée deux fois.",
        "Comparer les écritures de chaque paire ; annuler le doublon s'il "
        "est confirmé.",
    ),
    "BROUILLON_ANCIEN": (
        "Brouillons anciens",
        "Un brouillon n'est pas comptabilisé : il manque dans la balance et "
        "le FEC.",
        "Valider ou supprimer chaque brouillon listé.",
    ),
    "ECRITURE_PLANIFIEE": (
        "Écritures planifiées",
        "Brouillons qu'Odoo comptabilisera tout seul à leur date "
        "(amortissements, "
        "écritures récurrentes). C'est normal.",
        "Rien à faire, sauf si un plan d'amortissement semble faux.",
    ),
    "TIERS_SANS_SIREN_TVA": (
        "Sociétés françaises sans SIREN ni TVA",
        "Depuis la facture électronique, le SIREN du client est une mention "
        "obligatoire. "
        "Sans lui, la facture ne peut pas être transmise par une plateforme "
        "agréée.",
        "Compléter le SIREN (ou la TVA intracommunautaire) sur la fiche de "
        "chaque tiers.",
    ),
    "SIREN_INVALIDE": (
        "SIREN invalides",
        "La clé de contrôle (Luhn) du numéro est fausse : faute de frappe ou "
        "mauvais "
        "champ (TVA ou SIRET saisis à la place).",
        "Corriger le numéro sur la fiche du tiers (annuaire : "
        "annuaire-entreprises.data.gouv.fr).",
    ),
    "TVA_INVALIDE": (
        "TVA intracommunautaires invalides",
        "La clé de la TVA FR ne correspond pas au SIREN : la mention sur "
        "facture est fausse.",
        "Recalculer ou vérifier le numéro (service VIES de la Commission "
        "européenne).",
    ),
    "TIERS_DOUBLON": (
        "Tiers en double",
        "Le même client ou fournisseur existe deux fois : ses soldes et son "
        "historique "
        "sont coupés en deux, le lettrage devient impossible entre les deux "
        "fiches.",
        "Fusionner les fiches dans Odoo (Contacts > sélectionner > Action > "
        "Fusionner).",
    ),
    # --- Balance : anomalies par compte --------------------------------------
    "BALANCE_DESEQUILIBREE": (
        "Balance déséquilibrée",
        "Le total des débits ne vaut pas le total des crédits : la "
        "comptabilité est "
        "incohérente.",
        "Lancer une analyse complète pour trouver les écritures fautives.",
    ),
    "CAISSE_CREDITRICE": (
        "Caisse créditrice",
        "Une caisse ne peut pas avoir moins de 0 € : on ne sort pas "
        "d'espèces qu'on n'a "
        "pas. C'est un indice classique d'omission de recettes en contrôle "
        "fiscal.",
        "Rechercher les encaissements non saisis ou les sorties en double, "
        "jour par jour.",
    ),
    "BANQUE_CREDITRICE": (
        "Banque créditrice",
        "Le compte bancaire est à découvert dans la comptabilité. C'est "
        "possible, mais "
        "c'est souvent un rapprochement bancaire en retard ou un relevé mal "
        "importé.",
        "Comparer avec le relevé bancaire à la même date ; si le découvert "
        "est réel, "
        "il devra être présenté en dettes (519) au bilan.",
    ),
    "CLIENT_CREDITEUR": (
        "Clients créditeurs",
        "Un client qui a un solde en sa faveur : avoir non remboursé, "
        "paiement en double "
        "ou paiement non lettré avec sa facture.",
        "Lettrer paiements et factures du client ; rembourser ou imputer "
        "l'avoir.",
    ),
    "FOURNISSEUR_DEBITEUR": (
        "Fournisseurs débiteurs",
        "Un fournisseur à qui l'on a payé plus que facturé : facture "
        "manquante, paiement "
        "en double ou avoir non saisi.",
        "Réclamer la facture ou l'avoir, ou lettrer les écritures du "
        "fournisseur.",
    ),
    "COMPTE_ATTENTE_NON_SOLDE": (
        "Compte d'attente non soldé",
        "Les comptes 47x (attente) et 58x (virements internes) doivent être "
        "à zéro à la "
        "clôture : un solde signifie des opérations non affectées.",
        "Ouvrir le grand livre du compte, affecter chaque ligne à son vrai "
        "compte.",
    ),
    "CHARGE_CREDITRICE": (
        "Compte de charge créditeur",
        "Une charge (classe 6) a normalement un solde débiteur. Un solde "
        "créditeur "
        "signale souvent un avoir mal imputé ou une écriture inversée.",
        "Vérifier le sens des écritures du compte et l'imputation des avoirs.",
    ),
    "PRODUIT_DEBITEUR": (
        "Compte de produit débiteur",
        "Un produit (classe 7) a normalement un solde créditeur. Un solde "
        "débiteur "
        "signale un avoir client mal imputé ou une écriture inversée.",
        "Vérifier le sens des écritures du compte.",
    ),
    "TVA_DEDUCTIBLE_CREDITRICE": (
        "TVA déductible créditrice",
        "La TVA déductible (4456x) est normalement débitrice : un solde "
        "créditeur "
        "signale une TVA mal imputée ou une régularisation à l'envers.",
        "Contrôler les écritures du compte et les déclarations de TVA.",
    ),
    "TVA_COLLECTEE_DEBITRICE": (
        "TVA collectée débitrice",
        "La TVA collectée (4457x) est normalement créditrice : un solde "
        "débiteur "
        "signale des avoirs mal imputés ou une déclaration passée en double.",
        "Contrôler les écritures du compte et les déclarations de TVA.",
    ),
    "COMPTE_DEPRECIE_SOLDE": (
        "Compte déprécié avec un solde",
        "Un compte retiré du plan garde un solde : ce solde ne sera plus "
        "suivi.",
        "Solder le compte par une écriture de reclassement vers son "
        "remplaçant.",
    ),
    # --- Migration ERP -> Odoo (ADR-0004) ------------------------------------
    "MIG_LIGNE_ILLISIBLE": (
        "Lignes illisibles",
        "CONCORDE n'a pas pu lire ces lignes (colonnes en trop ou en moins, "
        "date ou montant "
        "invalide, plus de 2 décimales). Les ignorer ferait disparaître des "
        "montants.",
        "Corriger l'export dans l'ERP source (souvent un libellé contenant "
        "le séparateur), "
        "puis recharger le fichier.",
    ),
    "MIG_ECRITURE_DESEQUILIBREE": (
        "Écritures déséquilibrées",
        "Odoo refuse toute écriture dont le débit ne vaut pas le crédit au "
        "centime.",
        "Corriger l'écriture dans l'ERP source et réexporter.",
    ),
    "MIG_FICHIER_DESEQUILIBRE": (
        "Fichier déséquilibré",
        "Le total des débits ne vaut pas le total des crédits : il manque "
        "des lignes.",
        "Vérifier que l'export de l'ERP est complet (période, journaux).",
    ),
    "MIG_MONTANT_NUL": (
        "Lignes à montant nul",
        "Ces lignes n'ont aucun effet comptable et font échouer l'import.",
        "Ajouter le filtre « lignes_nulles » : CONCORDE les retire et "
        "vérifie que les "
        "totaux ne bougent pas.",
    ),
    "MIG_DEBIT_ET_CREDIT": (
        "Ligne avec débit et crédit",
        "Une ligne porte soit un débit, soit un crédit. Les deux à la fois "
        "signalent un "
        "export mal formé.",
        "Corriger l'export de l'ERP source.",
    ),
    "MIG_ECRITURE_UNE_LIGNE": (
        "Écritures d'une seule ligne",
        "Une écriture a toujours une contrepartie. Seule, une ligne ne peut "
        "pas être "
        "équilibrée.",
        "Retrouver la contrepartie dans l'ERP, ou retirer l'écriture par un "
        "filtre.",
    ),
    "MIG_COMPTE_INVALIDE": (
        "Compte vide ou « 0 »",
        "Odoo refuse une ligne sans compte valide.",
        "Corriger le compte dans l'ERP source.",
    ),
    "MIG_ECRITURE_DEUX_MOIS": (
        "Écriture à cheval sur deux mois",
        "Dans Odoo, une écriture a une seule date. Des lignes sur deux mois "
        "changeraient "
        "de période.",
        "Faire trancher la date par le comptable, ou couper l'écriture en "
        "deux dans l'ERP.",
    ),
    "MIG_DATE_FUTURE": (
        "Écritures datées dans le futur",
        "Une écriture postérieure à aujourd'hui est souvent une erreur de "
        "saisie ; elle "
        "doit être tranchée avant tout envoi.",
        "Faire valider la date par le comptable, ou la retirer par un filtre.",
    ),
    "MIG_ECRITURE_DEUX_JOURNAUX": (
        "Même numéro dans plusieurs journaux",
        "Souvent normal (numérotation par journal), mais peut cacher une "
        "écriture coupée "
        "en deux.",
        "Vérifier quelques cas ; rien à faire si la numérotation est par "
        "journal.",
    ),
    "MIG_DATES_DIFFERENTES": (
        "Dates différentes dans une écriture",
        "Odoo gardera une seule date (celle de l'écriture) pour toutes les "
        "lignes.",
        "Vérifier que c'est acceptable (même mois, donc même période).",
    ),
    "MIG_LIGNE_DOUBLON": (
        "Lignes en double",
        "Deux lignes strictement identiques : soit c'est voulu (deux "
        "règlements égaux), "
        "soit c'est un doublon d'export.",
        "Faire vérifier par le comptable ; CONCORDE ne supprime jamais un "
        "doublon tout seul.",
    ),
    "MIG_TIERS_MANQUANT": (
        "Lignes client / fournisseur sans tiers",
        "Sans compte auxiliaire, la ligne ne sera rattachée à aucun client "
        "ou fournisseur "
        "dans Odoo : relances et lettrage impossibles.",
        "Compléter le compte auxiliaire dans l'ERP source.",
    ),
    "MIG_LETTRAGE_NON_SOLDE": (
        "Lettrages partiels",
        "Les lignes d'une même lettre ne se soldent pas : c'est un lettrage "
        "partiel. Il "
        "sera repris en rapprochement partiel.",
        "Rien à faire en général ; vérifier si le volume est important.",
    ),
    "MIG_COMPTE_A_ARBITRER": (
        "Comptes à arbitrer",
        "Ces comptes de l'ERP n'ont pas de correspondance dans la table : "
        "CONCORDE ne "
        "devine jamais un compte.",
        "Faire remplir a_arbitrer.xlsx (colonne « Compte Odoo ») par le "
        "comptable, puis "
        "l'ajouter à la table.",
    ),
    "MIG_TABLE_CIBLE_VIDE": (
        "Table incomplète",
        "Des lignes de la table de correspondance n'ont pas de compte Odoo.",
        "Compléter la table.",
    ),
    "MIG_COMPTES_FUSIONNES": (
        "Comptes regroupés",
        "Plusieurs comptes de l'ERP vont sur un même compte Odoo : leur "
        "détail sera fondu.",
        "Vérifier que ce regroupement est voulu.",
    ),
    "MIG_ECART_SORTIE": (
        "Écart entre l'entrée et la sortie",
        "Le fichier produit n'a pas les mêmes totaux que le lot : quelque "
        "chose s'est perdu.",
        "Ne rien envoyer ; signaler l'anomalie (bug de CONCORDE).",
    ),
    "MIG_ILLISIBLE_SORTIE": (
        "FEC produit illisible",
        "CONCORDE ne relit pas son propre export : il serait refusé ailleurs "
        "aussi.",
        "Ne rien envoyer ; signaler l'anomalie.",
    ),
    "MIG_ECART_COMPTE": (
        "Soldes différents",
        "Le solde d'un compte diffère entre l'entrée et la sortie.",
        "Ne rien envoyer ; signaler l'anomalie.",
    ),
    "MIG_ECART_TIERS": (
        "Tiers différents",
        "Des lignes ont changé de tiers ou l'ont perdu entre l'entrée et la "
        "sortie.",
        "Ne rien envoyer ; signaler l'anomalie.",
    ),
    # --- Techniques ----------------------------------------------------------
    "PG_INJOIGNABLE": (
        "Base PostgreSQL injoignable",
        "CONCORDE ne peut plus lire les bases du serveur. Cause fréquente : "
        "le conteneur "
        "concorde-postgres est arrêté ou a changé d'adresse après un "
        "redémarrage.",
        "sudo docker ps (le conteneur tourne-t-il ?) ; sudo docker inspect "
        "concorde-postgres "
        "(adresse) ; ajuster PGHOST dans /etc/concorde/interface.env, puis "
        "redémarrer "
        "concorde-interface.",
    ),
    "ODOO_INJOIGNABLE": (
        "Odoo injoignable",
        "Odoo ne répond pas : les utilisateurs ne peuvent plus travailler et "
        "les envois "
        "par l'API échoueront.",
        "sudo docker ps ; sudo docker logs --tail 50 concorde-odoo.",
    ),
    "DISQUE_PLEIN": (
        "Disque presque plein",
        "Sous 10 % d'espace libre, les exports volumineux et les sauvegardes "
        "risquent "
        "d'échouer ; sous 5 %, la base PostgreSQL elle-même peut s'arrêter.",
        "Supprimer d'anciens résultats (/var/lib/concorde-interface), "
        "d'anciennes "
        "sauvegardes ou images Docker (sudo docker system df).",
    ),
    "TACHE_ECHEC": (
        "Tâches en échec",
        "Une analyse ou un téléchargement n'a pas abouti dans les dernières "
        "24 heures.",
        "Ouvrir la tâche dans l'Historique : le message d'erreur dit "
        "pourquoi.",
    ),
    "CONNEXIONS_REFUSEES": (
        "Tentatives de connexion refusées",
        "Des mots de passe faux ont été saisis sur l'interface. Si ce n'est "
        "pas vous, "
        "quelqu'un essaie d'entrer.",
        "Si ce n'est pas vous : changer le mot de passe "
        "(scripts/concorde_interface_mdp.py) "
        "et envisager une restriction par IP dans Caddy.",
    ),
    # --- Comparaison de deux bases -------------------------------------------
    "CMP_ECART_COMPTE": (
        "Soldes de comptes différents",
        "Sur la période, un même compte n'a pas le même solde dans les deux "
        "bases.",
        "Ouvrir la feuille « Ecarts comptes » du fichier Excel ; l'écart "
        "s'explique par les "
        "écritures différentes ou présentes d'un seul côté.",
    ),
    "CMP_ECART_JOURNAL": (
        "Soldes de journaux différents",
        "Un journal n'a pas les mêmes mouvements dans les deux bases.",
        "Voir la feuille « Ecarts journaux ».",
    ),
    "CMP_ECART_TIERS": (
        "Soldes de tiers différents",
        "Un client ou un fournisseur n'a pas le même solde dans les deux "
        "bases : les "
        "relances et le lettrage seront différents.",
        "Voir la feuille « Ecarts tiers ».",
    ),
    "CMP_ECRITURE_DIFFERENTE": (
        "Écritures différentes",
        "La même écriture (même journal et même numéro) n'a pas le même "
        "contenu : date, "
        "référence, comptes, montants, tiers, libellés ou lettrage.",
        "Le détail de chaque différence est dans la feuille « Ecritures "
        "differentes ».",
    ),
    "CMP_ANALYTIQUE_SEULE": (
        "Seule l'analytique diffère",
        "Comptabilité générale identique, mais la répartition analytique a "
        "changé.",
        "Vérifier que c'est le résultat voulu (correction analytique faite "
        "dans l'une des bases).",
    ),
    "CMP_SEULEMENT_A": (
        "Écritures présentes seulement dans la base A",
        "Ces écritures n'ont pas d'équivalent dans la base B (supprimées, ou "
        "jamais reprises).",
        "Voir la feuille « Seulement A ».",
    ),
    "CMP_SEULEMENT_B": (
        "Écritures présentes seulement dans la base B",
        "Ces écritures n'existent pas dans la base A (créées après coup, ou "
        "importées).",
        "Voir la feuille « Seulement B ».",
    ),
    "CMP_CONFLIT": (
        "Conflits",
        "Ces écritures ont été modifiées dans LES DEUX bases après la date "
        "de copie : "
        "aucune ne peut écraser l'autre sans perdre une correction.",
        "Trancher écriture par écriture avant tout alignement.",
    ),
    "CMP_BASE_DESEQUILIBREE": (
        "Base déséquilibrée",
        "Le total des débits ne vaut pas celui des crédits sur la période.",
        "Analyser la base pour trouver les écritures fautives.",
    ),
    "CMP_ANALYTIQUE_ORPHELINE": (
        "Analytique vers des comptes disparus",
        "Des répartitions pointent vers des comptes analytiques qui "
        "n'existent plus "
        "(affichés « #numéro ») : ces montants ne remontent dans aucun état "
        "analytique.",
        "Réaffecter ces lignes à un compte analytique existant.",
    ),
    # --- Sécurité du serveur (ADR-0007) --------------------------------------
    "SEC_PROCESSUS_TEMP": (
        "Programme lancé depuis un dossier temporaire",
        "Un logiciel légitime ne s'exécute pas depuis /tmp, /var/tmp ou "
        "/dev/shm. C'est la "
        "signature exacte du mineur installé le 01/11/2026 (/tmp/postgresql).",
        "Noter le pid, ne pas redémarrer le serveur ; examiner le processus "
        "(ls -l /proc/<pid>/exe, ss -tnp) puis l'arrêter (kill -9) et "
        "chercher la porte "
        "d'entrée. Voir "
        "/root/quarantaine_mineur_20261106/RAPPORT_INCIDENT.md.",
    ),
    "SEC_EXECUTABLE_EFFACE": (
        "Programme dont le fichier a été effacé",
        "Les logiciels malveillants effacent souvent leur fichier après "
        "lancement pour "
        "échapper à l'antivirus. Peut aussi arriver après une mise à jour.",
        "Vérifier le processus ; s'il est inconnu, le traiter comme un "
        "programme malveillant.",
    ),
    "SEC_MINEUR_CONNU": (
        "Mineur de cryptomonnaie détecté",
        "Un processus porte un nom ou des arguments de mineur (xmrig, "
        "stratum, kinsing…). "
        "Il vole le processeur et signale une intrusion.",
        "Arrêter le processus, puis trouver comment il est arrivé (base "
        "exposée, mot de "
        "passe faible, service vulnérable).",
    ),
    "SEC_PROCESSEUR_SATURE": (
        "Processeur saturé",
        "Un processus occupe presque tout le processeur depuis longtemps : "
        "c'est ainsi que "
        "le mineur a été repéré (186 % pendant 4 jours).",
        "Identifier le processus (ps --sort=-pcpu). S'il est légitime, "
        "l'ajouter à "
        "/etc/concorde/securite.json (processus_gourmands_autorises).",
    ),
    "SEC_CONNEXION_ATTAQUANT": (
        "Connexion vers une adresse d'attaquant connue",
        "Le serveur parle à une adresse de l'attaque du 01/11/2026 : une "
        "nouvelle "
        "compromission est en cours.",
        "Couper la connexion (arrêter le processus), puis rechercher le "
        "point d'entrée.",
    ),
    "SEC_PORT_MINAGE": (
        "Connexion vers un port de minage",
        "Les relais de minage écoutent sur des ports typiques (3333, 4444, "
        "14444, 44999…).",
        "Vérifier le processus à l'origine de la connexion.",
    ),
    "SEC_BASE_EXPOSEE": (
        "Base de données ouverte sur Internet",
        "Docker publie les ports en passant DEVANT le pare-feu UFW. C'est la "
        "porte d'entrée "
        "de l'attaque du 01/11/2026 : des robots la trouvent en moins d'une "
        "heure.",
        "Publier le port sur 127.0.0.1 seulement (-p 127.0.0.1:5432:5432), "
        "puis recréer "
        "le conteneur.",
    ),
    "SEC_PORT_PUBLIC_INCONNU": (
        "Port publié sur Internet non prévu",
        "Un conteneur expose un port à tout Internet, sans passer par le "
        "pare-feu.",
        "Le lier à 127.0.0.1, ou l'ajouter à ports_publics_acceptes s'il "
        "doit être public.",
    ),
    "SEC_PG_SUPERUTILISATEUR": (
        "Super-utilisateur PostgreSQL inconnu",
        "Les robots créent leurs propres super-utilisateurs (« wog », « "
        "priv_esc » le "
        "01/11/2026) pour exécuter des commandes sur le serveur.",
        "Vérifier le compte ; s'il est inconnu : DROP ROLE, changer les mots "
        "de passe, "
        "chercher la porte d'entrée. S'il est légitime, l'ajouter à "
        "superutilisateurs_autorises.",
    ),
    "SEC_PG_BASE_RANCON": (
        "Base de rançon",
        "Une base au nom de type « readme_to_recover » est la signature des "
        "robots "
        "rançonneurs : ils vident les bases et laissent une demande de "
        "rançon.",
        "Ne pas payer. Restaurer depuis une sauvegarde, fermer l'accès, "
        "porter plainte.",
    ),
    "SEC_PG_TABLE_SUSPECTE": (
        "Table suspecte",
        "Une table « readme » contient souvent une note de rançon ; une "
        "table « tests » "
        "ou « cmd_exec » sert aux robots à lire le résultat de leurs "
        "commandes.",
        "Lire son contenu et vérifier qu'elle appartient bien à une "
        "application.",
    ),
    "SEC_PG_SANS_MOT_DE_PASSE": (
        "PostgreSQL accessible sans mot de passe",
        "Une règle « trust » réseau laisse entrer n'importe qui, avec "
        "n'importe quel compte.",
        "Remplacer « trust » par « scram-sha-256 » dans pg_hba.conf et "
        "recharger PostgreSQL.",
    ),
    "SEC_PERSISTANCE": (
        "Mécanisme de persistance",
        "/etc/ld.so.preload sert aux logiciels malveillants à se charger "
        "dans tous les "
        "programmes et à se cacher.",
        "Examiner le contenu ; ne pas redémarrer avant analyse.",
    ),
    "SEC_FICHIER_SENSIBLE_MODIFIE": (
        "Fichiers sensibles modifiés",
        "Tâches planifiées, services système ou clés SSH modifiés depuis 24 "
        "h.",
        "Vérifier que ces changements viennent de vous.",
    ),
    "SEC_FICHIER_RANCON": (
        "Note de rançon ou fichier chiffré",
        "Des fichiers au nom de note de rançon ou chiffrés (.locked, "
        ".encrypted…) sont apparus.",
        "Isoler le serveur, ne rien effacer, vérifier les sauvegardes, "
        "porter plainte.",
    ),
    "SEC_ANTIVIRUS_DETECTION": (
        "Fichier malveillant détecté par l'antivirus",
        "ClamAV (avec les signatures CONCORDE de la campagne du 01/11/2026) "
        "a reconnu un fichier.",
        "Mettre le fichier en quarantaine (chmod 000, copie dans /root), "
        "chercher s'il "
        "tourne (SEC_PROCESSUS_TEMP), puis la porte d'entrée.",
    ),
    "SEC_ANTIVIRUS_ERREUR": (
        "Analyse antivirus incomplète",
        "La nuit dernière, ClamAV n'a pas pu finir son analyse.",
        "Lire /var/lib/concorde-securite/clamscan.log.",
    ),
    "SEC_ANTIVIRUS_PERIME": (
        "Signatures antivirus périmées",
        "Les signatures ClamAV n'ont pas été mises à jour depuis plus de 48 "
        "h : les menaces "
        "récentes ne sont plus reconnues.",
        "systemctl status clamav-freshclam ; journalctl -u clamav-freshclam.",
    ),
    "SEC_SURVEILLANCE_ARRETEE": (
        "Surveillance de sécurité arrêtée",
        "Le contrôle (toutes les 15 min) ou l'antivirus (chaque nuit) n'a "
        "pas tourné à temps.",
        "systemctl list-timers 'concorde-*' ; journalctl -u "
        "concorde-securite -u "
        "concorde-antivirus.",
    ),
    # --- Changements dans Odoo -----------------------------------------------
    "INSTANTANE_INITIAL": (
        "Surveillance des changements démarrée",
        "CONCORDE a pris une première photo de la base ; les prochains "
        "passages diront "
        "ce qui a changé depuis.",
        "Rien à faire.",
    ),
    "ECRITURES_NOUVELLES": (
        "Nouvelles écritures",
        "Des écritures ont été créées depuis le dernier passage.",
        "Rien à faire, sauf si personne n'était censé saisir sur cette base.",
    ),
    "ECRITURES_SUPPRIMEES": (
        "Écritures supprimées",
        "Des écritures ont disparu de la base. Une écriture validée ne "
        "devrait jamais être "
        "supprimée (inaltérabilité de la comptabilité).",
        "Vérifier qui a supprimé et pourquoi (journal d'Odoo) ; ressaisir si "
        "c'est une erreur.",
    ),
    "BROUILLONS_SUPPRIMES": (
        "Brouillons supprimés",
        "Des brouillons ont été supprimés. Un brouillon n'étant pas "
        "comptabilisé, "
        "c'est sans conséquence sur la balance.",
        "Rien à faire, sauf si le brouillon devait être validé.",
    ),
    "ECRITURES_REMISES_BROUILLON": (
        "Écritures validées remises en brouillon",
        "Une écriture validée a été remise en brouillon : elle sort de la "
        "balance et du "
        "FEC tant qu'elle n'est pas revalidée, et elle peut être modifiée.",
        "Vérifier que c'est volontaire, puis s'assurer qu'elle est revalidée.",
    ),
    "ECRITURES_VALIDEES": (
        "Écritures validées",
        "Des brouillons ont été validés depuis le dernier passage.",
        "Rien à faire.",
    ),
    "ECRITURES_MODIFIEES": (
        "Écritures modifiées",
        "Des écritures existantes ont été modifiées (libellé, lettrage, "
        "pièce jointe…).",
        "Rien à faire en général ; à surveiller sur une période clôturée.",
    ),
    "COMPTES_CREES": (
        "Comptes créés",
        "De nouveaux comptes sont apparus dans le plan comptable.",
        "Vérifier qu'ils respectent la nomenclature du plan.",
    ),
    "COMPTES_SUPPRIMES": (
        "Comptes supprimés",
        "Des comptes ont disparu du plan comptable.",
        "Vérifier que ce n'était pas un compte utilisé ou attendu par un "
        "mapping.",
    ),
    "BASE_SUPPRIMEE": (
        "Base locale supprimée",
        "Une base Odoo de ce serveur a été supprimée depuis CONCORDE (après "
        "une sauvegarde "
        "vérifiée pour une copie de base client ; sans sauvegarde pour une "
        "base de test).",
        "Rien à faire. Pour récupérer une copie client : pg_restore de la "
        "sauvegarde "
        "indiquée (gardée 7 jours dans "
        "/var/lib/concorde-interface/sauvegardes).",
    ),
    "BASE_REINITIALISEE": (
        "Base de test réinitialisée",
        "La base de test a été remise à l'état vierge depuis son modèle "
        "(sans sauvegarde : "
        "son contenu est jetable).",
        "Rien à faire.",
    ),
    "CLE_API_REVOQUEE": (
        "Clé API révoquée",
        "Une clé API d'une base Odoo de ce serveur a été supprimée : tout "
        "outil qui s'en "
        "servait est désormais refusé.",
        "Si un outil légitime l'utilisait, créer une nouvelle clé dans Odoo "
        "(Préférences > "
        "Sécurité du compte).",
    ),
    "PERIODE_DEVERROUILLEE": (
        "Période déverrouillée",
        "Une date de verrouillage a reculé : des écritures d'une période "
        "close peuvent de "
        "nouveau être créées ou modifiées. C'est une opération sensible.",
        "Vérifier qui l'a fait et pourquoi ; reverrouiller dès que la "
        "correction est faite.",
    ),
    "VERROU_AVANCE": (
        "Période verrouillée",
        "Une date de verrouillage a avancé : la période close est protégée.",
        "Rien à faire.",
    ),
}


def expliquer(code: str, message: str | None = None) -> dict[str, str]:
    """Rend l'explication d'une alerte, jamais vide.

    Rôle : donner à l'utilisateur le pourquoi et le que faire d'une alerte.
    Paramètres : code, code d'alerte ; message, titre de repli pour un code
    absent du catalogue.
    Retour : {"titre", "pourquoi", "que_faire"} ; explication générique si
    le code est inconnu.
    Erreurs : aucune.
    Usages : marceau, tests.
    """
    if code in CATALOGUE:
        titre, pourquoi, que_faire = CATALOGUE[code]
        return {"titre": titre, "pourquoi": pourquoi, "que_faire": que_faire}
    return {
        "titre": message or code,
        "pourquoi": "Situation relevée par CONCORDE (%s)." % code,
        "que_faire": "Consulter le détail de l'alerte et le journal.",
    }
