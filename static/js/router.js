// Routage par hash (#/chemin?parametres), sans rechargement de page.

export function lireRoute() {
  const brut = window.location.hash.replace(/^#/, "") || "/";
  const [chemin, requete = ""] = brut.split("?");
  return { chemin: chemin || "/", parametres: new URLSearchParams(requete) };
}

export function lienRoute(chemin, parametres = {}) {
  const requete = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(parametres)) {
    if (valeur !== undefined && valeur !== null && valeur !== "") requete.set(cle, valeur);
  }
  const texte = requete.toString();
  return `#${chemin}${texte ? "?" + texte : ""}`;
}

export function naviguer(chemin, parametres = {}) {
  window.location.hash = lienRoute(chemin, parametres);
}

// Met à jour l'adresse sans recharger l'écran (filtres, tri, fiche ouverte).
export function remplacerRoute(chemin, parametres = {}) {
  history.replaceState(null, "", lienRoute(chemin, parametres));
}

export function demarrerRouteur(surChangement) {
  window.addEventListener("hashchange", () => surChangement(lireRoute()));
  surChangement(lireRoute());
}
