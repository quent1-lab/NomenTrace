// Éléments partagés par la vue d'ensemble et le détail d'un ensemble.

import { api } from "../api.js";
import { formatEcart, formatMontant, formatNombre, formatPourcent, libelle } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, classeBloc, el, largeur, masquerErreur } from "../ui.js";
import { STATUTS_MONTAGE } from "../valeurs.js";

// Barre segmentée : part de chaque bloc dans l'ensemble. Sur le coût HT, ou sur le nombre
// de pièces quand rien n'est chiffré (composants fournis ou prix manquants).
export function barreRepartition(lignes, rangs) {
  if (!lignes.length) return el("p", { class: "texte-doux repartition__vide" }, "Aucun composant affecté.");
  const totalCout = lignes.reduce((s, r) => s + r.cout_ht, 0);
  const surCout = totalCout > 0;
  const total = surCout ? totalCout : lignes.reduce((s, r) => s + r.nb_pieces, 0);
  const segments = lignes.map((r) => {
    const segment = el("div", {
      class: `repartition__segment ${classeBloc(rangs.get(r.bloc_code) ?? 0)}`,
      title: `${r.bloc_code} : ${surCout ? formatMontant(r.cout_ht) : `${r.nb_pieces} pièce(s)`}`,
    });
    return largeur(segment, (100 * (surCout ? r.cout_ht : r.nb_pieces)) / total);
  });
  const legende = lignes.map((r) =>
    el(
      "span",
      { class: "repartition__legende-item" },
      el("span", { class: `repartition__pastille ${classeBloc(rangs.get(r.bloc_code) ?? 0)}` }),
      `${r.bloc_code} ${surCout ? formatPourcent((100 * r.cout_ht) / totalCout, 0) : `${r.nb_pieces} pc`}`,
    ),
  );
  return el(
    "div",
    { class: "repartition" },
    el("div", { class: "repartition__barre" }, segments),
    el("div", { class: "repartition__legende" }, legende, el("span", { class: "texte-doux" }, surCout ? "(sur le coût HT)" : "(sur les pièces, rien n'est chiffré)")),
  );
}

export function barreProgression(libelleTexte, valeur, total, vide) {
  const pourcent = total > 0 ? (100 * valeur) / total : 0;
  return el(
    "div",
    { class: "progression" },
    el(
      "div",
      { class: "carte__avancement-libelle" },
      el("span", {}, libelleTexte),
      el("span", {}, total > 0 ? `${formatNombre(valeur)} / ${formatNombre(total)}` : vide),
    ),
    el("div", { class: "barre" }, largeur(el("div", { class: "barre__remplissage" }), pourcent)),
  );
}

export function texteCout(ensemble) {
  const partiel = ensemble.nb_lignes_non_chiffrees > 0;
  return [
    formatMontant(ensemble.cout_ht),
    partiel ? el("span", { class: "a-chiffrer", title: `${ensemble.nb_lignes_non_chiffrees} composant(s) à acheter sans prix` }, " (partiel)") : null,
  ];
}

// Sélecteur du statut de montage, enregistré dès qu'il change.
export function selectStatutMontage(ensemble, surChangement) {
  const select = el("select", { class: "filtre", "aria-label": "Statut de montage" });
  for (const statut of STATUTS_MONTAGE) {
    select.append(el("option", { value: statut, selected: statut === ensemble.statut_montage }, libelle(statut)));
  }
  select.addEventListener("click", (e) => e.stopPropagation());
  select.addEventListener("change", async () => {
    select.disabled = true;
    try {
      await api.patchEnsemble(ensemble.code, { statut_montage: select.value });
      masquerErreur();
      await surChangement();
    } catch (erreur) {
      select.value = ensemble.statut_montage;
      select.disabled = false;
      afficherErreur(erreur);
    }
  });
  return select;
}

// --- Budget d'ensemble -------------------------------------------------------------------------

const SVG = "http://www.w3.org/2000/svg";
// Tracé du cadenas (grille 24 × 24), partagé avec le schéma.
export const TRACE_CADENAS = ["M7 11V8a5 5 0 0 1 10 0v3", "M5 11h14v10H5z"];

// Cadenas d'un budget verrouillé, à la place d'une étiquette.
export function cadenas(titre = "Budget verrouillé : il garde le montant saisi") {
  const icone = document.createElementNS(SVG, "svg");
  icone.setAttribute("class", "icone icone--cadenas");
  icone.setAttribute("viewBox", "0 0 24 24");
  icone.setAttribute("role", "img");
  icone.setAttribute("aria-label", titre);
  const infobulle = document.createElementNS(SVG, "title");
  infobulle.textContent = titre;
  icone.append(infobulle);
  for (const d of TRACE_CADENAS) {
    const trace = document.createElementNS(SVG, "path");
    trace.setAttribute("d", d);
    icone.append(trace);
  }
  return icone;
}

// Budget calculé (ou verrouillé) d'un ensemble, avec la mention du verrou.
export function texteBudget(ensemble) {
  if (ensemble.budget_ht === null || ensemble.budget_ht === undefined) {
    return el("span", { class: "texte-doux", title: "Aucun budget projet défini dans les paramètres" }, "non défini");
  }
  return [
    formatMontant(ensemble.budget_ht),
    ensemble.budget_verrouille ? cadenas() : null,
  ];
}

// Écart entre le coût estimé cumulé et le budget : positif = dépassement.
export function texteEcartBudget(ecart) {
  if (ecart === null || ecart === undefined) return "";
  return el("span", { class: ecart > 0 ? "texte-alerte" : "texte-conforme" }, formatEcart(ecart));
}

// Alerte portée par un parent dont les sous-ensembles verrouillés dépassent le budget.
export function alerteDepassement(depassement, classe = "") {
  if (!depassement) return null;
  return el(
    "p",
    { class: `texte-alerte texte-petit ${classe}` },
    `Sous-ensembles verrouillés et composants propres dépassent ce budget de ${formatMontant(depassement)} : les autres sous-ensembles reçoivent 0.`,
  );
}

// --- Formulaire -------------------------------------------------------------------------------

const DESCRIPTION = { nom: "texte", ordre: "entier", description: "texte", responsable: "texte", parent_code: "choix", budget_cible_ht: "montant" };
const LIBELLES = { ordre: "Ordre d'affichage", budget_cible_ht: "Budget cible HT" };

// L'ensemble et ses descendants : aucun d'eux ne peut devenir son parent.
function exclus(ensembles, code) {
  const resultat = new Set([code]);
  let ajout = true;
  while (ajout) {
    ajout = false;
    for (const e of ensembles) {
      if (!resultat.has(e.code) && resultat.has(e.parent_code)) {
        resultat.add(e.code);
        ajout = true;
      }
    }
  }
  return resultat;
}

function choixParent(ensembles, ensemble, parentInitial) {
  const interdits = ensemble ? exclus(ensembles, ensemble.code) : new Set();
  const options = ensembles
    .filter((e) => !interdits.has(e.code))
    .map((e) => [e.code, `${"\u2003".repeat(e.niveau - 1)}${e.nom} (${e.code})`]);
  return champChoix("parent_code", options, ensemble ? ensemble.parent_code : parentInitial, { vide: "— Aucun : premier niveau, sous le projet" });
}

/** Panneau de création (ensemble absent) ou de modification d'un ensemble. */
export async function ouvrirFormulaireEnsemble({ ensemble = null, ordreSuggere = 1, parentInitial = null, surEnregistre }) {
  const creation = ensemble === null;
  const ensembles = await api.getEnsembles();
  const code = champTexte("code", ensemble?.code ?? "", { disabled: !creation, maxlength: "20", autocomplete: "off" });
  code.addEventListener("input", () => {
    code.value = code.value.toUpperCase().replace(/[^A-Z0-9-]/g, "");
  });
  const budget = champNombre("budget_cible_ht", ensemble?.budget_cible_ht ?? null, 2);
  const verrou = el("input", { type: "checkbox", name: "budget_verrouille", checked: Boolean(ensemble?.budget_verrouille) });
  // Verrouiller sans montant saisi : on part du budget calculé actuel.
  verrou.addEventListener("change", () => {
    if (verrou.checked && !budget.value.trim() && ensemble?.budget_ht != null) budget.value = formatNombre(ensemble.budget_ht, 2);
  });
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Code", code, { requis: true, aide: creation ? "Majuscules, chiffres et tirets, sans espace. Il ne pourra plus être modifié." : "Le code d'un ensemble n'est pas modifiable." }),
    ligneChamp("Nom", champTexte("nom", ensemble?.nom ?? ""), { requis: true }),
    ligneChamp("Ensemble parent", choixParent(ensembles, ensemble, parentInitial), { aide: "Un ensemble a au plus un parent. Sans parent, il se range directement sous le projet." }),
    ligneChamp("Ordre d'affichage", champNombre("ordre", ensemble?.ordre ?? ordreSuggere), { aide: "Ordre parmi les ensembles de même parent." }),
    ligneChamp("Responsable", champTexte("responsable", ensemble?.responsable ?? "")),
    ligneChamp("Description", champZone("description", ensemble?.description ?? "")),
    ligneChamp("Budget cible HT", budget, { aide: "Pris en compte seulement si le budget est verrouillé. Sinon, le budget est calculé : une part égale de ce qui reste du budget du parent, après ses ensembles verrouillés et ses composants propres." }),
    el("label", { class: "filtre-case" }, verrou, "Verrouiller le budget sur ce montant"),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, creation ? "Créer l'ensemble" : "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, LIBELLES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    if (creation && !code.value) return afficherErreur("Le code de l'ensemble est obligatoire.");
    if (!lu.valeurs.nom) return afficherErreur("Le nom de l'ensemble est obligatoire.");
    if (verrou.checked && lu.valeurs.budget_cible_ht === null) return afficherErreur("Saisir un budget cible HT avant de verrouiller le budget.");
    const valeurs = { ...lu.valeurs, ordre: lu.valeurs.ordre ?? 0, budget_verrouille: verrou.checked };
    try {
      const resultat = creation
        ? await api.createEnsemble({ code: code.value, ...valeurs })
        : await api.patchEnsemble(ensemble.code, valeurs);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surEnregistre(resultat);
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau(creation ? "Nouvel ensemble" : `Modifier l'ensemble ${ensemble.code}`, formulaire);
  (creation ? code : formulaire.elements.namedItem("nom")).focus();
}
