// Vue par bloc fonctionnel (#/blocs) : une carte par bloc, budget cible modifiable sur place.

import { api } from "../api.js";
import { formatEcart, formatMontant, formatNombre, formatPourcent, lireNombre } from "../format.js";
import { naviguer } from "../router.js";
import { ecritBloc, estAdmin } from "../session.js";
import { afficherErreur, classeBloc, el, largeur, masquerErreur, rangsBlocs } from "../ui.js";

function etatEcart(bloc) {
  if (bloc.budget_cible_ht === null) return "neutre";
  if (bloc.ecart_budget > 0.005) return "alerte";
  return bloc.ecart_budget > -0.1 * bloc.budget_cible_ht ? "surveiller" : "conforme";
}

function texteEcart(bloc) {
  if (bloc.budget_cible_ht === null) return "budget non défini";
  return `${formatEcart(bloc.ecart_budget)} (${formatPourcent(bloc.ecart_pct)})`;
}

// Champ de budget : envoi au flou ou à Entrée, Échap annule, ancienne valeur rétablie en cas d'échec.
function champBudget(bloc, rafraichir) {
  const initial = bloc.budget_cible_ht === null ? "" : formatNombre(bloc.budget_cible_ht, 2);
  // Les budgets se saisissent par l'administrateur seulement.
  if (!estAdmin()) return initial ? formatMontant(bloc.budget_cible_ht) : el("span", { class: "texte-doux" }, "non défini");
  const champ = el("input", {
    class: "champ-montant",
    type: "text",
    inputmode: "decimal",
    value: initial,
    placeholder: "non défini",
    "aria-label": `Budget cible du bloc ${bloc.nom}`,
  });
  let annule = false;
  champ.addEventListener("click", (e) => e.stopPropagation());
  champ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") champ.blur();
    if (e.key === "Escape") {
      annule = true;
      champ.value = initial;
      champ.blur();
    }
  });
  champ.addEventListener("blur", async () => {
    if (annule || champ.value === initial) {
      annule = false;
      return;
    }
    const valeur = lireNombre(champ.value);
    if (Number.isNaN(valeur) || (valeur !== null && valeur < 0)) {
      afficherErreur(`Budget illisible : « ${champ.value} ». Saisir un montant positif, par exemple 450,00.`);
      champ.value = initial;
      return;
    }
    champ.disabled = true;
    try {
      await api.patchBloc(bloc.code, { budget_cible_ht: valeur });
      masquerErreur();
      await rafraichir();
    } catch (erreur) {
      champ.value = initial;
      champ.disabled = false;
      afficherErreur(erreur);
    }
  });
  return champ;
}

function carte(bloc, rang, rafraichir) {
  const barre = largeur(el("div", { class: "barre__remplissage" }), bloc.avancement_pct ?? 0);
  const ajouter = el(
    "button",
    { type: "button", class: "bouton bouton--discret", title: `Créer un composant dans le bloc ${bloc.code}`, hidden: !ecritBloc(bloc.code) },
    "+ Ajouter un composant",
  );
  ajouter.addEventListener("click", (e) => {
    e.stopPropagation();
    naviguer("/composants", { bloc: bloc.code, nouveau: 1 });
  });
  return el(
    "article",
    {
      class: `carte carte--cliquable ${classeBloc(rang)}`,
      tabindex: "0",
      onclick: () => naviguer("/composants", { bloc: bloc.code }),
      onkeydown: (e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) naviguer("/composants", { bloc: bloc.code });
      },
    },
    el("header", { class: "carte__entete" }, el("h2", {}, bloc.nom), el("span", { class: "etiquette" }, bloc.code)),
    el(
      "dl",
      { class: "carte__chiffres" },
      el("dt", {}, "Composants"),
      el("dd", {}, formatNombre(bloc.nb_composants)),
      el("dt", {}, "Coût HT"),
      el("dd", { class: "fort" }, formatMontant(bloc.cout_ht)),
      el("dt", {}, "Budget cible HT"),
      el("dd", {}, champBudget(bloc, rafraichir)),
      el("dt", {}, "Écart"),
      el("dd", { class: `ecart ecart--${etatEcart(bloc)}` }, texteEcart(bloc)),
      el("dt", {}, "À chiffrer"),
      el("dd", { class: bloc.nb_a_chiffrer > 0 ? "texte-surveiller" : "" }, formatNombre(bloc.nb_a_chiffrer)),
    ),
    el(
      "div",
      { class: "carte__avancement" },
      el(
        "div",
        { class: "carte__avancement-libelle" },
        el("span", {}, "Achats reçus"),
        el("span", {}, bloc.avancement_pct === null ? "rien à acheter" : formatPourcent(bloc.avancement_pct, 0)),
      ),
      el("div", { class: "barre" }, barre),
    ),
    el("footer", { class: "carte__pied" }, ajouter),
  );
}

export async function afficherBlocs(conteneur) {
  const rafraichir = () => afficherBlocs(conteneur);
  const blocs = await api.getBlocs();
  const rangs = rangsBlocs(blocs);
  conteneur.replaceChildren(
    el("h1", {}, "Blocs fonctionnels"),
    el(
      "p",
      { class: "texte-doux" },
      "Un bloc est un découpage fonctionnel : chaque composant appartient à un seul bloc, " +
        "figé dans son identifiant. Cliquer sur une carte pour voir ses composants.",
    ),
    el("div", { class: "grille-cartes" }, blocs.map((b) => carte(b, rangs.get(b.code), rafraichir))),
  );
}
