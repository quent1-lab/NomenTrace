// Détail d'un ensemble (#/ensembles/CODE) : composants affectés, quantités modifiables,
// liste de montage et sélecteur pour affecter un composant.

import { api } from "../api.js";
import { editerCellule } from "../edition.js";
import { formatMontant, formatNombre, formatPourcent, libelle } from "../format.js";
import { ouvrirPanneau } from "../panneau.js";
import { lienRoute, naviguer, remplacerRoute } from "../router.js";
import { afficherErreur, classeBloc, el, lienProduit, masquerErreur, rangsBlocs } from "../ui.js";
import { ouvrirCreation } from "./composants_creation.js";
import {
  alerteDepassement,
  barreProgression,
  barreRepartition,
  ouvrirFormulaireEnsemble,
  selectStatutMontage,
  texteBudget,
  texteCout,
  texteEcartBudget,
} from "./ensembles_commun.js";

const EDITION_QTE = { champ: "qte_affectee", type: "entier" };

let etat = null;

function coutLigne(ligne) {
  if (ligne.cout_ligne_ht !== null) return formatMontant(ligne.cout_ligne_ht);
  return ligne.avancement === "Hors achat" ? "—" : el("span", { class: "a-chiffrer" }, "à chiffrer");
}

async function enregistrerQte(ligne, modifs) {
  if (modifs.qte_affectee === 0) {
    throw new Error("Une quantité affectée doit être supérieure à zéro. Pour retirer le composant, utiliser ×.");
  }
  await api.patchAffectation(ligne.affectation_id, { qte: modifs.qte_affectee });
}

async function retirer(ligne) {
  if (!confirm(`Retirer ${ligne.composant_id} de l'ensemble ${etat.code} ?`)) return;
  try {
    await api.deleteAffectation(ligne.affectation_id);
    masquerErreur();
    await recharger();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function ligneComposant(ligne) {
  const qte = el("td", { class: "nombre editable", title: "Cliquer pour modifier la quantité" }, formatNombre(ligne.qte_affectee));
  qte.addEventListener("click", () =>
    editerCellule(qte, EDITION_QTE, ligne, {
      enregistrer: (modifs) => enregistrerQte(ligne, modifs),
      terminer: (reussi) => reussi && recharger(),
    }),
  );
  return el(
    "tr",
    {},
    el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: ligne.composant_id }) }, ligne.composant_id)),
    el("td", { class: "tronque tronque--large", title: ligne.designation }, ligne.designation),
    el("td", { class: "colonne-lien" }, lienProduit(ligne.lien_produit)),
    el("td", {}, el("span", { class: `etiquette-bloc ${classeBloc(etat.rangs.get(ligne.bloc_code) ?? 0)}` }, ligne.bloc_code)),
    qte,
    el("td", { class: "nombre" }, formatNombre(ligne.qte_montee)),
    el("td", { class: `nombre ${ligne.reste_a_monter < 0 ? "texte-alerte" : ""}` }, formatNombre(ligne.reste_a_monter)),
    el("td", {}, libelle(ligne.statut_appro)),
    el("td", { class: "nombre" }, formatMontant(ligne.pu_ht)),
    el("td", { class: "nombre" }, coutLigne(ligne)),
    el("td", { class: "nombre" }, el("button", { type: "button", class: "bouton-icone", title: "Retirer de l'ensemble", onclick: () => retirer(ligne) }, "×")),
  );
}

function tableComposants() {
  const entetes = ["ID", "Désignation", "", "Bloc", "Qté affectée", "Montée", "Reste à monter", "Statut appro", "PU HT", "Coût ligne HT", ""];
  const numeriques = new Set([4, 5, 6, 8, 9, 10]);
  const corps = el("tbody");
  if (etat.grouper) {
    const blocs = [...new Set(etat.lignes.map((l) => l.bloc_code))].sort((a, b) => (etat.rangs.get(a) ?? 0) - (etat.rangs.get(b) ?? 0));
    for (const bloc of blocs) {
      const lignes = etat.lignes.filter((l) => l.bloc_code === bloc);
      const sousTotal = lignes.reduce((s, l) => s + (l.cout_ligne_ht ?? 0), 0);
      const nom = etat.blocs.find((b) => b.code === bloc)?.nom ?? bloc;
      corps.append(
        el("tr", { class: "ligne-groupe" }, el("td", { colspan: 9 }, el("span", { class: `etiquette-bloc ${classeBloc(etat.rangs.get(bloc) ?? 0)}` }, bloc), ` ${nom} — ${lignes.length} composant(s)`), el("td", { class: "nombre fort" }, formatMontant(sousTotal)), el("td")),
        ...lignes.map(ligneComposant),
      );
    }
  } else {
    corps.append(...etat.lignes.map(ligneComposant));
  }
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: numeriques.has(i) ? "nombre" : "" }, t)))),
    corps,
    el("tfoot", {}, el("tr", {}, el("td", { colspan: 9, class: "nombre" }, "Coût total HT"), el("td", { class: "nombre fort" }, texteCout(etat.ensemble)), el("td"))),
  );
}

function etatPreparation(ligne) {
  if (ligne.stock_actuel >= ligne.reste_a_monter) return ["pret", "Prêt à monter"];
  if (ligne.stock_actuel > 0) return ["partiel", `${ligne.stock_actuel} en stock sur ${ligne.reste_a_monter}`];
  return ["attente", ligne.avancement === "Commande" ? "Attend la livraison" : ligne.avancement === "A commander" ? "Pas encore commandé" : "Pas en stock"];
}

function listeMontage() {
  const aMonter = etat.lignes.filter((l) => l.reste_a_monter > 0);
  if (!aMonter.length) {
    return el("p", { class: "texte-doux" }, etat.lignes.length ? "Tout ce qui est affecté est monté." : "Rien à monter : aucun composant affecté.");
  }
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, ["ID", "Désignation", "Reste à monter", "Statut appro", "Stock actuel", "État"].map((t, i) => el("th", { class: i === 2 || i === 4 ? "nombre" : "" }, t)))),
    el(
      "tbody",
      {},
      aMonter.map((l) => {
        const [classe, texte] = etatPreparation(l);
        return el(
          "tr",
          {},
          el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: l.composant_id }) }, l.composant_id)),
          el("td", { class: "tronque tronque--large", title: l.designation }, l.designation),
          el("td", { class: "nombre" }, formatNombre(l.reste_a_monter)),
          el("td", {}, libelle(l.statut_appro)),
          el("td", { class: `nombre ${l.stock_actuel < 0 ? "texte-alerte" : ""}` }, formatNombre(l.stock_actuel)),
          el("td", {}, el("span", { class: `preparation preparation--${classe}` }, texte)),
        );
      }),
    ),
  );
}

// Case du bandeau ; pour un parent, la valeur cumulée puis la part propre.
function caseChiffre(titre, valeur, propre = null) {
  return el(
    "div",
    {},
    el("span", { class: "texte-doux" }, titre),
    el("strong", {}, valeur),
    propre !== null ? el("span", { class: "carte__propre" }, `dont propre ${propre}`) : null,
  );
}

function bandeau() {
  const e = etat.ensemble;
  const parent = e.nb_sous_ensembles > 0;
  const c = parent ? e.cumul : e;
  const propre = (valeur) => (parent ? valeur : null);
  return el(
    "section",
    { class: "panneau bandeau-ensemble" },
    parent ? el("p", { class: "texte-doux texte-petit" }, `Chiffres cumulés : l'ensemble et ses ${e.nb_sous_ensembles} sous-ensemble(s). La part propre ne compte que ses affectations directes.`) : null,
    el(
      "div",
      { class: "bandeau-ensemble__chiffres" },
      caseChiffre("Composants distincts", formatNombre(c.nb_composants_distincts), propre(formatNombre(e.nb_composants_distincts))),
      caseChiffre("Pièces", formatNombre(c.nb_pieces_total), propre(formatNombre(e.nb_pieces_total))),
      caseChiffre("Coût HT", texteCout(c), propre(formatMontant(e.cout_ht))),
      caseChiffre("Budget HT", texteBudget(e), parent && e.budget_propre_ht !== null ? formatMontant(e.budget_propre_ht) : null),
      e.ecart_budget_ht !== null ? caseChiffre("Écart au budget", texteEcartBudget(e.ecart_budget_ht)) : null,
      caseChiffre("Blocs représentés", formatNombre(c.nb_blocs_representes)),
      el("div", {}, el("span", { class: "texte-doux" }, "Statut de montage"), selectStatutMontage(e, recharger)),
    ),
    alerteDepassement(e.depassement_verrouille_ht),
    barreRepartition(etat.repartition, etat.rangs),
    el(
      "div",
      { class: "grille-2" },
      barreProgression("Appro : composants reçus", c.nb_composants_recus, c.nb_composants_a_acheter, "rien à acheter"),
      barreProgression("Montage : pièces montées", c.nb_pieces_montees, c.nb_pieces_total, "aucune pièce"),
    ),
    e.description || e.responsable
      ? el("p", { class: "texte-doux" }, [e.responsable ? `Responsable : ${e.responsable}. ` : "", e.description ?? ""].join(""))
      : null,
  );
}

function filAriane(e) {
  const liens = [el("a", { href: "#/ensembles" }, "← Ensembles")];
  for (const parent of e.chemin) {
    liens.push(" / ", el("a", { href: `#/ensembles/${encodeURIComponent(parent.code)}` }, parent.nom));
  }
  return el("p", { class: "fil" }, liens);
}

function sectionSousEnsembles() {
  const lignes = etat.ensemble.enfants.map((s) => {
    const c = s.cumul;
    const ouvrir = () => naviguer(`/ensembles/${s.code}`);
    return el(
      "tr",
      { class: "ligne-cliquable", tabindex: "0", onclick: ouvrir, onkeydown: (ev) => ev.key === "Enter" && ouvrir() },
      el("td", {}, s.nom, el("span", { class: "etiquette etiquette--espace" }, s.code), s.nb_sous_ensembles ? el("span", { class: "texte-doux texte-petit" }, ` + ${s.nb_sous_ensembles} sous-ensemble(s)`) : null),
      el("td", { class: "nombre" }, formatNombre(c.nb_pieces_total)),
      el("td", { class: "nombre" }, texteCout(c)),
      el("td", { class: "nombre" }, texteBudget(s)),
      el("td", { class: "nombre" }, texteEcartBudget(s.ecart_budget_ht)),
      el("td", { class: "nombre" }, c.avancement_montage_pct === null ? "—" : formatPourcent(c.avancement_montage_pct, 0)),
    );
  });
  const entetes = [["Sous-ensemble"], ["Pièces", "nombre"], ["Coût HT cumulé", "nombre"], ["Budget HT", "nombre"], ["Écart", "nombre"], ["Montage", "nombre"]];
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Sous-ensembles"),
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, entetes.map(([t, c]) => el("th", { class: c ?? "" }, t)))),
      el("tbody", {}, lignes),
    ),
  );
}

function creerSousEnsemble() {
  ouvrirFormulaireEnsemble({
    parentInitial: etat.code,
    ordreSuggere: etat.ensemble.enfants.reduce((max, s) => Math.max(max, s.ordre), 0) + 1,
    surEnregistre: (cree) => naviguer(`/ensembles/${cree.code}`),
  });
}

function rendre() {
  const e = etat.ensemble;
  const grouper = el("label", { class: "filtre-case" }, el("input", {
    type: "checkbox",
    checked: etat.grouper,
    onchange: (ev) => {
      etat.grouper = ev.target.checked;
      remplacerRoute(`/ensembles/${etat.code}`, etat.grouper ? { grouper: 1 } : {});
      rendre();
    },
  }), "Grouper par bloc fonctionnel");
  etat.conteneur.replaceChildren(
    filAriane(e),
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, `${e.nom} `, el("span", { class: "etiquette" }, e.code)),
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "bouton", onclick: ouvrirSelecteur }, "+ Affecter un composant"),
        el("button", { type: "button", class: "bouton bouton--discret", onclick: creerSousEnsemble }, "+ Sous-ensemble"),
        el("button", { type: "button", class: "bouton bouton--discret", onclick: () => ouvrirFormulaireEnsemble({ ensemble: e, surEnregistre: recharger }) }, "Modifier"),
        el("button", { type: "button", class: "bouton bouton--danger", onclick: archiver }, "Archiver"),
      ),
    ),
    bandeau(),
    ...(e.enfants.length ? [sectionSousEnsembles()] : []),
    el(
      "section",
      { class: "panneau" },
      el("div", { class: "titre-section" }, el("h2", {}, e.enfants.length ? "Composants affectés directement" : "Composants affectés"), etat.lignes.length ? grouper : null),
      etat.lignes.length
        ? [el("p", { class: "texte-doux texte-petit" }, "Cliquer sur une quantité affectée pour la modifier ; × retire le composant de l'ensemble."), tableComposants()]
        : el("p", { class: "texte-doux" }, "Aucun composant n'est encore affecté à cet ensemble. Utiliser « Affecter un composant »."),
    ),
    el("section", { class: "panneau" }, el("h2", {}, "Liste de montage"), el("p", { class: "texte-doux texte-petit" }, "Composants qu'il reste à monter. Le stock est celui du composant, tous ensembles confondus."), listeMontage()),
  );
}

async function archiver() {
  if (!confirm(`Archiver l'ensemble ${etat.code} ?`)) return;
  try {
    await api.archiveEnsemble(etat.code);
    masquerErreur();
    naviguer("/ensembles");
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

async function recharger() {
  const [ensemble, lignes, repartition] = await Promise.all([
    api.getEnsemble(etat.code),
    api.getComposantsEnsemble(etat.code),
    api.getRepartition(true),
  ]);
  Object.assign(etat, { ensemble, lignes, repartition: repartition.filter((r) => r.ensemble_code === etat.code) });
  rendre();
}

// --- Sélecteur d'affectation ---------------------------------------------------------------

function ligneSelecteur(c, ici, surAffecte) {
  const ailleurs = c.qte_affectee - (ici?.qte_affectee ?? 0);
  const suggere = ici ? ici.qte_affectee : Math.max(1, c.qte_besoin - c.qte_affectee);
  const qte = el("input", { class: "champ-cellule champ-cellule--nombre", type: "text", inputmode: "numeric", value: String(suggere), "aria-label": `Quantité de ${c.id}` });
  const alerte = el("span", { class: "texte-petit" });
  const majAlerte = () => {
    const n = Number.parseInt(qte.value, 10);
    const exces = ailleurs + (Number.isNaN(n) ? 0 : n) - c.qte_besoin;
    alerte.textContent = exces > 0 ? `sur-affectation de ${exces}` : "";
    alerte.className = exces > 0 ? "texte-petit texte-surveiller" : "texte-petit";
  };
  qte.addEventListener("input", majAlerte);
  majAlerte();
  const executer = async (action) => {
    try {
      await action();
      masquerErreur();
      await surAffecte();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const retirer = () => executer(() => api.deleteAffectation(ici.affectation_id));
  const valider = () => {
    const n = Number(qte.value.trim());
    // Déjà affecté : 0 vaut retrait, la même quantité ne fait rien.
    if (ici && n === 0) return retirer();
    if (!Number.isInteger(n) || n <= 0) return afficherErreur("La quantité doit être un entier supérieur à zéro.");
    if (ici && n === ici.qte_affectee) return;
    return executer(() =>
      ici ? api.patchAffectation(ici.affectation_id, { qte: n }) : api.createAffectation(etat.code, { composant_id: c.id, qte: n }),
    );
  };
  qte.addEventListener("keydown", (e) => {
    if (e.key === "Enter") valider();
  });
  // Pour un composant déjà affecté, la quantité s'enregistre dès qu'on quitte le champ.
  if (ici) qte.addEventListener("change", valider);
  const actions = ici
    ? [el("button", { type: "button", class: "bouton bouton--petit bouton--danger", title: "Retirer de l'ensemble", onclick: retirer }, "Retirer")]
    : [el("button", { type: "button", class: "bouton bouton--petit", onclick: valider }, "Affecter")];
  return el(
    "tr",
    { class: ici ? "ligne--selection" : "" },
    el("td", { class: "code" }, c.id),
    el("td", { class: "tronque", title: c.designation }, c.designation),
    el("td", {}, c.bloc_code),
    el("td", { class: "nombre" }, formatNombre(c.qte_besoin)),
    el("td", { class: "nombre" }, formatNombre(ailleurs)),
    el("td", { class: "nombre" }, ici ? formatNombre(ici.qte_affectee) : "—"),
    el("td", { class: "nombre" }, qte),
    el("td", {}, actions, " ", alerte),
  );
}

async function ouvrirSelecteur() {
  const [composants, fournisseurs] = await Promise.all([api.getComposants({ tri: "id" }), api.getFournisseurs()]);
  let liste = composants;
  const recherche = el("input", { class: "champ", type: "search", placeholder: "Identifiant, désignation ou référence…", "aria-label": "Rechercher un composant" });
  const corps = el("tbody");
  const compte = el("p", { class: "texte-doux texte-petit" });

  const afficherListe = () => {
    const terme = recherche.value.trim().toLowerCase();
    const trouves = liste.filter((c) => !terme || [c.id, c.designation, c.fonction, c.ref_fabricant].some((v) => (v ?? "").toLowerCase().includes(terme)));
    const parId = new Map(etat.lignes.map((l) => [l.composant_id, l]));
    trouves.sort((a, b) => Number(parId.has(b.id)) - Number(parId.has(a.id)));
    corps.replaceChildren(...trouves.slice(0, 40).map((c) => ligneSelecteur(c, parId.get(c.id), surAffecte)));
    compte.textContent = trouves.length > 40 ? `${trouves.length} composants trouvés, 40 affichés : préciser la recherche.` : `${trouves.length} composant(s) trouvé(s).`;
  };
  const surAffecte = async () => {
    await recharger();
    liste = await api.getComposants({ tri: "id" });
    afficherListe();
  };
  recherche.addEventListener("input", afficherListe);

  const creer = () =>
    ouvrirCreation({
      blocs: etat.blocs,
      fournisseurs,
      blocInitial: "",
      note: `Le composant créé sera affecté à l'ensemble ${etat.code} avec sa quantité besoin. Choisir son bloc fonctionnel : il est indépendant de l'ensemble.`,
      surCree: async (cree) => {
        try {
          await api.createAffectation(etat.code, { composant_id: cree.id, qte: Math.max(1, cree.qte_besoin) });
          masquerErreur();
        } catch (erreur) {
          afficherErreur(erreur);
        }
        await recharger();
      },
    });

  ouvrirPanneau(`Affecter un composant à ${etat.code}`, [
    el("p", { class: "texte-doux" }, "« Ailleurs » est la quantité déjà affectée aux autres ensembles : comparée au besoin, elle montre tout de suite une sur-affectation. Entrée ou « Affecter » valide la ligne. Les composants déjà affectés ici sont en tête : leur quantité s'enregistre dès qu'on quitte le champ (0 ou « Retirer » les enlève)."),
    recherche,
    compte,
    el(
      "table",
      { class: "table table--dense selecteur" },
      el("thead", {}, el("tr", {}, ["ID", "Désignation", "Bloc", "Besoin", "Ailleurs", "Ici", "Qté", ""].map((t, i) => el("th", { class: i >= 3 && i <= 6 ? "nombre" : "" }, t)))),
      corps,
    ),
    el("p", { class: "selecteur__creation" }, "Le composant n'existe pas encore ? ", el("button", { type: "button", class: "bouton bouton--discret", onclick: creer }, "Créer un composant")),
  ]);
  afficherListe();
  recherche.focus();
}

export async function afficherDetailEnsemble(conteneur, parametres, code) {
  const blocs = await api.getBlocs();
  etat = { conteneur, code, blocs, rangs: rangsBlocs(blocs), grouper: parametres.get("grouper") === "1" };
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
