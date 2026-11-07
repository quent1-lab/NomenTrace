// Contrôle d'un envoi de fichiers avant de l'envoyer : un fichier refusé d'avance n'est pas
// transféré pour rien. Le serveur refait les mêmes contrôles et fait foi (GET /api/envoi).

import { api } from "./api.js";

function enMo(octets) {
  const mo = octets / (1024 * 1024);
  return `${Number.isInteger(mo) ? mo : mo.toFixed(1).replace(".", ",")} Mo`;
}

function extension(nom) {
  const point = nom.lastIndexOf(".");
  return point > 0 ? nom.slice(point).toLowerCase() : "";
}

/**
 * Renvoie le message qui explique pourquoi l'envoi serait refusé, ou null s'il peut partir.
 * fichiers : FileList ou tableau de File ; limites : réponse de GET /api/envoi, ou null si
 * elle n'a pas pu être lue (seul le serveur contrôle alors) ;
 * extensions : extensions acceptées par cet écran, celles des documents par défaut ;
 * documents : vrai si chaque fichier est un document joint, borné par le réglage du projet.
 */
export function refusEnvoi(fichiers, limites, { extensions = limites?.extensions, documents = false } = {}) {
  if (!limites) return null;
  const liste = [...fichiers];
  const refus = [];
  if (extensions) {
    const acceptees = new Set(extensions);
    const exclus = liste.filter((f) => !acceptees.has(extension(f.name)));
    if (exclus.length) {
      const noms = exclus.map((f) => `« ${f.name} »`).join(", ");
      refus.push(`Type de fichier non accepté : ${noms}. Acceptés : ${[...acceptees].map((e) => e.slice(1)).join(", ")}.`);
    }
  }
  if (documents) {
    for (const f of liste.filter((f) => f.size > limites.document_max_octets)) {
      refus.push(`« ${f.name} » pèse ${enMo(f.size)}, au-delà des ${enMo(limites.document_max_octets)} permis pour un document.`);
    }
  }
  const total = liste.reduce((somme, f) => somme + f.size, 0);
  if (total > limites.envoi_max_octets) {
    refus.push(`L'envoi pèse ${enMo(total)}, au-delà des ${enMo(limites.envoi_max_octets)} permis à la fois : envoyer les fichiers en plusieurs fois.`);
  }
  return refus.length ? `Rien n'a été envoyé. ${refus.join(" ")}` : null;
}

// Limites du projet de la page, ou d'un autre projet (commande commune) ; null en cas d'échec.
export async function lireLimites(projet = null) {
  try {
    return await api.getLimitesEnvoi(projet);
  } catch {
    return null;
  }
}
