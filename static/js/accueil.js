// Pages communes, hors de tout projet : accueil (/), dossier (/d/<code>/), organisme
// (/o/<code>/). Le serveur sert la même page pour les trois ; elle lit son adresse.
// Un compte qui n'a qu'un projet est envoyé directement dessus, sauf avec « ?accueil ».

import { api } from "./api.js";
import { afficherDossier } from "./commun/dossier.js";
import { afficherCompte, carteProjet, codeDepuis, formulairePanneau } from "./commun/elements.js";
import { afficherOrganisme } from "./commun/organisme.js";
import { champChoix, champTexte } from "./formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "./panneau.js";
import { afficherErreur, el } from "./ui.js";

const contenu = document.getElementById("contenu-commun");
const fil = document.getElementById("fil-commun");

function nouvelOrganisme() {
  const nom = champTexte("nom", "", { maxlength: "80" });
  const code = champTexte("code", "", { maxlength: "40" });
  nom.addEventListener("input", () => {
    code.value = codeDepuis(nom.value);
  });
  const formulaire = formulairePanneau(
    [
      ["Nom", nom, { requis: true }],
      ["Code d'adresse", code, { requis: true, aide: "Figé après la création." }],
    ],
    "Créer l'organisme",
    async (champs) => {
      await api.createOrganisme({ nom: champs.nom.value.trim(), code: champs.code.value.trim() });
      fermerPanneau({ silencieux: true });
      await afficherAccueil();
    },
  );
  ouvrirPanneau("Nouvel organisme", formulaire);
  nom.focus();
}

function ranger(carte, dossiers) {
  const choix = champChoix("dossier", dossiers.map((d) => [d.code, `${d.organisme} › ${d.nom}`]), null, { vide: "Choisir un dossier" });
  const equipe = champTexte("nom_equipe", carte.nom_equipe ?? "", { maxlength: "80" });
  const formulaire = formulairePanneau(
    [
      ["Dossier", choix, { requis: true }],
      ["Nom d'équipe", equipe],
    ],
    "Ranger",
    async (champs) => {
      if (!champs.dossier.value) throw new Error("Choisir un dossier.");
      await api.patchProjet(carte.code, { dossier: champs.dossier.value, nom_equipe: champs.nom_equipe.value.trim() || null });
      fermerPanneau({ silencieux: true });
      await afficherAccueil();
    },
  );
  ouvrirPanneau("Ranger dans un dossier", formulaire);
}

function sectionOrganisme(org) {
  return el(
    "section",
    { class: "commun__organisme" },
    el("div", { class: "titre-section" }, el("h1", {}, org.nom), org.page ? el("a", { href: `/o/${org.code}/` }, "Page de l'organisme") : null),
    org.dossiers.length
      ? org.dossiers.map((dos) =>
          el(
            "div",
            { class: "commun__dossier" },
            el(
              "div",
              { class: "titre-section" },
              el("h2", {}, dos.nom),
              dos.page ? el("a", { href: `/d/${dos.code}/` }, "Page du dossier") : null,
            ),
            dos.projets.length
              ? el("div", { class: "grille-cartes" }, dos.projets.map((c) => carteProjet(c)))
              : el("p", { class: "texte-doux" }, "Aucun projet dans ce dossier."),
          ),
        )
      : el("p", { class: "texte-doux" }, "Aucun dossier."),
  );
}

async function afficherAccueil() {
  const accueil = await api.getAccueil();
  if (accueil.destination && !new URLSearchParams(window.location.search).has("accueil")) {
    window.location.replace(accueil.destination + window.location.hash);
    return;
  }
  afficherCompte(accueil.compte);
  fil.textContent = "Vos projets";
  const serveur = accueil.compte.admin_serveur;
  const dossiers = accueil.organismes.flatMap((o) => o.dossiers.map((d) => ({ ...d, organisme: o.nom })));
  const horsDossier = accueil.hors_dossier.map((c) =>
    carteProjet(c, serveur ? el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ranger(c, dossiers) }, "Ranger dans un dossier") : null),
  );
  const vide = !accueil.organismes.length && !horsDossier.length;
  const sections = [
    serveur
      ? el("div", { class: "actions actions--droite" }, el("button", { type: "button", class: "bouton", onclick: nouvelOrganisme }, "Nouvel organisme"))
      : null,
    accueil.organismes.map(sectionOrganisme),
    horsDossier.length
      ? el("section", { class: "commun__organisme" }, el("h2", {}, "Hors dossier"), el("div", { class: "grille-cartes" }, horsDossier))
      : null,
    vide ? el("p", { class: "etat-vide" }, "Aucun projet ne vous est ouvert pour l'instant.") : null,
  ];
  contenu.replaceChildren(...sections.flat().filter(Boolean));
}

async function demarrer() {
  const [, niveau, code] = window.location.pathname.match(/^\/([do])\/([a-z0-9][a-z0-9-]*)\/$/) ?? [];
  try {
    if (niveau === "d") await afficherDossier(code, { contenu, fil });
    else if (niveau === "o") await afficherOrganisme(code, { contenu, fil });
    else await afficherAccueil();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

demarrer();
