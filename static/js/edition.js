// Édition en ligne d'une cellule : clic, saisie, envoi au flou ou à Entrée, Échap annule.
// Pendant l'envoi la cellule est grisée ; en cas d'échec l'ancienne valeur revient et
// l'erreur s'affiche dans le bandeau.

import { formatNombre, libelle, lireNombre } from "./format.js";
import { afficherErreur, el, masquerErreur } from "./ui.js";

function lireEntier(texte) {
  const valeur = lireNombre(texte);
  if (valeur === null) return { erreur: "Une quantité est obligatoire." };
  if (Number.isNaN(valeur) || !Number.isInteger(valeur) || valeur < 0) {
    return { erreur: `Quantité invalide : « ${texte} ». Saisir un entier positif ou nul.` };
  }
  return { valeur };
}

function lirePrix(texte) {
  const valeur = lireNombre(texte);
  if (Number.isNaN(valeur) || (valeur !== null && valeur < 0)) {
    return { erreur: `Prix illisible : « ${texte} ». Saisir un montant, par exemple 12,50.` };
  }
  return { valeur };
}

function selectOptions(options, valeur, avecVide) {
  const select = el("select", { class: "champ-cellule" });
  if (avecVide) select.append(el("option", { value: "" }, "—"));
  for (const option of options) {
    const [code, texte] = Array.isArray(option) ? option : [option, libelle(option)];
    select.append(el("option", { value: code, selected: code === valeur }, texte));
  }
  if (!avecVide && valeur === null) select.value = "";
  return select;
}

// Construit l'éditeur et renvoie { racine, focus, lire } ; lire() renvoie { modifs } ou { erreur }.
function construireEditeur(definition, composant) {
  const champ = definition.champ;
  if (definition.type === "entier") {
    const input = el("input", { class: "champ-cellule champ-cellule--nombre", type: "text", inputmode: "numeric", value: formatNombre(composant[champ]) });
    return {
      racine: input,
      focus: input,
      lire: () => {
        const r = lireEntier(input.value);
        return r.erreur ? r : { modifs: { [champ]: r.valeur } };
      },
    };
  }
  if (definition.type === "montant") {
    const input = el("input", {
      class: "champ-cellule champ-cellule--nombre",
      type: "text",
      inputmode: "decimal",
      value: composant[champ] === null ? "" : formatNombre(composant[champ], 2),
    });
    return {
      racine: input,
      focus: input,
      lire: () => {
        const r = lirePrix(input.value);
        return r.erreur ? r : { modifs: { [champ]: r.valeur } };
      },
    };
  }
  if (definition.type === "prix") {
    const input = el("input", {
      class: "champ-cellule champ-cellule--nombre",
      type: "text",
      inputmode: "decimal",
      value: composant.pu_releve === null ? "" : formatNombre(composant.pu_releve, 2),
    });
    const base = selectOptions(["HT", "TTC"], composant.base_prix_releve, false);
    return {
      racine: el("span", { class: "editeur-prix" }, input, base),
      focus: input,
      lire: () => {
        const r = lirePrix(input.value);
        return r.erreur ? r : { modifs: { pu_releve: r.valeur, base_prix_releve: base.value } };
      },
    };
  }
  const select = selectOptions(definition.options(), composant[champ], definition.vide);
  return {
    racine: select,
    focus: select,
    lire: () => ({ modifs: { [champ]: select.value === "" ? null : select.value } }),
  };
}

function modifsUtiles(modifs, composant) {
  return Object.fromEntries(Object.entries(modifs).filter(([cle, v]) => v !== composant[cle]));
}

/**
 * Ouvre l'éditeur dans la cellule `td`.
 * enregistrer(modifs) doit renvoyer une promesse ; terminer() est appelé à la fin, réussite ou non.
 */
export function editerCellule(td, definition, composant, { enregistrer, terminer }) {
  if (td.classList.contains("cellule--edition")) return;
  const contenuInitial = [...td.childNodes];
  const editeur = construireEditeur(definition, composant);
  let fini = false;

  const restaurer = () => {
    td.classList.remove("cellule--edition", "cellule--envoi");
    td.replaceChildren(...contenuInitial);
  };

  const conclure = async (valider) => {
    if (fini) return;
    fini = true;
    if (!valider) {
      restaurer();
      terminer(false);
      return;
    }
    const lu = editeur.lire();
    if (lu.erreur) {
      afficherErreur(lu.erreur);
      restaurer();
      terminer(false);
      return;
    }
    const modifs = modifsUtiles(lu.modifs, composant);
    if (Object.keys(modifs).length === 0) {
      restaurer();
      terminer(false);
      return;
    }
    td.classList.add("cellule--envoi");
    td.querySelectorAll("input, select").forEach((c) => (c.disabled = true));
    try {
      await enregistrer(modifs);
      masquerErreur();
      td.classList.remove("cellule--edition", "cellule--envoi");
      terminer(true);
    } catch (erreur) {
      afficherErreur(erreur);
      restaurer();
      terminer(false);
    }
  };

  td.classList.add("cellule--edition");
  td.replaceChildren(editeur.racine);
  editeur.racine.addEventListener("click", (e) => e.stopPropagation());
  editeur.racine.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      conclure(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      conclure(false);
    }
  });
  // Le flou ne valide que si le focus quitte l'éditeur entier (prix : champ + base).
  editeur.racine.addEventListener("focusout", (e) => {
    if (!editeur.racine.contains(e.relatedTarget)) conclure(true);
  });
  if (definition.type !== "prix" && editeur.racine.tagName === "SELECT") {
    editeur.racine.addEventListener("change", () => conclure(true));
  }
  editeur.focus.focus();
  if (editeur.focus.select) editeur.focus.select();
}
