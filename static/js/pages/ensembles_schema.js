// Vue « Schéma » de l'écran ensembles : l'arborescence dessinée en SVG, de gauche à droite,
// depuis le nœud du projet. Chaque nœud montre son coût cumulé face à son budget ; un clic
// ouvre le détail de l'ensemble.

import { formatMontant } from "../format.js";
import { naviguer } from "../router.js";
import { el } from "../ui.js";
import { TRACE_CADENAS } from "./ensembles_commun.js";

const SVG = "http://www.w3.org/2000/svg";
const LARGEUR = 230;
const HAUTEUR = 78;
const ECART_COLONNES = 64;
const ECART_LIGNES = 14;
const MARGE = 12;
const LONGUEUR_NOM = 28;

function svg(balise, attributs = {}, ...enfants) {
  const element = document.createElementNS(SVG, balise);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (valeur === null || valeur === undefined || valeur === false) continue;
    if (cle.startsWith("on") && typeof valeur === "function") element.addEventListener(cle.slice(2), valeur);
    else element.setAttribute(cle, valeur);
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    element.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return element;
}

function tronquer(texte, longueur) {
  return texte.length > longueur ? `${texte.slice(0, longueur - 1)}…` : texte;
}

// Place les nœuds : une colonne par niveau, les feuilles les unes sous les autres, chaque
// parent centré sur ses enfants.
function placer(racine, enfantsDe) {
  let prochaineLigne = 0;
  const visiter = (noeud, niveau) => {
    const enfants = enfantsDe.get(noeud.code) ?? [];
    enfants.forEach((e) => visiter(e, niveau + 1));
    noeud.x = MARGE + niveau * (LARGEUR + ECART_COLONNES);
    if (enfants.length) {
      noeud.y = (enfants[0].y + enfants[enfants.length - 1].y) / 2;
    } else {
      noeud.y = MARGE + prochaineLigne * (HAUTEUR + ECART_LIGNES);
      prochaineLigne += 1;
    }
  };
  visiter(racine, 0);
  return prochaineLigne;
}

function lien(parent, enfant) {
  const x1 = parent.x + LARGEUR;
  const y1 = parent.y + HAUTEUR / 2;
  const x2 = enfant.x;
  const y2 = enfant.y + HAUTEUR / 2;
  const milieu = (x1 + x2) / 2;
  return svg("path", { class: "schema__lien", d: `M${x1},${y1} C${milieu},${y1} ${milieu},${y2} ${x2},${y2}` });
}

// Jauge coût / budget : pleine à 100 %, rouge au-delà.
function jauge(noeud) {
  const largeurUtile = LARGEUR - 24;
  const fond = svg("rect", { class: "schema__jauge-fond", x: 12, y: HAUTEUR - 14, width: largeurUtile, height: 5, rx: 2 });
  if (!noeud.budget) return [fond];
  const part = Math.min(noeud.cout / noeud.budget, 1);
  const classe = noeud.cout > noeud.budget ? "schema__jauge schema__jauge--depasse" : "schema__jauge";
  return [fond, svg("rect", { class: classe, x: 12, y: HAUTEUR - 14, width: Math.max(part * largeurUtile, 0), height: 5, rx: 2 })];
}

function dessinerNoeud(noeud) {
  const classes = ["schema__noeud"];
  if (noeud.racine) classes.push("schema__noeud--racine");
  if (noeud.depassement) classes.push("schema__noeud--alerte");
  const budget = noeud.budget === null ? "budget non défini" : formatMontant(noeud.budget);
  const infobulle = [
    noeud.racine ? `${noeud.nom} (projet)` : `${noeud.nom} (${noeud.code})`,
    `Coût HT cumulé : ${formatMontant(noeud.cout)}`,
    `Budget HT : ${budget}${noeud.verrouille ? " (verrouillé)" : ""}`,
    noeud.depassement ? `Sous-ensembles verrouillés et composants propres au-delà de ce budget : ${formatMontant(noeud.depassement)}` : null,
  ].filter(Boolean).join("\n");
  const ouvrir = noeud.racine ? null : () => naviguer(`/ensembles/${noeud.code}`);
  return svg(
    "g",
    {
      class: classes.join(" "),
      transform: `translate(${noeud.x},${noeud.y})`,
      tabindex: ouvrir ? "0" : null,
      role: ouvrir ? "link" : null,
      onclick: ouvrir,
      onkeydown: ouvrir ? (e) => e.key === "Enter" && ouvrir() : null,
    },
    svg("title", {}, infobulle),
    svg("rect", { class: "schema__cadre", width: LARGEUR, height: HAUTEUR, rx: 6 }),
    svg("text", { class: "schema__nom", x: 12, y: 21 }, tronquer(noeud.nom, LONGUEUR_NOM)),
    svg(
      "text",
      { class: "schema__code", x: 12, y: 38 },
      noeud.racine ? "projet" : noeud.code,
    ),
    noeud.verrouille
      ? svg("g", { class: "schema__cadenas", transform: `translate(${LARGEUR - 26},8) scale(0.75)` }, TRACE_CADENAS.map((d) => svg("path", { d })))
      : null,
    svg("text", { class: "schema__montants", x: 12, y: 55 }, `${formatMontant(noeud.cout)} / ${budget}`),
    jauge(noeud),
  );
}

export function vueSchema(arbre) {
  const racine = {
    code: null,
    racine: true,
    nom: arbre.racine.nom || "Projet",
    cout: arbre.racine.cout_ht,
    budget: arbre.racine.budget_ht,
    depassement: arbre.racine.depassement_verrouille_ht,
  };
  const noeuds = arbre.ensembles.map((e) => ({
    code: e.code,
    parent: e.parent_code,
    nom: e.nom,
    cout: e.cumul.cout_ht,
    budget: e.budget_ht,
    verrouille: Boolean(e.budget_verrouille),
    depassement: e.depassement_verrouille_ht,
  }));
  // L'API renvoie les ensembles dans l'ordre de l'arbre : les frères restent triés.
  const enfantsDe = new Map([[null, []]]);
  const connus = new Set(noeuds.map((n) => n.code));
  for (const n of noeuds) {
    const parent = connus.has(n.parent) ? n.parent : null;
    if (!enfantsDe.has(parent)) enfantsDe.set(parent, []);
    enfantsDe.get(parent).push(n);
  }
  const nbLignes = placer(racine, enfantsDe);
  const profondeur = Math.max(0, ...arbre.ensembles.map((e) => e.niveau));
  const largeur = 2 * MARGE + (profondeur + 1) * LARGEUR + profondeur * ECART_COLONNES;
  const hauteur = 2 * MARGE + nbLignes * HAUTEUR + (nbLignes - 1) * ECART_LIGNES;

  const liens = [];
  for (const parent of [racine, ...noeuds]) {
    for (const enfant of enfantsDe.get(parent.code) ?? []) liens.push(lien(parent, enfant));
  }
  const dessin = svg(
    "svg",
    { class: "schema__dessin", width: largeur, height: hauteur, viewBox: `0 0 ${largeur} ${hauteur}`, role: "img", "aria-label": "Schéma de l'arborescence des ensembles" },
    liens,
    [racine, ...noeuds].map(dessinerNoeud),
  );
  return el(
    "section",
    { class: "panneau" },
    el(
      "p",
      { class: "texte-doux texte-petit" },
      "Chaque nœud montre son coût HT cumulé (lui et ses sous-ensembles) face à son budget ; la jauge passe au rouge en cas de dépassement, le cadre quand les sous-ensembles verrouillés et les composants propres dépassent le budget du parent. Survoler un nœud pour le détail, cliquer pour ouvrir l'ensemble.",
    ),
    el("div", { class: "schema" }, dessin),
  );
}
