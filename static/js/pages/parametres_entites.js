// Onglets « Blocs », « Ensembles » et « Fournisseurs » des paramètres.

import { api } from "../api.js";
import { formatMontant, formatNombre, libelle } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, lireFormulaire, ligneChamp } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, classeBloc, el, lienProduit, masquerErreur, rangsBlocs } from "../ui.js";
import { BASES_PRIX } from "../valeurs.js";
import { ouvrirFormulaireEnsemble } from "./ensembles_commun.js";

function table(entetes, lignes, vide) {
  if (!lignes.length) return el("p", { class: "texte-doux" }, vide);
  return el(
    "table",
    { class: "table table--dense table--parametres" },
    el("thead", {}, el("tr", {}, entetes.map(([texte, classe]) => el("th", { class: classe }, texte)))),
    el("tbody", {}, lignes),
  );
}

function boutonsFormulaire(texte) {
  return el(
    "div",
    { class: "actions-formulaire" },
    el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
    el("button", { type: "submit", class: "bouton" }, texte),
  );
}

// Envoie le formulaire, ferme le panneau et rafraîchit l'onglet ; l'erreur reste affichée sinon.
function surSoumission(formulaire, envoyer, rafraichir) {
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      if ((await envoyer()) === false) return;
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
}

// --- Blocs fonctionnels ---------------------------------------------------------------------

const DESCRIPTION_BLOC = { nom: "texte", ordre: "entier", budget_cible_ht: "montant", responsable: "texte", description: "texte" };
const LIBELLES_BLOC = { ordre: "Ordre d'affichage", budget_cible_ht: "Budget cible HT" };

function ouvrirFormulaireBloc(bloc, ordreSuggere, rafraichir) {
  const creation = bloc === null;
  const code = champTexte("code", bloc?.code ?? "", { disabled: !creation, maxlength: "4", autocomplete: "off" });
  code.addEventListener("input", () => {
    code.value = code.value.toUpperCase().replace(/[^A-Z]/g, "");
  });
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Code", code, {
      requis: true,
      aide: creation
        ? "2 à 4 lettres majuscules. Il entre dans l'identifiant de chaque composant du bloc et ne pourra plus être modifié."
        : "Le code d'un bloc est figé dans les identifiants de ses composants.",
    }),
    ligneChamp("Nom", champTexte("nom", bloc?.nom ?? ""), { requis: true }),
    ligneChamp("Ordre d'affichage", champNombre("ordre", bloc?.ordre ?? ordreSuggere)),
    ligneChamp("Budget cible HT", champNombre("budget_cible_ht", bloc?.budget_cible_ht ?? null, 2), { aide: "Laisser vide si le bloc n'a pas de budget propre." }),
    ligneChamp("Responsable", champTexte("responsable", bloc?.responsable ?? "")),
    ligneChamp("Description", champZone("description", bloc?.description ?? "")),
    boutonsFormulaire(creation ? "Créer le bloc" : "Enregistrer"),
  );
  surSoumission(
    formulaire,
    async () => {
      const lu = lireFormulaire(formulaire, DESCRIPTION_BLOC, LIBELLES_BLOC);
      if (lu.erreur) throw new Error(lu.erreur);
      if (creation && !/^[A-Z]{2,4}$/.test(code.value)) throw new Error("Le code du bloc doit compter 2 à 4 lettres majuscules.");
      if (!lu.valeurs.nom) throw new Error("Le nom du bloc est obligatoire.");
      if (creation) return api.createBloc({ code: code.value, ...lu.valeurs });
      return api.patchBloc(bloc.code, lu.valeurs);
    },
    rafraichir,
  );
  ouvrirPanneau(creation ? "Nouveau bloc fonctionnel" : `Modifier le bloc ${bloc.code}`, formulaire);
  (creation ? code : formulaire.elements.namedItem("nom")).focus();
}

export async function afficherOngletBlocs(cible) {
  const rafraichir = () => afficherOngletBlocs(cible);
  const blocs = await api.getBlocs();
  const rangs = rangsBlocs(blocs);
  const ordreSuggere = Math.max(0, ...blocs.map((b) => b.ordre)) + 1;
  const lignes = blocs.map((b) =>
    el(
      "tr",
      {},
      el("td", {}, el("span", { class: `etiquette-bloc ${classeBloc(rangs.get(b.code))}` }, b.code)),
      el("td", {}, b.nom),
      el("td", { class: "nombre" }, formatNombre(b.ordre)),
      el("td", { class: "nombre" }, b.budget_cible_ht === null ? "—" : formatMontant(b.budget_cible_ht)),
      el("td", {}, b.responsable ?? ""),
      el("td", { class: "nombre" }, formatNombre(b.nb_composants)),
      el("td", { class: "nombre" }, el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireBloc(b, ordreSuggere, rafraichir) }, "Modifier")),
    ),
  );
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "Le bloc est le découpage fonctionnel : un seul par composant, figé dans son identifiant. Un bloc ne se supprime pas."),
      el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireBloc(null, ordreSuggere, rafraichir) }, "Nouveau bloc"),
    ),
    table(
      [["Code"], ["Nom"], ["Ordre", "nombre"], ["Budget cible HT", "nombre"], ["Responsable"], ["Composants", "nombre"], [""]],
      lignes,
      "Aucun bloc fonctionnel pour l'instant. Créer le premier pour pouvoir saisir des composants.",
    ),
  );
}

// --- Ensembles --------------------------------------------------------------------------------

export async function afficherOngletEnsembles(cible) {
  const rafraichir = () => afficherOngletEnsembles(cible);
  const ensembles = await api.getEnsembles();
  const ordreSuggere = Math.max(0, ...ensembles.map((e) => e.ordre)) + 1;
  const archiver = async (ensemble) => {
    const message =
      `Archiver l'ensemble « ${ensemble.nom} » ?\n\n` +
      `Il disparaîtra des listes. Ses ${ensemble.nb_composants_distincts} affectation(s) et l'historique sont conservés.`;
    if (!confirm(message)) return;
    try {
      await api.archiveEnsemble(ensemble.code);
      masquerErreur();
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const lignes = ensembles.map((e) =>
    el(
      "tr",
      {},
      el("td", {}, el("span", { class: "etiquette" }, e.code)),
      el("td", {}, e.nom),
      el("td", { class: "nombre" }, formatNombre(e.ordre)),
      el("td", {}, e.responsable ?? ""),
      el("td", {}, libelle(e.statut_montage)),
      el("td", { class: "nombre" }, formatNombre(e.nb_composants_distincts)),
      el(
        "td",
        { class: "nombre" },
        el("span", { class: "actions actions--droite" },
          el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireEnsemble({ ensemble: e, surEnregistre: rafraichir }) }, "Modifier"),
          el("button", { type: "button", class: "bouton bouton--petit bouton--danger", onclick: () => archiver(e) }, "Archiver"),
        ),
      ),
    ),
  );
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "L'ensemble est le découpage physique : un composant peut entrer dans plusieurs ensembles, avec une quantité pour chacun."),
      el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireEnsemble({ ordreSuggere, surEnregistre: rafraichir }) }, "Nouvel ensemble"),
    ),
    table(
      [["Code"], ["Nom"], ["Ordre", "nombre"], ["Responsable"], ["Montage"], ["Composants", "nombre"], [""]],
      lignes,
      "Aucun ensemble pour l'instant.",
    ),
  );
}

// --- Fournisseurs -----------------------------------------------------------------------------

const DESCRIPTION_FOURNISSEUR = {
  nom: "texte",
  type: "texte",
  base_prix_defaut: "choix",
  pays: "texte",
  site_web: "texte",
  compte_ecole: "texte",
  delai_moyen_j: "entier",
  commentaire: "texte",
};

function ouvrirFormulaireFournisseur(fournisseur, rafraichir) {
  const creation = fournisseur === null;
  const f = fournisseur ?? {};
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Nom", champTexte("nom", f.nom ?? ""), {
      requis: true,
      aide: creation ? "" : "Renommer met à jour les composants et les commandes qui citent ce fournisseur.",
    }),
    ligneChamp("Type", champTexte("type", f.type ?? ""), { aide: "Distributeur, fabricant, atelier…" }),
    ligneChamp("Prix affichés en", champChoix("base_prix_defaut", BASES_PRIX, f.base_prix_defaut ?? null, { vide: "—" })),
    ligneChamp("Pays", champTexte("pays", f.pays ?? "")),
    ligneChamp("Site web", champTexte("site_web", f.site_web ?? "", { placeholder: "https://…" })),
    ligneChamp("Compte client", champTexte("compte_ecole", f.compte_ecole ?? "")),
    ligneChamp("Délai moyen (jours)", champNombre("delai_moyen_j", f.delai_moyen_j ?? null)),
    ligneChamp("Commentaire", champZone("commentaire", f.commentaire ?? "")),
    boutonsFormulaire(creation ? "Créer le fournisseur" : "Enregistrer"),
  );
  surSoumission(
    formulaire,
    async () => {
      const lu = lireFormulaire(formulaire, DESCRIPTION_FOURNISSEUR, { delai_moyen_j: "Délai moyen" });
      if (lu.erreur) throw new Error(lu.erreur);
      if (!lu.valeurs.nom) throw new Error("Le nom du fournisseur est obligatoire.");
      if (creation) return api.createFournisseur(lu.valeurs);
      return api.patchFournisseur(fournisseur.nom, lu.valeurs);
    },
    rafraichir,
  );
  ouvrirPanneau(creation ? "Nouveau fournisseur" : `Modifier ${fournisseur.nom}`, formulaire);
  formulaire.elements.namedItem("nom").focus();
}

export async function afficherOngletFournisseurs(cible) {
  const rafraichir = () => afficherOngletFournisseurs(cible);
  const fournisseurs = await api.getFournisseurs();
  const archiver = async (f) => {
    const usages = f.nb_composants + f.nb_commandes;
    const message =
      `Archiver le fournisseur « ${f.nom} » ?\n\n` +
      (usages
        ? `Il reste cité par ${f.nb_composants} composant(s) et ${f.nb_commandes} commande(s), qui le gardent. `
        : "") +
      "Il ne sera plus proposé dans les listes. Recréer un fournisseur du même nom le réactive.";
    if (!confirm(message)) return;
    try {
      await api.archiveFournisseur(f.nom);
      masquerErreur();
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const lignes = fournisseurs.map((f) =>
    el(
      "tr",
      {},
      el("td", {}, f.nom, " ", lienProduit(f.site_web)),
      el("td", {}, f.type ?? ""),
      el("td", {}, f.pays ?? ""),
      el("td", {}, f.base_prix_defaut ?? ""),
      el("td", { class: "nombre" }, f.delai_moyen_j === null ? "" : `${formatNombre(f.delai_moyen_j)} j`),
      el("td", { class: "nombre" }, formatNombre(f.nb_composants)),
      el("td", { class: "nombre" }, formatNombre(f.nb_commandes)),
      el(
        "td",
        { class: "nombre" },
        el("span", { class: "actions actions--droite" },
          el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireFournisseur(f, rafraichir) }, "Modifier"),
          el("button", { type: "button", class: "bouton bouton--petit bouton--danger", onclick: () => archiver(f) }, "Archiver"),
        ),
      ),
    ),
  );
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "Un fournisseur archivé n'est plus proposé, mais les composants et les commandes qui le citent le gardent."),
      el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireFournisseur(null, rafraichir) }, "Nouveau fournisseur"),
    ),
    table(
      [["Nom"], ["Type"], ["Pays"], ["Prix"], ["Délai", "nombre"], ["Composants", "nombre"], ["Commandes", "nombre"], [""]],
      lignes,
      "Aucun fournisseur pour l'instant.",
    ),
  );
}
