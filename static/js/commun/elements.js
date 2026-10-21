// Éléments partagés des pages communes : carte d'un projet, en-tête du compte, formulaires.

import { api } from "../api.js";
import { formatMontant, formatPourcent } from "../format.js";
import { ligneChamp } from "../formulaire.js";
import { fermerPanneau } from "../panneau.js";
import { afficherErreur, el, largeur, masquerErreur } from "../ui.js";

const ACCES = { lecteur: "Lecteur", contributeur: "Contributeur", administrateur: "Administrateur" };

export const PROFILS = [
  ["gestion", "Gestion complète"],
  ["lecture", "Lecture de tous les projets"],
  ["achats_stock", "Achats et stock"],
];

export function nomProjet(carte) {
  return [carte.nom_projet, carte.nom_equipe].filter(Boolean).join(" · ") || carte.code;
}

export function libelleAcces(acces) {
  return acces ? ACCES[acces] : "Résumé seul";
}

function barre(pourcent) {
  const remplissage = el("div", { class: "barre__remplissage" });
  return el("div", { class: "barre barre--fine" }, largeur(remplissage, pourcent ?? 0));
}

function resume(carte) {
  if (carte.hors_ligne) return el("p", { class: "texte-doux texte-petit" }, "Hors ligne : sa base n'a pas pu être préparée.");
  if (!carte.resume) return null;
  const { avancement_appro_pct: pct, budget_ht: budget, montant_engage_ht: engage } = carte.resume;
  return [
    el("div", { class: "carte__avancement-libelle" }, el("span", {}, "Approvisionnement"), el("span", {}, pct === null ? "—" : formatPourcent(pct, 0))),
    barre(pct),
    el(
      "div",
      { class: "carte__avancement-libelle" },
      el("span", {}, "Engagé"),
      el("span", {}, budget === null ? formatMontant(engage) : `${formatMontant(engage)} sur ${formatMontant(budget)}`),
    ),
  ];
}

// Carte d'un projet : lien vers le projet si le compte y a accès, sinon résumé seul.
export function carteProjet(carte, actions = null) {
  const ouvrable = carte.acces && !carte.hors_ligne;
  const corps = [
    el("div", { class: "carte__entete" }, el("strong", {}, nomProjet(carte)), el("span", { class: "etiquette" }, libelleAcces(carte.acces))),
    ...[resume(carte)].flat(),
  ];
  const tuile = ouvrable
    ? el("a", { class: "carte carte--cliquable carte--projet", href: `/p/${carte.code}/` }, corps)
    : el("div", { class: "carte carte--projet" }, corps);
  return actions ? el("div", { class: "carte-et-actions" }, tuile, el("div", { class: "carte__pied" }, actions)) : tuile;
}

// En-tête : nom du compte et déconnexion (rien en mode local, sans compte).
export function afficherCompte(compte) {
  const zone = document.getElementById("entete-compte");
  if (compte.local) return zone.replaceChildren(el("span", { class: "entete__role" }, "Mode local"));
  const sortir = async () => {
    try {
      await api.deconnecter();
    } finally {
      window.location.assign("/connexion.html");
    }
  };
  zone.replaceChildren(
    el("span", { class: "entete__nom" }, compte.nom),
    compte.admin_serveur ? el("span", { class: "entete__role" }, "administrateur du serveur") : null,
    el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: sortir }, "Se déconnecter"),
  );
}

// Formulaire du panneau latéral : champs, puis envoi ; `envoyer` reçoit les valeurs lues.
export function formulairePanneau(champs, libelleBouton, envoyer) {
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    champs.map(([libelle, champ, options]) => ligneChamp(libelle, champ, options)),
    el(
      "div",
      { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, libelleBouton),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await envoyer(formulaire.elements, formulaire);
      masquerErreur();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

// Code d'adresse proposé d'après un nom : minuscules sans accents, tirets.
export function codeDepuis(nom) {
  return nom
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}
