// Onglet Paramètres › Assistant IA : ouverture du projet à un assistant (protocole MCP),
// jetons personnels et commande pour brancher Claude Code. Le jeton n'est montré qu'une fois ;
// le serveur n'en garde que l'empreinte et vérifie tout, l'écran ne fait que présenter.

import { api } from "../api.js";
import { formatDate } from "../format.js";
import { champChoix, champTexte, ligneChamp, suivreModifications } from "../formulaire.js";
import { estAdmin, modeLocal } from "../session.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";

const ACCES = [
  ["ferme", "Fermé"],
  ["admin", "Administrateurs du projet"],
  ["membres", "Tous les membres du projet"],
];

function adresseMcp() {
  const projet = window.location.pathname.match(/^\/p\/[a-z0-9][a-z0-9-]*/)?.[0] ?? "";
  return `${window.location.origin}${projet}/api/mcp`;
}

function commande(jeton) {
  const base = `claude mcp add --transport http nomentrace ${adresseMcp()}`;
  return jeton ? `${base} --header "Authorization: Bearer ${jeton}"` : base;
}

function message(texte, classe = "message-info") {
  return el("p", { class: `message ${classe}` }, texte);
}

// Texte à copier, en lecture seule, avec son bouton.
function copiable(texte, libelle) {
  const champ = el("input", { class: "champ", type: "text", value: texte, readonly: true, "aria-label": libelle });
  champ.addEventListener("focus", () => champ.select());
  const copier = el("button", { type: "button", class: "bouton bouton--petit" }, "Copier");
  copier.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(texte);
      copier.textContent = "Copié";
    } catch {
      champ.select();
    }
  });
  return el("div", { class: "lien-invitation" }, champ, copier);
}

function horodatage(texte) {
  return texte ? `${formatDate(texte.slice(0, 10))} ${texte.slice(11, 16)}` : "jamais";
}

function sectionAcces(reglage, recharger) {
  const choix = champChoix("acces", ACCES, reglage.acces);
  const formulaire = el(
    "form",
    { class: "formulaire formulaire--reglages", novalidate: true },
    ligneChamp("Accès", choix, {
      aide: "Chacun se branche avec son propre jeton et garde ses droits. L'assistant lit tout ce que le compte lit et écrit ce qu'il peut écrire, sans jamais supprimer ni toucher aux budgets, aux comptes, aux sauvegardes ou aux paramètres. Fermer l'accès révoque tous les jetons.",
    }),
    el("div", { class: "actions-formulaire" }, el("button", { type: "submit", class: "bouton" }, "Enregistrer")),
  );
  suivreModifications(formulaire);
  if (!estAdmin()) formulaire.querySelectorAll("select, button").forEach((c) => { c.disabled = true; });
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (choix.value === "ferme" && reglage.jetons.length && !confirm("Fermer l'accès révoque tous les jetons du projet. Continuer ?")) return;
    try {
      await api.patchReglageMcp({ acces: choix.value });
      masquerErreur();
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Accès d'un assistant IA"),
    el("p", { class: "texte-doux" }, "Un assistant comme Claude peut consulter et mettre à jour ce projet par le protocole MCP. Ses écritures sont journalisées au nom du compte, suivi de « (IA) »."),
    formulaire,
  );
}

function tableJetons(reglage, recharger) {
  if (!reglage.jetons.length) return el("p", { class: "texte-doux" }, "Aucun jeton actif.");
  const lignes = reglage.jetons.map((j) => {
    const revoquer = el("button", { type: "button", class: "bouton bouton--discret bouton--petit" }, "Révoquer");
    revoquer.addEventListener("click", async () => {
      if (!confirm(`Révoquer le jeton « ${j.nom} » ? L'assistant qui s'en sert perd l'accès aussitôt.`)) return;
      try {
        await api.deleteJetonMcp(j.id);
        masquerErreur();
        await recharger();
      } catch (erreur) {
        afficherErreur(erreur);
      }
    });
    return el(
      "tr",
      {},
      el("td", {}, j.nom),
      estAdmin() ? el("td", {}, j.proprietaire) : null,
      el("td", {}, horodatage(j.cree_le)),
      el("td", {}, horodatage(j.dernier_usage)),
      el("td", {}, revoquer),
    );
  });
  const entetes = ["Nom", estAdmin() ? "Compte" : null, "Créé le", "Dernier usage", ""].filter((t) => t !== null);
  return el(
    "div",
    { class: "table-cadre" },
    el("table", { class: "table table--dense" }, el("thead", {}, el("tr", {}, entetes.map((t) => el("th", {}, t)))), el("tbody", {}, lignes)),
  );
}

function sectionJetons(reglage, recharger) {
  const nom = champTexte("nom", "", { maxlength: "60", placeholder: "Par exemple : portable" });
  const formulaire = el(
    "form",
    { class: "formulaire formulaire--reglages", novalidate: true },
    ligneChamp("Nom du jeton", nom, { requis: true, aide: "Pour le reconnaître et le révoquer : l'ordinateur ou l'outil qui s'en sert." }),
    el("div", { class: "actions-formulaire" }, el("button", { type: "submit", class: "bouton" }, "Créer un jeton")),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!nom.value.trim()) return afficherErreur("Donner un nom au jeton.");
    try {
      const cree = await api.createJetonMcp({ nom: nom.value.trim() });
      masquerErreur();
      await recharger();
      document.querySelector("[data-jeton-cree]")?.replaceChildren(
        el(
          "div",
          { class: "message message-ok" },
          el("p", {}, "Jeton créé. Il ne sera plus affiché : le copier maintenant et le garder comme un mot de passe."),
          copiable(cree.jeton, "Jeton"),
          el("p", {}, "Pour brancher Claude Code sur ce projet, lancer dans un terminal :"),
          copiable(commande(cree.jeton), "Commande Claude Code"),
        ),
      );
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, estAdmin() ? "Jetons du projet" : "Mes jetons"),
    formulaire,
    el("div", { "data-jeton-cree": "" }),
    tableJetons(reglage, recharger),
  );
}

function sectionLocale() {
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Brancher Claude Code"),
    el("p", {}, "En mode local, aucun jeton : seul ce poste peut joindre Nomentrace. Lancer dans un terminal :"),
    copiable(commande(null), "Commande Claude Code"),
  );
}

export async function afficherOngletIa(cible) {
  const recharger = () => afficherOngletIa(cible);
  const reglage = await api.getReglageMcp();
  const sections = [sectionAcces(reglage, recharger)];
  if (reglage.acces === "ferme") {
    sections.push(message("L'accès est fermé : aucun assistant ne peut se brancher sur ce projet."));
  } else if (modeLocal()) {
    sections.push(sectionLocale());
  } else if (reglage.autorise) {
    sections.push(sectionJetons(reglage, recharger));
  } else {
    sections.push(message("L'accès est réservé aux administrateurs du projet."));
  }
  cible.replaceChildren(el("div", { class: "grille-reglages" }, ...sections));
}
