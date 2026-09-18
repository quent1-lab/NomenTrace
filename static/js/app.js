// Point d'entrée du front : en-tête, état de l'export, menu et routage.

import { api, surEcriture } from "./api.js";
import { detruireGraphiques } from "./graphiques.js";
import { afficherBlocs } from "./pages/blocs.js";
import { afficherTableau } from "./pages/tableau.js";
import { demarrerRouteur } from "./router.js";
import { afficherErreur, el } from "./ui.js";

const ROUTES = {
  "/": afficherTableau,
  "/blocs": afficherBlocs,
};

const TITRES_A_VENIR = {
  "/ensembles": "Ensembles",
  "/composants": "Composants",
  "/achats": "Achats",
  "/stock": "Stock",
  "/imports": "Imports",
  "/parametres": "Paramètres",
};

const contenu = document.getElementById("contenu");
const etatExport = document.getElementById("etat-export");

function pageAVenir(conteneur, titre) {
  conteneur.replaceChildren(
    el("h1", {}, titre),
    el("p", { class: "texte-doux" }, "Cet écran sera disponible dans une prochaine version."),
  );
}

function marquerMenu(chemin) {
  const racine = "/" + (chemin.split("/")[1] ?? "");
  document.querySelectorAll(".menu__lien").forEach((lien) => {
    lien.classList.toggle("menu__lien--actif", lien.dataset.route === racine);
  });
}

async function afficherRoute({ chemin }) {
  detruireGraphiques();
  marquerMenu(chemin);
  const page = ROUTES[chemin];
  try {
    if (page) {
      await page(contenu);
    } else if (TITRES_A_VENIR[chemin]) {
      pageAVenir(contenu, TITRES_A_VENIR[chemin]);
    } else {
      pageAVenir(contenu, "Page introuvable");
    }
  } catch (erreur) {
    contenu.replaceChildren(el("h1", {}, "Chargement impossible"));
    afficherErreur(erreur);
  }
}

async function rafraichirEntete() {
  try {
    const sante = await api.getSante();
    const projet = sante.nom_projet ?? "";
    document.getElementById("nom-projet").textContent = projet;
    document.title = projet ? `Nomentrace — ${projet}` : "Nomentrace";
    etatExport.textContent = sante.export_en_attente
      ? "Export Excel en attente (fichier ouvert ?)"
      : "Export Excel à jour";
    etatExport.classList.toggle("etat-export--attente", sante.export_en_attente);
  } catch (erreur) {
    etatExport.textContent = "Serveur injoignable";
    etatExport.classList.add("etat-export--attente");
    afficherErreur(erreur);
  }
}

// L'export part environ 2 s après une écriture : on relit son état un peu plus tard.
surEcriture(() => setTimeout(rafraichirEntete, 3500));
setInterval(rafraichirEntete, 15000);

rafraichirEntete();
demarrerRouteur(afficherRoute);
