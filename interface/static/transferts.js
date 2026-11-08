// CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
// Écran Transferts (ADR-0011) : connexions, dépôts de FEC, transferts, feu vert.
// Chargé avant app.js : n'utilise ses outils ($, el, api, suivre…) qu'à
// l'appel des fonctions ; au chargement, seulement document.getElementById. Toute donnée reçue est
// insérée en TEXTE. Un secret saisi part une fois et ne revient jamais.
"use strict";

const ETAPES_TRANSFERT = [
  ["donnees", "1. Vérifier les données"],
  ["concordance", "2. Vérifier la concordance"],
  ["simulation", "3. Simuler le résultat"],
  ["test", "4. Test de transfert"],
  ["feu_vert", "5. Feu vert"],
  ["nouveau_test", "6. Nouveau test"],
  ["transfert", "7. Transfert complet"],
];
const NOMS_FICHIERS = { "a_arbitrer.xlsx": "Comptes à arbitrer (xlsx)",
                        "FEC_source.txt": "Photo de la source (FEC)" };
const etatTransferts = { logiciels: [], depotMax: 0, connexions: [] };

// --- outils ------------------------------------------------------------------
async function envoyerFichier(chemin, fichier) {
  if (fichier.size > etatTransferts.depotMax && chemin.includes("/depot")) {
    throw new Error(`Fichier trop gros : ${taille(fichier.size)} (maximum ${taille(etatTransferts.depotMax)}).`);
  }
  return api(chemin + "?nom=" + encodeURIComponent(fichier.name), { method: "POST", fichier });
}
const logicielBranche = (nom) => etatTransferts.logiciels.find((l) => l.logiciel === nom) || {};
const champLibre = (nom) => nom.replace(/_/g, " ");
function sertDe(c) {
  if (c.usage === "source") return "source (FEC déposé)";
  if (c.usage === "destination") return "destination (FEC produit)";
  return [c.lecture ? "source" : null, c.ecriture ? "destination" : null].filter(Boolean).join(" et ") || "—";
}
function tiroir(titre, ...contenu) {
  $("#voile").hidden = false;
  $("#tiroir-titre").textContent = titre;
  $("#tiroir-contenu").replaceChildren(...contenu);
}

// --- chargement ----------------------------------------------------------------
async function chargerEcranTransferts() {
  const [description, connexions] = await Promise.all([api("/api/logiciels"), api("/api/connexions")]);
  etatTransferts.logiciels = description.logiciels;
  etatTransferts.depotMax = description.depot_max;
  etatTransferts.connexions = connexions;
  afficherConnexions();
  preparerAjout();
  preparerTransfert();
  chargerListeTransferts();
}

// --- connexions ------------------------------------------------------------------
function afficherConnexions() {
  const corps = $("#table-connexions tbody");
  const liste = etatTransferts.connexions;
  corps.replaceChildren(...liste.map((c) => el("tr", {},
    el("td", {}, el("strong", { texte: c.libelle }), el("br"), el("small", { class: "mono", texte: c.id }),
      c.depot ? [el("br"), el("small", { texte: `FEC déposé : ${c.depot.nom} — ${nombre(c.depot.lignes)} lignes, ${nombre(c.depot.ecritures)} écritures, le ${dateFr(c.depot.depose_le)}` })] : null),
    el("td", { texte: c.logiciel_libelle }),
    el("td", {}, sertDe(c), c.connexion_test ? [el("br"), el("small", { texte: "test : " + libelleConnexion(c.connexion_test) })] : null),
    el("td", {}, c.secrets_erreur ? el("span", { class: "erreur", texte: c.secrets_erreur })
      : Object.keys(c.secrets).length ? Object.entries(c.secrets).map(([champ, ok]) =>
        el("div", {}, el("span", { class: "statut " + (ok ? "verte" : "bloquee"), texte: ok ? "renseigné" : "manquant" }), " ", champLibre(champ)))
        : "aucun"),
    el("td", {}, c.dernier_test ? dateFr(c.dernier_test) : "jamais"),
    el("td", {}, el("div", { class: "actions" },
      el("button", { class: "bouton petit", type: "button", texte: "Tester", onclick: () => testerConnexion(c) }),
      Object.keys(c.secrets).length ? el("button", { class: "bouton petit", type: "button", texte: "Saisir un secret",
        onclick: () => dialogueSecret(c) }) : null,
      c.usage === "source" ? el("button", { class: "bouton petit", type: "button", texte: "Déposer un FEC",
        onclick: () => dialogueDepot(c) }) : null,
      el("button", { class: "bouton petit", type: "button", texte: "Retirer", onclick: () => retirerConnexion(c) }))))));
  if (!liste.length) corps.append(el("tr", {}, el("td", { colspan: 6, class: "vide", texte: "Aucune connexion : ajoutez-en une ci-dessous." })));
}
function libelleConnexion(ident) {
  const c = etatTransferts.connexions.find((x) => x.id === ident);
  return c ? c.libelle : ident;
}

async function testerConnexion(c) {
  tiroir("Tester « " + c.libelle + " »", el("div", { class: "progression" }, el("span", { class: "roue" }), el("span", { texte: "Essai en cours…" })));
  try {
    const relue = await api(`/api/connexions/${encodeURIComponent(c.id)}/tester`, { method: "POST", corps: {} });
    const info = relue.derniere_info || {};
    tiroir("Connexion bonne — " + c.libelle, el("div", { class: "carte" },
      el("span", { class: "statut verte", texte: "connexion bonne" }),
      el("dl", {}, Object.entries(info).flatMap(([cle, valeur]) => [el("dt", { texte: champLibre(cle) }), el("dd", { texte: String(valeur ?? "—") })]))));
  } catch (e) {
    tiroir("Connexion refusée — " + c.libelle, el("p", { class: "erreur", texte: e.message }));
  }
  await rechargerConnexions();
}

function dialogueSecret(c) {
  const champ = el("select", { name: "champ" }, Object.keys(c.secrets).map((nom) => el("option", { value: nom, texte: champLibre(nom) })));
  const valeur = el("input", { type: "password", name: "valeur", autocomplete: "new-password", required: true, spellcheck: "false" });
  const erreur = el("p", { class: "erreur", role: "alert" });
  const form = el("form", { class: "formulaire", autocomplete: "off" },
    el("p", { class: "aide", texte: "Le secret est écrit sur le serveur (fichier lisible par CONCORDE seul) et ne sera plus jamais affiché. Pour le changer, retapez-le en entier." }),
    el("label", {}, "Secret", champ), el("label", {}, "Valeur", valeur), erreur,
    el("button", { class: "bouton principal", type: "submit", texte: "Enregistrer" }));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    erreur.textContent = "";
    try {
      await api(`/api/connexions/${encodeURIComponent(c.id)}/secret`, { method: "POST", corps: { champ: champ.value, valeur: valeur.value } });
      valeur.value = "";
      fermerTiroir();
      await rechargerConnexions();
    } catch (e) { erreur.textContent = e.message; }
  });
  tiroir("Secret de « " + c.libelle + " »", form);
  valeur.focus();
}

function dialogueDepot(c) {
  const fichier = el("input", { type: "file", name: "fec", accept: ".txt,.csv,.fec,.xml,text/plain", required: true });
  const erreur = el("p", { class: "erreur", role: "alert" });
  const bouton = el("button", { class: "bouton principal", type: "submit", texte: "Déposer et vérifier" });
  const form = el("form", { class: "formulaire" },
    el("p", { class: "aide", texte: `Export FEC du logiciel, ${taille(etatTransferts.depotMax)} au plus. Il est relu tout de suite ; s'il est refusé, rien n'est gardé et l'ancien dépôt reste en place.` }),
    el("label", {}, "Fichier FEC", fichier), erreur, bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!fichier.files.length) return;
    erreur.textContent = ""; bouton.disabled = true;
    try {
      const depot = await envoyerFichier(`/api/connexions/${encodeURIComponent(c.id)}/depot`, fichier.files[0]);
      tiroir("FEC accepté — " + c.libelle, el("div", { class: "carte" },
        el("span", { class: "statut verte", texte: "FEC accepté" }),
        el("p", { texte: `${depot.nom} : ${nombre(depot.lignes)} lignes, ${nombre(depot.ecritures)} écritures, débit ${centimes(depot.debit)} €, crédit ${centimes(depot.credit)} €.` })));
      await rechargerConnexions();
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  tiroir("Déposer un FEC — " + c.libelle, form);
}

async function retirerConnexion(c) {
  if (!confirm(`Retirer la connexion « ${c.libelle} » de CONCORDE ?\n\nSes secrets et son FEC déposé sont effacés. Rien ne change dans le logiciel lui-même.`)) return;
  try {
    await api("/api/connexions/" + encodeURIComponent(c.id), { method: "DELETE" });
  } catch (e) { alert(e.message); }
  await rechargerConnexions();
}

async function rechargerConnexions() {
  etatTransferts.connexions = await api("/api/connexions");
  afficherConnexions();
  preparerAjout(false);
  preparerTransfert();
}

// --- ajouter une connexion ------------------------------------------------------------
function preparerAjout(remplirLogiciels = true) {
  const choix = $("#ajout-logiciel");
  if (remplirLogiciels || !choix.options.length) {
    const garde = choix.value;
    choix.replaceChildren(...etatTransferts.logiciels.map((l) => el("option", { value: l.logiciel, texte: l.libelle })));
    if (garde) choix.value = garde;
  }
  majFormulaireAjout();
}

function majFormulaireAjout() {
  const l = logicielBranche($("#ajout-logiciel").value);
  $("#ajout-usage").hidden = !l.fichier;
  $("#ajout-parametres").replaceChildren(
    ...(l.parametres || []).map((nom) => el("label", {}, champLibre(nom), el("input", { name: "p_" + nom, required: true }))),
    ...(l.facultatifs || []).map((nom) => el("label", {}, champLibre(nom) + " (facultatif)", el("input", { name: "p_" + nom }))));
  $("#ajout-secrets").replaceChildren(...(l.secrets || []).map((nom) => el("label", {}, champLibre(nom) + " (secret)",
    el("input", { name: "s_" + nom, type: "password", autocomplete: "new-password", spellcheck: "false" }))));
  const tests = etatTransferts.connexions.filter((c) => c.logiciel === l.logiciel);
  $("#ajout-test-zone").hidden = l.fichier || !tests.length;
  $("#ajout-test").replaceChildren(el("option", { value: "", texte: "aucun" }),
    ...tests.map((c) => el("option", { value: c.id, texte: c.libelle })));
  $("#ajout-note").textContent = [
    l.lecture ? null : "Ce logiciel ne sert que de destination.",
    l.ecriture ? null : "Ce logiciel ne sert que de source (lecture seule).",
    l.fichier ? "CONCORDE range lui-même les fichiers : aucun chemin à donner." : null,
  ].filter(Boolean).join(" ");
}
document.getElementById("ajout-logiciel").addEventListener("change", majFormulaireAjout);

document.getElementById("form-ajout-connexion").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const bouton = $("button[type=submit]", f);
  const erreur = $("#erreur-ajout-connexion");
  erreur.textContent = ""; bouton.disabled = true;
  const d = new FormData(f);
  const parametres = {};
  const secretsSaisis = {};
  for (const [nom, valeur] of d.entries()) {
    if (nom.startsWith("p_") && valeur) parametres[nom.slice(2)] = valeur;
    if (nom.startsWith("s_") && valeur) secretsSaisis[nom.slice(2)] = valeur;
  }
  try {
    const fiche = await api("/api/connexions", { method: "POST", corps: {
      logiciel: d.get("logiciel"), libelle: d.get("libelle"), usage: d.get("usage"),
      connexion_test: d.get("connexion_test") || null, parametres } });
    for (const [champ, valeur] of Object.entries(secretsSaisis)) {
      await api(`/api/connexions/${encodeURIComponent(fiche.id)}/secret`, { method: "POST", corps: { champ, valeur } });
    }
    f.reset();
    await rechargerConnexions();
  } catch (e) { erreur.textContent = e.message; }
  finally {
    $$("input[type=password]", f).forEach((champ) => { champ.value = ""; });
    bouton.disabled = false;
  }
});

// --- nouveau transfert ------------------------------------------------------------------
function preparerTransfert() {
  const source = $("#transfert-source");
  const garde = source.value;
  const sources = etatTransferts.connexions.filter((c) => c.lecture);
  source.replaceChildren(el("option", { value: "", texte: sources.length ? "choisir…" : "aucune connexion source" }),
    ...sources.map((c) => el("option", { value: c.id, texte: `${c.libelle} (${c.logiciel_libelle})` })));
  if (sources.some((c) => c.id === garde)) source.value = garde;
  majDestinations();
}

function majDestinations() {
  const source = $("#transfert-source").value;
  const zone = $("#transfert-destinations");
  const dests = etatTransferts.connexions.filter((c) => c.ecriture && c.id !== source);
  zone.replaceChildren(...dests.map((c) => el("div", { class: "destination-choix", "data-destination": c.id },
    el("label", { class: "case" }, el("input", { type: "checkbox", name: "destination", value: c.id }),
      el("strong", { texte: c.libelle }), ` (${c.logiciel_libelle})`),
    el("div", { class: "ligne-champs" },
      el("label", { class: "case" }, el("input", { type: "checkbox", name: "identique" }), "Plan comptable identique (numéros repris tels quels)"),
      el("label", {}, "ou table de correspondance (xlsx, csv, json)", el("input", { type: "file", name: "table", accept: ".xlsx,.csv,.txt,.json" }))))));
  if (!dests.length) zone.append(el("p", { class: "note", texte: "Aucune destination possible : ajoutez une connexion qui sait écrire." }));
}
document.getElementById("transfert-source").addEventListener("change", majDestinations);

document.getElementById("form-transfert").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const bouton = $("button[type=submit]", f);
  const erreur = $("#erreur-transfert");
  erreur.textContent = ""; bouton.disabled = true;
  try {
    const corps = { source: f.source.value, du: f.du.value || null, au: f.au.value || null,
                    destinations: [], identique: {}, tables: {} };
    for (const bloc of $$(".destination-choix", f)) {
      if (!$("input[name=destination]", bloc).checked) continue;
      const ident = bloc.dataset.destination;
      corps.destinations.push(ident);
      corps.identique[ident] = $("input[name=identique]", bloc).checked;
      const table = $("input[name=table]", bloc).files[0];
      if (table) corps.tables[ident] = (await envoyerFichier("/api/tables", table)).jeton;
    }
    const { id } = await api("/api/transferts", { method: "POST", corps });
    suivreTransfert(id, $("#resultat-transfert"));
  } catch (e) { erreur.textContent = e.message; }
  finally { bouton.disabled = false; }
});

// Suit une tâche de transfert ou de feu vert, puis ouvre le transfert.
function suivreTransfert(id, zone) {
  suivre(id, zone);
  const attendre = async () => {
    const t = await api("/api/taches/" + id).catch(() => null);
    if (t && (t.statut === "en_cours" || t.statut === "en_attente")) return setTimeout(attendre, 1500);
    await chargerListeTransferts();
    if (t && t.resultat && t.resultat.transfert) ouvrirTransfert(t.resultat.transfert);
  };
  setTimeout(attendre, 1500);
}

function rendreTacheTransfert(t) {
  const r = t.resultat || {};
  const statuts = r.destinations || (r.destination ? { [r.destination]: r.statut } : {});
  return el("div", { class: "carte" },
    el("div", { class: "entete-resultat" }, el("h2", { texte: (ACTIONS[t.action] || t.action) + " — " + t.base }), statutPastille(t.statut)),
    el("ul", {}, Object.entries(statuts).map(([ident, statut]) =>
      el("li", {}, libelleConnexion(ident), " : ", statutPastille(statut)))),
    r.transfert ? el("button", { class: "bouton petit", type: "button", texte: "Ouvrir le transfert",
      onclick: () => { location.hash = "#transferts"; ouvrirTransfert(r.transfert); } }) : null);
}

// --- transferts enregistrés ------------------------------------------------------------------
async function chargerListeTransferts() {
  const liste = await api("/api/transferts");
  const corps = $("#table-transferts tbody");
  corps.replaceChildren(...liste.map((t) => el("tr", {},
    el("td", { class: "mono", texte: dateFr(t.cree_le) }),
    el("td", { texte: t.source }),
    el("td", {}, t.destinations.map((d) => el("div", {}, d.libelle, " ", statutPastille(d.statut)))),
    el("td", {}, el("button", { class: "bouton petit", type: "button", texte: "Ouvrir", onclick: () => ouvrirTransfert(t.id) })))));
  if (!liste.length) corps.append(el("tr", {}, el("td", { colspan: 4, class: "vide", texte: "Aucun transfert pour l'instant." })));
}

async function ouvrirTransfert(ident) {
  const zone = $("#detail-transfert");
  let t;
  try { t = await api("/api/transferts/" + encodeURIComponent(ident)); } catch (e) {
    zone.replaceChildren(el("div", { class: "carte erreur", texte: e.message })); return;
  }
  const lien = (chemin) => el("a", { href: `/api/transferts/${encodeURIComponent(ident)}/fichier?chemin=${encodeURIComponent(chemin)}`,
    texte: NOMS_FICHIERS[chemin.split("/").at(-1)] || chemin });
  const source = t.fichiers.filter((chemin) => chemin.startsWith("source/"));
  zone.replaceChildren(el("div", { class: "carte" },
    el("div", { class: "entete-resultat" }, el("h2", { texte: "Transfert " + t.id }), el("small", { texte: dateFr(t.cree_le) })),
    el("p", {}, "Source : ", el("strong", { texte: t.libelles[t.demande.source] }),
      t.demande.du || t.demande.au ? ` — du ${dateFr(t.demande.du) } au ${dateFr(t.demande.au)}` : " — toute la période"),
    source.length ? el("ul", { class: "fichiers-transfert" }, source.map((chemin) => el("li", {}, lien(chemin)))) : null),
    ...Object.entries(t.destinations).map(([dest, etatDest]) => carteDestination(t, dest, etatDest, lien)));
  zone.scrollIntoView({ behavior: "smooth", block: "start" });
}

function carteDestination(t, dest, etatDest, lien) {
  const libelle = t.libelles[dest];
  const fichiers = t.fichiers.filter((chemin) => chemin.startsWith(dest + "/"));
  return el("div", { class: "carte destination-carte" },
    el("div", { class: "entete-resultat" }, el("h3", { texte: libelle }), statutPastille(etatDest.statut)),
    el("ol", { class: "etapes" }, ETAPES_TRANSFERT.map(([cle, nom]) => {
      const etape = (etatDest.etapes || {})[cle] || { statut: "non_jouee" };
      const constats = (etape.constats || []).filter((c) => c.niveau && c.niveau !== "OK");
      return el("li", {}, el("span", { texte: nom }), statutPastille(etape.statut),
        el("span", {}, constats.length ? `${constats.length} constat(s)` : ""),
        etape.erreur ? el("p", { class: "erreur", texte: etape.erreur }) : null,
        constats.length ? el("small", {}, constats.slice(0, 5).map((c) => el("div", { texte: `${c.niveau} — ${c.message} (${nombre(c.nombre)})` }))) : null);
    })),
    fichiers.length ? el("ul", { class: "fichiers-transfert" }, fichiers.map((chemin) => el("li", {}, lien(chemin)))) : null,
    etatDest.statut === "attente_feu_vert" ? formulaireFeuVert(t, dest, libelle) : null);
}

function formulaireFeuVert(t, dest, libelle) {
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Nom de la destination à retaper" });
  const sauvegarde = el("input", { type: "date", required: true, max: aujourdhui() });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true, texte: "Donner le feu vert" });
  const erreur = el("p", { class: "erreur", role: "alert" });
  const majBouton = () => { bouton.disabled = saisie.value !== libelle || !sauvegarde.value; };
  saisie.addEventListener("input", majBouton);
  sauvegarde.addEventListener("input", majBouton);
  const form = el("form", { class: "formulaire" },
    el("div", { class: "danger", texte: "Au feu vert, CONCORDE refait un test complet, puis écrit pour de bon dans cette destination et relit tout au centime. Vérifiez d'abord qu'une sauvegarde de la destination existe." }),
    el("div", { class: "ligne-champs" },
      el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: libelle })), saisie),
      el("label", {}, "Date de la dernière sauvegarde de la destination", sauvegarde)),
    erreur, bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    erreur.textContent = ""; bouton.disabled = true;
    try {
      const { id } = await api(`/api/transferts/${encodeURIComponent(t.id)}/feu-vert`, { method: "POST",
        corps: { destination: dest, confirmation: saisie.value, sauvegarde_du: sauvegarde.value } });
      suivreTransfert(id, $("#resultat-feu_vert"));
      $("#resultat-feu_vert").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { erreur.textContent = e.message; majBouton(); }
  });
  return form;
}
