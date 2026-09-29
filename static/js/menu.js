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

// Sur téléphone, le menu est un tiroir par-dessus la page : le bouton l'ouvre ou le ferme, et
// il se referme dès qu'on choisit un écran ou qu'on touche la page. Même seuil que style.css.
const TELEPHONE = window.matchMedia("(max-width: 800px)");

function basculerTiroir(bouton, ouvert) {
  if (ouvert) document.documentElement.dataset.tiroir = "ouvert";
  else delete document.documentElement.dataset.tiroir;
  bouton.setAttribute("aria-expanded", String(ouvert));
  bouton.setAttribute("aria-label", ouvert ? "Fermer le menu" : "Ouvrir le menu");
}

export function installerMenu() {
  const bouton = document.getElementById("bascule-menu");
  const menu = document.getElementById("menu-principal");
  appliquer(lireEtat(), bouton);
  if (TELEPHONE.matches) basculerTiroir(bouton, false);
  bouton.addEventListener("click", () => {
    if (TELEPHONE.matches) {
      basculerTiroir(bouton, document.documentElement.dataset.tiroir !== "ouvert");
      return;
    }
    const suivant = ETATS[(ETATS.indexOf(document.documentElement.dataset.menu) + 1) % ETATS.length];
    ecrireEtat(suivant);
    appliquer(suivant, bouton);
  });
  window.addEventListener("hashchange", () => basculerTiroir(bouton, false));
  document.addEventListener("click", (e) => {
    if (document.documentElement.dataset.tiroir && !menu.contains(e.target) && !bouton.contains(e.target)) {
      basculerTiroir(bouton, false);
    }
  });
  TELEPHONE.addEventListener("change", () => {
    if (TELEPHONE.matches) basculerTiroir(bouton, false);
    else appliquer(lireEtat(), bouton);
  });
}
