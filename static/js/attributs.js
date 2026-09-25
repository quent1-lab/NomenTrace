// Attributs paramétrables (tension, matériau…) : définitions chargées depuis la base,
// affichage des valeurs et champs de saisie selon le type.

import { api } from "./api.js";
import { formatNombre, lireNombre } from "./format.js";
import { el } from "./ui.js";

export const TYPES_ATTRIBUT = {
  texte: "Texte",
  nombre: "Nombre",
  liste: "Liste de valeurs",
  booleen: "Oui / non",
};
export const PREFIXE = "attr:";

let definitions = [];

export async function chargerAttributs() {
  definitions = await api.getAttributs();
  return definitions;
}

export function tousLesAttributs() {
  return definitions;
}

export function attributsActifs() {
  return definitions.filter((a) => a.actif);
}

export function attribut(code) {
  return definitions.find((a) => a.code === code) ?? null;
}

// « Tension (V) » : libellé et unité, comme en tête de colonne des exports.
export function titreAttribut(a) {
  return a.unite ? `${a.libelle} (${a.unite})` : a.libelle;
}

// Nombre sans zéros inutiles : 3,3 et non 3,30 ; 12 et non 12,00.
function nombreCourt(valeur) {
  const decimales = Math.min(6, (String(valeur).split(".")[1] ?? "").length);
  return formatNombre(valeur, decimales);
}

// Valeur lisible : nombre avec son unité, libellé de liste, Oui / Non.
export function formatAttribut(a, valeur) {
  if (valeur === null || valeur === undefined) return "";
  if (a.type === "nombre") return a.unite ? `${nombreCourt(valeur)} ${a.unite}` : nombreCourt(valeur);
  if (a.type === "booleen") return valeur === "1" ? "Oui" : "Non";
  if (a.type === "liste") return a.valeurs.find((v) => v.code === valeur)?.libelle ?? valeur;
  return valeur;
}

// Options d'une liste : les valeurs actives, plus la valeur courante si elle est désactivée.
export function optionsListe(a, valeurCourante = null, { inclureInactives = false } = {}) {
  return a.valeurs
    .filter((v) => v.actif || inclureInactives || v.code === valeurCourante)
    .map((v) => [v.code, v.actif ? v.libelle : `${v.libelle} (désactivée)`]);
}

/**
 * Champ de saisie d'un attribut ; renvoie { element, lire } où lire() donne
 * { valeur } (null = vide) ou { erreur }.
 */
export function champAttribut(a, valeur) {
  if (a.type === "liste" || a.type === "booleen") {
    const options = a.type === "booleen" ? [["1", "Oui"], ["0", "Non"]] : optionsListe(a, valeur);
    const select = el("select", { class: "champ", name: `${PREFIXE}${a.code}` }, el("option", { value: "" }, "—"));
    for (const [code, texte] of options) select.append(el("option", { value: code, selected: code === valeur }, texte));
    if (valeur === null || valeur === undefined) select.value = "";
    return { element: select, lire: () => ({ valeur: select.value || null }) };
  }
  if (a.type === "nombre") {
    const texte = valeur === null || valeur === undefined ? "" : nombreCourt(valeur);
    const input = el("input", { class: "champ champ--nombre", type: "text", inputmode: "decimal", name: `${PREFIXE}${a.code}`, value: texte });
    const lire = () => {
      const brut = input.value.trim().replace(/\s*[a-zA-Zµ°Ω%]+$/, "");
      if (brut === "") return { valeur: null };
      const nombre = lireNombre(brut.replace(/^−/, "-"));
      if (nombre === null || Number.isNaN(nombre)) return { erreur: `${a.libelle} : « ${input.value} » n'est pas un nombre.` };
      return { valeur: nombre };
    };
    return { element: input, lire };
  }
  const input = el("input", { class: "champ", type: "text", name: `${PREFIXE}${a.code}`, value: valeur ?? "" });
  return { element: input, lire: () => ({ valeur: input.value.trim() || null }) };
}

// --- Filtres « code:operation[:valeur] » de la liste des composants ----------------------------

export const OPERATIONS = {
  egal: "est égal à",
  entre: "entre",
  renseigne: "est renseigné",
  vide: "est vide",
};

export function lireFiltre(texte) {
  const [code, operation, ...reste] = texte.split(":");
  const valeur = reste.join(":");
  if (operation === "entre") {
    const [min = "", max = ""] = valeur.split(":");
    return { code, operation, min, max };
  }
  return { code, operation, valeur };
}

export function ecrireFiltre({ code, operation, valeur = "", min = "", max = "" }) {
  if (operation === "entre") return `${code}:entre:${min}:${max}`;
  if (operation === "egal") return `${code}:egal:${valeur}`;
  return `${code}:${operation}`;
}

// Texte d'une pastille de filtre : « Tension entre 5 et 50 V ».
export function libelleFiltre(filtre) {
  const a = attribut(filtre.code);
  if (!a) return filtre.code;
  if (filtre.operation === "vide") return `${a.libelle} non renseigné`;
  if (filtre.operation === "renseigne") return `${a.libelle} renseigné`;
  if (filtre.operation === "entre") {
    const unite = a.unite ? ` ${a.unite}` : "";
    if (filtre.min && filtre.max) return `${a.libelle} entre ${filtre.min} et ${filtre.max}${unite}`;
    return filtre.min ? `${a.libelle} ≥ ${filtre.min}${unite}` : `${a.libelle} ≤ ${filtre.max}${unite}`;
  }
  const affiche = a.type === "nombre" ? `${filtre.valeur}${a.unite ? ` ${a.unite}` : ""}` : formatAttribut(a, filtre.valeur);
  return `${a.libelle} = ${affiche}`;
}
