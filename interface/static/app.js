// CONCORDE — (c) MASITH / Stéphane Moreau. Tous droits réservés.
// Interface sans dépendance. Toute donnée venue d'Odoo est insérée en TEXTE
// (textContent), jamais en HTML.
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const ACTIONS = { analyser: "Analyse", telecharger: "Téléchargement", comparer: "Comparaison",
                  supprimer_base: "Suppression de base", reinitialiser_base: "Réinitialisation",
                  transfert: "Transfert", feu_vert: "Feu vert",
                  siret_proposer: "SIRET et TVA — propositions", siret_ecrire: "SIRET et TVA — écriture",
                  siret_annuler: "SIRET et TVA — annulation",
                  peppol_verifier: "Facture électronique — vérification",
                  peppol_ecrire: "Facture électronique — écriture",
                  peppol_annuler: "Facture électronique — annulation" };
// Vue qui affiche le résultat d'une action, quand elle ne porte pas son nom.
const VUE_ACTION = { transfert: "transferts", feu_vert: "transferts", peppol_verifier: "peppol",
                     peppol_ecrire: "peppol", peppol_annuler: "peppol" };
const STATUTS = {
  en_attente: "En attente", en_cours: "En cours", terminee: "Terminée",
  echec: "Échec", interrompue: "Interrompue",
  conforme: "Conforme", alertes: "Alertes", bloquant: "Bloquant",
  verte: "Bonne", bloquee: "Bloquée", non_jouee: "Pas encore faite",
  attente_feu_vert: "Attend le feu vert", arretee_sans_test: "Arrêtée sans test",
  transferee: "Transférée", livree: "Livrée", arretee: "Arrêtée",
};

// --- utilitaires ------------------------------------------------------------
function el(tag, attrs = {}, ...enfants) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "texte") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const e of enfants.flat()) {
    if (e === null || e === undefined || e === false) continue;
    n.append(e instanceof Node ? e : document.createTextNode(String(e)));
  }
  return n;
}

// Appel de l'API : options.corps (objet JSON) ou options.fichier (envoyé brut).
async function api(chemin, options = {}) {
  const init = { method: options.method || "GET", credentials: "same-origin",
                 headers: { "X-Concorde": "1" } };
  if (options.corps !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.corps);
  }
  if (options.fichier !== undefined) {
    init.headers["Content-Type"] = "application/octet-stream";
    init.body = options.fichier;
  }
  const r = await fetch(chemin, init);
  let donnees = {};
  try { donnees = await r.json(); } catch (_) { /* corps vide */ }
  if (r.status === 401 && chemin !== "/api/connexion") { afficherConnexion(); }
  if (!r.ok) throw new Error(donnees.erreur || ("Erreur " + r.status));
  return donnees;
}

const memo = {
  lire(k) { try { return localStorage.getItem("concorde." + k); } catch (_) { return null; } },
  ecrire(k, v) { try { localStorage.setItem("concorde." + k, v); } catch (_) { /* privé */ } },
};

function dateFr(iso) {
  if (!iso) return "—";
  const [a, m, j] = iso.slice(0, 10).split("-");
  return `${j}/${m}/${a}` + (iso.length > 10 ? " " + iso.slice(11, 16) : "");
}
function taille(o) {
  if (o < 1024) return o + " o";
  if (o < 1048576) return (o / 1024).toFixed(0) + " Ko";
  return (o / 1048576).toFixed(1).replace(".", ",") + " Mo";
}
const nombre = (n) => (n ?? 0).toLocaleString("fr-FR");
function euros(texte) {
  // "357998068,68" -> "357 998 068,68 €" (texte exact, jamais de float)
  if (!texte) return "—";
  const [ent, dec] = texte.split(",");
  const signe = ent.startsWith("-") ? "-" : "";
  const e = ent.replace("-", "").replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${signe}${e},${dec} €`;
}
function statutPastille(s) {
  return el("span", { class: "statut " + s, texte: STATUTS[s] || s });
}

// --- état ---------------------------------------------------------------------
const etat = { bases: [], suivi: {} };

function baseCourante() { return $("#base").value; }

// --- connexion ----------------------------------------------------------------
function afficherConnexion() {
  $("#ecran-app").hidden = true;
  $("#ecran-connexion").hidden = false;
  $("#mdp").focus();
}

async function demarrer() {
  const { connecte, version } = await api("/api/etat");
  if (!connecte) return afficherConnexion();
  $("#version-concorde").textContent = "version " + version;
  $("#ecran-connexion").hidden = true;
  $("#ecran-app").hidden = false;
  await chargerBases();
  router();
  rafraichirCloche();
  if (!etat.minuterieCloche) etat.minuterieCloche = setInterval(rafraichirCloche, 30000);
}

$("#form-connexion").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("#erreur-connexion").textContent = "";
  const bouton = $("#form-connexion button");
  bouton.disabled = true;
  try {
    await api("/api/connexion", { method: "POST", corps: { mdp: $("#mdp").value } });
    $("#mdp").value = "";
    await demarrer();
  } catch (e) {
    $("#erreur-connexion").textContent = e.message;
  } finally {
    bouton.disabled = false;
  }
});

$("#deconnexion").addEventListener("click", async () => {
  await api("/api/deconnexion", { method: "POST", corps: {} }).catch(() => {});
  afficherConnexion();
});

// --- navigation ---------------------------------------------------------------
function router() {
  const vue = (location.hash || "#alertes").slice(1);
  const existe = $("#vue-" + vue) ? vue : "alertes";
  $$(".vue").forEach((v) => { v.hidden = v.id !== "vue-" + existe; });
  $$(".menu nav a").forEach((a) => a.classList.toggle("actif", a.dataset.vue === existe));
  if (existe === "historique") chargerHistorique();
  if (existe === "alertes") chargerAlertes();
  if (existe === "journal") suivreJournal();
  if (existe === "rapport" && !etat.rapport) chargerRapport();
  if (existe === "bases") { afficherBases(); chargerCles(); chargerSauvegardes(); }
  if (existe === "transferts") chargerEcranTransferts();
  if (existe === "montees") chargerEcranMontees();
  if (existe === "peppol") chargerEcranPeppol();
}
window.addEventListener("hashchange", router);

// --- bases ---------------------------------------------------------------------
async function chargerBases(rafraichir = false) {
  const { bases } = await api("/api/bases" + (rafraichir ? "?rafraichir=1" : ""));
  etat.bases = bases;
  const sel = $("#base");
  const avant = sel.value || memo.lire("base");
  sel.replaceChildren(...bases.map((b) =>
    el("option", { value: b.id, texte: nomBase(b) })));
  $$(".choix-bases").forEach((s, i) => {
    const garde = s.value;
    s.replaceChildren(...bases.map((b) => el("option", { value: b.id, texte: nomBase(b) })));
    if (bases.some((b) => b.id === garde)) s.value = garde;
    else if (bases[i]) s.value = bases[i].id;
  });
  if (!bases.length) sel.append(el("option", { value: "", texte: "Aucune base Odoo 17 trouvée" }));
  if (bases.some((b) => b.id === avant)) sel.value = avant;
  majInfoBase();
}

function majInfoBase() {
  const b = etat.bases.find((x) => x.id === baseCourante());
  memo.ecrire("base", baseCourante());
  $("#base-info").textContent = b
    ? `Odoo ${b.version} · ${b.devise} · lecture ${b.source === "sql" ? "SQL" : "API"}, écriture API ${b.ecriture_ok ? "prête" : "à configurer"}`
      + (b.siren ? "" : " · SIREN non renseigné")
    : "";
}
$("#base").addEventListener("change", majInfoBase);

function afficherBases() {
  const corps = $("#table-bases tbody");
  corps.replaceChildren(...etat.bases.map((b) => el("tr", {},
    el("td", {}, el("strong", { texte: b.libelle || b.nom }),
      b.libelle ? el("br") : null, b.libelle ? el("small", { class: "mono", texte: b.nom }) : null),
    el("td", { texte: b.societe }),
    el("td", { texte: b.devise }),
    el("td", { class: "mono", texte: b.siren || "—" }),
    el("td", {}, b.lecture,
      b.source === "xmlrpc" && !b.cle_presente ? el("span", { class: "pastille", texte: " clé supprimée" }) : null),
    el("td", {}, el("span", { class: "statut " + (b.ecriture_ok ? "terminee" : "en_attente"),
                              texte: b.ecriture_ok ? "prête" : "à configurer" }),
      " ", el("small", { texte: b.ecriture.replace(/^API Odoo — /, "par l'API Odoo — ") })),
    el("td", {}, el("div", { class: "actions" }, boutonRenommer(b), b.source === "xmlrpc"
      ? [b.cle_presente
          ? el("button", { class: "bouton petit", type: "button", texte: "Supprimer la clé",
              title: "Efface la clé API de CONCORDE. Rien ne change chez le client.",
              onclick: async () => {
                if (!confirm(`Supprimer de CONCORDE la clé API de « ${b.nom} » ?\n\nLa base reste dans la liste, déconnectée. Rien ne change chez le client.`)) return;
                await api("/api/distants/" + encodeURIComponent(b.id) + "/cle", { method: "DELETE" });
                await chargerBases(); afficherBases();
              } })
          : el("button", { class: "bouton petit", type: "button", texte: "Saisir une clé",
              onclick: async () => {
                const cle = prompt(`Nouvelle clé API pour « ${b.nom} » (${b.utilisateur}) :`);
                if (!cle) return;
                try {
                  await api("/api/distants/" + encodeURIComponent(b.id) + "/cle", { method: "POST", corps: { cle } });
                } catch (e) { alert(e.message); }
                await chargerBases(); afficherBases();
              } }),
        el("button", { class: "bouton petit", type: "button", texte: "Retirer de CONCORDE",
          title: "Enlève cette base de la liste. Rien n'est supprimé chez le client.",
          onclick: async () => {
            if (!confirm(`Retirer « ${b.nom} » de la liste de CONCORDE ?\n\nRien n'est supprimé chez le client.`)) return;
            await api("/api/distants/" + encodeURIComponent(b.id), { method: "DELETE" });
            await chargerBases(); afficherBases();
          } })]
      : [b.modele ? el("button", { class: "bouton petit", type: "button", texte: "Réinitialiser…",
          onclick: () => dialogueBase(b, "reinitialiser_base") }) : null,
         b.protegee ? el("span", { class: "pastille", texte: "protégée" })
           : el("button", { class: "bouton petit", type: "button", texte: "Supprimer…",
               onclick: () => dialogueBase(b, "supprimer_base") })])))));
  if (!etat.bases.length) corps.append(el("tr", {}, el("td", { colspan: 7, class: "vide", texte: "Aucune base." })));
}
// Nom parlant d'une base : « Client A — copie du 14/10 (base_test) ».
function nomBase(b) {
  return b.libelle ? `${b.libelle} (${b.nom})` : `${b.nom} — ${b.societe}`;
}

function boutonRenommer(b) {
  return el("button", { class: "bouton petit", type: "button", texte: b.libelle ? "Renommer" : "Nommer",
    title: "Donner un nom parlant à cette base (vide pour le retirer)",
    onclick: async () => {
      const libelle = prompt(`Nom parlant pour la base « ${b.nom} » (${b.societe}) :\nex. « Client A — production », « Client A — copie du 14/10 »`, b.libelle || "");
      if (libelle === null) return;
      try {
        await api("/api/bases/nom", { method: "POST", corps: { base_id: b.id, libelle } });
      } catch (e) { alert(e.message); return; }
      await chargerBases(); afficherBases();
    } });
}

async function chargerCles() {
  const corps = $("#table-cles tbody");
  let r;
  try { r = await api("/api/cles"); } catch (e) {
    corps.replaceChildren(el("tr", {}, el("td", { colspan: 6, class: "erreur", texte: e.message }))); return;
  }
  corps.replaceChildren(...r.cles.map((k) => el("tr", {},
    el("td", { texte: k.base }), el("td", {}, el("strong", { texte: k.nom || "(sans nom)" })),
    el("td", { texte: k.login }), el("td", { texte: k.portee }),
    el("td", { class: "mono", texte: dateFr(k.cree_le) }),
    el("td", {}, el("button", { class: "bouton petit", type: "button", texte: "Révoquer…",
      onclick: () => dialogueRevocation(k) })))));
  if (!r.cles.length) corps.append(el("tr", {}, el("td", { colspan: 6, class: "vide", texte: "Aucune clé API dans les bases du serveur." })));
}

function dialogueRevocation(k) {
  $("#voile").hidden = false;
  $("#tiroir-titre").textContent = `Révoquer la clé « ${k.nom} »`;
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false",
                               "aria-label": "Nom de la clé à retaper" });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true, texte: "Révoquer la clé" });
  const msg = el("p", { class: "erreur", role: "alert" });
  saisie.addEventListener("input", () => { bouton.disabled = saisie.value !== k.nom; });
  const form = el("form", { class: "formulaire" },
    el("p", {}, `Base « ${k.base} » (ce serveur) — utilisateur ${k.login}, créée le ${dateFr(k.cree_le)}.`),
    el("div", { class: "danger", texte: "Tout outil qui utilise cette clé sera refusé immédiatement. Pour le reconnecter, il faudra créer une nouvelle clé dans Odoo." }),
    el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: k.nom })), saisie),
    msg, bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    bouton.disabled = true;
    try {
      await api("/api/cles/revoquer", { method: "POST", corps: { base: k.base, id: k.id, confirmation: saisie.value } });
      $("#tiroir-contenu").replaceChildren(el("p", { class: "statut terminee", texte: `Clé « ${k.nom} » révoquée.` }));
      chargerCles();
    } catch (e) { msg.textContent = e.message; bouton.disabled = false; }
  });
  $("#tiroir-contenu").replaceChildren(form);
  saisie.focus();
}

async function chargerSauvegardes() {
  let r;
  try { r = await api("/api/sauvegardes"); } catch (_) { return; }
  const corps = $("#table-sauvegardes tbody");
  corps.replaceChildren(...r.sauvegardes.map((x) => el("tr", {},
    el("td", { class: "mono", texte: dateFr(x.date) }), el("td", { texte: x.base }),
    el("td", { class: "mono", texte: x.fichier }), el("td", { class: "mono", texte: taille(x.taille) }))));
  if (!r.sauvegardes.length) corps.append(el("tr", {}, el("td", { colspan: 4, class: "vide", texte: "Aucune sauvegarde." })));
}

function dialogueBase(b, action) {
  const suppr = action === "supprimer_base";
  $("#voile").hidden = false;
  $("#tiroir-titre").textContent = (suppr ? "Supprimer la base " : "Réinitialiser la base ") + b.nom;
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false",
                               "aria-label": "Nom de la base à retaper" });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true,
                                texte: !suppr ? "Réinitialiser" : b.modele ? "Supprimer" : "Sauvegarder puis supprimer" });
  const erreur = el("p", { class: "erreur", role: "alert" });
  const suivi = el("div", { id: "suivi-base" });
  saisie.addEventListener("input", () => { bouton.disabled = saisie.value !== b.nom; });
  const form = el("form", { class: "formulaire" },
    el("p", {}, `Base « ${b.nom} » — ${b.societe} (${b.devise}), sur ce serveur.`),
    el("div", { class: "danger" }, !suppr
      ? "Base de test : elle sera supprimée puis recréée vierge depuis son modèle, sans sauvegarde. Tout ce qu'elle contient sera perdu."
      : b.modele
        ? "Base de test : elle sera supprimée sans sauvegarde. La suppression est définitive (son modèle vierge reste disponible)."
        : "Copie de base client : elle sera supprimée de l'Odoo du serveur, après une sauvegarde complète vérifiée, gardée 7 jours. Si la sauvegarde échoue, rien n'est supprimé. Rien ne change chez le client."),
    el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: b.nom })), saisie),
    erreur, bouton, suivi);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (saisie.value !== b.nom) return;
    bouton.disabled = true; saisie.disabled = true; erreur.textContent = "";
    try {
      const { id } = await api("/api/taches", { method: "POST",
        corps: { action, base_id: b.id, confirmation: saisie.value } });
      suivre(id, suivi);
      const attendre = async () => {
        const t = await api("/api/taches/" + id).catch(() => null);
        if (t && (t.statut === "en_cours" || t.statut === "en_attente")) return setTimeout(attendre, 1500);
        await chargerBases(true); afficherBases(); chargerSauvegardes();
      };
      setTimeout(attendre, 1500);
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; saisie.disabled = false; }
  });
  $("#tiroir-contenu").replaceChildren(form);
  saisie.focus();
}

$("#rafraichir-bases").addEventListener("click", async () => { await chargerBases(true); afficherBases(); });

$("#form-distant").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const bouton = $("button", f);
  $("#erreur-distant").textContent = "";
  bouton.disabled = true;
  try {
    const d = Object.fromEntries(new FormData(f));
    const { id } = await api("/api/distants", { method: "POST", corps: d });
    f.reset();
    await chargerBases();
    $("#base").value = id; majInfoBase(); afficherBases();
  } catch (e) {
    $("#erreur-distant").textContent = e.message;
  } finally {
    bouton.disabled = false;
  }
});

// --- tâches ----------------------------------------------------------------------
async function lancer(action, formulaire, zone) {
  const d = new FormData(formulaire);
  const corps = {
    action, base_id: baseCourante(),
    du: d.get("du") || null, au: d.get("au") || null,
    validees: d.has("validees"), brouillons: d.has("brouillons"),
    formats: d.getAll("formats"), objets: d.getAll("objets"),
    separateur: d.get("separateur"), encodage: d.get("encodage"),
  };
  const { id } = await api("/api/taches", { method: "POST", corps });
  suivre(id, zone);
}

function ligneJournal(ev) {
  return el("li", { class: ev.niveau },
    el("time", { texte: ev.t.slice(11, 19) }), el("span", { texte: ev.message }));
}

// Bouton « Arrêter » d'une tâche en cours (ADR-0016).
function boutonArreter(id) {
  return el("button", { class: "bouton petit danger-bouton", type: "button", texte: "Arrêter",
    onclick: async (ev) => {
      if (!confirm("Arrêter cette tâche ?\n\nElle s'arrête au prochain point sûr (jamais au milieu d'une écriture), puis CONCORDE efface ce qu'elle a déjà écrit dans la base. Une écriture qu'Odoo refuse d'effacer (journal protégé, période verrouillée) sera nommée.")) return;
      ev.target.disabled = true; ev.target.textContent = "Arrêt demandé…";
      try { await api(`/api/taches/${id}/arreter`, { method: "POST", corps: {} }); }
      catch (e) { alert(e.message); ev.target.disabled = false; ev.target.textContent = "Arrêter"; }
    } });
}

function suivre(id, zone) {
  const prog = $("#modele-progression").content.cloneNode(true).firstElementChild;
  $(".progression", prog).append(boutonArreter(id));
  zone.replaceChildren(prog);
  const liste = $(".journal", prog);
  const debut = Date.now();
  let depuis = 0;
  etat.suivi[zone.id] = id;
  const tic = async () => {
    if (etat.suivi[zone.id] !== id) return;           // une autre tâche a pris la place
    let t;
    try { t = await api(`/api/taches/${id}?depuis=${depuis}`); } catch (e) {
      zone.replaceChildren(el("div", { class: "carte erreur", texte: e.message })); return;
    }
    for (const ev of t.journal || []) liste.append(ligneJournal(ev));
    depuis = t.journal_suivant ?? depuis;
    liste.scrollTop = liste.scrollHeight;
    if (t.statut === "en_attente" || t.statut === "en_cours") {
      const dernier = (t.journal || []).at(-1);
      $(".texte", prog).textContent = `${Math.round((Date.now() - debut) / 1000)} s · `
        + (dernier ? dernier.message : (t.statut === "en_cours" ? "En cours" : "En attente"));
      setTimeout(tic, 700);
      return;
    }
    const fini = rendreTache(t);
    // Le journal complet reste consultable sous le résultat.
    const tout = await api(`/api/taches/${id}`).catch(() => null);
    if (tout && tout.journal && tout.journal.length) {
      fini.append(el("details", { class: "journal-replie" },
        el("summary", { texte: `Journal de la tâche (${tout.journal.length} événements)` }),
        el("ol", { class: "journal" }, tout.journal.map(ligneJournal))));
    }
    zone.replaceChildren(fini);
    rafraichirCloche();
  };
  tic();
}

function rendreTache(t) {
  if (t.statut === "arretee") {
    return el("div", { class: "carte" },
      el("div", { class: "entete-resultat" }, el("h2", { texte: (ACTIONS[t.action] || t.action) + " arrêtée" }), statutPastille(t.statut)),
      el("p", { texte: t.erreur || "" }),
      el("details", { open: true }, el("summary", { texte: "Ce qui a été effacé" }),
        el("pre", { class: "mono", texte: JSON.stringify(t.annulation || {}, null, 1) })));
  }
  if (t.statut !== "terminee") {
    return el("div", { class: "carte" },
      el("div", { class: "entete-resultat" }, el("h2", { texte: ACTIONS[t.action] + " impossible" }),
        statutPastille(t.statut)),
      el("p", { class: "erreur", texte: t.erreur || "Erreur inconnue." }));
  }
  if (t.action === "comparer") return rendreComparaison(t);
  if (t.action === "transfert" || t.action === "feu_vert") return rendreTacheTransfert(t);
  if (t.action.startsWith("siret_") || t.action.startsWith("peppol_")) return rendreTacheTiers(t);
  if (t.action === "supprimer_base" || t.action === "reinitialiser_base") {
    return el("div", { class: "carte" },
      el("div", { class: "entete-resultat" }, el("h2", { texte: (t.action === "supprimer_base"
        ? "Base supprimée — " : "Base réinitialisée — ") + t.base }), statutPastille(t.statut)),
      el("p", { texte: t.resultat && t.resultat.sauvegarde
        ? "Sauvegarde : " + t.resultat.sauvegarde + " (gardée 7 jours)"
        : "Base de test : pas de sauvegarde." }));
  }
  return t.action === "analyser" ? rendreAnalyse(t) : rendreTelechargement(t);
}

function rendreAnalyse(t) {
  const r = t.resultat;
  const i = r.infos;
  const periode = i.periode && i.periode[0] ? `${dateFr(i.periode[0])} → ${dateFr(i.periode[1])}` : "—";
  const constats = r.constats.map((c) => el("details", { class: "constat " + c.niveau },
    el("summary", {},
      el("span", { class: "niveau " + c.niveau, texte: c.niveau }),
      el("span", { texte: c.message }),
      el("span", { class: "nombre", texte: nombre(c.nombre) })),
    el("div", { class: "detail" },
      blocMarceau(c.explication),
      el("ul", {}, c.exemples.map((e) => el("li", { texte: e }))),
      c.nombre > c.exemples.length
        ? el("p", { class: "note", texte: `${c.exemples.length} premiers sur ${nombre(c.nombre)}.` }) : null,
      el("div", { class: "actions" },
        el("a", { class: "bouton petit", href: `/api/taches/${t.id}/constats/${c.code}.csv`,
                  texte: "Liste complète (CSV)" }),
        c.code === "TIERS_SANS_SIREN_TVA"
          ? el("button", { class: "bouton petit principal", type: "button", texte: "Compléter SIRET et TVA…",
                           onclick: () => ouvrirSiret(t) }) : null))));
  return el("div", { class: "carte" },
    el("div", { class: "entete-resultat" },
      el("h2", { texte: "Résultat — " + t.base }),
      statutPastille(r.statut)),
    el("p", { class: "note", texte: `${i.societe || ""} · analyse du ${dateFr(t.cree_le)} en ${t.duree_s} s` }),
    el("div", { class: "chiffres" },
      chiffre("Lignes", nombre(i.lignes)), chiffre("Écritures", nombre(i.ecritures)),
      chiffre("Débit", euros(i.total_debit)), chiffre("Crédit", euros(i.total_credit)),
      chiffre("Période", periode),
      chiffre("Constats", `${r.synthese.BLOQUANT} bloq. · ${r.synthese.ALERTE} alertes · ${r.synthese.INFO} info`)),
    constats.length ? el("div", { class: "constats" }, constats)
      : el("p", { texte: "Aucun constat : la base est conforme." }),
    el("p", { class: "note" }, "Empreinte SHA-256 du rapport : ",
      el("span", { class: "mono", texte: r.empreinte.slice(0, 16) + "…" }), " · ",
      el("a", { href: `/api/taches/${t.id}/rapport.json`, texte: "rapport complet (JSON)" })));
}

function chiffre(titre, valeur) {
  return el("div", { class: "chiffre" }, el("small", { texte: titre }), el("strong", { texte: valeur }));
}

function rendreTelechargement(t) {
  const produits = t.resultat.produits.map((p) => el("div", { class: "produit" },
    el("div", { class: "format", texte: p.format }),
    el("div", {},
      el("div", { texte: p.resume }),
      p.alertes.map((a) => el("div", { class: "avertissement", texte: a })),
      el("ul", {}, t.fichiers.filter((f) => f.format === p.format).map((f) =>
        el("li", {}, el("a", { href: `/api/taches/${t.id}/fichiers/${f.n}`, texte: f.nom }),
          " ", el("small", { texte: taille(f.taille) })))))));
  return el("div", { class: "carte" },
    el("div", { class: "entete-resultat" },
      el("h2", { texte: "Fichiers prêts — " + t.base }),
      el("a", { class: "bouton principal", href: `/api/taches/${t.id}/zip`, texte: "Tout télécharger (zip)" })),
    el("p", { class: "note", texte: `Préparés le ${dateFr(t.cree_le)} en ${t.duree_s} s` }),
    el("div", { class: "produits" }, produits));
}

// --- formulaires ------------------------------------------------------------------
for (const [action, zone] of [["analyser", "#resultat-analyser"], ["telecharger", "#resultat-telecharger"]]) {
  $("#form-" + action).addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const bouton = $("button[type=submit]", ev.target);
    const erreur = $("#erreur-" + action);
    if (erreur) erreur.textContent = "";
    bouton.disabled = true;
    try {
      await lancer(action, ev.target, $(zone));
    } catch (e) {
      if (erreur) erreur.textContent = e.message;
      else $(zone).replaceChildren(el("div", { class: "carte erreur", texte: e.message }));
    } finally {
      bouton.disabled = false;
    }
  });
}

// FEC et brouillons sont incompatibles : on le montre au lieu de laisser échouer.
const fBrouillons = $("#form-telecharger [name=brouillons]");
const fFec = $("#form-telecharger [name=formats][value=fec]");
fBrouillons.addEventListener("change", () => {
  if (fBrouillons.checked) fFec.checked = false;
  fFec.disabled = fBrouillons.checked;
});

// --- historique -------------------------------------------------------------------
async function chargerHistorique() {
  const { taches } = await api("/api/taches");
  const corps = $("#table-historique tbody");
  corps.replaceChildren(...taches.map((t) => el("tr", {},
    el("td", { class: "mono", texte: dateFr(t.cree_le) }),
    el("td", { texte: ACTIONS[t.action] || t.action }),
    el("td", { texte: t.base }),
    el("td", {}, statutPastille(t.statut)),
    el("td", { class: "mono", texte: t.duree_s != null ? t.duree_s + " s" : "—" }),
    el("td", {}, t.statut === "en_cours" || t.statut === "en_attente" ? boutonArreter(t.id) : $("#resultat-" + t.action) ? el("button", { class: "bouton petit", type: "button",
      texte: "Ouvrir", onclick: () => {
        location.hash = "#" + (VUE_ACTION[t.action] || t.action);
        suivre(t.id, $("#resultat-" + t.action));
      } }) : el("small", { texte: t.erreur || "" })))));
  if (!taches.length) corps.append(el("tr", {}, el("td", { colspan: 6, class: "vide", texte: "Aucune tâche pour l'instant." })));
}


// --- Marceau ------------------------------------------------------------------------
function blocMarceau(x) {
  if (!x) return null;
  return el("div", { class: "marceau" },
    el("p", {}, el("b", { texte: "Pourquoi : " }), x.pourquoi),
    el("p", {}, el("b", { texte: "Que faire : " }), x.que_faire));
}

// --- cloche -------------------------------------------------------------------------
async function rafraichirCloche() {
  if ($("#ecran-app").hidden) return;
  let r;
  try { r = await api("/api/alertes/resume"); } catch (_) { return; }
  for (const c of [$("#cloche-compteur"), $("#compteur-alertes")]) {
    c.textContent = r.non_vues;
    c.className = "compteur" + (r.bloquantes ? " bloquant" : r.non_vues ? " alerte" : "");
    c.hidden = c.id === "compteur-alertes" && !r.non_vues;
  }
  $("#cloche").title = `${r.actives} alerte(s) active(s), ${r.non_vues} à voir`;
}

// --- alertes ------------------------------------------------------------------------
const CATEGORIES = { comptable: "Comptable", technique: "Technique", changement: "Changement" };
etat.filtreAlertes = "active";

async function chargerAlertes() {
  const { alertes, dernier_passage, en_cours } = await api("/api/alertes");
  $("#dernier-passage").textContent = en_cours ? "Surveillance en cours…"
    : dernier_passage ? "Dernier passage : " + dateFr(dernier_passage) : "Premier passage dans quelques instants.";
  const liste = alertes.filter((a) => a.statut === etat.filtreAlertes);
  const zone = $("#liste-alertes");
  zone.replaceChildren(...liste.map(carteAlerte));
  if (!liste.length) {
    zone.append(el("div", { class: "carte vide", texte: etat.filtreAlertes === "active"
      ? "Aucune alerte active. CONCORDE n'a rien relevé." : "Rien à afficher." }));
  }
  rafraichirCloche();
}

function carteAlerte(a) {
  const x = a.explication || {};
  return el("article", { class: `alerte-carte ${a.niveau}${a.vue ? " vue" : ""}` },
    el("div", { class: "alerte-tete" },
      el("span", { class: "niveau " + a.niveau, texte: a.niveau }),
      el("strong", { texte: a.message }),
      el("span", { class: "nombre", texte: nombre(a.nombre) }),
      el("span", { class: "categorie", texte: CATEGORIES[a.categorie] || a.categorie }),
      el("span", { class: "meta", texte: (a.base === "serveur" ? "Serveur" : "Base " + a.base)
        + " · " + (a.statut === "resolue" ? "résolue le " + dateFr(a.resolue_le)
          : a.statut === "evenement" ? dateFr(a.premiere_fois)
          : "depuis le " + dateFr(a.premiere_fois)) })),
    blocMarceau(x),
    a.exemples && a.exemples.length ? el("details", {},
      el("summary", { texte: a.nombre > a.exemples.length
        ? `Voir les ${a.exemples.length} premiers sur ${nombre(a.nombre)}` : "Voir le détail" }),
      el("ul", {}, a.exemples.map((e) => el("li", { texte: e })))) : null,
    !a.vue && a.statut !== "resolue" ? el("button", { class: "bouton petit", type: "button",
      texte: "Marquer comme vue", onclick: async () => {
        await api("/api/alertes/vue", { method: "POST", corps: { id: a.id } });
        chargerAlertes();
      } }) : null);
}

$$("#filtres-alertes .filtre").forEach((b) => b.addEventListener("click", () => {
  etat.filtreAlertes = b.dataset.filtre;
  $$("#filtres-alertes .filtre").forEach((x) => x.classList.toggle("actif", x === b));
  chargerAlertes();
}));
$("#tout-vu").addEventListener("click", async () => {
  await api("/api/alertes/vue", { method: "POST", corps: {} });
  chargerAlertes();
});
$("#surveiller").addEventListener("click", async () => {
  const b = $("#surveiller");
  b.disabled = true;
  try {
    await api("/api/surveillance", { method: "POST", corps: {} });
    $("#dernier-passage").textContent = "Surveillance en cours… (le Journal la raconte)";
    const attendre = async () => {
      const { en_cours } = await api("/api/alertes");
      if (en_cours) return setTimeout(attendre, 1500);
      b.disabled = false; chargerAlertes();
    };
    setTimeout(attendre, 1500);
  } catch (e) {
    $("#dernier-passage").textContent = e.message; b.disabled = false;
  }
});

// --- journal système ----------------------------------------------------------------
etat.journalDepuis = 0;
async function suivreJournal() {
  if (location.hash !== "#journal") { etat.journalActif = false; return; }
  if (etat.journalActif) return;
  etat.journalActif = true;
  const liste = $("#journal-systeme");
  const tic = async () => {
    if (location.hash !== "#journal") { etat.journalActif = false; return; }
    try {
      const { journal, suivant } = await api("/api/journal?depuis=" + etat.journalDepuis);
      // Le plus récent en haut.
      for (const ev of journal) liste.prepend(ligneJournal(ev));
      etat.journalDepuis = suivant;
    } catch (_) { /* réessaie au prochain tour */ }
    setTimeout(tic, 3000);
  };
  tic();
}

// --- comptes : balance, grand livre, écriture -----------------------------------------
const TYPES_COMPTE = {
  asset_receivable: "Client", liability_payable: "Fournisseur", asset_cash: "Banque/caisse",
  asset_current: "Actif circulant", asset_non_current: "Actif immobilisé", asset_fixed: "Immobilisation",
  asset_prepayments: "Charges constatées d'avance", liability_current: "Dette",
  liability_non_current: "Dette long terme", liability_credit_card: "Carte de crédit",
  equity: "Capitaux propres", equity_unaffected: "Résultat", income: "Produit",
  income_other: "Autre produit", expense: "Charge", expense_depreciation: "Amortissement",
  expense_direct_cost: "Coût direct", off_balance: "Hors bilan",
};
const centimes = (c) => {
  const s = Math.abs(c), signe = c < 0 ? "-" : "";
  return signe + Math.floor(s / 100).toLocaleString("fr-FR") + "," + String(s % 100).padStart(2, "0");
};
const soldeTexte = (s) => s === 0 ? "0,00" : centimes(Math.abs(s)) + (s > 0 ? " D" : " C");

function paramsComptes(extra = {}) {
  const d = new FormData($("#form-comptes"));
  const p = new URLSearchParams({ base: baseCourante() });
  if (d.get("du")) p.set("du", d.get("du"));
  if (d.get("au")) p.set("au", d.get("au"));
  if (d.has("brouillons")) p.set("brouillons", "1");
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p;
}

$("#form-comptes").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const b = $("button[type=submit]", ev.target);
  b.disabled = true;
  $("#balance").replaceChildren(el("div", { class: "carte progression" },
    el("span", { class: "roue" }), el("span", { texte: "Calcul de la balance…" })));
  $("#grand-livre").replaceChildren();
  try {
    etat.balance = await api("/api/comptes?" + paramsComptes());
    afficherBalance();
  } catch (e) {
    $("#balance").replaceChildren(el("div", { class: "carte erreur", texte: e.message }));
  } finally { b.disabled = false; }
});
for (const n of ["recherche", "mouvementes", "en_alerte"]) {
  $(`#form-comptes [name=${n}]`).addEventListener("input", () => etat.balance && afficherBalance());
}

function afficherBalance() {
  const { comptes, infos, constats } = etat.balance;
  const d = new FormData($("#form-comptes"));
  const q = (d.get("recherche") || "").toLowerCase().trim();
  const visibles = comptes.filter((c) =>
    (!d.has("mouvementes") || c.lignes) && (!d.has("en_alerte") || c.alertes.length)
    && (!q || c.code.startsWith(q) || c.libelle.toLowerCase().includes(q)));
  const niv = Object.fromEntries(constats.map((c) => [c.code, c]));
  $("#constats-comptes").replaceChildren(...(constats.length ? [el("div", { class: "constats" },
    constats.map((c) => el("details", { class: "constat " + c.niveau },
      el("summary", {}, el("span", { class: "niveau " + c.niveau, texte: c.niveau }),
        el("span", { texte: c.message }), el("span", { class: "nombre", texte: nombre(c.nombre) })),
      el("div", { class: "detail" }, blocMarceau(c.explication),
        el("ul", {}, c.exemples.map((e) => el("li", { texte: e })))))))]
    : [el("div", { class: "carte vide", texte: "Aucune anomalie par compte." })]));
  let D = 0, C = 0;
  const lignes = visibles.map((c) => {
    D += c.debit; C += c.credit;
    return el("tr", { "data-code": c.code, onclick: () => ouvrirGrandLivre(c) },
      el("td", { class: "code", texte: c.code }),
      el("td", {}, c.libelle, " ", c.alertes.map((a) =>
        el("span", { class: "puce " + (niv[a] ? niv[a].niveau : ""), title: niv[a] ? niv[a].message : a,
                     texte: (niv[a] ? niv[a].message : a).split(" ")[0] }))),
      el("td", { texte: TYPES_COMPTE[c.type] || c.type }),
      el("td", { class: "montant", texte: centimes(c.debit) }),
      el("td", { class: "montant", texte: centimes(c.credit) }),
      el("td", { class: "montant", texte: soldeTexte(c.debit - c.credit) }),
      el("td", { class: "montant", texte: nombre(c.lignes) }));
  });
  $("#balance").replaceChildren(el("div", { class: "carte" },
    el("div", { class: "entete-resultat" },
      el("h2", { texte: `Balance — ${visibles.length} compte(s)` }),
      el("span", { class: "note", texte: `${nombre(infos.comptes_mouvementes)} mouvementés sur ${nombre(infos.comptes)}` })),
    el("div", { class: "defilant" }, el("table", { class: "tableau balance-tableau" },
      el("thead", {}, el("tr", {}, ["Compte", "Libellé", "Type"].map((t) => el("th", { texte: t })),
        ["Débit", "Crédit", "Solde", "Lignes"].map((t) => el("th", { class: "montant", texte: t })))),
      el("tbody", {}, lignes),
      el("tfoot", {}, el("tr", {}, el("td", { colspan: 3, texte: "Total affiché" }),
        el("td", { class: "montant", texte: centimes(D) }), el("td", { class: "montant", texte: centimes(C) }),
        el("td", { class: "montant", texte: soldeTexte(D - C) }), el("td")))))));
}

async function ouvrirGrandLivre(compte, offset = 0) {
  $$("#balance tr.choisi").forEach((tr) => tr.classList.remove("choisi"));
  const tr = $(`#balance tr[data-code="${CSS.escape(compte.code)}"]`);
  if (tr) tr.classList.add("choisi");
  const zone = $("#grand-livre");
  zone.replaceChildren(el("div", { class: "carte progression" }, el("span", { class: "roue" }),
    el("span", { texte: `Grand livre du ${compte.code}…` })));
  zone.scrollIntoView({ behavior: "smooth", block: "start" });
  let g;
  try {
    g = await api(`/api/comptes/${encodeURIComponent(compte.code)}/grand-livre?` + paramsComptes({ offset }));
  } catch (e) { zone.replaceChildren(el("div", { class: "carte erreur", texte: e.message })); return; }
  const niv = Object.fromEntries(etat.balance.constats.map((c) => [c.code, c]));
  const t = g.totaux;
  zone.replaceChildren(el("div", { class: "carte" },
    el("div", { class: "entete-resultat" },
      el("h2", { texte: `${compte.code} — ${compte.libelle}` }),
      el("button", { class: "bouton", type: "button", disabled: true,
                     title: "Disponible en phase 3", texte: "Corriger (phase 3)" })),
    el("div", { class: "chiffres" },
      chiffre("Lignes", nombre(t.lignes)), chiffre("Débit", centimes(t.debit)),
      chiffre("Crédit", centimes(t.credit)), chiffre("Solde", soldeTexte(t.solde)),
      chiffre("Non lettrées", nombre(compte.non_lettrees))),
    compte.alertes.map((a) => niv[a] ? el("div", { class: "alerte-carte " + niv[a].niveau },
      el("div", { class: "alerte-tete" }, el("span", { class: "niveau " + niv[a].niveau, texte: niv[a].niveau }),
        el("strong", { texte: niv[a].message })), blocMarceau(niv[a].explication)) : null),
    el("div", { class: "defilant" }, el("table", { class: "tableau balance-tableau" },
      el("thead", {}, el("tr", {}, ["Date", "Journal", "Écriture", "Libellé", "Tiers", "Let."].map((x) => el("th", { texte: x })),
        ["Débit", "Crédit", "Solde cumulé"].map((x) => el("th", { class: "montant", texte: x })))),
      el("tbody", {}, g.lignes.map((l) => el("tr", { onclick: () => ouvrirEcriture(l.ecriture_id) },
        el("td", { class: "mono", texte: dateFr(l.date) }),
        el("td", { texte: l.journal_code }),
        el("td", {}, el("button", { class: "lien", type: "button", texte: l.ecriture || "brouillon" }),
          l.etat !== "posted" ? el("small", { texte: " (" + l.etat + ")" }) : null),
        el("td", { texte: l.libelle }),
        el("td", { texte: l.tiers_nom }),
        el("td", { texte: l.lettrage }),
        el("td", { class: "montant", texte: l.debit ? centimes(l.debit) : "" }),
        el("td", { class: "montant", texte: l.credit ? centimes(l.credit) : "" }),
        el("td", { class: "montant", texte: soldeTexte(l.cumul) })))))),
    t.lignes > g.limite ? el("div", { class: "pagination" },
      el("button", { class: "bouton petit", type: "button", disabled: g.offset === 0,
        texte: "← Précédent", onclick: () => ouvrirGrandLivre(compte, Math.max(0, g.offset - g.limite)) }),
      el("span", { class: "note", texte: `Lignes ${nombre(g.offset + 1)} à ${nombre(Math.min(g.offset + g.limite, t.lignes))} sur ${nombre(t.lignes)}` }),
      el("button", { class: "bouton petit", type: "button", disabled: g.offset + g.limite >= t.lignes,
        texte: "Suivant →", onclick: () => ouvrirGrandLivre(compte, g.offset + g.limite) })) : null));
}

async function ouvrirEcriture(id) {
  $("#voile").hidden = false;
  $("#tiroir-titre").textContent = "Écriture…";
  $("#tiroir-contenu").replaceChildren(el("div", { class: "progression" }, el("span", { class: "roue" })));
  let r;
  try { r = await api(`/api/ecritures/${id}?base=${encodeURIComponent(baseCourante())}`); }
  catch (e) { $("#tiroir-contenu").replaceChildren(el("p", { class: "erreur", texte: e.message })); return; }
  const l0 = r.lignes[0];
  let D = 0, C = 0;
  r.lignes.forEach((l) => { D += l.debit; C += l.credit; });
  $("#tiroir-titre").textContent = `${l0.ecriture || "Brouillon"} — ${l0.journal_lib || l0.journal_code}`;
  $("#tiroir-contenu").replaceChildren(
    el("div", { class: "chiffres" }, chiffre("Date", dateFr(l0.date)), chiffre("État", l0.etat),
      chiffre("Référence", l0.reference || "—"), chiffre("Équilibre", D === C ? "OK au centime" : "ÉCART " + centimes(D - C))),
    el("table", { class: "tableau balance-tableau" },
      el("thead", {}, el("tr", {}, ["Compte", "Libellé", "Tiers", "Let."].map((x) => el("th", { texte: x })),
        ["Débit", "Crédit"].map((x) => el("th", { class: "montant", texte: x })))),
      el("tbody", {}, r.lignes.map((l) => el("tr", {},
        el("td", { class: "code", texte: l.compte }), el("td", { texte: l.libelle }),
        el("td", { texte: l.tiers_nom }), el("td", { texte: l.lettrage }),
        el("td", { class: "montant", texte: l.debit ? centimes(l.debit) : "" }),
        el("td", { class: "montant", texte: l.credit ? centimes(l.credit) : "" })))),
      el("tfoot", {}, el("tr", {}, el("td", { colspan: 4, texte: "Total" }),
        el("td", { class: "montant", texte: centimes(D) }), el("td", { class: "montant", texte: centimes(C) })))));
}
function fermerTiroir() { $("#voile").hidden = true; }
$("#fermer-tiroir").addEventListener("click", fermerTiroir);
$("#voile").addEventListener("click", (e) => { if (e.target.id === "voile") fermerTiroir(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermerTiroir(); });
$("#base").addEventListener("change", () => {
  etat.balance = null;
  $("#balance").replaceChildren(); $("#grand-livre").replaceChildren(); $("#constats-comptes").replaceChildren();
});

// --- comparer deux bases ------------------------------------------------------------
$("#form-comparer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const d = new FormData(ev.target);
  const b = $("button[type=submit]", ev.target);
  $("#erreur-comparer").textContent = "";
  b.disabled = true;
  try {
    const { id } = await api("/api/taches", { method: "POST", corps: {
      action: "comparer", base_id: d.get("base_a"), base_id_b: d.get("base_b"),
      du: d.get("du") || null, au: d.get("au") || null, brouillons: d.has("brouillons"),
      date_copie: d.get("date_copie") || "",
      comptes: d.getAll("comptes"), analytiques: d.getAll("analytiques") } });
    suivre(id, $("#resultat-comparer"));
  } catch (e) { $("#erreur-comparer").textContent = e.message; }
  finally { b.disabled = false; }
});

function listeConstats(constats) {
  if (!constats.length) return el("p", { texte: "Aucune différence." });
  return el("div", { class: "constats" }, constats.map((c) => el("details", { class: "constat " + c.niveau },
    el("summary", {}, el("span", { class: "niveau " + c.niveau, texte: c.niveau }),
      el("span", { texte: c.message }), el("span", { class: "nombre", texte: nombre(c.nombre) })),
    el("div", { class: "detail" }, blocMarceau(c.explication),
      el("ul", {}, c.exemples.map((e) => el("li", { texte: e })))))));
}

function rendreComparaison(t) {
  const r = t.resultat, c = r.comparaison, i = c.infos;
  const ta = i.totaux_A, tb = i.totaux_B;
  const ligne = (titre, a, b, fmt) => el("tr", { class: a === b ? "" : "choisi" },
    el("td", { texte: titre }), el("td", { class: "montant", texte: fmt(a) }),
    el("td", { class: "montant", texte: fmt(b) }), el("td", { texte: a === b ? "=" : "≠" }));
  const periode = (r.du || "début") + " → " + (r.au || "aujourd'hui");
  return el("div", { class: "carte" },
    el("div", { class: "entete-resultat" },
      el("h2", { texte: `${r.base_a} ↔ ${r.base_b}` }), statutPastille(c.statut),
      t.fichiers && t.fichiers.length ? el("a", { class: "bouton principal",
        href: `/api/taches/${t.id}/fichiers/0`, texte: "Détail complet (Excel)" }) : null),
    (r.filtre_comptes.length || r.filtre_analytiques.length) ? el("p", { class: "avertissement",
      texte: "Comparaison limitée à : " + [r.filtre_comptes.length ? "comptes " + r.filtre_comptes.join(", ") : "",
        r.filtre_analytiques.length ? "analytique " + r.filtre_analytiques.join(", ") : ""].filter(Boolean).join(" et ") }) : null,
    el("p", { class: "note", texte: `Période ${periode} · ${r.etats.includes("draft") ? "validées et brouillons" : "écritures validées"}`
      + (r.date_copie ? ` · copie du ${dateFr(r.date_copie)}` : "") + ` · ${t.duree_s} s` }),
    el("table", { class: "tableau balance-tableau" },
      el("thead", {}, el("tr", {}, el("th", { texte: "" }), el("th", { class: "montant", texte: "A · " + r.base_a }),
        el("th", { class: "montant", texte: "B · " + r.base_b }), el("th", { texte: "" }))),
      el("tbody", {},
        ligne("Écritures", ta.ecritures, tb.ecritures, nombre),
        ligne("Lignes", ta.lignes, tb.lignes, nombre),
        ligne("Débit", ta.debit, tb.debit, centimes),
        ligne("Crédit", ta.credit, tb.credit, centimes),
        el("tr", {}, el("td", { texte: "Analyse" }), el("td", { class: "montant" }, statutPastille(r.analyse_A.statut)),
          el("td", { class: "montant" }, statutPastille(r.analyse_B.statut)), el("td")))),
    el("p", { texte: `${nombre(i.ecritures_rapprochees)} écritures rapprochées, dont ${nombre(i.ecritures_identiques)} identiques.` }),
    el("h2", { texte: "Différences" }), listeConstats(c.constats),
    el("details", { class: "journal-replie" }, el("summary", { texte: `Analyse de A (${r.base_a}) : ${r.analyse_A.constats.length} constat(s)` }),
      listeConstats(r.analyse_A.constats)),
    el("details", { class: "journal-replie" }, el("summary", { texte: `Analyse de B (${r.base_b}) : ${r.analyse_B.constats.length} constat(s)` }),
      listeConstats(r.analyse_B.constats)));
}

// --- filtres de la comparaison : listes à cocher ---------------------------------------
async function chargerChoixComparaison() {
  const f = $("#form-comparer");
  const a = f.elements.base_a.value, b = f.elements.base_b.value;
  if (!a || !b || a === b) return;
  for (const id of ["liste-comptes", "liste-analytiques"]) {
    $("#" + id).replaceChildren(el("p", { class: "note", texte: "Chargement…" }));
  }
  let r;
  try { r = await api(`/api/comparer/choix?base_a=${encodeURIComponent(a)}&base_b=${encodeURIComponent(b)}`); }
  catch (e) { $("#liste-comptes").replaceChildren(el("p", { class: "erreur", texte: e.message })); return; }
  const seul = (bases) => bases.length === 1 ? el("span", { class: "seul", texte: "seulement " + bases }) : null;
  $("#liste-comptes").replaceChildren(...r.comptes.map((c) => el("label", { class: "case", "data-texte": (c.code + " " + c.libelle).toLowerCase() },
    el("input", { type: "checkbox", name: "comptes", value: c.code }), el("span", { class: "mono", texte: c.code }), el("span", { texte: c.libelle }), seul(c.bases))));
  $("#liste-analytiques").replaceChildren(...r.analytiques.map((x) => el("label", { class: "case", "data-texte": x.nom.toLowerCase() },
    el("input", { type: "checkbox", name: "analytiques", value: x.nom }), el("span", { texte: x.nom }), seul(x.bases))));
  if (!r.analytiques.length) $("#liste-analytiques").append(el("p", { class: "note", texte: "Aucun compte analytique dans ces bases." }));
  majResumeFiltres();
}

function majResumeFiltres() {
  const nc = $$("#liste-comptes input:checked").length, na = $$("#liste-analytiques input:checked").length;
  $("#nb-comptes").textContent = `${nc} coché(s) sur ${$$("#liste-comptes input").length}`;
  $("#nb-analytiques").textContent = `${na} coché(s) sur ${$$("#liste-analytiques input").length}`;
  $("#resume-filtres").textContent = !nc && !na ? "(tout)" : `(${nc} compte(s), ${na} analytique(s))`;
}

for (const s of $$("#form-comparer .choix-bases")) s.addEventListener("change", chargerChoixComparaison);
$("#filtres-comparer").addEventListener("toggle", (ev) => {
  if (ev.target.open && !$$("#liste-comptes input").length) chargerChoixComparaison();
});
$("#filtres-comparer").addEventListener("change", majResumeFiltres);
for (const champ of $$("#filtres-comparer input[type=search]")) {
  champ.addEventListener("input", () => {
    const q = champ.value.toLowerCase().trim();
    for (const l of $$(`#${champ.dataset.liste} label`)) l.hidden = q && !l.dataset.texte.includes(q);
  });
}
for (const b of $$("#filtres-comparer [data-tout]")) b.addEventListener("click", () => {
  for (const l of $$(`#${b.dataset.tout} label`)) if (!l.hidden) $("input", l).checked = true;
  majResumeFiltres();
});
for (const b of $$("#filtres-comparer [data-rien]")) b.addEventListener("click", () => {
  for (const i of $$(`#${b.dataset.rien} input`)) i.checked = false;
  majResumeFiltres();
});

// --- rapport du jour -----------------------------------------------------------------
etat.rapport = null;
etat.rapportModifie = false;
const NIVEAU_FR = { BLOQUANT: "BLOQUANT", ALERTE: "ALERTE", INFO: "INFO", OK: "OK" };
const TITRES_SECTIONS = { securite: "Sécurité du serveur", alertes: "Alertes",
  changements: "Changements dans Odoo", taches: "Travaux de la journée" };

function aujourdhui() { return new Date().toISOString().slice(0, 10); }

function marquerModifie(oui = true) {
  etat.rapportModifie = oui;
  const e = $("#rapport-etat");
  if (oui) { e.textContent = "Modifications non enregistrées"; e.className = "note non-enregistre"; }
  else if (etat.rapport) {
    e.className = "note";
    e.textContent = "Généré le " + dateFr(etat.rapport.genere_le)
      + (etat.rapport.enregistre_le ? " · enregistré le " + dateFr(etat.rapport.enregistre_le) : "");
  }
}

async function chargerRapport() {
  const champ = $("#rapport-jour");
  if (!champ.value) champ.value = aujourdhui();
  if (etat.rapportModifie && !confirm("Des modifications ne sont pas enregistrées. Les abandonner ?")) return;
  $("#rapport-contenu").replaceChildren(el("div", { class: "carte progression" }, el("span", { class: "roue" }),
    el("span", { texte: "Préparation du rapport…" })));
  try { etat.rapport = await api("/api/rapport?jour=" + champ.value); }
  catch (e) { $("#rapport-contenu").replaceChildren(el("div", { class: "carte erreur", texte: e.message })); return; }
  afficherRapport();
  marquerModifie(false);
}

function zoneTexte(valeur, attrs = {}) {
  const t = el("textarea", Object.assign({ rows: 1 }, attrs));
  t.value = valeur || "";
  const ajuster = () => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; };
  t.addEventListener("input", () => { ajuster(); marquerModifie(); });
  requestAnimationFrame(ajuster);
  return t;
}

function ligneConclusion(c) {
  const coche = el("input", { type: "checkbox", title: "Faire figurer dans le rapport", "aria-label": "Dans le rapport" });
  coche.checked = c.visible !== false;
  const texte = zoneTexte(c.texte, { "aria-label": "Texte de la conclusion" });
  const com = zoneTexte(c.commentaire, { placeholder: "Votre commentaire…", "aria-label": "Commentaire" });
  const blocCom = el("div", { class: "commentaire" }, com);
  blocCom.hidden = !c.commentaire;
  const ligne = el("div", { class: "conclusion " + c.niveau + (coche.checked ? "" : " masquee"), "data-id": c.id },
    coche, el("span", { class: "quand mono", texte: c.quand ? dateFr(c.quand) : "—" }),
    el("span", { class: "niveau " + c.niveau, texte: NIVEAU_FR[c.niveau] || c.niveau }), texte,
    el("div", { class: "bas" },
      c.nouvelle ? el("span", { class: "etiquette nouvelle", texte: "nouvelle" }) : null,
      c.modifie ? el("span", { class: "etiquette modifiee", texte: "texte modifié" }) : null,
      c.perimee ? el("span", { class: "etiquette", texte: "n'est plus d'actualité" }) : null,
      el("button", { type: "button", class: "lien", texte: blocCom.hidden ? "Ajouter un commentaire" : "Commentaire",
        onclick: () => { blocCom.hidden = false; com.focus(); } }),
      c.texte_auto ? el("button", { type: "button", class: "lien", texte: "Texte d'origine",
        title: c.texte_auto, onclick: () => { texte.value = c.texte_auto; texte.dispatchEvent(new Event("input")); } }) : null),
    blocCom);
  ligne._donnees = c;
  coche.addEventListener("change", () => {
    ligne.classList.toggle("masquee", !coche.checked);
    for (const li of $$(`#rapport-contenu li[data-lie="${CSS.escape(c.id)}"]`)) li.classList.toggle("barre", !coche.checked);
    marquerModifie();
  });
  ligne._lire = () => ({ id: c.id, visible: coche.checked, niveau: c.niveau, section: c.section,
    quand: c.quand || "",
    texte: texte.value.trim() === (c.texte_auto || "").trim() ? "" : texte.value.trim(),
    commentaire: com.value.trim() });
  return ligne;
}

function maintenantIso() { return new Date().toISOString().slice(0, 19); }

function ligneAjout(a) {
  const t = zoneTexte(a.texte, { placeholder: "Votre conclusion…", "aria-label": "Conclusion ajoutée" });
  const quand = a.quand || maintenantIso();
  const l = el("div", { class: "ajout" }, el("span", { class: "quand mono", texte: dateFr(quand) }), t,
    el("button", { type: "button", class: "bouton petit", texte: "Retirer",
      onclick: () => { l.remove(); marquerModifie(); } }));
  l._lire = () => ({ id: a.id, texte: t.value.trim(), quand });
  return l;
}

function afficherRapport() {
  const r = etat.rapport;
  const visibles = r.conclusions.filter((c) => c.visible !== false).length;
  const ajouts = el("div", { class: "rapport-liste", id: "rapport-ajouts" }, r.ajouts.map(ligneAjout));
  const commentaire = zoneTexte(r.commentaire, { id: "rapport-commentaire", rows: 3,
    placeholder: "Commentaire général (en tête du rapport)…" });
  const sections = Object.keys(TITRES_SECTIONS).filter((s) => (r.sections[s] || []).length).map((s) => {
    const coche = el("input", { type: "checkbox", "data-section": s });
    coche.checked = !r.sections_masquees.includes(s);
    coche.addEventListener("change", marquerModifie);
    return el("details", { class: "journal-replie" },
      el("summary", {}, `${TITRES_SECTIONS[s]} — ${r.sections[s].length} élément(s) `,
        el("label", { class: "case case-en-ligne" }, coche, " dans le rapport")),
      el("ul", {}, r.sections[s].map((x) => el("li", { "data-lie": x.id || "",
        class: r.conclusions.some((c) => c.id === x.id && c.visible === false) ? "barre" : "",
        texte: (x.quand ? dateFr(x.quand) + " — " : "") + x.texte }))));
  });
  $("#rapport-contenu").replaceChildren(
    el("div", { class: "carte" },
      el("div", { class: "entete-resultat" }, el("h2", { texte: "Ce que CONCORDE conclut — " + dateFr(r.jour) }),
        el("span", { class: "note", texte: `${visibles} sur ${r.conclusions.length} retenue(s)` })),
      el("div", { class: "rapport-liste", id: "rapport-conclusions" }, r.conclusions.map(ligneConclusion)),
      el("h2", { texte: "Vos conclusions" }), ajouts,
      el("button", { type: "button", class: "bouton petit", texte: "Ajouter une conclusion",
        onclick: () => { const l = ligneAjout({ id: "ajout-" + Date.now(), texte: "", quand: maintenantIso() }); $("#rapport-ajouts").append(l); $("textarea", l).focus(); marquerModifie(); } }),
      el("h2", { texte: "Commentaire général" }), commentaire),
    el("div", { class: "carte" }, el("h2", { texte: "Détail de la journée" }),
      sections.length ? sections : el("p", { class: "note", texte: "Rien à détailler." })));
}

function lireRapport() {
  return {
    jour: etat.rapport.jour,
    conclusions: $$("#rapport-conclusions .conclusion").map((l) => l._lire()),
    ajouts: $$("#rapport-ajouts .ajout").map((l) => l._lire()).filter((a) => a.texte),
    commentaire: $("#rapport-commentaire").value.trim(),
    sections_masquees: $$("#rapport-contenu [data-section]").filter((c) => !c.checked).map((c) => c.dataset.section),
  };
}

async function enregistrerRapport() {
  if (!etat.rapport) return;
  const b = $("#rapport-enregistrer");
  b.disabled = true;
  try {
    etat.rapport = await api("/api/rapport", { method: "POST", corps: lireRapport() });
    afficherRapport();
    marquerModifie(false);
  } catch (e) { $("#rapport-etat").textContent = e.message; }
  finally { b.disabled = false; }
}

$("#rapport-actualiser").addEventListener("click", chargerRapport);
$("#rapport-jour").addEventListener("change", chargerRapport);
$("#rapport-enregistrer").addEventListener("click", enregistrerRapport);
$("#rapport-telecharger").addEventListener("click", async () => {
  if (!etat.rapport) return;
  if (etat.rapportModifie) await enregistrerRapport();
  location.href = "/api/rapport/export?jour=" + etat.rapport.jour;
});
window.addEventListener("beforeunload", (e) => { if (etat.rapportModifie) e.preventDefault(); });

demarrer().catch((e) => { document.body.prepend(el("p", { class: "erreur", texte: e.message })); });

// --- arrêt d'urgence (ADR-0016) ----------------------------------------------------
$("#arret-urgence").addEventListener("click", () => {
  const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Mot à retaper" });
  const bouton = el("button", { class: "bouton danger-bouton", type: "submit", disabled: true, texte: "ARRÊT D'URGENCE" });
  const erreur = el("p", { class: "erreur", role: "alert" });
  saisie.addEventListener("input", () => { bouton.disabled = saisie.value !== "ARRÊT"; });
  const form = el("form", { class: "formulaire" },
    el("div", { class: "danger" },
      el("strong", { texte: "DANGER pour la base de données et pour le logiciel." }), el("br"),
      "Tout s'arrête tout de suite, dans l'état où c'est : une écriture en cours peut rester à moitié faite dans la base, ",
      "rien n'est effacé automatiquement, les montées de version en cours sont coupées, et CONCORDE redémarre (quelques secondes). ",
      "Pour arrêter une seule tâche proprement, utilisez plutôt son bouton « Arrêter »."),
    el("label", {}, el("span", {}, "Pour confirmer, retapez ", el("span", { class: "mot-cle", texte: "ARRÊT" })), saisie),
    erreur, bouton);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); bouton.disabled = true;
    try {
      await api("/api/urgence", { method: "POST", corps: { confirmation: saisie.value } });
      $("#tiroir-contenu").replaceChildren(el("p", { class: "danger", texte: "Arrêt d'urgence fait. CONCORDE redémarre : la page se recharge dans quelques secondes." }));
      setTimeout(() => location.reload(), 8000);
    } catch (e) { erreur.textContent = e.message; bouton.disabled = false; }
  });
  $("#voile").hidden = false;
  $("#tiroir-titre").textContent = "Arrêt d'urgence";
  $("#tiroir-contenu").replaceChildren(form);
  saisie.focus();
});
