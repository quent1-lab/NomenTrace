// Panneau latéral unique (fiche, création), fermé par le bouton ou par Échap.

import { el } from "./ui.js";

let surFermetureCourante = null;

const panneau = el("aside", { class: "panneau-lateral", "aria-hidden": "true" });
document.body.append(panneau);

document.addEventListener("keydown", (e) => {
  // Échap dans un champ en cours d'édition annule la saisie, pas le panneau.
  if (e.key === "Escape" && estOuvert() && !e.target.closest?.(".cellule--edition")) {
    fermerPanneau();
  }
});

export function estOuvert() {
  return panneau.classList.contains("panneau-lateral--ouvert");
}

export function ouvrirPanneau(titre, contenu, surFermeture = null) {
  surFermetureCourante = surFermeture;
  panneau.replaceChildren(
    el(
      "header",
      { class: "panneau-lateral__entete" },
      el("h2", {}, titre),
      el("button", { type: "button", class: "bouton-fermer", "aria-label": "Fermer", onclick: () => fermerPanneau() }, "×"),
    ),
    el("div", { class: "panneau-lateral__corps" }, contenu),
  );
  panneau.classList.add("panneau-lateral--ouvert");
  panneau.setAttribute("aria-hidden", "false");
}

export function fermerPanneau({ silencieux = false } = {}) {
  if (!estOuvert()) return;
  panneau.classList.remove("panneau-lateral--ouvert");
  panneau.setAttribute("aria-hidden", "true");
  panneau.replaceChildren();
  const rappel = surFermetureCourante;
  surFermetureCourante = null;
  if (rappel && !silencieux) rappel();
}
