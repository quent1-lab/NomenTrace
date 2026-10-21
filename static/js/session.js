// Utilisateur connecté et ses droits, lus une fois au démarrage (GET /api/session).
// L'interface s'en sert pour masquer ce qui est interdit ; le serveur, lui, vérifie chaque
// requête : masquer un bouton n'est jamais la protection.

import { api } from "./api.js";

let courante = null;

const ROLES = { lecteur: "Lecteur", contributeur: "Contributeur", administrateur: "Administrateur" };

export async function chargerSession() {
  courante = await api.getSession();
  const corps = document.body.classList;
  corps.toggle("peut-ecrire", peutEcrire());
  corps.toggle("est-admin", estAdmin());
  corps.toggle("peut-achats", aPermission("achats"));
  corps.toggle("peut-ensembles", aPermission("ensembles"));
  corps.toggle("peut-attributs", aPermission("attributs"));
  corps.toggle("reglages-imposes", Boolean(reglagesImposes()));
  corps.toggle("est-reference", Boolean(dossierReference()));
  return courante;
}

export function utilisateur() {
  return courante?.utilisateur ?? null;
}

// Nom d'équipe du projet de la page, affiché après le nom du projet (« SPOC · Alpha »).
export function nomEquipe() {
  return courante?.nom_equipe ?? null;
}

// Nom du dossier qui impose ses réglages à ce projet, ou null (projet hors dossier).
export function reglagesImposes() {
  return courante?.imposes ?? null;
}

// Nom du dossier dont cette page règle les paramètres communs, ou null (projet ordinaire).
export function dossierReference() {
  return courante?.reference ?? null;
}

// « dossier » ou « organisme » quand la page est une référence (réglages communs, liste de
// fournisseurs), null sinon.
export function typeReference() {
  return courante?.type_reference ?? null;
}

// Code de l'organisme dont la page règle la liste des fournisseurs, ou null.
export function codeOrganisme() {
  return courante?.organisme ?? null;
}

// Code du dossier du projet de la page, ou null.
export function codeDossier() {
  return courante?.dossier ?? null;
}

export function modeLocal() {
  return Boolean(courante?.mode_local);
}

// Nom qui signe une action (« demandée par », « par qui ») ; vide en mode local, sans compte.
export function nomAuteur() {
  return modeLocal() ? "" : (utilisateur()?.nom ?? "");
}

export function libelleRole(role) {
  return ROLES[role] ?? role;
}

export function estAdmin() {
  return utilisateur()?.role === "administrateur";
}

export function peutEcrire() {
  return ["contributeur", "administrateur"].includes(utilisateur()?.role);
}

// Permission supplémentaire d'un contributeur : « achats », « ensembles » ou « attributs ».
export function aPermission(permission) {
  return estAdmin() || (peutEcrire() && utilisateur().permissions.includes(permission));
}

// Composants d'un bloc : modifiables par l'administrateur et les contributeurs de ce bloc.
export function ecritBloc(bloc) {
  return estAdmin() || (peutEcrire() && (utilisateur().tous_blocs || utilisateur().blocs.includes(bloc)));
}
