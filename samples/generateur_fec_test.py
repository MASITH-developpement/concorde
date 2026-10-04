# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Générateur de FEC synthétique type Quadra pour les tests.

Produit 45 écritures x 4 lignes = 180 lignes, équilibré, en ISO-8859-1.
"""
import random
from datetime import date


def generer_fec(nb_ecritures: int = 45) -> bytes:
    random.seed(2026)  # déterministe
    lignes = ["JournalCode\tEcritureNum\tEcritureDate\tCompteNum\tCompteLib\tEcritureLib\tDebit\tCredit"]
    for n in range(1, nb_ecritures + 1):
        montant = random.randint(1000, 500000)  # centimes
        d = date(2026, 1 + (n - 1) % 12, 1 + (n - 1) % 28).strftime("%Y%m%d")
        lib = "Facture client " + str(1000 + n)
        lignes.append("\t".join(["AC", str(n), d, "411000", "Clients", lib, str(montant), "0"]))
        lignes.append("\t".join(["AC", str(n), d, "706000", "Prestations", lib, "0", str(montant)]))
        lib3 = "TVA collectée " + str(1000 + n)
        lignes.append("\t".join(["VE", str(n), d, "445710", "TVA collectée", lib3, str(montant // 5), "0"]))
        lignes.append("\t".join(["VE", str(n), d, "445710", "TVA collectée", lib3, "0", str(montant // 5)]))
    texte = "\r\n".join(lignes) + "\r\n"
    return texte.encode("iso-8859-1")


def ecrire_fec(chemin: str, nb_ecritures: int = 45) -> str:
    with open(chemin, "wb") as f:
        f.write(generer_fec(nb_ecritures))
    return chemin


if __name__ == "__main__":
    import sys
    sortie = sys.argv[1] if len(sys.argv) > 1 else "fec_test.txt"
    print("FEC écrit :", ecrire_fec(sortie))
