// Page d'un dossier (/d/<code>/) : ses projets en tableau, ses responsables achats, et pour
// l'administrateur de l'organisme la création d'un projet et le nom du dossier.

import { api } from "../api.js";
import { formatMontant, formatPourcent, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, suivreModifications } from "../formulaire.js";
import { encartInvitation } from "../invitation.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { afficherCompte, codeDepuis, formulairePanneau, libelleAcces, montantSuivi, nomProjet } from "./elements.js";

function prefixeDepuis(nom) {
  return codeDepuis(nom).replace(/-/g, "").toUpperCase().slice(0, 10);
}

function nouveauProjet(dossier, rafraichir) {
  const equipe = champTexte("nom_equipe", "", { maxlength: "80" });
  const code = champTexte("code", "", { maxlength: "40" });
  const prefixe = champTexte("prefixe_id", "", { maxlength: "10" });
  equipe.addEventListener("input", () => {
    code.value = codeDepuis(equipe.value);
    prefixe.value = prefixeDepuis(equipe.value);
  });
  const formulaire = formulairePanneau(
    [
      ["Nom du projet", champTexte("nom_projet", dossier.nom_projet ?? "", { disabled: true }), { aide: "Imposé par le dossier." }],
      ["Nom d'équipe", equipe, { requis: true }],
      ["Code d'adresse", code, { requis: true, aide: "Figé après la création." }],
      ["Préfixe d'identifiant", prefixe, { requis: true, aide: "Majuscules et chiffres, figé après la création." }],
      ["Reprendre de", champChoix("modele", dossier.projets.map((c) => [c.code, nomProjet(c)]), null, { vide: "Aucun projet (départ vide)" }), {
        aide: "Reprend ses statuts d'appro et de choix et son arborescence d'ensembles, sans ses composants.",
      }],
      ["Administrateur du projet (adresse, facultatif)", champTexte("admin_identifiant", "", { type: "email", autocomplete: "off" }), {
        aide: "Reçoit un lien d'invitation ; un compte existant reçoit seulement l'accès.",
      }],
    ],
    "Créer le projet",
    async (champs, form) => {
      const admin = champs.admin_identifiant.value.trim();
      const cree = await api.createProjet(dossier.code, {
        nom_equipe: champs.nom_equipe.value.trim(),
        code: champs.code.value.trim(),
        prefixe_id: champs.prefixe_id.value.trim(),
        admin_identifiant: admin || null,
        modele: champs.modele.value || null,
      });
      await rafraichir();
      if (cree.invitation && !cree.invitation.existant) {
        form.replaceChildren(encartInvitation(cree.invitation.utilisateur.nom, cree.invitation));
      } else {
        fermerPanneau({ silencieux: true });
      }
    },
  );
  ouvrirPanneau("Nouveau projet", formulaire);
  equipe.focus();
}

function fixerBudget(carte, rafraichir) {
  const budget = champNombre("budget_ht", carte.resume?.budget_ht ?? null, 2);
  const formulaire = formulairePanneau(
    [["Budget HT", budget, { aide: "Fixé par le dossier : le projet ne peut pas le changer." }]],
    "Enregistrer",
    async (champs) => {
      const valeur = lireNombre(champs.budget_ht.value);
      if (Number.isNaN(valeur)) throw new Error("Budget illisible.");
      await api.patchProjet(carte.code, { budget_ht: valeur });
      fermerPanneau({ silencieux: true });
      await rafraichir();
    },
  );
  suivreModifications(formulaire);
  ouvrirPanneau(`Budget de ${nomProjet(carte)}`, formulaire);
  budget.focus();
}

function montantEngage(resume) {
  const { estime, montant } = montantSuivi(resume);
  if (!estime) return formatMontant(montant);
  return el("span", { class: "texte-doux", title: "Rien n'est engagé : coût estimé des composants" }, `${formatMontant(montant)} estimé`);
}

function etatReglages(dossier, carte) {
  if (!dossier.gestion) return null;
  const aJour = dossier.a_jour[carte.code];
  return el("span", { class: aJour ? "etiquette" : "etiquette etiquette--attention" }, aJour ? "à jour" : "en retard");
}

function ligneProjet(dossier, carte, rafraichir) {
  const r = carte.resume ?? {};
  const ouvrir = carte.acces && !carte.hors_ligne ? el("a", { class: "bouton bouton--petit bouton--discret", href: `/p/${carte.code}/` }, "Ouvrir") : el("span", { class: "texte-doux" }, carte.hors_ligne ? "hors ligne" : "résumé seul");
  return el(
    "tr",
    {},
    el("td", {}, el("strong", {}, nomProjet(carte))),
    el("td", {}, libelleAcces(carte.acces)),
    el("td", { class: "nombre" }, r.avancement_appro_pct == null ? "—" : formatPourcent(r.avancement_appro_pct, 0)),
    el(
      "td",
      { class: "nombre" },
      dossier.gestion && !carte.hors_ligne
        ? el("button", { type: "button", class: "bouton-lien", title: "Fixer le budget", onclick: () => fixerBudget(carte, rafraichir) }, formatMontant(r.budget_ht) || "à fixer")
        : formatMontant(r.budget_ht),
    ),
    el("td", { class: "nombre" }, montantEngage(carte.resume)),
    dossier.gestion ? el("td", {}, etatReglages(dossier, carte)) : null,
    el("td", { class: "nombre" }, ouvrir),
  );
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

function panneauResponsables(dossier, rafraichir) {
  const lignes = dossier.responsables.map((r) =>
    el(
      "li",
      { class: "ligne-compacte" },
      el("span", {}, r.nom),
      dossier.gestion
        ? el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => agir(() => api.retirerResponsable(dossier.code, r.id), rafraichir) }, "Retirer")
        : null,
    ),
  );
  const pris = new Set(dossier.responsables.map((r) => r.id));
  const candidats = dossier.candidats.filter((c) => !pris.has(c.id));
  const choix = champChoix("candidat", candidats.map((c) => [String(c.id), c.nom]), null, { vide: "Choisir un membre" });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Responsables achats"),
    lignes.length ? el("ul", { class: "liste-simple" }, lignes) : el("p", { class: "texte-doux" }, "Aucun responsable achats."),
    dossier.gestion && candidats.length
      ? el(
          "div",
          { class: "formulaire-ligne" },
          choix,
          el("button", { type: "button", class: "bouton bouton--discret", onclick: () => choix.value && agir(() => api.addResponsable(dossier.code, Number(choix.value)), rafraichir) }, "Ajouter"),
        )
      : null,
  );
}

function panneauDossier(dossier, rafraichir) {
  if (!dossier.gestion) return null;
  const nom = champTexte("nom", dossier.nom, { maxlength: "80" });
  const nomProjetImpose = champTexte("nom_projet", dossier.nom_projet ?? "", { maxlength: "80" });
  const formulaire = formulairePanneau(
    [
      ["Nom du dossier", nom, { requis: true }],
      ["Nom du projet", nomProjetImpose, { aide: "Donné aux projets créés dans ce dossier." }],
    ],
    "Enregistrer",
    async (champs) => {
      await api.patchDossier(dossier.code, { nom: champs.nom.value.trim(), nom_projet: champs.nom_projet.value.trim() || null });
      await rafraichir();
    },
  );
  formulaire.querySelector(".bouton--discret").remove();
  suivreModifications(formulaire);
  return el("section", { class: "panneau" }, el("h2", {}, "Dossier"), formulaire);
}

export async function afficherDossier(code, { contenu, fil }) {
  const rafraichir = () => afficherDossier(code, { contenu, fil });
  const dossier = await api.getDossier(code);
  afficherCompte(dossier.compte);
  fil.replaceChildren(el("a", { href: `/o/${dossier.organisme.code}/` }, dossier.organisme.nom), ` › ${dossier.nom}`);
  document.title = `${dossier.nom} · Nomentrace`;
  contenu.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("h1", {}, dossier.nom),
      dossier.gestion ? el("button", { type: "button", class: "bouton", onclick: () => nouveauProjet(dossier, rafraichir) }, "Nouveau projet") : null,
      dossier.reference
        ? el("a", { class: "bouton bouton--discret", href: `/p/${dossier.reference}/#/parametres` }, "Paramètres communs")
        : null,
    ),
    el(
      "div",
      { class: "commun__colonnes" },
      el(
        "section",
        { class: "panneau" },
        dossier.projets.length
          ? el(
              "div",
              { class: "table-defilante" },
              el(
                "table",
                { class: "table" },
                el(
                  "thead",
                  {},
                  el(
                    "tr",
                    {},
                    ["Projet", "Votre accès"].map((t) => el("th", {}, t)),
                    ["Appro.", "Budget HT", "Engagé HT"].map((t) => el("th", { class: "nombre" }, t)),
                    dossier.gestion ? el("th", {}, "Réglages communs") : null,
                    el("th", {}),
                  ),
                ),
                el("tbody", {}, dossier.projets.map((carte) => ligneProjet(dossier, carte, rafraichir))),
              ),
            )
          : el("p", { class: "texte-doux" }, "Aucun projet dans ce dossier."),
      ),
      el("aside", { class: "commun__cote" }, panneauResponsables(dossier, rafraichir), panneauDossier(dossier, rafraichir)),
    ),
  );
}
