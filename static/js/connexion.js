// Page de connexion : identifiant et mot de passe, ou choix du mot de passe depuis un lien
// d'invitation (connexion.html#invitation=JETON). Le jeton est lu après « # » : le navigateur
// ne l'envoie jamais au serveur, et il est effacé de la barre d'adresse dès sa lecture.

import { api } from "./api.js";

const formulaireConnexion = document.getElementById("formulaire-connexion");
const formulaireInvitation = document.getElementById("formulaire-invitation");
const message = document.getElementById("connexion-message");

function afficherMessage(texte) {
  message.textContent = texte;
  message.hidden = !texte;
}

// Après connexion, retour à l'écran demandé : seulement une route de l'application (#/…).
function entrer() {
  const retour = new URLSearchParams(window.location.search).get("retour") ?? "";
  window.location.assign(/^#\/[\w\-/?=&%.]*$/.test(retour) ? `/${retour}` : "/");
}

function lireJeton() {
  const jeton = new URLSearchParams(window.location.hash.slice(1)).get("invitation");
  if (jeton) history.replaceState(null, "", window.location.pathname);
  return jeton;
}

async function occuper(formulaire, action) {
  const bouton = formulaire.querySelector("button[type=submit]");
  bouton.disabled = true;
  afficherMessage("");
  try {
    await action();
  } catch (erreur) {
    afficherMessage(erreur.message);
    bouton.disabled = false;
  }
}

formulaireConnexion.addEventListener("submit", (e) => {
  e.preventDefault();
  const champs = formulaireConnexion.elements;
  const identifiant = champs.identifiant.value.trim();
  const motDePasse = champs.mot_de_passe.value;
  if (!identifiant || !motDePasse) return afficherMessage("Saisir l'adresse mail et le mot de passe.");
  occuper(formulaireConnexion, async () => {
    await api.connecter(identifiant, motDePasse);
    entrer();
  });
});

async function preparerInvitation(jeton) {
  formulaireConnexion.hidden = true;
  formulaireInvitation.hidden = false;
  document.getElementById("connexion-sous-titre").textContent = "Choisir votre mot de passe";
  let invitation;
  try {
    invitation = await api.verifierInvitation(jeton);
  } catch (erreur) {
    formulaireInvitation.hidden = true;
    formulaireConnexion.hidden = false;
    afficherMessage(erreur.message);
    return;
  }
  document.getElementById("invitation-bienvenue").textContent =
    `Bienvenue ${invitation.nom}. Ce lien ne sert qu'une fois : choisir maintenant le mot de passe de votre compte.`;
  formulaireInvitation.elements.identifiant.value = invitation.identifiant;
  formulaireInvitation.addEventListener("submit", (e) => {
    e.preventDefault();
    const champs = formulaireInvitation.elements;
    if (champs.mot_de_passe.value.length < 12) return afficherMessage("Le mot de passe doit compter au moins 12 caractères.");
    if (champs.mot_de_passe.value !== champs.confirmation.value) return afficherMessage("Les deux saisies du mot de passe diffèrent.");
    occuper(formulaireInvitation, async () => {
      await api.accepterInvitation(jeton, champs.mot_de_passe.value);
      entrer();
    });
  });
}

async function demarrer() {
  const jeton = lireJeton();
  if (jeton) return preparerInvitation(jeton);
  // Déjà connecté, ou mode local : rien à faire ici.
  try {
    await api.getSession();
    entrer();
  } catch {
    formulaireConnexion.elements.identifiant.focus();
  }
}

// Lien d'invitation collé alors que cette page est déjà ouverte : seul le « # » change.
window.addEventListener("hashchange", () => window.location.reload());

demarrer();
