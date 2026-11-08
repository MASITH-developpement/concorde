# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Parseur YAML minimal, maison, zéro dépendance externe.

Supporte le sous-ensemble YAML de CONCORDE :
- tables imbriquées par indentation, à toute profondeur, y compris sous
  un élément de liste
- listes de tables ("- nom: x" puis indentation), de scalaires ("- item")
  et de listes ("- - item")
- listes de scalaires en ligne entre crochets ([a, "b", 3], [])
- scalaires : chaînes (guillemets optionnels), entiers, booléens
- commentaires : ligne entière ou fin de ligne (" # ...", hors guillemets)

Jamais de donnée perdue ou déformée en silence : toute construction hors
de ce sous-ensemble (retrait incohérent, table en ligne {...}, liste en
ligne imbriquée, ligne sans clé...) lève ``ErreurYaml``.
"""

from typing import NamedTuple, Optional, Union

ScalaireYaml = Union[str, int, bool]
ValeurYaml = Union[ScalaireYaml, list["ValeurYaml"], dict[str, "ValeurYaml"]]

# Caractères de guillemet reconnus autour d'un scalaire ou d'une clé.
GUILLEMETS_YAML = "\"'"
# Caractères après lesquels un guillemet ouvre une chaîne entre guillemets.
OUVRANTS_GUILLEMET = " \t[,"


class ErreurYaml(ValueError):
    """Construction YAML hors du sous-ensemble géré, ligne citée.

    Levée au lieu de rendre une structure incomplète ou déformée.
    ``numero_ligne`` : numéro (à partir de 1) de la ligne fautive dans le
    texte d'origine ; le message commence par « ligne N : ».
    """

    def __init__(self, numero_ligne: int, motif: str) -> None:
        """Construit l'erreur à partir de la ligne fautive et du motif."""
        super().__init__(f"ligne {numero_ligne} : {motif}")
        self.numero_ligne = numero_ligne


class LigneYaml(NamedTuple):
    """Ligne utile du document : numéro d'origine, retrait, texte nettoyé."""

    numero: int
    retrait: int
    contenu: str


def _valeur(brut: str) -> ScalaireYaml:
    """Scalaire YAML : chaîne, entier ou booléen ('' pour ~ ou null)."""
    s = brut.strip()
    if not s or s == "~" or s.lower() == "null":
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in GUILLEMETS_YAML:
        return s[1:-1]
    bas = s.lower()
    if bas == "true":
        return True
    if bas == "false":
        return False
    try:
        return int(s)
    except ValueError:
        return s


def _ouvre_guillemet(texte: str, position: int, guillemet_ouvert: str) -> bool:
    """Dit si le caractère à ``position`` ouvre une chaîne entre guillemets.

    Rôle : distinguer un guillemet de début de chaîne ('x') d'une
    apostrophe dans le texte (l'arrondi).
    Paramètres : ``texte``, la ligne ou le fragment lu ; ``position``,
    l'indice du caractère examiné ; ``guillemet_ouvert``, le guillemet
    actuellement ouvert ("" si aucun).
    Retour : True si aucun guillemet n'est ouvert, que le caractère est un
    guillemet et qu'il est en début de texte ou après espace, [ ou virgule.
    Erreurs : aucune.
    Usages : ``_retirer_commentaire``, ``_decouper_liste_en_ligne``.
    """
    return (
        not guillemet_ouvert
        and texte[position] in GUILLEMETS_YAML
        and (position == 0 or texte[position - 1] in OUVRANTS_GUILLEMET)
    )


def _retirer_commentaire(texte: str) -> str:
    """Retire le commentaire de fin de ligne et les espaces finaux.

    Rôle : un # hors guillemets, en début de texte ou précédé d'un espace,
    ouvre un commentaire ; un # collé au texte ou entre guillemets reste
    du texte.
    Paramètres : ``texte``, la ligne d'origine.
    Retour : la ligne sans commentaire ni espaces finaux ("" si la ligne
    n'est qu'un commentaire).
    Erreurs : aucune.
    Usages : ``_lignes_utiles``.
    """
    guillemet_ouvert = ""
    for position, caractere in enumerate(texte):
        if _ouvre_guillemet(texte, position, guillemet_ouvert):
            guillemet_ouvert = caractere
        elif caractere == guillemet_ouvert:
            guillemet_ouvert = ""
        elif (
            caractere == "#"
            and not guillemet_ouvert
            and (position == 0 or texte[position - 1] in " \t")
        ):
            return texte[:position].rstrip()
    return texte.rstrip()


def _lignes_utiles(texte: str) -> list[LigneYaml]:
    """Découpe le texte en lignes utiles, sans commentaires ni blancs.

    Rôle : préparer la lecture en gardant le numéro d'origine de chaque
    ligne, pour que les erreurs citent la bonne ligne.
    Paramètres : ``texte``, le document YAML complet.
    Retour : les lignes non vides après retrait des commentaires.
    Erreurs : aucune.
    Usages : ``parse_yaml``.
    """
    lignes = []
    for numero, ligne_brute in enumerate(texte.splitlines(), start=1):
        ligne_nettoyee = _retirer_commentaire(ligne_brute)
        if ligne_nettoyee.strip():
            contenu = ligne_nettoyee.lstrip(" ")
            retrait = len(ligne_nettoyee) - len(contenu)
            lignes.append(LigneYaml(numero, retrait, contenu))
    return lignes


def _est_tiret(contenu: str) -> bool:
    """Dit si une ligne est un élément de liste (- seul ou « - ... »)."""
    return contenu == "-" or contenu.startswith("- ")


def _separer_cle(contenu: str) -> Optional[tuple[str, str]]:
    """Sépare « clé: valeur » ; rend None si le texte n'a pas de clé.

    Rôle : trouver le premier : suivi d'un espace ou de la fin de ligne,
    après une éventuelle clé entre guillemets.
    Paramètres : ``contenu``, la ligne sans retrait ni commentaire.
    Retour : (clé sans guillemets, valeur brute) ou None.
    Erreurs : aucune.
    Usages : ``_lire_table``, ``_lire_liste`` (élément table ou scalaire).
    """
    guillemet_fermant = 0
    if contenu[0] in GUILLEMETS_YAML:
        guillemet_fermant = contenu.find(contenu[0], 1)
        if guillemet_fermant == -1:
            return None
    position = contenu.find(":", guillemet_fermant)
    while position != -1:
        debut_valeur = position + 1
        if debut_valeur == len(contenu) or contenu[debut_valeur] in " \t":
            cle = contenu[:position].strip()
            if guillemet_fermant:
                cle = contenu[1:guillemet_fermant]
            return cle, contenu[debut_valeur:]
        position = contenu.find(":", debut_valeur)
    return None


def _decouper_liste_en_ligne(interieur: str, numero: int) -> list[str]:
    """Découpe l'intérieur d'une liste en ligne aux virgules hors guillemets.

    Rôle : isoler chaque élément de [a, "b, c", 3].
    Paramètres : ``interieur``, le texte entre les crochets (non vide) ;
    ``numero``, la ligne d'origine, pour les erreurs.
    Retour : les éléments bruts, espaces retirés.
    Erreurs : ``ErreurYaml`` si un crochet ou une accolade apparaît hors
    guillemets (imbrication non gérée) ou si un élément est vide.
    Usages : ``_valeur_en_ligne``.
    """
    elements_bruts = []
    debut_element = 0
    guillemet_ouvert = ""
    for position, caractere in enumerate(interieur):
        if _ouvre_guillemet(interieur, position, guillemet_ouvert):
            guillemet_ouvert = caractere
        elif caractere == guillemet_ouvert:
            guillemet_ouvert = ""
        elif not guillemet_ouvert and caractere in "[]{}":
            raise ErreurYaml(numero, "imbrication dans une liste en ligne")
        elif not guillemet_ouvert and caractere == ",":
            elements_bruts.append(interieur[debut_element:position].strip())
            debut_element = position + 1
    elements_bruts.append(interieur[debut_element:].strip())
    if "" in elements_bruts:
        raise ErreurYaml(numero, "élément vide dans une liste en ligne")
    return elements_bruts


def _valeur_en_ligne(brut: str, numero: int) -> ValeurYaml:
    """Valeur écrite sur la ligne même : scalaire ou liste entre crochets.

    Rôle : interpréter le texte qui suit « clé: » ou « - ».
    Paramètres : ``brut``, le texte de la valeur (sans commentaire) ;
    ``numero``, la ligne d'origine, pour les erreurs.
    Retour : la liste de scalaires pour [...], sinon le scalaire.
    Erreurs : ``ErreurYaml`` pour une table en ligne {...}, un crochet
    non fermé sur la ligne ou une liste en ligne imbriquée.
    Usages : ``_lire_table``, ``_lire_liste``.
    """
    texte_valeur = brut.strip()
    if texte_valeur.startswith("{"):
        raise ErreurYaml(numero, "table en ligne {...} non gérée")
    if not texte_valeur.startswith("["):
        return _valeur(texte_valeur)
    if not texte_valeur.endswith("]"):
        raise ErreurYaml(numero, "liste en ligne non fermée sur la ligne")
    interieur = texte_valeur[1:-1].strip()
    if not interieur:
        return []
    return [
        _valeur(element_brut)
        for element_brut in _decouper_liste_en_ligne(interieur, numero)
    ]


def _lire_enfant(
    lignes: list[LigneYaml], position: int, retrait: int
) -> Optional[tuple[ValeurYaml, int]]:
    """Lit le bloc plus indenté qui suit une clé ou un tiret sans valeur.

    Rôle : rattacher à son parent le bloc indenté sous lui.
    Paramètres : ``lignes``, le document ; ``position``, la ligne qui
    suit le parent ; ``retrait``, le retrait du parent.
    Retour : (bloc lu, position suivante), ou None s'il n'y a pas de
    ligne plus indentée à ``position``.
    Erreurs : celles de ``_lire_bloc``.
    Usages : ``_lire_table``, ``_lire_liste``.
    """
    if position < len(lignes) and lignes[position].retrait > retrait:
        return _lire_bloc(lignes, position, lignes[position].retrait)
    return None


def _continue_le_bloc(ligne: LigneYaml, retrait: int) -> bool:
    """Dit si la ligne continue le bloc courant ; erreur si trop indentée.

    Rôle : refuser une ligne plus indentée qui n'appartient à aucun parent
    (retrait incohérent), au lieu de l'ignorer.
    Paramètres : ``ligne``, la ligne examinée ; ``retrait``, celui du bloc.
    Retour : True si la ligne est au retrait du bloc, False si elle est
    moins indentée (fin du bloc).
    Erreurs : ``ErreurYaml`` si la ligne est plus indentée que le bloc.
    Usages : ``_lire_table``, ``_lire_liste``.
    """
    if ligne.retrait > retrait:
        raise ErreurYaml(ligne.numero, "retrait incohérent")
    return ligne.retrait == retrait


def _lire_table(
    lignes: list[LigneYaml],
    position: int,
    retrait: int,
    valeur_si_vide: ValeurYaml,
) -> tuple[dict[str, ValeurYaml], int]:
    """Lit les lignes « clé: valeur » au retrait donné, enfants compris.

    Rôle : construire une table ; une clé sans valeur reçoit le bloc
    indenté qui la suit, ou une liste au même retrait, sinon
    ``valeur_si_vide``.
    Paramètres : ``lignes``, le document ; ``position``, la première
    ligne ; ``retrait``, le retrait des clés ; ``valeur_si_vide``, valeur
    d'une clé sans valeur ni bloc ({} en table, "" dans un élément de
    liste).
    Retour : (table lue, position de la première ligne hors table).
    Erreurs : ``ErreurYaml`` si une ligne n'a pas de clé, est un tiret au
    niveau des clés, ou a un retrait incohérent.
    Usages : ``_lire_bloc``, ``_lire_liste`` (élément table).
    """
    table: dict[str, ValeurYaml] = {}
    while position < len(lignes) and _continue_le_bloc(
        lignes[position], retrait
    ):
        ligne = lignes[position]
        if _est_tiret(ligne.contenu):
            raise ErreurYaml(ligne.numero, "tiret au niveau des clés")
        cle_et_reste = _separer_cle(ligne.contenu)
        if cle_et_reste is None:
            raise ErreurYaml(ligne.numero, "ligne sans « clé: »")
        cle, reste = cle_et_reste
        position += 1
        if reste.strip():
            table[cle] = _valeur_en_ligne(reste, ligne.numero)
            continue
        enfant = _lire_enfant(lignes, position, retrait)
        if enfant is not None:
            table[cle], position = enfant
        elif (
            position < len(lignes)
            and lignes[position].retrait == retrait
            and _est_tiret(lignes[position].contenu)
        ):
            table[cle], position = _lire_liste(lignes, position, retrait)
        else:
            table[cle] = valeur_si_vide
    return table, position


def _lire_liste(
    lignes: list[LigneYaml], position: int, retrait: int
) -> tuple[list[ValeurYaml], int]:
    """Lit les éléments « - ... » au retrait donné, enfants compris.

    Rôle : construire une liste. Un élément « - clé: v » ou « - - x » est
    relu comme une ligne placée à la colonne de son contenu (la ligne est
    remplacée dans ``lignes``) : il ouvre une table dont les clés
    s'alignent sur la première, ou une liste. Un « - » seul prend le bloc
    indenté qui le suit ("" sinon).
    Paramètres : ``lignes``, le document ; ``position``, la première
    ligne ; ``retrait``, le retrait des tirets.
    Retour : (liste lue, position de la première ligne hors liste).
    Erreurs : ``ErreurYaml`` pour un retrait incohérent (dont un bloc
    indenté sous un élément scalaire) ; celles de ``_valeur_en_ligne``.
    Usages : ``_lire_bloc``, ``_lire_table`` (liste au retrait de la clé).
    """
    elements_liste: list[ValeurYaml] = []
    while (
        position < len(lignes)
        and _continue_le_bloc(lignes[position], retrait)
        and _est_tiret(lignes[position].contenu)
    ):
        ligne = lignes[position]
        contenu_element = ligne.contenu[1:].lstrip(" ")
        if not contenu_element:
            enfant = _lire_enfant(lignes, position + 1, retrait)
            if enfant is None:
                enfant = ("", position + 1)
            valeur_element, position = enfant
        elif _est_tiret(contenu_element) or _separer_cle(contenu_element):
            colonne = ligne.retrait + len(ligne.contenu) - len(contenu_element)
            lignes[position] = LigneYaml(
                ligne.numero, colonne, contenu_element
            )
            if _est_tiret(contenu_element):
                valeur_element, position = _lire_liste(
                    lignes, position, colonne
                )
            else:
                valeur_element, position = _lire_table(
                    lignes, position, colonne, ""
                )
        else:
            valeur_element = _valeur_en_ligne(contenu_element, ligne.numero)
            position += 1
        elements_liste.append(valeur_element)
    return elements_liste, position


def _lire_bloc(
    lignes: list[LigneYaml], position: int, retrait: int
) -> tuple[ValeurYaml, int]:
    """Lit le bloc (liste ou table) qui commence à ``position``.

    Rôle : choisir liste ou table d'après la première ligne du bloc.
    Paramètres : ``lignes``, le document ; ``position``, la première
    ligne du bloc ; ``retrait``, son retrait.
    Retour : (bloc lu, position de la première ligne hors bloc).
    Erreurs : celles de ``_lire_liste`` et ``_lire_table``.
    Usages : ``parse_yaml``, ``_lire_enfant``.
    """
    if _est_tiret(lignes[position].contenu):
        return _lire_liste(lignes, position, retrait)
    return _lire_table(lignes, position, retrait, {})


def parse_yaml(texte: str) -> ValeurYaml:
    """Parse une chaîne YAML en structure Python (dict/listes imbriquées).

    Paramètres : ``texte``, le document YAML.
    Retour : la table ou la liste racine ({} pour un document vide).
    Erreurs : ``ErreurYaml`` (ligne citée) pour toute construction hors du
    sous-ensemble géré, dont une ligne restée hors du bloc racine.
    """
    lignes = _lignes_utiles(texte)
    if not lignes:
        return {}
    arbre, position = _lire_bloc(lignes, 0, lignes[0].retrait)
    if position < len(lignes):
        raise ErreurYaml(lignes[position].numero, "ligne hors du bloc racine")
    return arbre


def charger_yaml(chemin: str) -> ValeurYaml:
    """Lit un fichier YAML (UTF-8) et le parse avec parse_yaml.

    Erreurs : ``OSError`` si le fichier est illisible ; ``ErreurYaml``
    comme ``parse_yaml``.
    """
    with open(chemin, "r", encoding="utf-8") as f:
        return parse_yaml(f.read())
