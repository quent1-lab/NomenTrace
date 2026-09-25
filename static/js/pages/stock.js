// Écran stock (#/stock) : état du stock, journal des mouvements, saisie manuelle.

import { api } from "../api.js";
import { aujourdhui, formatDate, formatMontant, formatNombre, libelle, lireNombre } from "../format.js";
import { champChoix, champComposant, champTexte, ligneChamp, lireComposant } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { lienRoute, remplacerRoute } from "../router.js";
import { afficherAvertissements, afficherErreur, el, masquerErreur } from "../ui.js";
import { sensImpose, TYPES_MONTAGE, valeursListe } from "../valeurs.js";

let etat = null;

function tableStock() {
  if (!etat.stock.length) return el("p", { class: "texte-doux" }, "Aucun composant en stock.");
  const negatifs = etat.stock.filter((s) => s.stock_actuel < 0).length;
  return [
    negatifs ? el("p", { class: "texte-alerte texte-petit" }, `${negatifs} composant(s) en stock négatif : une entrée a probablement été oubliée.`) : null,
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, ["Composant", "Désignation", "Bloc", "Stock", "Emplacement", "Dernier mouvement", "Valeur HT"].map((t, i) => el("th", { class: [3, 6].includes(i) ? "nombre" : "" }, t)))),
      el(
        "tbody",
        {},
        etat.stock.map((s) =>
          el(
            "tr",
            { class: s.stock_actuel < 0 ? "ligne--negative" : "" },
            el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: s.id }) }, s.id)),
            el("td", { class: "tronque tronque--large", title: s.designation }, s.designation),
            el("td", {}, s.bloc_code),
            el("td", { class: `nombre fort ${s.stock_actuel < 0 ? "texte-alerte" : ""}` }, formatNombre(s.stock_actuel)),
            el("td", {}, s.emplacement ?? "—"),
            el("td", {}, formatDate(s.dernier_mouvement)),
            el("td", { class: "nombre" }, formatMontant(s.valeur_ht)),
          ),
        ),
      ),
    ),
  ];
}

function filtresMouvements() {
  const changer = async (cle, valeur) => {
    etat.filtres[cle] = valeur;
    remplacerRoute("/stock", Object.fromEntries(Object.entries(etat.filtres).filter(([, v]) => v)));
    await rechargerMouvements();
  };
  const composant = champComposant("filtre_composant", etat.composants);
  const entree = composant.querySelector("input");
  entree.classList.replace("champ", "filtre");
  entree.value = etat.filtres.composant;
  entree.addEventListener("change", () => changer("composant", lireComposant(entree.value, etat.composants)?.id ?? ""));
  return el(
    "div",
    { class: "filtres" },
    composant,
    el("select", { class: "filtre", onchange: (e) => changer("type_mouvement", e.target.value) }, el("option", { value: "" }, "Tous les types"), valeursListe("type_mouvement", { inclureInactives: true }).map(([code, texte]) => el("option", { value: code, selected: code === etat.filtres.type_mouvement }, texte))),
    el("select", { class: "filtre", onchange: (e) => changer("ensemble", e.target.value) }, el("option", { value: "" }, "Tous les ensembles"), etat.ensembles.map((e) => el("option", { value: e.code, selected: e.code === etat.filtres.ensemble }, `${e.code} — ${e.nom}`))),
  );
}

function rendreMouvements() {
  etat.zoneMouvements.replaceChildren(
    etat.mouvements.length
      ? el(
          "table",
          { class: "table table--dense" },
          el("thead", {}, el("tr", {}, ["Date", "Composant", "Désignation", "Type", "Qté", "Ensemble", "Emplacement", "Par", "Commande", "Commentaire"].map((t, i) => el("th", { class: i === 4 ? "nombre" : "" }, t)))),
          el(
            "tbody",
            {},
            etat.mouvements.map((m) =>
              el(
                "tr",
                {},
                el("td", {}, formatDate(m.date)),
                el("td", { class: "code" }, el("a", { href: lienRoute("/composants", { fiche: m.composant_id }) }, m.composant_id)),
                el("td", { class: "tronque", title: m.designation }, m.designation),
                el("td", {}, libelle(m.type_mouvement)),
                el("td", { class: `nombre fort ${m.sens === "Sortie" ? "texte-surveiller" : "texte-conforme"}` }, `${m.sens === "Sortie" ? "−" : "+"}${formatNombre(m.qte)}`),
                el("td", {}, m.ensemble_code ? el("a", { href: lienRoute(`/ensembles/${m.ensemble_code}`) }, m.ensemble_code) : ""),
                el("td", {}, m.emplacement ?? ""),
                el("td", {}, m.par_qui ?? ""),
                el("td", {}, m.commande_numero ? el("a", { href: lienRoute(`/achats/${m.commande_numero}`) }, m.commande_numero) : ""),
                el("td", { class: "tronque", title: m.commentaire ?? "" }, m.commentaire ?? ""),
              ),
            ),
          ),
        )
      : el("p", { class: "texte-doux" }, "Aucun mouvement ne correspond."),
  );
}

async function rechargerMouvements() {
  etat.mouvements = await api.getMouvements(etat.filtres);
  rendreMouvements();
}

// --- Saisie manuelle ------------------------------------------------------------------------

function ouvrirSaisie() {
  const types = valeursListe("type_mouvement").filter(([code]) => code !== "Reception achat");
  const type = champChoix("type_mouvement", types, types[0]?.[0] ?? null);
  const sens = champChoix("sens", [["Entree", "Entrée"], ["Sortie", "Sortie"]], "Entree");
  const texteSens = el("span", { class: "texte-doux" });
  const ensemble = champChoix("ensemble_code", etat.ensembles.map((e) => [e.code, `${e.code} — ${e.nom}`]), null, { vide: "— choisir —" });
  const ligneSens = ligneChamp("Sens", el("span", {}, sens, texteSens));
  const ligneEnsemble = ligneChamp("Ensemble", ensemble, { requis: true });
  // Le sens est imposé par le type (sauf inventaire) ; l'ensemble n'existe que pour le montage.
  const adapter = () => {
    const impose = sensImpose(type.value);
    sens.hidden = Boolean(impose);
    texteSens.textContent = impose ? `${impose === "Entree" ? "Entrée" : "Sortie"} (imposé par le type)` : "";
    ligneEnsemble.hidden = !TYPES_MONTAGE.includes(type.value);
  };
  type.addEventListener("change", adapter);
  const composant = champComposant("composant", etat.composants, { requis: true });
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    el("p", { class: "note-formulaire" }, "Les réceptions d'achat se saisissent depuis la commande (mode réception). Ici : montage, prêts, retours, pertes et inventaires. Les types se gèrent dans Paramètres."),
    ligneChamp("Date", el("input", { class: "champ champ--date", type: "date", name: "date", value: aujourdhui() }), { requis: true }),
    ligneChamp("Composant", composant, { requis: true }),
    ligneChamp("Type", type, { requis: true }),
    ligneSens,
    ligneEnsemble,
    ligneChamp("Quantité", el("input", { class: "champ champ--nombre", type: "text", inputmode: "numeric", name: "qte" }), { requis: true }),
    ligneChamp("Emplacement", champTexte("emplacement")),
    ligneChamp("Par qui", champTexte("par_qui")),
    ligneChamp("Commentaire", champTexte("commentaire")),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, "Enregistrer le mouvement"),
    ),
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = formulaire.elements;
    const choisi = lireComposant(f.composant.value, etat.composants);
    if (!choisi) return afficherErreur("Choisir un composant dans la liste.");
    const qte = lireNombre(f.qte.value);
    if (qte === null || Number.isNaN(qte) || !Number.isInteger(qte) || qte <= 0) return afficherErreur("La quantité doit être un entier supérieur à zéro.");
    const montage = TYPES_MONTAGE.includes(type.value);
    if (montage && !ensemble.value) return afficherErreur(`Un mouvement « ${libelle(type.value)} » doit désigner un ensemble.`);
    if (!f.date.value) return afficherErreur("La date est obligatoire.");
    const valeurs = {
      date: f.date.value,
      composant_id: choisi.id,
      type_mouvement: type.value,
      sens: sensImpose(type.value) ? null : sens.value,
      qte,
      ensemble_code: montage ? ensemble.value : null,
      emplacement: f.emplacement.value.trim() || null,
      par_qui: f.par_qui.value.trim() || null,
      commentaire: f.commentaire.value.trim() || null,
    };
    try {
      const resultat = await api.createMouvement(valeurs);
      masquerErreur();
      afficherAvertissements(resultat.avertissements);
      fermerPanneau({ silencieux: true });
      await recharger();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau("Nouveau mouvement de stock", formulaire);
  adapter();
}

async function recharger() {
  const [stock, mouvements] = await Promise.all([api.getStock(), api.getMouvements(etat.filtres)]);
  Object.assign(etat, { stock, mouvements });
  etat.zoneStock.replaceChildren(...[tableStock()].flat().filter(Boolean));
  rendreMouvements();
}

export async function afficherStock(conteneur, parametres) {
  const [composants, ensembles] = await Promise.all([api.getComposants({ tri: "id" }), api.getEnsembles()]);
  etat = {
    composants,
    ensembles,
    filtres: {
      composant: parametres.get("composant") || "",
      type_mouvement: parametres.get("type_mouvement") || "",
      ensemble: parametres.get("ensemble") || "",
    },
    zoneStock: el("div"),
    zoneMouvements: el("div"),
  };
  conteneur.replaceChildren(
    el("div", { class: "titre-page" }, el("h1", {}, "Stock"), el("button", { type: "button", class: "bouton si-ecriture", onclick: ouvrirSaisie }, "+ Nouveau mouvement")),
    el("section", { class: "panneau" }, el("h2", {}, "État du stock"), etat.zoneStock),
    el("section", { class: "panneau" }, el("h2", {}, "Journal des mouvements"), filtresMouvements(), etat.zoneMouvements),
  );
  await recharger();
}
