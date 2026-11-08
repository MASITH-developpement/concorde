# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Secrets des connexions : /etc/concorde/connecteurs.env (ADR-0008, point 3).

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
    "CONCORDE_SECRETS", "/etc/concorde/connecteurs.env"
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
    Usages : secrets_connexion, scripts/concorde_secret.py.
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


def ecrire_variable(chemin: str, nom: str, valeur: str) -> None:
    """Ajoute ou remplace une variable `NOM=valeur` dans un fichier env.

    Rôle : écrire un secret sans jamais ouvrir le fichier à d'autres
    comptes (création en 600, droits remis à 600 ensuite).
    Paramètres : chemin — fichier ; nom — variable (majuscules) ;
    valeur — sans retour à la ligne.
    Retour : aucun.
    Erreurs : ErreurSecrets si le nom ou la valeur est invalide ; OSError
    si l'écriture échoue.
    Usages : scripts/concorde_secret.py, scripts/concorde_interface_mdp.py.
    """
    if not _NOM_VALIDE.match(nom):
        raise ErreurSecrets("Nom de variable invalide : %s" % nom)
    if "\n" in valeur or "\r" in valeur:
        raise ErreurSecrets(
            "La valeur de %s contient un retour à la ligne." % nom
        )
    lignes: list[str] = []
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as fichier:
            lignes = [
                ligne for ligne in fichier if not ligne.startswith(nom + "=")
            ]
    lignes.append("%s=%s\n" % (nom, valeur))
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    ancien = os.umask(0o077)
    try:
        with open(chemin, "w", encoding="utf-8") as fichier:
            fichier.writelines(lignes)
    finally:
        os.umask(ancien)
    os.chmod(chemin, 0o600)
