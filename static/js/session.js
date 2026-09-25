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
  return courante;
}

export function utilisateur() {
  return courante?.utilisateur ?? null;
}

export function modeLocal() {
  return Boolean(courante?.mode_local);
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

// Permission supplémentaire d'un contributeur : « achats » ou « ensembles ».
export function aPermission(permission) {
  return estAdmin() || (peutEcrire() && utilisateur().permissions.includes(permission));
}

// Composants d'un bloc : modifiables par l'administrateur et les contributeurs de ce bloc.
export function ecritBloc(bloc) {
  return estAdmin() || (peutEcrire() && utilisateur().blocs.includes(bloc));
}
