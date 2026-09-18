// Valeurs autorisées, reprises de docs/MODELE.md (section « Valeurs autorisées »).

export const MODES_APPRO = ["Achat", "Stock ecole", "Fourni PFM", "Fourni CEA", "Fabrication PFM"];
export const STATUTS_CHOIX = ["Acte", "A confirmer", "A sourcer"];
export const STATUTS_APPRO = [
  "Non lance",
  "Devis demande",
  "Devis recu",
  "A commander",
  "Commande",
  "Recu partiel",
  "Recu",
  "Stock-PFM",
  "Hors perimetre",
  "Abandonne",
];
export const CRITICITES = ["Bloquant", "Important", "Confort"];
export const BASES_PRIX = ["HT", "TTC"];
export const AVANCEMENTS = ["A commander", "Commande", "Recu", "Hors achat"];
export const STATUTS_MONTAGE = ["Non commence", "En cours", "Monte", "Valide"];
export const TYPES_COMMANDE = ["Commande", "Devis"];
export const STATUTS_COMMANDE = [
  "A demander",
  "Devis demande",
  "Devis recu",
  "Devis valide",
  "Commande",
  "Livre partiel",
  "Livre",
  "Refuse",
];
export const STATUTS_LIGNE = ["A commander", "Commandee", "Recue partiel", "Recue", "Annulee"];
export const TYPES_MOUVEMENT = [
  "Reception achat",
  "Pret ecole",
  "Retour ecole",
  "Sortie montage",
  "Retour montage",
  "Perte ou casse",
  "Inventaire",
];
export const TYPES_MONTAGE = ["Sortie montage", "Retour montage"];
// Sens imposé par le type de mouvement ; seul l'inventaire laisse choisir (même règle côté serveur).
export const SENS_IMPOSE = {
  "Reception achat": "Entree",
  "Pret ecole": "Entree",
  "Retour montage": "Entree",
  "Retour ecole": "Sortie",
  "Sortie montage": "Sortie",
  "Perte ou casse": "Sortie",
};
export const STATUTS_ENGAGES = ["Commande", "Livre partiel", "Livre"];
