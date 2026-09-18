// Écran achats (#/achats) : liste des commandes, filtres, création.

import { api } from "../api.js";
import { formatDate, formatMontant, libelle } from "../format.js";
import { naviguer, remplacerRoute } from "../router.js";
import { el } from "../ui.js";
import { STATUTS_COMMANDE } from "../valeurs.js";
import { badgeRetard, badgeStatut, ouvrirFormulaireCommande } from "./achats_commun.js";

let etat = null;

function lignesFiltrees() {
  const { statut, fournisseur, retard } = etat.filtres;
  return etat.commandes.filter(
    (c) =>
      (!statut || c.statut === statut) &&
      (!fournisseur || c.fournisseur_nom === fournisseur) &&
      (!retard || c.en_retard),
  );
}

function majUrl() {
  const p = {};
  for (const [cle, valeur] of Object.entries(etat.filtres)) if (valeur) p[cle] = valeur === true ? 1 : valeur;
  remplacerRoute("/achats", p);
}

function rendreTable() {
  const commandes = lignesFiltrees();
  const total = commandes.reduce((s, c) => s + c.total_ht, 0);
  etat.corps.replaceChildren(
    ...commandes.map((c) =>
      el(
        "tr",
        { class: "ligne-cliquable", onclick: () => naviguer(`/achats/${c.numero}`) },
        el("td", { class: "code" }, c.numero),
        el("td", {}, c.type),
        el("td", {}, badgeStatut(c), " ", badgeRetard(c)),
        el("td", {}, c.fournisseur_nom ?? "—"),
        el("td", { class: "nombre" }, String(c.nb_lignes)),
        el("td", { class: "nombre" }, formatMontant(c.total_ht)),
        el("td", { class: "nombre" }, formatMontant(c.total_ttc)),
        el("td", {}, formatDate(c.date_commande)),
        el("td", { class: c.en_retard ? "texte-alerte" : "" }, formatDate(c.livraison_annoncee)),
      ),
    ),
  );
  etat.pied.replaceChildren(
    el("tr", {}, el("td", { colspan: 5, class: "texte-doux" }, `${commandes.length} commande(s)`), el("td", { class: "nombre fort" }, formatMontant(total)), el("td", { colspan: 3 })),
  );
}

function filtres() {
  const changer = (cle, valeur) => {
    etat.filtres[cle] = valeur;
    majUrl();
    rendreTable();
  };
  const selectStatut = el("select", { class: "filtre", onchange: (e) => changer("statut", e.target.value) }, el("option", { value: "" }, "Tous les statuts"), STATUTS_COMMANDE.map((s) => el("option", { value: s, selected: s === etat.filtres.statut }, libelle(s))));
  const fournisseursUtilises = [...new Set(etat.commandes.map((c) => c.fournisseur_nom).filter(Boolean))].sort();
  const selectFournisseur = el("select", { class: "filtre", onchange: (e) => changer("fournisseur", e.target.value) }, el("option", { value: "" }, "Tous les fournisseurs"), fournisseursUtilises.map((f) => el("option", { value: f, selected: f === etat.filtres.fournisseur }, f)));
  const caseRetard = el("label", { class: "filtre-case" }, el("input", { type: "checkbox", checked: etat.filtres.retard, onchange: (e) => changer("retard", e.target.checked) }), "En retard uniquement");
  return el("div", { class: "filtres" }, selectStatut, selectFournisseur, caseRetard);
}

export async function afficherAchats(conteneur, parametres) {
  const [commandes, fournisseurs] = await Promise.all([api.getCommandes(), api.getFournisseurs()]);
  etat = {
    commandes,
    filtres: {
      statut: parametres.get("statut") || "",
      fournisseur: parametres.get("fournisseur") || "",
      retard: ["1", "true"].includes(parametres.get("retard")),
    },
    corps: el("tbody"),
    pied: el("tfoot"),
  };
  const creer = () => ouvrirFormulaireCommande({ fournisseurs, surEnregistre: (c) => naviguer(`/achats/${c.numero}`) });
  const entetes = ["N°", "Type", "Statut", "Fournisseur", "Lignes", "Total HT", "Total TTC", "Commandée le", "Livraison annoncée"];
  conteneur.replaceChildren(
    el("div", { class: "titre-page" }, el("h1", {}, "Achats"), el("button", { type: "button", class: "bouton", onclick: creer }, "+ Nouvelle commande")),
    filtres(),
    commandes.length
      ? el(
          "div",
          { class: "table-defilante" },
          el("table", { class: "table table--dense table--composants" }, el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: [4, 5, 6].includes(i) ? "nombre" : "" }, t)))), etat.corps, etat.pied),
        )
      : el("section", { class: "panneau" }, el("p", { class: "texte-doux" }, "Aucune commande enregistrée. Une commande regroupe les lignes d'un devis ou d'un bon de commande chez un fournisseur.")),
  );
  if (commandes.length) rendreTable();
}
