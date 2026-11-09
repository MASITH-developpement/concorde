// CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
// Écran Montée de version (ADR-0012). Chargé avant app.js : n'utilise ses
// outils ($, el, api…) qu'à l'appel ; au chargement, seulement
// document.getElementById. Toute donnée reçue est insérée en TEXTE.
"use strict";

const ETAPES_MONTEE_ECRAN = [
  ["inventaire", "1. Inventaire des modules"],
  ["photo_avant", "2. Photo comptable avant"],
  ["sauts", "3. Montée, une version à la fois"],
  ["photo_apres", "4. Photo comptable après"],
  ["comparaison", "4. Comparaison au centime"],
  ["feu_vert", "5. Feu vert"],
  ["nouvel_essai", "6. Nouvel essai sur une copie fraîche"],
  ["livraison", "7. Livraison"],
];
const etatMontees = { pret: false, depotMax: 0, suivi: null };

async function chargerEcranMontees() {
  const etat = await api("/api/montees");
  etatMontees.pret = etat.pret;
  etatMontees.depotMax = etat.depot_max;
  const bandeau = $("#montees-indisponible");
  bandeau.hidden = etat.pret;
  bandeau.textContent = etat.cause;
  $$("#form-montee input, #form-montee select, #form-montee button").forEach((champ) => { champ.disabled = !etat.pret; });
  const choix = $("#montee-arrivee");
  if (!choix.options.length) {
    const defaut = etat.versions.at(-2) || etat.versions.at(-1);
    choix.replaceChildren(...etat.versions.map((v) => el("option", { value: v, texte: "Odoo " + v, selected: v === defaut })));
  }
  afficherMontees(etat.montees, etat.en_attente.length > 0);
  const actif = etat.en_attente.length || etat.montees.some((m) => m.statut === "en_cours");
  clearTimeout(etatMontees.suivi);
  if (actif && (location.hash === "#montees")) etatMontees.suivi = setTimeout(chargerEcranMontees, 5000);
}

// Envoie une sauvegarde .zip ; rend son résumé (jeton, version, base…).
async function deposerSauvegarde(fichier) {
  if (fichier.size > etatMontees.depotMax) {
    throw new Error(`Sauvegarde trop grosse : ${taille(fichier.size)} (maximum ${taille(etatMontees.depotMax)}).`);
  }
  return api("/api/montees/depot?nom=" + encodeURIComponent(fichier.name), { method: "POST", fichier });
}

// Dépose une demande au service et attend son résultat, sans limite de
// durée (une montée peut prendre des heures) ; l'écran se met à jour seul.
async function demanderMontee(chemin, corps = {}) {
  const { demande } = await api(chemin, { method: "POST", corps });
  await chargerEcranMontees();
  for (;;) {
    await new Promise((fin) => setTimeout(fin, 3000));
    const resultat = await api("/api/montees/demandes/" + demande);
    if (resultat.statut === "refus") { await chargerEcranMontees(); throw new Error(resultat.message); }
    if (resultat.statut === "fait") { await chargerEcranMontees(); return resultat; }
  }
}

document.getElementById("form-montee").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const bouton = $("button[type=submit]", f);
  const erreur = $("#erreur-montee");
  erreur.textContent = ""; bouton.disabled = true;
  try {
    const depot = await deposerSauvegarde(f.sauvegarde.files[0]);
    $("#montee-depot").textContent = `Sauvegarde acceptée : base ${depot.base || "?"}, Odoo ${depot.version}, ${taille(depot.octets)} (${taille(depot.octets_decompresses)} décompressés, ${nombre(depot.pieces_jointes)} pièces jointes).`;
    await demanderMontee("/api/montees", { depot: depot.jeton, arrivee: Number(f.arrivee.value) });
    f.reset();
  } catch (e) { erreur.textContent = e.message; }
  finally { bouton.disabled = !etatMontees.pret; }
});

function afficherMontees(montees, demandeEnCours) {
  const zone = $("#liste-montees");
  zone.replaceChildren(...montees.map((m) => carteMontee(m, demandeEnCours)));
  if (!montees.length) zone.append(el("div", { class: "carte vide", texte: "Aucune montée pour l'instant." }));
}

function carteMontee(m, demandeEnCours) {
  const etapes = m.etapes || {};
  const erreur = el("p", { class: "erreur", role: "alert" });
  const action = (texte, chemin, corps, danger = false) => el("button", {
    class: "bouton " + (danger ? "danger-bouton" : "principal"), type: "button", texte, disabled: demandeEnCours || !etatMontees.pret,
    onclick: async (ev) => {
      ev.target.disabled = true; erreur.textContent = "";
      try { await demanderMontee(chemin, corps ? corps() : {}); } catch (e) { erreur.textContent = e.message; ev.target.disabled = false; }
    } });
  const base = `/api/montees/${encodeURIComponent(m.id)}`;
  const actions = [];
  if (m.statut === "en_cours") {
    actions.push(el("button", { class: "bouton danger-bouton", type: "button", texte: "Arrêter cette montée",
      onclick: async (ev) => {
        if (!confirm("Arrêter cette montée ?\n\nLe saut en cours s'arrête sous 10 secondes, puis la copie de travail est effacée. La base du client n'est pas touchée.")) return;
        ev.target.disabled = true; ev.target.textContent = "Arrêt demandé…";
        try { await api(base + "/arreter", { method: "POST", corps: {} }); } catch (e) { erreur.textContent = e.message; ev.target.disabled = false; }
      } }));
  }
  if (m.statut === "en_attente" || m.statut === "bloquee") {
    actions.push(action(m.statut === "bloquee" ? "Relancer les vérifications" : "Lancer les vérifications (étapes 1 à 4)", base + "/circuit"));
  }
  if (m.statut === "attente_feu_vert" && (etapes.feu_vert || {}).statut !== "verte") actions.push(formulaireFeuVertMontee(m, base, erreur));
  if ((etapes.feu_vert || {}).statut === "verte" && (etapes.nouvel_essai || {}).statut !== "verte") actions.push(formulaireNouvelEssai(base, erreur));
  if ((etapes.nouvel_essai || {}).statut === "verte" && m.statut !== "livree") actions.push(action("Livrer la base montée", base + "/livrer"));
  if (m.statut === "livree") {
    const infos = etapes.livraison.infos;
    actions.push(el("p", {}, el("a", { href: base + "/livraison", texte: `Télécharger ${infos.fichier} (${taille(infos.octets)})` }),
      el("br"), el("small", { class: "mono", texte: "SHA-256 " + infos.sha256 })));
  }
  return el("div", { class: "carte montee-carte" },
    el("div", { class: "entete-resultat" }, el("h3", { texte: `${m.base_client} — Odoo ${m.depart} → ${m.arrivee}` }), statutPastille(m.statut)),
    el("small", { texte: `Créée le ${dateFr(m.cree_le)} · sauvegarde du client ${taille(m.sauvegarde.octets)}, empreinte ${m.sauvegarde.sha256.slice(0, 12)}` }),
    el("ol", { class: "etapes" }, ETAPES_MONTEE_ECRAN.map(([cle, nom]) => ligneEtapeMontee(nom, etapes[cle] || { statut: "non_jouee" }))),
    etapes.arret ? el("p", { class: "erreur", texte: "Arrêt : " + etapes.arret.erreur }) : null,
    detailsInventaire(m.inventaire), detailsSauts(etapes.sauts), detailsEcarts(etapes.comparaison),
    el("div", { class: "actions" }, actions), erreur);
}

function ligneEtapeMontee(nom, etape) {
  return el("li", {}, el("span", { texte: nom }), statutPastille(etape.statut),
    el("span", { texte: etape.duree_s ? Math.round(etape.duree_s) + " s" : "" }),
    etape.erreur ? el("p", { class: "erreur", texte: etape.erreur }) : null);
}

function listeModules(titre, saut, cle) {
  const modules = saut[cle];
  if (!modules.length) return null;
  return el("div", {}, el("strong", { texte: `${titre} — Odoo ${saut.vers} (${modules.length})` }),
    el("ul", { class: "liste-modules" }, modules.map((x) => el("li", { texte: `${x.module} : ${x.cause}` }))));
}

function detailsInventaire(inventaire) {
  if (!inventaire) return null;
  return el("details", {}, el("summary", { texte: `Inventaire : ${inventaire.modules.length} modules installés${inventaire.bloque ? " — montée bloquée" : ""}` }),
    inventaire.sauts.map((saut) => [listeModules("Bloquants", saut, "bloquants"), listeModules("À vérifier", saut, "a_verifier")]),
    el("p", { class: "note", texte: "Un module bloquant (sur mesure, OCA ou Enterprise) doit être migré par le développeur du client, ou désinstallé avant la montée." }));
}

function detailsSauts(sauts) {
  const infos = (sauts || {}).infos;
  if (!infos || !Object.keys(infos).length) return null;
  return el("details", {}, el("summary", { texte: "Montée, version par version" }),
    el("ul", { class: "liste-modules" }, Object.entries(infos).map(([version, saut]) =>
      el("li", { texte: `Odoo ${version} : ${STATUTS[saut.statut] || saut.statut}, ${Math.round(saut.duree_s)} s`
        + (saut.lignes_erreur ? `, ${saut.lignes_erreur} message(s) d'erreur dans le journal` : "") + (saut.erreur ? " — " + saut.erreur : "") }))));
}

function detailsEcarts(comparaison) {
  const infos = (comparaison || {}).infos;
  if (!infos || !infos.ecarts) return null;
  return el("details", { open: true }, el("summary", { texte: `${infos.ecarts} écart(s) au centime` }),
    el("ul", { class: "liste-modules" }, infos.exemples.slice(0, 50).map((e) =>
      el("li", { texte: `${e.section} ${e.cle} : avant ${e.avant ?? "—"}, après ${e.apres ?? "—"}` }))));
}

function formulaireFeuVertMontee(m, base, erreur) {
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Nom de la base à retaper" });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true, texte: "Donner le feu vert" });
  saisie.addEventListener("input", () => { bouton.disabled = saisie.value !== m.base_client; });
  const form = el("form", { class: "formulaire" },
    el("div", { class: "danger", texte: "Zéro écart au centime. Au feu vert, il faudra une sauvegarde fraîche de la même base, juste avant la bascule : la montée est refaite dessus et doit encore donner zéro écart." }),
    el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: m.base_client })), saisie), bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); bouton.disabled = true; erreur.textContent = "";
    try { await demanderMontee(base + "/feu-vert", { confirmation: saisie.value }); } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  return form;
}

function formulaireNouvelEssai(base, erreur) {
  const fichier = el("input", { type: "file", accept: ".zip,application/zip", required: true });
  const bouton = el("button", { class: "bouton principal", type: "submit", texte: "Déposer et refaire la montée" });
  const form = el("form", { class: "formulaire" },
    el("label", {}, "Sauvegarde fraîche de la même base (.zip)", fichier), bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!fichier.files.length) return;
    bouton.disabled = true; erreur.textContent = "";
    try {
      const depot = await deposerSauvegarde(fichier.files[0]);
      await demanderMontee(base + "/nouvel-essai", { depot: depot.jeton });
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  return form;
}
