// Menu latéral repliable : déplié, réduit à une colonne d'icônes, ou masqué.
// L'état est une préférence d'affichage gardée dans localStorage, pas une donnée métier.

const CLE = "nomentrace.menu";
const ETATS = ["deplie", "icones", "masque"];
const ACTIONS = {
  deplie: "Réduire le menu à ses icônes",
  icones: "Masquer le menu",
  masque: "Afficher le menu",
};

function lireEtat() {
  try {
    const etat = localStorage.getItem(CLE);
    return ETATS.includes(etat) ? etat : "deplie";
  } catch {
    return "deplie";
  }
}

function ecrireEtat(etat) {
  try {
    localStorage.setItem(CLE, etat);
  } catch {
    // Sans localStorage, l'état vaut pour la page ouverte seulement.
  }
}

function appliquer(etat, bouton) {
  document.documentElement.dataset.menu = etat;
  bouton.title = ACTIONS[etat];
  bouton.setAttribute("aria-label", ACTIONS[etat]);
  bouton.setAttribute("aria-expanded", String(etat !== "masque"));
}

export function installerMenu() {
  const bouton = document.getElementById("bascule-menu");
  appliquer(lireEtat(), bouton);
  bouton.addEventListener("click", () => {
    const suivant = ETATS[(ETATS.indexOf(document.documentElement.dataset.menu) + 1) % ETATS.length];
    ecrireEtat(suivant);
    appliquer(suivant, bouton);
  });
}
