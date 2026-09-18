// Point d'entrée du front : en-tête, bandeau d'erreur, routage.

import { api } from "./api.js";
import { demarrerRouteur } from "./router.js";

const bandeau = document.getElementById("bandeau-erreur");

export function afficherErreur(message) {
  bandeau.textContent = message;
  bandeau.hidden = false;
}

async function chargerEntete() {
  try {
    const sante = await api.getSante();
    const projet = sante.nom_projet ?? "";
    document.getElementById("nom-projet").textContent = projet;
    document.title = projet ? `Nomentrace — ${projet}` : "Nomentrace";
  } catch (erreur) {
    afficherErreur(erreur.message);
  }
}

function afficherRoute() {
  document.getElementById("contenu").textContent = "";
}

chargerEntete();
demarrerRouteur(afficherRoute);
