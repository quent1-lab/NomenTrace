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

// Exigences du mot de passe, les mêmes que celles du serveur (exigences_mot_de_passe dans
// backend/services/authentification.py), qui seules font foi : elles ne servent ici qu'à
// guider la saisie. Le mot de passe n'est jamais envoyé avant la validation du formulaire.
const LONGUEUR_MIN = 12;
const LONGUEUR_MAX = 128;
const LONGUEUR_PHRASE = 20;
const COURANTS = [
  "motdepasse", "password", "azerty", "qwerty", "123456789", "1234567890", "abcdefghijkl",
  "nomentrace", "bonjour", "soleil", "doudou", "loveyou", "iloveyou", "admin",
  "administrateur", "azertyuiop", "qwertyuiop",
];

function simplifie(texte) {
  return [...texte.toLowerCase()].filter((c) => /[\p{L}\p{N}]/u.test(c)).join("");
}

function exigences(mot, identifiant, nom) {
  const compose =
    mot.length >= LONGUEUR_PHRASE ||
    (/\p{Ll}/u.test(mot) && /\p{Lu}/u.test(mot) && /\p{N}/u.test(mot) && /[^\p{L}\p{N}]/u.test(mot));
  const simple = simplifie(mot);
  const personnels = [simplifie(identifiant.split("@")[0]), simplifie(nom)].filter((p) => p.length >= 3);
  const courant = COURANTS.some((m) => simple.includes(m) && simple.replace(m, "").length < 6);
  return [
    [`${LONGUEUR_MIN} caractères au moins`, mot.length >= LONGUEUR_MIN && mot.length <= LONGUEUR_MAX],
    [`une minuscule, une majuscule, un chiffre et un caractère spécial, ou une phrase de ${LONGUEUR_PHRASE} caractères au moins`, compose],
    ["ni l'adresse mail ni le nom", !personnels.some((p) => simple.includes(p))],
    ["6 caractères différents au moins, pas un mot de passe courant", new Set(mot).size >= 6 && !courant],
  ];
}

function afficherExigences(liste) {
  const zone = document.getElementById("exigences");
  zone.replaceChildren(
    ...liste.map(([texte, ok]) => {
      const ligne = document.createElement("li");
      ligne.className = ok ? "exigence exigence--ok" : "exigence";
      ligne.textContent = texte;
      return ligne;
    }),
  );
}

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
  const saisie = formulaireInvitation.elements.mot_de_passe;
  const majExigences = () => afficherExigences(exigences(saisie.value, invitation.identifiant, invitation.nom));
  saisie.addEventListener("input", majExigences);
  majExigences();
  formulaireInvitation.addEventListener("submit", (e) => {
    e.preventDefault();
    const champs = formulaireInvitation.elements;
    const manquantes = exigences(champs.mot_de_passe.value, invitation.identifiant, invitation.nom).filter(([, ok]) => !ok);
    if (manquantes.length) return afficherMessage(`Mot de passe refusé. Il faut : ${manquantes.map(([t]) => t).join(" ; ")}.`);
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
