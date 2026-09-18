// Tableau de bord (#/) : lecture de la traçabilité, sans saisie.

import { api } from "../api.js";
import { formatEcart, formatMontant, formatNombre, formatPourcent, libelle } from "../format.js";
import { anneau, histogrammeHorizontal } from "../graphiques.js";
import { lienRoute } from "../router.js";
import { couleurBloc, couleurCss, el, largeur, rangsBlocs } from "../ui.js";

const MODES_APPRO = ["Achat", "Stock ecole", "Fourni PFM", "Fourni CEA", "Fabrication PFM"];

function tuile(titre, valeur, etat = "neutre", precision = "") {
  return el(
    "div",
    { class: `tuile tuile--${etat}` },
    el("div", { class: "tuile__titre" }, titre),
    el("div", { class: "tuile__valeur" }, valeur),
    precision ? el("div", { class: "tuile__precision" }, precision) : null,
  );
}

function etatConsommation(pourcent) {
  if (pourcent === null) return "neutre";
  if (pourcent > 100) return "alerte";
  return pourcent > 90 ? "surveiller" : "conforme";
}

function tuiles(p) {
  const aBudget = p.budget_ht !== null;
  return el(
    "section",
    { class: "tuiles" },
    tuile("Coût estimé HT", formatMontant(p.cout_ht), "neutre", `TTC ${formatMontant(p.cout_ttc)}`),
    tuile(
      "Écart au budget",
      aBudget ? formatEcart(p.ecart_budget_ht) : "Budget non défini",
      !aBudget ? "neutre" : p.ecart_budget_ht > 0 ? "alerte" : "conforme",
      aBudget ? formatPourcent(p.ecart_budget_pct) : "",
    ),
    tuile(
      "Budget consommé",
      aBudget ? formatPourcent(p.consommation_pct) : "—",
      etatConsommation(p.consommation_pct),
      aBudget ? `sur ${formatMontant(p.budget_ht)}` : "",
    ),
    tuile(
      "Lignes à chiffrer",
      formatNombre(p.nb_a_chiffrer),
      p.nb_a_chiffrer > 0 ? "surveiller" : "conforme",
      "achats sans prix relevé",
    ),
    tuile("Montant engagé HT", formatMontant(p.montant_engage_ht), "neutre", "commandes passées"),
    tuile(
      "Reste à engager HT",
      aBudget ? formatMontant(p.reste_a_engager_ht) : "—",
      aBudget && p.reste_a_engager_ht < 0 ? "alerte" : "neutre",
      "budget − engagé",
    ),
  );
}

function jauge(p) {
  const section = el("section", { class: "panneau" }, el("h2", {}, "Budget consommé"));
  if (p.budget_ht === null || p.budget_ht <= 0) {
    section.append(el("p", { class: "texte-doux" }, "Aucun budget n'est défini dans les paramètres."));
    return section;
  }
  // L'échelle couvre le plus grand des deux : budget ou coût estimé.
  const echelle = Math.max(p.budget_ht, p.cout_ht);
  const dansBudget = largeur(el("div", { class: "jauge__dans-budget" }), (Math.min(p.cout_ht, p.budget_ht) / echelle) * 100);
  const depassement = el("div", { class: "jauge__depassement" });
  largeur(depassement, (Math.max(0, p.cout_ht - p.budget_ht) / echelle) * 100);
  const trait = el("div", { class: "jauge__trait" });
  trait.style.left = `${(p.budget_ht / echelle) * 100}%`;
  section.append(
    el("div", { class: "jauge" }, dansBudget, depassement, trait),
    el(
      "div",
      { class: "jauge__legende" },
      el("span", {}, `Estimé : ${formatMontant(p.cout_ht)}`),
      el("span", {}, `Budget (100 %) : ${formatMontant(p.budget_ht)}`),
      p.cout_ht > p.budget_ht
        ? el("span", { class: "texte-alerte" }, `Dépassement : ${formatEcart(p.ecart_budget_ht)}`)
        : null,
    ),
  );
  return section;
}

function panneauGraphique(titre, classe) {
  const canvas = el("canvas");
  return { section: el("section", { class: "panneau" }, el("h2", {}, titre), el("div", { class: classe }, canvas)), canvas };
}

function tableTop(composants) {
  const lignes = composants.slice(0, 10).map((c) =>
    el(
      "tr",
      {},
      el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { q: c.id }) }, c.id)),
      el("td", {}, c.designation),
      el("td", {}, c.bloc_code),
      el("td", { class: "nombre" }, formatNombre(c.qte_a_acheter)),
      el("td", { class: "nombre" }, formatMontant(c.pu_ht)),
      el("td", { class: "nombre" }, formatMontant(c.total_ht)),
    ),
  );
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Les dix composants les plus coûteux"),
    el(
      "table",
      { class: "table" },
      el(
        "thead",
        {},
        el("tr", {}, ["ID", "Désignation", "Bloc", "Qté", "PU HT", "Total HT"].map((t, i) => el("th", { class: i >= 3 ? "nombre" : "" }, t))),
      ),
      el("tbody", {}, lignes),
    ),
  );
}

function alerte(nombre, texte, lien, informatif = false) {
  const etat = informatif || nombre === 0 ? "neutre" : "alerte";
  return el(
    "li",
    { class: `alerte alerte--${etat}` },
    el("a", { href: lien }, el("span", { class: "alerte__nombre" }, formatNombre(nombre)), " ", texte),
  );
}

function alertes(p, composants) {
  const bloquantsNonCommandes = composants.filter(
    (c) => c.criticite === "Bloquant" && c.avancement === "A commander",
  ).length;
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Alertes"),
    el(
      "ul",
      { class: "alertes" },
      alerte(p.nb_a_chiffrer, "ligne(s) à chiffrer", lienRoute("/composants", { a_chiffrer: 1 })),
      alerte(p.nb_commandes_retard, "commande(s) en retard", lienRoute("/achats", { retard: 1 })),
      alerte(bloquantsNonCommandes, "composant(s) bloquant(s) non commandé(s)", lienRoute("/composants", { criticite: "Bloquant" })),
      alerte(p.nb_composants_ecart_affectation, "composant(s) avec un écart d'affectation", lienRoute("/composants", { ecart_affectation: 1 })),
      alerte(p.nb_composants_non_affectes, "composant(s) non affecté(s) à un ensemble", lienRoute("/composants", { non_affecte: 1 }), true),
    ),
  );
}

export async function afficherTableau(conteneur) {
  const [p, blocs, composants] = await Promise.all([
    api.getPilotage(),
    api.getBlocs(),
    api.getComposants({ tri: "total_ht", ordre: "desc" }),
  ]);
  const rangs = rangsBlocs(blocs);
  const blocsTries = [...blocs].sort((a, b) => b.cout_ht - a.cout_ht);
  const histo = panneauGraphique("Coût HT par bloc fonctionnel", "graphique graphique--barres");
  const donut = panneauGraphique("Composants par mode d'approvisionnement", "graphique graphique--anneau");
  conteneur.replaceChildren(
    el("h1", {}, "Tableau de bord"),
    tuiles(p),
    jauge(p),
    el("div", { class: "grille-2" }, histo.section, alertes(p, composants)),
    el("div", { class: "grille-2" }, tableTop(composants), donut.section),
  );
  histogrammeHorizontal(histo.canvas, {
    libelles: blocsTries.map((b) => b.nom),
    valeurs: blocsTries.map((b) => b.cout_ht),
    couleurs: blocsTries.map((b) => couleurBloc(rangs.get(b.code))),
    formater: formatMontant,
  });
  const comptes = MODES_APPRO.map((mode) => composants.filter((c) => c.mode_appro === mode).length);
  const presents = MODES_APPRO.map((mode, i) => ({ mode, n: comptes[i] })).filter((m) => m.n > 0);
  anneau(donut.canvas, {
    libelles: presents.map((m) => libelle(m.mode)),
    valeurs: presents.map((m) => m.n),
    couleurs: presents.map((m) => couleurCss(`--mode-${MODES_APPRO.indexOf(m.mode) + 1}`)),
    formater: (n) => `${formatNombre(n)} composant${n > 1 ? "s" : ""}`,
  });
}
