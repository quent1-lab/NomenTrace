// Comparaison des fournisseurs avec une liste Excel : on choisit ce qui est créé et complété,
// rien n'est écrit avant « Appliquer ».

import { api } from "../api.js";
import { afficherErreur, afficherAvertissements, el, masquerErreur } from "../ui.js";
import { LIBELLES_FOURNISSEUR, lienFournisseur, vueContact } from "./fournisseurs_commun.js";

const CHAMPS_CREATION = ["categorie", "contact", "numero_compte", "site_web", "pays", "type", "delai_moyen_j", "commentaire"];

function valeurCourte(champ, valeur) {
  if (valeur === null || valeur === undefined || valeur === "") return el("span", { class: "texte-doux" }, "vide");
  return champ === "contact" ? vueContact(valeur) : String(valeur);
}

function section(titre, aide, contenu) {
  return el("section", { class: "panneau" }, el("h2", {}, titre), aide ? el("p", { class: "texte-doux texte-petit" }, aide) : null, contenu);
}

// Une ligne par fournisseur à créer : case à cocher et nom modifiable.
function sectionNouveaux(nouveaux, choix) {
  if (!nouveaux.length) return null;
  const lignes = nouveaux.map((lu) => {
    const coche = el("input", { type: "checkbox", checked: true, "aria-label": `Créer ${lu.nom}` });
    const nom = el("input", { class: "champ", type: "text", value: lu.nom, "aria-label": "Nom du fournisseur à créer" });
    choix.push(() => (coche.checked && nom.value.trim() ? { creation: { ...lu, nom: nom.value.trim() } } : null));
    return el(
      "tr",
      {},
      el("td", {}, coche),
      el("td", { class: "cellule-nom" }, nom),
      el("td", {}, lu.categorie ?? ""),
      el("td", { class: "texte-petit" }, vueContact(lu.contact)),
      el("td", {}, lu.numero_compte ?? ""),
      el("td", { class: "texte-petit" }, lu.site_web ?? ""),
    );
  });
  return section(
    `À créer (${nouveaux.length})`,
    "Absents de l'outil. Le nom peut être corrigé avant création (majuscules, espaces…).",
    el(
      "table",
      { class: "table table--dense table--parametres" },
      el("thead", {}, el("tr", {}, ["", "Nom", "Catégorie", "Contact", "N° de compte", "Site web"].map((t) => el("th", {}, t)))),
      el("tbody", {}, lignes),
    ),
  );
}

// Écarts d'un fournisseur existant : une case par champ. Les champs vides dans l'outil sont
// cochés d'office ; écraser une valeur déjà saisie se décide au cas par cas.
function tableEcarts(entree) {
  const cases = [];
  const lignes = Object.entries(entree.differences).map(([champ, { actuel, liste }]) => {
    const coche = el("input", { type: "checkbox", checked: actuel === null || actuel === "", "aria-label": `Reprendre ${LIBELLES_FOURNISSEUR[champ]}` });
    cases.push([champ, liste, coche]);
    return el(
      "tr",
      {},
      el("td", {}, coche),
      el("td", {}, LIBELLES_FOURNISSEUR[champ]),
      el("td", {}, valeurCourte(champ, actuel)),
      el("td", {}, valeurCourte(champ, liste)),
    );
  });
  const reactiver = entree.archive ? el("input", { type: "checkbox", checked: true }) : null;
  const valider = entree.a_valider ? el("input", { type: "checkbox", checked: true }) : null;
  const table = el(
    "table",
    { class: "table table--dense table--ecarts" },
    el("thead", {}, el("tr", {}, ["", "Champ", "Dans l'outil", "Dans la liste"].map((t) => el("th", {}, t)))),
    el("tbody", {}, lignes),
  );
  const lire = () => {
    const champs = Object.fromEntries(cases.filter(([, , c]) => c.checked).map(([champ, liste]) => [champ, liste]));
    if (valider?.checked) champs.statut = "Valide";
    if (!Object.keys(champs).length && !reactiver?.checked) return null;
    return { completion: { nom: entree.nom, champs } };
  };
  return {
    contenu: [
      reactiver ? el("label", { class: "filtre-case" }, reactiver, "Réactiver ce fournisseur (il est archivé)") : null,
      valider ? el("label", { class: "filtre-case" }, valider, "Valider ce fournisseur : il figure dans la liste de référence") : null,
      lignes.length ? table : null,
    ],
    lire,
  };
}

function sectionProbables(probables, choix) {
  if (!probables.length) return null;
  const blocs = probables.map((entree) => {
    const decision = el(
      "select",
      { class: "filtre", "aria-label": `Décision pour ${entree.liste.nom}` },
      el("option", { value: "completer" }, `Même fournisseur : compléter « ${entree.nom} »`),
      el("option", { value: "creer" }, `Fournisseur différent : créer « ${entree.liste.nom} »`),
      el("option", { value: "ignorer" }, "Ignorer"),
    );
    const ecarts = tableEcarts(entree);
    const zoneEcarts = el("div", {}, ecarts.contenu);
    decision.addEventListener("change", () => {
      zoneEcarts.hidden = decision.value !== "completer";
    });
    choix.push(() => {
      if (decision.value === "creer") return { creation: entree.liste };
      if (decision.value === "completer") return ecarts.lire();
      return null;
    });
    return el(
      "div",
      { class: "comparaison" },
      el("p", {}, lienFournisseur(entree.nom), " ↔ ", el("strong", {}, entree.liste.nom), " ", decision),
      zoneEcarts,
    );
  });
  return section(
    `Correspondances probables (${probables.length})`,
    "Noms proches mais pas identiques : à confirmer.",
    blocs,
  );
}

function sectionEcarts(presents, choix) {
  const avecEcarts = presents.filter((e) => Object.keys(e.differences).length || e.archive || e.a_valider);
  if (!avecEcarts.length) return null;
  const blocs = avecEcarts.map((entree) => {
    const ecarts = tableEcarts(entree);
    choix.push(ecarts.lire);
    return el("div", { class: "comparaison" }, el("p", {}, lienFournisseur(entree.nom)), ecarts.contenu);
  });
  return section(
    `Déjà présents, avec des écarts (${avecEcarts.length})`,
    "Les champs vides dans l'outil sont repris d'office ; cocher pour remplacer une valeur déjà saisie.",
    blocs,
  );
}

function sectionInfos(presents, absents) {
  const identiques = presents.filter((e) => !Object.keys(e.differences).length && !e.archive && !e.a_valider);
  return section(
    "Pour information",
    null,
    [
      el("p", {}, el("strong", {}, `Identiques (${identiques.length}) : `), identiques.map((e) => e.nom).join(", ") || "aucun"),
      el(
        "p",
        {},
        el("strong", {}, `Dans l'outil mais absents de la liste (${absents.length}) : `),
        absents.join(", ") || "aucun",
        absents.length ? el("span", { class: "texte-doux" }, " — rien n'est archivé automatiquement.") : null,
      ),
    ],
  );
}

function corpsApplication(choix) {
  const corps = { creations: [], completions: [] };
  for (const lire of choix) {
    const resultat = lire();
    if (resultat?.creation) {
      corps.creations.push(Object.fromEntries(Object.entries(resultat.creation).filter(([cle, v]) => v !== null && (cle === "nom" || CHAMPS_CREATION.includes(cle)))));
    }
    if (resultat?.completion) corps.completions.push(resultat.completion);
  }
  return corps;
}

export function afficherComparaison(cible, resultat, nomFichier, surTermine) {
  const choix = [];
  const appliquer = el("button", { type: "button", class: "bouton" }, "Appliquer");
  appliquer.addEventListener("click", async () => {
    const corps = corpsApplication(choix);
    if (!corps.creations.length && !corps.completions.length) return afficherErreur("Rien n'est coché : aucune modification à appliquer.");
    if (!confirm(`Créer ${corps.creations.length} fournisseur(s) et en compléter ${corps.completions.length} ?`)) return;
    appliquer.disabled = true;
    try {
      const bilan = await api.appliquerComparaison(corps);
      masquerErreur();
      afficherAvertissements([`Liste appliquée : ${bilan.crees} fournisseur(s) créé(s), ${bilan.completes} complété(s).`]);
      await surTermine();
    } catch (erreur) {
      afficherErreur(erreur);
      appliquer.disabled = false;
    }
  });
  const barre = el(
    "div",
    { class: "barre-application" },
    el("span", { class: "texte-doux" }, `Comparaison avec « ${nomFichier} » — rien n'est enregistré avant « Appliquer ».`),
    el("span", { class: "actions" }, el("button", { type: "button", class: "bouton bouton--discret", onclick: () => surTermine() }, "Annuler"), appliquer),
  );
  cible.replaceChildren(
    barre,
    sectionNouveaux(resultat.nouveaux, choix),
    sectionProbables(resultat.probables, choix),
    sectionEcarts(resultat.presents, choix),
    sectionInfos(resultat.presents, resultat.absents),
  );
}
