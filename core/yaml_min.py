# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Parseur YAML minimal, maison, zéro dépendance externe.

Supporte le sous-ensemble YAML de CONCORDE :
- mappings imbriqués par indentation
- listes d'objets ("- nom: x" puis indentation) et de scalaires ("- item")
- scalaires : chaînes (guillemets optionnels), entiers, booléens
"""


def _valeur(brut: str):
    s = brut.strip()
    if not s or s == "~" or s.lower() == "null":
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
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


def _indente(ligne: str) -> int:
    return len(ligne) - len(ligne.lstrip(" "))


def parse_yaml(texte: str):
    """Parse une chaîne YAML en structure Python (dict/listes imbriquées)."""
    lignes = [l for l in texte.splitlines()
              if l.strip() and not l.strip().startswith("#")]
    if not lignes:
        return {}

    def _bloc(i, ind):
        """Construit le sous-arbre démarrant à la ligne i, indentation minimale ind."""
        if lignes[i].lstrip().startswith("- "):
            resultat = []
            while i < len(lignes) and _indente(lignes[i]) == ind and lignes[i].lstrip().startswith("- "):
                contenu = lignes[i].lstrip()[2:]
                if ":" in contenu and not contenu.strip().startswith(("'", '"')):
                    # élément de liste-objet : "- cle: val"
                    obj = {}
                    cle, _, val = contenu.partition(":")
                    obj[cle.strip()] = _valeur(val) if val.strip() else ""
                    i += 1
                    # attributs suivants indentés sous le tiret
                    sous = ind + 2
                    while i < len(lignes) and _indente(lignes[i]) >= sous and not lignes[i].lstrip().startswith("- "):
                        c, _, v = lignes[i].strip().partition(":")
                        obj[c.strip()] = _valeur(v) if v.strip() else ""
                        i += 1
                    resultat.append(obj)
                else:
                    resultat.append(_valeur(contenu))
                    i += 1
            return resultat, i
        resultat = {}
        while i < len(lignes) and _indente(lignes[i]) == ind:
            ligne = lignes[i].strip()
            if ligne.startswith("- "):
                sous, i = _bloc(i, ind)
                return sous, i
            cle, _, val = ligne.partition(":")
            cle = cle.strip().strip('"').strip("'")
            if val.strip():
                resultat[cle] = _valeur(val)
                i += 1
            else:
                i += 1
                if i < len(lignes) and _indente(lignes[i]) > ind:
                    sous, i = _bloc(i, _indente(lignes[i]))
                    resultat[cle] = sous
                elif i < len(lignes) and _indente(lignes[i]) == ind and lignes[i].lstrip().startswith("- "):
                    sous, i = _bloc(i, ind)
                    resultat[cle] = sous
                else:
                    resultat[cle] = {}
        return resultat, i

    arbre, _ = _bloc(0, _indente(lignes[0]))
    return arbre


def charger_yaml(chemin: str):
    with open(chemin, "r", encoding="utf-8") as f:
        return parse_yaml(f.read())
