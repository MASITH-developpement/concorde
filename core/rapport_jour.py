# CONCORDE v1.0 — (c) MASITH / Stéphane Moreau. Tous droits réservés.
"""Rapport du jour : ce que CONCORDE a vu et fait, et ce qu'il en conclut.

  construire(jour, alertes, taches, securite) -> rapport automatique (dict)
  fusionner(auto, enregistre)    -> rapport avec les choix de l'utilisateur
  rendu_html(rapport)            -> page imprimable (seulement le visible)

Chaque ligne (conclusion, ajout, détail) porte sa date et son heure
(« quand ») et le rapport est rangé dans l'ordre chronologique (demande du
07/11/2026).

Chaque conclusion a un identifiant STABLE
(ex. « alerte|balance|testalbhade|CLIENT_CREDITEUR »).
Les choix de l'utilisateur (masquée, texte corrigé, commentaire) sont
rattachés à cet identifiant : régénérer le rapport ajoute les nouvelles
conclusions sans écraser ses corrections. Déterministe : aucun texte ne
passe par une IA.
"""

import html
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

NIVEAUX = {"BLOQUANT": 0, "ALERTE": 1, "INFO": 2, "OK": 3}
ACTIONS = {
    "analyser": "analyse",
    "telecharger": "téléchargement",
    "comparer": "comparaison",
    "supprimer_base": "suppression de base",
    "reinitialiser_base": "réinitialisation",
}
PLURIELS = {
    "analyse": "analyses",
    "téléchargement": "téléchargements",
    "comparaison": "comparaisons",
    "suppression de base": "suppressions de base",
    "réinitialisation": "réinitialisations",
}
SECTIONS = ("securite", "alertes", "changements", "taches")
# Données JSON (alertes, tâches, résultats de sécurité, rapports, saisie de
# l'écran) : dictionnaires aux valeurs hétérogènes.
DonneesJson = Mapping[str, Any]
TITRES = {
    "securite": "Sécurité du serveur",
    "alertes": "Alertes",
    "changements": "Changements dans Odoo",
    "taches": "Travaux de la journée",
}


def _jour(iso: str | None) -> str:
    """Rend la date AAAA-MM-JJ d'un horodatage ISO ('' si absent)."""
    return (iso or "")[:10]


def _date_fr(jour: str) -> str:
    """Rend une date AAAA-MM-JJ en JJ/MM/AAAA."""
    return date.fromisoformat(jour).strftime("%d/%m/%Y")


def _quand_borne(quand: str | None) -> str:
    """Borne un horodatage ISO à la seconde.

    Rôle : uniformiser le champ « quand » des conclusions et des détails.
    Paramètres : quand, horodatage ISO (None ou '' accepté).
    Retour : les 19 premiers caractères ('' si absent).
    Erreurs : aucune.
    Usages : _conclusion, _item.
    """
    return (quand or "")[:19]


def _conclusion(
    ident: str,
    niveau: str,
    texte: str,
    section: str,
    quand: str | None = "",
) -> dict[str, Any]:
    """Crée une conclusion automatique (texte non modifié par l'utilisateur).

    Rôle : forme commune de toutes les conclusions du rapport.
    Paramètres : ident, identifiant stable ; niveau, BLOQUANT / ALERTE /
    INFO / OK ; texte, texte automatique ; section, section d'origine ;
    quand, horodatage ISO.
    Retour : {id, niveau, texte_auto, section, quand}.
    Erreurs : aucune.
    Usages : construire (toutes les sections).
    """
    return {
        "id": ident,
        "niveau": niveau,
        "texte_auto": texte,
        "section": section,
        "quand": _quand_borne(quand),
    }


def _item(texte: str, ident: str, quand: str | None) -> dict[str, str]:
    """Crée une ligne de détail d'une section.

    Rôle : forme commune des détails du rapport.
    Paramètres : texte, ligne affichée ; ident, identifiant de la
    conclusion liée ; quand, horodatage ISO.
    Retour : {texte, id, quand}.
    Erreurs : aucune.
    Usages : construire (toutes les sections).
    """
    return {"texte": texte, "id": ident, "quand": _quand_borne(quand)}


def horodatage(iso: str | None) -> str:
    """Rend un horodatage ISO lisible.

    Rôle : afficher « quand » dans la page et l'écran.
    Paramètres : iso, ex. '2026-11-07T10:30:12'.
    Retour : '07/11/2026 10:30' ('' si absent ou trop court).
    Erreurs : aucune.
    Usages : rendu_html (conclusions, ajouts, sections), tests.
    """
    if not iso or len(iso) < 10:
        return ""
    return "%s/%s/%s%s" % (
        iso[8:10],
        iso[5:7],
        iso[:4],
        " " + iso[11:16] if len(iso) >= 16 else "",
    )


def construire(
    jour: str,
    alertes: Sequence[DonneesJson] = (),
    taches: Iterable[DonneesJson] = (),
    securite: DonneesJson | None = None,
    maintenant: datetime | None = None,
) -> dict[str, Any]:
    """Construit le rapport automatique d'un jour.

    Rôle : tirer les conclusions du jour (sécurité, alertes, changements
    dans Odoo, tâches), dans l'ordre chronologique.
    Paramètres : jour, AAAA-MM-JJ ; alertes, alertes du centre ; taches,
    tâches lancées ; securite, {controle, antivirus} (derniers résultats) ;
    maintenant, heure de référence (heure locale par défaut).
    Retour : {jour, genere_le, conclusions, sections}.
    Erreurs : KeyError si une alerte ou une tâche est incomplète ;
    ValueError si `jour` n'est pas une date ISO à l'affichage.
    Usages : interface/serveur (rapport du jour), tests.
    """
    maintenant = maintenant or datetime.now()
    aujourd_hui = jour == maintenant.date().isoformat()
    genere = maintenant.isoformat(timespec="seconds")
    conclusions: list[dict[str, Any]] = []
    sections: dict[str, list[dict[str, str]]] = {s: [] for s in SECTIONS}

    # --- Sécurité ------------------------------------------------------------
    sec = securite or {}
    for nom, libelle in (
        ("controle", "Contrôle mineur / rançongiciel"),
        ("antivirus", "Analyse antivirus ClamAV"),
    ):
        d = sec.get(nom)
        if not d:
            conclusions.append(
                _conclusion(
                    "securite|" + nom,
                    "ALERTE",
                    "%s : aucun résultat disponible." % libelle,
                    "securite",
                    genere,
                )
            )
            continue
        quand = d.get("date", "")
        ligne = "%s — dernier passage : %s" % (
            libelle,
            (d.get("statut") or "?").upper(),
        )
        if nom == "antivirus" and d.get("infos", {}).get("fichiers_analyses"):
            ligne += (
                " (%s fichiers analysés)" % d["infos"]["fichiers_analyses"]
            )
        sections["securite"].append(_item(ligne, "securite|" + nom, quand))
        if d.get("statut") == "conforme":
            detail = ""
            if nom == "antivirus":
                n = d.get("infos", {}).get("fichiers_analyses")
                detail = ", aucun fichier malveillant" + (
                    " sur %s fichiers" % n if n else ""
                )
            conclusions.append(
                _conclusion(
                    "securite|" + nom,
                    "OK",
                    "%s : rien à signaler%s." % (libelle, detail),
                    "securite",
                    quand,
                )
            )
        else:
            for c in d.get("constats", []):
                conclusions.append(
                    _conclusion(
                        "securite|%s|%s" % (nom, c["code"]),
                        c["niveau"],
                        "Sécurité — %s : %s (%s)."
                        % (
                            c["message"],
                            c["nombre"],
                            "; ".join(c.get("exemples", [])[:2]),
                        ),
                        "securite",
                        quand,
                    )
                )

    # --- Alertes -------------------------------------------------------------
    etat = [a for a in alertes if a.get("statut") in ("active", "resolue")]
    nouvelles = [a for a in etat if _jour(a.get("premiere_fois")) == jour]
    resolues = [
        a
        for a in etat
        if a.get("statut") == "resolue" and _jour(a.get("resolue_le")) == jour
    ]
    # Une base supprimée ferme ses alertes : ce n'est pas une correction, on
    # le dit.
    supprimees = {
        a.get("base"): a.get("premiere_fois")
        for a in alertes
        if a.get("code") == "BASE_SUPPRIMEE"
        and _jour(a.get("premiere_fois")) == jour
    }
    closes: dict[str, list[str]] = {}
    for a in [a for a in resolues if a.get("base") in supprimees]:
        closes.setdefault(a["base"], []).append(a["message"])
    resolues = [a for a in resolues if a.get("base") not in supprimees]
    actives = (
        [a for a in etat if a.get("statut") == "active"] if aujourd_hui else []
    )
    for a in actives:
        apparue = (
            " (apparue aujourd'hui)"
            if a in nouvelles
            else " (active depuis cette date)"
        )
        conclusions.append(
            _conclusion(
                "alerte|%s" % a["id"],
                a["niveau"],
                "%s — %s : %s%s."
                % (_base(a), a["message"], a["nombre"], apparue),
                "alertes",
                a.get("premiere_fois"),
            )
        )
        sections["alertes"].append(
            _item(
                "[%s] %s — %s : %s%s"
                % (a["niveau"], _base(a), a["message"], a["nombre"], apparue),
                "alerte|" + a["id"],
                a.get("premiere_fois"),
            )
        )
    for a in resolues:
        conclusions.append(
            _conclusion(
                "resolue|%s" % a["id"],
                "OK",
                "Résolu : %s — %s." % (_base(a), a["message"]),
                "alertes",
                a.get("resolue_le"),
            )
        )
        sections["alertes"].append(
            _item(
                "[RÉSOLUE] %s — %s" % (_base(a), a["message"]),
                "resolue|" + a["id"],
                a.get("resolue_le"),
            )
        )
    for base, messages in sorted(closes.items()):
        conclusions.append(
            _conclusion(
                "closes|%s" % base,
                "INFO",
                "Base %s supprimée : %d alerte(s) close(s) sans "
                "correction (%s)."
                % (base, len(messages), ", ".join(sorted(messages))),
                "alertes",
                supprimees.get(base),
            )
        )
        sections["alertes"].append(
            _item(
                "[CLOSES, base supprimée] base %s — %s"
                % (base, ", ".join(sorted(messages))),
                "closes|" + base,
                supprimees.get(base),
            )
        )
    if not aujourd_hui:
        for a in nouvelles:
            sections["alertes"].append(
                _item(
                    "[apparue] %s — %s : %s"
                    % (_base(a), a["message"], a["nombre"]),
                    "alerte|" + a["id"],
                    a.get("premiere_fois"),
                )
            )
    if aujourd_hui and not actives:
        conclusions.append(
            _conclusion(
                "alertes|aucune",
                "OK",
                "Aucune alerte active.",
                "alertes",
                genere,
            )
        )

    # --- Changements dans Odoo (événements du jour) --------------------------
    evts = [
        a
        for a in alertes
        if a.get("statut") == "evenement"
        and _jour(a.get("premiere_fois")) == jour
        and a.get("code")
        not in ("INSTANTANE_INITIAL", "BASE_SUPPRIMEE", "BASE_REINITIALISEE")
    ]
    par_base: dict[str, Counter[tuple[str, str]]] = {}
    premier: dict[str, str] = {}
    for a in evts:
        b = a.get("base", "?")
        par_base.setdefault(b, Counter())[
            (a["niveau"], a["message"])
        ] += a.get("nombre", 1)
        premier[b] = min(
            premier.get(b) or a["premiere_fois"], a["premiere_fois"]
        )
    for base, compteur in sorted(par_base.items()):
        graves = [
            (m, n)
            for (niv, m), n in compteur.items()
            if niv in ("BLOQUANT", "ALERTE")
        ]
        texte = ", ".join(
            "%s : %s" % (m, n) for (_, m), n in sorted(compteur.items())
        )
        sections["changements"].append(
            _item(
                "Base %s — %s" % (base, texte),
                "changements|" + base,
                premier[base],
            )
        )
        conclusions.append(
            _conclusion(
                "changements|%s" % base,
                "ALERTE" if graves else "INFO",
                "Base %s : %s." % (base, texte),
                "changements",
                premier[base],
            )
        )

    # --- Tâches de la journée -----------------------------------------------
    du_jour = [t for t in taches if _jour(t.get("cree_le")) == jour]
    if du_jour:
        compte = Counter(_libelle_action(t["action"]) for t in du_jour)
        conclusions.append(
            _conclusion(
                "taches|resume",
                "INFO",
                "Travaux de la journée : %s."
                % ", ".join(
                    "%d %s" % (n, PLURIELS.get(a, a) if n > 1 else a)
                    for a, n in sorted(compte.items())
                ),
                "taches",
                min(t.get("cree_le") or genere for t in du_jour),
            )
        )
    for t in sorted(du_jour, key=lambda t: t.get("cree_le", "")):
        heure = (t.get("cree_le") or "")[11:16]
        quoi = _libelle_action(t["action"])
        base = t.get("base", "")
        if t.get("base_b"):
            base += " ↔ " + t["base_b"]
        res = _resume_tache(t)
        quand = t.get("cree_le")
        sections["taches"].append(
            _item(
                "%s %s : %s%s"
                % (
                    quoi.capitalize(),
                    base,
                    t.get("statut"),
                    " — " + res if res else "",
                ),
                "tache|" + t["id"],
                quand,
            )
        )
        if t.get("statut") == "echec":
            conclusions.append(
                _conclusion(
                    "tache|%s" % t["id"],
                    "ALERTE",
                    "Échec — %s de %s : %s."
                    % (quoi, base, t.get("erreur") or "?"),
                    "taches",
                    quand,
                )
            )
        elif (
            t["action"] == "comparer" and t.get("statut") == "terminee" and res
        ):
            texte = "Comparaison %s : %s" % (base, res)
            deja = next(
                (c for c in conclusions if c.get("_cle") == texte), None
            )
            if deja:
                deja["_heures"].append(heure)
                deja["texte_auto"] = "%s (%d fois : %s)." % (
                    texte,
                    len(deja["_heures"]),
                    ", ".join(deja["_heures"]),
                )
                sections["taches"][-1]["id"] = deja["id"]
            else:
                c = _conclusion(
                    "tache|%s" % t["id"], "INFO", texte + ".", "taches", quand
                )
                c.update(_cle=texte, _heures=[heure])
                conclusions.append(c)
        elif (
            t["action"] in ("supprimer_base", "reinitialiser_base")
            and t.get("statut") == "terminee"
        ):
            conclusions.append(
                _conclusion(
                    "tache|%s" % t["id"],
                    "INFO",
                    "%s %s (%s)."
                    % (quoi.capitalize(), base, res or "sans sauvegarde"),
                    "taches",
                    quand,
                )
            )
    if not du_jour:
        conclusions.append(
            _conclusion(
                "taches|aucune",
                "INFO",
                "Aucun travail lancé dans CONCORDE ce jour.",
                "taches",
                genere,
            )
        )

    for c in conclusions:
        c.pop("_cle", None)
        c.pop("_heures", None)
    # Ordre chronologique : date, puis heure ; à égalité, le plus grave
    # d'abord.
    conclusions.sort(
        key=lambda c: (c["quand"] or genere, NIVEAUX.get(c["niveau"], 9))
    )
    for items in sections.values():
        items.sort(key=lambda x: x["quand"] or genere)
    return {
        "jour": jour,
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "conclusions": conclusions,
        "sections": sections,
    }


def _libelle_action(action: str) -> str:
    """Rend le libellé d'une action de tâche.

    Rôle : nommer une tâche en français dans le rapport.
    Paramètres : action, code d'action (ex. 'analyser').
    Retour : libellé de ACTIONS, ou le code lui-même s'il est inconnu.
    Erreurs : aucune.
    Usages : construire (résumé des travaux, détail de chaque tâche).
    """
    return ACTIONS.get(action, action)


def _base(a: DonneesJson) -> str:
    """Rend 'serveur' ou 'base <nom>' pour une alerte."""
    return (
        "serveur"
        if a.get("base") == "serveur"
        else "base %s" % a.get("base", "?")
    )


def _resume_tache(t: DonneesJson) -> str:
    """Résume le résultat d'une tâche terminée ('' si rien à dire)."""
    r = t.get("resultat") or {}
    if t["action"] == "analyser" and r.get("synthese"):
        s = r["synthese"]
        return "%s (%d bloquant, %d alerte)" % (
            r.get("statut", "?"),
            s.get("BLOQUANT", 0),
            s.get("ALERTE", 0),
        )
    if t["action"] == "comparer" and r.get("comparaison"):
        c = r["comparaison"]
        dif = ", ".join(
            "%s : %s" % (x["message"], x["nombre"])
            for x in c.get("constats", [])
        )
        return "%s%s" % (
            c.get("statut", "?"),
            " — " + dif if dif else ", aucune différence",
        )
    if t["action"] in ("supprimer_base", "reinitialiser_base"):
        return (
            ("sauvegarde %s" % r["sauvegarde"]) if r.get("sauvegarde") else ""
        )
    if t["action"] == "telecharger" and r.get("produits"):
        return ", ".join(p["format"].upper() for p in r["produits"])
    return ""


def fusionner(
    auto: DonneesJson, enregistre: DonneesJson | None = None
) -> dict[str, Any]:
    """Applique les choix enregistrés au rapport automatique.

    Rôle : garder les choix de l'utilisateur (masquer, corriger, commenter,
    ajouter) d'une génération à l'autre.
    Paramètres : auto, rapport de construire() ; enregistre, choix
    enregistrés (nettoyer_saisie), ou None.
    Retour : rapport fusionné (conclusions enrichies de visible, texte,
    modifie, commentaire, nouvelle ; ajouts, commentaire,
    sections_masquees, enregistre_le).
    Erreurs : KeyError si `auto` est incomplet.
    Usages : interface/serveur (écran et export), tests.
    """
    e = enregistre or {}
    choix = {c["id"]: c for c in e.get("conclusions", [])}
    res = dict(auto)
    res["conclusions"] = []
    for c in auto["conclusions"]:
        u = choix.get(c["id"], {})
        res["conclusions"].append(
            dict(
                c,
                visible=u.get("visible", True),
                texte=(
                    u.get("texte")
                    if u.get("texte") not in (None, "")
                    else c["texte_auto"]
                ),
                modifie=bool(u.get("texte"))
                and u.get("texte") != c["texte_auto"],
                commentaire=u.get("commentaire", ""),
                nouvelle=c["id"] not in choix and bool(choix),
            )
        )
    # Conclusions qui ne sont plus produites mais que l'utilisateur avait
    # gardées / corrigées.
    vus = {c["id"] for c in auto["conclusions"]}
    for ident, u in choix.items():
        if (
            ident not in vus
            and (u.get("texte") or u.get("commentaire"))
            and u.get("visible", True)
        ):
            res["conclusions"].append(
                {
                    "id": ident,
                    "niveau": u.get("niveau", "INFO"),
                    "section": u.get("section", "alertes"),
                    "texte_auto": "",
                    "texte": u.get("texte") or "",
                    "visible": True,
                    "modifie": True,
                    "commentaire": u.get("commentaire", ""),
                    "nouvelle": False,
                    "perimee": True,
                    "quand": u.get("quand", ""),
                }
            )
    res["conclusions"].sort(
        key=lambda c: (
            c.get("quand") or auto["genere_le"],
            NIVEAUX.get(c["niveau"], 9),
        )
    )
    res["ajouts"] = sorted(
        [a for a in e.get("ajouts", []) if (a.get("texte") or "").strip()],
        key=lambda a: a.get("quand") or "",
    )
    res["commentaire"] = e.get("commentaire", "")
    res["sections_masquees"] = [
        s for s in e.get("sections_masquees", []) if s in SECTIONS
    ]
    res["enregistre_le"] = e.get("enregistre_le")
    return res


def nettoyer_saisie(corps: DonneesJson) -> dict[str, Any]:
    """Valide et borne ce que l'écran envoie à l'enregistrement.

    Rôle : ne garder que les champs attendus, de longueur bornée.
    Paramètres : corps, JSON reçu de l'écran.
    Retour : {conclusions, ajouts, commentaire, sections_masquees,
    enregistre_le}.
    Erreurs : AttributeError si un élément n'est pas un dictionnaire.
    Usages : interface/serveur (enregistrement du rapport), tests.
    """

    def txt(v: object, n: int) -> str:
        """Rend `v` en texte sans espaces de bord, borné à `n` caractères."""
        return str(v or "").strip()[:n]

    return {
        "conclusions": [
            {
                "id": txt(c.get("id"), 300),
                "visible": bool(c.get("visible", True)),
                "texte": txt(c.get("texte"), 2000),
                "commentaire": txt(c.get("commentaire"), 2000),
                "niveau": txt(c.get("niveau"), 10),
                "section": txt(c.get("section"), 20),
                "quand": txt(c.get("quand"), 19),
            }
            for c in (corps.get("conclusions") or [])[:500]
            if c.get("id")
        ],
        "ajouts": [
            {
                "id": txt(a.get("id"), 50),
                "texte": txt(a.get("texte"), 2000),
                "quand": txt(a.get("quand"), 19),
            }
            for a in (corps.get("ajouts") or [])[:100]
        ],
        "commentaire": txt(corps.get("commentaire"), 5000),
        "sections_masquees": [
            s for s in corps.get("sections_masquees") or [] if s in SECTIONS
        ],
        "enregistre_le": datetime.now().isoformat(timespec="seconds"),
    }


def rendu_html(r: DonneesJson, societe: str = "MASITH") -> str:
    """Rend la page HTML autonome et imprimable du rapport.

    Rôle : export du rapport ; seul ce qui est visible est rendu.
    Paramètres : r, rapport fusionné (fusionner) ; societe, nom affiché en
    pied de page.
    Retour : page HTML complète (textes échappés).
    Erreurs : KeyError si le rapport est incomplet.
    Usages : interface/serveur (export), tests.
    """
    e = html.escape
    couleurs = {
        "BLOQUANT": "#b42318",
        "ALERTE": "#a15c00",
        "INFO": "#1f5fa8",
        "OK": "#18794e",
    }
    lignes: list[str] = []
    for c in r["conclusions"]:
        if not c.get("visible", True):
            continue
        com = (
            '<div class="com">%s</div>' % e(c["commentaire"])
            if c.get("commentaire")
            else ""
        )
        lignes.append(
            '<li><span class="q">%s</span> '
            '<span class="n" style="color:%s">%s</span>'
            " %s%s</li>"
            % (
                e(horodatage(c.get("quand"))),
                couleurs.get(c["niveau"], "#555"),
                e(c["niveau"]),
                e(c["texte"]),
                com,
            )
        )
    for a in r.get("ajouts", []):
        lignes.append(
            '<li><span class="q">%s</span> <span class="n" style="color:#555">'
            "AJOUT</span> %s</li>"
            % (e(horodatage(a.get("quand"))), e(a["texte"]))
        )
    masquees = {
        c["id"] for c in r["conclusions"] if not c.get("visible", True)
    }
    sections: list[str] = []
    for s in SECTIONS:
        if s in r.get("sections_masquees", []):
            continue
        items = [
            x for x in r["sections"].get(s, []) if x.get("id") not in masquees
        ]
        if items:
            sections.append(
                "<h2>%s</h2><ul>%s</ul>"
                % (
                    e(TITRES[s]),
                    "".join(
                        '<li><span class="q">%s</span> %s</li>'
                        % (e(horodatage(x.get("quand"))), e(x["texte"]))
                        for x in items
                    ),
                )
            )
    return """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>CONCORDE — Rapport du %(jour)s</title>
<style>
body{font:15px/1.5 system-ui,sans-serif;color:#1c2733;max-width:860px;\
margin:2rem auto;
padding:0 16px}
h1{font-size:1.5rem;margin:0}
h2{font-size:1.1rem;margin:1.6rem 0 .4rem;border-bottom:1px solid #dde3ea}
.meta{color:#5b6b7c}ul{padding-left:1.2rem}li{margin:.3rem 0}
.n{font-weight:700;font-size:.75rem;margin-right:.4rem}
.q{color:#5b6b7c;font-variant-numeric:tabular-nums;white-space:nowrap}
.com{color:#5b6b7c;font-style:italic;margin-left:1rem}
.general{background:#f4f6f9;border-left:4px solid #1f4e79;padding:.6rem .9rem}
footer{margin-top:2.5rem;color:#5b6b7c;font-size:.8rem;\
border-top:1px solid #dde3ea;
padding-top:.6rem}
@media print{body{margin:0}}</style></head><body>
<h1>CONCORDE — Rapport du %(jour)s</h1>
<p class="meta">Généré le %(genere)s%(enregistre)s</p>
%(general)s<h2>Conclusions</h2><ul>%(lignes)s</ul>%(sections)s
<footer>%(societe)s — SIRET 928 983 055 00015 · Valensole | \
contact@masith.fr · masith.fr</footer>
</body></html>""" % {
        "jour": e(_date_fr(r["jour"])),
        "genere": e(r["genere_le"].replace("T", " ")[:16]),
        "enregistre": (
            e(
                " · relu et modifié le %s"
                % r["enregistre_le"].replace("T", " ")[:16]
            )
            if r.get("enregistre_le")
            else ""
        ),
        "general": (
            '<div class="general">%s</div>'
            % e(r["commentaire"]).replace("\n", "<br>")
            if r.get("commentaire")
            else ""
        ),
        "lignes": "".join(lignes) or "<li>Aucune conclusion retenue.</li>",
        "sections": "".join(sections),
        "societe": e(societe),
    }
