# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Secrets des connexions : /etc/concorde/connecteurs/connecteurs.env.

Dossier propre au compte du service (700), seul endroit de /etc où
l'interface peut écrire (ADR-0011, point 3 ; ADR-0008, point 3).

Une ligne par secret, `NOM=valeur`. Le nom d'un secret de connexion est
`CONCORDE_CNX_<IDENTIFIANT>_<CHAMP>`, en majuscules, par exemple
`CONCORDE_CNX_PENNYLANE_3F2A9C_JETON`.

Le fichier n'est lu que s'il n'est lisible que par son propriétaire
(droits 600 ou 400) : sinon, refus. Aucune valeur n'apparaît jamais dans
un message d'erreur, un journal ou un rapport.
"""

import os
import re
import stat

CHEMIN_SECRETS = os.environ.get(
    "CONCORDE_SECRETS", "/etc/concorde/connecteurs/connecteurs.env"
)
_NOM_VALIDE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ErreurSecrets(RuntimeError):
    """Fichier de secrets refusé (droits trop ouverts, ligne invalide)."""


def nom_variable(ident: str, champ: str) -> str:
    """Nom de la variable qui porte un secret de connexion.

    Rôle : un seul endroit qui fabrique ce nom.
    Paramètres : ident — identifiant de la connexion ; champ — nom du
    secret attendu par le connecteur (ex. « jeton »).
    Retour : `CONCORDE_CNX_<IDENT>_<CHAMP>` en majuscules.
    Erreurs : ErreurSecrets si le nom obtenu n'est pas valide.
    Usages : secrets_connexion, etat_secrets, effacer_secrets_connexion,
    scripts/concorde_connexion.py, interface (écran Transferts).
    """
    nom = ("CONCORDE_CNX_%s_%s" % (ident, champ)).upper()
    if not _NOM_VALIDE.match(nom):
        raise ErreurSecrets("Nom de secret invalide : %s" % nom)
    return nom


def lire_secrets(chemin: str = CHEMIN_SECRETS) -> dict[str, str]:
    """Lit tous les secrets du fichier.

    Rôle : charger les secrets au moment de s'en servir (un secret ajouté
    est pris sans redémarrer le service).
    Paramètres : chemin — fichier de secrets.
    Retour : {nom: valeur} ; {} si le fichier n'existe pas.
    Erreurs : ErreurSecrets si le fichier est lisible par d'autres que son
    propriétaire, ou si une ligne n'est pas `NOM=valeur` (le numéro de la
    ligne est donné, jamais son contenu).
    Usages : connexions.Annuaire.ouvrir.
    """
    if not os.path.exists(chemin):
        return {}
    mode = os.stat(chemin).st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ErreurSecrets(
            "%s est lisible par d'autres comptes (droits %s) : "
            "lancer « chmod 600 %s »." % (chemin, oct(mode & 0o777), chemin)
        )
    secrets: dict[str, str] = {}
    with open(chemin, encoding="utf-8") as fichier:
        for numero, ligne in enumerate(fichier, 1):
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#"):
                continue
            nom, egal, valeur = ligne.partition("=")
            if not egal or not _NOM_VALIDE.match(nom.strip()):
                raise ErreurSecrets(
                    "%s, ligne %d : attendu NOM=valeur." % (chemin, numero)
                )
            secrets[nom.strip()] = valeur.strip()
    return secrets


def secrets_connexion(
    ident: str, champs: tuple[str, ...], secrets: dict[str, str]
) -> dict[str, str]:
    """Secrets d'une connexion, rangés par champ.

    Rôle : donner à un connecteur ses seuls secrets, pas ceux des autres.
    Paramètres : ident — identifiant de la connexion ; champs — secrets
    attendus par le connecteur ; secrets — résultat de lire_secrets.
    Retour : {champ: valeur} pour les champs présents.
    Erreurs : ErreurSecrets (nom invalide).
    Usages : connexions.Annuaire.ouvrir.
    """
    trouves: dict[str, str] = {}
    for champ in champs:
        valeur = secrets.get(nom_variable(ident, champ))
        if valeur:
            trouves[champ] = valeur
    return trouves


def etat_secrets(
    ident: str, champs: tuple[str, ...], secrets: dict[str, str]
) -> dict[str, bool]:
    """Pour chaque secret attendu : renseigné ou non, sans sa valeur.

    Rôle : ce que l'écran peut savoir d'un secret (ADR-0011, point 2).
    Paramètres : ident — identifiant de la connexion ; champs — secrets
    attendus par le connecteur ; secrets — résultat de lire_secrets.
    Retour : {champ: True si renseigné}.
    Erreurs : ErreurSecrets (nom invalide).
    Usages : connexions.Annuaire.secrets_renseignes.
    """
    trouves = secrets_connexion(ident, champs, secrets)
    return {champ: champ in trouves for champ in champs}


def _reecrire(chemin: str, lignes: list[str]) -> None:
    """Réécrit le fichier d'un seul coup, en 600 dès sa création.

    Rôle : qu'une coupure en pleine écriture ne perde jamais les secrets
    déjà enregistrés (fichier temporaire puis renommage).
    Paramètres : chemin — fichier final ; lignes — contenu complet.
    Retour : aucun.
    Erreurs : OSError si l'écriture échoue (le fichier d'origine reste
    intact).
    Usages : ecrire_variable, effacer_variables.
    """
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, mode=0o700, exist_ok=True)
    temporaire = chemin + ".tmp"
    ancien = os.umask(0o077)
    try:
        with open(temporaire, "w", encoding="utf-8") as fichier:
            fichier.writelines(lignes)
    finally:
        os.umask(ancien)
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, chemin)


def _lignes_sans(chemin: str, noms: set[str]) -> list[str]:
    """Lignes du fichier, sans celles des variables `noms` ; [] s'il manque."""
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as fichier:
        return [
            ligne
            for ligne in fichier
            if ligne.partition("=")[0].strip() not in noms
        ]


def ecrire_variable(chemin: str, nom: str, valeur: str) -> None:
    """Ajoute ou remplace une variable `NOM=valeur` dans un fichier env.

    Rôle : écrire un secret sans jamais ouvrir le fichier à d'autres
    comptes, ni risquer de perdre les autres (écriture atomique, 600).
    Paramètres : chemin — fichier ; nom — variable (majuscules) ;
    valeur — non vide, sans retour à la ligne.
    Retour : aucun.
    Erreurs : ErreurSecrets si le nom ou la valeur est invalide ; OSError
    si l'écriture échoue.
    Usages : scripts/concorde_connexion.py, scripts/concorde_interface_mdp.py,
    interface (écran Transferts).
    """
    if not _NOM_VALIDE.match(nom):
        raise ErreurSecrets("Nom de variable invalide : %s" % nom)
    if not valeur:
        raise ErreurSecrets("Valeur vide pour %s : rien n'est écrit." % nom)
    if "\n" in valeur or "\r" in valeur:
        raise ErreurSecrets(
            "La valeur de %s contient un retour à la ligne." % nom
        )
    lignes = _lignes_sans(chemin, {nom})
    lignes.append("%s=%s\n" % (nom, valeur))
    _reecrire(chemin, lignes)


def effacer_secrets_connexion(
    chemin: str, ident: str, champs: tuple[str, ...]
) -> None:
    """Efface du fichier les secrets d'une connexion.

    Rôle : une connexion retirée ne laisse aucun secret derrière elle
    (ADR-0011, point 2).
    Paramètres : chemin — fichier de secrets ; ident — connexion ;
    champs — secrets attendus par son connecteur.
    Retour : aucun (rien à faire si le fichier n'existe pas).
    Erreurs : ErreurSecrets (nom invalide) ; OSError.
    Usages : connexions.Annuaire.retirer.
    """
    if not os.path.exists(chemin):
        return
    noms = {nom_variable(ident, champ) for champ in champs}
    _reecrire(chemin, _lignes_sans(chemin, noms))
