// Suivi des achats tenu par l'établissement : le classeur imposé, en aller-retour.
// On envoie la dernière version du fichier ; Nomentrace propose ce que l'établissement y a
// rempli, applique ce qu'on retient et rend le fichier complété des devis transmis.

import { api } from "../api.js";
import { lireLimites, refusEnvoi } from "../envoi.js";
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
  mode_reel: "Répartition du réel",
  commentaire_suivi: "Commentaire",
};

function valeur(champ, v) {
  if (v === null || v === undefined || v === "") return "—";
  if (champ.endsWith("_confirmee")) return v ? "oui" : "non";
  if (champ === "montant_commande_ht") return formatMontant(v);
  if (champ === "mode_reel") return v === "lignes" ? "par ligne" : "au prorata de l'estimé";
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) return formatDate(v);
  return champ === "statut" ? libelle(v) : String(v);
}

function blocCommande(proposition) {
  const cases = proposition.changements.map((c) => {
    const coche = el("input", { type: "checkbox", checked: true, value: c.champ });
    return el("label", { class: "filtre-case suivi-changement" }, coche, `${CHAMPS[c.champ] ?? c.champ} : ${valeur(c.champ, c.avant)} → ${valeur(c.champ, c.apres)}`);
  });
  const note = el("p", { class: "texte-doux texte-petit", hidden: true }, "Lue dans des lignes saisies à la main : sans leur association, rien n'est repris pour cette commande.");
  const element = el("div", { class: "suivi-commande-bloc" }, el("h3", {}, `${proposition.numero} · ${proposition.fournisseur ?? ""}`), note, cases);
  // Une proposition tirée des lignes d'une association refusée n'est pas appliquée par le
  // serveur : l'écran la grise et l'exclut de l'envoi.
  const activer = (actif) => {
    cases.forEach((c) => { c.querySelector("input").disabled = !actif; });
    element.classList.toggle("suivi-commande-bloc--inactif", !actif);
    note.hidden = actif;
  };
  return { numero: proposition.numero, cases, element, activer };
}

// Lignes saisies à la main reconnues comme celles d'une commande : cochée d'office quand
// toutes ses lignes ont trouvé la leur. Retenue, la commande n'est pas ajoutée une seconde fois.
function blocAssociation(association) {
  const coche = el("input", { type: "checkbox", checked: association.complete, value: association.numero });
  const lignes = association.lignes.map((l) =>
    el("li", {}, `ligne ${l.ligne} : ${l.designation ?? ""}`, l.ecarts.length ? el("span", { class: "texte-surveiller" }, ` (${l.ecarts.join(" ; ")})`) : null),
  );
  return {
    association,
    coche,
    element: el(
      "div",
      { class: "suivi-commande-bloc" },
      el("label", { class: "filtre-case" }, coche, el("strong", {}, `Associer ${association.lignes.length} ligne(s) à ${association.numero} · ${association.fournisseur ?? ""}`)),
      el("ul", { class: "liste-simple texte-petit" }, lignes),
      association.manquantes.length
        ? el("p", { class: "texte-surveiller texte-petit" }, `Sans ligne dans le fichier, ajoutées en bas : ${association.manquantes.join(", ")}.`)
        : null,
    ),
  };
}

function resultat(analyse, fichier, surApplique, appliquerSuivi) {
  const blocs = analyse.propositions.map(blocCommande);
  const associations = (analyse.associations ?? []).map(blocAssociation);
  const appliquer = async () => {
    const retenues = Object.fromEntries(
      blocs.map((b) => [b.numero, b.cases.map((c) => c.querySelector("input")).filter((c) => c.checked && !c.disabled).map((c) => c.value)]),
    );
    const donnees = new FormData();
    donnees.append("fichier", fichier);
    donnees.append("retenues", JSON.stringify(retenues));
    donnees.append("associations", JSON.stringify(associations.filter((a) => a.coche.checked).map((a) => a.coche.value)));
    try {
      enregistrerFichier(await appliquerSuivi(donnees));
      masquerErreur();
      fermerPanneau({ silencieux: true });
      afficherInformation("Fichier de suivi complété : le reposer sur l'espace partagé à la place de l'ancien.");
      await surApplique();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  // L'analyse suppose toutes les associations retenues : les textes suivent les cases cochées.
  const texteAjout = el("p");
  const texteCompletion = el("p");
  const majTextes = () => {
    const refusees = associations.filter((a) => !a.coche.checked).map((a) => a.association);
    const nbAjout = analyse.nb_lignes_a_ajouter + refusees.reduce((s, a) => s + a.lignes_ajoutees_si_refusee, 0);
    const commandesAjout = [...new Set([...analyse.commandes_a_ajouter, ...refusees.map((a) => a.numero)])].sort();
    const nbCompletion = analyse.nb_lignes_a_completer - refusees.reduce((s, a) => s + a.lignes_completees_si_retenue, 0);
    texteAjout.textContent = nbAjout
      ? `${nbAjout} ligne(s) à ajouter au fichier (${commandesAjout.join(", ")}).`
      : "Aucune nouvelle ligne à ajouter : tous les devis transmis y sont déjà.";
    texteCompletion.textContent = nbCompletion
      ? `${nbCompletion} ligne(s) déjà présente(s) dont des cases vides seront complétées (date du devis, par exemple) ; une case déjà remplie n'est jamais réécrite.`
      : "";
    texteCompletion.hidden = !nbCompletion;
    const numerosRefuses = new Set(refusees.map((a) => a.numero));
    blocs.forEach((b) => b.activer(!numerosRefuses.has(b.numero)));
  };
  associations.forEach((a) => a.coche.addEventListener("change", majTextes));
  majTextes();
  return [
    associations.length
      ? [
          el("h3", {}, "Lignes saisies à la main"),
          el("p", { class: "texte-doux texte-petit" }, "Reconnues par le fournisseur, puis la référence, la désignation ou le montant d'un frais. Les écarts sont signalés, jamais corrigés dans le fichier."),
          associations.map((a) => a.element),
        ]
      : null,
    el("h3", {}, "Retour de l'établissement"),
    blocs.length ? blocs.map((b) => b.element) : el("p", { class: "texte-doux" }, "Rien de nouveau dans les colonnes de l'établissement."),
    analyse.lignes_inconnues.length
      ? el("div", { class: "texte-surveiller texte-petit" }, el("p", {}, "Lignes sans référence Nomentrace, ignorées :"), el("ul", { class: "liste-simple" }, analyse.lignes_inconnues.map((l) => el("li", {}, l))))
      : null,
    el("h3", {}, "Ajouts au fichier"),
    texteAjout,
    texteCompletion,
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "button", class: "bouton", onclick: appliquer }, "Appliquer et télécharger le fichier"),
    ),
  ];
}

// Par défaut, le suivi du projet ; la page d'un dossier passe ses propres appels (communes).
export function ouvrirSuivi(surApplique, { analyser = api.analyserSuivi, appliquer = api.appliquerSuivi } = {}) {
  const fichier = el("input", { type: "file", accept: ".xlsx", class: "champ-fichier", "aria-label": "Fichier de suivi" });
  const zone = el("div");
  const formulaire = el("form", { class: "formulaire-ligne formulaire-depot" }, fichier, el("button", { type: "submit", class: "bouton" }, "Analyser"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const choisi = fichier.files[0];
    if (!choisi) return afficherErreur("Choisir le fichier de suivi.");
    const refus = refusEnvoi([choisi], await lireLimites(), { extensions: [".xlsx"] });
    if (refus) return afficherErreur(refus);
    const donnees = new FormData();
    donnees.append("fichier", choisi);
    const suivi = suiviEnvoi(1, "Lecture");
    zone.replaceChildren(suivi.element);
    try {
      const analyse = await analyser(donnees, suivi.maj);
      masquerErreur();
      zone.replaceChildren(...resultat(analyse, choisi, surApplique, appliquer).flat(2).filter(Boolean));
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
