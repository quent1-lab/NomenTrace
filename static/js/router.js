// Routage par hash (#/chemin?parametres), sans rechargement de page.

export function lireRoute() {
  const brut = window.location.hash.replace(/^#/, "") || "/";
  const [chemin, requete = ""] = brut.split("?");
  return { chemin, parametres: new URLSearchParams(requete) };
}

export function demarrerRouteur(surChangement) {
  window.addEventListener("hashchange", () => surChangement(lireRoute()));
  surChangement(lireRoute());
}
