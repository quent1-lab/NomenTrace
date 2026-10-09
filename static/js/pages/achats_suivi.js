// Suivi des achats tenu par l'établissement : le classeur imposé, en aller-retour.
// On envoie la dernière version du fichier ; Nomentrace propose ce que l'établissement y a
// rempli, applique ce qu'on retient et rend le fichier complété des devis transmis.

import { api } from "../api.js";
import { formatDate, formatMontant, libelle } from "../format.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, afficherInformation, el, enregistrerFichier, masquerErreur, suiviEnvoi } from "../ui.js";

const CHAMPS = {
  type: "Type",
  statut: "Statut",
  date_commande: "Commandée le",
  date_commande_confirmee: "Date de commande confirmée",
  livraison_annoncee: "Livraison annoncée",
  livraison_confirmee: "Livraison confirmée",
  date_reception_annoncee: "Réception annoncée",
  montant_commande_ht: "Montant de la commande HT",
  commentaire_suivi: "Commentaire",
};

function valeur(champ, v) {
  if (v === null || v === undefined || v === "") return "—";
  if (champ.endsWith("_confirmee")) return v ? "oui" : "non";
  if (champ === "montant_commande_ht") return formatMontant(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) return formatDate(v);
  return champ === "statut" ? libelle(v) : String(v);
}

function blocCommande(proposition) {
  const cases = proposition.changements.map((c) => {
    const coche = el("input", { type: "checkbox", checked: true, value: c.champ });
    return el("label", { class: "filtre-case suivi-changement" }, coche, `${CHAMPS[c.champ] ?? c.champ} : ${valeur(c.champ, c.avant)} → ${valeur(c.champ, c.apres)}`);
  });
  return {
    numero: proposition.numero,
    cases,
    element: el("div", { class: "suivi-commande-bloc" }, el("h3", {}, `${proposition.numero} · ${proposition.fournisseur ?? ""}`), cases),
  };
}

function resultat(analyse, fichier, surApplique) {
  const blocs = analyse.propositions.map(blocCommande);
  const appliquer = async () => {
    const retenues = Object.fromEntries(
      blocs.map((b) => [b.numero, b.cases.map((c) => c.querySelector("input")).filter((c) => c.checked).map((c) => c.value)]),
    );
    const donnees = new FormData();
    donnees.append("fichier", fichier);
    donnees.append("retenues", JSON.stringify(retenues));
    try {
      enregistrerFichier(await api.appliquerSuivi(donnees));
      masquerErreur();
      fermerPanneau({ silencieux: true });
      afficherInformation("Fichier de suivi complété : le reposer sur l'espace partagé à la place de l'ancien.");
      await surApplique();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const ajout = analyse.nb_lignes_a_ajouter
    ? `${analyse.nb_lignes_a_ajouter} ligne(s) à ajouter au fichier (${analyse.commandes_a_ajouter.join(", ")}).`
    : "Aucune nouvelle ligne à ajouter : tous les devis transmis y sont déjà.";
  return [
    el("h3", {}, "Retour de l'établissement"),
    blocs.length ? blocs.map((b) => b.element) : el("p", { class: "texte-doux" }, "Rien de nouveau dans les colonnes de l'établissement."),
    analyse.lignes_inconnues.length
      ? el("p", { class: "texte-surveiller texte-petit" }, `Lignes sans référence Nomentrace, ignorées : ${analyse.lignes_inconnues.join(", ")}.`)
      : null,
    el("h3", {}, "Ajouts au fichier"),
    el("p", {}, ajout),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "button", class: "bouton", onclick: appliquer }, "Appliquer et télécharger le fichier"),
    ),
  ];
}

export function ouvrirSuivi(surApplique) {
  const fichier = el("input", { type: "file", accept: ".xlsx", class: "champ-fichier", "aria-label": "Fichier de suivi" });
  const zone = el("div");
  const formulaire = el("form", { class: "formulaire-ligne formulaire-depot" }, fichier, el("button", { type: "submit", class: "bouton" }, "Analyser"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const choisi = fichier.files[0];
    if (!choisi) return afficherErreur("Choisir le fichier de suivi.");
    const donnees = new FormData();
    donnees.append("fichier", choisi);
    const suivi = suiviEnvoi(1, "Lecture");
    zone.replaceChildren(suivi.element);
    try {
      const analyse = await api.analyserSuivi(donnees, suivi.maj);
      masquerErreur();
      zone.replaceChildren(...resultat(analyse, choisi, surApplique).flat().filter(Boolean));
    } catch (erreur) {
      zone.replaceChildren();
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau("Suivi de l'établissement", [
    el("p", { class: "texte-doux" }, "Envoyer la dernière version du fichier de suivi. Nomentrace lit ce que l'établissement y a rempli, puis y ajoute les devis transmis au suivi ; rien n'est modifié avant « Appliquer »."),
    formulaire,
    zone,
  ]);
}
