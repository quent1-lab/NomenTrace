// Revue d'un dépôt (#/imports/N) : chaque proposition se coche, champ par champ pour les
// modifications ; un seul bouton applique la sélection, en une transaction côté serveur.

import { api } from "../api.js";
import { PREFIXE, attribut, chargerAttributs, formatAttribut, titreAttribut } from "../attributs.js";
import { formatMontant, formatNombre, formatPourcent, libelle } from "../format.js";
import { lienRoute, naviguer } from "../router.js";
import { afficherAvertissements, afficherErreur, el, masquerErreur } from "../ui.js";
import { resumeCategories } from "./imports.js";

const CHAMPS = {
  bloc_code: "Bloc",
  fonction: "Fonction",
  designation: "Désignation",
  ref_fabricant: "Réf fabricant",
  fabricant: "Fabricant",
  mode_appro: "Mode appro",
  fournisseur_nom: "Fournisseur",
  lien_produit: "Lien produit",
  qte_besoin: "Qté besoin",
  qte_rechange: "Qté rechange",
  qte_disponible: "Qté déjà disponible",
  pu_releve: "PU relevé",
  base_prix_releve: "Base prix",
  taux_tva: "Taux TVA",
  statut_choix: "Statut choix",
  statut_appro: "Statut appro",
  criticite: "Criticité",
  origine_exigence: "Origine exigence",
  note_technique: "Note technique",
};

let etat = null;

// Libellé d'un champ : ceux du composant, ou « Tension (V) » pour un attribut.
function nomChamp(champ) {
  if (champ.startsWith(PREFIXE)) {
    const a = attribut(champ.slice(PREFIXE.length));
    return a ? titreAttribut(a) : champ.slice(PREFIXE.length);
  }
  return nomChamp(champ);
}

function valeur(champ, v) {
  if (v === null || v === undefined || v === "") return el("span", { class: "texte-doux" }, "vide");
  if (champ.startsWith(PREFIXE)) {
    const a = attribut(champ.slice(PREFIXE.length));
    return a ? formatAttribut(a, v) : String(v);
  }
  if (champ === "pu_releve") return formatMontant(v);
  if (champ === "taux_tva") return formatPourcent(v * 100, 1);
  if (typeof v === "number") return formatNombre(v);
  return libelle(v);
}

function origine(ligne) {
  return el("span", { class: "texte-doux texte-petit" }, `${ligne.donnees.fichier}, ligne ${ligne.numero_ligne}`);
}

function avertissements(ligne) {
  const liste = ligne.donnees.avertissements ?? [];
  return liste.length ? el("ul", { class: "avertissements-ligne" }, liste.map((a) => el("li", {}, a))) : null;
}

// Avertissements résumés dans une cellule de tableau, détaillés au survol.
function remarques(ligne) {
  const liste = ligne.donnees.avertissements ?? [];
  if (!liste.length) return null;
  return el("div", { class: "texte-surveiller texte-petit", title: liste.join("\n") }, liste.length > 1 ? `${liste.length} remarques` : liste[0]);
}

function lienComposant(id) {
  return el("a", { href: lienRoute("/composants", { fiche: id }) }, id);
}

// --- Décisions par défaut (ce qui est coché à l'ouverture) ------------------------------------

function decisionParDefaut(ligne) {
  const d = ligne.donnees;
  if (ligne.categorie === "MODIFIE") return { champs: Object.keys(d.differences) };
  if (ligne.categorie === "NOUVEAU" || ligne.categorie === "DOUBLON") {
    if (d.action_defaut !== "fusionner") return { action: "creer" };
    const meilleur = d.candidats.find((c) => c.fusion);
    return { action: "fusionner", cible: meilleur.type === "composant" ? { composant: meilleur.id } : { ligne: meilleur.ligne_id } };
  }
  if (ligne.categorie.endsWith("_AFFECTATION")) return { action: "appliquer" };
  if (ligne.categorie === "NOUVELLE_ENTITE") return { action: "creer" };
  return null;
}

// --- Sections ---------------------------------------------------------------------------------

function carteModifie(ligne) {
  const d = ligne.donnees;
  const decision = etat.decisions[ligne.id];
  const cases = Object.entries(d.differences).map(([champ, diff]) => {
    const coche = el("input", { type: "checkbox", checked: decision.champs.includes(champ), disabled: !etat.modifiable, "aria-label": `Accepter ${nomChamp(champ)}` });
    coche.addEventListener("change", () => {
      decision.champs = coche.checked ? [...new Set([...decision.champs, champ])] : decision.champs.filter((c) => c !== champ);
    });
    return { champ, diff, coche };
  });
  const tout = (valeurCoche) => () => {
    cases.forEach((c) => (c.coche.checked = valeurCoche));
    decision.champs = valeurCoche ? cases.map((c) => c.champ) : [];
  };
  return el(
    "article",
    { class: "carte-import" },
    el("header", { class: "carte-import__entete" },
      el("div", {}, lienComposant(ligne.composant_id), ` ${d.designation} `, origine(ligne)),
      etat.modifiable ? el("div", { class: "actions" },
        el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: tout(true) }, "Tout accepter"),
        el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: tout(false) }, "Tout refuser"),
      ) : null,
    ),
    avertissements(ligne),
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, ["", "Champ", "Valeur actuelle", "Valeur proposée"].map((t) => el("th", {}, t)))),
      el("tbody", {}, cases.map(({ champ, diff, coche }) => el("tr", {},
        el("td", {}, coche),
        el("td", {}, nomChamp(champ)),
        el("td", { class: "valeur-actuelle" }, valeur(champ, diff.actuel)),
        el("td", { class: "valeur-proposee" }, valeur(champ, diff.propose)),
      ))),
    ),
  );
}

function resumeValeurs(valeurs, affectation) {
  const caracteristiques = Object.keys(valeurs).filter((c) => c.startsWith(PREFIXE) && valeurs[c] !== null);
  const champs = ["bloc_code", "fonction", "designation", "ref_fabricant", "mode_appro", "qte_besoin", "pu_releve", ...caracteristiques];
  return el(
    "dl",
    { class: "fiche__champs fiche__champs--compact" },
    champs.flatMap((c) => [el("dt", {}, nomChamp(c)), el("dd", {}, valeur(c, valeurs[c]))]),
    affectation ? [el("dt", {}, "Ensemble"), el("dd", {}, `${affectation.ensemble} × ${affectation.qte}`)] : [],
  );
}

function choixDoublon(ligne) {
  const d = ligne.donnees;
  const decision = etat.decisions[ligne.id];
  const nom = `doublon-${ligne.id}`;
  const option = (valeurDecision, contenu, coche) => {
    const radio = el("input", { type: "radio", name: nom, checked: coche, disabled: !etat.modifiable });
    radio.addEventListener("change", () => {
      Object.keys(decision).forEach((k) => delete decision[k]);
      Object.assign(decision, valeurDecision);
    });
    return el("label", { class: "choix-doublon" }, radio, el("div", {}, contenu));
  };
  const estCible = (c) => decision.action === "fusionner" && (c.type === "composant" ? decision.cible?.composant === c.id : decision.cible?.ligne === c.ligne_id);
  const candidats = d.candidats.map((c) => {
    const cible = c.type === "composant" ? { composant: c.id } : { ligne: c.ligne_id };
    const titre = c.type === "composant"
      ? [el("strong", {}, "Fusionner avec "), lienComposant(c.id), ` ${c.designation}`]
      : [el("strong", {}, "Fusionner avec la ligne "), `${c.fichier}, ligne ${c.numero}`, ` (${c.designation})`];
    const detail = c.type === "composant"
      ? `Réf. ${c.ref_fabricant ?? "—"} · besoin actuel ${c.qte_besoin}, augmenté de ${d.valeurs.qte_besoin}`
      : "Nouveau composant proposé dans ce même dépôt : un seul sera créé.";
    const niveau = el("span", { class: `score-doublon ${c.fusion ? "score-doublon--fort" : ""}` }, `niveau ${c.niveau} · ${Math.round(c.score * 100)} % · ${c.motif}`);
    return option({ action: "fusionner", cible }, [el("div", {}, ...titre), el("div", { class: "texte-petit texte-doux" }, detail), niveau], estCible(c));
  });
  return el(
    "div",
    { class: "choix-doublons" },
    candidats,
    option({ action: "creer" }, [el("strong", {}, "Créer quand même"), el("span", { class: "texte-doux" }, ` sous l'identifiant ${d.id_indicatif} (indicatif)`)], decision.action === "creer"),
    option({ action: "ignorer" }, el("strong", {}, "Ignorer cette ligne"), decision.action === "ignorer"),
  );
}

function carteDoublon(ligne) {
  const d = ligne.donnees;
  return el(
    "article",
    { class: "carte-import carte-import--doublon" },
    el("header", { class: "carte-import__entete" }, el("div", {}, el("strong", {}, d.valeurs.designation), " ", origine(ligne))),
    avertissements(ligne),
    el("div", { class: "grille-doublon" },
      el("div", {}, el("h4", {}, "Ligne proposée"), resumeValeurs(d.valeurs, d.affectation)),
      el("div", {}, el("h4", {}, "Que faire ?"), choixDoublon(ligne)),
    ),
  );
}

function tableNouveaux(lignes) {
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, ["Créer", "ID attribué", "Bloc", "Fonction", "Désignation", "Réf fabricant", "Mode", "Qté", "PU relevé", "Ensemble", "Origine"].map((t) => el("th", {}, t)))),
    el("tbody", {}, lignes.map((ligne) => {
      const d = ligne.donnees;
      const decision = etat.decisions[ligne.id];
      const coche = el("input", { type: "checkbox", checked: decision.action === "creer", disabled: !etat.modifiable, "aria-label": `Créer ${d.valeurs.designation}` });
      coche.addEventListener("change", () => (decision.action = coche.checked ? "creer" : "ignorer"));
      const v = d.valeurs;
      return el("tr", {},
        el("td", {}, coche),
        el("td", { class: "code texte-doux", title: "Indicatif : attribué définitivement à l'application" }, d.id_indicatif),
        el("td", {}, v.bloc_code),
        el("td", { class: "tronque" }, v.fonction),
        el("td", { class: "tronque tronque--large", title: v.designation }, v.designation),
        el("td", {}, v.ref_fabricant ?? ""),
        el("td", {}, libelle(v.mode_appro)),
        el("td", { class: "nombre" }, formatNombre(v.qte_besoin)),
        el("td", { class: "nombre" }, v.pu_releve === null ? "" : `${formatMontant(v.pu_releve)} ${v.base_prix_releve}`),
        el("td", {}, d.affectation ? `${d.affectation.ensemble} × ${d.affectation.qte}` : ""),
        el("td", {}, origine(ligne), remarques(ligne)),
      );
    })),
  );
}

function tableAffectations(lignes) {
  const types = { CREATION_AFFECTATION: "à créer", MODIF_AFFECTATION: "quantité modifiée", SUPPRESSION_AFFECTATION: "à retirer" };
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, ["Appliquer", "Ensemble", "Composant", "Changement", "Qté actuelle", "Qté proposée", "Origine"].map((t) => el("th", {}, t)))),
    el("tbody", {}, lignes.map((ligne) => {
      const d = ligne.donnees;
      const decision = etat.decisions[ligne.id];
      const coche = el("input", { type: "checkbox", checked: decision.action === "appliquer", disabled: !etat.modifiable });
      coche.addEventListener("change", () => (decision.action = coche.checked ? "appliquer" : "ignorer"));
      return el("tr", {},
        el("td", {}, coche),
        el("td", {}, el("a", { href: lienRoute(`/ensembles/${d.ensemble}`) }, d.ensemble)),
        el("td", {}, lienComposant(ligne.composant_id)),
        el("td", {}, types[ligne.categorie]),
        el("td", { class: "nombre" }, d.qte_actuelle ?? "—"),
        el("td", { class: "nombre fort" }, d.qte_proposee ?? "—"),
        el("td", {}, origine(ligne)),
      );
    })),
  );
}

const TYPES_ENTITE = { fournisseur: "Fournisseur", ensemble: "Ensemble" };

function tableEntites(lignes) {
  const libelleListe = { mode_appro: "Mode appro", statut_appro: "Statut appro", statut_choix: "Statut choix", criticite: "Criticité" };
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, ["Créer", "Type", "Valeur", "Code", "Première citation"].map((t) => el("th", {}, t)))),
    el("tbody", {}, lignes.map((ligne) => {
      const e = ligne.donnees.entite;
      const decision = etat.decisions[ligne.id];
      const coche = el("input", { type: "checkbox", checked: decision.action === "creer", disabled: !etat.modifiable });
      coche.addEventListener("change", () => (decision.action = coche.checked ? "creer" : "ignorer"));
      const type = TYPES_ENTITE[e.type] ?? `Valeur de la liste « ${libelleListe[e.liste] ?? e.liste} »`;
      return el("tr", {},
        el("td", {}, coche),
        el("td", {}, type),
        el("td", { class: "fort" }, e.nom ?? e.libelle, e.type === "fournisseur" ? el("span", { class: "texte-doux texte-petit" }, " — créé « à valider »") : null),
        el("td", { class: "code texte-doux" }, e.code ?? ""),
        el("td", {}, origine(ligne)),
      );
    })),
  );
}

function tableRejets(lignes) {
  return el(
    "table",
    { class: "table table--dense" },
    el("thead", {}, el("tr", {}, ["Origine", "Catégorie", "Raison", "Contenu de la ligne"].map((t) => el("th", {}, t)))),
    el("tbody", {}, lignes.map((ligne) => el("tr", {},
      el("td", {}, origine(ligne)),
      el("td", {}, ligne.categorie === "INCONNU" ? "inconnu" : "invalide"),
      el("td", { class: "texte-alerte" }, (ligne.donnees.raisons ?? []).join(" ; ")),
      el("td", { class: "texte-petit texte-doux" }, Object.entries(ligne.donnees.brut ?? {}).map(([k, v]) => `${k} : ${v}`).join(" · ")),
    ))),
  );
}

function section(id, titre, aide, contenu) {
  return el("section", { class: "panneau", id }, el("h2", {}, titre), aide ? el("p", { class: "texte-doux texte-petit" }, aide) : null, contenu);
}

function sections() {
  const par = (...categories) => etat.depot.lignes.filter((l) => categories.includes(l.categorie));
  const resultat = [];
  const entites = par("NOUVELLE_ENTITE");
  if (entites.length) {
    resultat.push(section("NOUVELLE_ENTITE", `Nouvelles entités (${entites.length})`,
      "Fournisseurs, valeurs de liste et ensembles cités par les fichiers mais absents de la base. Décocher une entité refuse aussi les lignes qui s'en servent.",
      tableEntites(entites)));
  }
  const modifies = par("MODIFIE");
  if (modifies.length) resultat.push(section("MODIFIE", `Composants modifiés (${modifies.length})`, "Seuls les champs qui changent sont listés. Décocher un champ le laisse tel quel.", modifies.map(carteModifie)));
  const doublons = par("DOUBLON");
  if (doublons.length) resultat.push(section("DOUBLON", `Doublons probables (${doublons.length})`, "Par défaut, un doublon sûr est fusionné : la quantité s'ajoute au composant existant au lieu d'en créer un second.", doublons.map(carteDoublon)));
  const nouveaux = par("NOUVEAU");
  if (nouveaux.length) resultat.push(section("NOUVEAU", `Nouveaux composants (${nouveaux.length})`, null, tableNouveaux(nouveaux)));
  const affectations = par("CREATION_AFFECTATION", "MODIF_AFFECTATION", "SUPPRESSION_AFFECTATION");
  if (affectations.length) resultat.push(section("AFFECTATION", `Affectations (${affectations.length})`, null, tableAffectations(affectations)));
  const rejets = par("INCONNU", "INVALIDE");
  if (rejets.length) resultat.push(section("INVALIDE", `Lignes non exploitables (${rejets.length})`, "Elles ne seront pas appliquées : corriger le fichier puis le redéposer.", tableRejets(rejets)));
  const identiques = par("IDENTIQUE");
  if (identiques.length) {
    resultat.push(el("details", { class: "panneau" }, el("summary", {}, `${identiques.length} composant(s) identique(s) à la base`),
      el("p", { class: "texte-petit texte-doux" }, identiques.map((l) => l.composant_id).join(", "))));
  }
  return resultat;
}

async function appliquer() {
  const aAppliquer = Object.values(etat.decisions).filter((d) => (d.champs?.length ?? 0) > 0 || ["creer", "fusionner", "appliquer"].includes(d.action)).length;
  if (!confirm(`Appliquer ${aAppliquer} proposition(s) ? Une sauvegarde de la base est prise juste avant.`)) return;
  try {
    const resultat = await api.appliquerImport(etat.numero, etat.decisions);
    masquerErreur();
    const bilan = [`${resultat.appliquees} proposition(s) appliquée(s)${resultat.crees.length ? `, dont ${resultat.crees.length} composant(s) créé(s) : ${resultat.crees.join(", ")}` : ""}.`];
    afficherAvertissements([...bilan, ...resultat.refus.map((r) => `Refusée : ${r}`)]);
    await charger();
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

async function abandonner() {
  if (!confirm("Abandonner ce dépôt ? Rien ne sera appliqué ; les propositions restent consultables.")) return;
  try {
    await api.abandonnerImport(etat.numero);
    masquerErreur();
    naviguer("/imports");
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

function rendre() {
  const depot = etat.depot;
  const fichiers = depot.lots.map((lot) => el("li", {}, lot.nom_fichier,
    lot.bloc_devine ? el("span", { class: "etiquette" }, `modèle du bloc ${lot.bloc_devine}`) : null,
    lot.ensemble_devine ? el("span", { class: "etiquette" }, `modèle de l'ensemble ${lot.ensemble_devine}`) : null));
  const statut = { analyse: "à relire", applique: "appliqué", abandonne: "abandonné" }[depot.statut];
  etat.conteneur.replaceChildren(
    el("p", { class: "fil" }, el("a", { href: "#/imports" }, "← Imports")),
    el("div", { class: "titre-page" }, el("h1", {}, `Dépôt n° ${depot.depot} `, el("span", { class: `statut-import statut-import--${depot.statut}` }, statut))),
    el("section", { class: "panneau" }, el("ul", { class: "liste-fichiers" }, fichiers), resumeCategories(depot.resume),
      etat.modifiable ? null : el("p", { class: "texte-doux" }, depot.statut === "applique" ? "Ce dépôt a été appliqué : les cases cochées sont les propositions qui ont été appliquées." : "Ce dépôt a été abandonné.")),
    ...sections(),
    etat.modifiable
      ? el("div", { class: "barre-application" },
          el("span", { class: "texte-doux" }, "Rien n'est modifié tant que la sélection n'est pas appliquée."),
          el("button", { type: "button", class: "bouton bouton--discret", onclick: abandonner }, "Abandonner le dépôt"),
          el("button", { type: "button", class: "bouton", onclick: appliquer }, "Appliquer la sélection"))
      : null,
  );
}

async function charger() {
  etat.depot = await api.getImport(etat.numero);
  etat.modifiable = etat.depot.statut === "analyse";
  etat.decisions = {};
  for (const ligne of etat.depot.lignes) {
    // Dépôt clos : seules les décisions réellement appliquées apparaissent cochées.
    const decision = etat.modifiable ? decisionParDefaut(ligne) : (ligne.decision ?? { champs: [], action: "ignorer" });
    if (decision) etat.decisions[ligne.id] = structuredClone(decision);
  }
  rendre();
}

export async function afficherRevueImport(conteneur, _parametres, numero) {
  etat = { conteneur, numero: Number(numero) };
  try {
    await chargerAttributs();
    await charger();
  } catch (erreur) {
    if (erreur.statut !== 404) throw erreur;
    conteneur.replaceChildren(el("p", { class: "fil" }, el("a", { href: "#/imports" }, "← Imports")), el("h1", {}, "Dépôt introuvable"));
  }
}

