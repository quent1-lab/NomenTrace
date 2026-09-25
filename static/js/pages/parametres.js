// Écran paramètres (#/parametres?onglet=…) : projet, blocs, ensembles, fournisseurs, listes de
// valeurs, export et sauvegardes.

import { api } from "../api.js";
import { formatDate, formatNombre } from "../format.js";
import { champNombre, champTexte, lireFormulaire, ligneChamp } from "../formulaire.js";
import { lienRoute, remplacerRoute } from "../router.js";
import { afficherErreur, el, enregistrerFichier, masquerErreur } from "../ui.js";
import { afficherOngletBlocs, afficherOngletEnsembles, afficherOngletFournisseurs } from "./parametres_entites.js";
import { afficherOngletAttributs } from "./parametres_attributs.js";
import { afficherListes } from "./parametres_listes.js";

const ONGLETS = [
  ["projet", "Projet", afficherOngletProjet],
  ["blocs", "Blocs fonctionnels", afficherOngletBlocs],
  ["ensembles", "Ensembles", afficherOngletEnsembles],
  ["fournisseurs", "Fournisseurs", afficherOngletFournisseurs],
  ["listes", "Listes de valeurs", afficherListes],
  ["attributs", "Attributs", afficherOngletAttributs],
  ["sauvegardes", "Export et sauvegardes", afficherOngletSauvegardes],
];

// L'en-tête (nom du projet) se relit aussitôt après une modification du projet.
function signalerProjetModifie() {
  window.dispatchEvent(new Event("nomentrace:projet"));
}

function message(texte, classe = "message-info") {
  return el("p", { class: `message ${classe}` }, texte);
}

// --- Projet -----------------------------------------------------------------------------------

const DESCRIPTION_PROJET = { nom_projet: "texte", prefixe_id: "texte", budget_ht: "montant", taux_tva_defaut: "taux" };
const LIBELLES_PROJET = { budget_ht: "Budget HT", taux_tva_defaut: "TVA par défaut" };

async function afficherOngletProjet(cible) {
  const parametres = await api.getParametres();
  const nombre = (texte) => (texte === null || texte === undefined ? null : Number(texte));
  const tva = nombre(parametres.taux_tva_defaut);
  const prefixe = champTexte("prefixe_id", parametres.prefixe_id ?? "", { maxlength: "10", autocomplete: "off" });
  prefixe.addEventListener("input", () => {
    prefixe.value = prefixe.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  });
  const retour = el("div");
  const formulaire = el(
    "form",
    { class: "formulaire formulaire--page", novalidate: true },
    ligneChamp("Nom du projet", champTexte("nom_projet", parametres.nom_projet ?? ""), { requis: true, aide: "Affiché sous « Nomentrace » dans l'en-tête." }),
    ligneChamp("Préfixe des identifiants", prefixe, {
      requis: true,
      aide:
        "Lettres majuscules et chiffres. Il ne s'applique qu'aux composants créés ensuite : " +
        "les identifiants existants ne sont jamais renommés, car tout l'historique y est rattaché.",
    }),
    ligneChamp("Budget HT", champNombre("budget_ht", nombre(parametres.budget_ht), 2), { aide: "Budget global du projet, en euros hors taxes." }),
    ligneChamp("TVA par défaut (%)", champNombre("taux_tva_defaut", tva === null ? null : tva * 100, 1), {
      aide: "Sert à convertir en HT un prix relevé TTC quand le composant n'a pas de taux propre.",
    }),
    el("div", { class: "actions-formulaire" }, el("button", { type: "submit", class: "bouton" }, "Enregistrer")),
    retour,
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION_PROJET, LIBELLES_PROJET);
    if (lu.erreur) return afficherErreur(lu.erreur);
    if (!lu.valeurs.nom_projet) return afficherErreur("Le nom du projet est obligatoire.");
    if (!lu.valeurs.prefixe_id) return afficherErreur("Le préfixe des identifiants est obligatoire.");
    const modifs = {};
    for (const [cle, valeur] of Object.entries(lu.valeurs)) {
      const actuelle = cle === "nom_projet" || cle === "prefixe_id" ? parametres[cle] : nombre(parametres[cle]);
      const identique = typeof valeur === "number" && actuelle !== null ? Math.abs(valeur - actuelle) < 1e-9 : valeur === actuelle;
      if (!identique) modifs[cle] = valeur;
    }
    if (!Object.keys(modifs).length) return retour.replaceChildren(message("Rien à enregistrer : aucune valeur n'a changé."));
    if (
      modifs.prefixe_id &&
      parametres.prefixe_id &&
      !confirm(
        `Changer le préfixe « ${parametres.prefixe_id} » en « ${modifs.prefixe_id} » ?\n\n` +
          `Les prochains composants s'appelleront ${modifs.prefixe_id}-BLOC-001, etc. ` +
          `Les identifiants existants gardent l'ancien préfixe : ils ne sont pas renommés.`,
      )
    ) {
      return;
    }
    try {
      await api.patchParametres(modifs);
      masquerErreur();
      signalerProjetModifie();
      await afficherOngletProjet(cible);
      cible.querySelector("form").append(message("Paramètres enregistrés.", "message-ok"));
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  cible.replaceChildren(formulaire);
}

// --- Export et sauvegardes --------------------------------------------------------------------

function formatTaille(octets) {
  if (octets < 1024 * 1024) return `${formatNombre(octets / 1024, 0)} Ko`;
  return `${formatNombre(octets / (1024 * 1024), 1)} Mo`;
}

function formatHorodatage(iso) {
  return `${formatDate(iso.slice(0, 10))} ${iso.slice(11, 16)}`;
}

async function restaurer(sauvegarde, rafraichir) {
  const quand = formatHorodatage(sauvegarde.date);
  if (!confirm(`Restaurer la sauvegarde du ${quand} ?\n\nToutes les modifications faites depuis seront remplacées.`)) return;
  if (
    !confirm(
      "Confirmer la restauration.\n\nL'état actuel est d'abord sauvegardé : " +
        "on pourra y revenir en restaurant cette nouvelle sauvegarde, en tête de liste.",
    )
  ) {
    return;
  }
  try {
    const resultat = await api.restaurerSauvegarde(sauvegarde.nom);
    masquerErreur();
    const migrations =
      resultat.version_sauvegarde < resultat.version_schema
        ? ` La sauvegarde datait du schéma ${resultat.version_sauvegarde} : elle a été mise à niveau (schéma ${resultat.version_schema}).`
        : "";
    alert(`Base restaurée depuis la sauvegarde du ${quand}.${migrations}\n\nL'état précédent est conservé dans ${resultat.securite}. La page va se recharger.`);
    window.location.reload();
  } catch (erreur) {
    afficherErreur(erreur);
    await rafraichir();
  }
}

// Bouton qui fait construire un fichier par le serveur puis le propose au téléchargement.
function boutonTelechargement(texte, telecharger, { enCours, principal = false } = {}) {
  const bouton = el("button", { type: "button", class: principal ? "bouton" : "bouton bouton--discret" }, texte);
  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    bouton.textContent = enCours ?? texte;
    try {
      enregistrerFichier(await telecharger());
      masquerErreur();
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      bouton.disabled = false;
      bouton.textContent = texte;
    }
  });
  return bouton;
}

function sectionArchive() {
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Archive complète"),
    el(
      "p",
      { class: "texte-doux" },
      "Un fichier .zip qui contient une copie cohérente de la base (nomentrace.db) et tous les documents joints " +
        "(dossier documents). C'est la sauvegarde à conserver hors de la machine ; le README explique comment " +
        "restaurer à partir de cette archive.",
    ),
    el(
      "div",
      { class: "actions" },
      boutonTelechargement("Télécharger une archive complète", api.telechargerArchive, { enCours: "Préparation de l'archive…", principal: true }),
    ),
  );
}

function sectionExport(retour) {
  const bouton = el("button", { type: "button", class: "bouton" }, "Exporter maintenant");
  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    try {
      const resultat = await api.exporter();
      masquerErreur();
      retour.replaceChildren(
        resultat.statut === "ok"
          ? message("Export écrit : echange/exports/nomenclature.xlsx.", "message-ok")
          : message("Le fichier d'export est ouvert dans Excel : il sera réécrit dès sa fermeture.", "message-attention"),
      );
    } catch (erreur) {
      afficherErreur(erreur);
    } finally {
      bouton.disabled = false;
    }
  });
  return el(
    "section",
    { class: "panneau" },
    el("h2", {}, "Export Excel"),
    el(
      "p",
      { class: "texte-doux" },
      "Le classeur d'export est réécrit automatiquement quelques secondes après chaque modification. " +
        "C'est une copie de lecture : les changements faits dedans ne reviennent pas dans l'outil.",
    ),
    el(
      "div",
      { class: "actions" },
      bouton,
      boutonTelechargement("Télécharger l'Excel global", api.telechargerExcelGlobal, { enCours: "Préparation du classeur…" }),
    ),
    retour,
  );
}

async function afficherOngletSauvegardes(cible) {
  const rafraichir = () => afficherOngletSauvegardes(cible);
  const sauvegardes = await api.getSauvegardes();
  const retourExport = el("div");
  const retourSauvegarde = el("div");
  const sauvegarder = el("button", { type: "button", class: "bouton" }, "Sauvegarder maintenant");
  sauvegarder.addEventListener("click", async () => {
    sauvegarder.disabled = true;
    try {
      const { nom } = await api.createSauvegarde();
      masquerErreur();
      await rafraichir();
      cible.querySelector(".retour-sauvegarde").replaceChildren(message(`Sauvegarde créée : ${nom}.`, "message-ok"));
    } catch (erreur) {
      afficherErreur(erreur);
      sauvegarder.disabled = false;
    }
  });
  retourSauvegarde.className = "retour-sauvegarde";
  const lignes = sauvegardes.map((s, rang) =>
    el(
      "tr",
      {},
      el("td", {}, formatHorodatage(s.date), rang === 0 ? el("span", { class: "etiquette etiquette--espace" }, "la plus récente") : null),
      el("td", { class: "texte-doux" }, s.nom),
      el("td", { class: "nombre" }, formatTaille(s.taille)),
      el("td", { class: "nombre" }, el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => restaurer(s, rafraichir) }, "Restaurer")),
    ),
  );
  cible.replaceChildren(
    sectionExport(retourExport),
    sectionArchive(),
    el(
      "section",
      { class: "panneau" },
      el("div", { class: "titre-section" }, el("h2", {}, "Sauvegardes de la base"), sauvegarder),
      el(
        "p",
        { class: "texte-doux" },
        "Une sauvegarde est prise à chaque démarrage et avant chaque restauration ; les 20 plus récentes sont gardées " +
          "dans echange/sauvegardes. Elles ne contiennent que la base : pour y joindre les documents, télécharger une archive complète.",
      ),
      retourSauvegarde,
      lignes.length
        ? el(
            "table",
            { class: "table table--dense table--parametres" },
            el("thead", {}, el("tr", {}, el("th", {}, "Date"), el("th", {}, "Fichier"), el("th", { class: "nombre" }, "Taille"), el("th", {}))),
            el("tbody", {}, lignes),
          )
        : el("p", { class: "texte-doux" }, "Aucune sauvegarde pour l'instant."),
    ),
  );
}

// --- Onglets ----------------------------------------------------------------------------------

export async function afficherParametres(conteneur, parametres) {
  const demande = parametres?.get("onglet");
  const courant = ONGLETS.some(([code]) => code === demande) ? demande : "projet";
  const corps = el("div", { class: "onglet-parametres" });
  const barre = el(
    "nav",
    { class: "onglets", role: "tablist" },
    ONGLETS.map(([code, titre]) =>
      el(
        "button",
        {
          type: "button",
          role: "tab",
          class: code === courant ? "onglet onglet--actif" : "onglet",
          "aria-selected": code === courant ? "true" : "false",
          onclick: () => {
            remplacerRoute("/parametres", { onglet: code === "projet" ? "" : code });
            afficherParametres(conteneur, new URLSearchParams({ onglet: code }));
          },
        },
        titre,
      ),
    ),
  );
  const titre = el(
    "div",
    { class: "titre-page" },
    el("h1", {}, "Paramètres"),
    el("a", { class: "bouton bouton--discret", href: lienRoute("/nettoyage"), title: "Composants mal remplis, suppressions, journal" }, "Nettoyage de la base"),
  );
  conteneur.replaceChildren(titre, barre, corps);
  const [, , afficher] = ONGLETS.find(([code]) => code === courant);
  try {
    await afficher(corps, parametres);
  } catch (erreur) {
    corps.replaceChildren(el("p", { class: "texte-doux" }, "Chargement impossible."));
    afficherErreur(erreur);
  }
}
