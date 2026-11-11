// Page d'un dossier (/d/<code>/) : ses projets en tableau, ses commandes communes, ses
// responsables achats, et pour
// l'administrateur de l'organisme la création d'un projet et le nom du dossier.

import { api } from "../api.js";
import { formatMontant, formatPourcent, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, suivreModifications } from "../formulaire.js";
import { encartInvitation } from "../invitation.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, afficherInformation, el, masquerErreur } from "../ui.js";
import { panneauCommunes } from "./communes.js";
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
      dossier.nom_projet
        ? ["Nom du projet", champTexte("nom_projet", dossier.nom_projet, { disabled: true }), { aide: "Imposé par le dossier." }]
        : ["Nom du projet", champTexte("nom_projet", "", { maxlength: "80" }), { aide: "Le dossier n'en impose pas : modifiable ensuite dans les paramètres du projet." }],
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
        nom_projet: dossier.nom_projet ? null : champs.nom_projet.value.trim() || null,
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

// Unité de saisie des budgets, choisie par l'organisme : clé envoyée et suffixe affiché.
function unite(dossier) {
  return dossier.saisie_budget === "TTC" ? { cle: "budget_ttc", suffixe: "TTC" } : { cle: "budget_ht", suffixe: "HT" };
}

function equivalentHt(dossier, montantHt) {
  return dossier.saisie_budget === "TTC" && montantHt != null ? ` Soit ${formatMontant(montantHt)} HT.` : "";
}

function fixerBudget(dossier, carte, rafraichir) {
  const { cle, suffixe } = unite(dossier);
  const impose = Boolean(carte.resume?.budget_impose);
  const budget = champNombre(cle, impose ? (carte.resume?.[cle] ?? null) : null, 2);
  const actuel = !impose && carte.resume?.[cle] != null ? ` Le projet a fixé le sien : ${formatMontant(carte.resume[cle])} ${suffixe}.` : "";
  const formulaire = formulairePanneau(
    [[`Budget ${suffixe}`, budget, { aide: `Fixé ici, il s'impose au projet. Laisser vide pour le rendre au projet, qui garde le dernier montant.${actuel}${impose ? equivalentHt(dossier, carte.resume?.budget_ht) : ""}` }]],
    "Enregistrer",
    async (champs) => {
      const valeur = lireNombre(champs[cle].value);
      if (Number.isNaN(valeur)) throw new Error("Budget illisible.");
      await api.patchProjet(carte.code, { [cle]: valeur });
      fermerPanneau({ silencieux: true });
      await rafraichir();
    },
  );
  suivreModifications(formulaire);
  ouvrirPanneau(`Budget de ${nomProjet(carte)}`, formulaire);
  budget.focus();
}

// Nom d'équipe et retrait d'un projet, pour qui gère l'organisme.
function modifierProjet(carte, rafraichir) {
  const equipe = champTexte("nom_equipe", carte.nom_equipe ?? "", { maxlength: "80" });
  const formulaire = formulairePanneau(
    [["Nom d'équipe", equipe, { aide: `Affiché après le nom du projet. Le code d'adresse (${carte.code}) ne change pas.` }]],
    "Enregistrer",
    async (champs) => {
      await api.patchProjet(carte.code, { nom_equipe: champs.nom_equipe.value.trim() || null });
      fermerPanneau({ silencieux: true });
      await rafraichir();
    },
  );
  suivreModifications(formulaire);
  const retirer = el("button", { type: "button", class: "bouton bouton--danger" }, "Retirer le projet");
  retirer.addEventListener("click", async () => {
    const question =
      `Retirer le projet « ${nomProjet(carte)} » ?

` +
      "Vide (ni composant, ni commande, ni mouvement de stock, ni document), il est supprimé : " +
      "une sauvegarde est prise et ses fichiers partent à la corbeille du serveur. " +
      "Sinon, il est seulement archivé : masqué, ses données gardées.";
    if (!confirm(question)) return;
    try {
      const resultat = await api.retirerProjet(carte.code);
      fermerPanneau({ silencieux: true });
      masquerErreur();
      await rafraichir();
      afficherInformation(
        resultat.action === "archive" ? `Projet archivé : il contient encore ${resultat.traces.join(", ")}.` : "Projet supprimé.",
      );
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau(`Projet ${nomProjet(carte)}`, el("div", {}, formulaire, el("section", { class: "zone-retrait" }, el("h3", {}, "Retirer le projet"), el("p", { class: "texte-doux texte-petit" }, "Supprimé s'il est vide, archivé sinon."), retirer)));
  equipe.focus();
}

// Budget réglé par le projet lui-même (le dossier n'en a pas fixé).
function origineBudget(resume) {
  return resume.budget_ht != null && !resume.budget_impose ? el("span", { class: "texte-doux texte-petit" }, " (projet)") : null;
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
    el(
      "td",
      {},
      dossier.gestion && !carte.hors_ligne
        ? el("button", { type: "button", class: "bouton-lien", title: "Nom d'équipe, retrait du projet", onclick: () => modifierProjet(carte, rafraichir) }, el("strong", {}, nomProjet(carte)))
        : el("strong", {}, nomProjet(carte)),
    ),
    el("td", {}, libelleAcces(carte.acces)),
    el("td", { class: "nombre" }, r.avancement_appro_pct == null ? "—" : formatPourcent(r.avancement_appro_pct, 0)),
    el(
      "td",
      { class: "nombre" },
      dossier.gestion && !carte.hors_ligne
        ? el("button", { type: "button", class: "bouton-lien", title: "Fixer le budget", onclick: () => fixerBudget(dossier, carte, rafraichir) }, formatMontant(r[unite(dossier).cle]) || "à fixer", origineBudget(r))
        : [formatMontant(r[unite(dossier).cle]), origineBudget(r)],
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

const AIDE_PARTAGE =
  "À la création d'un composant, chaque équipe se voit proposer les références qui ressemblent chez les autres équipes du dossier, avec leurs fiches techniques. Aucune liste n'est montrée en entier ; quantités, commandes et identifiants restent propres à chaque équipe.";

// Membres des projets : l'état de la mise en commun, réglée par l'organisme.
function etatPartage(dossier) {
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Composants"),
    el(
      "p",
      { class: "etat-partage" },
      dossier.partage_composants
        ? el("span", { class: "puce-fiche puce-fiche--conforme" }, "Composants mis en commun")
        : el("span", { class: "puce-fiche puce-fiche--neutre" }, "Composants non partagés"),
      el("span", { class: "texte-doux texte-petit" }, "Réglé par l'organisme"),
    ),
  );
}

function panneauDossier(dossier, rafraichir) {
  if (!dossier.gestion) return etatPartage(dossier);
  const nom = champTexte("nom", dossier.nom, { maxlength: "80" });
  const nomProjetImpose = champTexte("nom_projet", dossier.nom_projet ?? "", { maxlength: "80" });
  const partage = el("input", { type: "checkbox", name: "partage_composants", checked: Boolean(dossier.partage_composants) });
  const { cle, suffixe } = unite(dossier);
  const enveloppe = champNombre(cle, dossier[cle] ?? null, 2);
  const formulaire = formulairePanneau(
    [
      ["Nom du dossier", nom, { requis: true }],
      [`Enveloppe budgétaire ${suffixe}`, enveloppe, { aide: `Budget global du dossier, à répartir entre ses projets. Vide : pas d'enveloppe.${equivalentHt(dossier, dossier.budget_ht)}` }],
      ["Nom du projet", nomProjetImpose, { aide: "Imposé à tous les projets du dossier. Laisser vide pour que chaque projet choisisse le sien." }],
      ["Mettre en commun les composants", partage, { aide: AIDE_PARTAGE }],
    ],
    "Enregistrer",
    async (champs) => {
      const budget = lireNombre(champs[cle].value);
      if (Number.isNaN(budget)) throw new Error("Enveloppe budgétaire illisible.");
      await api.patchDossier(dossier.code, {
        [cle]: budget,
        nom: champs.nom.value.trim(),
        nom_projet: champs.nom_projet.value.trim() || null,
        partage_composants: champs.partage_composants.checked,
      });
      await rafraichir();
    },
  );
  formulaire.querySelector(".bouton--discret").remove();
  suivreModifications(formulaire);
  return el("section", { class: "panneau" }, el("h2", {}, "Dossier"), formulaire);
}

// Enveloppe du dossier, ce que ses projets en ont déjà reçu et ce qui reste à répartir.
function panneauBudget(dossier) {
  const ttc = dossier.saisie_budget === "TTC";
  const suffixe = ttc ? "TTC" : "HT";
  const m = (base) => dossier[`${base}_${ttc ? "ttc" : "ht"}`];
  const reste = m("budget_reste");
  const ligne = (libelle, valeur, classe = "") => el("div", { class: "ligne-budget" }, el("span", {}, libelle), el("strong", { class: classe }, valeur));
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Budget"),
    ligne(`Enveloppe ${suffixe}`, formatMontant(m("budget")) || "non fixée"),
    ligne("Réparti entre les projets", formatMontant(m("budget_reparti")) || formatMontant(0)),
    reste == null ? null : ligne(reste < 0 ? "Dépassement" : "Reste à répartir", formatMontant(Math.abs(reste)), reste < 0 ? "texte-alerte" : ""),
    ttc ? el("p", { class: "texte-doux texte-petit" }, `Montants TTC au taux de ${formatPourcent(dossier.taux_tva * 100, 1)} ; calculés en HT.`) : null,
  );
}

function sectionProjets(dossier, rafraichir) {
  return el(
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
                ["Appro.", `Budget ${unite(dossier).suffixe}`, "Engagé HT"].map((t) => el("th", { class: "nombre" }, t)),
                dossier.gestion ? el("th", {}, "Réglages communs") : null,
                el("th", {}),
              ),
            ),
            el("tbody", {}, dossier.projets.map((carte) => ligneProjet(dossier, carte, rafraichir))),
          ),
        )
      : el("p", { class: "texte-doux" }, "Aucun projet dans ce dossier."),
  );
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
        "div",
        { class: "commun__principal" },
        sectionProjets(dossier, rafraichir),
        panneauCommunes(code),
      ),
      el("aside", { class: "commun__cote" }, panneauBudget(dossier), panneauResponsables(dossier, rafraichir), panneauDossier(dossier, rafraichir)),
    ),
  );
}
