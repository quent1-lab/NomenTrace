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
