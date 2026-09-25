// Onglets « Blocs », « Ensembles » et « Fournisseurs » des paramètres.

import { api } from "../api.js";
import { formatMontant, formatNombre, libelle } from "../format.js";
import { champNombre, champTexte, champZone, lireFormulaire, ligneChamp } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, classeBloc, el, lienProduit, masquerErreur, rangsBlocs } from "../ui.js";
import { naviguer } from "../router.js";
import { ouvrirFormulaireEnsemble } from "./ensembles_commun.js";
import { afficherComparaison } from "./fournisseurs_comparaison.js";
import { A_VALIDER, archiverFournisseur, lienFournisseur, ouvrirFormulaireFournisseur, routeFournisseur } from "./fournisseurs_commun.js";

function table(entetes, lignes, vide) {
  if (!lignes.length) return el("p", { class: "texte-doux" }, vide);
  return el(
    "table",
    { class: "table table--dense table--parametres" },
    el("thead", {}, el("tr", {}, entetes.map(([texte, classe]) => el("th", { class: classe }, texte)))),
    el("tbody", {}, lignes),
  );
}

function boutonsFormulaire(texte) {
  return el(
    "div",
    { class: "actions-formulaire" },
    el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
    el("button", { type: "submit", class: "bouton" }, texte),
  );
}

// Envoie le formulaire, ferme le panneau et rafraîchit l'onglet ; l'erreur reste affichée sinon.
function surSoumission(formulaire, envoyer, rafraichir) {
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      if ((await envoyer()) === false) return;
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
}

// --- Blocs fonctionnels ---------------------------------------------------------------------

const DESCRIPTION_BLOC = { nom: "texte", ordre: "entier", budget_cible_ht: "montant", responsable: "texte", description: "texte" };
const LIBELLES_BLOC = { ordre: "Ordre d'affichage", budget_cible_ht: "Budget cible HT" };

function ouvrirFormulaireBloc(bloc, ordreSuggere, rafraichir) {
  const creation = bloc === null;
  const code = champTexte("code", bloc?.code ?? "", { disabled: !creation, maxlength: "4", autocomplete: "off" });
  code.addEventListener("input", () => {
    code.value = code.value.toUpperCase().replace(/[^A-Z]/g, "");
  });
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Code", code, {
      requis: true,
      aide: creation
        ? "2 à 4 lettres majuscules. Il entre dans l'identifiant de chaque composant du bloc et ne pourra plus être modifié."
        : "Le code d'un bloc est figé dans les identifiants de ses composants.",
    }),
    ligneChamp("Nom", champTexte("nom", bloc?.nom ?? ""), { requis: true }),
    ligneChamp("Ordre d'affichage", champNombre("ordre", bloc?.ordre ?? ordreSuggere)),
    ligneChamp("Budget cible HT", champNombre("budget_cible_ht", bloc?.budget_cible_ht ?? null, 2), { aide: "Laisser vide si le bloc n'a pas de budget propre." }),
    ligneChamp("Responsable", champTexte("responsable", bloc?.responsable ?? "")),
    ligneChamp("Description", champZone("description", bloc?.description ?? "")),
    boutonsFormulaire(creation ? "Créer le bloc" : "Enregistrer"),
  );
  surSoumission(
    formulaire,
    async () => {
      const lu = lireFormulaire(formulaire, DESCRIPTION_BLOC, LIBELLES_BLOC);
      if (lu.erreur) throw new Error(lu.erreur);
      if (creation && !/^[A-Z]{2,4}$/.test(code.value)) throw new Error("Le code du bloc doit compter 2 à 4 lettres majuscules.");
      if (!lu.valeurs.nom) throw new Error("Le nom du bloc est obligatoire.");
      if (creation) return api.createBloc({ code: code.value, ...lu.valeurs });
      return api.patchBloc(bloc.code, lu.valeurs);
    },
    rafraichir,
  );
  ouvrirPanneau(creation ? "Nouveau bloc fonctionnel" : `Modifier le bloc ${bloc.code}`, formulaire);
  (creation ? code : formulaire.elements.namedItem("nom")).focus();
}

export async function afficherOngletBlocs(cible) {
  const rafraichir = () => afficherOngletBlocs(cible);
  const blocs = await api.getBlocs({ archives: true });
  const rangs = rangsBlocs(blocs.filter((b) => !b.archive));
  const basculerArchive = async (b) => {
    const archiver = !b.archive;
    const message = archiver
      ? `Archiver le bloc « ${b.code} — ${b.nom} » ?

Il ne sera plus proposé à la création de composant. Il peut être réactivé ensuite.`
      : `Réactiver le bloc « ${b.code} — ${b.nom} » ?`;
    if (!confirm(message)) return;
    try {
      await api.patchBloc(b.code, { archive: archiver ? 1 : 0 });
      masquerErreur();
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const ordreSuggere = Math.max(0, ...blocs.map((b) => b.ordre)) + 1;
  const lignes = blocs.map((b) =>
    el(
      "tr",
      { class: b.archive ? "ligne--inactive" : "" },
      el("td", {}, el("span", { class: `etiquette-bloc ${classeBloc(rangs.get(b.code) ?? 0)}` }, b.code)),
      el("td", {}, b.nom, b.archive ? el("span", { class: "etiquette etiquette--espace" }, "Archivé") : null),
      el("td", { class: "nombre" }, formatNombre(b.ordre)),
      el("td", { class: "nombre" }, b.budget_cible_ht === null ? "—" : formatMontant(b.budget_cible_ht)),
      el("td", {}, b.responsable ?? ""),
      el("td", { class: "nombre" }, formatNombre(b.nb_composants)),
      el(
        "td",
        { class: "nombre" },
        el("span", { class: "actions actions--droite" },
          el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireBloc(b, ordreSuggere, rafraichir) }, "Modifier"),
          el("button", { type: "button", class: `bouton bouton--petit ${b.archive ? "bouton--discret" : "bouton--danger"}`, onclick: () => basculerArchive(b) }, b.archive ? "Réactiver" : "Archiver"),
        ),
      ),
    ),
  );
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "Le bloc est le découpage fonctionnel : un seul par composant, figé dans son identifiant. Un bloc archivé n'accepte plus de composant ; un bloc qui n'a jamais porté de composant se supprime depuis l'écran Nettoyage."),
      el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireBloc(null, ordreSuggere, rafraichir) }, "Nouveau bloc"),
    ),
    table(
      [["Code"], ["Nom"], ["Ordre", "nombre"], ["Budget cible HT", "nombre"], ["Responsable"], ["Composants", "nombre"], [""]],
      lignes,
      "Aucun bloc fonctionnel pour l'instant. Créer le premier pour pouvoir saisir des composants.",
    ),
  );
}

// --- Ensembles --------------------------------------------------------------------------------

export async function afficherOngletEnsembles(cible) {
  const rafraichir = () => afficherOngletEnsembles(cible);
  const ensembles = await api.getEnsembles();
  const ordreSuggere = Math.max(0, ...ensembles.map((e) => e.ordre)) + 1;
  const archiver = async (ensemble) => {
    const message =
      `Archiver l'ensemble « ${ensemble.nom} » ?\n\n` +
      `Il disparaîtra des listes. Ses ${ensemble.nb_composants_distincts} affectation(s) et l'historique sont conservés.`;
    if (!confirm(message)) return;
    try {
      await api.archiveEnsemble(ensemble.code);
      masquerErreur();
      await rafraichir();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const lignes = ensembles.map((e) =>
    el(
      "tr",
      {},
      el("td", {}, el("span", { class: "etiquette" }, e.code)),
      el("td", {}, e.nom),
      el("td", { class: "nombre" }, formatNombre(e.ordre)),
      el("td", {}, e.responsable ?? ""),
      el("td", {}, libelle(e.statut_montage)),
      el("td", { class: "nombre" }, formatNombre(e.nb_composants_distincts)),
      el(
        "td",
        { class: "nombre" },
        el("span", { class: "actions actions--droite" },
          el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireEnsemble({ ensemble: e, surEnregistre: rafraichir }) }, "Modifier"),
          el("button", { type: "button", class: "bouton bouton--petit bouton--danger", onclick: () => archiver(e) }, "Archiver"),
        ),
      ),
    ),
  );
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "L'ensemble est le découpage physique : un composant peut entrer dans plusieurs ensembles, avec une quantité pour chacun."),
      el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireEnsemble({ ordreSuggere, surEnregistre: rafraichir }) }, "Nouvel ensemble"),
    ),
    table(
      [["Code"], ["Nom"], ["Ordre", "nombre"], ["Responsable"], ["Montage"], ["Composants", "nombre"], [""]],
      lignes,
      "Aucun ensemble pour l'instant.",
    ),
  );
}

// --- Fournisseurs -----------------------------------------------------------------------------

function premiereLigne(texte) {
  if (!texte) return "";
  const [ligne, ...reste] = texte.split("\n");
  return reste.length ? `${ligne} (+${reste.length})` : ligne;
}

function champFichierListe(surComparaison) {
  const fichier = el("input", { type: "file", accept: ".xlsx,.xlsm", hidden: true });
  fichier.addEventListener("change", async () => {
    if (!fichier.files.length) return;
    const donnees = new FormData();
    donnees.append("fichier", fichier.files[0]);
    try {
      const resultat = await api.comparerFournisseurs(donnees);
      masquerErreur();
      surComparaison(resultat, fichier.files[0].name);
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      fichier.value = "";
    }
  });
  const bouton = el("button", { type: "button", class: "bouton bouton--discret", title: "Comparer avec un classeur Excel de fournisseurs (liste des fournisseurs autorisés…)" }, "Comparer avec une liste…");
  bouton.addEventListener("click", () => fichier.click());
  return [fichier, bouton];
}

export async function afficherOngletFournisseurs(cible, parametres = null) {
  const rafraichir = () => afficherOngletFournisseurs(cible, parametres);
  const fournisseurs = await api.getFournisseurs();
  const recherche = el("input", { class: "champ champ--recherche", type: "search", placeholder: "Filtrer : nom, catégorie, contact…", "aria-label": "Filtrer les fournisseurs" });
  const ligne = (f) =>
    el(
      "tr",
      { class: "ligne-cliquable", "data-texte": [f.nom, f.categorie, f.contact, f.numero_compte, f.type].join(" ").toLowerCase(), onclick: () => naviguer(routeFournisseur(f.nom)) },
      el("td", {}, lienFournisseur(f.nom, f.statut), " ", lienProduit(f.site_web)),
      el("td", {}, f.categorie ?? ""),
      el("td", { class: "texte-petit" }, premiereLigne(f.contact)),
      el("td", {}, f.numero_compte ?? ""),
      el("td", { class: "nombre" }, formatNombre(f.nb_composants)),
      el("td", { class: "nombre" }, formatNombre(f.nb_commandes)),
      el(
        "td",
        { class: "nombre", onclick: (e) => e.stopPropagation() },
        el("span", { class: "actions actions--droite" },
          el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaireFournisseur(f, { fournisseurs, surEnregistre: rafraichir }) }, "Modifier"),
          el("button", { type: "button", class: "bouton bouton--petit bouton--danger", onclick: async () => (await archiverFournisseur(f)) && rafraichir() }, "Archiver"),
        ),
      ),
    );
  const tableau = table(
    [["Nom"], ["Catégorie"], ["Contact devis"], ["N° de compte"], ["Composants", "nombre"], ["Commandes", "nombre"], [""]],
    fournisseurs.map(ligne),
    "Aucun fournisseur pour l'instant.",
  );
  const nbAValider = fournisseurs.filter((f) => f.statut === A_VALIDER).length;
  const seulementAValider = el("input", { type: "checkbox", checked: parametres?.get("statut") === "a_valider" && nbAValider > 0 });
  const filtrer = () => {
    const texte = recherche.value.trim().toLowerCase();
    tableau.querySelectorAll("tbody tr").forEach((tr, i) => {
      const statutExclu = seulementAValider.checked && fournisseurs[i].statut !== A_VALIDER;
      tr.hidden = statutExclu || (Boolean(texte) && !tr.dataset.texte.includes(texte));
    });
  };
  recherche.addEventListener("input", filtrer);
  seulementAValider.addEventListener("change", filtrer);
  const comparer = (resultat, nomFichier) => afficherComparaison(cible, resultat, nomFichier, rafraichir);
  cible.replaceChildren(
    el(
      "div",
      { class: "titre-section" },
      el("p", { class: "texte-doux" }, "Cliquer sur un fournisseur ouvre sa fiche. Un fournisseur archivé n'est plus proposé, mais les composants et les commandes qui le citent le gardent."),
      el("span", { class: "actions" },
        champFichierListe(comparer),
        el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaireFournisseur(null, { fournisseurs, surEnregistre: rafraichir }) }, "Nouveau fournisseur"),
      ),
    ),
    fournisseurs.length
      ? el(
          "div",
          { class: "barre-filtres" },
          recherche,
          nbAValider ? el("label", { class: "filtre-case" }, seulementAValider, `Seulement les ${nbAValider} à valider`) : null,
        )
      : null,
    tableau,
  );
  filtrer();
}
