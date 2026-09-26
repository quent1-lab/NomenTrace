// Formatage français centralisé : montants, dates, pourcentages, libellés accentués.

import { libelleListe } from "./valeurs.js";

const ESPACE_FINE = "\u202f";

function grouperMilliers(entier) {
  return entier.replace(/\B(?=(\d{3})+(?!\d))/g, ESPACE_FINE);
}

export function formatNombre(valeur, decimales = 0) {
  if (valeur === null || valeur === undefined || Number.isNaN(valeur)) return "";
  const signe = valeur < 0 ? "−" : "";
  const [entier, fraction] = Math.abs(valeur).toFixed(decimales).split(".");
  return signe + grouperMilliers(entier) + (fraction ? "," + fraction : "");
}

export function formatMontant(valeur) {
  const texte = formatNombre(valeur, 2);
  return texte === "" ? "" : `${texte}${ESPACE_FINE}€`;
}

// Coût estimé face au budget. L'API donne l'écart (coût − budget, positif = dépassement) ;
// l'interface ne montre jamais ce signe. Là où la place le permet, le titre dit la
// situation et le montant reste positif : « Marge restante 500 € » ou « Dépassement 185 € ».
// Dans une colonne de tableau, au titre fixe, on affiche la marge signée (formatMarge).
// Écart nul au centime près : ni marge ni dépassement, à surveiller.
const CENTIME = 0.005;

// seuil : part du budget sous laquelle une marge est à surveiller (0.1 pour les blocs).
export function situationBudget(ecart, budget, seuil = null) {
  if (ecart === null || ecart === undefined || budget === null || budget === undefined) {
    return { titre: "Marge sur budget", montant: "budget non défini", pourcent: "", niveau: "neutre" };
  }
  const pourcent = budget > 0 ? formatPourcent((Math.abs(ecart) / budget) * 100) : "";
  if (ecart > CENTIME) {
    return { titre: "Dépassement", montant: formatMontant(ecart), pourcent, niveau: "alerte" };
  }
  const marge = Math.abs(ecart) < CENTIME ? 0 : -ecart;
  const faible = marge === 0 || (seuil !== null && marge < seuil * budget);
  return { titre: "Marge restante", montant: formatMontant(marge), pourcent, niveau: faible ? "surveiller" : "conforme" };
}

// Marge signée (budget − coût) : négative en cas de dépassement.
export function formatMarge(ecart) {
  if (ecart === null || ecart === undefined) return "";
  return formatMontant(Math.abs(ecart) < CENTIME ? 0 : -ecart);
}

export function niveauMarge(ecart) {
  if (ecart === null || ecart === undefined) return "neutre";
  if (ecart > CENTIME) return "alerte";
  return ecart > -CENTIME ? "surveiller" : "conforme";
}

export function formatPourcent(valeur, decimales = 1) {
  const texte = formatNombre(valeur, decimales);
  return texte === "" ? "" : `${texte}${ESPACE_FINE}%`;
}

export function formatDate(iso) {
  if (!iso) return "";
  const [annee, mois, jour] = iso.slice(0, 10).split("-");
  return `${jour}/${mois}/${annee}`;
}

// Date du jour en heure locale, au format ISO (AAAA-MM-JJ) attendu par la base.
export function aujourdhui() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Lit un nombre saisi à la française (« 1 234,50 ») ; renvoie null si vide, NaN si illisible.
export function lireNombre(texte) {
  const nettoye = String(texte ?? "").replace(/[\s\u202f\u00a0€]/g, "").replace(",", ".");
  if (nettoye === "") return null;
  return /^-?\d+(\.\d+)?$/.test(nettoye) ? Number(nettoye) : Number.NaN;
}

// Les valeurs énumérées sont stockées sans accents ; l'interface les affiche accentuées.
// Les listes paramétrables portent leur propre libellé (valeurs.js) ; cette table couvre
// les listes figées.
const LIBELLES = {
  Acte: "Acté",
  "A confirmer": "À confirmer",
  "A sourcer": "À sourcer",
  "Non lance": "Non lancé",
  "Devis demande": "Devis demandé",
  "Devis recu": "Devis reçu",
  "A commander": "À commander",
  Commande: "Commandé",
  "Recu partiel": "Reçu partiel",
  Recu: "Reçu",
  "Hors perimetre": "Hors périmètre",
  Abandonne: "Abandonné",
  "A demander": "À demander",
  "Devis valide": "Devis validé",
  "Livre partiel": "Livré partiel",
  Livre: "Livré",
  Refuse: "Refusé",
  Commandee: "Commandée",
  "Recue partiel": "Reçue partiel",
  Recue: "Reçue",
  Annulee: "Annulée",
  Entree: "Entrée",
  "Reception achat": "Réception achat",
  "Non commence": "Non commencé",
  Monte: "Monté",
  Valide: "Validé",
};

export function libelle(valeur) {
  if (valeur === null || valeur === undefined) return "";
  return libelleListe(valeur) ?? LIBELLES[valeur] ?? valeur;
}
