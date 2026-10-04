# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Générateur de FEC synthétique type Quadra pour les tests."""
import random
from datetime import date


def generer_fec(nb_ecritures: int = 45, comptes=None) -> bytes:
    """Produit des écritures équilibrées, en ISO-8859-1.

    comptes : liste de paires (compte_debit, compte_credit) réelles du client.
    """
    random.seed(2026)  # déterministe
    if not comptes:
        comptes = [("41100000", "70600000"), ("40100000", "60100000"),
                   ("44572000", "44562000"), ("51211000", "41100000")]
    lignes = ["JournalCode\tEcritureNum\tEcritureDate\tCompteNum\tCompteLib\tEcritureLib\tDebit\tCredit"]
    for n in range(1, nb_ecritures + 1):
        cd, cc = comptes[(n - 1) % len(comptes)]
        montant = random.randint(1000, 500000)  # centimes
        d = date(2026, 2, 1 + (n - 1) % 28).strftime("%Y%m%d")
        lib = "Facture client " + str(1000 + n)
        lignes.append("\t".join(["AC", str(n), d, cd, "Lib", lib, str(montant), "0"]))
        lignes.append("\t".join(["AC", str(n), d, cc, "Lib", lib, "0", str(montant)]))
    texte = "\r\n".join(lignes) + "\r\n"
    return texte.encode("iso-8859-1")


def ecrire_fec(chemin: str, nb_ecritures: int = 45, comptes=None) -> str:
    with open(chemin, "wb") as f:
        f.write(generer_fec(nb_ecritures, comptes))
    return chemin


if __name__ == "__main__":
    import sys
    sortie = sys.argv[1] if len(sys.argv) > 1 else "fec_test.txt"
    print("FEC écrit :", ecrire_fec(sortie))
