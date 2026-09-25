// Éléments communs aux écrans fournisseurs : formulaire, contact, lien vers la fiche.

import { api } from "../api.js";
import { champChoix, champNombre, champTexte, champZone, lireFormulaire, ligneChamp } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { BASES_PRIX } from "../valeurs.js";

export const LIBELLES_FOURNISSEUR = {
  categorie: "Catégorie",
  contact: "Contact devis",
  numero_compte: "N° de compte client",
  site_web: "Site web",
  pays: "Pays",
  type: "Type",
  delai_moyen_j: "Délai moyen (jours)",
  commentaire: "Commentaire",
};

const DESCRIPTION = {
  nom: "texte",
  categorie: "texte",
  contact: "texte",
  numero_compte: "texte",
  site_web: "texte",
  type: "texte",
  base_prix_defaut: "choix",
  pays: "texte",
  delai_moyen_j: "entier",
  commentaire: "texte",
  statut: "choix",
};

// Adresse de la fiche d'un fournisseur (le nom peut contenir « / »).
export function routeFournisseur(nom) {
  return `/fournisseurs/${encodeURIComponent(nom)}`;
}

export const A_VALIDER = "A valider";

export function badgeAValider() {
  return el("span", { class: "etiquette etiquette--attention", title: "Fournisseur trouvé par l'équipe, pas encore validé" }, "à valider");
}

// Nom cliquable qui ouvre la fiche ; le clic ne déclenche pas l'action de la ligne. Le statut,
// s'il est connu, ajoute l'étiquette « à valider ».
export function lienFournisseur(nom, statut = null) {
  if (!nom) return "—";
  const lien = el("a", { class: "lien-fournisseur", href: `#${routeFournisseur(nom)}`, title: `Fiche du fournisseur ${nom}` }, nom);
  lien.addEventListener("click", (e) => e.stopPropagation());
  return statut === A_VALIDER ? el("span", { class: "fournisseur-a-valider" }, lien, " ", badgeAValider()) : lien;
}

// Statut de chaque fournisseur, pour afficher l'étiquette là où seul le nom est connu.
export function statutsFournisseurs(fournisseurs) {
  return new Map(fournisseurs.map((f) => [f.nom, f.statut]));
}

function cleNom(nom) {
  return nom.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

const NOUVEAU = "__nouveau__";

// Choix du fournisseur d'un composant : liste existante, ou un nouveau nom saisi par
// l'équipe, créé « à valider » au moment d'enregistrer (resoudre()).
export function champFournisseur(fournisseurs, valeur) {
  const options = fournisseurs.map((f) => [f.nom, f.statut === A_VALIDER ? `${f.nom} (à valider)` : f.nom]);
  const select = champChoix("fournisseur_nom", options, valeur, { vide: "—" });
  select.append(el("option", { value: NOUVEAU }, "+ Nouveau fournisseur (à valider)…"));
  const saisie = el("input", { class: "champ", type: "text", hidden: true, placeholder: "Nom du nouveau fournisseur", "aria-label": "Nom du nouveau fournisseur" });
  const aide = el("span", { class: "ligne-champ__aide", hidden: true }, "Il sera créé « à valider » : une personne autorisée complétera sa fiche et le validera.");
  select.addEventListener("change", () => {
    const nouveau = select.value === NOUVEAU;
    saisie.hidden = !nouveau;
    aide.hidden = !nouveau;
    if (nouveau) saisie.focus();
  });
  async function resoudre() {
    if (select.value !== NOUVEAU) return select.value || null;
    const nom = saisie.value.trim().replace(/\s+/g, " ");
    if (!nom) throw new Error("Saisir le nom du nouveau fournisseur, ou en choisir un dans la liste.");
    const existant = fournisseurs.find((f) => cleNom(f.nom) === cleNom(nom));
    if (existant) return existant.nom;
    const cree = await api.createFournisseur({ nom, statut: A_VALIDER });
    fournisseurs.push(cree);
    return cree.nom;
  }
  return { element: el("span", { class: "champ-fournisseur" }, select, saisie, aide), select, resoudre };
}

// Contact sur plusieurs lignes ; les adresses électroniques deviennent des liens mailto.
export function vueContact(contact) {
  if (!contact) return "—";
  return el(
    "div",
    { class: "contact" },
    contact.split("\n").map((ligne) =>
      el(
        "div",
        {},
        ligne.split(/([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/).map((morceau, i) =>
          i % 2 ? el("a", { href: `mailto:${morceau}` }, morceau) : morceau,
        ),
      ),
    ),
  );
}

// Catégories déjà employées, proposées à la saisie (une catégorie composée compte pour chacune).
function listeCategories(fournisseurs) {
  const categories = new Set(fournisseurs.flatMap((f) => (f.categorie ?? "").split(" / ").filter(Boolean)));
  return el("datalist", { id: "categories-fournisseurs" }, [...categories].sort().map((c) => el("option", { value: c })));
}

export function ouvrirFormulaireFournisseur(fournisseur, { fournisseurs = [], surEnregistre }) {
  const creation = fournisseur === null;
  const f = fournisseur ?? {};
  const contact = champZone("contact", f.contact ?? "");
  contact.rows = 3;
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    ligneChamp("Nom", champTexte("nom", f.nom ?? ""), {
      requis: true,
      aide: creation ? "" : "Renommer met à jour les composants et les commandes qui citent ce fournisseur.",
    }),
    ligneChamp(LIBELLES_FOURNISSEUR.categorie, champTexte("categorie", f.categorie ?? "", { list: "categories-fournisseurs", autocomplete: "off" }), {
      aide: "Électronique, mécanique… Plusieurs catégories se séparent par « / ».",
    }),
    listeCategories(fournisseurs),
    ligneChamp(LIBELLES_FOURNISSEUR.contact, contact, { aide: "Une personne ou une adresse par ligne." }),
    ligneChamp(LIBELLES_FOURNISSEUR.numero_compte, champTexte("numero_compte", f.numero_compte ?? "")),
    ligneChamp(LIBELLES_FOURNISSEUR.site_web, champTexte("site_web", f.site_web ?? "", { placeholder: "https://…" })),
    ligneChamp(LIBELLES_FOURNISSEUR.type, champTexte("type", f.type ?? ""), { aide: "Distributeur, fabricant, atelier…" }),
    ligneChamp("Prix affichés en", champChoix("base_prix_defaut", BASES_PRIX, f.base_prix_defaut ?? null, { vide: "—" })),
    ligneChamp(LIBELLES_FOURNISSEUR.pays, champTexte("pays", f.pays ?? "")),
    ligneChamp(LIBELLES_FOURNISSEUR.delai_moyen_j, champNombre("delai_moyen_j", f.delai_moyen_j ?? null)),
    ligneChamp(LIBELLES_FOURNISSEUR.commentaire, champZone("commentaire", f.commentaire ?? "")),
    ligneChamp("Statut", champChoix("statut", [["Valide", "Validé"], [A_VALIDER, "À valider"]], f.statut ?? "Valide"), {
      aide: "« À valider » : trouvé par l'équipe, pas encore vérifié par une personne autorisée.",
    }),
    el(
      "div",
      { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, creation ? "Créer le fournisseur" : "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, { delai_moyen_j: "Délai moyen" });
    if (lu.erreur) return afficherErreur(lu.erreur);
    if (!lu.valeurs.nom) return afficherErreur("Le nom du fournisseur est obligatoire.");
    try {
      const resultat = creation ? await api.createFournisseur(lu.valeurs) : await api.patchFournisseur(fournisseur.nom, lu.valeurs);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surEnregistre(resultat);
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau(creation ? "Nouveau fournisseur" : `Modifier ${fournisseur.nom}`, formulaire);
  formulaire.elements.namedItem("nom").focus();
}

// Archivage après confirmation ; renvoie true si le fournisseur a été archivé.
export async function archiverFournisseur(f) {
  const usages = (f.nb_composants ?? 0) + (f.nb_commandes ?? 0);
  const message =
    `Archiver le fournisseur « ${f.nom} » ?\n\n` +
    (usages ? `Il reste cité par ${f.nb_composants} composant(s) et ${f.nb_commandes} commande(s), qui le gardent. ` : "") +
    "Il ne sera plus proposé dans les listes. Recréer un fournisseur du même nom le réactive.";
  if (!confirm(message)) return false;
  try {
    await api.archiveFournisseur(f.nom);
    masquerErreur();
    return true;
  } catch (erreur) {
    afficherErreur(erreur);
    return false;
  }
}
