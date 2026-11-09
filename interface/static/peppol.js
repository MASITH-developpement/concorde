// CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
// Facture électronique des tiers (ADR-0014). Chargé avant app.js : n'utilise
// ses outils ($, el, api…) qu'à l'appel ; au chargement, seulement
// document.getElementById. Toute donnée reçue est insérée en TEXTE.
"use strict";

const CLASSES_PEPPOL = { inscrit: "Inscrit", non_trouve: "Non trouvé — à vérifier", sans_siren: "Sans SIREN" };

async function chargerEcranPeppol() {
  const connexions = (await api("/api/connexions")).filter((c) => c.logiciel === "odoo" && c.connexion_test);
  const choix = $("#peppol-connexion");
  choix.replaceChildren(...connexions.map((c) => el("option", { value: c.id, texte: c.libelle })));
  $("#form-peppol button").disabled = !connexions.length;
  $("#peppol-note").textContent = connexions.length ? ""
    : "Il faut une connexion Odoo vers la base, avec sa connexion de test (copie). Ajoutez-les dans Transferts → Connexions, avec leur clé API.";
}

document.getElementById("form-peppol").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const bouton = $("#form-peppol button");
  const erreur = $("#erreur-peppol");
  erreur.textContent = ""; bouton.disabled = true;
  try {
    const { id } = await api("/api/peppol", { method: "POST", corps: { connexion: $("#peppol-connexion").value } });
    const t = await attendreTache(id, $("#suivi-peppol"));
    if (t.statut !== "terminee") throw new Error(t.erreur || "Échec de la vérification.");
    afficherVerification(await api("/api/peppol/" + id));
  } catch (e) { erreur.textContent = e.message; }
  finally { bouton.disabled = false; }
});

function ligneAdresse(resultat, adresse) {
  const tiers = resultat.tiers;
  const proposee = resultat.proposee && resultat.proposee.identifiant === adresse.identifiant && resultat.proposee.schema === adresse.schema;
  return el("label", { class: "case" },
    el("input", { type: "radio", name: "p-" + tiers.id, value: `${adresse.schema}|${adresse.identifiant}`,
                  disabled: Boolean(tiers.adresse_actuelle), checked: proposee && !tiers.adresse_actuelle }),
    el("span", {}, el("strong", { class: "mono", texte: `${adresse.schema}:${adresse.identifiant}` }),
      ` — ${adresse.documents.join(", ") || "documents non précisés"}`,
      adresse.inscrit_le ? ` — inscrit le ${dateFr(adresse.inscrit_le)}` : "",
      proposee ? el("small", { texte: " · sans code de routage (proposée)" }) : null));
}

function afficherVerification(donnees) {
  const resultats = donnees.propositions;
  const zone = $("#resultat-peppol");
  const liste = el("div", { class: "siret-liste" });
  const comptes = { inscrit: 0, non_trouve: 0, sans_siren: 0 };
  for (const r of resultats) {
    comptes[r.classe] += 1;
    const role = [r.tiers.client ? "client" : null, r.tiers.fournisseur ? "fournisseur" : null].filter(Boolean).join(" et ");
    liste.append(el("div", { class: "siret-tiers", "data-classe": r.classe },
      el("div", { class: "entete-resultat" },
        el("strong", { texte: `${r.tiers.nom} (id ${r.tiers.id})` }),
        el("span", { class: "statut " + r.classe, texte: CLASSES_PEPPOL[r.classe] })),
      el("small", { texte: `${role} · SIREN ${r.tiers.siren || "absent"}` + (r.tiers.adresse_actuelle ? ` · adresse déjà dans Odoo : ${r.tiers.adresse_actuelle}` : "") }),
      r.adresses.map((a) => ligneAdresse(r, a)),
      r.adresses.length && !r.tiers.adresse_actuelle ? el("label", { class: "case" },
        el("input", { type: "radio", name: "p-" + r.tiers.id, value: "", checked: !r.proposee }),
        el("span", { texte: "Ne rien écrire pour ce tiers" })) : null));
  }
  const filtre = (classe) => () => $$(".siret-tiers", liste).forEach((b) => { b.hidden = Boolean(classe) && b.dataset.classe !== classe; });
  const erreur = el("p", { class: "erreur", role: "alert" });
  const suite = el("div", {});
  const lireChoix = () => resultats.flatMap((r) => {
    const coche = $(`input[name="p-${r.tiers.id}"]:checked`, liste);
    if (!coche || !coche.value) return [];
    const [schema, identifiant] = coche.value.split("|");
    return [{ id: r.tiers.id, schema, identifiant }];
  });
  const essai = el("button", { class: "bouton principal", type: "button", texte: "Reprendre les adresses : essai sur la copie de test",
    onclick: async () => {
      erreur.textContent = ""; essai.disabled = true;
      try {
        const choix = lireChoix();
        const { id } = await api(`/api/peppol/${donnees.tache}/ecrire`, { method: "POST", corps: { cible: "test", choix } });
        const t = await attendreTache(id, suite);
        if (t.statut !== "terminee") throw new Error(t.erreur || "Échec de l'essai.");
        suite.replaceChildren(bilanTiers(t.resultat), formulaireFeuVertTiers("/api/peppol", donnees, choix, suite));
      } catch (e) { erreur.textContent = e.message; }
      finally { essai.disabled = false; }
    } });
  zone.replaceChildren(el("div", { class: "carte" },
    el("div", { class: "entete-resultat" }, el("h2", { texte: "Résultat — " + donnees.connexion }),
      el("a", { class: "bouton petit", href: `/api/peppol/${donnees.tache}/csv`, texte: "Liste complète (CSV)" })),
    el("p", { class: "aide", texte: `${resultats.length} clients et fournisseurs : ${comptes.inscrit} inscrits, ${comptes.non_trouve} non trouvés (à vérifier), ${comptes.sans_siren} sans SIREN (à compléter : Analyser → « Compléter SIRET et TVA »).` }),
    el("div", { class: "actions" },
      el("button", { class: "bouton petit", type: "button", texte: "Tous", onclick: filtre("") }),
      el("button", { class: "bouton petit", type: "button", texte: "Inscrits", onclick: filtre("inscrit") }),
      el("button", { class: "bouton petit", type: "button", texte: "Non trouvés", onclick: filtre("non_trouve") }),
      el("button", { class: "bouton petit", type: "button", texte: "Sans SIREN", onclick: filtre("sans_siren") })),
    liste, erreur, el("div", { class: "actions" }, essai), suite));
}
