// Modifications en masse depuis la liste des composants, dans le panneau latéral :
// champs et caractéristiques (« Modifier… ») ou affectation à un ensemble. Toujours un aperçu
// d'abord (changent, déjà à jour, refusés), puis l'application, tout ou rien.

import { api } from "../api.js";
import { PREFIXE, attribut, attributsActifs, champAttribut, formatAttribut, titreAttribut } from "../attributs.js";
import { formatNombre, libelle, lireNombre } from "../format.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, afficherInformation, el, masquerErreur } from "../ui.js";
import { BASES_PRIX, valeursListe } from "../valeurs.js";

const INCHANGE = "";
const EFFACER = "__effacer__";

const LIBELLES_CHAMPS = {
  mode_appro: "Mode d'appro",
  statut_appro: "Statut d'appro",
  statut_choix: "Statut de choix",
  criticite: "Criticité",
  fournisseur_nom: "Fournisseur",
  taux_tva: "Taux de TVA",
  base_prix_releve: "Base du prix",
};

function pluriel(n, mot) {
  return `${formatNombre(n)} ${mot}${n > 1 ? "s" : ""}`;
}

// Liste « Ne pas changer » / (« Effacer ») / valeurs.
function choix(nom, options, effacable) {
  const select = el("select", { class: "champ", name: nom }, el("option", { value: INCHANGE }, "Ne pas changer"));
  if (effacable) select.append(el("option", { value: EFFACER }, "Effacer"));
  for (const [code, texte] of options) select.append(el("option", { value: code }, texte));
  return select;
}

function ligne(texte, champ) {
  return el("label", { class: "ligne-champ" }, el("span", { class: "ligne-champ__libelle" }, texte), champ);
}

// --- Aperçu commun ----------------------------------------------------------------------------

function texteValeur(champ, valeur) {
  if (valeur === null || valeur === undefined || valeur === "") return "—";
  if (champ.startsWith(PREFIXE)) {
    const a = attribut(champ.slice(PREFIXE.length));
    return a ? formatAttribut(a, valeur) : String(valeur);
  }
  if (champ === "taux_tva") return `${formatNombre(valeur * 100, 1)} %`;
  return libelle(valeur) || String(valeur);
}

function texteChamp(champ) {
  if (champ.startsWith(PREFIXE)) {
    const a = attribut(champ.slice(PREFIXE.length));
    return a ? titreAttribut(a) : champ;
  }
  return LIBELLES_CHAMPS[champ] ?? champ;
}

function zoneApercu(recap, compteurs) {
  const lignes = compteurs.map(([texte, nombre, classe]) =>
    el("div", { class: "apercu-lot__ligne" }, el("span", {}, texte), el("span", { class: `apercu-lot__nombre apercu-lot__nombre--${classe}` }, formatNombre(nombre))),
  );
  const refus = recap.refuses.length
    ? el("ul", { class: "apercu-lot__refus" }, recap.refuses.map((r) => el("li", {}, el("span", { class: "code" }, r.id), ` : ${r.raison}`)))
    : null;
  let detail = null;
  if (recap.detail?.length) {
    const table = el(
      "table",
      { class: "table table--dense", hidden: true },
      el("thead", {}, el("tr", {}, ["ID", "Champ", "Avant", "Après"].map((t) => el("th", {}, t)))),
      el(
        "tbody",
        {},
        recap.detail.map((d) =>
          el("tr", {}, el("td", { class: "code" }, d.id), el("td", {}, texteChamp(d.champ)), el("td", { class: "apercu-lot__avant" }, texteValeur(d.champ, d.avant)), el("td", { class: "apercu-lot__apres" }, texteValeur(d.champ, d.apres))),
        ),
      ),
    );
    const bascule = el("button", { type: "button", class: "bouton-lien", "aria-expanded": "false" }, "voir le détail");
    bascule.addEventListener("click", () => {
      table.hidden = !table.hidden;
      bascule.setAttribute("aria-expanded", String(!table.hidden));
      bascule.textContent = table.hidden ? "voir le détail" : "masquer le détail";
    });
    detail = el("div", { class: "apercu-lot__detail" }, bascule, el("div", { class: "table-defilante" }, table));
  }
  return el("div", { class: "apercu-lot", role: "status" }, lignes, refus, detail);
}

// Pied du panneau : « Voir l'aperçu », puis « Appliquer » tant que rien n'a changé depuis.
function piedLot({ formulaire, lireCorps, envoyer, texteAppliquer, texteFait, nombreApplicable, surApplique }) {
  const zone = el("div");
  const appliquer = el("button", { type: "button", class: "bouton", disabled: true }, "Appliquer");
  const apercu = el("button", { type: "button", class: "bouton bouton--discret" }, "Voir l'aperçu");
  let corpsVu = null;

  const invalider = () => {
    corpsVu = null;
    appliquer.disabled = true;
    appliquer.textContent = "Appliquer";
    zone.replaceChildren();
  };
  formulaire.addEventListener("input", invalider);
  formulaire.addEventListener("change", invalider);

  apercu.addEventListener("click", async () => {
    const corps = lireCorps();
    if (corps.erreur) {
      afficherErreur(corps.erreur);
      return;
    }
    apercu.disabled = true;
    try {
      const recap = await envoyer({ ...corps.valeurs, simuler: true });
      masquerErreur();
      zone.replaceChildren(zoneApercu(recap, recap.compteurs));
      const n = nombreApplicable(recap);
      corpsVu = recap.refuses.length || !n ? null : corps.valeurs;
      appliquer.disabled = corpsVu === null;
      appliquer.textContent = texteAppliquer(n);
      if (recap.refuses.length) zone.append(el("p", { class: "texte-doux texte-petit" }, "Tout ou rien : retirez les composants refusés de la sélection, ou changez les valeurs, avant d'appliquer."));
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      apercu.disabled = false;
    }
  });

  appliquer.addEventListener("click", async () => {
    if (!corpsVu) return;
    appliquer.disabled = true;
    try {
      const recap = await envoyer({ ...corpsVu, simuler: false });
      if (!recap.applique) {
        zone.replaceChildren(zoneApercu(recap, recap.compteurs));
        afficherErreur("Rien n'a été modifié : la sélection a changé depuis l'aperçu. Relancez l'aperçu.");
        return;
      }
      masquerErreur();
      fermerPanneau({ silencieux: true });
      afficherInformation(texteFait(nombreApplicable(recap)));
      await surApplique();
    } catch (erreur) {
      afficherErreur(erreur);
      appliquer.disabled = false;
    }
  });

  return el("div", {}, zone, el("div", { class: "actions-formulaire" }, el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"), apercu, appliquer));
}

// --- Modifier les champs ------------------------------------------------------------------------

export function ouvrirModificationLot({ ids, fournisseurs, surApplique }) {
  const champs = {
    mode_appro: choix("mode_appro", valeursListe("mode_appro"), false),
    statut_appro: choix("statut_appro", valeursListe("statut_appro"), false),
    statut_choix: choix("statut_choix", valeursListe("statut_choix"), true),
    criticite: choix("criticite", valeursListe("criticite"), true),
    fournisseur_nom: choix("fournisseur_nom", fournisseurs.map((f) => [f.nom, f.nom]), true),
    base_prix_releve: choix("base_prix_releve", BASES_PRIX.map((b) => [b, b]), false),
  };
  const tva = el("input", { class: "champ champ--nombre", type: "text", inputmode: "decimal", name: "taux_tva", placeholder: "Ne pas changer" });
  const caracteristiques = attributsActifs().map((a) => {
    const champ = champAttribut(a, null);
    const effacer = el("input", { type: "checkbox" });
    effacer.addEventListener("change", () => {
      champ.element.disabled = effacer.checked;
    });
    if (champ.element.tagName === "SELECT") champ.element.firstChild.textContent = "Ne pas changer";
    else champ.element.placeholder = "Ne pas changer";
    return { a, champ, effacer };
  });

  const lireCorps = () => {
    const modifications = {};
    for (const [nom, select] of Object.entries(champs)) {
      if (select.value === EFFACER) modifications[nom] = null;
      else if (select.value !== INCHANGE) modifications[nom] = select.value;
    }
    if (tva.value.trim()) {
      const pourcent = lireNombre(tva.value.replace("%", "").trim());
      if (pourcent === null || Number.isNaN(pourcent) || pourcent < 0 || pourcent >= 100) return { erreur: "Taux de TVA : un pourcentage entre 0 et 100, par exemple 20." };
      modifications.taux_tva = pourcent / 100;
    }
    const attributs = {};
    for (const { a, champ, effacer } of caracteristiques) {
      if (effacer.checked) {
        attributs[a.code] = null;
        continue;
      }
      const lu = champ.lire();
      if (lu.erreur) return { erreur: lu.erreur };
      if (lu.valeur !== null) attributs[a.code] = lu.valeur;
    }
    if (!Object.keys(modifications).length && !Object.keys(attributs).length) return { erreur: "Choisissez au moins une valeur à poser." };
    return { valeurs: { ids, modifications, attributs } };
  };

  const formulaire = el(
    "form",
    { class: "formulaire", onsubmit: (e) => e.preventDefault() },
    el("p", { class: "texte-doux texte-petit" }, "Seuls les champs réglés changent. Les quantités, les prix et le bloc restent propres à chaque composant."),
    el("h3", { class: "titre-groupe" }, "Approvisionnement"),
    Object.entries(champs).map(([nom, select]) => ligne(LIBELLES_CHAMPS[nom], select)),
    ligne("Taux de TVA (%)", tva),
    caracteristiques.length ? el("h3", { class: "titre-groupe" }, "Caractéristiques") : null,
    caracteristiques.map(({ a, champ, effacer }) =>
      el(
        "div",
        { class: "ligne-champ" },
        el("span", { class: "ligne-champ__libelle" }, titreAttribut(a)),
        champ.element,
        el("label", { class: "filtre-case texte-petit" }, effacer, "effacer"),
      ),
    ),
  );
  formulaire.append(
    piedLot({
      formulaire,
      lireCorps,
      envoyer: async (corps) => {
        const recap = await api.modifierLot(corps);
        recap.compteurs = [
          ["Changent", recap.changent.length, "ok"],
          ["Déjà à jour", recap.a_jour.length, "neutre"],
          ["Refusés", recap.refuses.length, recap.refuses.length ? "alerte" : "neutre"],
        ];
        return recap;
      },
      nombreApplicable: (recap) => recap.changent.length,
      texteAppliquer: (n) => `Appliquer à ${pluriel(n, "composant")}`,
      texteFait: (n) => `${pluriel(n, "composant")} modifié${n > 1 ? "s" : ""}.`,
      surApplique,
    }),
  );
  ouvrirPanneau(`Modifier ${pluriel(ids.length, "composant")}`, formulaire);
}

// --- Affecter à un ensemble ----------------------------------------------------------------------

export function ouvrirAffectationLot({ ids, ensembles, surApplique }) {
  const ensemble = el(
    "select",
    { class: "champ", name: "ensemble_code", required: true },
    el("option", { value: "" }, "Choisir…"),
    ensembles.map((e) => el("option", { value: e.code }, `${" ".repeat((e.niveau ?? 1) - 1)}${e.code} · ${e.nom}`)),
  );
  const auBesoin = el("input", { type: "radio", name: "mode_qte", value: "besoin", checked: true });
  const fixe = el("input", { type: "radio", name: "mode_qte", value: "fixe" });
  const qte = el("input", { class: "champ champ--nombre", type: "text", inputmode: "numeric", name: "qte", value: "1" });

  const lireCorps = () => {
    if (!ensemble.value) return { erreur: "Choisissez l'ensemble." };
    let quantite = null;
    if (fixe.checked) {
      quantite = Number(qte.value);
      if (!Number.isInteger(quantite) || quantite <= 0) return { erreur: "Quantité fixe : un nombre entier de pièces, au moins 1." };
    }
    return { valeurs: { ids, ensemble_code: ensemble.value, qte: quantite } };
  };

  const formulaire = el(
    "form",
    { class: "formulaire", onsubmit: (e) => e.preventDefault() },
    ligne("Ensemble", ensemble),
    el(
      "div",
      { class: "ligne-champ" },
      el("span", { class: "ligne-champ__libelle" }, "Quantité"),
      el("div", { class: "choix-quantite" }, el("label", { class: "filtre-case" }, auBesoin, "le besoin de chaque composant"), el("label", { class: "filtre-case" }, fixe, "fixe : ", qte)),
    ),
    el("p", { class: "texte-doux texte-petit" }, "Un composant déjà affecté à cet ensemble garde son affectation."),
  );
  formulaire.append(
    piedLot({
      formulaire,
      lireCorps,
      envoyer: async (corps) => {
        const recap = await api.affecterLot(corps);
        recap.compteurs = [
          ["Nouvelles affectations", recap.nouvelles.length, "ok"],
          ["Déjà affectés à cet ensemble", recap.deja.length, "neutre"],
          ["Refusés", recap.refuses.length, recap.refuses.length ? "alerte" : "neutre"],
        ];
        return recap;
      },
      nombreApplicable: (recap) => recap.nouvelles.length,
      texteAppliquer: (n) => `Affecter ${pluriel(n, "composant")}`,
      texteFait: (n) => `${pluriel(n, "composant")} affecté${n > 1 ? "s" : ""} à l'ensemble.`,
      surApplique,
    }),
  );
  ouvrirPanneau(`Affecter ${pluriel(ids.length, "composant")}`, formulaire);
}
