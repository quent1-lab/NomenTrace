// Fiche d'un composant dans le panneau latéral : tous les champs, ses affectations aux
// ensembles (modifiables), ses lignes de commande, ses mouvements et son historique.

import { api } from "../api.js";
import { sectionDocuments } from "../documents.js";
import { formatDate, formatMontant, formatNombre, formatPourcent, libelle, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { lienRoute } from "../router.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { BASES_PRIX, valeursListe } from "../valeurs.js";

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

function vueChamps(c) {
  const lien = c.lien_produit ? el("a", { href: c.lien_produit, target: "_blank", rel: "noopener noreferrer" }, "ouvrir la page produit") : null;
  return [
    definitions([
      ["Bloc fonctionnel", c.bloc_code],
      ["Fonction", c.fonction],
      ["Désignation", c.designation],
      ["Réf fabricant", c.ref_fabricant],
      ["Fabricant", c.fabricant],
      ["Mode d'appro", libelle(c.mode_appro)],
      ["Fournisseur", c.fournisseur_nom],
      ["Lien produit", lien],
    ]),
    definitions([
      ["Qté besoin / rechange / déjà dispo.", `${c.qte_besoin} / ${c.qte_rechange} / ${c.qte_disponible}`],
      ["Qté à acheter", formatNombre(c.qte_a_acheter)],
      ["PU relevé", c.pu_releve === null ? (c.mode_appro === "Achat" ? "à chiffrer" : null) : `${formatMontant(c.pu_releve)} ${c.base_prix_releve}`],
      ["TVA", formatPourcent(c.taux_tva * 100, 1)],
      ["PU HT / TTC", c.pu_ht === null ? null : `${formatMontant(c.pu_ht)} / ${formatMontant(c.pu_ttc)}`],
      ["Total HT / TTC", `${formatMontant(c.total_ht)} / ${formatMontant(c.total_ttc)}`],
      ["Commandé / reçu", `${c.qte_commandee} / ${c.qte_recue}`],
      ["Stock actuel", el("span", { class: c.stock_actuel < 0 ? "texte-alerte" : "" }, formatNombre(c.stock_actuel))],
    ]),
    definitions([
      ["Statut choix", libelle(c.statut_choix)],
      ["Statut appro", libelle(c.statut_appro)],
      ["Criticité", libelle(c.criticite)],
      ["Avancement", libelle(c.avancement)],
      ["Origine exigence", c.origine_exigence],
      ["Créé le / modifié le", `${formatDate(c.cree_le)} / ${formatDate(c.modifie_le)}`],
    ]),
    c.note_technique ? el("div", { class: "fiche__note" }, el("strong", {}, "Note technique"), el("p", {}, c.note_technique)) : null,
  ];
}

function formulaireModif(c, fournisseurs, { surEnregistre, surAnnule }) {
  const base = champChoix("base_prix_releve", BASES_PRIX, c.base_prix_releve);
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Fonction", champTexte("fonction", c.fonction), { requis: true }),
    ligneChamp("Désignation", champTexte("designation", c.designation), { requis: true }),
    ligneChamp("Réf fabricant", champTexte("ref_fabricant", c.ref_fabricant)),
    ligneChamp("Fabricant", champTexte("fabricant", c.fabricant)),
    ligneChamp("Mode d'appro", champChoix("mode_appro", valeursListe("mode_appro", { valeurCourante: c.mode_appro }), c.mode_appro), { requis: true }),
    ligneChamp("Fournisseur", champChoix("fournisseur_nom", fournisseurs.map((f) => [f.nom, f.nom]), c.fournisseur_nom, { vide: "—" })),
    ligneChamp("Lien produit", champTexte("lien_produit", c.lien_produit, { type: "url" })),
    ligneChamp("Qté besoin", champNombre("qte_besoin", c.qte_besoin), { requis: true }),
    ligneChamp("Qté rechange", champNombre("qte_rechange", c.qte_rechange)),
    ligneChamp("Qté déjà disponible", champNombre("qte_disponible", c.qte_disponible)),
    ligneChamp("PU relevé", champNombre("pu_releve", c.pu_releve, 2)),
    ligneChamp("Base du prix", base),
    ligneChamp("Taux de TVA (%)", champNombre("taux_tva", c.taux_tva * 100, 1)),
    ligneChamp("Statut choix", champChoix("statut_choix", valeursListe("statut_choix", { valeurCourante: c.statut_choix }), c.statut_choix, { vide: "—" })),
    ligneChamp("Statut appro", champChoix("statut_appro", valeursListe("statut_appro", { valeurCourante: c.statut_appro }), c.statut_appro)),
    ligneChamp("Criticité", champChoix("criticite", valeursListe("criticite", { valeurCourante: c.criticite }), c.criticite, { vide: "—" })),
    ligneChamp("Origine exigence", champTexte("origine_exigence", c.origine_exigence)),
    ligneChamp("Note technique", champZone("note_technique", c.note_technique)),
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
    const modifs = Object.fromEntries(Object.entries(lu.valeurs).filter(([cle, v]) => v !== c[cle]));
    if (Object.keys(modifs).length === 0) return surAnnule();
    try {
      await api.patchComposant(c.id, modifs);
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

function sectionAffectations(fiche, ensembles, surChangement) {
  const c = fiche.composant;
  const lignes = fiche.affectations.map((a) =>
    el(
      "tr",
      {},
      el("td", {}, el("a", { href: lienRoute(`/ensembles/${a.ensemble_code}`) }, a.ensemble_code), " ", el("span", { class: "texte-doux" }, a.ensemble_nom)),
      el("td", { class: "nombre" }, champQteAffectation(a, surChangement)),
      el("td", { class: "nombre" }, formatNombre(a.qte_montee)),
      el(
        "td",
        { class: "nombre" },
        el("button", {
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
  const resume = el("p", { class: "texte-doux" }, `Besoin : ${c.qte_besoin} — affecté : ${c.qte_affectee}` + (c.nb_ensembles > 0 && c.ecart_affectation !== 0 ? ` (écart ${c.ecart_affectation > 0 ? "+" : ""}${c.ecart_affectation})` : ""));
  return section(
    "Ensembles où il est monté",
    resume,
    tableSimple([["Ensemble"], ["Qté", "nombre"], ["Montée", "nombre"], ["", "nombre"]], lignes, "Affecté à aucun ensemble pour l'instant."),
    formulaireAffectation(c, disponibles, ensembles.length, surChangement),
  );
}

function formulaireAffectation(c, disponibles, nbEnsembles, surChangement) {
  if (nbEnsembles === 0) {
    return el("p", { class: "texte-doux" }, "Aucun ensemble n'existe encore : ils se créent depuis l'écran Ensembles.");
  }
  if (disponibles.length === 0) return el("p", { class: "texte-doux" }, "Affecté à tous les ensembles existants.");
  const choix = champChoix("ensemble", disponibles.map((e) => [e.code, `${e.code} — ${e.nom}`]), null, { vide: "— ensemble —" });
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

function sectionCommandes(lignes) {
  return section(
    "Lignes de commande",
    tableSimple(
      [["Commande"], ["Statut"], ["Qté", "nombre"], ["PU HT devis", "nombre"], ["Reçu", "nombre"]],
      lignes.map((l) => el("tr", {}, el("td", {}, l.commande_numero), el("td", {}, `${libelle(l.statut)} — ${libelle(l.statut_ligne)}`), el("td", { class: "nombre" }, formatNombre(l.qte_commandee)), el("td", { class: "nombre" }, formatMontant(l.pu_ht_devis)), el("td", { class: "nombre" }, formatNombre(l.qte_recue)))),
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

function sectionHistorique(journal) {
  return section(
    "Historique",
    tableSimple(
      [["Date"], ["Champ"], ["Ancienne"], ["Nouvelle"], ["Origine"]],
      journal.map((j) => el("tr", {}, el("td", { class: "code" }, `${formatDate(j.horodatage)} ${j.horodatage.slice(11, 16)}`), el("td", {}, j.table_cible === "affectation" ? `affectation ${j.cle_cible.split(":")[0]}` : j.champ), el("td", {}, j.ancienne_valeur ?? "—"), el("td", {}, j.nouvelle_valeur ?? "—"), el("td", { class: "texte-doux", title: j.nom_fichier ?? "" }, j.nom_fichier ? `import : ${j.nom_fichier}` : j.origine))),
      "Aucune modification enregistrée.",
    ),
  );
}

export async function ouvrirFiche(id, { ensembles, fournisseurs, surChangement, surFermeture }) {
  let fiche;
  let documents;
  try {
    [fiche, documents] = await Promise.all([api.getComposant(id), api.getDocumentsComposant(id)]);
  } catch (erreur) {
    afficherErreur(erreur);
    surFermeture();
    return;
  }
  const c = fiche.composant;
  const rafraichir = async () => {
    await surChangement();
    await ouvrirFiche(id, { ensembles, fournisseurs, surChangement, surFermeture });
  };
  const zoneChamps = el("div", {}, vueChamps(c));
  const boutonModifier = el("button", { type: "button", class: "bouton bouton--discret" }, "Modifier");
  boutonModifier.addEventListener("click", () => {
    boutonModifier.disabled = true;
    zoneChamps.replaceChildren(
      formulaireModif(c, fournisseurs, {
        surEnregistre: rafraichir,
        surAnnule: () => {
          boutonModifier.disabled = false;
          zoneChamps.replaceChildren(...vueChamps(c));
        },
      }),
    );
  });
  const boutonArchiver = el("button", {
    type: "button",
    class: "bouton bouton--danger",
    onclick: async () => {
      if (!confirm(`Archiver ${c.id} — ${c.designation} ?\nIl disparaîtra des listes mais restera en base, avec son historique.`)) return;
      try {
        await api.archiveComposant(c.id);
        fermerPanneau();
        await surChangement();
      } catch (erreur) {
        afficherErreur(erreur);
      }
    },
  }, "Archiver");
  ouvrirPanneau(
    `${c.id} — ${c.designation}`,
    [
      el("div", { class: "fiche__actions" }, boutonModifier, boutonArchiver),
      section("Composant", zoneChamps),
      sectionAffectations(fiche, ensembles, rafraichir),
      sectionCommandes(fiche.lignes_commande),
      sectionDocuments({
        documents,
        avecSource: true,
        typeParDefaut: "Fiche technique",
        aide: "Documents propres au composant (fiche technique, plan, photo) et documents des commandes où il figure.",
        deposer: (donnees) => api.deposerDocumentsComposant(id, donnees),
        surChangement: rafraichir,
      }),
      sectionMouvements(fiche.mouvements),
      sectionHistorique(fiche.journal),
    ],
    surFermeture,
  );
}
