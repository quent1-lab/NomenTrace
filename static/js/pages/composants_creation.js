// Panneau de création d'un composant. L'identifiant n'est pas saisissable : il est
// calculé par le serveur, affiché en aperçu et attribué définitivement à l'enregistrement.

import { api } from "../api.js";
import { champChoix, champNombre, champTexte, champZone, ligneChamp, lireFormulaire } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";
import { BASES_PRIX, CRITICITES, MODES_APPRO, STATUTS_APPRO, STATUTS_CHOIX } from "../valeurs.js";

const DESCRIPTION = {
  bloc_code: "choix",
  fonction: "texte",
  designation: "texte",
  mode_appro: "choix",
  qte_besoin: "entier",
  qte_rechange: "entier",
  qte_dispo_ecole: "entier",
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
  bloc_code: "Bloc fonctionnel",
  fonction: "Fonction",
  designation: "Désignation",
  mode_appro: "Mode d'approvisionnement",
  qte_besoin: "Qté besoin",
  qte_rechange: "Qté rechange",
  qte_dispo_ecole: "Qté dispo école",
  pu_releve: "PU relevé",
  taux_tva: "Taux de TVA",
};

const OBLIGATOIRES = ["bloc_code", "fonction", "designation", "mode_appro", "qte_besoin"];

export async function ouvrirCreation({ blocs, fournisseurs, blocInitial, surCree }) {
  const parametres = await api.getParametres();
  const tauxDefaut = Number(parametres.taux_tva_defaut ?? 0.2) * 100;
  const apercu = el("strong", { class: "code" }, "choisir un bloc");

  const bloc = champChoix("bloc_code", blocs.map((b) => [b.code, `${b.code} — ${b.nom}`]), blocInitial || null, { vide: "— choisir —", requis: true });
  const fournisseur = champChoix("fournisseur_nom", fournisseurs.map((f) => [f.nom, f.nom]), null, { vide: "—" });
  const base = champChoix("base_prix_releve", BASES_PRIX, "HT");

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
    el("p", { class: "apercu-id" }, "Identifiant attribué : ", apercu, el("span", { class: "texte-doux" }, " (aperçu, confirmé à l'enregistrement)")),
    el("fieldset", {}, el("legend", {}, "Identification"),
      ligneChamp("Bloc fonctionnel", bloc, { requis: true }),
      ligneChamp("Fonction", champTexte("fonction"), { requis: true }),
      ligneChamp("Désignation", champTexte("designation"), { requis: true }),
      ligneChamp("Réf fabricant", champTexte("ref_fabricant")),
      ligneChamp("Fabricant", champTexte("fabricant")),
    ),
    el("fieldset", {}, el("legend", {}, "Approvisionnement"),
      ligneChamp("Mode d'appro", champChoix("mode_appro", MODES_APPRO, "Achat", { requis: true }), { requis: true }),
      ligneChamp("Qté besoin", champNombre("qte_besoin", null), { requis: true }),
      ligneChamp("Qté rechange", champNombre("qte_rechange", 0)),
      ligneChamp("Qté dispo école", champNombre("qte_dispo_ecole", 0)),
      ligneChamp("Fournisseur", fournisseur),
      ligneChamp("Lien produit", champTexte("lien_produit", "", { type: "url" })),
      ligneChamp("PU relevé", champNombre("pu_releve", null, 2), { aide: "Laisser vide si le prix n'est pas encore connu." }),
      ligneChamp("Base du prix", base),
      ligneChamp("Taux de TVA (%)", champNombre("taux_tva", tauxDefaut, 1)),
    ),
    el("fieldset", {}, el("legend", {}, "Suivi"),
      ligneChamp("Statut choix", champChoix("statut_choix", STATUTS_CHOIX, "A sourcer", { vide: "—" })),
      ligneChamp("Statut appro", champChoix("statut_appro", STATUTS_APPRO, "Non lance")),
      ligneChamp("Criticité", champChoix("criticite", CRITICITES, null, { vide: "—" })),
      ligneChamp("Origine exigence", champTexte("origine_exigence")),
      ligneChamp("Note technique", champZone("note_technique")),
    ),
    el("div", { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, "Créer le composant"),
    ),
  );

  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lu = lireFormulaire(formulaire, DESCRIPTION, LIBELLES);
    if (lu.erreur) return afficherErreur(lu.erreur);
    const manquants = OBLIGATOIRES.filter((nom) => lu.valeurs[nom] === null).map((nom) => LIBELLES[nom]);
    if (manquants.length) return afficherErreur(`Champs obligatoires manquants : ${manquants.join(", ")}.`);
    const valeurs = Object.fromEntries(Object.entries(lu.valeurs).filter(([, v]) => v !== null));
    const bouton = formulaire.querySelector("button[type=submit]");
    bouton.disabled = true;
    try {
      const cree = await api.createComposant(valeurs);
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surCree(cree);
    } catch (erreur) {
      bouton.disabled = false;
      afficherErreur(erreur);
    }
  });

  ouvrirPanneau("Nouveau composant", formulaire);
  if (bloc.value) majApercu();
  formulaire.elements.namedItem(bloc.value ? "fonction" : "bloc_code").focus();
}
