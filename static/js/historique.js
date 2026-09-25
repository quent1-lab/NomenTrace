// Lecture de l'historique : texte d'un événement, lien vers sa source, frise d'un composant.
// Partagé par la fiche composant et l'onglet Paramètres › Historique.

import { formatDate, libelle } from "./format.js";
import { lienRoute } from "./router.js";
import { el } from "./ui.js";

export const CATEGORIES = [
  ["modification", "Modifications"],
  ["achat", "Achats"],
  ["stock", "Stock"],
  ["montage", "Montage"],
  ["document", "Documents"],
];

// Noms lisibles des champs les plus courants ; les autres s'affichent tels quels.
const CHAMPS = {
  designation: "Désignation",
  fonction: "Fonction",
  mode_appro: "Mode d'appro",
  statut_appro: "Statut d'appro",
  statut_choix: "Statut de choix",
  criticite: "Criticité",
  qte_besoin: "Qté besoin",
  qte_rechange: "Qté rechange",
  qte_disponible: "Qté disponible",
  pu_releve: "PU relevé",
  base_prix_releve: "Base du prix",
  taux_tva: "Taux de TVA",
  fournisseur_nom: "Fournisseur",
  ref_fabricant: "Réf. fabricant",
  fabricant: "Fabricant",
  lien_produit: "Lien produit",
  remplace_par: "Remplacé par",
  archive: "Archivé",
  qte_commandee: "Qté commandée",
  qte_recue: "Qté reçue",
  pu_ht_devis: "PU HT devis",
  statut_ligne: "Statut de ligne",
  date_reception: "Date de réception",
  statut: "Statut",
  type: "Type",
  date_commande: "Date de commande",
  livraison_annoncee: "Livraison annoncée",
  date_reception_reelle: "Date de réception réelle",
  date_demande: "Date de demande",
  port_ht: "Port HT",
  statut_montage: "Statut de montage",
  parent_code: "Ensemble parent",
  budget_cible_ht: "Budget cible HT",
  budget_verrouille: "Budget verrouillé",
  nom: "Nom",
  ordre: "Ordre",
  qte: "Quantité",
};

const TABLES = {
  composant: "Composant",
  composant_attribut: "Caractéristique",
  affectation: "Affectation",
  commande: "Commande",
  ligne_commande: "Ligne de commande",
  ensemble: "Ensemble",
  bloc: "Bloc",
  fournisseur: "Fournisseur",
  document: "Document",
  parametre: "Paramètre",
  valeur_liste: "Valeur de liste",
  attribut: "Attribut",
  attribut_valeur: "Valeur d'attribut",
  mouvement_stock: "Mouvement de stock",
};

export function libelleTable(table) {
  return TABLES[table] ?? table;
}

function valeur(v) {
  if (v === null || v === undefined || v === "") return "—";
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? formatDate(v) : libelle(v);
}

function changement(nom, e) {
  return `${nom} : ${valeur(e.ancienne_valeur)} → ${valeur(e.nouvelle_valeur)}`;
}

// L'ensemble ou la commande d'un mouvement est porté par le lien vers sa source.
function texteMouvement(e) {
  const signe = e.sens === "Sortie" ? "−" : "+";
  return [`${libelle(e.type_mouvement)} ${signe}${e.qte}`, e.emplacement].filter(Boolean).join(" · ");
}

// L'ensemble concerné est porté par le lien vers la source.
function texteAffectation(e) {
  if (e.champ === "composant_id") return `Affectation reprise de ${e.ancienne_valeur}`;
  if (e.ancienne_valeur === null) return `Affecté à l'ensemble : ${e.nouvelle_valeur}`;
  if (e.nouvelle_valeur === null) return "Retiré de l'ensemble";
  return `Quantité affectée : ${e.ancienne_valeur} → ${e.nouvelle_valeur}`;
}

function texteCommande(e, composant) {
  if (e.champ?.startsWith("ligne ")) {
    if (composant) return e.nouvelle_valeur === composant ? "Ajouté à la commande" : "Retiré de la commande";
    return e.nouvelle_valeur ? `Ligne ajoutée : ${e.nouvelle_valeur}` : `Ligne retirée : ${e.ancienne_valeur}`;
  }
  if (e.champ?.startsWith("document ")) return e.nouvelle_valeur ? `Document joint : ${e.nouvelle_valeur}` : "Document retiré";
  return changement(CHAMPS[e.champ] ?? e.champ, e);
}

/** Texte d'un événement ; `composant` précise le point de vue de la frise d'un composant. */
export function texteEvenement(e, composant = null) {
  if (e.table_cible === "mouvement_stock") return texteMouvement(e);
  if (e.champ === "creation") return e.nouvelle_valeur && !["créé", "créée"].includes(e.nouvelle_valeur) ? `Créé (${e.nouvelle_valeur})` : "Créé";
  if (e.champ === "suppression") return "Supprimé";
  if (e.table_cible === "affectation") return texteAffectation(e);
  if (e.table_cible === "commande") return texteCommande(e, composant);
  if (e.table_cible === "ligne_commande") return `Ligne — ${changement(CHAMPS[e.champ] ?? e.champ, e)}`;
  if (e.table_cible === "composant_attribut") return changement(`Caractéristique ${e.cle_cible.split(":").slice(1).join(":")}`, e);
  if (e.champ?.startsWith("document ")) return e.nouvelle_valeur ? `Document joint : ${e.nouvelle_valeur}` : "Document retiré";
  return changement(CHAMPS[e.champ] ?? e.champ ?? "", e);
}

/** Lien vers la source d'un événement, ou null. */
export function lienEvenement(e) {
  const cle = e.cle_cible ?? "";
  if (e.commande_numero) return [lienRoute(`/achats/${encodeURIComponent(e.commande_numero)}`), e.commande_numero];
  if (e.ensemble_code) return [lienRoute(`/ensembles/${encodeURIComponent(e.ensemble_code)}`), e.ensemble_code];
  switch (e.table_cible) {
    case "composant":
      return [lienRoute("/composants", { fiche: cle }), cle];
    case "composant_attribut":
      return [lienRoute("/composants", { fiche: cle.split(":")[0] }), cle.split(":")[0]];
    case "affectation":
      return [lienRoute(`/ensembles/${encodeURIComponent(cle.split(":")[0])}`), cle.split(":")[0]];
    case "commande":
      return [lienRoute(`/achats/${encodeURIComponent(cle)}`), cle];
    case "ensemble":
      return [lienRoute(`/ensembles/${encodeURIComponent(cle)}`), cle];
    case "fournisseur":
      return [lienRoute(`/fournisseurs/${encodeURIComponent(cle)}`), cle];
    case "bloc":
      return [lienRoute("/composants", { bloc: cle }), cle];
    default:
      return null;
  }
}

export function formatHorodatage(horodatage) {
  const heure = horodatage.length > 10 ? ` ${horodatage.slice(11, 16)}` : "";
  return `${formatDate(horodatage)}${heure}`;
}

export function origineEvenement(e) {
  if (e.nom_fichier) return el("a", { href: lienRoute(`/imports/${e.lot_id}`), title: e.nom_fichier }, "import");
  return e.origine === "import" ? "import" : "";
}

/** Frise d'un composant, filtrable par catégorie. */
export function frise(evenements, composant) {
  const actives = new Set(CATEGORIES.map(([code]) => code));
  const liste = el("ol", { class: "frise" });
  const presentes = new Set(evenements.map((e) => e.categorie));
  const rendre = () => {
    const visibles = evenements.filter((e) => actives.has(e.categorie));
    liste.replaceChildren(
      ...visibles.map((e) => {
        const lien = lienEvenement(e);
        const montrerLien = lien && !(e.table_cible === "composant" && e.cle_cible === composant);
        return el(
          "li",
          { class: `frise__evenement frise__evenement--${e.categorie}` },
          el("span", { class: "frise__date" }, formatHorodatage(e.horodatage)),
          el("span", { class: "frise__texte" }, montrerLien ? [el("a", { class: "frise__source", href: lien[0] }, lien[1]), " "] : null, texteEvenement(e, composant)),
          el("span", { class: "frise__origine texte-doux" }, origineEvenement(e)),
        );
      }),
    );
    if (!visibles.length) liste.append(el("li", { class: "texte-doux" }, "Aucun événement."));
  };
  const filtres = el(
    "div",
    { class: "frise__filtres" },
    CATEGORIES.filter(([code]) => presentes.has(code)).map(([code, titre]) =>
      el(
        "label",
        { class: `filtre-case frise__categorie frise__categorie--${code}` },
        el("input", {
          type: "checkbox",
          checked: true,
          onchange: (ev) => {
            if (ev.target.checked) actives.add(code);
            else actives.delete(code);
            rendre();
          },
        }),
        titre,
      ),
    ),
  );
  rendre();
  if (!evenements.length) return el("p", { class: "texte-doux" }, "Aucun événement enregistré.");
  return el("div", {}, filtres, liste);
}
