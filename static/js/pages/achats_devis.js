// Préparation des demandes de devis : les composants qu'il reste à commander, regroupés par
// fournisseur ; une demande (devis « À demander ») est créée par fournisseur coché.

import { api } from "../api.js";
import { formatMontant, formatNombre } from "../format.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { lienRoute, naviguer } from "../router.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";

function lienComposant(id) {
  return el("a", { href: lienRoute("/composants", { fiche: id }) }, id);
}

function tableGroupe(groupe, cases, surChangement) {
  const casesGroupe = [];
  const lignes = groupe.lignes.map((l) => {
    const deja = l.demandes_ouvertes.length > 0;
    const coche = el("input", { type: "checkbox", checked: !deja, "aria-label": `Demander ${l.id}` });
    coche.addEventListener("change", surChangement);
    cases.set(l.id, coche);
    casesGroupe.push(coche);
    return el(
      "tr",
      {},
      el("td", {}, coche),
      el("td", { class: "code" }, lienComposant(l.id)),
      el("td", { class: "tronque", title: l.designation }, l.designation),
      el("td", {}, l.bloc_code),
      el("td", { class: "nombre" }, formatNombre(l.reste_a_commander)),
      el("td", { class: "nombre" }, l.pu_ht === null ? el("span", { class: "a-chiffrer" }, "à chiffrer") : formatMontant(l.pu_ht)),
      el("td", { class: "texte-petit" }, deja ? el("span", { class: "texte-surveiller", title: "Déjà dans une demande en cours : décoché d'office" }, `déjà dans ${l.demandes_ouvertes.join(", ")}`) : ""),
    );
  });
  const tout = el("input", { type: "checkbox", checked: casesGroupe.every((c) => c.checked), "aria-label": `Tout ${groupe.fournisseur_nom}` });
  tout.addEventListener("change", () => {
    casesGroupe.forEach((c) => (c.checked = tout.checked));
    surChangement();
  });
  return el(
    "table",
    { class: "table table--dense selecteur" },
    el(
      "thead",
      {},
      el("tr", {}, el("th", {}, tout), el("th", { colspan: 6 }, groupe.fournisseur_nom, el("span", { class: "texte-doux" }, ` — ${groupe.lignes.length} composant(s)`))),
      el("tr", { class: "texte-petit" }, ["", "ID", "Désignation", "Bloc", "Reste à commander", "PU HT connu", ""].map((t, i) => el("th", { class: i === 4 || i === 5 ? "nombre texte-doux" : "texte-doux" }, t))),
    ),
    el("tbody", {}, lignes),
  );
}

export async function ouvrirDemandesDevis() {
  const candidats = await api.getCandidatsDevis();
  const cases = new Map();
  const bouton = el("button", { type: "submit", class: "bouton" });
  const majBouton = () => {
    const choisis = candidats.fournisseurs.flatMap((g) => g.lignes.filter((l) => cases.get(l.id).checked).map(() => g.fournisseur_nom));
    const nbFournisseurs = new Set(choisis).size;
    bouton.textContent = choisis.length ? `Créer ${nbFournisseurs} demande(s) de devis — ${choisis.length} composant(s)` : "Aucun composant coché";
    bouton.disabled = !choisis.length;
  };
  const groupes = candidats.fournisseurs.map((g) => tableGroupe(g, cases, majBouton));
  const sansFournisseur = candidats.sans_fournisseur.length
    ? el(
        "section",
        { class: "devis__sans-fournisseur" },
        el("h3", {}, `Sans fournisseur (${candidats.sans_fournisseur.length})`),
        el("p", { class: "texte-doux texte-petit" }, "Renseigner leur fournisseur sur leur fiche pour pouvoir les demander."),
        el("p", {}, candidats.sans_fournisseur.map((l, i) => [i ? ", " : "", lienComposant(l.id)])),
      )
    : null;
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    el("p", { class: "texte-doux" }, "Composants en mode Achat dont il reste des pièces à commander, regroupés par fournisseur. Chaque fournisseur coché reçoit une demande de devis « À demander » ; chaque ligne porte le reste à commander, le PU HT du devis restant à saisir à réception du devis."),
    candidats.fournisseurs.length ? groupes : el("p", { class: "texte-doux" }, "Rien à commander chez un fournisseur connu."),
    sansFournisseur,
    el("div", { class: "actions-formulaire" }, el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"), bouton),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const composants = [...cases].filter(([, c]) => c.checked).map(([id]) => id);
    bouton.disabled = true;
    try {
      const creees = await api.creerDemandesDevis(composants);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      alert(`Demandes de devis créées : ${creees.map((c) => `${c.numero} (${c.fournisseur_nom})`).join(", ")}.`);
      naviguer("/achats", { statut: "A demander" });
    } catch (erreur) {
      afficherErreur(erreur);
      majBouton();
    }
  });
  majBouton();
  ouvrirPanneau("Préparer les demandes de devis", formulaire);
}
