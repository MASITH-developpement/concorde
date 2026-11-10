# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Générateur de FEC synthétique type Quadra pour les tests."""

import random
from datetime import date


def generer_fec(
    nb_ecritures: int = 45, comptes: list[tuple[str, str]] | None = None
) -> bytes:
    """Produit des écritures équilibrées, en ISO-8859-1.

    Rôle : FEC synthétique déterministe (graine fixe 2026) pour les tests.
    Paramètres : nb_ecritures — nombre d'écritures (2 lignes chacune) ;
    comptes — paires (compte_debit, compte_credit) réelles du client
    (défaut : 4 paires types Quadra).
    Retour : le FEC en octets ISO-8859-1, fins de ligne CRLF.
    Erreurs : aucune levée volontairement.
    Usages : ecrire_fec (ce module), tests/test_moteur.py.
    """
    # Générateur local à graine fixe : sortie déterministe, sans toucher
    # à l'état global du module random. Données de test, pas de sécurité.
    tirage = random.Random(2026)
    if not comptes:
        comptes = [
            ("41109009", "70619018"),
            ("40129007", "60419016"),
            ("44589012", "44569010"),
            ("51219013", "41109009"),
        ]
    lignes = [
        "\t".join(
            [
                "JournalCode",
                "EcritureNum",
                "EcritureDate",
                "CompteNum",
                "CompteLib",
                "EcritureLib",
                "Debit",
                "Credit",
            ]
        )
    ]
    for n in range(1, nb_ecritures + 1):
        cd, cc = comptes[(n - 1) % len(comptes)]
        montant = tirage.randint(1000, 500000)  # centimes
        d = date(2026, 2, 1 + (n - 1) % 28).strftime("%Y%m%d")
        lib = "Facture client " + str(1000 + n)
        lignes.append(
            "\t".join(["AC", str(n), d, cd, "Lib", lib, str(montant), "0"])
        )
        lignes.append(
            "\t".join(["AC", str(n), d, cc, "Lib", lib, "0", str(montant)])
        )
    texte = "\r\n".join(lignes) + "\r\n"
    return texte.encode("iso-8859-1")


def ecrire_fec(
    chemin: str,
    nb_ecritures: int = 45,
    comptes: list[tuple[str, str]] | None = None,
) -> str:
    """Écrit un FEC synthétique (voir generer_fec) ; rend son chemin."""
    with open(chemin, "wb") as f:
        f.write(generer_fec(nb_ecritures, comptes))
    return chemin


if __name__ == "__main__":
    import sys

    sortie = sys.argv[1] if len(sys.argv) > 1 else "fec_test.txt"
    print("FEC écrit :", ecrire_fec(sortie))
