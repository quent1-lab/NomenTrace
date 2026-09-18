// Petits outils d'interface partagés : création d'éléments et bandeau d'erreur.

// el("div", { class: "carte", onclick: f }, enfant1, "texte", ...)
export function el(balise, attributs = {}, ...enfants) {
  const element = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (valeur === undefined || valeur === null || valeur === false) continue;
    if (cle.startsWith("on") && typeof valeur === "function") {
      element.addEventListener(cle.slice(2), valeur);
    } else if (cle === "class") {
      element.className = valeur;
    } else if (valeur === true) {
      element.setAttribute(cle, "");
    } else {
      element.setAttribute(cle, valeur);
    }
  }
  for (const enfant of enfants.flat()) {
    if (enfant === undefined || enfant === null || enfant === false) continue;
    element.append(enfant instanceof Node ? enfant : String(enfant));
  }
  return element;
}

const bandeau = document.getElementById("bandeau-erreur");
const bandeauTexte = document.getElementById("bandeau-erreur-texte");
document.getElementById("bandeau-erreur-fermer").addEventListener("click", masquerErreur);

export function afficherErreur(erreur) {
  bandeauTexte.textContent = erreur instanceof Error ? erreur.message : String(erreur);
  bandeau.hidden = false;
}

export function masquerErreur() {
  bandeau.hidden = true;
}

// Avertissements non bloquants renvoyés par le serveur (réception excédentaire, stock négatif…).
const bandeauAvertissement = document.getElementById("bandeau-avertissement");
document.getElementById("bandeau-avertissement-fermer").addEventListener("click", () => {
  bandeauAvertissement.hidden = true;
});

export function afficherAvertissements(messages) {
  if (!messages?.length) return;
  document.getElementById("bandeau-avertissement-liste").replaceChildren(...messages.map((m) => el("li", {}, m)));
  bandeauAvertissement.hidden = false;
}

// Largeur d'une barre de progression, bornée entre 0 et 100 %.
export function largeur(element, pourcent) {
  const borne = Math.max(0, Math.min(100, Number(pourcent) || 0));
  element.style.width = `${borne}%`;
  return element;
}

export function couleurCss(nomVariable) {
  return getComputedStyle(document.documentElement).getPropertyValue(nomVariable).trim();
}

// Couleur fixe d'un bloc, selon son rang dans l'ordre des blocs (palette de 9 couleurs).
export const NB_COULEURS_BLOC = 9;

export function classeBloc(rang) {
  return `bloc-${(rang % NB_COULEURS_BLOC) + 1}`;
}

export function couleurBloc(rang) {
  return couleurCss(`--bloc-${(rang % NB_COULEURS_BLOC) + 1}`);
}

// Associe à chaque code de bloc son rang, à partir de la liste triée par ordre.
export function rangsBlocs(blocs) {
  const tries = [...blocs].sort((a, b) => a.ordre - b.ordre || a.code.localeCompare(b.code));
  return new Map(tries.map((bloc, rang) => [bloc.code, rang]));
}

// Lien vers la page produit du fournisseur, ouvert dans un nouvel onglet. Seules les adresses
// http(s) sont rendues cliquables ; le clic n'ouvre pas la fiche de la ligne.
const SVG = "http://www.w3.org/2000/svg";

function iconeLienExterne() {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icone-lien");
  for (const d of ["M9 2h5v5", "M14 2 7 9", "M12 9v4.5a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5H7"]) {
    const trait = document.createElementNS(SVG, "path");
    trait.setAttribute("d", d);
    svg.append(trait);
  }
  return svg;
}

export function lienProduit(adresse) {
  if (!adresse || !/^https?:\/\//i.test(adresse)) return null;
  const lien = el("a", { class: "lien-produit", href: adresse, target: "_blank", rel: "noopener noreferrer", title: `Ouvrir la page produit : ${adresse}` }, iconeLienExterne());
  lien.addEventListener("click", (e) => e.stopPropagation());
  return lien;
}
