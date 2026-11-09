// CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
// Compléter SIRET et TVA (ADR-0013), depuis le constat d'une analyse.
// Chargé avant app.js : n'utilise ses outils ($, el, api, suivre…) qu'à
// l'appel. Toute donnée reçue est insérée en TEXTE.
"use strict";

const CLASSES_SIRET = { sure: "Sûre", a_choisir: "À choisir", introuvable: "Introuvable" };

// Attend la fin d'une tâche ; rend son état final.
async function attendreTache(id, zone) {
  if (zone) suivre(id, zone);
  for (;;) {
    await new Promise((fin) => setTimeout(fin, 1500));
    const t = await api("/api/taches/" + id);
    if (t.statut !== "en_cours" && t.statut !== "en_attente") return t;
  }
}

const AIDE_DEUX_BASES = "Il faut deux bases où CONCORDE peut écrire : la base à compléter et sa copie de test. "
  + "Branchez-les dans l'écran Bases (Odoo distant avec sa clé API) ou dans Transferts → Connexions.";

// Deux listes : base à compléter (par défaut celle du sélecteur du haut) et
// copie de test (par défaut une base dont le nom contient « test »).
function selecteursBases(sources) {
  const options = (choisie) => sources.map((s) => el("option", { value: s.id, texte: s.libelle, selected: s.id === choisie }));
  const enHaut = "base:" + baseCourante();
  const production = sources.some((s) => s.id === enHaut) ? enHaut : (sources[0] || {}).id;
  const test = (sources.find((s) => s.id !== production && /test/i.test(s.libelle)) || sources.find((s) => s.id !== production) || {}).id;
  return [el("select", { name: "production" }, options(production)), el("select", { name: "test" }, options(test))];
}

async function ouvrirSiret(analyse) {
  const sources = await api("/api/tiers/bases");
  const erreur = el("p", { class: "erreur", role: "alert" });
  const suiviZone = el("div", { id: "suivi-siret" });
  if (sources.length < 2) {
    return tiroir("Compléter SIRET et TVA", el("p", { class: "aide", texte: AIDE_DEUX_BASES }));
  }
  const [production, test] = selecteursBases(sources);
  const bouton = el("button", { class: "bouton principal", type: "submit", texte: "Chercher dans l'annuaire des entreprises" });
  const form = el("form", { class: "formulaire" },
    el("p", { class: "aide", texte: "Les tiers signalés sont relus dans la base choisie, puis cherchés dans l'annuaire public de l'État (nom et code postal seulement). SIRET et TVA sont contrôlés par calcul. Rien n'est écrit à cette étape." }),
    el("div", { class: "ligne-champs" }, el("label", {}, "Base à compléter", production), el("label", {}, "Copie de test (écrite d'abord)", test)),
    erreur, bouton, suiviZone);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); bouton.disabled = true; erreur.textContent = "";
    try {
      const { id } = await api("/api/siret", { method: "POST", corps: { analyse: analyse.id, production: production.value, test: test.value } });
      const t = await attendreTache(id, suiviZone);
      if (t.statut !== "terminee") throw new Error(t.erreur || "Échec des propositions.");
      afficherPropositions(await api("/api/siret/" + id));
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  tiroir("Compléter SIRET et TVA — " + analyse.base, form);
}

function ligneCandidate(proposition, candidate, rang) {
  const siretOk = !candidate.controles.some((a) => !a.startsWith("TVA"));
  const tvaOk = !candidate.controles.some((a) => a.startsWith("TVA"));
  const radio = el("input", { type: "radio", name: "c-" + proposition.tiers.id, value: rang, disabled: !siretOk,
    checked: proposition.classe === "sure" && rang === 0 });
  return el("label", { class: "case" }, radio, el("span", {},
    el("strong", { texte: candidate.nom }), ` — SIRET ${candidate.siret}`,
    tvaOk ? ` — TVA ${candidate.tva}` : " — TVA non écrite (" + candidate.controles.filter((a) => a.startsWith("TVA")).join(", ") + ")",
    el("br"), el("small", { texte: candidate.adresse + (candidate.meme_code_postal ? " · même code postal" : "") + (candidate.meme_nom ? " · même nom" : "") }),
    siretOk ? null : el("small", { class: "erreur", texte: " " + candidate.controles.join(", ") })));
}

function afficherPropositions(donnees) {
  const liste = el("div", { class: "siret-liste" });
  const comptes = { sure: 0, a_choisir: 0, introuvable: 0 };
  for (const p of donnees.propositions) {
    comptes[p.classe] += 1;
    liste.append(el("div", { class: "siret-tiers", "data-tiers": p.tiers.id },
      el("div", { class: "entete-resultat" },
        el("strong", { texte: `${p.tiers.nom} (id ${p.tiers.id})` }),
        el("span", { class: "statut " + p.classe, texte: CLASSES_SIRET[p.classe] })),
      el("small", { texte: [p.tiers.code_postal, p.tiers.ville].filter(Boolean).join(" ") || "adresse absente dans Odoo" }),
      p.candidates.map((c, rang) => ligneCandidate(p, c, rang)),
      p.candidates.length ? el("label", { class: "case" }, el("input", { type: "radio", name: "c-" + p.tiers.id, value: "", checked: p.classe !== "sure" }),
        el("span", { texte: "Ne rien écrire pour ce tiers" })) : el("p", { class: "note", texte: "Aucune entreprise trouvée : à compléter dans Odoo." })));
  }
  const erreur = el("p", { class: "erreur", role: "alert" });
  const zone = el("div", {});
  const lireChoix = () => donnees.propositions.flatMap((p) => {
    const coche = $(`input[name="c-${p.tiers.id}"]:checked`, liste);
    if (!coche || coche.value === "") return [];
    const c = p.candidates[Number(coche.value)];
    const tvaOk = !c.controles.some((a) => a.startsWith("TVA"));
    return [{ id: p.tiers.id, siret: c.siret, tva: tvaOk ? c.tva : "" }];
  });
  const essai = el("button", { class: "bouton principal", type: "button", texte: "Essayer sur la copie de test",
    onclick: async () => {
      erreur.textContent = ""; essai.disabled = true;
      try {
        const choix = lireChoix();
        const { id } = await api(`/api/siret/${donnees.tache}/ecrire`, { method: "POST", corps: { cible: "test", choix } });
        const t = await attendreTache(id, zone);
        if (t.statut !== "terminee") throw new Error(t.erreur || "Échec de l'essai.");
        zone.replaceChildren(bilanTiers(t.resultat), formulaireFeuVertTiers("/api/siret", donnees, choix, zone));
      } catch (e) { erreur.textContent = e.message; }
      finally { essai.disabled = false; }
    } });
  tiroir("Compléter SIRET et TVA — " + donnees.connexion,
    el("p", { class: "aide", texte: `${donnees.propositions.length} tiers à compléter : ${comptes.sure} sûrs (cochés), ${comptes.a_choisir} à choisir, ${comptes.introuvable} introuvables. Essai d'abord sur « ${donnees.connexion_test} », puis feu vert pour « ${donnees.connexion} ».` }),
    liste, erreur, el("div", { class: "actions" }, essai), zone);
}

function bilanTiers(r) {
  return el("div", { class: "carte" },
    el("p", {}, el("strong", { texte: `${r.base} (${r.cible === "test" ? "copie de test" : "production"}) : ` }),
      `${r.ecrits.length} fiche(s) complétée(s), ${r.ignores.length} déjà complétée(s), ${r.refus.length} refus d'Odoo.`),
    r.refus.length ? el("ul", {}, r.refus.map((x) => el("li", { class: "erreur", texte: `Tiers ${x.id} : ${x.cause}` }))) : null);
}

function formulaireFeuVertTiers(racine, donnees, choix, zone) {
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Nom de la connexion à retaper" });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true, texte: "Feu vert : écrire en production" });
  const erreur = el("p", { class: "erreur", role: "alert" });
  saisie.addEventListener("input", () => { bouton.disabled = saisie.value !== donnees.connexion; });
  const form = el("form", { class: "formulaire" },
    el("div", { class: "danger", texte: `Vérifiez quelques fiches dans « ${donnees.connexion_test} ». Le feu vert écrit exactement les mêmes choix dans la base de production. Une fiche complétée entre-temps n'est pas touchée ; tout est tracé et peut être annulé.` }),
    el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: donnees.connexion })), saisie), erreur, bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); bouton.disabled = true; erreur.textContent = "";
    try {
      const { id } = await api(`${racine}/${donnees.tache}/ecrire`, { method: "POST",
        corps: { cible: "production", choix, confirmation: saisie.value } });
      const t = await attendreTache(id, null);
      if (t.statut !== "terminee") throw new Error(t.erreur || "Échec de l'écriture.");
      zone.replaceChildren(bilanTiers(t.resultat), boutonAnnulerTiers(racine, donnees.tache, "production"));
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  return el("div", {}, boutonAnnulerTiers(racine, donnees.tache, "test"), form);
}

function boutonAnnulerTiers(racine, tache, cible) {
  return el("button", { class: "bouton petit", type: "button", texte: `Annuler l'écriture (${cible === "test" ? "copie de test" : "production"})`,
    onclick: async (ev) => {
      if (!confirm("Remettre les anciennes valeurs (vides) sur les fiches complétées ?")) return;
      ev.target.disabled = true;
      try {
        const { id } = await api(`${racine}/${tache}/annuler`, { method: "POST", corps: { cible } });
        const t = await attendreTache(id, null);
        alert(t.statut === "terminee" ? `${t.resultat.remis.length} fiche(s) remise(s), ${t.resultat.ignores.length} modifiée(s) depuis (laissées).` : t.erreur);
      } catch (e) { alert(e.message); }
      finally { ev.target.disabled = false; }
    } });
}

// Résultat d'une tâche d'un écran de tiers (SIRET, facture électronique).
function rendreTacheTiers(t) {
  const r = t.resultat || {};
  const libelles = Object.assign({}, CLASSES_SIRET, CLASSES_PEPPOL);
  return el("div", { class: "carte" },
    el("div", { class: "entete-resultat" }, el("h2", { texte: (ACTIONS[t.action] || t.action) + " — " + t.base }), statutPastille(t.statut)),
    t.statut !== "terminee" ? el("p", { class: "erreur", texte: t.erreur || "" })
      : r.classes ? el("p", { texte: `${r.tiers} tiers : ` + Object.entries(r.classes).map(([k, n]) => `${n} ${libelles[k] || k}`).join(", ") })
        : r.ecrits ? bilanTiers(r)
          : el("p", { texte: `${(r.remis || []).length} fiche(s) remise(s).` }));
}
