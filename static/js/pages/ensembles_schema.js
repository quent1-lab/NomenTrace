// Vue « Schéma » de l'écran ensembles : l'arborescence dessinée en SVG, de gauche à droite,
// depuis le nœud du projet. Chaque nœud montre son coût cumulé face à son budget ; un clic
// ouvre le détail de l'ensemble.

import { formatMontant, formatPourcent, libelle } from "../format.js";
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

// Modes de couleur : ce que la jauge et la bande de gauche de chaque nœud racontent.
const MODES = {
  budget: {
    titre: "Écart au budget",
    legende: [["conforme", "dans le budget"], ["alerte", "au-delà du budget"], ["neutre", "sans budget"]],
    etat: (n) => (n.budget ? { part: n.cout / n.budget, niveau: n.cout > n.budget ? "alerte" : "conforme" } : { part: 0, niveau: "neutre" }),
    texte: (n) => `${formatMontant(n.cout)} / ${n.budget === null ? "budget non défini" : formatMontant(n.budget)}`,
  },
  appro: {
    titre: "Avancement d'appro",
    legende: [["conforme", "tout reçu"], ["surveiller", "en partie reçu"], ["alerte", "rien reçu"], ["neutre", "rien à acheter"]],
    etat: (n) => {
      if (!n.aAcheter) return { part: 0, niveau: "neutre" };
      const part = n.recus / n.aAcheter;
      return { part, niveau: part >= 1 ? "conforme" : part > 0 ? "surveiller" : "alerte" };
    },
    texte: (n) => (n.aAcheter ? `${n.recus} / ${n.aAcheter} composant(s) reçu(s)` : "rien à acheter"),
  },
  montage: {
    titre: "Avancement de montage",
    legende: [["conforme", "tout monté"], ["surveiller", "en partie monté"], ["alerte", "rien monté"], ["neutre", "aucune pièce"]],
    etat: (n) => {
      if (n.montagePct === null) return { part: 0, niveau: "neutre" };
      const part = n.montagePct / 100;
      return { part, niveau: part >= 1 ? "conforme" : part > 0 ? "surveiller" : "alerte" };
    },
    texte: (n) => (n.montagePct === null ? "aucune pièce affectée" : `${formatPourcent(n.montagePct, 0)} des pièces montées`),
  },
  statut: {
    titre: "Statut de montage",
    legende: [["neutre", libelle("Non commence")], ["surveiller", libelle("En cours")], ["info", libelle("Monte")], ["conforme", libelle("Valide")]],
    etat: (n) => ({ part: null, niveau: { "En cours": "surveiller", Monte: "info", Valide: "conforme" }[n.statut] ?? "neutre" }),
    texte: (n) => (n.statut ? libelle(n.statut) : ""),
  },
};

let modeCourant = "budget";

// Jauge (pleine à 100 %) et bande de gauche, colorées selon le mode choisi.
function jauge(noeud, mode) {
  const { part, niveau } = MODES[mode].etat(noeud);
  const largeurUtile = LARGEUR - 24;
  const elements = [svg("rect", { class: `schema__bande schema__niveau--${niveau}`, x: 0, y: 0, width: 5, height: HAUTEUR, rx: 2 })];
  if (part === null || noeud.racine) return elements;
  elements.push(svg("rect", { class: "schema__jauge-fond", x: 12, y: HAUTEUR - 14, width: largeurUtile, height: 5, rx: 2 }));
  elements.push(svg("rect", { class: `schema__jauge schema__niveau--${niveau}`, x: 12, y: HAUTEUR - 14, width: Math.max(Math.min(part, 1) * largeurUtile, 0), height: 5, rx: 2 }));
  return elements;
}

function dessinerNoeud(noeud, mode) {
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
    svg("text", { class: "schema__montants", x: 12, y: 55 }, noeud.racine ? MODES.budget.texte(noeud) : MODES[mode].texte(noeud)),
    jauge(noeud, noeud.racine ? "budget" : mode),
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
    recus: e.cumul.nb_composants_recus,
    aAcheter: e.cumul.nb_composants_a_acheter,
    montagePct: e.cumul.avancement_montage_pct,
    statut: e.statut_montage,
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
  const dessiner = () =>
    svg(
      "svg",
      { class: "schema__dessin", width: largeur, height: hauteur, viewBox: `0 0 ${largeur} ${hauteur}`, role: "img", "aria-label": "Schéma de l'arborescence des ensembles" },
      liens,
      [racine, ...noeuds].map((n) => dessinerNoeud(n, modeCourant)),
    );
  const zone = el("div", { class: "schema" }, dessiner());
  const legende = el("div", { class: "schema__legende texte-petit" });
  const majLegende = () =>
    legende.replaceChildren(
      ...MODES[modeCourant].legende.map(([niveau, texte]) => el("span", { class: "schema__legende-item" }, el("span", { class: `schema__pastille schema__niveau--${niveau}` }), texte)),
    );
  const choix = el(
    "select",
    {
      class: "filtre",
      "aria-label": "Couleur des nœuds",
      onchange: (e) => {
        modeCourant = e.target.value;
        zone.replaceChildren(dessiner());
        majLegende();
      },
    },
    Object.entries(MODES).map(([code, m]) => el("option", { value: code, selected: code === modeCourant }, m.titre)),
  );
  majLegende();
  return el(
    "section",
    { class: "panneau" },
    el(
      "p",
      { class: "texte-doux texte-petit" },
      "Chiffres cumulés : chaque nœud compte ses sous-ensembles. Le cadre rouge signale un parent dont les sous-ensembles verrouillés et les composants propres dépassent le budget. Survoler un nœud pour le détail, cliquer pour ouvrir l'ensemble.",
    ),
    el("div", { class: "filtres" }, el("label", { class: "filtre-case" }, "Couleur : ", choix), legende),
    zone,
  );
}
