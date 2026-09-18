// Formatage français centralisé : montants, dates, pourcentages.

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

export function formatPourcent(valeur, decimales = 1) {
  const texte = formatNombre(valeur, decimales);
  return texte === "" ? "" : `${texte}${ESPACE_FINE}%`;
}

export function formatDate(iso) {
  if (!iso) return "";
  const [annee, mois, jour] = iso.slice(0, 10).split("-");
  return `${jour}/${mois}/${annee}`;
}
