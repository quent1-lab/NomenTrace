// Onglet « Attributs » des paramètres : caractéristiques des composants propres au projet
// (tension, matériau…). Le code et le type d'un attribut sont figés à sa création.

import { api } from "../api.js";
import { TYPES_ATTRIBUT, chargerAttributs, tousLesAttributs } from "../attributs.js";
import { lienRoute } from "../router.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";

let conteneur = null;

async function executer(action) {
  try {
    await action();
    masquerErreur();
    await chargerAttributs();
    rendre();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

// Champ texte modifié au flou ou à Entrée ; Échap rétablit la valeur.
function champEnLigne(valeur, surValide, { libelle, vide = false, classe = "champ" } = {}) {
  const champ = el("input", { class: classe, type: "text", value: valeur ?? "", "aria-label": libelle });
  const valider = () => {
    const texte = champ.value.trim();
    if (texte === (valeur ?? "") || (!texte && !vide)) {
      champ.value = valeur ?? "";
      return;
    }
    surValide(texte);
  };
  champ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") valider();
    if (e.key === "Escape") champ.value = valeur ?? "";
  });
  champ.addEventListener("blur", valider);
  return champ;
}

// Échange les rangs de deux éléments voisins ; `patch(element, ordre)` enregistre un rang.
function deplacer(elements, index, decalage, patch) {
  const voisin = elements[index + decalage];
  if (!voisin) return;
  const courant = elements[index];
  const ordreCourant = courant.ordre === voisin.ordre ? courant.ordre + decalage : voisin.ordre;
  executer(async () => {
    await patch(courant, ordreCourant);
    await patch(voisin, courant.ordre);
  });
}

function boutonsOrdre(elements, index, patch) {
  return el(
    "td",
    { class: "ordre" },
    el("button", { type: "button", class: "bouton-icone", title: "Monter", disabled: index === 0, onclick: () => deplacer(elements, index, -1, patch) }, "▲"),
    el("button", { type: "button", class: "bouton-icone", title: "Descendre", disabled: index === elements.length - 1, onclick: () => deplacer(elements, index, 1, patch) }, "▼"),
  );
}

function caseActif(actif, libelle, surChangement) {
  const coche = el("input", { type: "checkbox", checked: Boolean(actif), "aria-label": `${libelle} actif` });
  coche.addEventListener("change", () => surChangement(coche.checked ? 1 : 0));
  return el("label", { class: "filtre-case" }, coche, "actif");
}

// --- Attributs ----------------------------------------------------------------------------------

const patchOrdreAttribut = (a, ordre) => api.patchAttribut(a.code, { ordre });

function ligneAttribut(attributs, index) {
  const a = attributs[index];
  return el(
    "tr",
    { class: a.actif ? "" : "ligne--inactive" },
    boutonsOrdre(attributs, index, patchOrdreAttribut),
    el("td", {}, champEnLigne(a.libelle, (texte) => executer(() => api.patchAttribut(a.code, { libelle: texte })), { libelle: `Libellé de ${a.code}` })),
    el("td", { class: "code texte-doux" }, a.code),
    el("td", {}, TYPES_ATTRIBUT[a.type]),
    el("td", {}, champEnLigne(a.unite, (texte) => executer(() => api.patchAttribut(a.code, { unite: texte || null })), { libelle: `Unité de ${a.code}`, vide: true, classe: "champ champ--court" })),
    el("td", {}, caseActif(a.actif, a.libelle, (actif) => executer(() => api.patchAttribut(a.code, { actif })))),
    el("td", { class: "nombre" }, el("a", { href: lienRoute("/attributs", { attribut: a.code }) }, "Répartition")),
  );
}

function formulaireAttribut() {
  const libelle = el("input", { class: "champ", type: "text", placeholder: "Libellé (ex. Tension)", maxlength: "60", "aria-label": "Libellé" });
  const type = el("select", { class: "champ", "aria-label": "Type" }, Object.entries(TYPES_ATTRIBUT).map(([code, texte]) => el("option", { value: code }, texte)));
  const unite = el("input", { class: "champ champ--court", type: "text", placeholder: "Unité (ex. V)", maxlength: "20", "aria-label": "Unité" });
  const formulaire = el("form", { class: "formulaire-ligne" }, libelle, type, unite, el("button", { type: "submit", class: "bouton" }, "Créer l'attribut"));
  formulaire.addEventListener("submit", (e) => {
    e.preventDefault();
    const texte = libelle.value.trim();
    if (!texte) return afficherErreur("Saisir le libellé du nouvel attribut.");
    executer(() => api.createAttribut({ libelle: texte, type: type.value, unite: unite.value.trim() || null }));
  });
  return formulaire;
}

// --- Valeurs d'un attribut de type liste ----------------------------------------------------------

function sectionValeurs(a) {
  const patchOrdre = (v, ordre) => api.patchValeurAttribut(a.code, v.code, { ordre });
  const lignes = a.valeurs.map((v, index) =>
    el(
      "tr",
      { class: v.actif ? "" : "ligne--inactive" },
      boutonsOrdre(a.valeurs, index, patchOrdre),
      el("td", {}, champEnLigne(v.libelle, (texte) => executer(() => api.patchValeurAttribut(a.code, v.code, { libelle: texte })), { libelle: `Libellé de ${v.code}` })),
      el("td", { class: "code texte-doux" }, v.code),
      el("td", {}, caseActif(v.actif, v.libelle, (actif) => executer(() => api.patchValeurAttribut(a.code, v.code, { actif })))),
    ),
  );
  const libelle = el("input", { class: "champ", type: "text", placeholder: "Nouvelle valeur…", maxlength: "60", "aria-label": `Nouvelle valeur de ${a.libelle}` });
  const ajout = el("form", { class: "formulaire-ligne" }, libelle, el("button", { type: "submit", class: "bouton" }, "Ajouter"));
  ajout.addEventListener("submit", (e) => {
    e.preventDefault();
    const texte = libelle.value.trim();
    if (!texte) return afficherErreur("Saisir le libellé de la nouvelle valeur.");
    executer(() => api.createValeurAttribut(a.code, texte));
  });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, `Valeurs de « ${a.libelle} »`),
    lignes.length
      ? el(
          "table",
          { class: "table table--dense table--listes" },
          el("thead", {}, el("tr", {}, ["", "Libellé affiché", "Code stocké", ""].map((t) => el("th", {}, t)))),
          el("tbody", {}, lignes),
        )
      : el("p", { class: "texte-doux" }, "Aucune valeur pour l'instant."),
    ajout,
  );
}

function rendre() {
  const attributs = tousLesAttributs();
  conteneur.replaceChildren(
    el(
      "p",
      { class: "texte-doux" },
      "Les attributs sont les caractéristiques des composants propres au projet : tension, matériau, étanchéité… " +
        "Chacun devient une colonne affichable, filtrable et triable de l'écran Composants, une colonne des exports et des modèles Excel. " +
        "Le code et le type sont figés à la création ; le libellé et l'unité se modifient. Un attribut désactivé n'est plus proposé à la saisie.",
    ),
    el(
      "section",
      { class: "panneau" },
      attributs.length
        ? el(
            "table",
            { class: "table table--dense table--listes" },
            el("thead", {}, el("tr", {}, ["", "Libellé", "Code", "Type", "Unité", "", ""].map((t) => el("th", {}, t)))),
            el("tbody", {}, attributs.map((_, i) => ligneAttribut(attributs, i))),
          )
        : el("p", { class: "texte-doux" }, "Aucun attribut pour l'instant. La tension est un bon premier attribut : type Nombre, unité V."),
      formulaireAttribut(),
    ),
    ...attributs.filter((a) => a.type === "liste").map(sectionValeurs),
  );
}

export async function afficherOngletAttributs(cible) {
  conteneur = cible;
  await chargerAttributs();
  rendre();
}
