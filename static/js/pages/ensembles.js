// Vue d'ensemble (#/ensembles) : une carte par ensemble physique et l'encadré de cohérence.

import { api } from "../api.js";
import { formatNombre } from "../format.js";
import { lienRoute, naviguer } from "../router.js";
import { el, rangsBlocs } from "../ui.js";
import {
  barreProgression,
  barreRepartition,
  ouvrirFormulaireEnsemble,
  selectStatutMontage,
  texteCout,
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

function carte(ensemble, repartition, rangs, rafraichir) {
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
    el(
      "dl",
      { class: "carte__chiffres" },
      el("dt", {}, "Composants distincts"),
      el("dd", {}, formatNombre(ensemble.nb_composants_distincts)),
      el("dt", {}, "Pièces"),
      el("dd", {}, formatNombre(ensemble.nb_pieces_total)),
      el("dt", {}, "Coût HT"),
      el("dd", { class: "fort" }, texteCout(ensemble)),
    ),
    barreRepartition(repartition, rangs),
    barreProgression("Appro : composants reçus", ensemble.nb_composants_recus, ensemble.nb_composants_a_acheter, "rien à acheter"),
    barreProgression("Montage : pièces montées", ensemble.nb_pieces_montees, ensemble.nb_pieces_total, "aucune pièce"),
    el("footer", { class: "carte__pied carte__pied--espace" }, el("span", { class: "texte-doux" }, "Statut de montage"), selectStatutMontage(ensemble, rafraichir)),
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
      "Un ensemble est une partie physique du robot : la nacelle, le mât, le coffret électrique, " +
        "le bumper, le poste opérateur… Il dit où un composant est monté, et en quelle quantité.",
    ),
    el(
      "p",
      {},
      "Il ne remplace pas le bloc fonctionnel : un composant appartient à un seul bloc, figé dans " +
        "son identifiant, mais il peut être monté dans plusieurs ensembles. Un transceiver CAN du " +
        "bloc Transverse peut ainsi se retrouver dans quatre ensembles différents.",
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

export async function afficherEnsembles(conteneur) {
  const rafraichir = () => afficherEnsembles(conteneur);
  const [ensembles, repartition, blocs, incoherences] = await Promise.all([
    api.getEnsembles(),
    api.getRepartition(),
    api.getBlocs(),
    api.getIncoherences(),
  ]);
  const rangs = rangsBlocs(blocs);
  const ordreSuggere = ensembles.reduce((max, e) => Math.max(max, e.ordre), 0) + 1;
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
  conteneur.replaceChildren(
    entete,
    el("p", { class: "texte-doux" }, "Un ensemble est une partie physique du robot. Cliquer sur une carte pour voir ce qu'elle contient et ce qu'il reste à monter."),
    el(
      "div",
      { class: "grille-cartes" },
      ensembles.map((e) => carte(e, repartition.filter((r) => r.ensemble_code === e.code), rangs, rafraichir)),
    ),
    encadreCoherence(incoherences),
  );
}
