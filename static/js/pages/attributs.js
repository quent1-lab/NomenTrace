// Écran d'analyse des attributs (#/attributs) : pour un attribut choisi, la répartition des
// composants par valeur (nombre, pièces, coût HT), « non renseigné » compris. Générique :
// la tension n'y a pas de traitement particulier. Cliquer une valeur ouvre l'écran
// Composants filtré sur elle.

import { api } from "../api.js";
import { chargerAttributs, ecrireFiltre, formatAttribut, titreAttribut, tousLesAttributs } from "../attributs.js";
import { formatMontant, formatNombre, formatPourcent } from "../format.js";
import { lienRoute, remplacerRoute } from "../router.js";
import { afficherErreur, el, largeur } from "../ui.js";
import { valeursListe } from "../valeurs.js";

const FILTRES = ["bloc", "ensemble", "mode_appro"];

let etat = null;

function select(nom, libelleVide, options, surChangement) {
  const champ = el("select", { class: "filtre", "aria-label": libelleVide, onchange: (e) => surChangement(e.target.value) });
  if (libelleVide !== null) champ.append(el("option", { value: "" }, libelleVide));
  for (const [code, texte] of options) champ.append(el("option", { value: code, selected: etat.filtres[nom] === code }, texte));
  return champ;
}

function parametresUrl() {
  return Object.fromEntries(Object.entries(etat.filtres).filter(([, v]) => v));
}

// Lien vers la liste des composants filtrée sur une valeur, avec les mêmes filtres.
function lienComposants(filtreAttribut) {
  const a = etat.attribut;
  const parametres = { attr: [filtreAttribut], cols: a.code };
  for (const cle of FILTRES) if (etat.filtres[cle]) parametres[cle] = etat.filtres[cle];
  return lienRoute("/composants", parametres);
}

function valeurFiltre(valeur) {
  // Un nombre s'écrit avec un point : c'est le serveur qui le relit.
  return typeof valeur === "number" ? String(valeur) : valeur;
}

function ligne(texte, chiffres, total, lien) {
  const part = total ? (chiffres.nb_composants * 100) / total : 0;
  return el(
    "tr",
    {},
    el("td", {}, el("a", { href: lien }, texte)),
    el("td", { class: "nombre" }, formatNombre(chiffres.nb_composants)),
    // La mise en ligne barre + pourcentage se fait dans un bloc interne : une cellule de
    // tableau en display: flex perd sa bordure et son alignement avec la ligne.
    el("td", {}, el("div", { class: "cellule-part" }, el("div", { class: "barre" }, largeur(el("div", { class: "barre__remplissage" }), part)), el("span", { class: "texte-doux texte-petit" }, formatPourcent(part, 0)))),
    el("td", { class: "nombre" }, formatNombre(chiffres.nb_pieces)),
    el("td", { class: "nombre" }, formatMontant(chiffres.cout_ht)),
  );
}

function filtresApi() {
  return Object.fromEntries(FILTRES.map((cle) => [cle, etat.filtres[cle]]));
}

// --- Options avancées (attribut de type nombre) : somme ou moyenne sur les composants filtrés --

const CALCULS = { somme: "Somme", moyenne: "Moyenne" };

// Au plus trois décimales, sans zéros inutiles.
function arrondi(valeur) {
  return valeur === null || valeur === undefined ? null : Math.round(valeur * 1000) / 1000;
}

async function rendreCalcul() {
  const a = etat.attribut;
  const zone = etat.zoneAvancee;
  if (!a || a.type !== "nombre") {
    zone.replaceChildren();
    return;
  }
  const bascule = el(
    "button",
    { type: "button", class: "bouton-lien", "aria-expanded": String(etat.avance.ouvert), onclick: () => {
      etat.avance.ouvert = !etat.avance.ouvert;
      rendreCalcul().catch(afficherErreur);
    } },
    `Options avancées ${etat.avance.ouvert ? "▾" : "▸"}`,
  );
  if (!etat.avance.ouvert) {
    zone.replaceChildren(bascule);
    return;
  }
  const c = await api.getCalculAttribut(a.code, filtresApi());
  const choixCalcul = el("select", { class: "filtre", "aria-label": "Calcul" }, Object.entries(CALCULS).map(([code, texte]) => el("option", { value: code, selected: code === etat.avance.calcul }, texte)));
  choixCalcul.addEventListener("change", () => {
    etat.avance.calcul = choixCalcul.value;
    rendreCalcul().catch(afficherErreur);
  });
  const ponderer = el("input", { type: "checkbox", checked: etat.avance.ponderer });
  ponderer.addEventListener("change", () => {
    etat.avance.ponderer = ponderer.checked;
    rendreCalcul().catch(afficherErreur);
  });
  const cle = `${etat.avance.calcul}${etat.avance.ponderer ? "_ponderee" : ""}`;
  const valeur = arrondi(c[cle]);
  const quantite = c.quantite === "affectee" ? "quantité affectée à l'ensemble choisi" : "quantité de besoin";
  const detail = [
    `${formatNombre(c.nb_renseignes)} composant(s)`,
    etat.avance.ponderer ? `${formatNombre(c.nb_pieces)} pièce(s), selon la ${quantite}` : "chacun compté une fois",
  ];
  if (c.nb_non_renseignes) detail.push(`${formatNombre(c.nb_non_renseignes)} composant(s) sans valeur, non compté(s)`);
  zone.replaceChildren(
    bascule,
    el(
      "div",
      { class: "panneau panneau--encart options-avancees" },
      el("div", { class: "filtres" }, choixCalcul, el("label", { class: "filtre-case" }, ponderer, "Tenir compte du nombre de pièces nécessaires")),
      el(
        "p",
        { class: "resultat-calcul" },
        `${CALCULS[etat.avance.calcul]} — ${a.libelle} : `,
        el("strong", {}, valeur === null ? "—" : formatAttribut(a, valeur)),
      ),
      el("p", { class: "texte-doux texte-petit" }, detail.join(" ; ") + "."),
    ),
  );
}

async function rendreRepartition() {
  if (!etat.attribut) return;
  rendreCalcul().catch(afficherErreur);
  const filtres = filtresApi();
  const donnees = await api.getRepartitionAttribut(etat.attribut.code, filtres);
  const a = etat.attribut;
  const total = donnees.valeurs.reduce((s, v) => s + v.nb_composants, 0) + donnees.non_renseigne.nb_composants;
  const lignes = donnees.valeurs.map((v) =>
    ligne(formatAttribut(a, v.valeur), v, total, lienComposants(ecrireFiltre({ code: a.code, operation: "egal", valeur: valeurFiltre(v.valeur) }))),
  );
  lignes.push(ligne(el("em", {}, "Non renseigné"), donnees.non_renseigne, total, lienComposants(ecrireFiltre({ code: a.code, operation: "vide" }))));
  const somme = (cle) => donnees.valeurs.reduce((s, v) => s + v[cle], 0) + donnees.non_renseigne[cle];
  const distinctes =
    a.type === "nombre" && donnees.valeurs.length
      ? el("p", {}, el("strong", {}, `${donnees.valeurs.length} valeur(s) distincte(s) : `), donnees.valeurs.map((v) => formatAttribut(a, v.valeur)).join(" · "))
      : null;
  etat.zone.replaceChildren(
    distinctes,
    el(
      "table",
      { class: "table table--dense table--repartition" },
      el("thead", {}, el("tr", {}, el("th", {}, titreAttribut(a)), el("th", { class: "nombre" }, "Composants"), el("th", {}, "Part"), el("th", { class: "nombre", title: "Somme des quantités de besoin" }, "Pièces"), el("th", { class: "nombre" }, "Coût HT"))),
      el("tbody", {}, lignes),
      el("tfoot", {}, el("tr", {}, el("td", { class: "fort" }, "Total"), el("td", { class: "nombre fort" }, formatNombre(total)), el("td"), el("td", { class: "nombre fort" }, formatNombre(somme("nb_pieces"))), el("td", { class: "nombre fort" }, formatMontant(somme("cout_ht"))))),
    ),
    el("p", { class: "texte-doux texte-petit" }, "Composants non archivés. Cliquer une valeur ouvre la liste des composants filtrée sur elle, avec la caractéristique en colonne."),
  );
}

function changer(cle, valeur) {
  etat.filtres[cle] = valeur;
  if (cle === "attribut") etat.attribut = tousLesAttributs().find((a) => a.code === valeur) ?? null;
  remplacerRoute("/attributs", parametresUrl());
  rendreRepartition().catch(afficherErreur);
}

export async function afficherAttributs(conteneur, parametres) {
  const [attributs, blocs, ensembles] = await Promise.all([chargerAttributs(), api.getBlocs(), api.getEnsembles()]);
  if (!attributs.length) {
    conteneur.replaceChildren(
      el("h1", {}, "Analyse des attributs"),
      el("p", { class: "texte-doux" }, "Aucun attribut n'est défini. ", el("a", { href: lienRoute("/parametres", { onglet: "attributs" }) }, "Créer un attribut"), " (la tension, par exemple) pour analyser sa répartition."),
    );
    return;
  }
  const demande = parametres.get("attribut");
  const attribut = attributs.find((a) => a.code === demande) ?? attributs.find((a) => a.actif) ?? attributs[0];
  etat = {
    attribut,
    filtres: { attribut: attribut.code, ...Object.fromEntries(FILTRES.map((cle) => [cle, parametres.get(cle) || ""])) },
    zone: el("div"),
    zoneAvancee: el("div", { class: "zone-avancee" }),
    avance: { ouvert: false, calcul: "somme", ponderer: true },
  };
  conteneur.replaceChildren(
    el("h1", {}, "Analyse des attributs"),
    el(
      "div",
      { class: "filtres" },
      select("attribut", null, attributs.map((a) => [a.code, a.actif ? titreAttribut(a) : `${titreAttribut(a)} (désactivé)`]), (v) => changer("attribut", v)),
      select("bloc", "Tous les blocs", blocs.map((b) => [b.code, `${b.code} — ${b.nom}`]), (v) => changer("bloc", v)),
      select("ensemble", "Tous les ensembles", ensembles.map((e) => [e.code, `${e.code} — ${e.nom}`]), (v) => changer("ensemble", v)),
      select("mode_appro", "Tous les modes d'appro", valeursListe("mode_appro", { inclureInactives: true }), (v) => changer("mode_appro", v)),
    ),
    etat.zoneAvancee,
    el("section", { class: "panneau" }, etat.zone),
  );
  remplacerRoute("/attributs", parametresUrl());
  await rendreRepartition();
}
