// Fiche d'un fournisseur (#/fournisseurs/NOM) : coordonnées, composants et commandes.

import { api } from "../api.js";
import { formatDate, formatMontant, formatNombre, libelle } from "../format.js";
import { lienRoute, naviguer, remplacerRoute } from "../router.js";
import { afficherErreur, el, lienProduit, masquerErreur } from "../ui.js";
import { A_VALIDER, LIBELLES_FOURNISSEUR, archiverFournisseur, badgeAValider, ouvrirFormulaireFournisseur, routeFournisseur, vueContact } from "./fournisseurs_commun.js";

function boutonCopier(texte) {
  const bouton = el("button", { type: "button", class: "bouton bouton--petit bouton--discret", title: "Copier le numéro de compte" }, "Copier");
  bouton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(texte);
      bouton.textContent = "Copié";
    } catch {
      afficherErreur("Copie impossible dans ce navigateur : sélectionner le numéro à la main.");
    }
  });
  return bouton;
}

function coordonnees(f) {
  const site = f.site_web ? el("span", {}, el("a", { href: f.site_web, target: "_blank", rel: "noopener noreferrer" }, f.site_web), " ", lienProduit(f.site_web)) : null;
  const paires = [
    [LIBELLES_FOURNISSEUR.categorie, f.categorie],
    [LIBELLES_FOURNISSEUR.contact, f.contact ? vueContact(f.contact) : null],
    [LIBELLES_FOURNISSEUR.numero_compte, f.numero_compte ? el("span", { class: "numero-compte" }, el("code", {}, f.numero_compte), " ", boutonCopier(f.numero_compte)) : null],
    [LIBELLES_FOURNISSEUR.site_web, site],
    [LIBELLES_FOURNISSEUR.type, f.type],
    ["Prix affichés en", f.base_prix_defaut],
    [LIBELLES_FOURNISSEUR.pays, f.pays],
    [LIBELLES_FOURNISSEUR.delai_moyen_j, f.delai_moyen_j === null ? null : `${formatNombre(f.delai_moyen_j)} j`],
  ];
  return el(
    "section",
    { class: "panneau" },
    el("dl", { class: "fiche__champs" }, paires.flatMap(([t, v]) => [el("dt", {}, t), el("dd", {}, v === null || v === undefined || v === "" ? "—" : v)])),
    f.commentaire ? el("div", { class: "fiche__note" }, el("strong", {}, "Commentaire"), el("p", {}, f.commentaire)) : null,
  );
}

function tableau(entetes, lignes, vide) {
  if (!lignes.length) return el("p", { class: "texte-doux" }, vide);
  return el(
    "table",
    { class: "table table--dense table--parametres" },
    el("thead", {}, el("tr", {}, entetes.map(([t, c]) => el("th", { class: c ?? "" }, t)))),
    el("tbody", {}, lignes),
  );
}

function sectionComposants(f) {
  const lignes = f.composants.map((c) =>
    el(
      "tr",
      { class: "ligne-cliquable", onclick: () => naviguer("/composants", { fiche: c.id }) },
      el("td", {}, c.id),
      el("td", {}, c.designation),
      el("td", {}, c.ref_fabricant ?? ""),
      el("td", { class: "nombre" }, formatNombre(c.qte_a_acheter)),
      el("td", { class: "nombre" }, c.pu_ht === null ? "—" : formatMontant(c.pu_ht)),
      el("td", { class: "nombre" }, formatMontant(c.total_ht)),
      el("td", {}, libelle(c.avancement)),
    ),
  );
  const total = f.composants.reduce((somme, c) => somme + (c.total_ht ?? 0), 0);
  return el(
    "section",
    { class: "panneau" },
    el(
      "div",
      { class: "titre-section" },
      el("h2", {}, `Composants (${f.composants.length})`),
      f.composants.length ? el("a", { href: lienRoute("/composants", { fournisseur: f.nom }) }, "Voir dans l'écran composants") : null,
    ),
    tableau(
      [["ID"], ["Désignation"], ["Réf fabricant"], ["Qté à acheter", "nombre"], ["PU HT", "nombre"], ["Total HT", "nombre"], ["Avancement"]],
      lignes,
      "Aucun composant ne cite ce fournisseur.",
    ),
    f.composants.length ? el("p", { class: "texte-doux texte-petit" }, `Coût estimé HT des composants : ${formatMontant(total)}.`) : null,
  );
}

function sectionCommandes(f) {
  const lignes = f.commandes.map((c) =>
    el(
      "tr",
      { class: "ligne-cliquable", onclick: () => naviguer(`/achats/${encodeURIComponent(c.numero)}`) },
      el("td", {}, c.numero),
      el("td", {}, c.type),
      el("td", {}, libelle(c.statut)),
      el("td", {}, formatDate(c.date_commande) || "—"),
      el("td", {}, formatDate(c.livraison_annoncee) || "—"),
      el("td", { class: "nombre" }, formatMontant(c.total_ht)),
    ),
  );
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, `Devis et commandes (${f.commandes.length})`),
    tableau([["Numéro"], ["Type"], ["Statut"], ["Commandée le"], ["Livraison annoncée"], ["Total HT", "nombre"]], lignes, "Aucun devis ni aucune commande chez ce fournisseur."),
  );
}

function bandeauValidation(f, recharger) {
  const valider = el("button", { type: "button", class: "bouton" }, "Valider ce fournisseur");
  valider.addEventListener("click", async () => {
    const manque = [["catégorie", f.categorie], ["contact", f.contact], ["site web", f.site_web]].filter(([, v]) => !v).map(([t]) => t);
    if (manque.length && !confirm(`La fiche n'a pas encore de ${manque.join(", ")}. Valider quand même ?`)) return;
    try {
      await api.patchFournisseur(f.nom, { statut: "Valide" });
      masquerErreur();
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  return el(
    "div",
    { class: "message message-attention bandeau-validation" },
    el("span", {}, "Ce fournisseur a été ajouté par l'équipe et n'est pas encore validé. Compléter sa fiche (« Modifier »), puis le valider."),
    valider,
  );
}

export async function afficherFicheFournisseur(conteneur, _parametres, nom) {
  const [f, fournisseurs] = await Promise.all([api.getFournisseur(nom), api.getFournisseurs()]);
  const recharger = (modifie) => {
    const nouveauNom = modifie?.nom ?? nom;
    if (nouveauNom !== nom) remplacerRoute(routeFournisseur(nouveauNom));
    return afficherFicheFournisseur(conteneur, _parametres, nouveauNom);
  };
  const usages = { ...f, nb_composants: f.composants.length, nb_commandes: f.commandes.length };
  conteneur.replaceChildren(
    el("p", { class: "fil" }, el("a", { href: lienRoute("/parametres", { onglet: "fournisseurs" }) }, "← Fournisseurs")),
    el(
      "div",
      { class: "titre-page" },
      el("h1", {}, `${f.nom} `, f.categorie ? el("span", { class: "etiquette" }, f.categorie) : null, " ", f.statut === A_VALIDER ? badgeAValider() : null, " ", f.archive ? el("span", { class: "etiquette etiquette--alerte" }, "archivé") : null),
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "bouton bouton--discret", onclick: () => ouvrirFormulaireFournisseur(f, { fournisseurs, surEnregistre: recharger }) }, "Modifier"),
        f.archive ? null : el("button", { type: "button", class: "bouton bouton--danger", onclick: async () => (await archiverFournisseur(usages)) && recharger() }, "Archiver"),
      ),
    ),
    f.statut === A_VALIDER ? bandeauValidation(f, recharger) : null,
    coordonnees(f),
    sectionComposants(f),
    sectionCommandes(f),
  );
}
