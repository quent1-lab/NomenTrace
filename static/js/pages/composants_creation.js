// Panneau de création d'un composant. L'identifiant n'est pas saisissable : il est
// calculé par le serveur, affiché en aperçu et attribué définitivement à l'enregistrement.
// Depuis l'écran Composants, la création se fait en deux étapes : l'étape 1 crée le composant
// et lui attribue son identifiant ; l'étape 2, facultative, propose les caractéristiques, les
// ensembles et les documents, pour que rien ne soit oublié.
// Une duplication ouvre le même panneau, prérempli avec les champs et les caractéristiques
// d'un composant existant ; ses affectations, documents, quantité déjà disponible et statut
// d'appro ne sont pas repris.

import { api } from "../api.js";
import { champAttribut, chargerAttributs } from "../attributs.js";
import { sectionDocuments } from "../documents.js";
import { formatNombre, lireNombre } from "../format.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { champFournisseur } from "./fournisseurs_commun.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { ecritBloc } from "../session.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { BASES_PRIX, valeursListe } from "../valeurs.js";

const DESCRIPTION = {
  bloc_code: "choix",
  fonction: "texte",
  designation: "texte",
  mode_appro: "choix",
  qte_besoin: "entier",
  qte_rechange: "entier",
  qte_disponible: "entier",
  ref_fabricant: "texte",
  fabricant: "texte",
  fournisseur_nom: "choix",
  lien_produit: "texte",
  pu_releve: "montant",
  base_prix_releve: "choix",
  taux_tva: "taux",
  statut_choix: "choix",
  statut_appro: "choix",
  criticite: "choix",
  origine_exigence: "texte",
  note_technique: "texte",
};

const LIBELLES = {
  bloc_code: "Bloc",
  fonction: "Fonction",
  designation: "Désignation",
  mode_appro: "Mode d'approvisionnement",
  qte_besoin: "Qté besoin",
  qte_rechange: "Qté rechange",
  qte_disponible: "Qté déjà disponible",
  pu_releve: "PU relevé",
  taux_tva: "Taux de TVA",
};

const OBLIGATOIRES = ["bloc_code", "fonction", "designation", "mode_appro", "qte_besoin"];

// Indicateur des deux étapes de la création.
function etapes(courante) {
  const etape = (numero, texte) =>
    el(
      "li",
      { class: `etapes__etape ${numero < courante ? "etapes__etape--faite" : numero === courante ? "etapes__etape--courante" : ""}` },
      el("span", { class: "etapes__numero" }, numero < courante ? "✓" : String(numero)),
      texte,
    );
  return el("ol", { class: "etapes", "aria-label": `Étape ${courante} sur 2` }, etape(1, "Identification et achat"), el("li", { class: "etapes__trait", "aria-hidden": "true" }), etape(2, "Compléments"));
}

// Étape 2 : caractéristiques (toutes proposées), affectations et documents du composant créé.
// Affectations et documents s'enregistrent aussitôt ; les caractéristiques à « Terminer ».
async function ouvrirComplements(cree, valeursSaisies, { ensembles, surCree, surFermeture }) {
  const definitions = await chargerAttributs();
  const champs = definitions.filter((a) => a.actif).map((a) => ({ a, ...champAttribut(a, valeursSaisies[a.code] ?? null) }));
  const zoneEnsembles = el("div");
  const zoneDocuments = el("div");

  const rendreEnsembles = async () => {
    const fiche = await api.getComposant(cree.id);
    const c = fiche.composant;
    const dejaAffectes = new Set(fiche.affectations.map((a) => a.ensemble_code));
    const choix = champChoix("ensemble", ensembles.filter((e) => !dejaAffectes.has(e.code)).map((e) => [e.code, `${e.code} · ${e.nom}`]), null, { vide: "Ensemble…" });
    const qte = champNombre("qte", Math.max(1, c.ecart_affectation), 0, { "aria-label": "Quantité" });
    const affecter = el("form", { class: "formulaire-ligne" }, choix, qte, el("button", { type: "submit", class: "bouton bouton--discret" }, "Affecter"));
    affecter.addEventListener("submit", async (e) => {
      e.preventDefault();
      const quantite = lireNombre(qte.value);
      if (!choix.value) return afficherErreur("Choisir un ensemble.");
      if (!Number.isInteger(quantite) || quantite <= 0) return afficherErreur("La quantité doit être un entier supérieur à zéro.");
      try {
        await api.createAffectation(choix.value, { composant_id: cree.id, qte: quantite });
        masquerErreur();
        await rendreEnsembles();
      } catch (erreur) {
        afficherErreur(erreur);
      }
    });
    zoneEnsembles.replaceChildren(
      el(
        "div",
        { class: "fiche-caracteristiques__liste" },
        fiche.affectations.map((a) =>
          el(
            "span",
            { class: "puce-fiche puce-fiche--info" },
            `${a.ensemble_code} · ${formatNombre(a.qte_affectee)}`,
            el("button", {
              type: "button",
              class: "bouton-icone",
              "aria-label": `Retirer de ${a.ensemble_code}`,
              onclick: async () => {
                try {
                  await api.deleteAffectation(a.affectation_id);
                  await rendreEnsembles();
                } catch (erreur) {
                  afficherErreur(erreur);
                }
              },
            }, "×"),
          ),
        ),
      ),
      ensembles.length ? affecter : el("p", { class: "texte-doux texte-petit" }, "Aucun ensemble n'existe encore."),
      el("p", { class: "texte-doux texte-petit" }, `Besoin ${c.qte_besoin}, affecté ${c.qte_affectee}`),
    );
  };

  const rendreDocuments = async () => {
    const documents = await api.getDocumentsComposant(cree.id);
    zoneDocuments.replaceChildren(
      sectionDocuments({
        titre: "",
        documents,
        typeParDefaut: "Fiche technique",
        deposer: (donnees, progression) => api.deposerDocumentsComposant(cree.id, donnees, progression),
        surChangement: rendreDocuments,
      }),
    );
  };

  const terminer = el("button", { type: "button", class: "bouton" }, "Terminer et ouvrir la fiche");
  terminer.addEventListener("click", async () => {
    const attributs = {};
    for (const { a, lire } of champs) {
      const lu = lire();
      if (lu.erreur) return afficherErreur(lu.erreur);
      if (lu.valeur !== (valeursSaisies[a.code] ?? null)) attributs[a.code] = lu.valeur;
    }
    terminer.disabled = true;
    try {
      if (Object.keys(attributs).length) await api.patchComposant(cree.id, { attributs });
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surCree(cree);
    } catch (erreur) {
      terminer.disabled = false;
      afficherErreur(erreur);
    }
  });
  const passer = el("button", {
    type: "button",
    class: "bouton bouton--discret",
    onclick: async () => {
      fermerPanneau({ silencieux: true });
      await surCree(cree);
    },
  }, "Passer, compléter plus tard");

  ouvrirPanneau(
    "Nouveau composant",
    el(
      "div",
      { class: "formulaire" },
      etapes(2),
      el("p", { class: "message message-ok" }, `${cree.id} est créé. Ces informations sont facultatives et restent modifiables depuis la fiche.`),
      champs.length
        ? el("fieldset", {}, el("legend", {}, "Caractéristiques"),
            champs.map(({ a, element }) => ligneChamp(a.unite ? `${a.libelle} (${a.unite})` : a.libelle, element, { requis: Boolean(a.obligatoire) })),
            el("p", { class: "texte-doux texte-petit" }, "Celles laissées vides n'apparaîtront pas sur la fiche."))
        : null,
      el("fieldset", {}, el("legend", {}, "Ensembles où il sera monté"), zoneEnsembles),
      el("fieldset", {}, el("legend", {}, "Documents"), zoneDocuments),
      el("div", { class: "actions-formulaire actions-formulaire--espace" }, passer, terminer),
    ),
    surFermeture,
  );
  await Promise.all([rendreEnsembles(), rendreDocuments()]);
}

// completer : passe à l'étape 2 après la création (écran Composants) ; sinon le panneau se
// ferme dès le composant créé (création depuis un ensemble, par exemple).
export async function ouvrirCreation({ blocs, fournisseurs, blocInitial, surCree, note = "", modele = null, completer = null }) {
  const [parametres, definitions] = await Promise.all([api.getParametres(), chargerAttributs()]);
  // Champs rendus obligatoires dans les paramètres : marqués ici, contrôlés par le serveur.
  const requis = new Set((parametres.champs_obligatoires ?? "").split(",").filter(Boolean));
  const m = modele?.composant ?? {};
  const valeursModele = modele?.attributs ?? {};
  // Caractéristiques proposées : les obligatoires, plus celles que porte le composant dupliqué.
  const caracteristiques = definitions
    .filter((a) => a.actif && (a.obligatoire || valeursModele[a.code] !== undefined))
    .map((a) => ({ a, ...champAttribut(a, valeursModele[a.code] ?? null) }));
  const tauxDefaut = m.taux_tva !== undefined ? m.taux_tva * 100 : Number(parametres.taux_tva_defaut ?? 0.2) * 100;
  const apercu = el("strong", { class: "code" }, "choisir un bloc");

  // Un contributeur ne crée que dans ses blocs ; l'administrateur, dans tous.
  const permis = blocs.filter((b) => ecritBloc(b.code));
  const initial = permis.some((b) => b.code === blocInitial) ? blocInitial : null;
  const bloc = champChoix("bloc_code", permis.map((b) => [b.code, `${b.code} · ${b.nom}`]), initial, { vide: "Choisir…", requis: true });
  const choixFournisseur = champFournisseur(fournisseurs, m.fournisseur_nom ?? null);
  const fournisseur = choixFournisseur.select;
  const base = champChoix("base_prix_releve", BASES_PRIX, m.base_prix_releve ?? "HT");

  const majApercu = async () => {
    if (!bloc.value) {
      apercu.textContent = "choisir un bloc";
      return;
    }
    try {
      apercu.textContent = (await api.getProchainId(bloc.value)).id;
    } catch (erreur) {
      apercu.textContent = "—";
      afficherErreur(erreur);
    }
  };
  bloc.addEventListener("change", majApercu);
  // La base de prix par défaut suit le fournisseur (sites grand public en TTC).
  fournisseur.addEventListener("change", () => {
    const choisi = fournisseurs.find((f) => f.nom === fournisseur.value);
    if (choisi?.base_prix_defaut) base.value = choisi.base_prix_defaut;
  });

  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    completer ? etapes(1) : null,
    note ? el("p", { class: "note-formulaire" }, note) : null,
    modele ? el("p", { class: "note-formulaire" }, `Copie de ${m.id} : modifier ce qui diffère, puis créer.`) : null,
    el("p", { class: "apercu-id" }, "Identifiant attribué : ", apercu, el("span", { class: "texte-doux" }, " (aperçu, confirmé à l'enregistrement)")),
    el("fieldset", {}, el("legend", {}, "Identification"),
      ligneChamp("Bloc", bloc, { requis: true }),
      ligneChamp("Fonction", champTexte("fonction", m.fonction), { requis: true }),
      ligneChamp("Désignation", champTexte("designation", m.designation), { requis: true }),
      ligneChamp("Réf fabricant", champTexte("ref_fabricant", m.ref_fabricant), { requis: requis.has("ref_fabricant") }),
      ligneChamp("Fabricant", champTexte("fabricant", m.fabricant), { requis: requis.has("fabricant") }),
    ),
    el("fieldset", {}, el("legend", {}, "Approvisionnement"),
      ligneChamp("Mode d'appro", champChoix("mode_appro", valeursListe("mode_appro"), m.mode_appro ?? "Achat", { requis: true }), { requis: true }),
      ligneChamp("Qté besoin", champNombre("qte_besoin", m.qte_besoin ?? null), { requis: true }),
      ligneChamp("Qté rechange", champNombre("qte_rechange", m.qte_rechange ?? 0)),
      ligneChamp("Qté déjà disponible", champNombre("qte_disponible", 0), { aide: "Déjà en stock ou prêtée : réduit la quantité à acheter." }),
      ligneChamp("Fournisseur", choixFournisseur.element, { requis: requis.has("fournisseur_nom") }),
      ligneChamp("Lien produit", champTexte("lien_produit", m.lien_produit ?? "", { type: "url" }), { requis: requis.has("lien_produit") }),
      ligneChamp("PU relevé", champNombre("pu_releve", m.pu_releve ?? null, 2), { requis: requis.has("pu_releve") }),
      ligneChamp("Base du prix", base),
      ligneChamp("Taux de TVA (%)", champNombre("taux_tva", tauxDefaut, 1)),
    ),
    caracteristiques.length
      ? el("fieldset", {}, el("legend", {}, "Caractéristiques"), caracteristiques.map(({ a, element }) => ligneChamp(a.unite ? `${a.libelle} (${a.unite})` : a.libelle, element, { requis: Boolean(a.obligatoire) })))
      : null,
    el("fieldset", {}, el("legend", {}, "Suivi"),
      ligneChamp("Statut choix", champChoix("statut_choix", valeursListe("statut_choix"), m.statut_choix ?? null, { vide: "—" })),
      ligneChamp("Statut appro", champChoix("statut_appro", valeursListe("statut_appro"), "Non lance")),
      ligneChamp("Criticité", champChoix("criticite", valeursListe("criticite"), m.criticite ?? null, { vide: "—" })),
      ligneChamp("Origine exigence", champTexte("origine_exigence", m.origine_exigence)),
      ligneChamp("Note technique", champZone("note_technique", m.note_technique)),
    ),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, completer ? "Créer et continuer" : "Créer le composant"),
    ),
  );

  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, LIBELLES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    const manquants = OBLIGATOIRES.filter((nom) => lu.valeurs[nom] === null).map((nom) => LIBELLES[nom]);
    if (manquants.length) return afficherErreur(`Champs obligatoires manquants : ${manquants.join(", ")}.`);
    const valeurs = Object.fromEntries(Object.entries(lu.valeurs).filter(([, v]) => v !== null));
    const attributs = {};
    for (const { a, lire } of caracteristiques) {
      const valeur = lire();
      if (valeur.erreur) return afficherErreur(valeur.erreur);
      if (valeur.valeur !== null) attributs[a.code] = valeur.valeur;
    }
    if (Object.keys(attributs).length) valeurs.attributs = attributs;
    const bouton = formulaire.querySelector("button[type=submit]");
    bouton.disabled = true;
    try {
      const nomFournisseur = await choixFournisseur.resoudre();
      if (nomFournisseur) valeurs.fournisseur_nom = nomFournisseur;
      const cree = await api.createComposant(valeurs);
      masquerErreur();
      if (completer) return await ouvrirComplements(cree, attributs, { ...completer, surCree });
      fermerPanneau({ silencieux: true });
      await surCree(cree);
    } catch (erreur) {
      bouton.disabled = false;
      afficherErreur(erreur);
    }
  });

  ouvrirPanneau(modele ? `Dupliquer ${m.id}` : "Nouveau composant", formulaire);
  if (bloc.value) majApercu();
  formulaire.elements.namedItem(bloc.value ? "fonction" : "bloc_code").focus();
}
