// Badges partagés par les pages d'un projet et les pages communes.

import { el } from "./ui.js";

// Badge de statut coloré selon l'avancement de la commande.
export function badgeStatut(commande) {
  const classe = { Livre: "recu", "Livre partiel": "commande", Commande: "commande", Refuse: "hors-achat" }[commande.statut] ?? "a-commander";
  return el("span", { class: `avancement avancement--${classe}` }, commande.statut === "Commande" ? "Commandée" : libelleStatut(commande.statut));
}

function libelleStatut(statut) {
  return { "Livre partiel": "Livrée partiellement", Livre: "Livrée", Refuse: "Refusée", "A demander": "À demander", "Devis demande": "Devis demandé", "Devis recu": "Devis reçu", "Devis valide": "Devis validé" }[statut] ?? statut;
}
