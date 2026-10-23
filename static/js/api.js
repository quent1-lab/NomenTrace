// Tous les appels au serveur passent par ce module : aucun fetch ailleurs.

export class ErreurApi extends Error {
  constructor(message, statut) {
    super(message);
    this.statut = statut;
  }
}

const ecouteursEcriture = new Set();

// Projet de la page, lu dans son adresse (/p/<code>/) : chaque appel et chaque lien vers le
// serveur en porte le préfixe. Sans préfixe (page de connexion), l'adresse reste nue.
const PREFIXE_PROJET = window.location.pathname.match(/^\/p\/[a-z0-9][a-z0-9-]*(?=\/)/)?.[0] ?? "";

function adresse(chemin) {
  return PREFIXE_PROJET + chemin;
}

// Session expirée ou absente : retour à la page de connexion, qui ramènera ensuite à l'écran
// en cours. Rien depuis la page de connexion elle-même, dont les refus s'affichent sur place.
export function allerConnexion() {
  if (window.location.pathname.endsWith("/connexion.html")) return;
  const page = window.location.pathname.match(/^\/[dop]\/[a-z0-9][a-z0-9-]*\//)?.[0] ?? "/";
  const retour = encodeURIComponent(`${page}${window.location.hash}`);
  window.location.assign(`/connexion.html?retour=${retour}`);
}

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
    reponse = await fetch(adresse(chemin), options);
  } catch {
    throw new ErreurApi("Le serveur Nomentrace ne répond pas : vérifier qu'il est lancé.", 0);
  }
  const donnees = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    if (reponse.status === 401) allerConnexion();
    const message = donnees?.erreur ?? `Erreur ${reponse.status}`;
    throw new ErreurApi(message, reponse.status);
  }
  if (methode !== "GET") ecouteursEcriture.forEach((rappel) => rappel());
  return donnees;
}

// Envoi de fichiers : le navigateur fixe lui-même l'en-tête multipart. XMLHttpRequest plutôt
// que fetch, seul à donner l'avancement de l'envoi : progression(envoye, total) est appelée
// pendant l'envoi, puis progression(total, total, true) quand le serveur traite les fichiers.
// Tant qu'un envoi est en cours, fermer ou recharger l'onglet demande confirmation. Changer
// d'écran ne l'interrompt pas : le routage par hash ne recharge pas la page.
let envoisEnCours = 0;
window.addEventListener("beforeunload", (e) => {
  if (envoisEnCours > 0) e.preventDefault();
});

function requeteFormulaire(chemin, donnees, progression = null) {
  envoisEnCours += 1;
  return new Promise((resoudre, rejeter) => {
    const xhr = new XMLHttpRequest();
    xhr.addEventListener("loadend", () => {
      envoisEnCours -= 1;
    });
    xhr.open("POST", adresse(chemin));
    xhr.responseType = "json";
    if (progression) {
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) progression(e.loaded, e.total, false);
      });
      xhr.upload.addEventListener("load", () => progression(1, 1, true));
    }
    xhr.addEventListener("error", () => {
      rejeter(new ErreurApi("Le serveur Nomentrace ne répond pas : vérifier qu'il est lancé.", 0));
    });
    xhr.addEventListener("load", () => {
      const resultat = xhr.response;
      if (xhr.status < 200 || xhr.status >= 300) {
        if (xhr.status === 401) allerConnexion();
        const message = xhr.status === 413 ? "Envoi trop volumineux : 100 Mo au plus à la fois." : resultat?.erreur;
        rejeter(new ErreurApi(message ?? `Erreur ${xhr.status}`, xhr.status));
        return;
      }
      ecouteursEcriture.forEach((rappel) => rappel());
      resoudre(resultat);
    });
    xhr.send(donnees);
  });
}

// Téléchargement d'un fichier construit par le serveur : renvoie son contenu et son nom.
async function requeteFichier(chemin) {
  let reponse;
  try {
    reponse = await fetch(adresse(chemin));
  } catch {
    throw new ErreurApi("Le serveur Nomentrace ne répond pas : vérifier qu'il est lancé.", 0);
  }
  if (!reponse.ok) {
    if (reponse.status === 401) allerConnexion();
    const donnees = await reponse.json().catch(() => null);
    throw new ErreurApi(donnees?.erreur ?? `Erreur ${reponse.status}`, reponse.status);
  }
  const disposition = reponse.headers.get("Content-Disposition") ?? "";
  // filename* (encodé, accents permis) d'abord, sinon filename.
  const encode = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const nom = encode ? decodeURIComponent(encode) : (disposition.match(/filename="?([^";]+)"?/)?.[1] ?? "nomentrace");
  return { contenu: await reponse.blob(), nom };
}

// Envoi d'un fichier dont la réponse est un fichier (classeur complété) : { contenu, nom }.
async function requeteFormulaireFichier(chemin, donnees) {
  let reponse;
  try {
    reponse = await fetch(adresse(chemin), { method: "POST", body: donnees });
  } catch {
    throw new ErreurApi("Le serveur Nomentrace ne répond pas : vérifier qu'il est lancé.", 0);
  }
  if (!reponse.ok) {
    if (reponse.status === 401) allerConnexion();
    const resultat = await reponse.json().catch(() => null);
    throw new ErreurApi(resultat?.erreur ?? `Erreur ${reponse.status}`, reponse.status);
  }
  ecouteursEcriture.forEach((rappel) => rappel());
  const disposition = reponse.headers.get("Content-Disposition") ?? "";
  const encode = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  return { contenu: await reponse.blob(), nom: encode ? decodeURIComponent(encode) : "suivi.xlsx" };
}

// Adresses de téléchargement des modèles à remplir (liens, pas des appels fetch).
export function lienModele(type, code) {
  if (type === "vierge") return adresse("/api/modeles/vierge");
  return adresse(`/api/${type === "bloc" ? "blocs" : "ensembles"}/${encodeURIComponent(code)}/modele`);
}

// Adresse d'ouverture d'un document joint (lien, pas un appel fetch).
// Fichier d'un document de commande commune, lu dans la copie d'un de ses projets.
export function lienFichierCommune(dossier, numero, projet, id) {
  return `/api/dossiers/${dossier}/communes/${numero}/documents/${projet}/${id}/fichier`;
}

function lienDemandeDevisCommune(dossier, numero, format, avant) {
  const requete = avant ? `?avant=${encodeURIComponent(avant)}` : "";
  return `/api/dossiers/${dossier}/communes/${numero}/demande-devis.${format}${requete}`;
}

export function lienFichierDocument(id) {
  return adresse(`/api/documents/${id}/fichier`);
}

// Adresse de l'image du logo ; la date de modification déjoue le cache après un changement.
export function lienLogo(modifieLe) {
  return adresse(`/api/parametres/logo?v=${encodeURIComponent(modifieLe)}`);
}

function avecParametres(chemin, parametres = {}) {
  const requeteUrl = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(parametres)) {
    // Une liste devient un paramètre répété : ?attr=a&attr=b
    if (Array.isArray(valeur)) valeur.forEach((v) => requeteUrl.append(cle, v));
    else if (valeur !== undefined && valeur !== null && valeur !== "") requeteUrl.set(cle, valeur);
  }
  const texte = requeteUrl.toString();
  return texte ? `${chemin}?${texte}` : chemin;
}

export const api = {
  getSante: () => requete("GET", "/api/sante"),
  getSession: () => requete("GET", "/api/session"),
  connecter: (identifiant, motDePasse) => requete("POST", "/api/session", { identifiant, mot_de_passe: motDePasse }),
  deconnecter: () => requete("DELETE", "/api/session"),
  verifierInvitation: (jeton) => requete("POST", "/api/invitation/verifier", { jeton }),
  accepterInvitation: (jeton, motDePasse) => requete("POST", "/api/invitation", { jeton, mot_de_passe: motDePasse }),
  getUtilisateurs: () => requete("GET", "/api/utilisateurs"),
  createUtilisateur: (valeurs) => requete("POST", "/api/utilisateurs", valeurs),
  patchUtilisateur: (id, modifs) => requete("PATCH", `/api/utilisateurs/${id}`, modifs),
  renouvelerInvitation: (id) => requete("POST", `/api/utilisateurs/${id}/invitation`),
  retirerUtilisateur: (id) => requete("DELETE", `/api/utilisateurs/${id}`),

  // Pages communes : hors de tout projet (adresses sans préfixe /p/<code>).
  getAccueil: () => requete("GET", "/api/accueil"),
  createOrganisme: (valeurs) => requete("POST", "/api/organismes", valeurs),
  getOrganisme: (code) => requete("GET", `/api/organismes/${code}`),
  patchOrganisme: (code, modifs) => requete("PATCH", `/api/organismes/${code}`, modifs),
  createDossier: (organisme, valeurs) => requete("POST", `/api/organismes/${organisme}/dossiers`, valeurs),
  createMembreOrganisme: (organisme, valeurs) => requete("POST", `/api/organismes/${organisme}/membres`, valeurs),
  patchMembreOrganisme: (organisme, id, profil) =>
    requete("PATCH", `/api/organismes/${organisme}/membres/${id}`, { profil }),
  retirerMembreOrganisme: (organisme, id) => requete("DELETE", `/api/organismes/${organisme}/membres/${id}`),
  getDossier: (code) => requete("GET", `/api/dossiers/${code}`),
  patchDossier: (code, modifs) => requete("PATCH", `/api/dossiers/${code}`, modifs),
  createProjet: (dossier, valeurs) => requete("POST", `/api/dossiers/${dossier}/projets`, valeurs),
  addResponsable: (dossier, id) => requete("POST", `/api/dossiers/${dossier}/responsables`, { utilisateur_id: id }),
  retirerResponsable: (dossier, id) => requete("DELETE", `/api/dossiers/${dossier}/responsables/${id}`),
  patchProjet: (code, modifs) => requete("PATCH", `/api/projets/${code}`, modifs),
  getCommunes: (dossier) => requete("GET", `/api/dossiers/${dossier}/communes`),
  createCommune: (dossier, valeurs) => requete("POST", `/api/dossiers/${dossier}/communes`, valeurs),
  getFournisseursCommune: (dossier) => requete("GET", `/api/dossiers/${dossier}/communes/fournisseurs`),
  getCommune: (dossier, numero) => requete("GET", `/api/dossiers/${dossier}/communes/${numero}`),
  patchCommune: (dossier, numero, modifs) => requete("PATCH", `/api/dossiers/${dossier}/communes/${numero}`, modifs),
  archiveCommune: (dossier, numero) => requete("DELETE", `/api/dossiers/${dossier}/communes/${numero}`),
  getCandidatsCommune: (dossier, numero) => requete("GET", `/api/dossiers/${dossier}/communes/${numero}/candidats`),
  addLignesCommune: (dossier, numero, lignes) => requete("POST", `/api/dossiers/${dossier}/communes/${numero}/lignes`, { lignes }),
  patchLigneCommune: (dossier, numero, projet, id, modifs) =>
    requete("PATCH", `/api/dossiers/${dossier}/communes/${numero}/lignes/${projet}/${id}`, modifs),
  deleteLigneCommune: (dossier, numero, projet, id) => requete("DELETE", `/api/dossiers/${dossier}/communes/${numero}/lignes/${projet}/${id}`),
  createFraisCommune: (dossier, numero, valeurs) => requete("POST", `/api/dossiers/${dossier}/communes/${numero}/frais`, valeurs),
  deleteFraisCommune: (dossier, numero, id) => requete("DELETE", `/api/dossiers/${dossier}/communes/${numero}/frais/${id}`),
  receptionnerCommune: (dossier, numero, corps) => requete("POST", `/api/dossiers/${dossier}/communes/${numero}/reception`, corps),
  analyserSuiviCommunes: (dossier, donnees, progression) => requeteFormulaire(`/api/dossiers/${dossier}/communes/suivi/analyse`, donnees, progression),
  appliquerSuiviCommunes: (dossier, donnees) => requeteFormulaireFichier(`/api/dossiers/${dossier}/communes/suivi/appliquer`, donnees),
  deposerDocumentsCommune: (dossier, numero, donnees, progression) => requeteFormulaire(`/api/dossiers/${dossier}/communes/${numero}/documents`, donnees, progression),
  retirerDocumentCommune: (dossier, numero, empreinte) => requete("DELETE", `/api/dossiers/${dossier}/communes/${numero}/documents/${empreinte}`),
  telechargerDemandeDevisCommune: (dossier, numero, format, avant) => requeteFichier(lienDemandeDevisCommune(dossier, numero, format, avant)),
  rechercher: (q) => requete("GET", avecParametres("/api/recherche", { q })),
  getHistorique: (filtres) => requete("GET", avecParametres("/api/historique", filtres)),
  getTablesHistorique: () => requete("GET", "/api/historique/tables"),
  telechargerHistorique: (filtres) => requeteFichier(avecParametres("/api/historique/export", filtres)),
  getPilotage: () => requete("GET", "/api/pilotage"),
  getParametres: () => requete("GET", "/api/parametres"),
  patchParametres: (modifs) => requete("PATCH", "/api/parametres", modifs),
  getLogoInfos: () => requete("GET", "/api/parametres/logo/infos"),
  envoyerLogo: (donnees) => requeteFormulaire("/api/parametres/logo", donnees),
  deleteLogo: () => requete("DELETE", "/api/parametres/logo"),
  exporter: () => requete("POST", "/api/export"),
  telechargerExcelGlobal: () => requeteFichier("/api/export/classeur"),
  telechargerArchive: () => requeteFichier("/api/sauvegardes/archive"),
  getSauvegardes: () => requete("GET", "/api/sauvegardes"),
  createSauvegarde: () => requete("POST", "/api/sauvegardes"),
  getCorbeille: () => requete("GET", "/api/sauvegardes/corbeille"),
  viderCorbeille: () => requete("POST", "/api/sauvegardes/corbeille/vider"),
  restaurerSauvegarde: (nom) => requete("POST", `/api/sauvegardes/${encodeURIComponent(nom)}/restaurer`),
  getListes: () => requete("GET", "/api/listes"),
  createValeurListe: (liste, valeurs) => requete("POST", `/api/listes/${liste}`, valeurs),
  patchValeurListe: (liste, code, modifs) =>
    requete("PATCH", `/api/listes/${liste}/${encodeURIComponent(code)}`, modifs),
  deleteValeurListe: (liste, code) => requete("DELETE", `/api/listes/${liste}/${encodeURIComponent(code)}`),

  getAttributs: () => requete("GET", "/api/attributs"),
  createAttribut: (valeurs) => requete("POST", "/api/attributs", valeurs),
  patchAttribut: (code, modifs) => requete("PATCH", `/api/attributs/${encodeURIComponent(code)}`, modifs),
  createValeurAttribut: (code, libelle) => requete("POST", `/api/attributs/${encodeURIComponent(code)}/valeurs`, { libelle }),
  patchValeurAttribut: (code, valeur, modifs) =>
    requete("PATCH", `/api/attributs/${encodeURIComponent(code)}/valeurs/${encodeURIComponent(valeur)}`, modifs),
  getCalculAttribut: (code, filtres) =>
    requete("GET", avecParametres(`/api/attributs/${encodeURIComponent(code)}/calcul`, filtres)),
  getRepartitionAttribut: (code, filtres) =>
    requete("GET", avecParametres(`/api/attributs/${encodeURIComponent(code)}/repartition`, filtres)),

  getBlocs: ({ archives = false } = {}) => requete("GET", avecParametres("/api/blocs", { archives: archives ? "true" : "" })),
  createBloc: (valeurs) => requete("POST", "/api/blocs", valeurs),
  patchBloc: (code, modifs) => requete("PATCH", `/api/blocs/${encodeURIComponent(code)}`, modifs),
  getProchainId: (code) => requete("GET", `/api/blocs/${encodeURIComponent(code)}/prochain-id`),

  getFournisseurs: () => requete("GET", "/api/fournisseurs"),
  createFournisseur: (valeurs) => requete("POST", "/api/fournisseurs", valeurs),
  patchFournisseur: (nom, modifs) => requete("PATCH", `/api/fournisseurs/${encodeURIComponent(nom)}`, modifs),
  getFournisseur: (nom) => requete("GET", `/api/fournisseurs/${encodeURIComponent(nom)}`),
  comparerFournisseurs: (donnees) => requeteFormulaire("/api/fournisseurs/comparaison", donnees),
  appliquerComparaison: (corps) => requete("POST", "/api/fournisseurs/comparaison/appliquer", corps),
  archiveFournisseur: (nom) => requete("DELETE", `/api/fournisseurs/${encodeURIComponent(nom)}`),
  getEnsembles: () => requete("GET", "/api/ensembles"),
  getEnsemble: (code) => requete("GET", `/api/ensembles/${encodeURIComponent(code)}`),
  createEnsemble: (valeurs) => requete("POST", "/api/ensembles", valeurs),
  patchEnsemble: (code, modifs) => requete("PATCH", `/api/ensembles/${encodeURIComponent(code)}`, modifs),
  archiveEnsemble: (code) => requete("DELETE", `/api/ensembles/${encodeURIComponent(code)}`),
  getComposantsEnsemble: (code) => requete("GET", `/api/ensembles/${encodeURIComponent(code)}/composants`),
  getArbreEnsembles: () => requete("GET", "/api/ensembles/arbre"),
  getPropositionCopie: (code, nouveau) =>
    requete("GET", avecParametres(`/api/ensembles/${encodeURIComponent(code)}/copie`, { nouveau })),
  copierEnsemble: (code, corps) => requete("POST", `/api/ensembles/${encodeURIComponent(code)}/copie`, corps),
  getRepartition: (cumul = false) => requete("GET", avecParametres("/api/ensembles/repartition", { cumul: cumul ? "true" : "" })),
  getIncoherences: () => requete("GET", "/api/ensembles/incoherences"),

  getComposants: (filtres) => requete("GET", avecParametres("/api/composants", filtres)),
  exporterComposants: (filtres, colonnes) =>
    requeteFichier(avecParametres("/api/composants/export", { ...filtres, colonnes: colonnes.join(",") })),
  getComposant: (id) => requete("GET", `/api/composants/${encodeURIComponent(id)}`),
  createComposant: (valeurs) => requete("POST", "/api/composants", valeurs),
  patchComposant: (id, modifs) => requete("PATCH", `/api/composants/${encodeURIComponent(id)}`, modifs),
  archiveComposant: (id) => requete("DELETE", `/api/composants/${encodeURIComponent(id)}`),
  getCompteVisas: () => requete("GET", "/api/visas/compte"),
  viserComposants: (composants) => requete("POST", "/api/visas", { composants }),
  putAttributsComposant: (id, valeurs) => requete("PUT", `/api/composants/${encodeURIComponent(id)}/attributs`, { valeurs }),
  reclasserComposant: (id, blocCode) =>
    requete("POST", `/api/composants/${encodeURIComponent(id)}/reclasser`, { bloc_code: blocCode }),

  getControlesComposants: () => requete("GET", "/api/nettoyage/composants"),
  traiterComposants: (cles, action, simuler) => requete("POST", "/api/nettoyage/composants", { cles, action, simuler }),
  getControlesCommandes: () => requete("GET", "/api/nettoyage/commandes"),
  traiterCommandes: (cles, action, simuler) => requete("POST", "/api/nettoyage/commandes", { cles, action, simuler }),
  getEntitesSupprimables: () => requete("GET", "/api/nettoyage/entites"),
  supprimerEntite: (type, cle) => requete("DELETE", `/api/nettoyage/entites/${type}/${encodeURIComponent(cle)}`),
  viderJournal: () => requete("POST", "/api/nettoyage/journal/purge", { confirmer: true }),

  getCommandes: () => requete("GET", "/api/commandes"),
  getCandidatsDevis: () => requete("GET", "/api/demandes-devis"),
  creerDemandesDevis: (composants) => requete("POST", "/api/demandes-devis", { composants }),
  getCommande: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}`),
  createCommande: (valeurs) => requete("POST", "/api/commandes", valeurs),
  patchCommande: (numero, modifs) => requete("PATCH", `/api/commandes/${encodeURIComponent(numero)}`, modifs),
  archiveCommande: (numero) => requete("DELETE", `/api/commandes/${encodeURIComponent(numero)}`),
  getLignes: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}/lignes`),
  createLigne: (numero, valeurs) => requete("POST", `/api/commandes/${encodeURIComponent(numero)}/lignes`, valeurs),
  patchLigne: (numero, id, modifs) => requete("PATCH", `/api/commandes/${encodeURIComponent(numero)}/lignes/${id}`, modifs),
  deleteLigne: (numero, id) => requete("DELETE", `/api/commandes/${encodeURIComponent(numero)}/lignes/${id}`),
  analyserSuivi: (donnees, progression) => requeteFormulaire("/api/suivi-achats/analyse", donnees, progression),
  appliquerSuivi: (donnees) => requeteFormulaireFichier("/api/suivi-achats/appliquer", donnees),
  telechargerDemandeDevis: (numero, format, avant) =>
    requeteFichier(avecParametres(`/api/commandes/${encodeURIComponent(numero)}/demande-devis.${format}`, { avant })),
  getFrais: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}/frais`),
  createFrais: (numero, frais) => requete("POST", `/api/commandes/${encodeURIComponent(numero)}/frais`, frais),
  patchFrais: (id, modifs) => requete("PATCH", `/api/frais/${id}`, modifs),
  deleteFrais: (id) => requete("DELETE", `/api/frais/${id}`),
  receptionner: (numero, reception) => requete("POST", `/api/commandes/${encodeURIComponent(numero)}/reception`, reception),

  getStock: () => requete("GET", "/api/stock"),
  getMouvements: (filtres) => requete("GET", avecParametres("/api/mouvements", filtres)),
  createMouvement: (valeurs) => requete("POST", "/api/mouvements", valeurs),

  getDocumentsCommande: (numero) => requete("GET", `/api/commandes/${encodeURIComponent(numero)}/documents`),
  getDocumentsComposant: (id) => requete("GET", `/api/composants/${encodeURIComponent(id)}/documents`),
  deposerDocumentsCommande: (numero, donnees, progression) =>
    requeteFormulaire(`/api/commandes/${encodeURIComponent(numero)}/documents`, donnees, progression),
  deposerDocumentsComposant: (id, donnees, progression) =>
    requeteFormulaire(`/api/composants/${encodeURIComponent(id)}/documents`, donnees, progression),
  retirerDocument: (id) => requete("DELETE", `/api/documents/${id}`),

  getImports: () => requete("GET", "/api/imports"),
  getConsigneIA: () => requete("GET", "/api/modeles/consigne-ia"),
  getImport: (depot) => requete("GET", `/api/imports/${depot}`),
  deposerImport: (donnees, progression) => requeteFormulaire("/api/imports", donnees, progression),
  appliquerImport: (depot, decisions) => requete("POST", `/api/imports/${depot}/appliquer`, { decisions }),
  abandonnerImport: (depot) => requete("POST", `/api/imports/${depot}/abandonner`),

  createAffectation: (ensemble, valeurs) =>
    requete("POST", `/api/ensembles/${encodeURIComponent(ensemble)}/affectations`, valeurs),
  patchAffectation: (id, modifs) => requete("PATCH", `/api/affectations/${id}`, modifs),
  deleteAffectation: (id) => requete("DELETE", `/api/affectations/${id}`),
};
