// Vue d'ensemble (#/ensembles) : une carte par ensemble physique et l'encadré de cohérence.

import { api } from "../api.js";
import { editerCellule } from "../edition.js";
import { formatMontant, formatNombre, formatPourcent } from "../format.js";
import { lienRoute, naviguer, remplacerRoute } from "../router.js";
import { vueSchema } from "./ensembles_schema.js";
import { el, rangsBlocs } from "../ui.js";
import {
  alerteDepassement,
  barreProgression,
  barreRepartition,
  ouvrirFormulaireEnsemble,
  selectStatutMontage,
  texteBudget,
  texteCout,
  texteEcartBudget,
} from "./ensembles_commun.js";

const TYPES_INCOHERENCE = {
  sur_affecte: {
    titre: "Affectés au-delà du besoin",
    texte: (i) => `${i.valeur} pièce(s) affectée(s) pour un besoin de ${i.reference}`,
  },
  affecte_non_commande: {
    titre: "Affectés mais pas encore commandés",
    texte: (i) => `${i.reference} à acheter, rien de commandé`,
  },
  monte_plus_qu_affecte: {
    titre: "Montés au-delà de leur affectation",
    texte: (i) => `${i.valeur} monté(s) dans ${i.ensemble_code} pour ${i.reference} affecté(s)`,
  },
  monte_sans_affectation: {
    titre: "Montés dans un ensemble sans y être affectés",
    texte: (i) => `${i.valeur} monté(s) dans ${i.ensemble_code}`,
  },
};

// Chiffre d'une carte : cumulé pour un parent, avec la part propre en second.
function chiffre(ensemble, cle) {
  if (!ensemble.nb_sous_ensembles) return formatNombre(ensemble[cle]);
  return [formatNombre(ensemble.cumul[cle]), el("span", { class: "carte__propre" }, `dont propre ${formatNombre(ensemble[cle])}`)];
}

function carte(ensemble, repartition, rangs, rafraichir, noms) {
  const parent = ensemble.nb_sous_ensembles > 0;
  const mentions = [
    ensemble.parent_code ? `Sous-ensemble de ${noms.get(ensemble.parent_code) ?? ensemble.parent_code}` : null,
    parent ? `chiffres cumulés avec ${ensemble.nb_sous_ensembles} sous-ensemble(s)` : null,
  ].filter(Boolean);
  const mention = mentions.join(" · ");
  const chiffres = parent ? ensemble.cumul : ensemble;
  return el(
    "article",
    {
      class: "carte carte--cliquable carte--ensemble",
      tabindex: "0",
      onclick: () => naviguer(`/ensembles/${ensemble.code}`),
      onkeydown: (e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) naviguer(`/ensembles/${ensemble.code}`);
      },
    },
    el("header", { class: "carte__entete" }, el("h2", {}, ensemble.nom), el("span", { class: "etiquette" }, ensemble.code)),
    mention ? el("p", { class: "texte-doux texte-petit carte__mention" }, mention.charAt(0).toUpperCase() + mention.slice(1)) : null,
    el(
      "dl",
      { class: "carte__chiffres" },
      el("dt", {}, "Composants distincts"),
      el("dd", {}, chiffre(ensemble, "nb_composants_distincts")),
      el("dt", {}, "Pièces"),
      el("dd", {}, chiffre(ensemble, "nb_pieces_total")),
      el("dt", {}, "Coût HT"),
      el("dd", { class: "fort" }, texteCout(chiffres), parent ? el("span", { class: "carte__propre" }, `dont propre ${formatMontant(ensemble.cout_ht)}`) : null),
      el("dt", {}, "Budget HT"),
      el("dd", {}, texteBudget(ensemble)),
      ensemble.ecart_budget_ht !== null ? [el("dt", {}, "Écart au budget"), el("dd", {}, texteEcartBudget(ensemble.ecart_budget_ht))] : null,
    ),
    alerteDepassement(ensemble.depassement_verrouille_ht),
    barreRepartition(repartition, rangs),
    barreProgression("Appro : composants reçus", chiffres.nb_composants_recus, chiffres.nb_composants_a_acheter, "rien à acheter"),
    barreProgression("Montage : pièces montées", chiffres.nb_pieces_montees, chiffres.nb_pieces_total, "aucune pièce"),
    el("footer", { class: "carte__pied carte__pied--espace" }, el("span", { class: "texte-doux" }, "Statut de montage"), selectStatutMontage(ensemble, rafraichir)),
  );
}

// --- Vue « Arbre » ----------------------------------------------------------------------------

function celluleNom(texte, code, niveau) {
  return el(
    "td",
    { class: `arbre__nom arbre__nom--${Math.min(niveau, 6)}` },
    niveau > 0 ? el("span", { class: "arbre__trait", "aria-hidden": "true" }, "└ ") : null,
    texte,
    code ? el("span", { class: "etiquette etiquette--espace" }, code) : null,
  );
}

const EDITION_BUDGET = { champ: "budget_cible_ht", type: "montant" };

// Cellule éditable du budget cible. Saisir un montant verrouille l'ensemble dessus ;
// vider la case le déverrouille.
function celluleBudgetCible(valeur, enregistrer, rafraichir, contenu) {
  const td = el("td", { class: "nombre editable", title: "Cliquer pour saisir le budget cible" }, contenu);
  td.addEventListener("click", (ev) => {
    ev.stopPropagation();
    editerCellule(td, EDITION_BUDGET, { budget_cible_ht: valeur }, {
      enregistrer: (modifs) => enregistrer(modifs.budget_cible_ht),
      terminer: (reussi) => reussi && rafraichir(),
    });
  });
  td.addEventListener("keydown", (ev) => ev.stopPropagation());
  return td;
}

function budgetCibleEnsemble(e, rafraichir) {
  const valeur = e.budget_verrouille ? e.budget_cible_ht : null;
  const enregistrer = (montant) =>
    api.patchEnsemble(e.code, montant === null ? { budget_verrouille: false, budget_cible_ht: null } : { budget_cible_ht: montant, budget_verrouille: true });
  const contenu = valeur === null ? el("span", { class: "texte-doux" }, "calculé") : [formatMontant(valeur), el("span", { class: "etiquette etiquette--espace" }, "verrouillé")];
  return celluleBudgetCible(valeur, enregistrer, rafraichir, contenu);
}

function ligneArbre(e, rafraichir) {
  const c = e.cumul;
  const appro = c.nb_composants_a_acheter > 0 ? `${formatNombre(c.nb_composants_recus)} / ${formatNombre(c.nb_composants_a_acheter)}` : "—";
  const nom = celluleNom(e.nom, e.code, e.niveau);
  const alerte = alerteDepassement(e.depassement_verrouille_ht, "arbre__alerte");
  if (alerte) nom.append(alerte);
  const ouvrir = () => naviguer(`/ensembles/${e.code}`);
  return el(
    "tr",
    { class: "ligne-cliquable", tabindex: "0", onclick: ouvrir, onkeydown: (ev) => ev.key === "Enter" && ouvrir() },
    nom,
    el("td", { class: "nombre" }, texteCout(c)),
    el("td", { class: "nombre" }, e.nb_sous_ensembles ? formatMontant(e.cout_ht) : ""),
    budgetCibleEnsemble(e, rafraichir),
    el("td", { class: "nombre" }, e.budget_ht === null ? el("span", { class: "texte-doux" }, "non défini") : formatMontant(e.budget_ht)),
    el("td", { class: "nombre" }, texteEcartBudget(e.ecart_budget_ht)),
    el("td", { class: "nombre" }, appro),
    el("td", { class: "nombre" }, c.avancement_montage_pct === null ? "—" : formatPourcent(c.avancement_montage_pct, 0)),
  );
}

function ligneRacine(racine) {
  const nom = celluleNom(racine.nom || "Projet", null, 0);
  nom.append(el("span", { class: "texte-doux texte-petit" }, " (projet)"));
  const alerte = alerteDepassement(racine.depassement_verrouille_ht, "arbre__alerte");
  if (alerte) nom.append(alerte);
  if (racine.budget_non_reparti_ht > 0.005 && racine.nb_ensembles) {
    nom.append(el("p", { class: "texte-surveiller texte-petit arbre__alerte" }, `${formatMontant(racine.budget_non_reparti_ht)} de budget non réparti : tous les ensembles de premier niveau sont verrouillés.`));
  }
  return el(
    "tr",
    { class: "arbre__racine" },
    nom,
    el("td", { class: "nombre" }, formatMontant(racine.cout_ht)),
    el("td"),
    el("td", { class: "nombre texte-doux texte-petit", title: "Le budget du projet se modifie dans Paramètres › Projet" }, "Paramètres"),
    el("td", { class: "nombre" }, racine.budget_ht === null ? el("span", { class: "texte-doux" }, "non défini") : formatMontant(racine.budget_ht)),
    el("td", { class: "nombre" }, texteEcartBudget(racine.ecart_budget_ht)),
    el("td"),
    el("td"),
  );
}

function vueArbre(arbre, rafraichir) {
  const entetes = [["Ensemble"], ["Coût HT cumulé", "nombre"], ["dont propre", "nombre"], ["Budget cible HT", "nombre"], ["Budget HT", "nombre"], ["Écart", "nombre"], ["Appro reçus", "nombre"], ["Montage", "nombre"]];
  return el(
    "section",
    { class: "panneau" },
    el(
      "p",
      { class: "texte-doux texte-petit" },
      "Le budget du projet descend l'arbre : à chaque niveau, les ensembles verrouillés gardent leur montant, le reste est partagé à parts égales entre les autres, même vides, pour voir ce qu'il reste à chacun ; les composants affectés directement au parent comptent pour une part. " +
        "Ces budgets d'ensemble sont un axe parallèle aux budgets de bloc : les deux découpent le même budget total, l'un par partie physique, l'autre par fonction.",
    ),
    el(
      "p",
      { class: "texte-doux texte-petit" },
      "Cliquer sur un budget cible pour le saisir : l'ensemble est alors verrouillé sur ce montant. Vider la case le déverrouille, son budget redevient calculé. Le budget du projet se modifie dans Paramètres.",
    ),
    el(
      "div",
      { class: "table-defilante" },
      el(
        "table",
        { class: "table table--dense table--arbre" },
        el("thead", {}, el("tr", {}, entetes.map(([t, c]) => el("th", { class: c ?? "" }, t)))),
        el("tbody", {}, ligneRacine(arbre.racine), arbre.ensembles.map((e) => ligneArbre(e, rafraichir))),
      ),
    ),
  );
}

function barreVues(courante, conteneur) {
  const vues = [["cartes", "Cartes"], ["arbre", "Arbre"], ["schema", "Schéma"]];
  return el(
    "nav",
    { class: "onglets", role: "tablist" },
    vues.map(([code, titre]) =>
      el(
        "button",
        {
          type: "button",
          role: "tab",
          class: code === courante ? "onglet onglet--actif" : "onglet",
          "aria-selected": code === courante ? "true" : "false",
          onclick: () => {
            remplacerRoute("/ensembles", { vue: code === "cartes" ? "" : code });
            afficherEnsembles(conteneur, new URLSearchParams({ vue: code }));
          },
        },
        titre,
      ),
    ),
  );
}

function etatVide(surCreer) {
  return el(
    "section",
    { class: "panneau etat-vide" },
    el("h2", {}, "Aucun ensemble pour l'instant"),
    el(
      "p",
      {},
      "Un ensemble est une partie physique du système suivi : un sous-ensemble mécanique, un " +
        "coffret, un poste de commande… Il dit où un composant est monté, et en quelle quantité.",
    ),
    el(
      "p",
      {},
      "Il ne remplace pas le bloc fonctionnel : un composant appartient à un seul bloc, figé dans " +
        "son identifiant, mais il peut être monté dans plusieurs ensembles, en quantités " +
        "différentes. Un même connecteur peut ainsi se retrouver dans quatre ensembles.",
    ),
    el("button", { type: "button", class: "bouton", onclick: surCreer }, "+ Créer le premier ensemble"),
  );
}

function encadreCoherence(incoherences) {
  const contenu = [];
  for (const [type, definition] of Object.entries(TYPES_INCOHERENCE)) {
    const lignes = incoherences.filter((i) => i.type === type);
    if (!lignes.length) continue;
    contenu.push(
      el("h3", {}, `${definition.titre} (${lignes.length})`),
      el(
        "ul",
        { class: "liste-coherence" },
        lignes.map((i) =>
          el(
            "li",
            {},
            el("a", { href: lienRoute("/composants", { fiche: i.composant_id }) }, i.composant_id),
            ` ${i.designation} — ${definition.texte(i)}`,
          ),
        ),
      ),
    );
  }
  return el(
    "section",
    { class: "panneau coherence" },
    el("h2", {}, "Cohérence"),
    contenu.length ? contenu : el("p", { class: "texte-doux" }, "Aucune incohérence entre affectations, commandes et montage."),
    el("p", { class: "texte-doux texte-petit" }, "Les composants non affectés n'apparaissent pas ici : c'est un état normal tant que l'affectation n'est pas faite (filtre dédié sur l'écran Composants)."),
  );
}

export async function afficherEnsembles(conteneur, parametres) {
  const vue = ["arbre", "schema"].includes(parametres?.get("vue")) ? parametres.get("vue") : "cartes";
  const rafraichir = () => afficherEnsembles(conteneur, new URLSearchParams({ vue }));
  const [arbre, repartition, repartitionCumul, blocs, incoherences] = await Promise.all([
    api.getArbreEnsembles(),
    api.getRepartition(),
    api.getRepartition(true),
    api.getBlocs(),
    api.getIncoherences(),
  ]);
  const ensembles = arbre.ensembles;
  const rangs = rangsBlocs(blocs);
  const ordreSuggere = ensembles.filter((e) => e.niveau === 1).reduce((max, e) => Math.max(max, e.ordre), 0) + 1;
  const creer = () =>
    ouvrirFormulaireEnsemble({ ordreSuggere, surEnregistre: (e) => naviguer(`/ensembles/${e.code}`) });
  const entete = el(
    "div",
    { class: "titre-page" },
    el("h1", {}, "Ensembles"),
    ensembles.length ? el("button", { type: "button", class: "bouton", onclick: creer }, "+ Nouvel ensemble") : null,
  );
  if (!ensembles.length) {
    conteneur.replaceChildren(entete, etatVide(creer), encadreCoherence(incoherences));
    return;
  }
  // Toutes les cartes à plat, dans l'ordre de l'arbre ; un parent affiche la répartition
  // par bloc de toute sa branche.
  const noms = new Map(ensembles.map((e) => [e.code, e.nom]));
  const carteDe = (e) => {
    const source = e.nb_sous_ensembles ? repartitionCumul : repartition;
    return carte(e, source.filter((r) => r.ensemble_code === e.code), rangs, rafraichir, noms);
  };
  const corps = {
    cartes: () => el("div", { class: "grille-cartes" }, ensembles.map(carteDe)),
    arbre: () => vueArbre(arbre, rafraichir),
    schema: () => vueSchema(arbre),
  }[vue]();
  conteneur.replaceChildren(
    entete,
    el("p", { class: "texte-doux" }, "Un ensemble est une partie physique du système suivi ; il peut contenir des sous-ensembles. Cliquer sur un ensemble pour voir ce qu'il contient et ce qu'il reste à monter."),
    barreVues(vue, conteneur),
    corps,
    encadreCoherence(incoherences),
  );
}
