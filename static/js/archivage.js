// Bandeau d'un élément archivé : date et auteur de l'archivage, bouton « Désarchiver ».
// Partagé par les fiches du composant, de l'ensemble, de la commande et du fournisseur.

import { formatDate } from "./format.js";
import { modeLocal } from "./session.js";
import { afficherErreur, el } from "./ui.js";

// `classeDroit` masque le bouton à qui ne peut pas désarchiver (le serveur vérifie toujours).
export function bandeauArchive({ element, texte, classeDroit, desarchiver, apres }) {
  const quand = element.archive_le ? ` le ${formatDate(element.archive_le.slice(0, 10))}` : "";
  // En mode local, un seul poste : l'auteur n'apprend rien.
  const qui = element.archive_par && !modeLocal() ? ` par ${element.archive_par}` : "";
  const bouton = desarchiver
    ? el(
        "button",
        {
          type: "button",
          class: `bouton ${classeDroit}`,
          onclick: async (evenement) => {
            evenement.currentTarget.disabled = true;
            try {
              await desarchiver();
              await apres();
            } catch (erreur) {
              evenement.target.disabled = false;
              afficherErreur(erreur);
            }
          },
        },
        "Désarchiver",
      )
    : null;
  return el(
    "div",
    { class: "message message-attention bandeau-archive" },
    el("p", {}, el("strong", {}, `Archivé${quand}${qui}.`), " ", texte),
    bouton,
  );
}
