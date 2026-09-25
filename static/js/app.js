// Point d'entrée du front : en-tête, état de l'export, menu et routage.

import { allerConnexion, api, surEcriture } from "./api.js";
import { detruireGraphiques } from "./graphiques.js";
import { installerMenu } from "./menu.js";
import { fermerPanneau } from "./panneau.js";
import { installerRecherche } from "./recherche.js";
import { afficherAchats } from "./pages/achats.js";
import { afficherAttributs } from "./pages/attributs.js";
import { afficherBlocs } from "./pages/blocs.js";
import { afficherDetailCommande } from "./pages/commande_detail.js";
import { afficherComposants } from "./pages/composants.js";
import { afficherDetailEnsemble } from "./pages/ensemble_detail.js";
import { afficherEnsembles } from "./pages/ensembles.js";
import { afficherRevueImport } from "./pages/import_revue.js";
import { afficherImports } from "./pages/imports.js";
import { afficherNettoyage } from "./pages/nettoyage.js";
import { afficherParametres } from "./pages/parametres.js";
import { afficherFicheFournisseur } from "./pages/fournisseur_detail.js";
import { afficherStock } from "./pages/stock.js";
import { afficherTableau } from "./pages/tableau.js";
import { demarrerRouteur } from "./router.js";
import { chargerSession, libelleRole, modeLocal, utilisateur } from "./session.js";
import { chargerListes } from "./valeurs.js";
import { afficherErreur, el } from "./ui.js";

const ROUTES = {
  "/": afficherTableau,
  "/blocs": afficherBlocs,
  "/composants": afficherComposants,
  "/ensembles": afficherEnsembles,
  "/achats": afficherAchats,
  "/stock": afficherStock,
  "/attributs": afficherAttributs,
  "/parametres": afficherParametres,
  "/imports": afficherImports,
  "/nettoyage": afficherNettoyage,
};

// Routes à paramètre : #/ensembles/CODE et #/achats/NUMERO.
function routeParametree(chemin) {
  const detail = chemin.match(/^\/ensembles\/([^/]+)$/);
  if (detail) {
    const code = decodeURIComponent(detail[1]);
    return (conteneur, parametres) => afficherDetailEnsemble(conteneur, parametres, code);
  }
  const fournisseur = chemin.match(/^\/fournisseurs\/([^/]+)$/);
  if (fournisseur) {
    const nom = decodeURIComponent(fournisseur[1]);
    return (conteneur, parametres) => afficherFicheFournisseur(conteneur, parametres, nom);
  }
  const depot = chemin.match(/^\/imports\/(\d+)$/);
  if (depot) return (conteneur, parametres) => afficherRevueImport(conteneur, parametres, depot[1]);
  const commande = chemin.match(/^\/achats\/([^/]+)$/);
  if (commande) {
    const numero = decodeURIComponent(commande[1]);
    return (conteneur, parametres) => afficherDetailCommande(conteneur, parametres, numero);
  }
  return null;
}

const TITRES_A_VENIR = {
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
  const segment = chemin.split("/")[1] ?? "";
  // La fiche d'un fournisseur et l'écran nettoyage se rattachent à l'écran Paramètres.
  const racine = "/" + (["fournisseurs", "nettoyage"].includes(segment) ? "parametres" : segment);
  document.querySelectorAll(".menu__lien").forEach((lien) => {
    lien.classList.toggle("menu__lien--actif", lien.dataset.route === racine);
  });
}

async function afficherRoute({ chemin, parametres }) {
  detruireGraphiques();
  fermerPanneau({ silencieux: true });
  marquerMenu(chemin);
  const page = ROUTES[chemin] ?? routeParametree(chemin);
  const racine = "/" + (chemin.split("/")[1] ?? "");
  try {
    if (page) {
      await page(contenu, parametres);
    } else if (TITRES_A_VENIR[racine]) {
      pageAVenir(contenu, TITRES_A_VENIR[racine]);
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
window.addEventListener("nomentrace:projet", rafraichirEntete);

// Nom de l'utilisateur, son rôle et la déconnexion ; rien en mode local, sans compte.
function afficherUtilisateur() {
  const zone = document.getElementById("entete-utilisateur");
  const moi = utilisateur();
  if (!moi || modeLocal()) {
    zone.replaceChildren(el("span", { class: "entete__role", title: "Lancé sans connexion, sur ce poste seulement" }, "Mode local"));
    return;
  }
  const deconnexion = el("button", { type: "button", class: "bouton bouton--petit bouton--discret" }, "Déconnexion");
  deconnexion.addEventListener("click", async () => {
    try {
      await api.deconnecter();
    } catch (erreur) {
      afficherErreur(erreur);
      return;
    }
    window.location.assign("/connexion.html");
  });
  zone.replaceChildren(
    el("span", { class: "entete__nom", title: moi.identifiant }, moi.nom),
    el("span", { class: "entete__role" }, libelleRole(moi.role)),
    deconnexion,
  );
}

async function demarrer() {
  try {
    await chargerSession();
  } catch (erreur) {
    if (erreur.statut === 401) allerConnexion();
    else afficherErreur(erreur);
    return;
  }
  afficherUtilisateur();
  installerMenu();
  installerRecherche(document.getElementById("recherche-globale"));
  try {
    await chargerListes();
  } catch (erreur) {
    afficherErreur(erreur);
  }
  rafraichirEntete();
  demarrerRouteur(afficherRoute);
}

demarrer();
