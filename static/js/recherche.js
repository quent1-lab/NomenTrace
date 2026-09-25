// Recherche globale de l'en-tête : composants, commandes, fournisseurs, ensembles, blocs.
// Ctrl+F ou « / » place le curseur dans le champ ; un second Ctrl+F laisse la recherche du
// navigateur s'ouvrir. Flèches pour parcourir, Entrée pour ouvrir, Échap pour fermer.

import { api } from "./api.js";
import { lienRoute } from "./router.js";
import { el } from "./ui.js";

const TYPES = {
  composant: ["Composants", (cle) => lienRoute("/composants", { fiche: cle })],
  commande: ["Commandes", (cle) => lienRoute(`/achats/${encodeURIComponent(cle)}`)],
  fournisseur: ["Fournisseurs", (cle) => lienRoute(`/fournisseurs/${encodeURIComponent(cle)}`)],
  ensemble: ["Ensembles", (cle) => lienRoute(`/ensembles/${encodeURIComponent(cle)}`)],
  bloc: ["Blocs fonctionnels", (cle) => lienRoute("/composants", { bloc: cle })],
};
const LONGUEUR_MIN = 2;

function saisieEnCours(cible) {
  return cible instanceof HTMLElement && (cible.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(cible.tagName));
}

export function installerRecherche(conteneur) {
  const champ = el("input", {
    class: "recherche-globale__champ",
    type: "search",
    placeholder: "Rechercher… (Ctrl+F ou /)",
    "aria-label": "Recherche globale",
    autocomplete: "off",
    role: "combobox",
    "aria-expanded": "false",
    "aria-controls": "recherche-globale-resultats",
  });
  const liste = el("div", { class: "recherche-globale__resultats", id: "recherche-globale-resultats", role: "listbox", hidden: true });
  conteneur.replaceChildren(champ, liste);
  let liens = [];
  let actif = -1;
  let minuterie = null;
  let demande = 0;

  const fermer = () => {
    liste.hidden = true;
    champ.setAttribute("aria-expanded", "false");
    actif = -1;
  };
  const surligner = (rang) => {
    liens.forEach((l, i) => l.classList.toggle("recherche-globale__lien--actif", i === rang));
    actif = rang;
    liens[rang]?.scrollIntoView({ block: "nearest" });
  };
  const ouvrir = (lien) => {
    window.location.hash = lien.getAttribute("href");
    champ.value = "";
    fermer();
    champ.blur();
  };
  const afficher = (groupes) => {
    liens = [];
    const contenu = groupes.map((g) => {
      const [titre, route] = TYPES[g.type];
      return el(
        "section",
        {},
        el("h3", { class: "recherche-globale__type" }, titre),
        g.resultats.map((r) => {
          const lien = el(
            "a",
            { class: `recherche-globale__lien${r.archive ? " texte-doux" : ""}`, href: route(r.cle), role: "option", onclick: (e) => { e.preventDefault(); ouvrir(e.currentTarget); } },
            el("span", { class: "code" }, r.cle),
            r.titre && r.titre !== r.cle ? el("span", {}, r.titre) : null,
            r.detail ? el("span", { class: "texte-doux" }, r.detail) : null,
            r.archive ? el("span", { class: "etiquette" }, "archivé") : null,
          );
          liens.push(lien);
          return lien;
        }),
      );
    });
    liste.replaceChildren(...(contenu.length ? contenu : [el("p", { class: "texte-doux recherche-globale__vide" }, "Aucun résultat.")]));
    liste.hidden = false;
    champ.setAttribute("aria-expanded", "true");
    surligner(liens.length ? 0 : -1);
  };
  const chercher = async () => {
    const texte = champ.value.trim();
    if (texte.length < LONGUEUR_MIN) return fermer();
    const numero = ++demande;
    try {
      const groupes = await api.rechercher(texte);
      if (numero === demande) afficher(groupes);
    } catch (erreur) {
      if (numero === demande) {
        liste.replaceChildren(el("p", { class: "texte-alerte recherche-globale__vide" }, erreur.message));
        liste.hidden = false;
      }
    }
  };

  champ.addEventListener("input", () => {
    clearTimeout(minuterie);
    minuterie = setTimeout(chercher, 200);
  });
  champ.addEventListener("focus", () => {
    if (champ.value.trim().length >= LONGUEUR_MIN) chercher();
  });
  champ.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && liens.length) {
      e.preventDefault();
      surligner((actif + 1) % liens.length);
    } else if (e.key === "ArrowUp" && liens.length) {
      e.preventDefault();
      surligner((actif - 1 + liens.length) % liens.length);
    } else if (e.key === "Enter" && actif >= 0) {
      e.preventDefault();
      ouvrir(liens[actif]);
    } else if (e.key === "Escape") {
      fermer();
      champ.blur();
    }
  });
  document.addEventListener("click", (e) => {
    if (!conteneur.contains(e.target)) fermer();
  });
  document.addEventListener("keydown", (e) => {
    const ctrlF = (e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "f";
    const barre = e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !saisieEnCours(e.target);
    // Déjà dans le champ : Ctrl+F retrouve la recherche dans la page du navigateur.
    if ((ctrlF && document.activeElement !== champ) || barre) {
      e.preventDefault();
      champ.focus();
      champ.select();
    }
  });
}
