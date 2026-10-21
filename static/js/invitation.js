// Lien d'invitation affiché une seule fois, avec un bouton pour le copier. Aucun courriel
// n'est envoyé : le lien est à transmettre soi-même ; seule son empreinte reste au serveur.

import { formatDate } from "./format.js";
import { el } from "./ui.js";

function lienInvitation(jeton) {
  return `${window.location.origin}/connexion.html#invitation=${jeton}`;
}

// Lien affiché une seule fois, avec un bouton pour le copier.
export function encartInvitation(nom, { jeton, expire_le: expire }) {
  const lien = lienInvitation(jeton);
  const champ = el("input", { class: "champ", type: "text", value: lien, readonly: true, "aria-label": "Lien d'invitation" });
  champ.addEventListener("focus", () => champ.select());
  const copier = el("button", { type: "button", class: "bouton bouton--petit" }, "Copier");
  copier.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(lien);
      copier.textContent = "Copié";
    } catch {
      champ.select();
    }
  });
  return el(
    "div",
    { class: "message message-ok" },
    el("p", {}, `Lien pour ${nom}, valable jusqu'au ${formatDate(expire.slice(0, 10))} à ${expire.slice(11, 16)}, utilisable une seule fois. ` +
      "Il ne sera plus affiché : le transmettre maintenant, par un canal sûr (il donne accès au compte)."),
    el("div", { class: "lien-invitation" }, champ, copier),
  );
}
