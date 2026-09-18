// Formatage français centralisé : montants, dates, pourcentages, libellés accentués.

const ESPACE_FINE = " ";

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

// Montant signé explicitement : « +184,98 € » pour un dépassement.
export function formatEcart(valeur) {
  if (valeur === null || valeur === undefined) return "";
  return (valeur > 0 ? "+" : "") + formatMontant(valeur);
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
  const nettoye = String(texte ?? "").replace(/[\s  €]/g, "").replace(",", ".");
  if (nettoye === "") return null;
  return /^-?\d+(\.\d+)?$/.test(nettoye) ? Number(nettoye) : Number.NaN;
}

// Les valeurs énumérées sont stockées sans accents ; l'interface les affiche accentuées.
const LIBELLES = {
  "Stock ecole": "Stock école",
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
  "Pret ecole": "Prêt école",
  "Retour ecole": "Retour école",
  "Non commence": "Non commencé",
  Monte: "Monté",
  Valide: "Validé",
};

export function libelle(valeur) {
  if (valeur === null || valeur === undefined) return "";
  return LIBELLES[valeur] ?? valeur;
}
