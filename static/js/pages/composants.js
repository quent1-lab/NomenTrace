// Écran composants (#/composants) : table filtrable et triable, édition en ligne,
// création et fiche dans un panneau latéral. Filtres, tri et fiche ouverte sont dans l'URL.

import { api } from "../api.js";
import { OPERATIONS, PREFIXE, attribut, attributsActifs, chargerAttributs, ecrireFiltre, formatAttribut, libelleFiltre, lireFiltre, optionsListe, titreAttribut } from "../attributs.js";
import { editerCellule } from "../edition.js";
import { formatEcart, formatMontant, formatNombre, libelle } from "../format.js";
import { fermerPanneau } from "../panneau.js";
import { remplacerRoute } from "../router.js";
import { afficherErreur, classeBloc, el, enregistrerFichier, lienProduit, masquerErreur, rangsBlocs } from "../ui.js";
import { valeursListe } from "../valeurs.js";
import { ouvrirCreation } from "./composants_creation.js";
import { ouvrirFiche } from "./composants_fiche.js";
import { lienFournisseur, statutsFournisseurs } from "./fournisseurs_commun.js";

const FILTRES_TEXTE = ["q", "bloc", "ensemble", "mode_appro", "statut_appro", "statut_choix", "criticite", "fournisseur"];
const FILTRES_CASES = ["a_chiffrer", "non_affecte", "ecart_affectation"];

let etat = null;

// --- Colonnes ------------------------------------------------------------------------------

function celluleAffectee(c) {
  const texte = c.nb_ensembles > 0 ? `${formatNombre(c.qte_affectee)} (${c.nb_ensembles} ens.)` : "0";
  const ecart = c.nb_ensembles > 0 && c.ecart_affectation !== 0;
  if (!ecart) return texte;
  const sens = c.ecart_affectation > 0 ? "de moins" : "de plus";
  return [
    el("span", { class: "pastille", title: `${Math.abs(c.ecart_affectation)} pièce(s) affectée(s) ${sens} que le besoin (${c.qte_besoin})` }),
    texte,
  ];
}

function cellulePuReleve(c) {
  if (c.pu_releve === null) {
    return c.mode_appro === "Achat" ? el("span", { class: "a-chiffrer" }, "à chiffrer") : "—";
  }
  return [formatMontant(c.pu_releve), " ", el("span", { class: "texte-doux" }, c.base_prix_releve)];
}

// `cle` nomme la colonne pour l'export Excel, qui reprend les colonnes dans cet ordre.
const COLONNES = [
  { cle: "id", titre: "ID", tri: "id", classe: "code colonne-fixe", rendu: (c) => c.id },
  { cle: "bloc_code", titre: "Bloc", tri: "bloc_code", rendu: (c) => el("span", { class: `etiquette-bloc ${classeBloc(etat.rangs.get(c.bloc_code) ?? 0)}` }, c.bloc_code) },
  { cle: "fonction", titre: "Fonction", tri: "fonction", classe: "tronque", rendu: (c) => c.fonction, infobulle: (c) => c.fonction },
  { cle: "designation", titre: "Désignation", tri: "designation", classe: "tronque tronque--large", rendu: (c) => c.designation, infobulle: (c) => c.designation },
  { cle: "lien_produit", titre: "", classe: "colonne-lien", rendu: (c) => lienProduit(c.lien_produit), aide: "Page produit" },
  { cle: "ref_fabricant", titre: "Réf fabricant", tri: "ref_fabricant", classe: "tronque", rendu: (c) => c.ref_fabricant ?? "", infobulle: (c) => c.ref_fabricant },
  { cle: "mode_appro", titre: "Mode appro", tri: "mode_appro", rendu: (c) => libelle(c.mode_appro) },
  {
    cle: "fournisseur_nom",
    titre: "Fournisseur",
    tri: "fournisseur_nom",
    classe: "tronque",
    rendu: (c) => lienFournisseur(c.fournisseur_nom, etat.statutsFournisseurs.get(c.fournisseur_nom)),
    edition: { champ: "fournisseur_nom", type: "choix", vide: true, options: () => etat.fournisseurs.map((f) => [f.nom, f.nom]) },
  },
  { cle: "qte_besoin", titre: "Besoin", classe: "nombre", rendu: (c) => formatNombre(c.qte_besoin), edition: { champ: "qte_besoin", type: "entier" } },
  { cle: "qte_rechange", titre: "Rech.", classe: "nombre", rendu: (c) => formatNombre(c.qte_rechange), edition: { champ: "qte_rechange", type: "entier" }, aide: "Quantité de rechange" },
  { cle: "qte_disponible", titre: "Dispo.", classe: "nombre", rendu: (c) => formatNombre(c.qte_disponible), edition: { champ: "qte_disponible", type: "entier" }, aide: "Quantité déjà disponible sans achat (stock existant, prêt…)" },
  { cle: "qte_a_acheter", titre: "À acheter", tri: "qte_a_acheter", classe: "nombre", rendu: (c) => formatNombre(c.qte_a_acheter) },
  { cle: "qte_affectee", titre: "Qté affectée", tri: "qte_affectee", classe: "nombre", rendu: celluleAffectee },
  { cle: "pu_releve", titre: "PU relevé", classe: "nombre", rendu: cellulePuReleve, edition: { champ: "pu_releve", type: "prix" } },
  { cle: "pu_ht", titre: "PU HT", tri: "pu_ht", classe: "nombre", rendu: (c) => formatMontant(c.pu_ht) },
  { cle: "total_ht", titre: "Total HT", tri: "total_ht", classe: "nombre fort", rendu: (c) => formatMontant(c.total_ht) },
  { cle: "statut_choix", titre: "Statut choix", tri: "statut_choix", rendu: (c) => libelle(c.statut_choix) || "—", edition: { champ: "statut_choix", type: "choix", vide: true, options: (courante) => valeursListe("statut_choix", { valeurCourante: courante }) } },
  { cle: "statut_appro", titre: "Statut appro", tri: "statut_appro", rendu: (c) => libelle(c.statut_appro), edition: { champ: "statut_appro", type: "choix", vide: false, options: (courante) => valeursListe("statut_appro", { valeurCourante: courante }) } },
  { cle: "criticite", titre: "Criticité", tri: "criticite", rendu: (c) => libelle(c.criticite) || "—", edition: { champ: "criticite", type: "choix", vide: true, options: (courante) => valeursListe("criticite", { valeurCourante: courante }) } },
  { cle: "avancement", titre: "Avancement", tri: "avancement", rendu: (c) => el("span", { class: `avancement avancement--${c.avancement.replace(/\s/g, "-").toLowerCase()}` }, libelle(c.avancement)) },
];

// Colonnes affichées : les colonnes fixes, puis les attributs choisis (paramètre cols).
function colonnesAttributs() {
  return etat.filtres.cols
    .map((code) => attribut(code))
    .filter((a) => a && a.actif)
    .map((a) => ({
      cle: `${PREFIXE}${a.code}`,
      titre: titreAttribut(a),
      tri: `${PREFIXE}${a.code}`,
      classe: a.type === "nombre" ? "nombre" : "",
      rendu: (c) => formatAttribut(a, c.attributs?.[a.code]),
      aide: "Caractéristique : se modifie dans la fiche",
    }));
}

function colonnes() {
  return [...COLONNES, ...colonnesAttributs()];
}

// --- URL et filtres -------------------------------------------------------------------------

function lireFiltres(parametres) {
  const filtres = { tri: parametres.get("tri") || "id", ordre: parametres.get("ordre") || "asc" };
  for (const cle of FILTRES_TEXTE) filtres[cle] = parametres.get(cle) || "";
  for (const cle of FILTRES_CASES) filtres[cle] = ["1", "true"].includes(parametres.get(cle));
  filtres.attr = parametres.getAll("attr");
  filtres.cols = (parametres.get("cols") || "").split(",").filter(Boolean);
  return filtres;
}

function parametresUrl() {
  const p = {};
  for (const cle of FILTRES_TEXTE) if (etat.filtres[cle]) p[cle] = etat.filtres[cle];
  for (const cle of FILTRES_CASES) if (etat.filtres[cle]) p[cle] = 1;
  if (etat.filtres.tri !== "id") p.tri = etat.filtres.tri;
  if (etat.filtres.ordre !== "asc") p.ordre = etat.filtres.ordre;
  if (etat.filtres.attr.length) p.attr = etat.filtres.attr;
  if (etat.filtres.cols.length) p.cols = etat.filtres.cols.join(",");
  if (etat.ficheOuverte) p.fiche = etat.ficheOuverte;
  return p;
}

function parametresApi() {
  const p = { tri: etat.filtres.tri, ordre: etat.filtres.ordre };
  for (const cle of FILTRES_TEXTE) if (etat.filtres[cle]) p[cle] = etat.filtres[cle];
  for (const cle of FILTRES_CASES) if (etat.filtres[cle]) p[cle] = "true";
  if (etat.filtres.attr.length) p.attr = etat.filtres.attr;
  return p;
}

function majUrl() {
  remplacerRoute("/composants", parametresUrl());
}

function changerFiltre(cle, valeur) {
  etat.filtres[cle] = valeur;
  majUrl();
  rechargerListe();
}

function selectFiltre(cle, libelleVide, options) {
  const select = el("select", { class: "filtre", "aria-label": libelleVide, onchange: (e) => changerFiltre(cle, e.target.value) });
  select.append(el("option", { value: "" }, libelleVide));
  for (const [code, texte] of options) select.append(el("option", { value: code, selected: etat.filtres[cle] === code }, texte));
  return select;
}

function caseFiltre(cle, texte) {
  return el(
    "label",
    { class: "filtre-case" },
    el("input", { type: "checkbox", checked: etat.filtres[cle], onchange: (e) => changerFiltre(cle, e.target.checked) }),
    texte,
  );
}

function barreFiltres() {
  let minuterie = null;
  const recherche = el("input", {
    class: "filtre filtre--recherche",
    type: "search",
    placeholder: "Rechercher (ID, désignation, référence…)",
    value: etat.filtres.q,
    oninput: (e) => {
      clearTimeout(minuterie);
      minuterie = setTimeout(() => changerFiltre("q", e.target.value.trim()), 300);
    },
  });
  // Les filtres proposent aussi les valeurs désactivées : des composants peuvent les porter.
  const tousLibelles = (liste) => valeursListe(liste, { inclureInactives: true });
  return el(
    "div",
    { class: "filtres" },
    recherche,
    selectFiltre("bloc", "Tous les blocs", etat.blocs.map((b) => [b.code, `${b.code} — ${b.nom}`])),
    selectFiltre("ensemble", "Tous les ensembles", etat.ensembles.map((e) => [e.code, `${e.code} — ${e.nom}`])),
    selectFiltre("mode_appro", "Tous les modes d'appro", tousLibelles("mode_appro")),
    selectFiltre("statut_appro", "Tous les statuts d'appro", tousLibelles("statut_appro")),
    selectFiltre("statut_choix", "Tous les statuts de choix", tousLibelles("statut_choix")),
    selectFiltre("criticite", "Toutes les criticités", tousLibelles("criticite")),
    selectFiltre("fournisseur", "Tous les fournisseurs", etat.fournisseurs.map((f) => [f.nom, f.nom])),
    caseFiltre("a_chiffrer", "À chiffrer uniquement"),
    caseFiltre("non_affecte", "Non affecté à un ensemble"),
    etat.filtres.ecart_affectation ? caseFiltre("ecart_affectation", "Écart d'affectation") : null,
    el("button", { type: "button", class: "bouton bouton--discret", onclick: effacerFiltres }, "Tout effacer"),
  );
}

function effacerFiltres() {
  const { tri, ordre, cols } = etat.filtres;
  etat.filtres = lireFiltres(new URLSearchParams());
  Object.assign(etat.filtres, { tri, ordre, cols });
  majUrl();
  etat.zoneFiltres.replaceWith((etat.zoneFiltres = barreFiltres()));
  etat.zoneAttributs.replaceWith((etat.zoneAttributs = barreAttributs()));
  rechargerListe();
}

// --- Caractéristiques : filtres et colonnes d'attributs -----------------------------------------

function changerFiltresAttributs(filtres) {
  etat.filtres.attr = filtres;
  majUrl();
  etat.zoneAttributs.replaceWith((etat.zoneAttributs = barreAttributs()));
  rechargerListe();
}

function changerColonnes(cols) {
  etat.filtres.cols = cols;
  if (etat.filtres.tri.startsWith(PREFIXE) && !cols.includes(etat.filtres.tri.slice(PREFIXE.length))) {
    etat.filtres.tri = "id";
    etat.filtres.ordre = "asc";
  }
  majUrl();
  etat.table.replaceChildren(entete(), etat.corps, etat.pied);
  rechargerListe();
}

// Saisie de la valeur selon le type et l'opération choisis.
function champsValeur(a, operation) {
  if (operation === "vide" || operation === "renseigne") return [];
  if (operation === "entre") {
    return [
      el("input", { class: "filtre filtre--court", type: "text", name: "min", placeholder: "min", "aria-label": "Minimum" }),
      el("input", { class: "filtre filtre--court", type: "text", name: "max", placeholder: "max", "aria-label": "Maximum" }),
    ];
  }
  if (a.type === "liste" || a.type === "booleen") {
    const options = a.type === "booleen" ? [["1", "Oui"], ["0", "Non"]] : optionsListe(a, null, { inclureInactives: true });
    return [el("select", { class: "filtre", name: "valeur", "aria-label": "Valeur" }, options.map(([code, texte]) => el("option", { value: code }, texte)))];
  }
  return [el("input", { class: "filtre", type: "text", name: "valeur", placeholder: a.unite ? `valeur (${a.unite})` : "valeur", "aria-label": "Valeur" })];
}

function formulaireFiltreAttribut(actifs) {
  const choixAttribut = el("select", { class: "filtre", "aria-label": "Caractéristique" }, actifs.map((a) => el("option", { value: a.code }, a.libelle)));
  const choixOperation = el("select", { class: "filtre", "aria-label": "Condition" });
  const zoneValeur = el("span", { class: "actions" });
  const majOperations = () => {
    const a = attribut(choixAttribut.value);
    const operations = Object.entries(OPERATIONS).filter(([op]) => op !== "entre" || a.type === "nombre");
    choixOperation.replaceChildren(...operations.map(([op, texte]) => el("option", { value: op }, texte)));
    majValeur();
  };
  const majValeur = () => zoneValeur.replaceChildren(...champsValeur(attribut(choixAttribut.value), choixOperation.value));
  choixAttribut.addEventListener("change", majOperations);
  choixOperation.addEventListener("change", majValeur);
  const formulaire = el("form", { class: "actions" }, choixAttribut, choixOperation, zoneValeur, el("button", { type: "submit", class: "bouton bouton--discret" }, "Filtrer"));
  formulaire.addEventListener("submit", (e) => {
    e.preventDefault();
    const lu = (nom) => formulaire.querySelector(`[name="${nom}"]`)?.value.trim() ?? "";
    const filtre = { code: choixAttribut.value, operation: choixOperation.value, valeur: lu("valeur"), min: lu("min"), max: lu("max") };
    if (filtre.operation === "egal" && !filtre.valeur) return afficherErreur("Saisir la valeur recherchée.");
    if (filtre.operation === "entre" && !filtre.min && !filtre.max) return afficherErreur("Saisir au moins une borne.");
    changerFiltresAttributs([...etat.filtres.attr, ecrireFiltre(filtre)]);
  });
  majOperations();
  return formulaire;
}

function choixColonnes(actifs) {
  const zone = el("div", { class: "choix-colonnes", hidden: true });
  for (const a of actifs) {
    const coche = el("input", { type: "checkbox", checked: etat.filtres.cols.includes(a.code) });
    coche.addEventListener("change", () => {
      const cols = coche.checked ? [...etat.filtres.cols, a.code] : etat.filtres.cols.filter((c) => c !== a.code);
      changerColonnes(actifs.map((x) => x.code).filter((c) => cols.includes(c)));
    });
    zone.append(el("label", { class: "filtre-case" }, coche, titreAttribut(a)));
  }
  return zone;
}

function barreAttributs() {
  const actifs = attributsActifs();
  if (!actifs.length && !etat.filtres.attr.length) return el("div");
  const pastilles = etat.filtres.attr.map((texte, rang) =>
    el(
      "span",
      { class: "pastille-filtre" },
      libelleFiltre(lireFiltre(texte)),
      el("button", { type: "button", class: "bouton-icone", title: "Retirer ce filtre", onclick: () => changerFiltresAttributs(etat.filtres.attr.filter((_, i) => i !== rang)) }, "×"),
    ),
  );
  const colonnesChoisies = choixColonnes(actifs);
  const boutonColonnes = el(
    "button",
    { type: "button", class: "bouton bouton--discret", title: "Afficher des caractéristiques en colonnes", onclick: () => (colonnesChoisies.hidden = !colonnesChoisies.hidden) },
    `Colonnes (${etat.filtres.cols.length})`,
  );
  return el(
    "div",
    {},
    el("div", { class: "filtres-attributs" }, el("span", { class: "texte-doux" }, "Caractéristiques :"), actifs.length ? formulaireFiltreAttribut(actifs) : null, pastilles, actifs.length ? boutonColonnes : null),
    colonnesChoisies,
  );
}

// --- Rendu de la table ----------------------------------------------------------------------

function trier(colonne) {
  if (!colonne.tri) return;
  if (etat.filtres.tri === colonne.tri) {
    etat.filtres.ordre = etat.filtres.ordre === "asc" ? "desc" : "asc";
  } else {
    etat.filtres.tri = colonne.tri;
    etat.filtres.ordre = "asc";
  }
  majUrl();
  etat.table.querySelector("thead").replaceWith(entete());
  rechargerListe();
}

function entete() {
  return el(
    "thead",
    {},
    el(
      "tr",
      {},
      colonnes().map((col) => {
        const actif = col.tri && etat.filtres.tri === col.tri;
        const fleche = actif ? (etat.filtres.ordre === "asc" ? " ▲" : " ▼") : "";
        return el(
          "th",
          {
            class: [col.classe ?? "", col.tri ? "triable" : "", col.edition ? "editable-entete" : ""].join(" "),
            title: col.aide ?? (col.edition ? "Modifiable : cliquer sur la cellule" : null),
            onclick: () => trier(col),
          },
          col.titre + fleche,
        );
      }),
    ),
  );
}

function ligne(c) {
  const tr = el("tr", { "data-id": c.id, class: c.id === etat.ficheOuverte ? "ligne--selection" : "", onclick: () => ouvrirFicheComposant(c.id) });
  for (const col of colonnes()) {
    const td = el("td", { class: [col.classe ?? "", col.edition ? "editable" : ""].join(" "), title: col.infobulle?.(c) ?? null }, col.rendu(c));
    if (col.edition) {
      td.addEventListener("click", (e) => {
        e.stopPropagation();
        editerCellule(td, col.edition, etat.parId.get(c.id), {
          enregistrer: (modifs) => enregistrerModif(c.id, modifs),
          terminer: () => rendreLigne(c.id),
        });
      });
    }
    tr.append(td);
  }
  return tr;
}

function rendreLigne(id) {
  const ancienne = etat.corps.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
  // Une autre cellule de la ligne est encore en cours d'édition : elle rafraîchira la ligne.
  if (!ancienne || ancienne.querySelector(".cellule--edition")) return;
  ancienne.replaceWith(ligne(etat.parId.get(id)));
}

function rendreCorps() {
  etat.corps.replaceChildren(...etat.composants.map(ligne));
  rendrePied();
}

function rendrePied() {
  const total = etat.composants.reduce((somme, c) => somme + (c.total_ht ?? 0), 0);
  etat.pied.replaceChildren(
    el(
      "tr",
      {},
      el("td", { colspan: COLONNES.length - 6, class: "texte-doux" }, `${etat.composants.length} composant(s) affiché(s)`),
      el("td", { class: "nombre" }, "Total HT"),
      el("td", { class: "nombre fort" }, formatMontant(total)),
      el("td", { colspan: 4 + colonnesAttributs().length }),
    ),
  );
  etat.compteur.textContent = `${etat.composants.length} résultat(s)`;
}

// --- Indicateurs en tête d'écran ----------------------------------------------------------

async function rendreIndicateurs() {
  const p = await api.getPilotage();
  const ecartClasse = p.ecart_budget_ht > 0 ? "texte-alerte" : "texte-conforme";
  etat.indicateurs.replaceChildren(
    el("span", {}, "Coût estimé HT ", el("strong", {}, formatMontant(p.cout_ht))),
    p.budget_ht !== null ? el("span", {}, "Écart au budget ", el("strong", { class: ecartClasse }, formatEcart(p.ecart_budget_ht))) : null,
    el("span", {}, "À chiffrer ", el("strong", { class: p.nb_a_chiffrer ? "texte-surveiller" : "" }, formatNombre(p.nb_a_chiffrer))),
    el("span", {}, "Composants ", el("strong", {}, formatNombre(p.nb_composants))),
  );
}

// --- Données ---------------------------------------------------------------------------------

let numeroRequete = 0;

async function rechargerListe() {
  // Seule la réponse à la dernière requête est affichée (saisie rapide dans la recherche).
  const numero = ++numeroRequete;
  const composants = await api.getComposants(parametresApi());
  if (numero !== numeroRequete) return;
  etat.parId = new Map(composants.map((c) => [c.id, c]));
  etat.composants = composants;
  rendreCorps();
}

async function enregistrerModif(id, modifs) {
  const maj = await api.patchComposant(id, modifs);
  etat.parId.set(id, maj);
  etat.composants = etat.composants.map((c) => (c.id === id ? maj : c));
  rendrePied();
  await rendreIndicateurs();
}

async function apresChangement() {
  await Promise.all([rechargerListe(), rendreIndicateurs()]);
}

function ouvrirFicheComposant(id) {
  etat.ficheOuverte = id;
  majUrl();
  etat.corps.querySelectorAll(".ligne--selection").forEach((tr) => tr.classList.remove("ligne--selection"));
  etat.corps.querySelector(`tr[data-id="${CSS.escape(id)}"]`)?.classList.add("ligne--selection");
  ouvrirFiche(id, {
    ensembles: etat.ensembles,
    fournisseurs: etat.fournisseurs,
    surChangement: apresChangement,
    surFermeture: () => {
      etat.ficheOuverte = null;
      majUrl();
      etat.corps.querySelectorAll(".ligne--selection").forEach((tr) => tr.classList.remove("ligne--selection"));
    },
  });
}

// Classeur de la liste affichée : mêmes filtres, même tri, mêmes colonnes.
async function exporterListe(evenement) {
  const bouton = evenement.currentTarget;
  bouton.disabled = true;
  try {
    enregistrerFichier(await api.exporterComposants(parametresApi(), colonnes().map((col) => col.cle)));
    masquerErreur();
  } catch (erreur) {
    afficherErreur(erreur);
  } finally {
    bouton.disabled = false;
  }
}

function ouvrirCreationComposant() {
  ouvrirCreation({
    blocs: etat.blocs,
    fournisseurs: etat.fournisseurs,
    blocInitial: etat.filtres.bloc,
    surCree: async (composant) => {
      await apresChangement();
      ouvrirFicheComposant(composant.id);
    },
  });
}

export async function afficherComposants(conteneur, parametres) {
  fermerPanneau({ silencieux: true });
  const [blocs, fournisseurs, ensembles] = await Promise.all([api.getBlocs(), api.getFournisseurs(), api.getEnsembles(), chargerAttributs()]);
  etat = {
    filtres: lireFiltres(parametres),
    blocs,
    fournisseurs,
    statutsFournisseurs: statutsFournisseurs(fournisseurs),
    ensembles,
    rangs: rangsBlocs(blocs),
    composants: [],
    parId: new Map(),
    ficheOuverte: parametres.get("fiche") || null,
    corps: el("tbody"),
    pied: el("tfoot"),
    compteur: el("span", { class: "compteur" }),
    indicateurs: el("div", { class: "indicateurs" }),
  };
  etat.zoneFiltres = barreFiltres();
  etat.zoneAttributs = barreAttributs();
  etat.table = el("table", { class: "table table--dense table--composants" }, entete(), etat.corps, etat.pied);
  conteneur.replaceChildren(
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, "Composants"),
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "bouton bouton--discret", title: "Classeur Excel de la liste affichée", onclick: exporterListe }, "Exporter"),
        el("button", { type: "button", class: "bouton", onclick: ouvrirCreationComposant }, "+ Ajouter un composant"),
      ),
    ),
    etat.indicateurs,
    etat.zoneFiltres,
    etat.zoneAttributs,
    el("div", { class: "barre-resultats" }, etat.compteur, el("span", { class: "texte-doux" }, "Cliquer sur une ligne pour ouvrir la fiche ; les colonnes soulignées se modifient sur place.")),
    el("div", { class: "table-defilante" }, etat.table),
  );
  await Promise.all([rechargerListe(), rendreIndicateurs()]);
  if (etat.ficheOuverte) ouvrirFicheComposant(etat.ficheOuverte);
  if (parametres.get("nouveau")) {
    majUrl();
    ouvrirCreationComposant();
  }
}
