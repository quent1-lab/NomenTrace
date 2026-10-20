// Fiche d'un composant dans le panneau latéral : un en-tête (désignation, pastilles de visa
// et d'actions à faire), le suivi du composant de son chiffrage à son montage, son prix et son
// fournisseur, puis des onglets : détails, ensembles, achats, stock, documents, historique.

import { frise } from "../historique.js";
import { api } from "../api.js";
import { champAttribut, chargerAttributs, formatAttribut, tousLesAttributs } from "../attributs.js";
import { sectionDocuments } from "../documents.js";
import { formatDate, formatMontant, formatNombre, formatPourcent, libelle, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { lienRoute, naviguer } from "../router.js";
import { aPermission, ecritBloc, estAdmin } from "../session.js";
import { afficherErreur, el, largeur, lienExterne, masquerErreur } from "../ui.js";
import { BASES_PRIX, valeursListe } from "../valeurs.js";
import { champFournisseur, lienFournisseur, statutsFournisseurs } from "./fournisseurs_commun.js";

const DESCRIPTION_MODIF = {
  fonction: "texte",
  designation: "texte",
  ref_fabricant: "texte",
  fabricant: "texte",
  mode_appro: "choix",
  fournisseur_nom: "choix",
  lien_produit: "texte",
  qte_besoin: "entier",
  qte_rechange: "entier",
  qte_disponible: "entier",
  pu_releve: "montant",
  base_prix_releve: "choix",
  taux_tva: "taux",
  statut_choix: "choix",
  statut_appro: "choix",
  criticite: "choix",
  origine_exigence: "texte",
  note_technique: "texte",
};
const OBLIGATOIRES = { fonction: "Fonction", designation: "Désignation", mode_appro: "Mode d'appro", qte_besoin: "Qté besoin" };

function section(titre, ...contenu) {
  return el("section", { class: "fiche__section" }, el("h3", {}, titre), ...contenu);
}

function definitions(paires) {
  return el(
    "dl",
    { class: "fiche__champs" },
    paires.flatMap(([terme, valeur]) => [el("dt", {}, terme), el("dd", {}, valeur === null || valeur === undefined || valeur === "" ? "—" : valeur)]),
  );
}

function tableSimple(entetes, lignes, vide) {
  if (!lignes.length) return el("p", { class: "texte-doux" }, vide);
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, entetes.map(([t, c]) => el("th", { class: c ?? "" }, t)))),
    el("tbody", {}, lignes),
  );
}

function lienComposant(id) {
  return el("a", { class: "code", href: lienRoute("/composants", { fiche: id }) }, id);
}

// Reclassement : le composant est recréé dans le bloc cible avec un nouvel identifiant.
async function ouvrirReclassement(c, zone, surReclasse) {
  let blocs;
  try {
    blocs = (await api.getBlocs()).filter((b) => b.code !== c.bloc_code);
  } catch (erreur) {
    afficherErreur(erreur);
    return;
  }
  if (!blocs.length) {
    zone.replaceChildren(el("p", { class: "texte-doux" }, "Aucun autre bloc ouvert."));
    return;
  }
  const choix = champChoix("bloc_code", blocs.map((b) => [b.code, `${b.code} · ${b.nom}`]), null, { vide: "Bloc cible…" });
  const formulaire = el(
    "form",
    { class: "panneau panneau--encart" },
    el(
      "p",
      { class: "texte-petit" },
      "Le bloc est figé dans l'identifiant : reclasser crée un nouveau composant dans le bloc choisi, avec les mêmes données " +
        `et un nouvel identifiant. ${c.id} est archivé ; ses affectations et ses documents passent au nouveau, ses commandes et son stock lui restent.`,
    ),
    el("div", { class: "formulaire-ligne" }, choix,
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => zone.replaceChildren() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, "Reclasser"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!choix.value) return afficherErreur("Choisir le bloc cible.");
    try {
      const nouveau = await api.reclasserComposant(c.id, choix.value);
      masquerErreur();
      await surReclasse(nouveau);
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  zone.replaceChildren(formulaire);
}

// --- En-tête, suivi, prix et onglets de la fiche ---------------------------------------------

const SVG = "http://www.w3.org/2000/svg";

// Petite icône tracée (coche, avertissement), décorative.
function icone(traces, classe = "") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", `icone-fiche ${classe}`);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of traces) {
    const trace = document.createElementNS(SVG, "path");
    trace.setAttribute("d", d);
    svg.append(trace);
  }
  return svg;
}
const COCHE = ["M5 12l5 5 9-10"];
const ATTENTION = ["M12 3l10 18H2z", "M12 10v5", "M12 18h.01"];

function texteVisa(visa) {
  const auteur = visa.vise_par ? ` par ${visa.vise_par}` : "";
  return `Visé${auteur} le ${formatDate(visa.vise_le)}`;
}

// Pastille du visa : posé tout seul quand un responsable ouvre la fiche.
function pastilleVisa(visa) {
  if (visa?.a_jour) return el("span", { class: "puce-fiche puce-fiche--conforme" }, icone(COCHE), texteVisa(visa));
  const texte = visa ? "Modifié depuis le dernier visa" : "Pas encore visé";
  return el("span", { class: "puce-fiche puce-fiche--neutre", title: "Un responsable le vise en ouvrant la fiche" }, texte);
}

// Pastille « N actions » : un clic déroule la liste de ce qui reste à faire.
function pastilleActions(actions, allerA) {
  if (!actions.length) return null;
  const liste = el(
    "div",
    { class: "actions-fiche", hidden: true },
    el("strong", {}, "À faire sur ce composant"),
    actions.map((a) =>
      el(
        "div",
        { class: "actions-fiche__ligne" },
        el("span", {}, a.texte),
        el("button", { type: "button", class: "bouton-lien", onclick: () => { fermer(); allerA(a.onglet); } }, LIBELLES_ACTION[a.onglet] ?? "Voir"),
      ),
    ),
  );
  const bouton = el(
    "button",
    { type: "button", class: "puce-fiche puce-fiche--actions", "aria-expanded": "false" },
    icone(ATTENTION),
    `${actions.length} action${actions.length > 1 ? "s" : ""}`,
  );
  function fermer() {
    liste.hidden = true;
    bouton.setAttribute("aria-expanded", "false");
  }
  bouton.addEventListener("click", () => {
    liste.hidden = !liste.hidden;
    bouton.setAttribute("aria-expanded", String(!liste.hidden));
  });
  const ancre = el("span", { class: "actions-fiche__ancre" }, bouton, liste);
  // Un clic ailleurs referme la liste ; l'écouteur s'en va avec la fiche.
  const ailleurs = (e) => {
    if (!ancre.isConnected) return document.removeEventListener("click", ailleurs);
    if (!ancre.contains(e.target)) fermer();
  };
  document.addEventListener("click", ailleurs);
  return ancre;
}
const LIBELLES_ACTION = { modifier: "Compléter", ensembles: "Affecter", documents: "Joindre" };

// Une étape du suivi : valeur courte, fine jauge verte (fait), orange (en cours) ou grise.
function etapeSuivi({ titre, valeur, fait = null, total = null, note = "", neutre = false, onglet, allerA }) {
  const part = total ? Math.min(fait / total, 1) : fait === null ? 0 : 1;
  const niveau = neutre ? "neutre" : part >= 1 ? "fait" : part > 0 ? "encours" : "neutre";
  const jauge = el("span", { class: "suivi__jauge" }, largeur(el("span", { class: `suivi__remplissage suivi__remplissage--${niveau}` }), (neutre ? 0 : part) * 100));
  return el(
    "button",
    { type: "button", class: `suivi__etape suivi__etape--${niveau}`, onclick: () => allerA(onglet) },
    el("span", { class: "suivi__titre" }, niveau === "fait" ? icone(COCHE) : null, titre),
    el("span", { class: "suivi__valeur" }, valeur),
    jauge,
    note ? el("span", { class: "suivi__note" }, note) : null,
  );
}

// Lien vers la page produit, en pastille avec un globe : repérable d'un coup d'œil.
const GLOBE = ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M3 12h18", "M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9", "M12 3c-2.5 2.6-3.8 5.6-3.8 9s1.3 6.4 3.8 9"];
function boutonPageProduit(adresse) {
  const lien = lienExterne(adresse, "Page produit");
  if (lien.tagName !== "A") return lien;
  lien.classList.add("lien-page-produit");
  lien.title = adresse;
  lien.prepend(icone(GLOBE));
  return lien;
}

function prochaineLivraison(lignes) {
  const dates = lignes
    .filter((l) => l.type === "Commande" && l.qte_recue < l.qte_commandee && l.statut_ligne !== "Annulee")
    .map((l) => l.date_reception_annoncee || l.livraison_annoncee)
    .filter(Boolean)
    .sort();
  return dates[0] ?? null;
}

// Où en est le composant : chiffré, commandé, reçu, affecté, monté.
function suivi(fiche, allerA) {
  const c = fiche.composant;
  const achat = c.mode_appro === "Achat";
  const aAcheter = c.qte_a_acheter;
  const montees = fiche.affectations.reduce((s, a) => s + Math.min(Math.max(a.qte_montee, 0), a.qte_affectee), 0);
  const livraison = prochaineLivraison(fiche.lignes_commande);
  const noteRecu = [livraison ? `solde le ${formatDate(livraison)}` : "", `${formatNombre(c.stock_actuel)} en stock`].filter(Boolean).join(" · ");
  const horsAchat = { valeur: achat ? "rien à acheter" : libelle(c.mode_appro), neutre: true };
  const etapes = [
    achat
      ? { titre: "Chiffré", valeur: c.pu_ht === null ? "à chiffrer" : `${formatMontant(c.pu_ht)} HT`, fait: c.pu_ht === null ? 0 : 1, total: 1, onglet: "modifier" }
      : { titre: "Chiffré", ...horsAchat, onglet: "details" },
    achat && aAcheter > 0
      ? { titre: "Commandé", valeur: `${formatNombre(c.qte_commandee)} / ${formatNombre(aAcheter)}`, fait: c.qte_commandee, total: aAcheter, onglet: "achats" }
      : { titre: "Commandé", ...horsAchat, onglet: "achats" },
    achat && aAcheter > 0
      ? { titre: "Reçu", valeur: `${formatNombre(c.qte_recue)} / ${formatNombre(aAcheter)}`, fait: c.qte_recue, total: aAcheter, note: noteRecu, onglet: "achats" }
      : { titre: "Reçu", ...horsAchat, note: `${formatNombre(c.stock_actuel)} en stock`, onglet: "stock" },
    // Aucune affectation est un état normal : l'étape reste neutre, sans alerte.
    c.nb_ensembles > 0
      ? { titre: "Affecté", valeur: `${formatNombre(c.qte_affectee)} / ${formatNombre(c.qte_besoin)}`, fait: c.qte_affectee, total: c.qte_besoin, onglet: "ensembles" }
      : { titre: "Affecté", valeur: "aucun ensemble", neutre: true, onglet: "ensembles" },
    c.qte_affectee > 0
      ? { titre: "Monté", valeur: `${formatNombre(montees)} / ${formatNombre(c.qte_affectee)}`, fait: montees, total: c.qte_affectee, onglet: "ensembles" }
      : { titre: "Monté", valeur: "—", neutre: true, onglet: "ensembles" },
  ];
  return el(
    "section",
    { class: "suivi" },
    el(
      "div",
      { class: "suivi__entete" },
      el("strong", {}, "Suivi"),
      el("span", { class: "suivi__formule" }, `Besoin ${c.qte_besoin} + rechange ${c.qte_rechange} − déjà disponible ${c.qte_disponible} = `, el("strong", {}, `${formatNombre(aAcheter)} à acheter`)),
    ),
    el("div", { class: "suivi__etapes" }, etapes.map((e) => etapeSuivi({ ...e, allerA }))),
  );
}

function blocPrixFournisseur(c, statuts) {
  const prix = c.pu_ht === null
    ? [el("div", { class: "fiche-prix__montant" }, c.mode_appro === "Achat" ? "à chiffrer" : "—")]
    : [
        el("div", { class: "fiche-prix__montant" }, `${formatMontant(c.pu_ht)} HT `, el("span", { class: "texte-doux" }, "l'unité")),
        el("div", { class: "texte-doux" }, `Relevé ${formatMontant(c.pu_releve)} ${c.base_prix_releve} · TVA ${formatPourcent(c.taux_tva * 100, 1)}`),
        el("div", {}, "Total HT ", el("strong", {}, formatMontant(c.total_ht))),
      ];
  const reference = [c.ref_fabricant, c.fabricant].filter(Boolean).join(" · ");
  return el(
    "section",
    { class: "fiche-prix" },
    el("div", {}, el("div", { class: "texte-doux texte-petit" }, "Prix"), ...prix),
    el(
      "div",
      {},
      el("div", { class: "texte-doux texte-petit" }, "Fournisseur"),
      el("div", { class: "fiche-prix__fournisseur" }, c.fournisseur_nom ? lienFournisseur(c.fournisseur_nom, statuts.get(c.fournisseur_nom)) : "—"),
      reference ? el("div", {}, `Réf. ${reference}`) : null,
      c.lien_produit ? el("div", {}, boutonPageProduit(c.lien_produit)) : null,
    ),
  );
}

function vueDetails(fiche) {
  const c = fiche.composant;
  const renseignes = tousLesAttributs().filter((a) => fiche.attributs[a.code] !== undefined && fiche.attributs[a.code] !== null);
  return [
    el(
      "dl",
      { class: "fiche-details" },
      [
        ["Fonction", c.fonction],
        ["Mode d'appro", libelle(c.mode_appro)],
        ["Statut de choix", libelle(c.statut_choix)],
        ["Statut d'appro", libelle(c.statut_appro)],
        ["Criticité", libelle(c.criticite)],
        ["Avancement", libelle(c.avancement)],
        ["Origine de l'exigence", c.origine_exigence],
      ].map(([terme, valeur]) => el("div", {}, el("dt", {}, terme), el("dd", {}, valeur || "—"))),
    ),
    renseignes.length
      ? el(
          "div",
          { class: "fiche-caracteristiques" },
          el("div", { class: "texte-doux texte-petit" }, "Caractéristiques"),
          el("div", { class: "fiche-caracteristiques__liste" }, renseignes.map((a) => el("span", { class: "puce-fiche puce-fiche--info" }, `${a.libelle} `, el("strong", {}, formatAttribut(a, fiche.attributs[a.code]))))),
        )
      : null,
    c.note_technique ? el("div", { class: "fiche__note" }, el("strong", {}, "Note technique"), el("p", {}, c.note_technique)) : null,
    fiche.remplace.length
      ? el("p", { class: "lien-remplacement texte-doux" }, "Remplace ", fiche.remplace.flatMap((ancien, rang) => [rang ? ", " : "", lienComposant(ancien)]), " (reclassement : historique, commandes et stock restent sur l'ancien identifiant).")
      : null,
    el("p", { class: "texte-doux texte-petit" }, `Créé le ${formatDate(c.cree_le)} · modifié le ${formatDate(c.modifie_le)}`),
  ];
}

// Onglet ouvert, gardé d'un rafraîchissement à l'autre pour le même composant.
let ongletCourant = { id: null, onglet: "details" };

// Champs de base rendus obligatoires dans les paramètres, relus à l'ouverture de la fiche.
let champsRequis = new Set();

// Les champs et les caractéristiques se modifient ensemble et s'enregistrent en une seule fois.
function formulaireModif(c, valeursAttributs, fournisseurs, { surEnregistre, surAnnule }) {
  const requis = (champ) => ({ requis: champsRequis.has(champ) });
  const caracteristiques = champsCaracteristiques(valeursAttributs);
  const choixFournisseur = champFournisseur(fournisseurs, c.fournisseur_nom);
  const base = champChoix("base_prix_releve", BASES_PRIX, c.base_prix_releve);
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Fonction", champTexte("fonction", c.fonction), { requis: true }),
    ligneChamp("Désignation", champTexte("designation", c.designation), { requis: true }),
    ligneChamp("Réf fabricant", champTexte("ref_fabricant", c.ref_fabricant), requis("ref_fabricant")),
    ligneChamp("Fabricant", champTexte("fabricant", c.fabricant), requis("fabricant")),
    ligneChamp("Mode d'appro", champChoix("mode_appro", valeursListe("mode_appro", { valeurCourante: c.mode_appro }), c.mode_appro), { requis: true }),
    ligneChamp("Fournisseur", choixFournisseur.element, requis("fournisseur_nom")),
    ligneChamp("Lien produit", champTexte("lien_produit", c.lien_produit, { type: "url" }), requis("lien_produit")),
    ligneChamp("Qté besoin", champNombre("qte_besoin", c.qte_besoin), { requis: true }),
    ligneChamp("Qté rechange", champNombre("qte_rechange", c.qte_rechange)),
    ligneChamp("Qté déjà disponible", champNombre("qte_disponible", c.qte_disponible)),
    ligneChamp("PU relevé", champNombre("pu_releve", c.pu_releve, 2), requis("pu_releve")),
    ligneChamp("Base du prix", base),
    ligneChamp("Taux de TVA (%)", champNombre("taux_tva", c.taux_tva * 100, 1)),
    ligneChamp("Statut choix", champChoix("statut_choix", valeursListe("statut_choix", { valeurCourante: c.statut_choix }), c.statut_choix, { vide: "—" })),
    ligneChamp("Statut appro", champChoix("statut_appro", valeursListe("statut_appro", { valeurCourante: c.statut_appro }), c.statut_appro)),
    ligneChamp("Criticité", champChoix("criticite", valeursListe("criticite", { valeurCourante: c.criticite }), c.criticite, { vide: "—" })),
    ligneChamp("Origine exigence", champTexte("origine_exigence", c.origine_exigence)),
    ligneChamp("Note technique", champZone("note_technique", c.note_technique)),
    caracteristiques.length
      ? el("fieldset", {}, el("legend", {}, "Caractéristiques"),
          caracteristiques.map(({ a, element }) => ligneChamp(a.unite ? `${a.libelle} (${a.unite})` : a.libelle, element, { requis: Boolean(a.obligatoire) })))
      : null,
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: surAnnule }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION_MODIF, OBLIGATOIRES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    const manquants = Object.keys(OBLIGATOIRES).filter((n) => lu.valeurs[n] === null);
    if (manquants.length) return afficherErreur(`Champs obligatoires manquants : ${manquants.map((n) => OBLIGATOIRES[n]).join(", ")}.`);
    const attributs = {};
    for (const { a, lire } of caracteristiques) {
      const valeur = lire();
      if (valeur.erreur) return afficherErreur(valeur.erreur);
      if (valeur.valeur !== (valeursAttributs[a.code] ?? null)) attributs[a.code] = valeur.valeur;
    }
    try {
      lu.valeurs.fournisseur_nom = await choixFournisseur.resoudre();
      const modifs = Object.fromEntries(Object.entries(lu.valeurs).filter(([cle, v]) => v !== c[cle]));
      if (Object.keys(attributs).length) modifs.attributs = attributs;
      if (Object.keys(modifs).length === 0) return surAnnule();
      // Date lue à l'ouverture : si quelqu'un a modifié le composant depuis, le serveur refuse.
      await api.patchComposant(c.id, { ...modifs, modifie_le: c.modifie_le });
      masquerErreur();
      await surEnregistre();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

// Quantité d'une affectation, modifiable directement dans la fiche.
function champQteAffectation(affectation, surChangement) {
  const initial = String(affectation.qte_affectee);
  const champ = el("input", { class: "champ-cellule champ-cellule--nombre", type: "text", inputmode: "numeric", value: initial, "aria-label": `Quantité dans ${affectation.ensemble_code}` });
  let enCours = false;
  const valider = async () => {
    const valeur = lireNombre(champ.value);
    if (enCours || champ.value.trim() === initial) return;
    if (valeur === null || Number.isNaN(valeur) || !Number.isInteger(valeur) || valeur <= 0) {
      champ.value = initial;
      return afficherErreur("La quantité affectée doit être un entier supérieur à zéro. Pour retirer l'affectation, utiliser ×.");
    }
    enCours = true;
    champ.disabled = true;
    try {
      await api.patchAffectation(affectation.affectation_id, { qte: valeur });
      masquerErreur();
      await surChangement();
    } catch (erreur) {
      champ.value = initial;
      champ.disabled = false;
      enCours = false;
      afficherErreur(erreur);
    }
  };
  champ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") valider();
    if (e.key === "Escape") {
      e.stopPropagation();
      champ.value = initial;
      champ.blur();
    }
  });
  champ.addEventListener("blur", valider);
  return champ;
}

function sectionAffectations(fiche, ensembles, surChangement, modifiable) {
  const c = fiche.composant;
  const lignes = fiche.affectations.map((a) =>
    el(
      "tr",
      {},
      el("td", {}, el("a", { href: lienRoute(`/ensembles/${a.ensemble_code}`) }, a.ensemble_code), " ", el("span", { class: "texte-doux" }, a.ensemble_nom)),
      el("td", { class: "nombre" }, modifiable ? champQteAffectation(a, surChangement) : formatNombre(a.qte_affectee)),
      el("td", { class: "nombre" }, formatNombre(a.qte_montee)),
      el(
        "td",
        { class: "nombre" },
        modifiable && el("button", {
          type: "button",
          class: "bouton-icone",
          title: "Retirer l'affectation",
          onclick: async () => {
            if (!confirm(`Retirer ${c.id} de l'ensemble ${a.ensemble_code} ?`)) return;
            try {
              await api.deleteAffectation(a.affectation_id);
              await surChangement();
            } catch (erreur) {
              afficherErreur(erreur);
            }
          },
        }, "×"),
      ),
    ),
  );
  const dejaAffectes = new Set(fiche.affectations.map((a) => a.ensemble_code));
  const disponibles = ensembles.filter((e) => !dejaAffectes.has(e.code));
  const resume = el("p", { class: "texte-doux" }, `Besoin ${c.qte_besoin}, affecté ${c.qte_affectee}` + (c.nb_ensembles > 0 && c.ecart_affectation !== 0 ? ` (écart ${c.ecart_affectation > 0 ? "+" : ""}${c.ecart_affectation})` : ""));
  return section(
    "Ensembles où il est monté",
    resume,
    tableSimple([["Ensemble"], ["Qté", "nombre"], ["Montée", "nombre"], ["", "nombre"]], lignes, "Affecté à aucun ensemble pour l'instant."),
    modifiable ? formulaireAffectation(c, disponibles, ensembles.length, surChangement) : null,
  );
}

function formulaireAffectation(c, disponibles, nbEnsembles, surChangement) {
  if (nbEnsembles === 0) {
    return el("p", { class: "texte-doux" }, "Aucun ensemble n'existe encore : ils se créent depuis l'écran Ensembles.");
  }
  if (disponibles.length === 0) return el("p", { class: "texte-doux" }, "Affecté à tous les ensembles existants.");
  const choix = champChoix("ensemble", disponibles.map((e) => [e.code, `${e.code} · ${e.nom}`]), null, { vide: "Ensemble…" });
  const qte = champNombre("qte", Math.max(1, c.ecart_affectation), 0);
  const formulaire = el("form", { class: "formulaire-ligne" }, choix, qte, el("button", { type: "submit", class: "bouton" }, "Affecter"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const quantite = lireNombre(qte.value);
    if (!choix.value) return afficherErreur("Choisir un ensemble.");
    if (quantite === null || Number.isNaN(quantite) || !Number.isInteger(quantite) || quantite <= 0) {
      return afficherErreur("La quantité doit être un entier supérieur à zéro.");
    }
    try {
      await api.createAffectation(choix.value, { composant_id: c.id, qte: quantite });
      masquerErreur();
      await surChangement();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return formulaire;
}

// --- Caractéristiques (attributs paramétrables) ----------------------------------------------

// Champs de saisie : les attributs actifs. Un attribut désactivé garde sa valeur, affichée
// dans la fiche mais plus modifiable.
function champsCaracteristiques(valeurs) {
  return tousLesAttributs()
    .filter((a) => a.actif)
    .map((a) => ({ a, ...champAttribut(a, valeurs[a.code] ?? null) }));
}

// Seules les caractéristiques renseignées s'affichent : un attribut sans objet pour ce
// composant (la tension d'une vis) n'encombre pas la fiche.
function vueCaracteristiques(valeurs) {
  const renseignes = tousLesAttributs().filter((a) => valeurs[a.code] !== undefined && valeurs[a.code] !== null);
  if (!renseignes.length) return null;
  return definitions(renseignes.map((a) => [a.unite ? `${a.libelle} (${a.unite})` : a.libelle, formatAttribut(a, valeurs[a.code])]));
}

function sectionCaracteristiques(valeurs) {
  const vue = vueCaracteristiques(valeurs);
  return vue ? section("Caractéristiques", vue) : null;
}

function sectionCommandes(lignes) {
  return section(
    "Lignes de commande",
    tableSimple(
      [["Commande"], ["Statut"], ["Qté", "nombre"], ["PU HT devis", "nombre"], ["Reçu", "nombre"]],
      lignes.map((l) => el("tr", {}, el("td", {}, l.commande_numero), el("td", {}, `${libelle(l.statut)}, ${libelle(l.statut_ligne)}`), el("td", { class: "nombre" }, formatNombre(l.qte_commandee)), el("td", { class: "nombre" }, formatMontant(l.pu_ht_devis)), el("td", { class: "nombre" }, formatNombre(l.qte_recue)))),
      "Aucune ligne de commande.",
    ),
  );
}

function sectionMouvements(mouvements) {
  return section(
    "Mouvements de stock",
    tableSimple(
      [["Date"], ["Type"], ["Qté", "nombre"], ["Ensemble"], ["Emplacement"]],
      mouvements.map((m) => el("tr", {}, el("td", {}, formatDate(m.date)), el("td", {}, libelle(m.type_mouvement)), el("td", { class: "nombre" }, (m.sens === "Sortie" ? "−" : "+") + formatNombre(m.qte)), el("td", {}, m.ensemble_code ?? ""), el("td", {}, m.emplacement ?? ""))),
      "Aucun mouvement de stock.",
    ),
  );
}

function sectionHistorique(evenements, composant) {
  return section("Historique", frise(evenements, composant));
}

// Fiche d'un composant archivé, en lecture seule : son historique reste consultable,
// notamment celui d'un composant reclassé dans un autre bloc.
function ouvrirFicheArchivee(fiche, documents, surFermeture) {
  const c = fiche.composant;
  const lien = c.lien_produit ? lienExterne(c.lien_produit, "ouvrir la page produit") : null;
  ouvrirPanneau(
    `${c.id} · ${c.designation}`,
    [
      el(
        "p",
        { class: "message message-attention" },
        c.remplace_par ? ["Composant archivé, reclassé : remplacé par ", lienComposant(c.remplace_par), "."] : "Composant archivé : il n'apparaît plus dans les listes ni dans les calculs.",
      ),
      section(
        "Composant",
        definitions([
          ["Bloc", c.bloc_code],
          ["Fonction", c.fonction],
          ["Désignation", c.designation],
          ["Réf fabricant", c.ref_fabricant],
          ["Mode d'appro", libelle(c.mode_appro)],
          ["Fournisseur", c.fournisseur_nom],
          ["Lien produit", lien],
          ["Qté besoin / rechange / déjà dispo.", `${c.qte_besoin} / ${c.qte_rechange} / ${c.qte_disponible}`],
          ["PU relevé", c.pu_releve === null ? null : `${formatMontant(c.pu_releve)} ${c.base_prix_releve}`],
          ["Créé le / modifié le", `${formatDate(c.cree_le)} / ${formatDate(c.modifie_le)}`],
        ]),
      ),
      sectionCaracteristiques(fiche.attributs),
      fiche.affectations.length
        ? section("Affectations conservées", tableSimple([["Ensemble"], ["Qté", "nombre"]], fiche.affectations.map((a) => el("tr", {}, el("td", {}, a.ensemble_code, " ", el("span", { class: "texte-doux" }, a.ensemble_nom)), el("td", { class: "nombre" }, formatNombre(a.qte_affectee)))), ""))
        : null,
      sectionCommandes(fiche.lignes_commande),
      sectionDocuments({ documents, avecSource: true, depot: false, surChangement: () => {} }),
      sectionMouvements(fiche.mouvements),
      sectionHistorique(fiche.historique, c.id),
    ],
    surFermeture,
  );
}

export async function ouvrirFiche(id, { ensembles, fournisseurs, surChangement, surFermeture, surDupliquer }) {
  let fiche;
  let documents;
  try {
    let parametres;
    [fiche, documents, , parametres] = await Promise.all([api.getComposant(id), api.getDocumentsComposant(id), chargerAttributs(), api.getParametres()]);
    champsRequis = new Set((parametres.champs_obligatoires ?? "").split(",").filter(Boolean));
  } catch (erreur) {
    afficherErreur(erreur);
    surFermeture();
    return;
  }
  const c = fiche.composant;
  if (c.archive) return ouvrirFicheArchivee(fiche, documents, surFermeture);
  if (ongletCourant.id !== id) ongletCourant = { id, onglet: "details" };
  // Modifiable par l'administrateur et par les contributeurs du bloc du composant.
  const modifiable = ecritBloc(c.bloc_code);
  const statuts = statutsFournisseurs(fournisseurs);
  const rafraichir = async () => {
    await surChangement();
    await ouvrirFiche(id, { ensembles, fournisseurs, surChangement, surFermeture, surDupliquer });
  };

  const corpsOnglet = el("div", { class: "fiche-onglet" });
  const contenus = {
    details: () => vueDetails(fiche),
    ensembles: () => sectionAffectations(fiche, ensembles, rafraichir, modifiable),
    achats: () => sectionCommandes(fiche.lignes_commande),
    stock: () => sectionMouvements(fiche.mouvements),
    documents: () =>
      sectionDocuments({
        documents,
        avecSource: true,
        typeParDefaut: "Fiche technique",
        aide: "Les documents des commandes où il figure s'affichent aussi ici.",
        deposer: (donnees, progression) => api.deposerDocumentsComposant(id, donnees, progression),
        depot: modifiable,
        surChangement: rafraichir,
      }),
    historique: () => frise(fiche.historique, c.id),
  };
  const titres = [
    ["details", "Détails"],
    ["ensembles", `Ensembles · ${fiche.affectations.length}`],
    ["achats", `Achats · ${fiche.lignes_commande.length}`],
    ["stock", `Stock · ${fiche.mouvements.length}`],
    ["documents", `Documents · ${documents.length}`],
    ["historique", "Historique"],
  ];
  const boutonsOnglets = titres.map(([code, titre]) =>
    el("button", { type: "button", role: "tab", class: "onglet", "data-onglet": code, onclick: () => choisirOnglet(code) }, titre),
  );
  function choisirOnglet(code) {
    ongletCourant.onglet = code;
    for (const bouton of boutonsOnglets) {
      const actif = bouton.dataset.onglet === code;
      bouton.classList.toggle("onglet--actif", actif);
      bouton.setAttribute("aria-selected", String(actif));
    }
    corpsOnglet.replaceChildren(...[contenus[code]()].flat().filter(Boolean));
  }

  // Lecture (suivi, prix, onglets) ou formulaire de modification, à la même place.
  const zone = el("div");
  const lecture = el(
    "div",
    {},
    suivi(fiche, allerA),
    blocPrixFournisseur(c, statuts),
    el("nav", { class: "onglets onglets--fiche", role: "tablist", "aria-label": "Sections de la fiche" }, boutonsOnglets),
    corpsOnglet,
  );
  const boutonModifier = el("button", { type: "button", class: "bouton", onclick: () => modifier() }, "Modifier");
  function modifier() {
    if (!modifiable) return;
    boutonModifier.disabled = true;
    zone.replaceChildren(
      formulaireModif(c, fiche.attributs, fournisseurs, {
        surEnregistre: rafraichir,
        surAnnule: () => {
          boutonModifier.disabled = false;
          zone.replaceChildren(lecture);
        },
      }),
    );
  }
  function allerA(onglet) {
    if (onglet === "modifier") return modifiable ? modifier() : choisirOnglet("details");
    choisirOnglet(contenus[onglet] ? onglet : "details");
  }

  const zoneReclassement = el("div");
  const menuPlus = el(
    "details",
    { class: "menu-plus" },
    el("summary", { class: "bouton bouton--discret" }, "Plus"),
    el(
      "div",
      { class: "menu-plus__liste" },
      estAdmin()
        ? el("button", {
            type: "button",
            class: "bouton-lien",
            title: "Changer de bloc (nouvel identifiant)",
            onclick: () => {
              menuPlus.open = false;
              ouvrirReclassement(c, zoneReclassement, async (nouveau) => {
                await surChangement();
                naviguer("/composants", { fiche: nouveau.id });
              });
            },
          }, "Reclasser dans un autre bloc…")
        : null,
      el("button", {
        type: "button",
        class: "bouton-lien texte-alerte",
        onclick: async () => {
          if (!confirm(`Archiver ${c.id} (${c.designation}) ?\nIl disparaîtra des listes mais restera en base, avec son historique.`)) return;
          try {
            await api.archiveComposant(c.id);
            fermerPanneau();
            await surChangement();
          } catch (erreur) {
            afficherErreur(erreur);
          }
        },
      }, "Archiver"),
    ),
  );
  const boutonDupliquer = el("button", {
    type: "button",
    class: "bouton bouton--discret si-ecriture",
    title: "Créer un composant prérempli avec ces informations",
    onclick: () => surDupliquer({ composant: c, attributs: fiche.attributs }),
  }, "Dupliquer");

  const zoneVisa = el("span", {}, pastilleVisa(fiche.visa));
  ouvrirPanneau(
    c.id,
    [
      el(
        "header",
        { class: "fiche-entete" },
        el("h3", { class: "fiche-entete__titre" }, c.designation),
        el("p", { class: "fiche-entete__sous-titre" }, `Bloc ${c.bloc_code} · ${c.fonction}`),
        el(
          "div",
          { class: "fiche-entete__puces" },
          c.criticite === "Bloquant" ? el("span", { class: "puce-fiche puce-fiche--alerte" }, libelle(c.criticite)) : null,
          zoneVisa,
          pastilleActions(fiche.actions, allerA),
        ),
      ),
      modifiable
        ? el("div", { class: "fiche__actions fiche__actions--gauche" }, boutonModifier, boutonDupliquer, el("span", { class: "fiche__espace" }), menuPlus)
        : el("div", { class: "fiche__actions fiche__actions--gauche" }, el("p", { class: "texte-doux texte-petit" }, `Lecture seule : le bloc ${c.bloc_code} ne vous est pas attribué.`), boutonDupliquer),
      zoneReclassement,
      zone,
    ],
    surFermeture,
  );
  zone.replaceChildren(lecture);
  choisirOnglet(ongletCourant.onglet);
  viserAOuverture(fiche, zoneVisa);
}

// Un responsable qui ouvre la fiche la vise : il a vu le composant tel qu'il est.
async function viserAOuverture(fiche, zoneVisa) {
  if (!aPermission("achats") || fiche.visa?.a_jour) return;
  try {
    await api.viserComposants([fiche.composant.id]);
    zoneVisa.replaceChildren(el("span", { class: "puce-fiche puce-fiche--conforme" }, icone(COCHE), "Visé par vous à l'instant"));
  } catch (erreur) {
    afficherErreur(erreur);
  }
}
