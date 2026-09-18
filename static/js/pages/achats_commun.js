// Formulaire de commande (création et modification), partagé par la liste et le détail.

import { api } from "../api.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { STATUTS_COMMANDE, TYPES_COMMANDE } from "../valeurs.js";

const DESCRIPTION = {
  type: "choix",
  statut: "choix",
  fournisseur_nom: "choix",
  demande_par: "texte",
  date_demande: "texte",
  date_reception_devis: "texte",
  date_commande: "texte",
  livraison_annoncee: "texte",
  date_reception_reelle: "texte",
  port_ht: "montant",
  taux_tva: "taux",
  reference_externe: "texte",
  lien_document: "texte",
  commentaire: "texte",
};
const LIBELLES = { port_ht: "Port HT", taux_tva: "Taux de TVA" };

function champDate(nom, valeur) {
  return el("input", { class: "champ champ--date", type: "date", name: nom, value: valeur ?? "" });
}

/** Panneau de création (commande absente) ou de modification d'une commande. */
export async function ouvrirFormulaireCommande({ commande = null, fournisseurs, surEnregistre }) {
  const creation = commande === null;
  const parametres = creation ? await api.getParametres() : null;
  const tva = creation ? Number(parametres.taux_tva_defaut ?? 0.2) : commande.taux_tva;
  const c = commande ?? {};
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    creation ? el("p", { class: "apercu-id" }, "Le numéro (CMD-NNN) est attribué à l'enregistrement.") : null,
    el("fieldset", {}, el("legend", {}, "Commande"),
      ligneChamp("Type", champChoix("type", TYPES_COMMANDE, c.type ?? "Commande")),
      ligneChamp("Statut", champChoix("statut", STATUTS_COMMANDE, c.statut ?? "A demander")),
      ligneChamp("Fournisseur", champChoix("fournisseur_nom", fournisseurs.map((f) => [f.nom, f.nom]), c.fournisseur_nom ?? null, { vide: "—" })),
      ligneChamp("Demandée par", champTexte("demande_par", c.demande_par)),
      ligneChamp("Référence externe", champTexte("reference_externe", c.reference_externe), { aide: "Numéro de devis ou de bon de commande du fournisseur." }),
    ),
    el("fieldset", {}, el("legend", {}, "Dates"),
      ligneChamp("Demande", champDate("date_demande", c.date_demande)),
      ligneChamp("Réception du devis", champDate("date_reception_devis", c.date_reception_devis)),
      ligneChamp("Commande", champDate("date_commande", c.date_commande), { aide: "Renseignée automatiquement au passage en Commande si vide." }),
      ligneChamp("Livraison annoncée", champDate("livraison_annoncee", c.livraison_annoncee)),
      ligneChamp("Réception réelle", champDate("date_reception_reelle", c.date_reception_reelle)),
    ),
    el("fieldset", {}, el("legend", {}, "Montants"),
      ligneChamp("Port HT", champNombre("port_ht", c.port_ht ?? 0, 2)),
      ligneChamp("Taux de TVA (%)", champNombre("taux_tva", tva * 100, 1)),
    ),
    ligneChamp("Lien du document", champTexte("lien_document", c.lien_document, { type: "url" })),
    ligneChamp("Commentaire", champZone("commentaire", c.commentaire)),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, creation ? "Créer la commande" : "Enregistrer"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, LIBELLES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    const valeurs = { ...lu.valeurs, port_ht: lu.valeurs.port_ht ?? 0 };
    const modifs = creation ? valeurs : Object.fromEntries(Object.entries(valeurs).filter(([k, v]) => v !== c[k]));
    try {
      const resultat = creation ? await api.createCommande(modifs) : await api.patchCommande(c.numero, modifs);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surEnregistre(resultat);
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau(creation ? "Nouvelle commande" : `Modifier ${c.numero}`, formulaire);
}

// Badge de statut coloré selon l'avancement de la commande.
export function badgeStatut(commande) {
  const classe = { Livre: "recu", "Livre partiel": "commande", Commande: "commande", Refuse: "hors-achat" }[commande.statut] ?? "a-commander";
  return el("span", { class: `avancement avancement--${classe}` }, commande.statut === "Commande" ? "Commandée" : libelleStatut(commande.statut));
}

function libelleStatut(statut) {
  return { "Livre partiel": "Livrée partiellement", Livre: "Livrée", Refuse: "Refusée", "A demander": "À demander", "Devis demande": "Devis demandé", "Devis recu": "Devis reçu", "Devis valide": "Devis validé" }[statut] ?? statut;
}

export function badgeRetard(commande) {
  return commande.en_retard ? el("span", { class: "badge-retard", title: "Livraison annoncée dépassée" }, "en retard") : null;
}
