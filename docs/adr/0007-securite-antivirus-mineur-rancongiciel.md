# ADR-0007 — Surveillance de sécurité du serveur : ClamAV de nuit, contrôle mineur / rançongiciel toutes les 15 minutes

- **Statut** : Acceptée — demande de Stéphane Moreau du 07/11/2026
- **Date** : 07/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Le 01/11/2026, le PostgreSQL d'AzalPlus V2, ouvert sur Internet sans mot de passe, a été
vidé par un robot rançonneur puis utilisé pour installer un mineur de Monero
(`/tmp/postgresql`, 1,9 cœur sur 2 pendant 4 jours). Découvert seulement le 06/11 en
cherchant pourquoi CONCORDE était lent. Stéphane demande une vérification antivirus
quotidienne par ClamAV, mise à jour chaque jour, et une surveillance spécifique des
mineurs et des rançongiciels.

Mesure faite : **ClamAV seul n'aurait pas vu cette attaque**. Il reconnaît le mineur une
fois décompressé (`PUA.Unix.Coinminer.XMRig`), mais pas les deux fichiers réellement
déposés, compressés avec UPX (dont l'un avec un en-tête modifié contre la décompression).

## Décision
1. **ClamAV** (`clamav`, `clamav-freshclam`) : signatures mises à jour **toutes les heures**
   par `clamav-freshclam` (`Checks 24`). Pas de démon `clamd` (1 Go de mémoire en permanence).
2. **Signatures CONCORDE** (`deploy/clamav/concorde_campagne.{hsb,ndb}`, copiées dans
   `/var/lib/clamav`) : empreintes exactes des deux fichiers de l'attaque et deux chaînes
   propres à la campagne, limitées aux exécutables. Avec elles, les 4 fichiers de la
   quarantaine sont détectés.
3. **Analyse antivirus chaque nuit à 3 h 30** (`concorde-antivirus.timer`) : détection des
   mineurs (« PUA ») activée ; zones : `/tmp`, `/var/tmp`, `/dev/shm`, `/home`, `/root`,
   `/opt`, `/etc`, `/usr/local`, **les couches modifiables des conteneurs Docker**
   (`overlay2/*/diff`) et leurs volumes ; priorité minimale, 60 % d'un processeur et
   1,5 Go de mémoire au plus.
4. **Contrôle ciblé toutes les 15 minutes** (`concorde-securite.timer`, ~4 s) :
   - programmes lancés depuis un dossier temporaire ou dont le fichier a été effacé ;
   - noms et arguments de mineurs ; processus qui saturent le processeur ;
   - connexions vers des ports de minage ou les adresses de l'attaque (hôte et conteneurs) ;
   - PostgreSQL (chaque conteneur) : super-utilisateurs inconnus, bases et tables de rançon,
     accès réseau sans mot de passe ;
   - base de données publiée sur Internet par Docker (qui passe devant UFW) ;
   - persistance (`ld.so.preload`, tâches planifiées, services, clés SSH récentes) ;
   - notes de rançon et fichiers chiffrés récents ; signatures ClamAV de plus de 48 h.
5. **Alertes dans CONCORDE** : l'interface lit `/var/lib/concorde-securite/*.json` à chaque
   passage de surveillance et en fait des alertes « techniques » expliquées par Marceau.
   Une surveillance qui ne tourne plus (contrôle > 1 h, antivirus > 36 h) est elle-même
   une alerte.
6. **Lecture seule** : ces contrôles ne tuent rien et n'effacent rien ; l'action reste humaine.
7. Réglages locaux (comptes et ports acceptés) : `/etc/concorde/securite.json`.

## Conséquences
- Le programme tourne en root (lecture de tous les processus, de Docker et des bases).
- Un nouveau composant, un nouveau compte PostgreSQL ou un port publié volontairement
  produiront une alerte jusqu'à ce qu'on les ajoute aux réglages : c'est voulu.

## Options écartées
- **ClamAV seul** : il n'aurait pas détecté l'attaque du 01/11 (fichiers compressés).
- **Démon clamd et analyse en temps réel** : trop de mémoire pour ce serveur (3,7 Go).
- **Arrêt automatique des processus suspects** : un faux positif couperait un service ;
  l'alerte suffit, la décision reste humaine.
