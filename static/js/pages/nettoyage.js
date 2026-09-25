// Écran nettoyage (#/nettoyage, depuis Paramètres) : repérer les composants mal remplis ou
// douteux et les traiter en lot, faire de même pour les commandes et devis, supprimer les
// blocs, ensembles et fournisseurs inutilisés, vider le journal.
// Une suppression n'est possible que pour ce qui n'a laissé aucune trace ; le serveur le
// vérifie et prend une sauvegarde avant d'agir.

import { api } from "../api.js";
import { formatDate, formatMontant, formatNombre, libelle } from "../format.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { lienRoute, naviguer } from "../router.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";

const TYPES_ENTITE = { bloc: "Bloc fonctionnel", ensemble: "Ensemble", fournisseur: "Fournisseur" };
const FILTRE_ANOMALIES = "__anomalies";
const FILTRE_TOUS = "__tous";

function select(options, valeur, surChangement, libelleAccessible) {
  const champ = el("select", { class: "filtre", "aria-label": libelleAccessible, onchange: (e) => surChangement(e.target.value) });
  for (const [code, texte] of options) champ.append(el("option", { value: code, selected: code === valeur }, texte));
  return champ;
}

function caseACocher(coche, surChangement, libelleAccessible) {
  return el("input", { type: "checkbox", checked: coche, "aria-label": libelleAccessible, onchange: (e) => surChangement(e.target.checked) });
}

function etiquettes(codes, libelles, infobulles = {}) {
  return codes.map((code) => el("span", { class: "etiquette etiquette--attention etiquette--espace", title: infobulles[code] ?? null }, libelles[code] ?? code));
}

function celluleSuppression(raison) {
  return raison
    ? el("span", { class: "texte-doux texte-petit", title: raison }, "Archivage seul")
    : el("span", { class: "texte-conforme texte-petit" }, "Supprimable");
}

// --- Récapitulatif avant d'agir ------------------------------------------------------------------

const VERBES = { supprimer: "Supprimer définitivement", archiver: "Archiver" };

function listeRecap(titre, cles) {
  if (!cles.length) return null;
  return el("div", { class: "recap" }, el("h3", {}, `${titre} (${cles.length})`), el("p", { class: "texte-petit" }, cles.join(", ")));
}

// Demande au serveur ce qui serait fait, l'affiche, puis agit sur confirmation.
async function traiterEnLot({ cles, action, traiter, nature, surTermine }) {
  let recap;
  try {
    recap = await traiter(cles, action, true);
  } catch (erreur) {
    afficherErreur(erreur);
    return;
  }
  const faisables = recap.supprimes.length + recap.archives.length;
  const confirmer = el("button", { type: "button", class: action === "supprimer" ? "bouton bouton--danger" : "bouton", disabled: faisables === 0 }, `${VERBES[action]} (${faisables})`);
  confirmer.addEventListener("click", async () => {
    confirmer.disabled = true;
    try {
      const fait = await traiter(cles, action, false);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surTermine(fait);
    } catch (erreur) {
      afficherErreur(erreur);
      confirmer.disabled = false;
    }
  });
  ouvrirPanneau(`${VERBES[action]} : récapitulatif`, [
    el("p", {}, `${recap.supprimes.length} ${nature} supprimé(s), ${recap.archives.length} archivé(s), ${recap.refuses.length} refusé(s).`),
    action === "supprimer" && recap.supprimes.length
      ? el("p", { class: "message message-attention" }, "La suppression est définitive. Une sauvegarde de la base est prise juste avant ; le journal garde un résumé de chaque ligne supprimée.")
      : null,
    listeRecap("Seront supprimés", recap.supprimes),
    listeRecap("Seront archivés", recap.archives),
    recap.refuses.length
      ? el(
          "div",
          { class: "recap" },
          el("h3", {}, `Refusés (${recap.refuses.length})`),
          el("ul", { class: "texte-petit" }, recap.refuses.map((r) => el("li", {}, el("strong", {}, r.cle), ` : ${r.raison}`))),
        )
      : null,
    el(
      "div",
      { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      confirmer,
    ),
  ]);
}

function messageFait(fait, nature) {
  const refus = fait.refuses.length ? `, ${fait.refuses.length} refusé(s)` : "";
  return el("p", { class: "message message-ok" }, `${fait.supprimes.length} ${nature} supprimé(s), ${fait.archives.length} archivé(s)${refus}.`);
}

// --- Table à sélection multiple ----------------------------------------------------------------

// Table dont les lignes visibles se cochent ; `lignesVisibles()` rend les données filtrées.
function tableSelection({ entetes, lignesVisibles, cle, cellules, selection, surSelection }) {
  const corps = el("tbody");
  const tout = el("input", { type: "checkbox", "aria-label": "Tout sélectionner" });
  const rendre = () => {
    const visibles = lignesVisibles();
    corps.replaceChildren(
      ...visibles.map((ligne) =>
        el(
          "tr",
          { class: ligne.archive ? "ligne--inactive" : "" },
          el("td", {}, caseACocher(selection.has(cle(ligne)), (coche) => {
            if (coche) selection.add(cle(ligne));
            else selection.delete(cle(ligne));
            majTout();
            surSelection();
          }, `Sélectionner ${cle(ligne)}`)),
          ...cellules(ligne),
        ),
      ),
    );
    if (!visibles.length) corps.append(el("tr", {}, el("td", { colspan: entetes.length + 1, class: "texte-doux" }, "Aucune ligne pour ces filtres.")));
    majTout();
  };
  const majTout = () => {
    const visibles = lignesVisibles();
    tout.checked = visibles.length > 0 && visibles.every((l) => selection.has(cle(l)));
  };
  tout.addEventListener("change", () => {
    for (const ligne of lignesVisibles()) {
      if (tout.checked) selection.add(cle(ligne));
      else selection.delete(cle(ligne));
    }
    rendre();
    surSelection();
  });
  const table = el(
    "div",
    { class: "table-defilante table-defilante--nettoyage" },
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, el("th", {}, tout), entetes.map(([texte, classe]) => el("th", { class: classe ?? "" }, texte)))),
      corps,
    ),
  );
  return { table, rendre };
}

function barreActions(selection, boutons) {
  const compteur = el("span", { class: "texte-doux" });
  const zone = el("div", { class: "barre-actions-lot" }, compteur, ...boutons.map((b) => b.element));
  const maj = () => {
    compteur.textContent = `${selection.size} sélectionné(s)`;
    for (const bouton of boutons) bouton.element.disabled = !bouton.actif(selection.size);
  };
  maj();
  return { zone, maj };
}

// --- Composants ----------------------------------------------------------------------------------

function infobulleDoublons(composant) {
  return composant.doublons.map((d) => `${d.id} : ${d.motif}`).join("\n");
}

async function sectionComposants(cible, blocs, apresLot) {
  const { controles, composants } = await api.getControlesComposants();
  const filtres = { controle: FILTRE_ANOMALIES, bloc: "", archives: false };
  const selection = new Set();
  const retour = el("div");
  const visibles = () =>
    composants.filter((c) => {
      if (c.archive && !filtres.archives) return false;
      if (filtres.bloc && c.bloc_code !== filtres.bloc) return false;
      if (filtres.controle === FILTRE_ANOMALIES) return c.controles.length > 0;
      if (filtres.controle === FILTRE_TOUS) return true;
      return c.controles.includes(filtres.controle);
    });
  const nbParControle = (code) => composants.filter((c) => !c.archive && c.controles.includes(code)).length;
  const optionsControle = [
    [FILTRE_ANOMALIES, `Toutes les anomalies (${composants.filter((c) => !c.archive && c.controles.length).length})`],
    ...Object.entries(controles).map(([code, texte]) => [code, `${texte} (${nbParControle(code)})`]),
    [FILTRE_TOUS, "Tous les composants"],
  ];
  const { table, rendre } = tableSelection({
    entetes: [["ID"], ["Bloc"], ["Désignation"], ["Fonction"], ["Contrôles"], ["Suppression"]],
    lignesVisibles: visibles,
    cle: (c) => c.id,
    selection,
    surSelection: () => actions.maj(),
    cellules: (c) => [
      el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: c.id }) }, c.id)),
      el("td", {}, c.bloc_code),
      el("td", { class: "tronque tronque--large", title: c.designation }, c.designation),
      el("td", { class: "tronque", title: c.fonction }, c.fonction),
      el("td", {}, c.archive ? el("span", { class: "etiquette etiquette--espace" }, "Archivé") : null, etiquettes(c.controles, controles, { doublon: infobulleDoublons(c) })),
      el("td", {}, celluleSuppression(c.raison_refus)),
    ],
  });
  const rafraichir = async (fait) => {
    await Promise.all([sectionComposants(cible, blocs, apresLot), apresLot()]);
    if (fait) cible.querySelector(".retour-lot")?.replaceChildren(messageFait(fait, "composant(s)"));
  };
  const agir = (action) => traiterEnLot({ cles: [...selection], action, traiter: api.traiterComposants, nature: "composant(s)", surTermine: rafraichir });
  const actions = barreActions(selection, [
    { element: el("button", { type: "button", class: "bouton bouton--danger", onclick: () => agir("supprimer") }, "Supprimer"), actif: (n) => n > 0 },
    { element: el("button", { type: "button", class: "bouton bouton--discret", onclick: () => agir("archiver") }, "Archiver"), actif: (n) => n > 0 },
    { element: el("button", { type: "button", class: "bouton bouton--discret", onclick: () => naviguer("/composants", { fiche: [...selection][0] }) }, "Ouvrir la fiche"), actif: (n) => n === 1 },
  ]);
  // Changer de filtre vide la sélection : on n'agit jamais sur une ligne masquée.
  const changer = (cle, valeur) => {
    filtres[cle] = valeur;
    selection.clear();
    actions.maj();
    rendre();
  };
  retour.className = "retour-lot";
  cible.replaceChildren(
    el("h2", {}, "Composants"),
    el("p", { class: "texte-doux" }, "Chaque contrôle est une étiquette sur la ligne. Un composant sans commande, sans mouvement de stock et sans document peut être supprimé ; les autres ne peuvent qu'être archivés."),
    el(
      "div",
      { class: "filtres" },
      select(optionsControle, filtres.controle, (v) => changer("controle", v), "Contrôle"),
      select([["", "Tous les blocs"], ...blocs.map((b) => [b.code, `${b.code} — ${b.nom}`])], filtres.bloc, (v) => changer("bloc", v), "Bloc fonctionnel"),
      el("label", { class: "filtre-case" }, caseACocher(false, (v) => changer("archives", v), "Inclure les archivés"), "Inclure les archivés"),
    ),
    actions.zone,
    retour,
    table,
  );
  rendre();
}

// --- Commandes et devis ------------------------------------------------------------------------

async function sectionCommandes(cible, apresLot) {
  const { controles, commandes } = await api.getControlesCommandes();
  const filtres = { archives: false };
  const selection = new Set();
  const visibles = () => commandes.filter((c) => filtres.archives || !c.archive);
  const { table, rendre } = tableSelection({
    entetes: [["Numéro"], ["Type"], ["Statut"], ["Fournisseur"], ["Date"], ["Lignes", "nombre"], ["Documents", "nombre"], ["Total HT", "nombre"], ["Contrôles"], ["Suppression"]],
    lignesVisibles: visibles,
    cle: (c) => c.numero,
    selection,
    surSelection: () => actions.maj(),
    cellules: (c) => [
      el("td", { class: "code" }, c.archive ? c.numero : el("a", { href: lienRoute(`/achats/${c.numero}`) }, c.numero)),
      el("td", {}, c.type),
      el("td", {}, libelle(c.statut)),
      el("td", {}, c.fournisseur_nom ?? "—"),
      el("td", {}, formatDate(c.date_commande ?? c.date_demande)),
      el("td", { class: "nombre" }, formatNombre(c.nb_lignes)),
      el("td", { class: "nombre" }, formatNombre(c.nb_documents)),
      el("td", { class: "nombre" }, c.total_ht === null ? "—" : formatMontant(c.total_ht)),
      el("td", {}, c.archive ? el("span", { class: "etiquette etiquette--espace" }, "Archivée") : null, etiquettes(c.controles, controles)),
      el("td", {}, celluleSuppression(c.raison_refus)),
    ],
  });
  const rafraichir = async (fait) => {
    await Promise.all([sectionCommandes(cible, apresLot), apresLot()]);
    if (fait) cible.querySelector(".retour-lot")?.replaceChildren(messageFait(fait, "commande(s)"));
  };
  const agir = (action) => traiterEnLot({ cles: [...selection], action, traiter: api.traiterCommandes, nature: "commande(s)", surTermine: rafraichir });
  const actions = barreActions(selection, [
    { element: el("button", { type: "button", class: "bouton bouton--danger", onclick: () => agir("supprimer") }, "Supprimer"), actif: (n) => n > 0 },
    { element: el("button", { type: "button", class: "bouton bouton--discret", onclick: () => agir("archiver") }, "Archiver"), actif: (n) => n > 0 },
  ]);
  cible.replaceChildren(
    el("h2", {}, "Commandes et devis"),
    el("p", { class: "texte-doux" }, "Une commande sans pièce reçue et sans mouvement de stock lié peut être supprimée, avec ses lignes et ses documents (fichiers compris)."),
    el("div", { class: "filtres" }, el("label", { class: "filtre-case" }, caseACocher(false, (v) => {
      filtres.archives = v;
      selection.clear();
      actions.maj();
      rendre();
    }, "Inclure les archivées"), "Inclure les archivées")),
    actions.zone,
    el("div", { class: "retour-lot" }),
    table,
  );
  rendre();
}

// --- Blocs, ensembles et fournisseurs inutilisés ---------------------------------------------------

async function sectionEntites(cible) {
  const entites = await api.getEntitesSupprimables();
  const supprimer = async (entite) => {
    if (!confirm(`Supprimer définitivement ${TYPES_ENTITE[entite.type].toLowerCase()} « ${entite.nom} » ?\n\nUne sauvegarde de la base est prise juste avant.`)) return;
    try {
      await api.supprimerEntite(entite.type, entite.cle);
      masquerErreur();
      await sectionEntites(cible);
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const lignes = entites.map((e) =>
    el(
      "tr",
      { class: e.archive ? "ligne--inactive" : "" },
      el("td", {}, TYPES_ENTITE[e.type]),
      el("td", { class: "code" }, e.cle),
      el("td", {}, e.type === "fournisseur" ? "" : e.nom),
      el("td", {}, e.archive ? el("span", { class: "etiquette" }, "Archivé") : ""),
      el("td", { class: "nombre" }, el("button", { type: "button", class: "bouton bouton--petit bouton--danger", onclick: () => supprimer(e) }, "Supprimer")),
    ),
  );
  cible.replaceChildren(
    el("h2", {}, "Blocs, ensembles et fournisseurs inutilisés"),
    el("p", { class: "texte-doux" }, "Seuls apparaissent ceux qui n'ont laissé aucune trace : bloc sans composant, ensemble sans affectation ni montage, fournisseur cité nulle part (archivés compris)."),
    lignes.length
      ? el(
          "table",
          { class: "table table--dense table--parametres" },
          el("thead", {}, el("tr", {}, el("th", {}, "Type"), el("th", {}, "Code ou nom"), el("th", {}, "Nom"), el("th", {}), el("th", {}))),
          el("tbody", {}, lignes),
        )
      : el("p", { class: "texte-doux" }, "Rien à supprimer : tout est utilisé."),
  );
}

// --- Journal -------------------------------------------------------------------------------------

function sectionJournal(cible) {
  const bouton = el("button", { type: "button", class: "bouton bouton--danger" }, "Vider le journal");
  const retour = el("div");
  bouton.addEventListener("click", async () => {
    if (!confirm("Vider le journal ?\n\nL'historique de toutes les modifications sera effacé. Une sauvegarde de la base est prise juste avant.")) return;
    if (!confirm("Confirmer : l'historique des fiches (qui a changé quoi, quand) repartira de zéro.")) return;
    bouton.disabled = true;
    try {
      const { lignes_supprimees: nombre } = await api.viderJournal();
      masquerErreur();
      retour.replaceChildren(el("p", { class: "message message-ok" }, `Journal vidé : ${formatNombre(nombre)} ligne(s) supprimée(s). Une ligne trace la purge.`));
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      bouton.disabled = false;
    }
  });
  cible.replaceChildren(
    el("div", { class: "titre-section" }, el("h2", {}, "Journal"), bouton),
    el("p", { class: "texte-doux" }, "Pour repartir d'une base propre : l'historique est effacé, après sauvegarde. Le journal garde une seule ligne, celle qui trace la purge."),
    retour,
  );
}

// --- Écran -------------------------------------------------------------------------------------

async function charger(section, afficher) {
  try {
    await afficher();
  } catch (erreur) {
    section.replaceChildren(el("p", { class: "texte-doux" }, "Chargement impossible."));
    afficherErreur(erreur);
  }
}

export async function afficherNettoyage(conteneur) {
  const blocs = await api.getBlocs({ archives: true });
  const zones = [0, 1, 2, 3].map(() => el("section", { class: "panneau" }));
  conteneur.replaceChildren(
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, "Nettoyage"),
      el("a", { class: "bouton bouton--discret", href: lienRoute("/parametres") }, "Retour aux paramètres"),
    ),
    ...zones,
  );
  // Supprimer des composants ou des commandes peut libérer un bloc ou un fournisseur.
  const rechargerEntites = () => charger(zones[2], () => sectionEntites(zones[2]));
  await Promise.all([
    charger(zones[0], () => sectionComposants(zones[0], blocs, rechargerEntites)),
    charger(zones[1], () => sectionCommandes(zones[1], rechargerEntites)),
    rechargerEntites(),
  ]);
  sectionJournal(zones[3]);
}
