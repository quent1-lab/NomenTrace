// Écran paramètres (#/parametres) : listes de valeurs propres au projet suivi.
// Le reste des paramètres (projet, budget, blocs, fournisseurs, sauvegardes) arrive en phase 8.

import { api } from "../api.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { chargerListes, toutesLesListes } from "../valeurs.js";

const LISTES = {
  mode_appro: {
    titre: "Modes d'approvisionnement",
    aide: "Comment un composant est obtenu. Seul « Achat » entre dans le coût estimé et les commandes.",
  },
  statut_appro: { titre: "Statuts d'appro", aide: "Suivi manuel de l'approvisionnement d'un composant." },
  statut_choix: { titre: "Statuts de choix", aide: "Degré de certitude sur le choix technique." },
  criticite: { titre: "Criticités", aide: "« Bloquant » alimente l'alerte des bloquants non commandés." },
  type_mouvement: {
    titre: "Types de mouvement de stock",
    aide: "Chaque type impose une entrée ou une sortie, ou laisse le sens libre (inventaire). Les types de réception et de montage sont gérés par l'outil.",
  },
};

const SENS = [["Entree", "Entrée"], ["Sortie", "Sortie"], ["", "Libre"]];

let conteneur = null;

async function executer(action) {
  try {
    await action();
    masquerErreur();
    await chargerListes();
    rendre();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function champLibelle(liste, valeur) {
  const champ = el("input", { class: "champ", type: "text", value: valeur.libelle, "aria-label": `Libellé de ${valeur.code}` });
  const valider = () => {
    const texte = champ.value.trim();
    if (!texte || texte === valeur.libelle) {
      champ.value = valeur.libelle;
      return;
    }
    executer(() => api.patchValeurListe(liste, valeur.code, { libelle: texte }));
  };
  champ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") valider();
    if (e.key === "Escape") champ.value = valeur.libelle;
  });
  champ.addEventListener("blur", valider);
  return champ;
}

function selectSens(liste, valeur) {
  if (valeur.systeme) return el("span", { class: "texte-doux" }, SENS.find(([c]) => c === (valeur.sens ?? ""))[1]);
  const select = el("select", { class: "filtre" }, SENS.map(([code, texte]) => el("option", { value: code, selected: code === (valeur.sens ?? "") }, texte)));
  select.addEventListener("change", () => executer(() => api.patchValeurListe(liste, valeur.code, { sens: select.value || null })));
  return select;
}

function deplacer(liste, valeurs, index, decalage) {
  const voisin = valeurs[index + decalage];
  if (!voisin) return;
  const courante = valeurs[index];
  // Échange des rangs ; si deux valeurs ont le même ordre, on les sépare d'abord.
  const ordreCourant = courante.ordre === voisin.ordre ? courante.ordre + decalage : voisin.ordre;
  executer(async () => {
    await api.patchValeurListe(liste, courante.code, { ordre: ordreCourant });
    await api.patchValeurListe(liste, voisin.code, { ordre: courante.ordre });
  });
}

function ligne(liste, valeurs, index) {
  const v = valeurs[index];
  const actif = el("input", { type: "checkbox", checked: Boolean(v.actif), disabled: Boolean(v.systeme), "aria-label": `${v.libelle} active` });
  actif.addEventListener("change", () => executer(() => api.patchValeurListe(liste, v.code, { actif: actif.checked ? 1 : 0 })));
  const supprimer = v.systeme
    ? el("span", { class: "etiquette", title: "Valeur utilisée par les calculs : ni supprimable ni désactivable" }, "système")
    : el("button", {
        type: "button",
        class: "bouton-icone",
        title: "Supprimer (seulement si la valeur n'est utilisée nulle part)",
        onclick: () => {
          if (confirm(`Supprimer « ${v.libelle} » ?`)) executer(() => api.deleteValeurListe(liste, v.code));
        },
      }, "×");
  return el(
    "tr",
    { class: v.actif ? "" : "ligne--inactive" },
    el("td", { class: "ordre" },
      el("button", { type: "button", class: "bouton-icone", title: "Monter", disabled: index === 0, onclick: () => deplacer(liste, valeurs, index, -1) }, "↑"),
      el("button", { type: "button", class: "bouton-icone", title: "Descendre", disabled: index === valeurs.length - 1, onclick: () => deplacer(liste, valeurs, index, 1) }, "↓"),
    ),
    el("td", {}, champLibelle(liste, v)),
    el("td", { class: "code texte-doux" }, v.code),
    liste === "type_mouvement" ? el("td", {}, selectSens(liste, v)) : null,
    el("td", {}, el("label", { class: "filtre-case" }, actif, "active")),
    el("td", { class: "nombre" }, supprimer),
  );
}

function formulaireAjout(liste) {
  const libelle = el("input", { class: "champ", type: "text", placeholder: "Nouvelle valeur…", maxlength: "60" });
  const sens = liste === "type_mouvement" ? el("select", { class: "filtre" }, SENS.map(([code, texte]) => el("option", { value: code }, texte))) : null;
  const formulaire = el("form", { class: "formulaire-ligne" }, libelle, sens, el("button", { type: "submit", class: "bouton" }, "Ajouter"));
  formulaire.addEventListener("submit", (e) => {
    e.preventDefault();
    const texte = libelle.value.trim();
    if (!texte) return afficherErreur("Saisir le libellé de la nouvelle valeur.");
    const corps = { libelle: texte };
    if (sens) corps.sens = sens.value || null;
    executer(() => api.createValeurListe(liste, corps));
  });
  return formulaire;
}

function sectionListe(liste, valeurs) {
  const { titre, aide } = LISTES[liste];
  const entetes = ["", "Libellé affiché", "Code stocké", liste === "type_mouvement" ? "Sens" : null, "", ""].filter((t) => t !== null);
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, titre),
    el("p", { class: "texte-doux texte-petit" }, aide),
    el(
      "table",
      { class: "table table--dense table--listes" },
      el("thead", {}, el("tr", {}, entetes.map((t) => el("th", {}, t)))),
      el("tbody", {}, valeurs.map((_, i) => ligne(liste, valeurs, i))),
    ),
    formulaireAjout(liste),
  );
}

function rendre() {
  const listes = toutesLesListes();
  conteneur.replaceChildren(
    el("h1", {}, "Paramètres"),
    el(
      "p",
      { class: "texte-doux" },
      "Les listes ci-dessous portent le vocabulaire du projet suivi. Renommer une valeur ne change que son libellé affiché : " +
        "le code stocké reste, et avec lui l'historique. Une valeur utilisée se désactive au lieu de se supprimer.",
    ),
    el("div", { class: "grille-2" }, Object.keys(LISTES).map((liste) => sectionListe(liste, listes[liste] ?? []))),
    el("p", { class: "texte-doux texte-petit" }, "Nom du projet, budget, blocs, fournisseurs et sauvegardes : à venir dans cet écran."),
  );
}

export async function afficherParametres(cible) {
  conteneur = cible;
  await chargerListes();
  rendre();
}
