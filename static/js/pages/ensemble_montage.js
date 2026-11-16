// Montage d'un ensemble (#/ensembles/CODE/montage) : les composants affectés directement,
// groupés par état (prêt, partiel, en attente, monté). « Monter » crée une sortie de montage,
// « Annuler » un retour de montage ; le serveur refuse ce qui n'est pas en stock et tient le
// statut de montage à jour.

import { api } from "../api.js";
import { formatNombre, libelle } from "../format.js";
import { lienRoute } from "../router.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { barreProgression } from "./ensembles_commun.js";

const DUREE_ANNULATION_MS = 10000;

let etat = null;

function etatLigne(ligne) {
  if (ligne.reste_a_monter <= 0) return "monte";
  if (ligne.stock_actuel >= ligne.reste_a_monter) return "pret";
  if (ligne.stock_actuel > 0) return "partiel";
  return "attente";
}

function raisonAttente(ligne) {
  if (ligne.avancement === "Commande") return "attend la livraison";
  if (ligne.avancement === "A commander") return "pas encore commandé";
  return "pas en stock";
}

// --- Actions --------------------------------------------------------------------------------

async function agir(ligne, qte, sens) {
  const corps = { composant_id: ligne.composant_id, qte };
  try {
    if (sens === "monter") await api.monterEnsemble(etat.code, corps);
    else await api.demonterEnsemble(etat.code, corps);
    masquerErreur();
  } catch (erreur) {
    afficherErreur(erreur);
    return;
  }
  etat.dernier = sens === "monter" ? { ligne, qte, jusqua: Date.now() + DUREE_ANNULATION_MS } : null;
  await recharger();
  if (etat.dernier) {
    clearTimeout(etat.minuterie);
    etat.minuterie = setTimeout(() => {
      etat.dernier = null;
      // L'écran a pu être quitté entre-temps : ne pas redessiner par-dessus un autre.
      if (location.hash.startsWith(`#/ensembles/${encodeURIComponent(etat.code)}/montage`)) rendre();
    }, DUREE_ANNULATION_MS);
  }
}

// Quantité choisie entre 1 et max, avec − et + ; renvoie l'élément et un lecteur de valeur.
function choixQuantite(initiale, max, designation) {
  const champ = el("input", {
    type: "number",
    class: "montage-qte__champ",
    min: "1",
    max: String(max),
    value: String(initiale),
    inputmode: "numeric",
    "aria-label": `Quantité pour ${designation}`,
  });
  const lire = () => Math.min(max, Math.max(1, Math.trunc(Number(champ.value)) || 1));
  const regler = (delta) => {
    champ.value = String(Math.min(max, Math.max(1, lire() + delta)));
  };
  const element = el(
    "span",
    { class: "montage-qte si-ecriture" },
    el("button", { type: "button", "aria-label": "Une pièce de moins", onclick: () => regler(-1) }, "−"),
    champ,
    el("button", { type: "button", "aria-label": "Une pièce de plus", onclick: () => regler(1) }, "+"),
  );
  return { element, lire };
}

// --- Lignes ---------------------------------------------------------------------------------

function infos(ligne, classe) {
  const stock = classe === "attente" ? el("span", { class: "texte-doux" }, raisonAttente(ligne)) : el("span", { class: "texte-doux" }, `stock ${formatNombre(ligne.stock_actuel)}`);
  if (classe === "monte") {
    return el("span", { class: "montage-ligne__infos" }, el("span", {}, "monté ", el("strong", {}, formatNombre(ligne.qte_montee))));
  }
  return el("span", { class: "montage-ligne__infos" }, el("span", {}, "reste ", el("strong", {}, formatNombre(ligne.reste_a_monter))), stock);
}

function actions(ligne, classe) {
  if (classe === "attente") {
    return el("span", { class: "montage-ligne__actions" }, el("button", { type: "button", class: "bouton si-ecriture", disabled: true }, "Monter"));
  }
  if (classe === "monte") {
    const choix = choixQuantite(1, ligne.qte_montee, ligne.designation);
    return el(
      "span",
      { class: "montage-ligne__actions" },
      choix.element,
      el("button", { type: "button", class: "bouton bouton--discret si-ecriture", onclick: () => agir(ligne, choix.lire(), "demonter") }, "Démonter"),
    );
  }
  const max = Math.min(ligne.reste_a_monter, ligne.stock_actuel);
  const choix = choixQuantite(max, max, ligne.designation);
  return el(
    "span",
    { class: "montage-ligne__actions" },
    choix.element,
    el("button", { type: "button", class: "bouton si-ecriture", onclick: () => agir(ligne, choix.lire(), "monter") }, "Monter"),
  );
}

function ligneMontage(ligne, classe) {
  const emplacement = etat.emplacements.get(ligne.composant_id);
  return el(
    "li",
    { class: `montage-ligne montage-ligne--${classe}` },
    el("a", { class: "code montage-ligne__id", href: lienRoute("/composants", { fiche: ligne.composant_id }) }, ligne.composant_id),
    el("span", { class: "montage-ligne__designation", title: ligne.designation }, ligne.designation),
    el("span", { class: "montage-ligne__emplacement" }, emplacement && classe !== "monte" ? el("span", { class: "emplacement" }, emplacement) : null),
    infos(ligne, classe),
    actions(ligne, classe),
  );
}

const GROUPES = [
  ["pret", "Prêt à monter"],
  ["partiel", "Partiel"],
  ["attente", "En attente"],
  ["monte", "Monté"],
];

function groupe(classe, titre, lignes) {
  if (!lignes.length) return null;
  const replie = classe === "monte" && !etat.voirMontes;
  const bascule =
    classe === "monte"
      ? el("button", { type: "button", class: "bouton-lien", "aria-expanded": String(!replie), onclick: () => { etat.voirMontes = !etat.voirMontes; rendre(); } }, replie ? "afficher" : "masquer")
      : null;
  return el(
    "section",
    { class: "montage-groupe" },
    el("h2", { class: "montage-groupe__titre" }, el("span", { class: `pastille-etat pastille-etat--${classe}`, "aria-hidden": "true" }), `${titre} · ${lignes.length}`, bascule),
    replie ? null : el("ul", { class: "montage-liste" }, lignes.map((l) => ligneMontage(l, classe))),
  );
}

function sousEnsembles() {
  const enfants = etat.ensemble.enfants;
  if (!enfants.length) return null;
  return el(
    "section",
    { class: "montage-groupe" },
    el("h2", { class: "montage-groupe__titre" }, `Sous-ensembles · ${enfants.length}`),
    el(
      "ul",
      { class: "montage-liste" },
      enfants.map((s) =>
        el(
          "li",
          { class: "montage-sous" },
          el("span", {}, el("strong", {}, s.nom), " ", el("span", { class: "etiquette" }, s.code)),
          barreProgression("Pièces montées", s.cumul.nb_pieces_montees, s.cumul.nb_pieces_total, "aucune pièce"),
          el("a", { class: "bouton bouton--discret", href: `#/ensembles/${encodeURIComponent(s.code)}/montage` }, "Monter"),
        ),
      ),
    ),
  );
}

function bandeauAnnulation() {
  const dernier = etat.dernier;
  if (!dernier || Date.now() > dernier.jusqua) return null;
  return el(
    "div",
    { class: "montage-annulation", role: "status" },
    el("span", {}, `${formatNombre(dernier.qte)} × ${dernier.ligne.composant_id} monté${dernier.qte > 1 ? "s" : ""}`),
    el(
      "button",
      {
        type: "button",
        class: "bouton-lien",
        onclick: () => {
          etat.dernier = null;
          agir(dernier.ligne, dernier.qte, "demonter");
        },
      },
      "Annuler",
    ),
  );
}

function filAriane(e) {
  const liens = [el("a", { href: "#/ensembles" }, "← Ensembles")];
  for (const parent of e.chemin) {
    liens.push(" / ", el("a", { href: `#/ensembles/${encodeURIComponent(parent.code)}` }, parent.nom));
  }
  liens.push(" / ", el("a", { href: `#/ensembles/${encodeURIComponent(e.code)}` }, e.nom));
  return el("p", { class: "fil" }, liens);
}

function rendre() {
  const e = etat.ensemble;
  const parLigne = new Map(GROUPES.map(([classe]) => [classe, []]));
  for (const ligne of etat.lignes) parLigne.get(etatLigne(ligne)).push(ligne);
  const titreProgression = e.enfants.length ? "Pièces montées (affectations directes)" : "Pièces montées";
  const elements = [
    filAriane(e),
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, `Montage · ${e.nom} `, el("span", { class: "etiquette" }, e.code)),
      el(
        "div",
        { class: "actions" },
        el("span", { class: `statut-montage statut-montage--${e.statut_montage.replace(/\s/g, "-").toLowerCase()}` }, libelle(e.statut_montage)),
        el("a", { class: "bouton bouton--discret montage-fiche", href: `#/ensembles/${encodeURIComponent(e.code)}` }, "Fiche de l'ensemble"),
      ),
    ),
    el("section", { class: "panneau montage-progression" }, barreProgression(titreProgression, e.nb_pieces_montees, e.nb_pieces_total, "aucune pièce affectée")),
    etat.lignes.length ? null : el("p", { class: "texte-doux" }, "Aucun composant affecté directement à cet ensemble."),
    GROUPES.map(([classe, titre]) => groupe(classe, titre, parLigne.get(classe))),
    sousEnsembles(),
    bandeauAnnulation(),
  ];
  etat.conteneur.replaceChildren(...elements.flat().filter(Boolean));
}

async function recharger() {
  const [ensemble, lignes, stock] = await Promise.all([api.getEnsemble(etat.code), api.getComposantsEnsemble(etat.code), api.getStock()]);
  const emplacements = new Map(stock.filter((s) => s.emplacement).map((s) => [s.id, s.emplacement]));
  Object.assign(etat, { ensemble, lignes, emplacements });
  rendre();
}

export async function afficherMontageEnsemble(conteneur, parametres, code) {
  clearTimeout(etat?.minuterie);
  etat = { conteneur, code, voirMontes: false, dernier: null, minuterie: null };
  try {
    await recharger();
  } catch (erreur) {
    if (erreur.statut !== 404) throw erreur;
    conteneur.replaceChildren(
      el("p", { class: "fil" }, el("a", { href: "#/ensembles" }, "← Ensembles")),
      el("h1", {}, "Ensemble introuvable"),
      el("p", { class: "texte-doux" }, `L'ensemble « ${code} » n'existe pas ou a été archivé.`),
    );
  }
}
