// Section « Documents » partagée par le détail d'une commande et la fiche d'un composant.

import { api, lienFichierDocument } from "./api.js";
import { formatDate } from "./format.js";
import { lienRoute } from "./router.js";
import { afficherAvertissements, afficherErreur, el, masquerErreur } from "./ui.js";

export const TYPES_DOCUMENT = [
  "Devis",
  "Bon de commande",
  "Facture",
  "Bon de livraison",
  "Fiche technique",
  "Plan",
  "Photo",
  "Autre",
];

function formatTaille(octets) {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} ko`;
  return `${(octets / (1024 * 1024)).toFixed(1).replace(".", ",")} Mo`;
}

function ligneDocument(document, { avecSource, surChangement }) {
  const retirer = el("button", {
    type: "button",
    class: "bouton-icone",
    title: "Retirer le document (le fichier reste dans le dossier des documents)",
    onclick: async () => {
      if (!confirm(`Retirer « ${document.nom_origine} » ?`)) return;
      try {
        await api.retirerDocument(document.id);
        masquerErreur();
        await surChangement();
      } catch (erreur) {
        afficherErreur(erreur);
      }
    },
  }, "×");
  const source = document.source === "commande"
    ? el("a", { href: lienRoute(`/achats/${document.commande_numero}`) }, document.commande_numero)
    : el("span", { class: "texte-doux" }, "composant");
  return el(
    "tr",
    {},
    el("td", {}, el("span", { class: "etiquette" }, document.type_document)),
    el("td", { class: "tronque tronque--large", title: document.nom_origine }, el("a", { href: lienFichierDocument(document.id), target: "_blank", rel: "noopener" }, document.nom_origine)),
    avecSource ? el("td", {}, source) : null,
    el("td", { class: "nombre texte-doux" }, formatTaille(document.taille)),
    el("td", { class: "texte-doux" }, formatDate(document.ajoute_le)),
    el("td", { class: "tronque", title: document.commentaire ?? "" }, document.commentaire ?? ""),
    // Un document de commande se retire depuis la commande, pas depuis le composant.
    el("td", { class: "nombre" }, avecSource && document.source === "commande" ? null : retirer),
  );
}

function formulaireDepot({ typeParDefaut, deposer, surChangement }) {
  const fichiers = el("input", { type: "file", multiple: true, class: "champ-fichier", "aria-label": "Fichiers à joindre" });
  const type = el("select", { class: "filtre", "aria-label": "Type de document" }, TYPES_DOCUMENT.map((t) => el("option", { value: t, selected: t === typeParDefaut }, t)));
  const commentaire = el("input", { class: "champ", type: "text", placeholder: "Commentaire (facultatif)" });
  const formulaire = el("form", { class: "formulaire-ligne formulaire-depot" }, fichiers, type, commentaire, el("button", { type: "submit", class: "bouton" }, "Joindre"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fichiers.files.length) return afficherErreur("Choisir au moins un fichier à joindre.");
    const donnees = new FormData();
    for (const fichier of fichiers.files) donnees.append("fichiers", fichier);
    donnees.append("type_document", type.value);
    if (commentaire.value.trim()) donnees.append("commentaire", commentaire.value.trim());
    const bouton = formulaire.querySelector("button");
    bouton.disabled = true;
    try {
      const resultat = await deposer(donnees);
      masquerErreur();
      afficherAvertissements(resultat.erreurs);
      await surChangement();
    } catch (erreur) {
      bouton.disabled = false;
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

/**
 * documents : liste renvoyée par l'API ; deposer(FormData) renvoie une promesse ;
 * avecSource : affiche d'où vient chaque document (fiche composant).
 */
export function sectionDocuments({ titre = "Documents", documents, deposer, surChangement, typeParDefaut, avecSource = false, aide }) {
  const entetes = ["Type", "Fichier", avecSource ? "Source" : null, "Taille", "Ajouté le", "Commentaire", ""].filter((t) => t !== null);
  return el(
    "section",
    { class: "fiche__section section-documents" },
    el("h3", {}, titre),
    aide ? el("p", { class: "texte-doux texte-petit" }, aide) : null,
    documents.length
      ? el(
          "table",
          { class: "table table--dense" },
          el("thead", {}, el("tr", {}, entetes.map((t) => el("th", { class: t === "Taille" ? "nombre" : "" }, t)))),
          el("tbody", {}, documents.map((d) => ligneDocument(d, { avecSource, surChangement }))),
        )
      : el("p", { class: "texte-doux" }, "Aucun document joint."),
    formulaireDepot({ typeParDefaut, deposer, surChangement }),
  );
}
