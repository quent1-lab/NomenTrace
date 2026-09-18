// Éléments partagés par la vue d'ensemble et le détail d'un ensemble.

import { api } from "../api.js";
import { formatMontant, formatNombre, formatPourcent, libelle } from "../format.js";
import { champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
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

const DESCRIPTION = { nom: "texte", ordre: "entier", description: "texte", responsable: "texte" };

/** Panneau de création (ensemble absent) ou de modification d'un ensemble. */
export function ouvrirFormulaireEnsemble({ ensemble = null, ordreSuggere = 1, surEnregistre }) {
  const creation = ensemble === null;
  const code = champTexte("code", ensemble?.code ?? "", { disabled: !creation, maxlength: "20", autocomplete: "off" });
  code.addEventListener("input", () => {
    code.value = code.value.toUpperCase().replace(/[^A-Z0-9-]/g, "");
  });
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Code", code, { requis: true, aide: creation ? "Majuscules, chiffres et tirets, sans espace. Il ne pourra plus être modifié." : "Le code d'un ensemble n'est pas modifiable." }),
    ligneChamp("Nom", champTexte("nom", ensemble?.nom ?? ""), { requis: true }),
    ligneChamp("Ordre d'affichage", champNombre("ordre", ensemble?.ordre ?? ordreSuggere)),
    ligneChamp("Responsable", champTexte("responsable", ensemble?.responsable ?? "")),
    ligneChamp("Description", champZone("description", ensemble?.description ?? "")),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, creation ? "Créer l'ensemble" : "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, { ordre: "Ordre d'affichage" });
    if (lu.erreur) return afficherErreur(lu.erreur);
    if (creation && !code.value) return afficherErreur("Le code de l'ensemble est obligatoire.");
    if (!lu.valeurs.nom) return afficherErreur("Le nom de l'ensemble est obligatoire.");
    const valeurs = { ...lu.valeurs, ordre: lu.valeurs.ordre ?? 0 };
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
