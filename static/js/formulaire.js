// Champs de formulaire communs aux panneaux de création et de modification.

import { formatNombre, libelle, lireNombre } from "./format.js";
import { el } from "./ui.js";

export function champTexte(nom, valeur = "", attributs = {}) {
  return el("input", { class: "champ", type: "text", name: nom, value: valeur ?? "", ...attributs });
}

export function champZone(nom, valeur = "") {
  const zone = el("textarea", { class: "champ champ--zone", name: nom, rows: "4" });
  zone.value = valeur ?? "";
  return zone;
}

export function champNombre(nom, valeur, decimales = 0, attributs = {}) {
  const texte = valeur === null || valeur === undefined ? "" : formatNombre(valeur, decimales);
  return el("input", { class: "champ champ--nombre", type: "text", inputmode: "decimal", name: nom, value: texte, ...attributs });
}

// options : liste de valeurs ou de paires [code, libellé].
export function champChoix(nom, options, valeur, { vide = null, requis = false } = {}) {
  const select = el("select", { class: "champ", name: nom, required: requis });
  if (vide !== null) select.append(el("option", { value: "" }, vide));
  for (const option of options) {
    const [code, texte] = Array.isArray(option) ? option : [option, libelle(option)];
    select.append(el("option", { value: code, selected: code === valeur }, texte));
  }
  if (valeur === null || valeur === undefined) select.value = "";
  return select;
}

export function ligneChamp(libelleTexte, champ, { requis = false, aide = "" } = {}) {
  return el(
    "label",
    { class: "ligne-champ" },
    el("span", { class: "ligne-champ__libelle" }, libelleTexte, requis ? el("span", { class: "requis" }, " *") : null),
    champ,
    aide ? el("span", { class: "ligne-champ__aide" }, aide) : null,
  );
}

/**
 * Lit un formulaire selon une description { nom: "texte" | "entier" | "montant" | "taux" | "choix" }.
 * Renvoie { valeurs } ou { erreur } avec un message en français.
 */
export function lireFormulaire(formulaire, description, libelles = {}) {
  const valeurs = {};
  for (const [nom, type] of Object.entries(description)) {
    const champ = formulaire.elements.namedItem(nom);
    const brut = champ.value.trim();
    const nomLisible = libelles[nom] ?? nom;
    if (type === "texte" || type === "choix") {
      valeurs[nom] = brut === "" ? null : brut;
      continue;
    }
    const nombre = lireNombre(brut);
    if (Number.isNaN(nombre)) return { erreur: `${nomLisible} : valeur illisible « ${brut} ».` };
    if (nombre !== null && nombre < 0) return { erreur: `${nomLisible} : la valeur doit être positive.` };
    if (type === "entier" && nombre !== null && !Number.isInteger(nombre)) {
      return { erreur: `${nomLisible} : un nombre entier est attendu.` };
    }
    if (type === "taux" && nombre !== null && nombre >= 100) {
      return { erreur: `${nomLisible} : un taux en pourcentage, inférieur à 100, est attendu.` };
    }
    valeurs[nom] = type === "taux" && nombre !== null ? Math.round(nombre * 1000) / 100000 : nombre;
  }
  return { valeurs };
}
