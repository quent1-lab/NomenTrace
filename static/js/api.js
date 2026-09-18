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

  getBlocs: () => requete("GET", "/api/blocs"),
  patchBloc: (code, modifs) => requete("PATCH", `/api/blocs/${encodeURIComponent(code)}`, modifs),
  getProchainId: (code) => requete("GET", `/api/blocs/${encodeURIComponent(code)}/prochain-id`),

  getFournisseurs: () => requete("GET", "/api/fournisseurs"),
  getEnsembles: () => requete("GET", "/api/ensembles"),

  getComposants: (filtres) => requete("GET", avecParametres("/api/composants", filtres)),
  getComposant: (id) => requete("GET", `/api/composants/${encodeURIComponent(id)}`),
  createComposant: (valeurs) => requete("POST", "/api/composants", valeurs),
  patchComposant: (id, modifs) => requete("PATCH", `/api/composants/${encodeURIComponent(id)}`, modifs),
  archiveComposant: (id) => requete("DELETE", `/api/composants/${encodeURIComponent(id)}`),

  createAffectation: (ensemble, valeurs) =>
    requete("POST", `/api/ensembles/${encodeURIComponent(ensemble)}/affectations`, valeurs),
  patchAffectation: (id, modifs) => requete("PATCH", `/api/affectations/${id}`, modifs),
  deleteAffectation: (id) => requete("DELETE", `/api/affectations/${id}`),
};
