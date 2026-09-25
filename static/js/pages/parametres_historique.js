// Onglet « Historique » des paramètres : le journal de tout le projet, filtré et paginé.

import { api } from "../api.js";
import { formatNombre } from "../format.js";
import { formatHorodatage, libelleTable, lienEvenement, origineEvenement, texteEvenement } from "../historique.js";
import { afficherErreur, el, enregistrerFichier, masquerErreur } from "../ui.js";

const TAILLE_PAGE = 100;

function ligneJournal(j) {
  const lien = lienEvenement(j);
  return el(
    "tr",
    {},
    el("td", { class: "code" }, formatHorodatage(j.horodatage)),
    el("td", {}, libelleTable(j.table_cible)),
    el("td", {}, lien ? el("a", { href: lien[0] }, j.cle_cible) : j.cle_cible ?? ""),
    el("td", {}, texteEvenement(j)),
    el("td", { class: "texte-doux" }, origineEvenement(j)),
  );
}

export async function afficherOngletHistorique(cible) {
  const tables = await api.getTablesHistorique();
  const filtres = { table: "", origine: "", du: "", au: "", texte: "" };
  let page = 1;
  const corps = el("tbody");
  const compte = el("p", { class: "texte-doux texte-petit" });
  const precedent = el("button", { type: "button", class: "bouton bouton--petit bouton--discret" }, "← Plus récents");
  const suivant = el("button", { type: "button", class: "bouton bouton--petit bouton--discret" }, "Plus anciens →");

  const charger = async () => {
    try {
      const resultat = await api.getHistorique({ ...filtres, page, taille: TAILLE_PAGE });
      masquerErreur();
      corps.replaceChildren(...resultat.lignes.map(ligneJournal));
      if (!resultat.lignes.length) corps.append(el("tr", {}, el("td", { colspan: 5, class: "texte-doux" }, "Aucune ligne ne correspond aux filtres.")));
      const debut = resultat.total ? (page - 1) * TAILLE_PAGE + 1 : 0;
      const fin = Math.min(page * TAILLE_PAGE, resultat.total);
      compte.textContent = `${formatNombre(resultat.total)} ligne(s)${resultat.total ? `, ${debut} à ${fin} affichées` : ""}.`;
      precedent.disabled = page <= 1;
      suivant.disabled = fin >= resultat.total;
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const changer = (cle, valeur) => {
    filtres[cle] = valeur;
    page = 1;
    charger();
  };
  precedent.addEventListener("click", () => {
    page -= 1;
    charger();
  });
  suivant.addEventListener("click", () => {
    page += 1;
    charger();
  });

  let minuterie = null;
  const texte = el("input", {
    class: "filtre filtre--recherche",
    type: "search",
    placeholder: "Clé, champ ou valeur…",
    oninput: (e) => {
      clearTimeout(minuterie);
      minuterie = setTimeout(() => changer("texte", e.target.value.trim()), 300);
    },
  });
  const choixTable = el("select", { class: "filtre", "aria-label": "Élément", onchange: (e) => changer("table", e.target.value) }, el("option", { value: "" }, "Tous les éléments"), tables.map((t) => el("option", { value: t }, libelleTable(t))));
  const choixOrigine = el(
    "select",
    { class: "filtre", "aria-label": "Origine", onchange: (e) => changer("origine", e.target.value) },
    el("option", { value: "" }, "Toutes origines"),
    el("option", { value: "interface" }, "Interface"),
    el("option", { value: "import" }, "Import"),
  );
  const date = (cle, titre) => el("label", { class: "filtre-case" }, titre, el("input", { class: "filtre", type: "date", onchange: (e) => changer(cle, e.target.value) }));
  const exporter = el("button", { type: "button", class: "bouton bouton--discret" }, "Exporter la sélection (Excel)");
  exporter.addEventListener("click", async () => {
    exporter.disabled = true;
    try {
      enregistrerFichier(await api.telechargerHistorique(filtres));
      masquerErreur();
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      exporter.disabled = false;
    }
  });

  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "Toutes les modifications du projet, les plus récentes en haut : saisies dans l'interface ou appliquées par un import. Chaque clé mène à l'élément concerné."),
      exporter,
    ),
    el("div", { class: "filtres" }, texte, choixTable, choixOrigine, date("du", "Du "), date("au", "au ")),
    compte,
    el(
      "div",
      { class: "table-defilante" },
      el(
        "table",
        { class: "table table--dense table--parametres" },
        el("thead", {}, el("tr", {}, ["Date", "Élément", "Clé", "Détail", "Origine"].map((t) => el("th", {}, t)))),
        corps,
      ),
    ),
    el("div", { class: "actions" }, precedent, suivant),
  );
  await charger();
}
