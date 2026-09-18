// Valeurs des listes. Les listes figées (statuts de commande, de ligne, de montage…) sont
// écrites ici ; les listes paramétrables (modes d'appro, statuts d'appro et de choix,
// criticités, types de mouvement) sont chargées depuis la base au démarrage.

import { api } from "./api.js";

let listes = {};

export async function chargerListes() {
  listes = await api.getListes();
}

export function toutesLesListes() {
  return listes;
}

/**
 * Paires [code, libellé] d'une liste paramétrable : les valeurs actives, plus la valeur
 * courante si elle a été désactivée depuis (pour qu'un champ existant reste lisible).
 */
export function valeursListe(liste, { valeurCourante = null, inclureInactives = false } = {}) {
  return (listes[liste] ?? [])
    .filter((v) => v.actif || inclureInactives || v.code === valeurCourante)
    .map((v) => [v.code, v.actif ? v.libelle : `${v.libelle} (désactivé)`]);
}

export function libelleListe(code) {
  for (const valeurs of Object.values(listes)) {
    const trouvee = valeurs.find((v) => v.code === code);
    if (trouvee) return trouvee.libelle;
  }
  return null;
}

// Sens imposé par un type de mouvement ; null s'il est libre (inventaire…).
export function sensImpose(typeMouvement) {
  return (listes.type_mouvement ?? []).find((v) => v.code === typeMouvement)?.sens ?? null;
}

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
// Types de mouvement système : leur code est figé (calcul de la quantité montée).
export const TYPES_MONTAGE = ["Sortie montage", "Retour montage"];
export const STATUTS_ENGAGES = ["Commande", "Livre partiel", "Livre"];
