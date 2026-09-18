// Écran composants (#/composants) : table filtrable et triable, édition en ligne,
// création et fiche dans un panneau latéral. Filtres, tri et fiche ouverte sont dans l'URL.

import { api } from "../api.js";
import { editerCellule } from "../edition.js";
import { formatEcart, formatMontant, formatNombre, libelle } from "../format.js";
import { fermerPanneau } from "../panneau.js";
import { remplacerRoute } from "../router.js";
import { classeBloc, el, rangsBlocs } from "../ui.js";
import {
  CRITICITES,
  MODES_APPRO,
  STATUTS_APPRO,
  STATUTS_CHOIX,
} from "../valeurs.js";
import { ouvrirCreation } from "./composants_creation.js";
import { ouvrirFiche } from "./composants_fiche.js";

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

const COLONNES = [
  { titre: "ID", tri: "id", classe: "code colonne-fixe", rendu: (c) => c.id },
  { titre: "Bloc", tri: "bloc_code", rendu: (c) => el("span", { class: `etiquette-bloc ${classeBloc(etat.rangs.get(c.bloc_code) ?? 0)}` }, c.bloc_code) },
  { titre: "Fonction", tri: "fonction", classe: "tronque", rendu: (c) => c.fonction, infobulle: (c) => c.fonction },
  { titre: "Désignation", tri: "designation", classe: "tronque tronque--large", rendu: (c) => c.designation, infobulle: (c) => c.designation },
  { titre: "Réf fabricant", tri: "ref_fabricant", classe: "tronque", rendu: (c) => c.ref_fabricant ?? "", infobulle: (c) => c.ref_fabricant },
  { titre: "Mode appro", tri: "mode_appro", rendu: (c) => libelle(c.mode_appro) },
  {
    titre: "Fournisseur",
    tri: "fournisseur_nom",
    classe: "tronque",
    rendu: (c) => c.fournisseur_nom ?? "—",
    edition: { champ: "fournisseur_nom", type: "choix", vide: true, options: () => etat.fournisseurs.map((f) => [f.nom, f.nom]) },
  },
  { titre: "Besoin", classe: "nombre", rendu: (c) => formatNombre(c.qte_besoin), edition: { champ: "qte_besoin", type: "entier" } },
  { titre: "Rech.", classe: "nombre", rendu: (c) => formatNombre(c.qte_rechange), edition: { champ: "qte_rechange", type: "entier" }, aide: "Quantité de rechange" },
  { titre: "École", classe: "nombre", rendu: (c) => formatNombre(c.qte_dispo_ecole), edition: { champ: "qte_dispo_ecole", type: "entier" }, aide: "Quantité disponible à l'école" },
  { titre: "À acheter", tri: "qte_a_acheter", classe: "nombre", rendu: (c) => formatNombre(c.qte_a_acheter) },
  { titre: "Qté affectée", tri: "qte_affectee", classe: "nombre", rendu: celluleAffectee },
  { titre: "PU relevé", classe: "nombre", rendu: cellulePuReleve, edition: { champ: "pu_releve", type: "prix" } },
  { titre: "PU HT", tri: "pu_ht", classe: "nombre", rendu: (c) => formatMontant(c.pu_ht) },
  { titre: "Total HT", tri: "total_ht", classe: "nombre fort", rendu: (c) => formatMontant(c.total_ht) },
  { titre: "Statut choix", tri: "statut_choix", rendu: (c) => libelle(c.statut_choix) || "—", edition: { champ: "statut_choix", type: "choix", vide: true, options: () => STATUTS_CHOIX } },
  { titre: "Statut appro", tri: "statut_appro", rendu: (c) => libelle(c.statut_appro), edition: { champ: "statut_appro", type: "choix", vide: false, options: () => STATUTS_APPRO } },
  { titre: "Criticité", tri: "criticite", rendu: (c) => libelle(c.criticite) || "—", edition: { champ: "criticite", type: "choix", vide: true, options: () => CRITICITES } },
  { titre: "Avancement", tri: "avancement", rendu: (c) => el("span", { class: `avancement avancement--${c.avancement.replace(/\s/g, "-").toLowerCase()}` }, libelle(c.avancement)) },
];

// --- URL et filtres -------------------------------------------------------------------------

function lireFiltres(parametres) {
  const filtres = { tri: parametres.get("tri") || "id", ordre: parametres.get("ordre") || "asc" };
  for (const cle of FILTRES_TEXTE) filtres[cle] = parametres.get(cle) || "";
  for (const cle of FILTRES_CASES) filtres[cle] = ["1", "true"].includes(parametres.get(cle));
  return filtres;
}

function parametresUrl() {
  const p = {};
  for (const cle of FILTRES_TEXTE) if (etat.filtres[cle]) p[cle] = etat.filtres[cle];
  for (const cle of FILTRES_CASES) if (etat.filtres[cle]) p[cle] = 1;
  if (etat.filtres.tri !== "id") p.tri = etat.filtres.tri;
  if (etat.filtres.ordre !== "asc") p.ordre = etat.filtres.ordre;
  if (etat.ficheOuverte) p.fiche = etat.ficheOuverte;
  return p;
}

function parametresApi() {
  const p = { tri: etat.filtres.tri, ordre: etat.filtres.ordre };
  for (const cle of FILTRES_TEXTE) if (etat.filtres[cle]) p[cle] = etat.filtres[cle];
  for (const cle of FILTRES_CASES) if (etat.filtres[cle]) p[cle] = "true";
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
  const tousLibelles = (liste) => liste.map((v) => [v, libelle(v)]);
  return el(
    "div",
    { class: "filtres" },
    recherche,
    selectFiltre("bloc", "Tous les blocs", etat.blocs.map((b) => [b.code, `${b.code} — ${b.nom}`])),
    selectFiltre("ensemble", "Tous les ensembles", etat.ensembles.map((e) => [e.code, `${e.code} — ${e.nom}`])),
    selectFiltre("mode_appro", "Tous les modes d'appro", tousLibelles(MODES_APPRO)),
    selectFiltre("statut_appro", "Tous les statuts d'appro", tousLibelles(STATUTS_APPRO)),
    selectFiltre("statut_choix", "Tous les statuts de choix", tousLibelles(STATUTS_CHOIX)),
    selectFiltre("criticite", "Toutes les criticités", tousLibelles(CRITICITES)),
    selectFiltre("fournisseur", "Tous les fournisseurs", etat.fournisseurs.map((f) => [f.nom, f.nom])),
    caseFiltre("a_chiffrer", "À chiffrer uniquement"),
    caseFiltre("non_affecte", "Non affecté à un ensemble"),
    etat.filtres.ecart_affectation ? caseFiltre("ecart_affectation", "Écart d'affectation") : null,
    el("button", { type: "button", class: "bouton bouton--discret", onclick: effacerFiltres }, "Tout effacer"),
  );
}

function effacerFiltres() {
  const { tri, ordre } = etat.filtres;
  etat.filtres = lireFiltres(new URLSearchParams());
  Object.assign(etat.filtres, { tri, ordre });
  majUrl();
  etat.zoneFiltres.replaceWith((etat.zoneFiltres = barreFiltres()));
  rechargerListe();
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
  rechargerListe();
}

function entete() {
  return el(
    "thead",
    {},
    el(
      "tr",
      {},
      COLONNES.map((col) => {
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
  for (const col of COLONNES) {
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
      el("td", { colspan: 4 }),
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
  const [blocs, fournisseurs, ensembles] = await Promise.all([api.getBlocs(), api.getFournisseurs(), api.getEnsembles()]);
  etat = {
    filtres: lireFiltres(parametres),
    blocs,
    fournisseurs,
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
  conteneur.replaceChildren(
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, "Composants"),
      el("button", { type: "button", class: "bouton", onclick: ouvrirCreationComposant }, "+ Ajouter un composant"),
    ),
    etat.indicateurs,
    etat.zoneFiltres,
    el("div", { class: "barre-resultats" }, etat.compteur, el("span", { class: "texte-doux" }, "Cliquer sur une ligne pour ouvrir la fiche ; les colonnes soulignées se modifient sur place.")),
    el("div", { class: "table-defilante" }, el("table", { class: "table table--dense table--composants" }, entete(), etat.corps, etat.pied)),
  );
  await Promise.all([rechargerListe(), rendreIndicateurs()]);
  if (etat.ficheOuverte) ouvrirFicheComposant(etat.ficheOuverte);
  if (parametres.get("nouveau")) {
    majUrl();
    ouvrirCreationComposant();
  }
}
