// Commandes communes d'un dossier : panneau de la page du dossier (/d/<code>/) et page d'une
// commune (/d/<code>/#/communes/CC-NNN). Ses lignes vivent dans les projets, son en-tête et
// ses frais dans le dossier ; le serveur calcule la part de chaque projet.

import { api, lienFichierCommune } from "../api.js";
import { sectionDocuments } from "../documents.js";
import { badgeStatut } from "../badges.js";
import { formatDate, formatMontant, formatPourcent, libelle, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire, suivreModifications } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, enregistrerFichier, lienExterne, masquerErreur } from "../ui.js";
import { STATUTS_COMMANDE, TYPES_COMMANDE } from "../valeurs.js";
import { ouvrirSuivi } from "../pages/achats_suivi.js";
import { afficherCompte, formulairePanneau } from "./elements.js";

// Livré et Livré partiel se déduisent des réceptions : on ne les choisit pas.
const STATUTS_CHOISIS = STATUTS_COMMANDE.filter((s) => !["Livre partiel", "Livre"].includes(s));

export function adresseCommune(dossier, numero) {
  return `/d/${dossier}/#/communes/${numero}`;
}

function champDate(nom, valeur) {
  return el("input", { class: "champ champ--date", type: "date", name: nom, value: valeur ?? "" });
}

async function agir(action) {
  try {
    await action();
    masquerErreur();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

// --- Panneau de la page du dossier ---------------------------------------------------------------

async function nouvelleCommune(code) {
  const fournisseurs = await api.getFournisseursCommune(code);
  const formulaire = formulairePanneau(
    [
      ["Fournisseur", champChoix("fournisseur_nom", fournisseurs.map((f) => [f, f]), null, { vide: "Choisir un fournisseur" }), { requis: true, aide: "Liste de l'organisme." }],
      ["Type", champChoix("type", TYPES_COMMANDE, "Commande")],
      ["Statut", champChoix("statut", STATUTS_CHOISIS, "A demander")],
      ["Demandée par", champTexte("demande_par", "")],
      ["Référence externe", champTexte("reference_externe", "")],
      ["Commentaire", champZone("commentaire", "")],
    ],
    "Créer la commande",
    async (champs) => {
      if (!champs.fournisseur_nom.value) throw new Error("Choisir un fournisseur.");
      const valeurs = { fournisseur_nom: champs.fournisseur_nom.value, type: champs.type.value, statut: champs.statut.value };
      for (const nom of ["demande_par", "reference_externe", "commentaire"]) {
        const texte = champs[nom].value.trim();
        if (texte) valeurs[nom] = texte;
      }
      const cree = await api.createCommune(code, valeurs);
      fermerPanneau({ silencieux: true });
      window.location.assign(adresseCommune(code, cree.numero));
    },
  );
  ouvrirPanneau("Nouvelle commande commune", formulaire);
}

function ligneListe(code, c) {
  return el(
    "tr",
    {},
    el("td", { class: "code" }, el("a", { href: adresseCommune(code, c.numero) }, c.numero)),
    el("td", {}, c.fournisseur_nom),
    el("td", {}, c.projets.join(", ") || el("span", { class: "texte-doux" }, "aucun")),
    el("td", {}, badgeStatut({ statut: c.statut_affiche })),
    el("td", {}, formatDate(c.livraison_annoncee) || "—"),
    el("td", { class: "nombre" }, formatMontant(c.estime_ht ?? 0)),
    el("td", { class: "nombre" }, c.montant_commande_ht == null ? "—" : formatMontant(c.montant_commande_ht)),
  );
}

export function panneauCommunes(code) {
  const section = el("section", { class: "panneau" }, el("h2", {}, "Commandes communes"), el("p", { class: "texte-doux" }, "Chargement…"));
  api
    .getCommunes(code)
    .then(({ acheteur, communes }) => {
      const entetes = ["Numéro", "Fournisseur", "Projets", "Statut", "Livraison annoncée", "Estimé HT", "Réel HT"];
      section.replaceChildren(
        el(
          "div",
          { class: "titre-section" },
          el("h2", {}, "Commandes communes"),
          acheteur
            ? el("div", { class: "actions" },
                el("button", { type: "button", class: "bouton bouton--discret", onclick: () => ouvrirSuivi(() => window.location.reload(), { analyser: (d, p) => api.analyserSuiviCommunes(code, d, p), appliquer: (d) => api.appliquerSuiviCommunes(code, d) }) }, "Suivi de l'établissement"),
                el("button", { type: "button", class: "bouton", onclick: () => nouvelleCommune(code).catch(afficherErreur) }, "Nouvelle commande commune"),
              )
            : null,
        ),
        communes.length
          ? el(
              "div",
              { class: "table-defilante" },
              el(
                "table",
                { class: "table" },
                el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: i >= 5 ? "nombre" : "" }, t)))),
                el("tbody", {}, communes.map((c) => ligneListe(code, c))),
              ),
            )
          : el("p", { class: "texte-doux" }, "Aucune commande commune."),
        el("p", { class: "texte-doux texte-petit" }, "Chaque projet compte sa part dans son engagé. Les membres des projets voient la commande en lecture seule."),
      );
    })
    .catch((erreur) => {
      section.replaceChildren(el("h2", {}, "Commandes communes"), el("p", { class: "texte-doux" }, erreur.message));
    });
  return section;
}

// --- Page d'une commune --------------------------------------------------------------------------

let etat = null;

// Une commune passée (Commandé ou Livré partiel) se réceptionne.
function receptionnable(c) {
  return c.type === "Commande" && ["Commande", "Livre partiel"].includes(c.statut_affiche) && c.projets.some((p) => p.lignes.some((l) => l.statut_ligne !== "Annulee"));
}

async function recharger() {
  etat.commune = await api.getCommune(etat.code, etat.numero);
  rendre();
}

function modifier() {
  const c = etat.commune;
  const description = {
    type: "choix",
    statut: "choix",
    demande_par: "texte",
    reference_externe: "texte",
    date_demande: "texte",
    date_reception_devis: "texte",
    date_commande: "texte",
    livraison_annoncee: "texte",
    taux_tva: "taux",
    date_transmission_suivi: "texte",
    montant_commande_ht: "montant",
    date_reception_annoncee: "texte",
    commentaire_suivi: "texte",
    lien_document: "texte",
    commentaire: "texte",
  };
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    el("fieldset", {}, el("legend", {}, "Commande"),
      ligneChamp("Type", champChoix("type", TYPES_COMMANDE, c.type)),
      ligneChamp("Statut", champChoix("statut", STATUTS_CHOISIS, STATUTS_CHOISIS.includes(c.statut) ? c.statut : "Commande"), { aide: "Livré et Livré partiel suivent les réceptions." }),
      ligneChamp("Demandée par", champTexte("demande_par", c.demande_par)),
      ligneChamp("Référence externe", champTexte("reference_externe", c.reference_externe)),
    ),
    el("fieldset", {}, el("legend", {}, "Dates"),
      ligneChamp("Demande", champDate("date_demande", c.date_demande)),
      ligneChamp("Réception du devis", champDate("date_reception_devis", c.date_reception_devis)),
      ligneChamp("Commande", champDate("date_commande", c.date_commande), { aide: "Renseignée automatiquement au passage en Commande si vide." }),
      ligneChamp("Livraison annoncée", champDate("livraison_annoncee", c.livraison_annoncee)),
    ),
    ligneChamp("Taux de TVA (%)", champNombre("taux_tva", c.taux_tva * 100, 1)),
    el("fieldset", {}, el("legend", {}, "Suivi de l'établissement"),
      ligneChamp("Transmise au suivi le", champDate("date_transmission_suivi", c.date_transmission_suivi)),
      ligneChamp("Montant réel HT", champNombre("montant_commande_ht", c.montant_commande_ht ?? null, 2), { aide: "Frais compris ; réparti entre les projets au prorata de leur estimé." }),
      ligneChamp("Réception annoncée", champDate("date_reception_annoncee", c.date_reception_annoncee)),
      ligneChamp("Commentaire", champTexte("commentaire_suivi", c.commentaire_suivi)),
    ),
    ligneChamp("Lien du document", champTexte("lien_document", c.lien_document, { type: "url" })),
    ligneChamp("Commentaire", champZone("commentaire", c.commentaire)),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, description, { taux_tva: "Taux de TVA", montant_commande_ht: "Montant réel" });
    if (lu.erreur) return afficherErreur(lu.erreur);
    const modifs = Object.fromEntries(Object.entries(lu.valeurs).filter(([k, v]) => v !== c[k]));
    agir(async () => {
      await api.patchCommune(etat.code, etat.numero, modifs);
      fermerPanneau({ silencieux: true });
      await recharger();
    });
  });
  suivreModifications(formulaire);
  ouvrirPanneau(`Modifier ${c.numero}`, formulaire);
}

function archiver() {
  if (!confirm(`Archiver la commande commune ${etat.numero} ? Ses copies dans les projets sont archivées aussi.`)) return;
  agir(async () => {
    await api.archiveCommune(etat.code, etat.numero);
    window.location.assign(`/d/${etat.code}/`);
  });
}

// Ajout de composants : reste à commander chez ce fournisseur, coché par projet, puis à la main.
async function ajouterComposants() {
  const c = etat.commune;
  const projets = await api.getCandidatsCommune(etat.code, etat.numero);
  const presents = new Set(c.projets.map((p) => p.projet));
  const cases = [];
  const groupes = projets.flatMap((p) => {
    const candidats = p.composants.filter((k) => k.fournisseur_nom === c.fournisseur_nom && k.reste_a_commander > 0);
    if (!candidats.length) return [];
    return [
      el("tr", { class: "ligne-groupe" }, el("td", { colspan: 6 }, p.nom, presents.has(p.projet) ? null : el("span", { class: "texte-doux" }, " · rejoindra la commande"))),
      ...candidats.map((k) => {
        const coche = el("input", { type: "checkbox", "aria-label": `Choisir ${k.id}` });
        const qte = champNombre("qte", k.reste_a_commander, 0, { "aria-label": "Quantité" });
        cases.push({ projet: p.projet, composant: k, coche, qte });
        return el("tr", {}, el("td", {}, coche), el("td", { class: "code" }, k.id), el("td", {}, k.designation), el("td", { class: "nombre" }, String(k.reste_a_commander)), el("td", { class: "nombre" }, qte), el("td", { class: "nombre" }, formatMontant(k.pu_ht)));
      }),
    ];
  });
  const choixProjet = champChoix("projet", projets.map((p) => [p.projet, p.nom]), null, { vide: "Choisir un projet" });
  const choixComposant = champChoix("composant", [], null, { vide: "Choisir d'abord le projet" });
  choixProjet.addEventListener("change", () => {
    const projet = projets.find((p) => p.projet === choixProjet.value);
    choixComposant.replaceChildren(el("option", { value: "" }, "Choisir un composant"), ...(projet?.composants ?? []).map((k) => el("option", { value: k.id }, `${k.id} · ${k.designation}`)));
  });
  const qteMain = champNombre("qte_main", null, 0);
  const puMain = champNombre("pu_main", null, 2, { placeholder: "€ HT" });
  const envoyer = () =>
    agir(async () => {
      const lignes = cases
        .filter((x) => x.coche.checked)
        .map((x) => ({ projet: x.projet, composant_id: x.composant.id, qte_commandee: lireNombre(x.qte.value), pu_ht_devis: x.composant.pu_ht ?? null }));
      if (choixComposant.value) {
        lignes.push({ projet: choixProjet.value, composant_id: choixComposant.value, qte_commandee: lireNombre(qteMain.value), pu_ht_devis: lireNombre(puMain.value) });
      }
      if (!lignes.length) throw new Error("Cocher au moins un composant ou en choisir un à la main.");
      if (lignes.some((l) => !Number.isInteger(l.qte_commandee) || l.qte_commandee <= 0)) throw new Error("Chaque quantité doit être un entier positif.");
      await api.addLignesCommune(etat.code, etat.numero, lignes);
      fermerPanneau({ silencieux: true });
      await recharger();
    });
  ouvrirPanneau(
    `Ajouter des composants à ${c.numero}`,
    el(
      "div",
      { class: "formulaire" },
      el("h3", { class: "sous-titre" }, `Reste à commander chez ${c.fournisseur_nom}`),
      groupes.length
        ? el("div", { class: "table-defilante" }, el("table", { class: "table table--dense" }, el("thead", {}, el("tr", {}, ["", "Composant", "Désignation", "Reste", "Qté", "PU estimé"].map((t, i) => el("th", { class: i >= 3 ? "nombre" : "" }, t)))), el("tbody", {}, groupes)))
        : el("p", { class: "texte-doux" }, "Aucun composant de ce fournisseur ne reste à commander."),
      el("h3", { class: "sous-titre" }, "Ajouter à la main"),
      ligneChamp("Projet", choixProjet),
      ligneChamp("Composant", choixComposant, { aide: "Tout composant acheté du projet, quel que soit son fournisseur." }),
      ligneChamp("Quantité", qteMain),
      ligneChamp("PU du devis HT", puMain),
      el("div", { class: "actions-formulaire" },
        el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
        el("button", { type: "button", class: "bouton", onclick: envoyer }, "Ajouter les lignes"),
      ),
    ),
  );
}

function modifierLigne(projet, ligne) {
  const formulaire = formulairePanneau(
    [
      ["Quantité", champNombre("qte_commandee", ligne.qte_commandee, 0), { requis: true }],
      ["PU du devis HT", champNombre("pu_ht_devis", ligne.pu_ht_devis, 2)],
      ["Commentaire", champTexte("commentaire", ligne.commentaire)],
    ],
    "Enregistrer",
    async (champs) => {
      const qte = lireNombre(champs.qte_commandee.value);
      const pu = lireNombre(champs.pu_ht_devis.value);
      if (!Number.isInteger(qte) || qte <= 0) throw new Error("La quantité doit être un entier positif.");
      if (Number.isNaN(pu)) throw new Error("PU illisible.");
      await api.patchLigneCommune(etat.code, etat.numero, projet.projet, ligne.id, { qte_commandee: qte, pu_ht_devis: pu, commentaire: champs.commentaire.value.trim() || null });
      fermerPanneau({ silencieux: true });
      await recharger();
    },
  );
  suivreModifications(formulaire);
  ouvrirPanneau(`${ligne.composant_id} · ${projet.nom}`, formulaire);
}

function actionsLigne(projet, ligne) {
  if (!etat.commune.acheteur || etat.commune.archive) return el("td");
  const annulee = ligne.statut_ligne === "Annulee";
  const basculer = () =>
    agir(async () => {
      const statut = annulee ? "A commander" : "Annulee";
      await api.patchLigneCommune(etat.code, etat.numero, projet.projet, ligne.id, { statut_ligne: statut });
      await recharger();
    });
  const supprimer = () => {
    if (!confirm(`Supprimer la ligne ${ligne.composant_id} ?`)) return;
    agir(async () => {
      await api.deleteLigneCommune(etat.code, etat.numero, projet.projet, ligne.id);
      await recharger();
    });
  };
  return el(
    "td",
    { class: "nombre actions-ligne" },
    annulee ? null : el("button", { type: "button", class: "bouton-lien", onclick: () => modifierLigne(projet, ligne) }, "Modifier"),
    " ",
    el("button", { type: "button", class: "bouton-lien", onclick: basculer }, annulee ? "Rétablir" : "Annuler"),
    " ",
    ligne.qte_recue > 0 ? null : el("button", { type: "button", class: "bouton-lien texte-alerte", onclick: supprimer }, "Supprimer"),
  );
}

function lignesProjet(p) {
  const part = p.part;
  const titre = el("tr", { class: "ligne-groupe" }, el("td", { colspan: 8 }, p.nom, el("span", { class: "texte-doux" }, ` · dans le projet : ${p.numero_local}`), p.hors_ligne ? el("span", { class: "etiquette etiquette--attention" }, "hors ligne") : null));
  const lignes = p.lignes.map((l) =>
    el(
      "tr",
      { class: l.statut_ligne === "Annulee" ? "texte-doux" : "" },
      el("td", { class: "code" }, l.composant_id),
      el("td", {}, l.designation ?? "—"),
      el("td", { class: "nombre" }, String(l.qte_commandee)),
      el("td", { class: "nombre" }, l.pu_ht_devis == null ? el("span", { class: "etiquette etiquette--attention" }, "sans prix") : formatMontant(l.pu_ht_devis)),
      el("td", { class: "nombre" }, l.pu_ht_devis == null ? "—" : formatMontant(l.qte_commandee * l.pu_ht_devis)),
      el("td", {}, libelle(l.statut_ligne)),
      el("td", { class: "nombre" }, `${l.qte_recue} / ${l.qte_commandee}`),
      actionsLigne(p, l),
    ),
  );
  const resume = part
    ? el("tr", { class: "ligne-resume" }, el("td", { colspan: 8, class: "texte-doux texte-petit" },
        `Lignes ${formatMontant(part.lignes_ht)} · part des frais ${formatMontant(part.frais_ht)} · estimé ${formatMontant(part.estime_ht)}`,
        part.reel_ht == null ? null : el("strong", {}, ` · part du réel ${formatMontant(part.reel_ht)}`),
      ))
    : null;
  return [titre, ...lignes, resume];
}

function sectionLignes() {
  const c = etat.commune;
  const sansPrix = c.projets.reduce((s, p) => s + (p.part?.sans_prix ?? 0), 0);
  const entetes = ["Composant", "Désignation", "Qté", "PU HT", "Total HT", "Ligne", "Reçu", ""];
  return el(
    "section",
    { class: "panneau" },
    el(
      "div",
      { class: "titre-section" },
      el("h2", {}, "Lignes, par projet"),
      c.acheteur && !c.archive ? el("button", { type: "button", class: "bouton", onclick: () => ajouterComposants().catch(afficherErreur) }, "Ajouter des composants") : null,
    ),
    c.projets.length
      ? el(
          "div",
          { class: "table-defilante" },
          el("table", { class: "table table--dense" }, el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: [2, 3, 4, 6].includes(i) ? "nombre" : "" }, t)))), el("tbody", {}, c.projets.flatMap(lignesProjet))),
        )
      : el("p", { class: "texte-doux" }, "Aucune ligne pour l'instant."),
    sansPrix ? el("p", { class: "texte-doux texte-petit" }, "Une ligne sans prix compte 0 dans l'estimé et fausse la répartition du réel : saisir son PU.") : null,
  );
}

function formulaireFrais() {
  const c = etat.commune;
  const actifs = c.types_frais.filter((t) => t.actif);
  const type = champChoix("type_frais", actifs.map((t) => [t.code, t.libelle]), actifs[0]?.code ?? null);
  const montant = champNombre("montant_ht", null, 2, { placeholder: "€ HT", "aria-label": "Montant HT" });
  const commentaire = champTexte("commentaire", "", { placeholder: "Commentaire", "aria-label": "Commentaire" });
  const ajouter = () =>
    agir(async () => {
      const valeur = lireNombre(montant.value);
      if (valeur === null || Number.isNaN(valeur) || valeur < 0) throw new Error("Montant du frais illisible.");
      await api.createFraisCommune(etat.code, etat.numero, { type_frais: type.value, montant_ht: valeur, commentaire: commentaire.value.trim() || null });
      await recharger();
    });
  return el("div", { class: "formulaire-ligne" }, type, montant, commentaire, el("button", { type: "button", class: "bouton bouton--discret", onclick: ajouter }, "Ajouter un frais"));
}

function sectionFrais() {
  const c = etat.commune;
  const libelles = Object.fromEntries(c.types_frais.map((t) => [t.code, t.libelle]));
  const n = c.nb_presents;
  const retirer = (f) =>
    agir(async () => {
      await api.deleteFraisCommune(etat.code, etat.numero, f.id);
      await recharger();
    });
  const entetes = ["Type", "Commentaire", "Montant HT", n ? `Par projet (${n})` : "Par projet", ""];
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Frais"),
    c.frais.length
      ? el(
          "table",
          { class: "table table--dense" },
          el("thead", {}, el("tr", {}, entetes.map((t, i) => el("th", { class: [2, 3].includes(i) ? "nombre" : "" }, t)))),
          el("tbody", {}, c.frais.map((f) =>
            el("tr", {},
              el("td", {}, libelles[f.type_frais] ?? f.type_frais),
              el("td", {}, f.commentaire ?? "—"),
              el("td", { class: "nombre" }, formatMontant(f.montant_ht)),
              el("td", { class: "nombre" }, n ? formatMontant(f.montant_ht / n) : "—"),
              el("td", { class: "nombre" }, c.acheteur && !c.archive ? el("button", { type: "button", class: "bouton-lien texte-alerte", onclick: () => retirer(f) }, "Retirer") : null),
            ),
          )),
        )
      : el("p", { class: "texte-doux" }, "Aucun frais."),
    c.acheteur && !c.archive ? formulaireFrais() : null,
  );
}

function infos() {
  const c = etat.commune;
  const paires = [
    ["Fournisseur", c.fournisseur_nom],
    ["Demandée par", c.demande_par || "—"],
    ["Commandée le", formatDate(c.date_commande) || "—"],
    ["Livraison annoncée", formatDate(c.livraison_annoncee) || "—"],
    ["Réception réelle", formatDate(c.date_reception_reelle) || "—"],
    ["TVA", formatPourcent(c.taux_tva * 100, 1)],
    ["Référence", c.reference_externe || "—"],
    ["Document", c.lien_document ? lienExterne(c.lien_document, "Ouvrir") : "—"],
  ];
  return el(
    "section",
    { class: "panneau" },
    el("dl", { class: "infos-commune" }, paires.flatMap(([t, v]) => [el("dt", {}, t), el("dd", {}, v)])),
    c.commentaire ? el("p", { class: "texte-doux" }, c.commentaire) : null,
    blocSuivi(),
  );
}

function explicationReel(c) {
  if (c.montant_commande_ht == null) return "Le montant réel, lu dans le suivi de l'établissement ou saisi dans « Modifier », sera réparti entre les projets.";
  if (c.mode_reel === "lignes") return "Réel lu ligne par ligne dans le suivi de l'établissement : chaque projet a la somme de ses lignes, plus sa part des frais.";
  return "Réel pour toute la commande, réparti au prorata de l'estimé. Frais à parts égales entre les projets présents.";
}

function repartition() {
  const c = etat.commune;
  const presents = c.projets.filter((p) => p.part);
  if (!presents.length) return null;
  const reel = c.montant_commande_ht;
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Répartition"),
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, el("th", {}, "Projet"), el("th", { class: "nombre" }, "Estimé"), el("th", { class: "nombre" }, "Part du réel"))),
      el(
        "tbody",
        {},
        presents.map((p) => el("tr", {}, el("td", {}, p.nom), el("td", { class: "nombre" }, formatMontant(p.part.estime_ht)), el("td", { class: "nombre" }, p.part.reel_ht == null ? "—" : formatMontant(p.part.reel_ht)))),
        el("tr", { class: "fort" }, el("td", {}, "Total"), el("td", { class: "nombre" }, formatMontant(c.estime_ht)), el("td", { class: "nombre" }, reel == null ? "—" : formatMontant(reel))),
      ),
    ),
    el("p", { class: "texte-doux texte-petit" }, explicationReel(c)),
  );
}

// Réception depuis la commune : chaque ligne part dans la base de son projet. La quantité
// déjà reçue lue ici accompagne la saisie : une réception faite entre-temps dans un projet
// est refusée plutôt que comptée deux fois.
function sectionReception() {
  const c = etat.commune;
  const champs = [];
  const corps = c.projets.flatMap((p) => {
    const lignes = p.lignes.filter((l) => l.statut_ligne !== "Annulee");
    if (!lignes.length) return [];
    return [
      el("tr", { class: "ligne-groupe" }, el("td", { colspan: 5 }, p.nom)),
      ...lignes.map((l) => {
        const reste = Math.max(0, l.qte_commandee - l.qte_recue);
        const champ = el("input", { class: "champ-cellule champ-cellule--nombre", type: "text", inputmode: "numeric", value: String(reste), "aria-label": `Reçu pour ${l.composant_id}` });
        champs.push({ projet: p.projet, ligne: l, champ });
        return el("tr", {}, el("td", { class: "code" }, l.composant_id), el("td", {}, l.designation ?? "—"), el("td", { class: "nombre" }, String(l.qte_commandee)), el("td", { class: "nombre" }, String(l.qte_recue)), el("td", { class: "nombre" }, champ));
      }),
    ];
  });
  const date = champDate("date", new Date().toISOString().slice(0, 10));
  const emplacement = champTexte("emplacement", "", { placeholder: "ex. Armoire A - bac 3" });
  const valider = () =>
    agir(async () => {
      const lignes = [];
      for (const { projet, ligne, champ } of champs) {
        const n = lireNombre(champ.value);
        if (n === null || n === 0) continue;
        if (Number.isNaN(n) || !Number.isInteger(n) || n < 0) throw new Error(`Quantité reçue invalide : « ${champ.value} ».`);
        lignes.push({ projet, id: ligne.id, qte: n, qte_recue_lue: ligne.qte_recue });
      }
      if (!lignes.length) throw new Error("Aucune quantité reçue n'a été saisie.");
      const resultat = await api.receptionnerCommune(etat.code, etat.numero, { date: date.value || null, emplacement: emplacement.value.trim() || null, lignes });
      etat.reception = false;
      etat.commune = resultat;
      rendre();
      if (resultat.avertissements?.length) afficherErreur(new Error(resultat.avertissements.join(" ")));
    });
  return el(
    "section",
    { class: "panneau panneau--reception" },
    el("h2", {}, "Réception de la livraison"),
    el("p", { class: "texte-doux" }, "La quantité reçue s'ajoute aux réceptions précédentes ; chaque ligne entre dans le stock de son projet."),
    el("div", { class: "formulaire-ligne" }, el("label", { class: "ligne-compacte" }, "Date ", date), el("label", { class: "ligne-compacte" }, "Emplacement ", emplacement)),
    el("div", { class: "table-defilante" }, el("table", { class: "table table--dense" },
      el("thead", {}, el("tr", {}, ["Composant", "Désignation", "Commandé", "Déjà reçu", "Reçu cette fois"].map((t, i) => el("th", { class: i >= 2 ? "nombre" : "" }, t)))),
      el("tbody", {}, corps),
    )),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => { etat.reception = false; rendre(); } }, "Annuler"),
      el("button", { type: "button", class: "bouton", onclick: valider }, "Valider la réception"),
    ),
  );
}

// Documents : joints à la copie de chaque projet, montrés ici une fois chacun.
function panneauDocuments() {
  const c = etat.commune;
  const premiere = (d) => d.copies[0];
  return el(
    "section",
    { class: "panneau" },
    sectionDocuments({
      documents: c.documents,
      typeParDefaut: c.type === "Devis" ? "Devis" : "Bon de commande",
      aide: c.projets.length ? "Joints à la commande de chaque projet ; ils apparaissent aussi dans la fiche de chaque composant." : "Ajouter d'abord des lignes : un document se joint aux projets de la commande.",
      depot: c.acheteur && !c.archive && c.projets.length > 0,
      deposer: (donnees, progression) => api.deposerDocumentsCommune(etat.code, etat.numero, donnees, progression),
      surChangement: recharger,
      lien: (d) => lienFichierCommune(etat.code, etat.numero, premiere(d).projet, premiere(d).id),
      retirer: (d) => api.retirerDocumentCommune(etat.code, etat.numero, d.empreinte),
    }),
  );
}

// Demande de devis au fournisseur : les articles de tous les projets, regroupés.
function demandeDevis() {
  const c = etat.commune;
  if (!c.acheteur || !c.projets.length) return null;
  const avant = el("input", { class: "champ champ--date", type: "date", "aria-label": "Réponse souhaitée avant le" });
  const telecharger = (format) => () =>
    agir(async () => enregistrerFichier(await api.telechargerDemandeDevisCommune(etat.code, etat.numero, format, avant.value || null)));
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Demande au fournisseur"),
    el("p", { class: "texte-doux texte-petit" }, "Les articles de tous les projets, un même article regroupé ; aucun prix."),
    el("div", { class: "formulaire-ligne formulaire-ligne--repli" },
      el("label", { class: "ligne-compacte" }, "Réponse avant le ", avant),
      el("button", { type: "button", class: "bouton bouton--discret", onclick: telecharger("pdf") }, "PDF"),
      el("button", { type: "button", class: "bouton bouton--discret", onclick: telecharger("xlsx") }, "Excel"),
    ),
  );
}

// Transmission au suivi de l'établissement : la commune y entrera au prochain passage du
// fichier (bouton « Suivi de l'établissement » de la page du dossier).
function blocSuivi() {
  const c = etat.commune;
  if (c.date_transmission_suivi) return el("p", { class: "texte-doux texte-petit" }, `Transmise au suivi de l'établissement le ${formatDate(c.date_transmission_suivi)}.`);
  if (!c.acheteur || c.archive || !c.projets.length) return null;
  const transmettre = () =>
    agir(async () => {
      await api.patchCommune(etat.code, etat.numero, { date_transmission_suivi: new Date().toISOString().slice(0, 10) });
      await recharger();
    });
  return el("p", { class: "texte-doux texte-petit" }, "Pas encore transmise au suivi de l'établissement. ", el("button", { type: "button", class: "bouton bouton--petit", onclick: transmettre }, "Transmettre au suivi"));
}

function rendre() {
  const c = etat.commune;
  document.title = `${c.numero} · Nomentrace`;
  etat.fil.replaceChildren(
    el("a", { href: `/o/${c.nom_dossier.organisme}/` }, c.nom_dossier.nom_organisme),
    " › ",
    el("a", { href: `/d/${etat.code}/` }, c.nom_dossier.nom),
    ` › ${c.numero}`,
  );
  const blocs = [
    el(
      "div",
      { class: "titre-section" },
      el("h1", {}, `${c.numero} `, el("span", { class: "etiquette" }, c.type), " ", badgeStatut({ statut: c.statut_affiche }), c.archive ? el("span", { class: "etiquette" }, " archivée") : null),
      el("span", { class: "texte-doux" }, `commande commune · ${c.fournisseur_nom}`),
      c.acheteur && !c.archive
        ? el("div", { class: "actions" },
            receptionnable(c) && !etat.reception ? el("button", { type: "button", class: "bouton", onclick: () => { etat.reception = true; rendre(); } }, "Réceptionner") : null,
            el("button", { type: "button", class: "bouton bouton--discret", onclick: modifier }, "Modifier"),
            el("button", { type: "button", class: "bouton bouton--danger", onclick: archiver }, "Archiver"),
          )
        : null,
    ),
    c.manquants.length
      ? el("div", { class: "bandeau-avertissement" }, `Projets hors ligne : ${c.manquants.join(", ")}. La répartition n'est pas mise à jour tant qu'ils ne sont pas revenus.`)
      : null,
    el(
      "div",
      { class: "commun__colonnes commun__colonnes--commune" },
      el("div", { class: "commun__principal" }, etat.reception ? sectionReception() : sectionLignes(), sectionFrais(), panneauDocuments()),
      el("aside", { class: "commun__cote" }, infos(), repartition(), demandeDevis()),
    ),
  ];
  etat.contenu.replaceChildren(...blocs.filter(Boolean));
}

export async function afficherCommune(code, numero, { contenu, fil }) {
  etat = { code, numero, contenu, fil, commune: null, reception: false };
  etat.commune = await api.getCommune(code, numero);
  afficherCompte(etat.commune.compte);
  rendre();
}
