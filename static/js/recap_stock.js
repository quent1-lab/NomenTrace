// Panneau « Ajouté au stock » montré après une réception, sur la page d'une commande et sur
// celle d'une commande commune.

import { formatDate, formatNombre } from "./format.js";
import { lienRoute } from "./router.js";
import { el } from "./ui.js";

/** `recap` : date et entrées renvoyées par la réception. `projets` : noms des projets par
 * code, pour une commune où chaque ligne entre dans le stock de son projet. */
export function tableAjoutStock(recap, { fermer, projets = null }) {
  const sansLieu = recap.entrees.filter((e) => !e.emplacement).length;
  const titres = ["Composant", "Désignation", ...(projets ? ["Projet"] : []), "Pièces ajoutées", "Stock", "Emplacement"];
  const premierNombre = projets ? 3 : 2;
  const lien = (e) => {
    const route = lienRoute("/composants", { fiche: e.composant_id });
    return e.projet ? `/p/${encodeURIComponent(e.projet)}/${route}` : route;
  };
  return el(
    "section",
    { class: "panneau panneau--recap-stock", role: "status" },
    el("h2", {}, "Ajouté au stock"),
    el("p", { class: "texte-doux" }, `Réception du ${formatDate(recap.date)} : ${recap.entrees.length} composant(s) entré(s) en stock.`),
    el(
      "div",
      { class: "table-defilante" },
      el(
        "table",
        { class: "table table--dense" },
        el("thead", {}, el("tr", {}, titres.map((t, i) => el("th", { class: i === premierNombre || i === premierNombre + 1 ? "nombre" : "" }, t)))),
        el(
          "tbody",
          {},
          recap.entrees.map((e) =>
            el(
              "tr",
              {},
              el("td", { class: "code" }, el("a", { href: lien(e) }, e.composant_id)),
              el("td", { class: "tronque tronque--large", title: e.designation ?? "" }, e.designation ?? ""),
              projets ? el("td", {}, projets[e.projet] ?? e.projet) : null,
              el("td", { class: "nombre" }, `+${formatNombre(e.pieces)}`),
              el("td", { class: "nombre" }, e.stock_actuel === null ? "—" : formatNombre(e.stock_actuel)),
              el("td", { class: e.emplacement ? "" : "texte-surveiller" }, e.emplacement ?? "non renseigné"),
            ),
          ),
        ),
      ),
    ),
    sansLieu ? el("p", { class: "texte-surveiller texte-petit" }, `${sansLieu} composant(s) sans emplacement : la page Stock ne saura pas dire où ils sont rangés.`) : null,
    el(
      "div",
      { class: "actions-formulaire" },
      projets ? null : el("a", { class: "bouton bouton--discret", href: lienRoute("/stock") }, "Voir le stock"),
      el("button", { type: "button", class: "bouton", onclick: fermer }, "Fermer"),
    ),
  );
}
