// Détail d'une commande (#/achats/NUMERO) : lignes, ajout de ligne, réception.

import { api } from "../api.js";
import { sectionDocuments } from "../documents.js";
import { editerCellule } from "../edition.js";
import { aujourdhui, formatDate, formatMontant, formatNombre, formatPourcent, libelle, lireNombre } from "../format.js";
import { champComposant, lireComposant } from "../formulaire.js";
import { lienRoute, naviguer } from "../router.js";
import { aPermission, nomAuteur } from "../session.js";
import { afficherAvertissements, afficherErreur, el, enregistrerFichier, lienExterne, lienProduit, masquerErreur } from "../ui.js";
import { STATUTS_COMMANDE, STATUTS_ENGAGES, STATUTS_LIGNE, valeursListe } from "../valeurs.js";
import { badgeRetard, badgeStatut, ouvrirFormulaireCommande } from "./achats_commun.js";
import { lienFournisseur } from "./fournisseurs_commun.js";

const SEUIL_ECART_PCT = 10;
let etat = null;

function ecartPrix(ligne) {
  if (ligne.pu_ht_devis === null || !ligne.pu_ht_estime) return { texte: "—", classe: "" };
  const pct = (100 * (ligne.pu_ht_devis - ligne.pu_ht_estime)) / ligne.pu_ht_estime;
  const classe = Math.abs(pct) > SEUIL_ECART_PCT ? (pct > 0 ? "texte-alerte" : "texte-conforme") : "texte-doux";
  return { texte: `${pct > 0 ? "+" : ""}${formatPourcent(pct, 0)}`, classe };
}

function celluleEditable(ligne, definition, contenu) {
  if (!aPermission("achats")) return el("td", { class: "nombre" }, contenu);
  const td = el("td", { class: "nombre editable" }, contenu);
  td.addEventListener("click", () =>
    editerCellule(td, definition, ligne, {
      enregistrer: (modifs) => api.patchLigne(etat.numero, ligne.id, modifs),
      terminer: (reussi) => reussi && recharger(),
    }),
  );
  return td;
}

function ligneCommande(ligne) {
  const ecart = ecartPrix(ligne);
  const attendent = ligne.ensembles.length
    ? ligne.ensembles.map((e) => el("a", { class: "etiquette", href: lienRoute(`/ensembles/${e.code}`), title: `${e.qte} affecté(s)` }, `${e.code} ×${e.qte}`))
    : el("span", { class: "texte-doux" }, "—");
  const achats = aPermission("achats");
  const statut = el("td", { class: achats ? "editable" : "" }, libelle(ligne.statut_ligne));
  if (achats) {
    statut.addEventListener("click", () =>
      editerCellule(statut, { champ: "statut_ligne", type: "choix", vide: false, options: () => STATUTS_LIGNE }, ligne, {
        enregistrer: (modifs) => api.patchLigne(etat.numero, ligne.id, modifs),
        terminer: (reussi) => reussi && recharger(),
      }),
    );
  }
  return el(
    "tr",
    {},
    el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: ligne.composant_id }) }, ligne.composant_id)),
    el("td", { class: "tronque tronque--large", title: ligne.designation }, ligne.designation),
    el("td", { class: "colonne-lien" }, lienProduit(ligne.lien_produit)),
    // Le conteneur flex reste dans la cellule : posé sur la cellule, il la sortirait du tableau
    // et décalerait les bordures de la ligne.
    el("td", {}, el("div", { class: "attendent" }, attendent)),
    celluleEditable(ligne, { champ: "qte_commandee", type: "entier" }, formatNombre(ligne.qte_commandee)),
    celluleEditable(ligne, { champ: "pu_ht_devis", type: "montant" }, formatMontant(ligne.pu_ht_devis) || el("span", { class: "a-chiffrer" }, "à saisir")),
    el("td", { class: "nombre texte-doux" }, formatMontant(ligne.pu_ht_estime)),
    el("td", { class: `nombre ${ecart.classe}` }, ecart.texte),
    el("td", { class: "nombre" }, formatMontant(ligne.montant_ligne_ht)),
    el("td", { class: `nombre ${ligne.qte_recue > ligne.qte_commandee ? "texte-surveiller" : ""}` }, formatNombre(ligne.qte_recue)),
    statut,
    el("td", { class: "nombre" }, achats ? el("button", { type: "button", class: "bouton-icone", title: "Supprimer la ligne", onclick: () => supprimerLigne(ligne) }, "×") : null),
  );
}

async function supprimerLigne(ligne) {
  if (!confirm(`Supprimer la ligne ${ligne.composant_id} de ${etat.numero} ?`)) return;
  try {
    await api.deleteLigne(etat.numero, ligne.id);
    masquerErreur();
    await recharger();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function formulaireAjout() {
  const composant = champComposant("composant", etat.composants);
  const entree = composant.querySelector("input");
  const qte = el("input", { class: "champ champ--nombre", type: "text", inputmode: "numeric", name: "qte", placeholder: "Qté" });
  const pu = el("input", { class: "champ champ--nombre", type: "text", inputmode: "decimal", name: "pu", placeholder: "PU HT" });
  const aide = el("span", { class: "texte-doux texte-petit" });
  // Choisir un composant pré-remplit la quantité restant à commander et le PU HT estimé.
  entree.addEventListener("change", () => {
    const choisi = lireComposant(entree.value, etat.composants);
    if (!choisi) return;
    qte.value = String(Math.max(1, choisi.reste_a_commander));
    pu.value = choisi.pu_ht === null ? "" : formatNombre(choisi.pu_ht, 2);
    aide.textContent = `Reste à commander : ${choisi.reste_a_commander}, PU HT estimé : ${formatMontant(choisi.pu_ht) || "non chiffré"}`;
  });
  const formulaire = el("form", { class: "formulaire-ligne formulaire-ajout" }, composant, qte, pu, el("button", { type: "submit", class: "bouton" }, "Ajouter la ligne"), aide);
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const choisi = lireComposant(entree.value, etat.composants);
    if (!choisi) return afficherErreur("Choisir un composant dans la liste (identifiant ou désignation).");
    const quantite = lireNombre(qte.value);
    if (quantite === null || Number.isNaN(quantite) || !Number.isInteger(quantite) || quantite <= 0) {
      return afficherErreur("La quantité commandée doit être un entier supérieur à zéro.");
    }
    const prix = lireNombre(pu.value);
    if (Number.isNaN(prix) || (prix !== null && prix < 0)) return afficherErreur(`PU HT illisible : « ${pu.value} ».`);
    try {
      await api.createLigne(etat.numero, { composant_id: choisi.id, qte_commandee: quantite, pu_ht_devis: prix });
      masquerErreur();
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

function tableLignes() {
  const entetes = ["Composant", "Désignation", "", "Attendu par", "Qté", "PU HT devis", "PU estimé", "Écart", "Montant HT", "Reçu", "Statut ligne", ""];
  const numeriques = new Set([4, 5, 6, 7, 8, 9, 11]);
  const c = etat.commande;
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: numeriques.has(i) ? "nombre" : "" }, t)))),
    el("tbody", {}, etat.lignes.map(ligneCommande)),
    el(
      "tfoot",
      {},
      el("tr", {}, el("td", { colspan: 8, class: "nombre" }, "Articles HT"), el("td", { class: "nombre" }, formatMontant(c.montant_articles_ht)), el("td", { colspan: 3 })),
      etat.frais.map(ligneFrais),
      el("tr", {}, el("td", { colspan: 8, class: "nombre fort" }, "Total HT"), el("td", { class: "nombre fort" }, formatMontant(c.total_ht)), el("td", { colspan: 3, class: "texte-doux" }, `TTC ${formatMontant(c.total_ttc)}`)),
    ),
  );
}

// --- Document de demande de devis --------------------------------------------------------

function sectionDemande() {
  const avant = el("input", { class: "champ champ--date", type: "date", "aria-label": "Réponse souhaitée avant le" });
  const telecharger = (format) => async () => {
    try {
      enregistrerFichier(await api.telechargerDemandeDevis(etat.numero, format, avant.value || null));
      masquerErreur();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Demande au fournisseur"),
    el("p", { class: "texte-doux texte-petit" }, "Articles à chiffrer, sans prix ; l'en-tête reprend l'établissement saisi dans Paramètres › Projet."),
    el(
      "div",
      { class: "formulaire-ligne" },
      el("label", { class: "ligne-compacte" }, "Réponse souhaitée avant le ", avant),
      el("button", { type: "button", class: "bouton", onclick: telecharger("pdf") }, "Télécharger le PDF"),
      el("button", { type: "button", class: "bouton bouton--discret", onclick: telecharger("xlsx") }, "Télécharger l'Excel"),
    ),
  );
}

// --- Frais (livraison, douane, facturation…) ----------------------------------------------

function ligneFrais(frais) {
  const achats = aPermission("achats");
  const montant = el("td", { class: achats ? "nombre editable" : "nombre" }, formatMontant(frais.montant_ht));
  if (achats) {
    montant.addEventListener("click", () =>
      editerCellule(montant, { champ: "montant_ht", type: "montant" }, frais, {
        enregistrer: (modifs) => api.patchFrais(frais.id, modifs),
        terminer: (reussi) => reussi && recharger(),
      }),
    );
  }
  const retirer = async () => {
    if (!confirm(`Retirer le frais « ${frais.type_libelle ?? frais.type_frais} » de ${etat.numero} ?`)) return;
    try {
      await api.deleteFrais(frais.id);
      masquerErreur();
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const intitule = frais.commentaire ? `${frais.type_libelle ?? frais.type_frais} (${frais.commentaire})` : (frais.type_libelle ?? frais.type_frais);
  return el(
    "tr",
    {},
    el("td", { colspan: 8, class: "nombre" }, intitule),
    montant,
    el("td", { colspan: 2 }),
    el("td", { class: "nombre" }, achats ? el("button", { type: "button", class: "bouton-icone", title: "Retirer le frais", onclick: retirer }, "×") : null),
  );
}

function formulaireFrais() {
  const type = el("select", { class: "champ", "aria-label": "Type de frais" }, valeursListe("type_frais").map(([code, texte]) => el("option", { value: code }, texte)));
  const montant = el("input", { class: "champ champ--nombre", type: "text", inputmode: "decimal", placeholder: "Montant HT", "aria-label": "Montant HT" });
  const commentaire = el("input", { class: "champ", type: "text", placeholder: "Commentaire (facultatif)", "aria-label": "Commentaire" });
  const formulaire = el("form", { class: "formulaire-ligne formulaire-ajout" }, type, montant, commentaire, el("button", { type: "submit", class: "bouton" }, "Ajouter le frais"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const valeur = lireNombre(montant.value);
    if (valeur === null || Number.isNaN(valeur) || valeur < 0) return afficherErreur(`Montant illisible : « ${montant.value} ».`);
    try {
      await api.createFrais(etat.numero, { type_frais: type.value, montant_ht: valeur, commentaire: commentaire.value.trim() || null });
      masquerErreur();
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

// --- Réception ---------------------------------------------------------------------------

function modeReception() {
  const aRecevoir = etat.lignes.filter((l) => l.statut_ligne !== "Annulee");
  const champs = new Map();
  const lignes = aRecevoir.map((l) => {
    const reste = Math.max(0, l.qte_commandee - l.qte_recue);
    const champ = el("input", { class: "champ-cellule champ-cellule--nombre", type: "text", inputmode: "numeric", value: String(reste), "aria-label": `Reçu pour ${l.composant_id}` });
    champs.set(l.id, champ);
    return el(
      "tr",
      {},
      el("td", { class: "code" }, l.composant_id),
      el("td", { class: "tronque tronque--large", title: l.designation }, l.designation),
      el("td", { class: "nombre" }, formatNombre(l.qte_commandee)),
      el("td", { class: "nombre" }, formatNombre(l.qte_recue)),
      el("td", { class: "nombre" }, champ),
    );
  });
  const date = el("input", { class: "champ champ--date", type: "date", value: aujourdhui() });
  const emplacement = el("input", { class: "champ", type: "text", placeholder: "ex. Armoire A - bac 3" });
  // Par défaut, la personne connectée ; modifiable si quelqu'un d'autre a reçu le colis.
  const parQui = el("input", { class: "champ", type: "text", value: nomAuteur() });
  const valider = async () => {
    const detail = [];
    for (const [id, champ] of champs) {
      const n = lireNombre(champ.value);
      if (n === null) continue;
      if (Number.isNaN(n) || !Number.isInteger(n) || n < 0) return afficherErreur(`Quantité reçue invalide : « ${champ.value} ».`);
      detail.push({ id, qte: n });
    }
    try {
      const resultat = await api.receptionner(etat.numero, { date: date.value || null, emplacement: emplacement.value.trim() || null, par_qui: parQui.value.trim() || null, lignes: detail });
      masquerErreur();
      afficherAvertissements(resultat.avertissements);
      etat.reception = false;
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  return el(
    "section",
    { class: "panneau panneau--reception" },
    el("h2", {}, "Réception de la livraison"),
    el("p", { class: "texte-doux" }, "Saisir la quantité reçue dans cette livraison ; elle s'ajoute aux réceptions précédentes. La validation met à jour les lignes, le stock et le statut de la commande."),
    el("div", { class: "formulaire-ligne" }, el("label", { class: "ligne-compacte" }, "Date ", date), el("label", { class: "ligne-compacte" }, "Emplacement ", emplacement), el("label", { class: "ligne-compacte" }, "Reçu par ", parQui)),
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, ["Composant", "Désignation", "Commandé", "Déjà reçu", "Reçu cette fois"].map((t, i) => el("th", { class: i >= 2 ? "nombre" : "" }, t)))),
      el("tbody", {}, lignes),
    ),
    el(
      "div",
      { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => { etat.reception = false; rendre(); } }, "Annuler"),
      el("button", { type: "button", class: "bouton", onclick: valider }, "Valider la réception"),
    ),
  );
}

// --- Page -----------------------------------------------------------------------------------

function infos() {
  const c = etat.commande;
  const statut = el("select", { class: "filtre", "aria-label": "Statut de la commande", disabled: !aPermission("achats") }, STATUTS_COMMANDE.map((s) => el("option", { value: s, selected: s === c.statut }, libelle(s))));
  statut.addEventListener("change", async () => {
    try {
      await api.patchCommande(c.numero, { statut: statut.value });
      masquerErreur();
      await recharger();
    } catch (erreur) {
      statut.value = c.statut;
      afficherErreur(erreur);
    }
  });
  const lien = c.lien_document ? lienExterne(c.lien_document, "ouvrir") : "—";
  const paires = [
    ["Fournisseur", lienFournisseur(c.fournisseur_nom, etat.fournisseurs.find((f) => f.nom === c.fournisseur_nom)?.statut)],
    ["Statut", statut],
    ["Demandée par", c.demande_par ?? "—"],
    ["Référence externe", c.reference_externe ?? "—"],
    ["Demande", formatDate(c.date_demande) || "—"],
    ["Devis reçu", formatDate(c.date_reception_devis) || "—"],
    ["Commandée le", formatDate(c.date_commande) || "—"],
    ["Livraison annoncée", [formatDate(c.livraison_annoncee) || "—", " ", badgeRetard(c)]],
    ["Réception réelle", formatDate(c.date_reception_reelle) || "—"],
    ["TVA", formatPourcent(c.taux_tva * 100, 1)],
    ["Document", lien],
  ];
  return el(
    "section",
    { class: "panneau" },
    el("dl", { class: "infos-commande" }, paires.flatMap(([t, v]) => [el("dt", {}, t), el("dd", {}, v)])),
    c.commentaire ? el("p", { class: "texte-doux" }, c.commentaire) : null,
    c.type === "Commande" && !STATUTS_ENGAGES.includes(c.statut)
      ? el("p", { class: "texte-doux texte-petit" }, "Cette commande n'est pas encore engagée : passer son statut à « Commandé » pour qu'elle compte dans le montant engagé et puisse être réceptionnée.")
      : null,
  );
}

function rendre() {
  const c = etat.commande;
  const receptionnable = c.type === "Commande" && ["Commande", "Livre partiel"].includes(c.statut) && etat.lignes.length > 0;
  etat.conteneur.replaceChildren(
    el("p", { class: "fil" }, el("a", { href: "#/achats" }, "← Achats")),
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, `${c.numero} `, el("span", { class: "etiquette" }, c.type), " ", badgeStatut(c)),
      el(
        "div",
        { class: "actions" },
        receptionnable && !etat.reception ? el("button", { type: "button", class: "bouton si-achats", onclick: () => { etat.reception = true; rendre(); } }, "Réceptionner") : null,
        el("button", { type: "button", class: "bouton bouton--discret si-achats", onclick: () => ouvrirFormulaireCommande({ commande: c, fournisseurs: etat.fournisseurs, surEnregistre: recharger }) }, "Modifier"),
        el("button", { type: "button", class: "bouton bouton--danger si-achats", onclick: archiver }, "Archiver"),
      ),
    ),
    infos(),
    etat.lignes.length && !etat.reception ? sectionDemande() : "",
    etat.reception
      ? modeReception()
      : el(
          "section",
          { class: "panneau" },
          el("h2", {}, "Lignes"),
          etat.lignes.length || etat.frais.length ? tableLignes() : el("p", { class: "texte-doux" }, "Aucune ligne pour l'instant."),
          el("p", { class: "texte-doux texte-petit" }, `L'écart entre le PU du devis et le PU estimé est coloré au-delà de ${SEUIL_ECART_PCT} %.`),
          aPermission("achats") ? el("h3", { class: "sous-titre" }, "Ajouter une ligne") : null,
          aPermission("achats") ? formulaireAjout() : null,
          aPermission("achats") ? el("h3", { class: "sous-titre" }, "Ajouter un frais") : null,
          aPermission("achats") ? formulaireFrais() : null,
        ),
    el(
      "div",
      { class: "panneau" },
      sectionDocuments({
        documents: etat.documents,
        typeParDefaut: etat.commande.type === "Devis" ? "Devis" : "Bon de commande",
        aide: "Ils apparaissent aussi dans la fiche de chaque composant de la commande.",
        deposer: (donnees, progression) => api.deposerDocumentsCommande(etat.numero, donnees, progression),
        depot: aPermission("achats"),
        surChangement: recharger,
      }),
    ),
  );
}

async function archiver() {
  if (!confirm(`Archiver la commande ${etat.numero} ?`)) return;
  try {
    await api.archiveCommande(etat.numero);
    masquerErreur();
    naviguer("/achats");
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

async function recharger() {
  const [commande, lignes, frais, composants, documents] = await Promise.all([
    api.getCommande(etat.numero),
    api.getLignes(etat.numero),
    api.getFrais(etat.numero),
    api.getComposants({ tri: "id" }),
    api.getDocumentsCommande(etat.numero),
  ]);
  Object.assign(etat, { commande, lignes, frais, composants, documents });
  rendre();
}

export async function afficherDetailCommande(conteneur, _parametres, numero) {
  etat = { conteneur, numero, reception: false, fournisseurs: await api.getFournisseurs() };
  try {
    await recharger();
  } catch (erreur) {
    if (erreur.statut !== 404) throw erreur;
    conteneur.replaceChildren(
      el("p", { class: "fil" }, el("a", { href: "#/achats" }, "← Achats")),
      el("h1", {}, "Commande introuvable"),
      el("p", { class: "texte-doux" }, `La commande « ${numero} » n'existe pas ou a été archivée.`),
    );
  }
}
