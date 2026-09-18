// Tous les appels au serveur passent par ce module : aucun fetch ailleurs.

export class ErreurApi extends Error {
  constructor(message, statut) {
    super(message);
    this.statut = statut;
  }
}

const ecouteursEcriture = new Set();

// Permet à l'interface de réagir après chaque écriture réussie (état de l'export).
export function surEcriture(rappel) {
  ecouteursEcriture.add(rappel);
}

async function requete(methode, chemin, corps) {
  const options = { method: methode, headers: {} };
  if (corps !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  let reponse;
  try {
    reponse = await fetch(chemin, options);
  } catch {
    throw new ErreurApi("Le serveur Nomentrace ne répond pas. Est-il toujours lancé ?", 0);
  }
  const donnees = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const message = donnees?.erreur ?? `Erreur ${reponse.status}`;
    throw new ErreurApi(message, reponse.status);
  }
  if (methode !== "GET") ecouteursEcriture.forEach((rappel) => rappel());
  return donnees;
}

function avecParametres(chemin, parametres = {}) {
  const requeteUrl = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(parametres)) {
    if (valeur !== undefined && valeur !== null && valeur !== "") requeteUrl.set(cle, valeur);
  }
  const texte = requeteUrl.toString();
  return texte ? `${chemin}?${texte}` : chemin;
}

export const api = {
  getSante: () => requete("GET", "/api/sante"),
  getPilotage: () => requete("GET", "/api/pilotage"),
  getParametres: () => requete("GET", "/api/parametres"),
  getListes: () => requete("GET", "/api/listes"),
  createValeurListe: (liste, valeurs) => requete("POST", `/api/listes/${liste}`, valeurs),
  patchValeurListe: (liste, code, modifs) =>
    requete("PATCH", `/api/listes/${liste}/${encodeURIComponent(code)}`, modifs),
  deleteValeurListe: (liste, code) => requete("DELETE", `/api/listes/${liste}/${encodeURIComponent(code)}`),

  getBlocs: () => requete("GET", "/api/blocs"),
  patchBloc: (code, modifs) => requete("PATCH", `/api/blocs/${encodeURIComponent(code)}`, modifs),
  getProchainId: (code) => requete("GET", `/api/blocs/${encodeURIComponent(code)}/prochain-id`),

  getFournisseurs: () => requete("GET", "/api/fournisseurs"),
  getEnsembles: () => requete("GET", "/api/ensembles"),
  getEnsemble: (code) => requete("GET", `/api/ensembles/${encodeURIComponent(code)}`),
  createEnsemble: (valeurs) => requete("POST", "/api/ensembles", valeurs),
  patchEnsemble: (code, modifs) => requete("PATCH", `/api/ensembles/${encodeURIComponent(code)}`, modifs),
  archiveEnsemble: (code) => requete("DELETE", `/api/ensembles/${encodeURIComponent(code)}`),
  getComposantsEnsemble: (code) => requete("GET", `/api/ensembles/${encodeURIComponent(code)}/composants`),
  getRepartition: () => requete("GET", "/api/ensembles/repartition"),
  getIncoherences: () => requete("GET", "/api/ensembles/incoherences"),

  getComposants: (filtres) => requete("GET", avecParametres("/api/composants", filtres)),
  getComposant: (id) => requete("GET", `/api/composants/${encodeURIComponent(id)}`),
  createComposant: (valeurs) => requete("POST", "/api/composants", valeurs),
  patchComposant: (id, modifs) => requete("PATCH", `/api/composants/${encodeURIComponent(id)}`, modifs),
  archiveComposant: (id) => requete("DELETE", `/api/composants/${encodeURIComponent(id)}`),

  getCommandes: () => requete("GET", "/api/commandes"),
  getCommande: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}`),
  createCommande: (valeurs) => requete("POST", "/api/commandes", valeurs),
  patchCommande: (numero, modifs) => requete("PATCH", `/api/commandes/${encodeURIComponent(numero)}`, modifs),
  archiveCommande: (numero) => requete("DELETE", `/api/commandes/${encodeURIComponent(numero)}`),
  getLignes: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}/lignes`),
  createLigne: (numero, valeurs) => requete("POST", `/api/commandes/${encodeURIComponent(numero)}/lignes`, valeurs),
  patchLigne: (numero, id, modifs) => requete("PATCH", `/api/commandes/${encodeURIComponent(numero)}/lignes/${id}`, modifs),
  deleteLigne: (numero, id) => requete("DELETE", `/api/commandes/${encodeURIComponent(numero)}/lignes/${id}`),
  receptionner: (numero, reception) => requete("POST", `/api/commandes/${encodeURIComponent(numero)}/reception`, reception),

  getStock: () => requete("GET", "/api/stock"),
  getMouvements: (filtres) => requete("GET", avecParametres("/api/mouvements", filtres)),
  createMouvement: (valeurs) => requete("POST", "/api/mouvements", valeurs),

  createAffectation: (ensemble, valeurs) =>
    requete("POST", `/api/ensembles/${encodeURIComponent(ensemble)}/affectations`, valeurs),
  patchAffectation: (id, modifs) => requete("PATCH", `/api/affectations/${id}`, modifs),
  deleteAffectation: (id) => requete("DELETE", `/api/affectations/${id}`),
};
