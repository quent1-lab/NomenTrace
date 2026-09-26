# API

L'interface de Nomentrace ne fait rien que l'API ne permette : tout passe par des routes
JSON sous `/api/`, qu'on peut appeler depuis un script. Ce document les liste par domaine.
Le détail exact des champs acceptés est dans les modèles Pydantic de `backend/models.py`.
En mode local, FastAPI publie une description interactive sur
<http://127.0.0.1:8000/docs> ; en mode connecté, elle n'est pas publiée.

## Conventions

Les corps de requête et les réponses sont en JSON, sauf les dépôts de fichiers
(`multipart/form-data`) et les téléchargements (classeurs Excel, archive zip, documents).
Un champ inconnu dans un corps est refusé. Les montants sont en euros, hors taxes sauf
mention contraire, arrondis à deux décimales dans les réponses ; les taux de TVA sont des
fractions (0,2 pour 20 %). Les dates sont au format `AAAA-MM-JJ`, les horodatages en
`AAAA-MM-JJTHH:MM:SS`, heure locale.

Les valeurs énumérées circulent sans accents, telles qu'elles sont stockées (`Recu`,
`Non commence`) ; c'est l'interface qui les accentue.

Un PATCH ne modifie que les champs présents dans le corps. Un DELETE sur un composant, un
ensemble, une commande ou un fournisseur archive, il ne supprime pas ; les suppressions
physiques passent par les routes de nettoyage.

Une erreur renvoie `{"erreur": "message en français"}` avec un code adapté : 400 pour un
refus métier, 404 pour un élément introuvable ou archivé, 409 pour un conflit avec l'état
de la base (code déjà pris, cycle, contrainte), 422 pour des données invalides, 500 pour
un cas imprévu.

## Connexion et droits

En mode connecté, l'API s'utilise avec la session ouverte par `POST /api/session`, portée
par le cookie `nomentrace_session` (HttpOnly, SameSite=Lax, Secure en HTTPS). Sans session
valide, une route répond 401 ; avec une session mais sans le droit demandé, 403. Seules
`/api/sante`, l'ouverture et la fermeture de session et les routes d'invitation sont
accessibles sans connexion ; `/api/sante` ne donne alors ni le nom du projet ni l'état de
l'export.

La condition de chaque route (lecture, écriture, permission « achats » ou « ensembles »,
bloc du composant concerné, administrateur) est écrite dans la table `REGLES` de
`backend/services/droits.py`, qui fait référence. Une route absente de cette table est
réservée à l'administrateur.

Toute écriture (POST, PATCH, PUT, DELETE) doit porter un en-tête `Origin` égal à l'adresse
du serveur, comme le fait un navigateur ; un script qui appelle l'API l'ajoute lui-même.
Sinon la requête est refusée en 403. En mode local, seules les requêtes émises depuis le
poste et adressées à `127.0.0.1` ou `localhost` sont servies.

Le PATCH d'un composant accepte `modifie_le`, la date de modification lue avant l'édition :
si le composant a changé depuis, rien n'est écrit et la réponse est un 409 qui nomme
l'auteur de la dernière modification.

## Session et comptes

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/api/session` | Connexion : `identifiant`, `mot_de_passe` ; 401 si refusée, 429 après trop d'échecs, 503 si trop de connexions sont en cours |
| GET | `/api/session` | Utilisateur connecté, son rôle, ses blocs et permissions, nom du projet, mode local |
| DELETE | `/api/session` | Déconnexion : la session est supprimée côté serveur |
| POST | `/api/invitation/verifier` | Validité d'un jeton d'invitation (`jeton`) : compte concerné, ou 410 |
| POST | `/api/invitation` | Choix du mot de passe (`jeton`, `mot_de_passe`), puis session ouverte ; 400 qui cite les exigences non remplies |
| GET, POST | `/api/utilisateurs` | Comptes du projet ; création (renvoie le jeton d'invitation, une seule fois) |
| PATCH | `/api/utilisateurs/{id}` | Nom, rôle, blocs, permissions, actif |
| POST | `/api/utilisateurs/{id}/invitation` | Nouveau lien : efface le mot de passe et ferme les sessions |

Les routes `/api/utilisateurs` sont réservées à l'administrateur et répondent 409 en mode
local, où il n'y a pas de comptes.

## Projet, pilotage et historique

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/sante` | État du serveur, nom du projet, export en attente |
| GET | `/api/pilotage` | Indicateurs du tableau de bord (vue `v_pilotage`) |
| GET, PATCH | `/api/parametres` | Paramètres du projet : nom, préfixe, budget, TVA par défaut |
| GET | `/api/journal` | Dernières lignes du journal, filtrables par `table_cible` et `cle_cible` |
| GET | `/api/historique` | Journal filtré et paginé : `table`, `origine`, `du`, `au`, `texte`, `page`, `taille` |
| GET | `/api/historique/tables` | Tables présentes dans le journal |
| GET | `/api/historique/export` | Classeur Excel du journal filtré |
| GET | `/api/recherche?q=` | Recherche globale, deux caractères au moins |

## Blocs, listes et attributs

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/blocs` | Blocs fonctionnels ; création avec un code de 2 à 4 lettres |
| PATCH | `/api/blocs/{code}` | Modification (nom, ordre, budget cible, archivage…) |
| GET | `/api/blocs/{code}/prochain-id` | Identifiant que recevra le prochain composant du bloc |
| GET | `/api/listes` | Toutes les listes de valeurs paramétrables |
| POST | `/api/listes/{liste}` | Nouvelle valeur dans une liste |
| PATCH, DELETE | `/api/listes/{liste}/{code}` | Renommer, désactiver, supprimer une valeur non système |
| GET, POST | `/api/attributs` | Attributs de composant |
| PATCH | `/api/attributs/{code}` | Libellé, unité, ordre, activation |
| POST | `/api/attributs/{code}/valeurs` | Valeur d'un attribut de type liste |
| PATCH | `/api/attributs/{code}/valeurs/{valeur}` | Libellé, ordre, activation d'une valeur |
| GET | `/api/attributs/{code}/repartition` | Répartition des composants par valeur |
| GET | `/api/attributs/{code}/calcul` | Somme et moyenne d'un attribut numérique |

## Composants

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/composants` | Liste filtrée et triée (voir ci-dessous) |
| GET | `/api/composants/export` | Classeur Excel de la liste filtrée, colonnes choisies par `cols` |
| POST | `/api/composants` | Création ; l'identifiant est attribué par le serveur |
| GET | `/api/composants/{id}` | Fiche complète : composant, attributs, affectations, lignes de commande, mouvements, historique |
| PATCH | `/api/composants/{id}` | Modification |
| DELETE | `/api/composants/{id}` | Archivage |
| POST | `/api/composants/{id}/reclasser` | Reclassement dans un autre bloc (`bloc_code`) |
| PUT | `/api/composants/{id}/attributs` | Valeurs des caractéristiques, `null` efface |

La liste accepte les filtres `q` (texte), `bloc`, `ensemble` (avec ses sous-ensembles,
sauf si `ensemble_seul=true`), `mode_appro`, `statut_appro`, `statut_choix`,
`criticite`, `fournisseur`, `a_chiffrer`, `non_affecte`, `ecart_affectation`, et le tri
`tri` avec `ordre` (`asc` ou `desc`). Le paramètre `attr`, répétable, filtre sur un
attribut : `attr=tension:egal:24`, `attr=materiau:vide`, `attr=materiau:renseigne`,
`attr=tension:entre:12:48`. Le
tri `tri=attr:tension` trie sur un attribut. Un code d'attribut inconnu est refusé.

## Ensembles et affectations

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/ensembles` | Ensembles dans l'ordre de l'arbre, indicateurs propres et cumulés, budgets |
| GET | `/api/ensembles/arbre` | Racine du projet et ensembles, pour les vues Arbre et Schéma |
| GET | `/api/ensembles/repartition` | Répartition par bloc ; `cumul=true` pour inclure les sous-ensembles |
| GET | `/api/ensembles/incoherences` | Écarts entre affectations, commandes et montage |
| POST | `/api/ensembles` | Création, avec parent et budget éventuels |
| GET | `/api/ensembles/{code}` | Un ensemble, avec son chemin depuis la racine et ses enfants |
| PATCH | `/api/ensembles/{code}` | Modification ; cycle ou parent archivé refusés |
| DELETE | `/api/ensembles/{code}` | Archivage, refusé s'il reste des affectations ou des sous-ensembles |
| GET | `/api/ensembles/{code}/copie?nouveau=` | Codes proposés pour les sous-ensembles d'une copie |
| POST | `/api/ensembles/{code}/copie` | Duplication, avec ou sans affectations et sous-ensembles |
| GET | `/api/ensembles/{code}/composants` | Composants affectés directement |
| POST | `/api/ensembles/{code}/affectations` | Affecter un composant avec une quantité |
| PATCH, DELETE | `/api/affectations/{id}` | Modifier la quantité, retirer l'affectation |
| GET | `/api/ensembles/{code}/modele` | Modèle Excel de l'ensemble pour l'équipe |

Verrouiller le budget d'un ensemble se fait par PATCH avec `budget_cible_ht` et
`budget_verrouille: true` ; le déverrouiller avec `budget_verrouille: false`, et
éventuellement `budget_cible_ht: null`.

## Achats et stock

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/commandes` | Commandes et devis, filtrables par `statut` et `fournisseur` ; création |
| GET, PATCH, DELETE | `/api/commandes/{numero}` | Détail, modification, archivage |
| GET, POST | `/api/commandes/{numero}/lignes` | Lignes d'une commande ; ajout |
| PATCH, DELETE | `/api/commandes/{numero}/lignes/{id}` | Modifier, supprimer une ligne sans réception |
| POST | `/api/commandes/{numero}/reception` | Réception, partielle ou complète, avec entrée en stock |
| GET, POST | `/api/demandes-devis` | Composants à commander par fournisseur ; création des demandes |
| GET | `/api/stock` | État du stock |
| GET, POST | `/api/mouvements` | Journal des mouvements ; saisie d'un mouvement |

## Fournisseurs

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/fournisseurs` | Liste ; création |
| GET, PATCH, DELETE | `/api/fournisseurs/{nom}` | Fiche, modification (renommage propagé), archivage |
| POST | `/api/fournisseurs/comparaison` | Compare un classeur Excel déposé à la liste existante |
| POST | `/api/fournisseurs/comparaison/appliquer` | Applique les créations et compléments choisis |

## Documents

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/commandes/{numero}/documents` | Documents d'une commande ; dépôt |
| GET, POST | `/api/composants/{id}/documents` | Documents d'un composant, et ceux de ses commandes ; dépôt |
| GET | `/api/documents/{id}/fichier` | Le fichier, ouvert dans le navigateur ou téléchargé selon son type |
| PATCH, DELETE | `/api/documents/{id}` | Type et commentaire ; retrait (le fichier reste) |

## Imports

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/blocs/{code}/modele` | Modèle Excel d'un bloc |
| GET, POST | `/api/imports` | Dépôts passés ; dépôt et analyse de fichiers |
| GET | `/api/imports/{depot}` | Propositions d'un dépôt |
| POST | `/api/imports/{depot}/appliquer` | Applique les propositions retenues |
| POST | `/api/imports/{depot}/abandonner` | Abandonne le dépôt sans rien appliquer |

## Nettoyage, export et sauvegardes

| Méthode | Chemin | Rôle |
|---|---|---|
| GET, POST | `/api/nettoyage/composants` | Contrôles de qualité ; archivage ou suppression en lot (simulable) |
| GET, POST | `/api/nettoyage/commandes` | Idem pour les commandes et devis |
| GET | `/api/nettoyage/entites` | Blocs, ensembles, fournisseurs supprimables |
| DELETE | `/api/nettoyage/entites/{type}/{cle}` | Suppression physique d'une entité sans trace |
| POST | `/api/nettoyage/journal/purge` | Vide le journal, après sauvegarde |
| POST | `/api/export` | Réécrit tout de suite l'export Excel |
| GET | `/api/export/classeur` | Télécharge l'export Excel complet |
| GET, POST | `/api/sauvegardes` | Liste des sauvegardes ; nouvelle sauvegarde |
| POST | `/api/sauvegardes/{nom}/restaurer` | Restauration, avec accord des fichiers joints |
| GET | `/api/sauvegardes/archive` | Archive complète : base et documents |
| GET | `/api/sauvegardes/corbeille` | Nombre et taille des fichiers de la corbeille |
| POST | `/api/sauvegardes/corbeille/vider` | Efface la corbeille, sauf les fichiers encore nécessaires |
