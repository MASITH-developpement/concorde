# ADR-0014 — Facture électronique : vérifier l'inscription des tiers et reprendre leur adresse dans l'ERP

> Noms et codes neutralisés le 10/11/2026 (données client retirées du dépôt). Décision inchangée.

- **Statut** : Acceptée — arbitrages de Stéphane Moreau du 09/11/2026
- **Date** : 09/11/2026
- **Décideur** : Stéphane Moreau

## Contexte
Demande de Stéphane du 09/11/2026 : savoir si les **clients et fournisseurs** d'une base
ont fait leurs démarches de facture électronique (choix d'une plateforme agréée pour
recevoir), et **reprendre leurs données dans l'ERP du client** pour lui envoyer les
factures au bon endroit.

CONCORDE contrôle déjà la configuration d'Odoo pour la facture électronique
(`core/demat.py` : modules, formats, envois, SIREN et TVA des clients), mais pas
l'inscription de chaque tiers.

Mesures et recherches du 09/11/2026 :
- **L'annuaire officiel** (annuaire de la facturation électronique, tenu par le PPF /
  DGFiP) : son API est **réservée aux plateformes agréées** (certificat délivré par
  l'AIFE). Les guides publiés se contredisent sur une consultation publique, fiche par
  fiche, sur le portail Chorus Pro ; aucune documentation officielle d'une interrogation
  en masse n'a été trouvée.
- **Le répertoire Peppol** (`directory.peppol.eu`, public, gratuit, sans clé) répond
  depuis le serveur et contient **5 764 406 participants français**. Les plateformes y
  publient les adresses de facturation électronique françaises : identifiant `0225`
  (SIREN + code de routage) ou `0002` (SIREN). Recherche par SIREN mesurée :
  `222222226` (société d'exemple) → 3 adresses (`0225:222222226_routage1`, …), avec les
  documents acceptés (facture, avoir) et la date d'inscription.
- **Limite** : être trouvé sur Peppol prouve l'inscription. **Ne pas y être trouvé ne
  prouve pas l'absence d'inscription** (plateforme qui ne publie pas, ou pas encore).

## Décision proposée
### 1. Un contrôle « facture électronique des tiers »
Pour chaque client et fournisseur français d'une base (avec SIREN), CONCORDE
interroge le répertoire Peppol par SIREN (le SIREN seul part, rien d'autre) et classe :
- **inscrit** : au moins une adresse trouvée ; adresses, documents acceptés et date
  d'inscription montrés ;
- **non trouvé** : à vérifier (appel ou courrier au tiers, ou consultation de l'annuaire
  officiel) — jamais présenté comme « pas inscrit » ;
- **sans SIREN** : renvoyé vers « Compléter SIRET et TVA » (ADR-0013).

Résultat dans l'écran (par tiers, filtrable) et en CSV, avec un compte par classe.

### 2. Reprendre l'adresse dans l'ERP
- Odoo : champs `peppol_eas` (schéma, ex. `0225`) et `peppol_endpoint` (ex.
  `222222226_routage1`) du tiers, s'ils existent dans la base (module de facture
  électronique installé) et si le schéma est accepté par cette version d'Odoo ; sinon,
  rien n'est écrit et la cause est donnée.
- Plusieurs adresses pour un tiers : proposée d'office celle **sans code de routage**
  (SIREN seul) si elle existe ; sinon, choix par Stéphane.
- Même circuit que l'ADR-0013 : bases choisies dans la même liste (base à compléter et
  sa copie de test), écriture par l'API d'Odoo, d'abord sur la copie de test, feu vert
  (nom retapé, mêmes choix), fiche déjà renseignée jamais écrasée, trace et annulation.
- Autres ERP : par leur connecteur (ADR-0008) quand il sait écrire un tiers ; aujourd'hui
  seul Odoo le sait.

### 3. Limites
- Appels au répertoire espacés (pas de limite publiée : environ 5 par seconde).
- Le contrôle est une photo du jour : à refaire avant la bascule de facturation.

## Arbitrages (Stéphane Moreau, 09/11/2026)
1. Répertoire Peppol public ; « non trouvé » = à vérifier, jamais « non inscrit » : oui.
2. Source : **Peppol** (pas d'API d'une plateforme agréée à ce jour).
3. Tiers contrôlés : **tous** les clients et fournisseurs français (avec SIREN).
4. Plusieurs adresses : celle sans code de routage proposée d'office, sinon choix : oui.
5. Même circuit que l'ADR-0013 (copie de test, feu vert, trace, annulation) : oui.

## Options écartées
- **Lire l'annuaire officiel en automatisant le portail Chorus Pro** (aspiration de
  pages) : contraire aux conditions d'usage, fragile, et sans garantie de légalité.
- **Écrire l'adresse sans validation** : une mauvaise adresse enverrait des factures
  légales au mauvais destinataire.
- **Déclarer « non inscrit » tout tiers absent de Peppol** : faux pour un tiers dont la
  plateforme ne publie pas.
