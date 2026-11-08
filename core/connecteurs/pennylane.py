# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Connecteur Pennylane : API REST v2 (ADR-0008).

Secret : `jeton` (Bearer). Un jeton d'entreprise ne vaut que pour le bac
à sable de Pennylane ; la production passe par OAuth 2.0 (à brancher).
Paramètres facultatifs : `adresse` (défaut : API v2 de Pennylane),
`societe_id` (en-tête X-Company-Id, jeton de cabinet), `statuts_lus`
(statuts des écritures lues, séparés par des virgules : exigé pour lire).

Écriture : une écriture Pennylane par écriture du lot, `piece_number` =
« <référence du transfert>/<journal>/<n°> ». L'API n'empêche pas les
doublons : CONCORDE cherche ces références dans la période avant
d'envoyer. Rien n'est créé sans arbitrage : journal ou compte absent,
compte présent sous plusieurs identifiants (un par taux de TVA), ligne
en devise, avec tiers ou lettrage (Pennylane ne les porte pas sur la
ligne) : refus nommé.
"""

import datetime
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ..canonical import ErreurMontant, vers_centimes
from ..journal import Journal, nombre_texte
from ..migration.injection import decouper, ref_ecriture
from ..migration.lot import LigneLot, Lot
from ..xlsx_ecrire import euros_texte
from .base import (
    CapacitesConnecteur,
    Connecteur,
    ErreurConnexion,
    InfoConnexion,
    PerimetreLecture,
    ResultatEcriture,
    nouveau_lot,
)
from .http_json import ClientJson

ADRESSE_PENNYLANE = "https://app.pennylane.com/api/external/v2"
TAILLE_FILTRE = 100  # valeurs par filtre « in » (au-delà : HTTP 414)

Element = dict[str, Any]  # élément JSON rendu par Pennylane


class ConnecteurPennylane(Connecteur):
    """Une société Pennylane, lue et écrite par l'API v2."""

    logiciel = "pennylane"
    libelle = "Pennylane"
    capacites: ClassVar[CapacitesConnecteur] = {
        "lecture": "api",
        "ecriture": "api",
    }
    parametres_facultatifs = ("societe_id", "adresse", "statuts_lus")
    secrets_requis = ("jeton",)

    def __init__(
        self,
        parametres: Mapping[str, str],
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        """Prépare le client de l'API et la mémoire des écritures."""
        super().__init__(parametres, secrets)
        entetes = (
            {"X-Company-Id": self.parametres["societe_id"]}
            if self.parametres.get("societe_id")
            else {}
        )
        self.client = ClientJson(
            self.parametres.get("adresse") or ADRESSE_PENNYLANE,
            self._secrets["jeton"],
            entetes,
        )
        # Identifiants Pennylane des écritures écrites (ou déjà présentes)
        # sous chaque référence, pour la relecture.
        self._ecrites: dict[str, list[int]] = {}

    def _journaux(self) -> dict[int, str]:
        """{id de journal: code}."""
        return {
            int(journal["id"]): str(journal["code"])
            for journal in self.client.tout_lire("/journals")
        }

    def tester(self, journal: Journal) -> InfoConnexion:
        """Lit les journaux (jeton et droits vérifiés)."""
        journaux = self._journaux()
        journal.dire(
            "Pennylane : %s journal(aux) lisible(s)"
            % nombre_texte(len(journaux)),
            "ok",
        )
        return {
            "logiciel": self.logiciel,
            "societe": self.parametres.get("societe_id", ""),
            "siren": "",
            "devise": "EUR",
            "version": "API v2",
        }

    def _comptes(self, numeros: Sequence[str]) -> dict[str, list[int]]:
        """{numéro de compte: [identifiants actifs]} pour ces numéros."""
        trouves: dict[str, list[int]] = {}
        for paquet in decouper(sorted(numeros), TAILLE_FILTRE):
            for compte in self.client.tout_lire(
                "/ledger_accounts",
                {
                    "filter": [
                        {"field": "number", "operator": "in", "value": paquet},
                        {"field": "enabled", "operator": "eq", "value": True},
                    ]
                },
            ):
                trouves.setdefault(str(compte["number"]), []).append(
                    int(compte["id"])
                )
        return trouves

    def _ecritures_de(self, filtres: list[dict[str, object]]) -> list[Element]:
        """Écritures Pennylane répondant aux filtres."""
        return self.client.tout_lire("/ledger_entries", {"filter": filtres})

    def _lot(self, ecritures: list[Element], journaux: dict[int, str]) -> Lot:
        """Écritures Pennylane (et leurs lignes) -> Lot."""
        par_id = {int(ecriture["id"]): ecriture for ecriture in ecritures}
        lignes_api: list[Element] = []
        for paquet in decouper(sorted(par_id), TAILLE_FILTRE):
            lignes_api += self.client.tout_lire(
                "/ledger_entry_lines",
                {
                    "filter": [
                        {
                            "field": "ledger_entry_id",
                            "operator": "in",
                            "value": paquet,
                        }
                    ],
                    "sort": "id",
                },
            )
        lignes: list[LigneLot] = []
        for numero, ligne in enumerate(lignes_api, 1):
            ecriture = par_id[int(ligne["ledger_entry"]["id"])]
            lettrees = list(ligne["lettered_ledger_entry_lines"]["ids"] or [])
            try:
                debit = vers_centimes(ligne["debit"])
                credit = vers_centimes(ligne["credit"])
            except ErreurMontant as exc:
                raise ErreurConnexion("Pennylane : %s" % exc) from exc
            lignes.append(
                {
                    "n": numero,
                    "journal_code": journaux.get(
                        int(ligne["journal"]["id"]), ""
                    ),
                    "journal_lib": "",
                    "ecriture": str(
                        ecriture.get("piece_number") or ecriture["id"]
                    ),
                    "date": _date(ligne["date"]),
                    "compte": str(ligne["ledger_account"]["number"]),
                    "compte_lib": "",
                    "tiers_ref": "",
                    "tiers_nom": "",
                    "piece": str(ecriture.get("piece_number") or ""),
                    "piece_date": None,
                    "libelle": str(
                        ligne.get("label") or ecriture.get("label") or ""
                    ),
                    "debit": debit,
                    "credit": credit,
                    "lettrage": (
                        "P%d" % min(lettrees + [int(ligne["id"])])
                        if lettrees
                        else ""
                    ),
                    "date_lettrage": None,
                    "valid_date": None,
                    "montant_devise": None,
                    "devise": "",
                    "analytique": "",
                    "compte_cible": None,
                }
            )
        return nouveau_lot(
            self.logiciel, self.parametres.get("societe_id", ""), lignes
        )

    def lire(self, perimetre: PerimetreLecture, journal: Journal) -> Lot:
        """Écritures de la période, aux statuts de `statuts_lus`."""
        statuts = [
            statut.strip()
            for statut in self.parametres.get("statuts_lus", "").split(",")
            if statut.strip()
        ]
        if not statuts:
            raise ErreurConnexion(
                "Pennylane : paramètre statuts_lus absent (statuts des "
                "écritures à lire, à arbitrer)."
            )
        filtres: list[dict[str, object]] = []
        if perimetre["du"]:
            filtres.append(
                {"field": "date", "operator": "gteq", "value": perimetre["du"]}
            )
        if perimetre["au"]:
            filtres.append(
                {"field": "date", "operator": "lteq", "value": perimetre["au"]}
            )
        ecritures = [
            ecriture
            for ecriture in self._ecritures_de(filtres)
            if ecriture.get("status") in statuts
        ]
        lot = self._lot(ecritures, self._journaux())
        journal.dire(
            "Pennylane : %s écriture(s), %s ligne(s) lue(s)"
            % (nombre_texte(len(ecritures)), nombre_texte(len(lot.lignes))),
            "ok",
        )
        return lot

    def _refus(
        self, lot: Lot, codes_journaux: dict[str, int]
    ) -> tuple[list[str], dict[str, int]]:
        """(motifs de refus, {numéro de compte: identifiant})."""
        motifs: list[str] = []
        for nom, lignes in (
            ("en devise", [ligne for ligne in lot.lignes if ligne["devise"]]),
            (
                "avec tiers",
                [ligne for ligne in lot.lignes if ligne["tiers_ref"]],
            ),
            (
                "lettrée(s)",
                [ligne for ligne in lot.lignes if ligne["lettrage"]],
            ),
        ):
            if lignes:
                motifs.append(
                    "%s ligne(s) %s : non reprises par Pennylane sur la "
                    "ligne, règle à arbitrer"
                    % (nombre_texte(len(lignes)), nom)
                )
        absents = sorted(
            {ligne["journal_code"] for ligne in lot.lignes}
            - set(codes_journaux)
        )
        if absents:
            motifs.append(
                "Journaux absents de Pennylane : %s" % ", ".join(absents)
            )
        numeros = sorted(
            {
                str(ligne["compte_cible"] or ligne["compte"])
                for ligne in lot.lignes
            }
        )
        trouves = self._comptes(numeros)
        manquants = [numero for numero in numeros if numero not in trouves]
        multiples = [
            numero for numero in numeros if len(trouves.get(numero, [])) > 1
        ]
        if manquants:
            motifs.append(
                "Comptes absents de Pennylane : %s" % ", ".join(manquants)
            )
        if multiples:
            motifs.append(
                "Comptes présents sous plusieurs identifiants (TVA), à "
                "arbitrer : %s" % ", ".join(multiples)
            )
        uniques = {
            numero: ids[0] for numero, ids in trouves.items() if len(ids) == 1
        }
        return motifs, uniques

    def ecrire(
        self, lot: Lot, reference: str, essai: bool, journal: Journal
    ) -> ResultatEcriture:
        """Essai : refus et écritures à créer. Sinon : création."""
        codes_journaux = {
            code: ident for ident, code in self._journaux().items()
        }
        motifs, comptes = self._refus(lot, codes_journaux)
        ecritures = lot.ecritures()
        refs = {cle: ref_ecriture(reference, cle) for cle in ecritures}
        dates = [ligne["date"] for ligne in lot.lignes]
        presentes: dict[str, int] = {}
        if dates and not motifs:
            for ecriture in self._ecritures_de(
                [
                    {"field": "date", "operator": "gteq", "value": min(dates)},
                    {"field": "date", "operator": "lteq", "value": max(dates)},
                ]
            ):
                if ecriture.get("piece_number") in refs.values():
                    presentes[str(ecriture["piece_number"])] = int(
                        ecriture["id"]
                    )
        resultat: ResultatEcriture = {
            "essai": essai,
            "ecritures_a_creer": len(refs) - len(presentes),
            "ecritures_deja_presentes": len(presentes),
            "erreurs": motifs,
            "fichiers": {},
        }
        if essai or motifs:
            return resultat
        ids = list(presentes.values())
        for cle, lignes in ecritures.items():
            if refs[cle] in presentes:
                continue
            corps = {
                "date": str(lignes[0]["date"]),
                "label": lignes[0]["libelle"] or refs[cle],
                "journal_id": codes_journaux[cle[0]],
                "piece_number": refs[cle],
                "ledger_entry_lines": [
                    {
                        "debit": euros_texte(ligne["debit"]),
                        "credit": euros_texte(ligne["credit"]),
                        "ledger_account_id": comptes[
                            str(ligne["compte_cible"] or ligne["compte"])
                        ],
                        "label": ligne["libelle"],
                    }
                    for ligne in lignes
                ],
            }
            try:
                cree = self.client.requete(
                    "POST", "/ledger_entries", corps=corps
                )
            except ErreurConnexion as exc:
                resultat["erreurs"].append("%s : %s" % (refs[cle], exc))
                continue
            ids.append(int(cree["id"]))
        self._ecrites[reference] = ids
        journal.dire(
            "Pennylane : %s écriture(s) créée(s), %s erreur(s)"
            % (
                nombre_texte(len(ids) - len(presentes)),
                nombre_texte(len(resultat["erreurs"])),
            ),
            "ok" if not resultat["erreurs"] else "erreur",
        )
        return resultat

    def relire(self, reference: str, journal: Journal) -> Lot:
        """Relit les écritures écrites sous `reference` par ce connecteur."""
        ids = self._ecrites.get(reference)
        if ids is None:
            raise ErreurConnexion(
                "Pennylane : rien n'a été écrit sous %s par cette connexion "
                "(l'API ne permet pas de chercher une référence)." % reference
            )
        ecritures: list[Element] = []
        for paquet in decouper(ids, TAILLE_FILTRE):
            ecritures += self._ecritures_de(
                [{"field": "id", "operator": "in", "value": paquet}]
            )
        return self._lot(ecritures, self._journaux())


def _date(texte: object) -> datetime.date:
    """Date ISO de Pennylane -> date. Lève ErreurConnexion si invalide."""
    try:
        return datetime.date.fromisoformat(str(texte))
    except ValueError as exc:
        raise ErreurConnexion("Pennylane : date invalide %r" % texte) from exc
