// Formulaire de commande (création et modification), partagé par la liste et le détail.

import { api } from "../api.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { nomAuteur } from "../session.js";
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
  taux_tva: "taux",
  date_transmission_suivi: "texte",
  montant_commande_ht: "montant",
  date_reception_annoncee: "texte",
  commentaire_suivi: "texte",
  reference_externe: "texte",
  lien_document: "texte",
  commentaire: "texte",
};
// Le suivi de l'établissement ne concerne qu'une commande existante : pas de ces champs à la création.
const CHAMPS_SUIVI = ["date_transmission_suivi", "montant_commande_ht", "date_reception_annoncee", "commentaire_suivi"];
const DESCRIPTION_CREATION = Object.fromEntries(Object.entries(DESCRIPTION).filter(([k]) => !CHAMPS_SUIVI.includes(k)));
const LIBELLES = { taux_tva: "Taux de TVA", montant_commande_ht: "Montant de la commande" };

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
      // Par défaut, la personne connectée ; modifiable pour une demande faite au nom d'un autre.
      ligneChamp("Demandée par", champTexte("demande_par", creation ? nomAuteur() : c.demande_par)),
      ligneChamp("Référence externe", champTexte("reference_externe", c.reference_externe), { aide: "Numéro de devis ou de bon de commande du fournisseur." }),
    ),
    el("fieldset", {}, el("legend", {}, "Dates"),
      ligneChamp("Demande", champDate("date_demande", c.date_demande)),
      ligneChamp("Réception du devis", champDate("date_reception_devis", c.date_reception_devis)),
      ligneChamp("Commande", champDate("date_commande", c.date_commande), { aide: "Renseignée automatiquement au passage en Commande si vide." }),
      ligneChamp("Livraison annoncée", champDate("livraison_annoncee", c.livraison_annoncee)),
      ligneChamp("Réception réelle", champDate("date_reception_reelle", c.date_reception_reelle)),
    ),
    ligneChamp("Taux de TVA (%)", champNombre("taux_tva", tva * 100, 1), { aide: "Les frais (livraison, douane…) se saisissent sur la commande." }),
    creation ? null : el("fieldset", {}, el("legend", {}, "Suivi de l'établissement"),
      ligneChamp("Transmise au suivi le", champDate("date_transmission_suivi", c.date_transmission_suivi)),
      ligneChamp("Montant de la commande HT", champNombre("montant_commande_ht", c.montant_commande_ht ?? null, 2), { aide: "Saisi par l'établissement, frais compris ; il remplace l'estimation dans le montant engagé." }),
      ligneChamp("Réception annoncée", champDate("date_reception_annoncee", c.date_reception_annoncee)),
      ligneChamp("Commentaire", champTexte("commentaire_suivi", c.commentaire_suivi)),
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
    const lu = lireFormulaire(formulaire, creation ? DESCRIPTION_CREATION : DESCRIPTION, LIBELLES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    const valeurs = lu.valeurs;
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
