// Onglet Paramètres › Utilisateurs, réservé à l'administrateur : comptes, rôles, blocs,
// permissions et liens d'invitation. Aucun courriel n'est envoyé : le lien s'affiche une fois,
// à copier et à transmettre soi-même ; seule son empreinte est gardée par le serveur.

import { api } from "../api.js";
import { formatDate } from "../format.js";
import { champChoix, champTexte, ligneChamp } from "../formulaire.js";
import { fermerPanneau, ouvrirPanneau } from "../panneau.js";
import { libelleRole, utilisateur } from "../session.js";
import { afficherErreur, el, masquerErreur } from "../ui.js";

const ROLES = [
  ["lecteur", "Lecteur : lit tout, télécharge les exports"],
  ["contributeur", "Contributeur : modifie les composants de ses blocs"],
  ["administrateur", "Administrateur : tout, dont les paramètres et les comptes"],
];

const PERMISSIONS = [
  ["achats", "Achats : commandes, réceptions, demandes de devis, fiches fournisseurs"],
  ["ensembles", "Ensembles : créer et modifier l'arborescence (hors budgets)"],
];

function lienInvitation(jeton) {
  return `${window.location.origin}/connexion.html#invitation=${jeton}`;
}

// Lien affiché une seule fois, avec un bouton pour le copier.
function encartInvitation(nom, { jeton, expire_le: expire }) {
  const lien = lienInvitation(jeton);
  const champ = el("input", { class: "champ", type: "text", value: lien, readonly: true, "aria-label": "Lien d'invitation" });
  champ.addEventListener("focus", () => champ.select());
  const copier = el("button", { type: "button", class: "bouton bouton--petit" }, "Copier");
  copier.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(lien);
      copier.textContent = "Copié";
    } catch {
      champ.select();
    }
  });
  return el(
    "div",
    { class: "message message-ok" },
    el("p", {}, `Lien pour ${nom}, valable jusqu'au ${formatDate(expire.slice(0, 10))} à ${expire.slice(11, 16)}, utilisable une seule fois. ` +
      "Il ne sera plus affiché : le transmettre maintenant, par un canal sûr (il donne accès au compte)."),
    el("div", { class: "lien-invitation" }, champ, copier),
  );
}

function cases(nom, options, coches) {
  return el(
    "div",
    { class: "cases-a-cocher" },
    options.map(([code, texte]) =>
      el("label", { class: "filtre-case" }, el("input", { type: "checkbox", name: nom, value: code, checked: coches.includes(code) }), texte),
    ),
  );
}

function valeursCochees(formulaire, nom) {
  return [...formulaire.querySelectorAll(`input[name="${nom}"]:checked`)].map((c) => c.value);
}

function ouvrirFormulaire(compte, blocs, { surEnregistre }) {
  const creation = compte === null;
  const u = compte ?? { role: "contributeur", blocs: [], permissions: [], actif: true };
  const role = champChoix("role", ROLES, u.role);
  const zoneContributeur = el(
    "div",
    {},
    ligneChamp("Blocs fonctionnels", cases("blocs", blocs.map((b) => [b.code, `${b.code} — ${b.nom}`]), u.blocs), {
      aide: "Composants que ce contributeur peut créer et modifier.",
    }),
    ligneChamp("Permissions en plus", cases("permissions", PERMISSIONS, u.permissions)),
  );
  const majRole = () => {
    zoneContributeur.hidden = role.value !== "contributeur";
  };
  role.addEventListener("change", majRole);
  majRole();
  const actif = el("input", { type: "checkbox", name: "actif", checked: u.actif });
  const retour = el("div");
  const formulaire = el(
    "form",
    { class: "formulaire", novalidate: true },
    creation
      ? ligneChamp("Adresse mail", champTexte("identifiant", "", { type: "email", autocomplete: "off" }), { requis: true, aide: "Sert d'identifiant de connexion ; aucun courriel n'y est envoyé." })
      : ligneChamp("Adresse mail", champTexte("identifiant", u.identifiant, { disabled: true })),
    ligneChamp("Nom affiché", champTexte("nom", u.nom ?? "", { maxlength: "60" }), { requis: true, aide: "Apparaît dans l'historique à chaque modification : il doit rester distinctif." }),
    ligneChamp("Rôle", role, { requis: true }),
    zoneContributeur,
    creation ? null : el("label", { class: "filtre-case" }, actif, "Compte actif (décocher ferme aussitôt ses sessions)"),
    el(
      "div",
      { class: "actions-formulaire" },
      el("button", { type: "button", class: "bouton bouton--discret", onclick: () => fermerPanneau() }, "Annuler"),
      el("button", { type: "submit", class: "bouton" }, creation ? "Créer et obtenir le lien" : "Enregistrer"),
    ),
    retour,
  );
  formulaire.addEventListener("submit", async (e) => {
    e.preventDefault();
    const champs = formulaire.elements;
    const contributeur = role.value === "contributeur";
    const valeurs = {
      nom: champs.nom.value.trim(),
      role: role.value,
      blocs: contributeur ? valeursCochees(formulaire, "blocs") : [],
      permissions: contributeur ? valeursCochees(formulaire, "permissions") : [],
    };
    if (!valeurs.nom) return afficherErreur("Le nom affiché est obligatoire.");
    try {
      if (creation) {
        const identifiant = champs.identifiant.value.trim();
        if (!identifiant) return afficherErreur("L'adresse mail est obligatoire.");
        const cree = await api.createUtilisateur({ identifiant, ...valeurs });
        masquerErreur();
        await surEnregistre();
        formulaire.replaceChildren(encartInvitation(cree.utilisateur.nom, cree));
        return;
      }
      await api.patchUtilisateur(u.id, { ...valeurs, actif: actif.checked });
      masquerErreur();
      fermerPanneau({ silencieux: true });
      await surEnregistre();
    } catch (erreur) {
      afficherErreur(erreur);
    }
  });
  ouvrirPanneau(creation ? "Nouvel utilisateur" : `Modifier ${u.nom}`, formulaire);
  (creation ? formulaire.elements.identifiant : formulaire.elements.nom).focus();
}

function etatCompte(u) {
  if (!u.actif) return el("span", { class: "etiquette etiquette--alerte" }, "désactivé");
  if (u.invitation_expire_le) return el("span", { class: "etiquette" }, `invitation jusqu'au ${formatDate(u.invitation_expire_le.slice(0, 10))}`);
  if (!u.a_mot_de_passe) return el("span", { class: "etiquette" }, "sans mot de passe : nouveau lien à envoyer");
  return el("span", { class: "texte-doux" }, u.derniere_connexion ? `connecté le ${formatDate(u.derniere_connexion.slice(0, 10))}` : "jamais connecté");
}

function droitsCompte(u) {
  if (u.role !== "contributeur") return "—";
  const morceaux = [u.blocs.length ? `blocs ${u.blocs.join(", ")}` : "aucun bloc"];
  if (u.permissions.length) morceaux.push(`+ ${u.permissions.join(", ")}`);
  return morceaux.join(" ");
}

export async function afficherOngletUtilisateurs(cible) {
  const rafraichir = () => afficherOngletUtilisateurs(cible);
  const [comptes, blocs] = await Promise.all([api.getUtilisateurs(), api.getBlocs({ archives: true })]);
  const retour = el("div");
  const nouveauLien = async (u) => {
    const texte = u.a_mot_de_passe
      ? `Envoyer un nouveau lien à ${u.nom} ?\n\nSon mot de passe actuel sera effacé et ses sessions fermées : il choisira un nouveau mot de passe par le lien.`
      : `Générer un nouveau lien pour ${u.nom} ? L'ancien lien ne fonctionnera plus.`;
    if (!confirm(texte)) return;
    try {
      const invitation = await api.renouvelerInvitation(u.id);
      masquerErreur();
      await rafraichir();
      cible.querySelector(".retour-utilisateurs").replaceChildren(encartInvitation(u.nom, invitation));
    } catch (erreur) {
      afficherErreur(erreur);
    }
  };
  const moi = utilisateur()?.id;
  const lignes = comptes.map((u) =>
    el(
      "tr",
      { class: u.actif ? "" : "ligne--inactive" },
      el("td", {}, u.nom, u.id === moi ? el("span", { class: "texte-doux" }, " (vous)") : null),
      el("td", { class: "texte-doux" }, u.identifiant),
      el("td", {}, libelleRole(u.role)),
      el("td", {}, droitsCompte(u)),
      el("td", {}, etatCompte(u)),
      el(
        "td",
        { class: "nombre" },
        el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => ouvrirFormulaire(u, blocs, { surEnregistre: rafraichir }) }, "Modifier"),
        " ",
        u.actif ? el("button", { type: "button", class: "bouton bouton--petit bouton--discret", onclick: () => nouveauLien(u) }, "Nouveau lien") : null,
      ),
    ),
  );
  retour.className = "retour-utilisateurs";
  cible.replaceChildren(
    el(
      "section",
      { class: "panneau" },
      el(
        "div",
        { class: "titre-section" },
        el("h2", {}, "Utilisateurs"),
        el("button", { type: "button", class: "bouton", onclick: () => ouvrirFormulaire(null, blocs, { surEnregistre: rafraichir }) }, "Nouvel utilisateur"),
      ),
      el(
        "p",
        { class: "texte-doux" },
        "Chaque compte entre par un lien d'invitation à usage unique, valable 72 heures, où la personne choisit son mot de passe. " +
          "Un mot de passe oublié se règle par « Nouveau lien ». Un compte n'est jamais supprimé : le désactiver ferme ses sessions, " +
          "et son nom reste dans l'historique.",
      ),
      retour,
      el(
        "table",
        { class: "table table--dense table--parametres" },
        el("thead", {}, el("tr", {}, ["Nom", "Adresse mail", "Rôle", "Droits", "État", ""].map((t) => el("th", {}, t)))),
        el("tbody", {}, lignes),
      ),
    ),
  );
}
