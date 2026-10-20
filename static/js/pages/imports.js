// Écran imports (#/imports) : modèles à remplir, dépôt des fichiers de l'équipe, historique.

import { api, lienModele } from "../api.js";
import { formatDate } from "../format.js";
import { lienRoute, naviguer } from "../router.js";
import { modeLocal, peutEcrire } from "../session.js";
import { afficherErreur, afficherInformation, el, masquerErreur, suiviEnvoi } from "../ui.js";

export const LIBELLES_CATEGORIES = {
  NOUVELLE_ENTITE: "entité(s) à créer",
  MODIFIE: "modifié(s)",
  DOUBLON: "doublon(s)",
  NOUVEAU: "nouveau(x)",
  CREATION_AFFECTATION: "affectation(s) à créer",
  MODIF_AFFECTATION: "affectation(s) modifiée(s)",
  SUPPRESSION_AFFECTATION: "affectation(s) à retirer",
  INCONNU: "inconnu(s)",
  INVALIDE: "invalide(s)",
  IDENTIQUE: "identique(s)",
};

const STATUTS = { analyse: "à relire", applique: "appliqué", abandonne: "abandonné" };

export function resumeCategories(resume) {
  return el(
    "span",
    { class: "resume-import" },
    Object.entries(resume).map(([categorie, nb]) => el("span", { class: `puce-import puce-import--${categorie.toLowerCase()}` }, `${nb} ${LIBELLES_CATEGORIES[categorie] ?? categorie}`)),
  );
}

function sectionModeles(blocs, ensembles) {
  const choixBloc = el("select", { class: "filtre", "aria-label": "Bloc du modèle" }, blocs.map((b) => el("option", { value: b.code }, `${b.code} · ${b.nom}`)));
  const lienBloc = el("a", { class: "bouton bouton--discret", href: lienModele("bloc", blocs[0]?.code ?? ""), download: "" }, "Télécharger le modèle du bloc");
  choixBloc.addEventListener("change", () => (lienBloc.href = lienModele("bloc", choixBloc.value)));
  const ligneEnsemble = ensembles.length
    ? (() => {
        const choix = el("select", { class: "filtre", "aria-label": "Ensemble du modèle" }, ensembles.map((e) => el("option", { value: e.code }, `${e.code} · ${e.nom}`)));
        const lien = el("a", { class: "bouton bouton--discret", href: lienModele("ensemble", ensembles[0].code), download: "" }, "Télécharger le modèle de l'ensemble");
        choix.addEventListener("change", () => (lien.href = lienModele("ensemble", choix.value)));
        return el("div", { class: "formulaire-ligne" }, choix, lien);
      })()
    : el("p", { class: "texte-doux texte-petit" }, "Aucun ensemble : le modèle d'ensemble apparaîtra dès qu'un ensemble sera créé.");
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Modèles à remplir"),
    el("p", { class: "texte-doux texte-petit" }, "Un modèle reprend les composants existants, plus des lignes vides pour les ajouts. " +
      "Celui d'un ensemble ajoute la colonne « Qté dans cet ensemble », pour la personne qui monte cette partie."),
    el("div", { class: "formulaire-ligne" }, choixBloc, lienBloc),
    ligneEnsemble,
  );
}

// Partir de l'Excel d'une équipe : l'outil d'IA de son choix recopie le fichier dans le
// modèle vierge, guidé par une consigne qui reprend le vocabulaire du projet.
function sectionGuideIA(blocs) {
  const zoneConsigne = el("div");
  const copier = el("button", { type: "button", class: "bouton" }, "Copier la consigne");
  copier.addEventListener("click", async () => {
    let consigne;
    try {
      ({ consigne } = await api.getConsigneIA());
    } catch (erreur) {
      return afficherErreur(erreur);
    }
    const zone = el("textarea", { class: "champ champ--zone consigne-ia", readonly: true, rows: "12", "aria-label": "Consigne pour l'outil d'IA" });
    zone.value = consigne;
    try {
      await navigator.clipboard.writeText(consigne);
      zoneConsigne.replaceChildren(el("p", { class: "message message-ok" }, "Consigne copiée. La voici aussi, pour la relire :"), zone);
    } catch {
      // Presse-papiers refusé par le navigateur : la consigne reste à sélectionner à la main.
      zoneConsigne.replaceChildren(el("p", { class: "texte-doux texte-petit" }, "Sélectionner la consigne ci-dessous et la copier :"), zone);
      zone.select();
    }
  });
  const etapeBlocs = blocs.length
    ? el("li", {}, `Les blocs du projet existent (${blocs.length}) : l'IA rangera chaque composant dans l'un d'eux.`)
    : el("li", { class: "texte-surveiller" }, "Créer d'abord les blocs dans ", el("a", { href: lienRoute("/parametres", { onglet: "blocs" }) }, "Paramètres › Blocs"), " : l'import refuse un composant sans bloc.");
  return el(
    "section",
    { class: "panneau guide-ia" },
    el("h2", {}, "Partir de votre propre Excel, avec une IA"),
    el(
      "ol",
      { class: "guide-ia__etapes" },
      etapeBlocs,
      el("li", {}, el("a", { class: "bouton bouton--discret", href: lienModele("vierge"), download: "" }, "Télécharger le modèle vierge"), " tous blocs, avec les listes du projet."),
      el("li", {}, "Ouvrir l'outil d'IA conversationnel de votre choix, lui joindre votre Excel et le modèle vierge, puis coller la consigne. ", copier),
      el("li", {}, "Déposer le classeur qu'il rend dans « Déposer des fichiers de l'équipe » : rien n'est écrit avant que vous ayez relu et accepté les propositions."),
    ),
    el("p", { class: "texte-doux texte-petit" }, "La consigne reprend les blocs, les listes, les fournisseurs et les caractéristiques actuels du projet : copiez-la à nouveau s'ils ont changé. Vérifiez la liste des lignes que l'IA dit avoir ignorées ou regroupées."),
    zoneConsigne,
  );
}

function sectionDepot() {
  const fichiers = el("input", { type: "file", multiple: true, accept: ".xlsx,.xlsm", class: "champ-fichier", "aria-label": "Fichiers à analyser" });
  // En mode connecté, le serveur sait qui dépose : la case ne sert qu'en mode local.
  const auteur = modeLocal() ? el("input", { class: "champ", type: "text", placeholder: "Déposé par (facultatif)" }) : null;
  const formulaire = el("form", { class: "formulaire-ligne formulaire-depot" }, fichiers, auteur, el("button", { type: "submit", class: "bouton" }, "Analyser"));
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fichiers.files.length) return afficherErreur("Choisir au moins un fichier Excel à analyser.");
    const donnees = new FormData();
    for (const fichier of fichiers.files) donnees.append("fichiers", fichier);
    if (auteur?.value.trim()) donnees.append("depose_par", auteur.value.trim());
    const bouton = formulaire.querySelector("button");
    const suivi = suiviEnvoi(fichiers.files.length, "Analyse");
    formulaire.append(suivi.element);
    bouton.disabled = true;
    try {
      const { depot } = await api.deposerImport(donnees, suivi.maj);
      masquerErreur();
      // Écran quitté pendant l'analyse : on n'y ramène pas de force, le bandeau prévient.
      if (formulaire.isConnected) naviguer(`/imports/${depot}`);
      else afficherInformation(`Analyse terminée : le dépôt ${depot} est à relire dans Imports.`);
    } catch (erreur) {
      suivi.element.remove();
      bouton.disabled = false;
      afficherErreur(erreur);
    }
  });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Déposer des fichiers de l'équipe"),
    el("p", { class: "texte-doux texte-petit" }, "L'analyse ne modifie rien : elle produit des propositions à relire, puis à appliquer."),
    formulaire,
  );
}

function sectionHistorique(depots) {
  if (!depots.length) return el("section", { class: "panneau" }, el("h2", {}, "Dépôts"), el("p", { class: "texte-doux" }, "Aucun fichier déposé pour l'instant."));
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Dépôts"),
    el(
      "table",
      { class: "table table--dense" },
      el("thead", {}, el("tr", {}, ["N°", "Date", "Fichiers", "Déposé par", "Statut", "Résumé"].map((t) => el("th", {}, t)))),
      el(
        "tbody",
        {},
        depots.map((d) =>
          el(
            "tr",
            { class: "ligne-cliquable", onclick: () => naviguer(`/imports/${d.depot}`) },
            el("td", { class: "code" }, String(d.depot)),
            el("td", {}, `${formatDate(d.horodatage)} ${d.horodatage.slice(11, 16)}`),
            el("td", { class: "tronque tronque--large", title: d.fichiers.join(", ") }, d.fichiers.join(", ")),
            el("td", {}, d.depose_par ?? ""),
            el("td", {}, el("span", { class: `statut-import statut-import--${d.statut}` }, STATUTS[d.statut])),
            el("td", {}, resumeCategories(d.resume)),
          ),
        ),
      ),
    ),
  );
}

export async function afficherImports(conteneur) {
  const [blocs, ensembles, depots] = await Promise.all([api.getBlocs(), api.getEnsembles(), api.getImports()]);
  conteneur.replaceChildren(
    el("h1", {}, "Imports"),
    sectionGuideIA(blocs),
    el("div", { class: "grille-2" }, sectionModeles(blocs, ensembles), peutEcrire() ? sectionDepot() : null),
    sectionHistorique(depots),
  );
}
