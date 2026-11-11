// Page d'un organisme (/o/<code>/) : ses dossiers, et pour l'administrateur de l'organisme
// la création d'un dossier, les profils de ses administrateurs et le nom de l'organisme.

import { api } from "../api.js";
import { formatMontant } from "../format.js";
import { champChoix, champTexte, suivreModifications } from "../formulaire.js";
import { encartInvitation } from "../invitation.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { PROFILS, afficherCompte, codeDepuis, formulairePanneau, zoneSuppression } from "./elements.js";

function nouveauDossier(organisme, rafraichir) {
  const nom = champTexte("nom", "", { maxlength: "80" });
  const code = champTexte("code", "", { maxlength: "40" });
  nom.addEventListener("input", () => {
    code.value = codeDepuis(nom.value);
  });
  const formulaire = formulairePanneau(
    [
      ["Nom", nom, { requis: true }],
      ["Code d'adresse", code, { requis: true, aide: "Figé après la création." }],
      ["Nom du projet", champTexte("nom_projet", "", { maxlength: "80" }), { aide: "Imposé aux projets du dossier, par exemple le nom de l'épreuve. Vide : chaque projet choisit le sien." }],
    ],
    "Créer le dossier",
    async (champs) => {
      await api.createDossier(organisme.code, {
        nom: champs.nom.value.trim(),
        code: champs.code.value.trim(),
        nom_projet: champs.nom_projet.value.trim() || null,
      });
      fermerPanneau({ silencieux: true });
      await rafraichir();
    },
  );
  ouvrirPanneau("Nouveau dossier", formulaire);
  nom.focus();
}

function inviter(organisme, rafraichir) {
  const formulaire = formulairePanneau(
    [
      ["Adresse mail", champTexte("identifiant", "", { type: "email", autocomplete: "off" }), { requis: true }],
      ["Nom affiché", champTexte("nom", "", { maxlength: "60" }), { requis: true }],
      ["Profil", champChoix("profil", PROFILS, "lecture"), { requis: true }],
    ],
    "Inviter",
    async (champs, form) => {
      const cree = await api.createMembreOrganisme(organisme.code, {
        identifiant: champs.identifiant.value.trim(),
        nom: champs.nom.value.trim(),
        profil: champs.profil.value,
      });
      await rafraichir();
      if (cree.jeton) form.replaceChildren(encartInvitation(champs.nom.value.trim(), cree));
      else fermerPanneau({ silencieux: true });
    },
  );
  ouvrirPanneau("Inviter un administrateur d'organisme", formulaire);
}

async function agir(action, rafraichir) {
  try {
    await action();
    masquerErreur();
    await rafraichir();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function panneauMembres(organisme, rafraichir) {
  if (!organisme.gestion) return null;
  const lignes = organisme.membres.map((m) => {
    const profil = champChoix(`profil-${m.id}`, PROFILS, m.profil);
    profil.setAttribute("aria-label", `Profil de ${m.nom}`);
    profil.addEventListener("change", () => agir(() => api.patchMembreOrganisme(organisme.code, m.id, profil.value), rafraichir));
    const retirer = () => confirm(`Retirer le profil de ${m.nom} ?`) && agir(() => api.retirerMembreOrganisme(organisme.code, m.id), rafraichir);
    // En liste plutôt qu'en tableau : la colonne de côté est trop étroite pour quatre colonnes.
    return el(
      "li",
      { class: "membre" },
      el("span", {}, m.nom),
      el("span", { class: "membre__adresse texte-doux texte-petit" }, m.identifiant),
      el("span", { class: "membre__actions" }, profil, el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: retirer }, "Retirer")),
    );
  });
  return el(
    "section",
    { class: "panneau" },
    el(
      "div",
      { class: "titre-section" },
      el("h2", {}, "Administrateurs de l'organisme"),
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => inviter(organisme, rafraichir) }, "Inviter"),
    ),
    lignes.length
      ? el("ul", { class: "liste-simple" }, lignes)
      : el("p", { class: "texte-doux" }, "Aucun administrateur d'organisme."),
    el("p", { class: "texte-doux texte-petit" }, "Les membres d'un projet s'invitent depuis l'écran Utilisateurs de ce projet."),
  );
}

function panneauNom(organisme, rafraichir) {
  if (!organisme.gestion) return null;
  const formulaire = formulairePanneau(
    [
      ["Nom", champTexte("nom", organisme.nom, { maxlength: "80" }), { requis: true }],
      ["Budgets saisis en", champChoix("saisie_budget", [["HT", "HT"], ["TTC", "TTC"]], organisme.saisie_budget ?? "HT"), {
        aide: "Unité dans laquelle on saisit les budgets des dossiers et des projets. Ils restent calculés en HT : un montant TTC est converti au taux de TVA par défaut.",
      }],
    ],
    "Enregistrer",
    async (champs) => {
      await api.patchOrganisme(organisme.code, { nom: champs.nom.value.trim(), saisie_budget: champs.saisie_budget.value });
      await rafraichir();
    },
  );
  formulaire.querySelector(".bouton--discret").remove();
  suivreModifications(formulaire);
  const suppression = organisme.compte?.admin_serveur
    ? zoneSuppression("Supprimer l'organisme", organisme.code, `Supprimer l'organisme « ${organisme.nom} », ses ${organisme.dossiers.length} dossier(s), tous leurs projets et sa liste de fournisseurs ?`, async (confirmation) => {
        await api.supprimerOrganisme(organisme.code, confirmation);
        window.location.assign("/");
      })
    : null;
  return el("section", { class: "panneau" }, el("h2", {}, "Organisme"), formulaire, suppression);
}

export async function afficherOrganisme(code, { contenu, fil }) {
  const rafraichir = () => afficherOrganisme(code, { contenu, fil });
  const organisme = await api.getOrganisme(code);
  afficherCompte(organisme.compte);
  fil.textContent = organisme.nom;
  document.title = `${organisme.nom} · Nomentrace`;
  const lignes = organisme.dossiers.map((d) =>
    el(
      "tr",
      {},
      el("td", {}, el("a", { href: `/d/${d.code}/` }, el("strong", {}, d.nom))),
      el("td", { class: "nombre" }, String(d.nb_projets)),
      el("td", { class: "nombre" }, formatMontant(d.enveloppe_ht) || "—"),
      el("td", { class: "nombre" }, formatMontant(d.budget_ht)),
    ),
  );
  contenu.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("h1", {}, organisme.nom),
      el("a", { class: "bouton bouton--discret", href: `/p/${organisme.fournisseurs}/#/parametres?onglet=fournisseurs` }, "Fournisseurs"),
    ),
    el(
      "div",
      { class: "commun__colonnes" },
      el(
        "section",
        { class: "panneau" },
        el(
          "div",
          { class: "titre-section" },
          el("h2", {}, "Dossiers"),
          organisme.gestion ? el("button", { type: "button", class: "bouton", onclick: () => nouveauDossier(organisme, rafraichir) }, "Nouveau dossier") : null,
        ),
        lignes.length
          ? el(
              "table",
              { class: "table" },
              el("thead", {}, el("tr", {}, el("th", {}, "Dossier"), el("th", { class: "nombre" }, "Projets"), el("th", { class: "nombre" }, "Enveloppe HT"), el("th", { class: "nombre" }, "Budgets des projets HT"))),
              el("tbody", {}, lignes),
            )
          : el("p", { class: "texte-doux" }, "Aucun dossier."),
      ),
      el("aside", { class: "commun__cote" }, panneauMembres(organisme, rafraichir), panneauNom(organisme, rafraichir)),
    ),
  );
}
