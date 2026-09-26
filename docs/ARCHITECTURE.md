# Architecture technique

Ce document explique comment Nomentrace est construit, pour qui veut le lire, le modifier
ou le faire évoluer. Le modèle de données et les formules de calcul sont dans
[MODELE.md](MODELE.md), la liste des routes dans [API.md](API.md), les règles de
contribution dans [CONTRIBUER.md](CONTRIBUER.md).

## Vue d'ensemble

L'application tient en trois couches et une base.

Le navigateur charge une page unique, `static/index.html`, et des modules JavaScript
natifs, sans framework ni étape de construction. Ces modules appellent une API JSON sous
`/api/`. L'API est servie par FastAPI : des routes minces qui valident la requête avec
Pydantic et appellent un service. Les services portent la logique métier et parlent à
SQLite avec le module `sqlite3` de la bibliothèque standard, en SQL écrit à la main. Les
calculs (quantités à acheter, coûts, avancement, budgets de bloc, indicateurs d'ensemble)
vivent dans des vues SQL.

```
navigateur ──► static/ (HTML, CSS, modules ES)
                   │  fetch, uniquement depuis static/js/api.js
                   ▼
backend/routes/   validation Pydantic, appel d'un service, arrondi de la réponse
                   ▼
backend/services/ logique métier, transactions, journal
                   ▼
SQLite            tables, déclencheurs de contrôle, vues de calcul (backend/migrations/)
```

Le choix est délibérément sobre. Un projet suivi compte quelques centaines de composants
et une poignée d'utilisateurs : SQLite suffit largement, une base est un fichier qu'on
copie, et l'absence d'ORM et de framework front garde le code lisible par une seule
personne. Les dépendances Python se limitent à FastAPI, Uvicorn, Pydantic, openpyxl et
python-multipart ; Chart.js est livré dans `static/vendor/`.

## Organisation du dépôt

| Chemin | Rôle |
|---|---|
| `backend/main.py` | Construction de l'application, démarrage, gestion des erreurs, middleware |
| `backend/config.py` | Chemins et constantes, surchargeables par variables d'environnement |
| `backend/db.py` | Connexion, transactions, helpers de requête, migrations |
| `backend/deps.py` | Dépendances FastAPI : utilisateur de la requête, connexions SQLite, contrôle des droits |
| `backend/securite.py` | Contrôle d'origine des écritures, restriction du mode local, en-têtes de sécurité |
| `backend/comptes.py` | Ligne de commande : premier administrateur et secours |
| `backend/models.py` | Modèles Pydantic des corps de requête |
| `backend/arrondi.py` | Arrondi des montants à la sortie de l'API |
| `backend/erreurs.py` | Exceptions métier (`ErreurMetier`, `Introuvable`, `Conflit`) |
| `backend/routes/` | Une route par fichier de domaine, sans logique ni SQL |
| `backend/services/` | La logique métier, un fichier par domaine |
| `backend/migrations/` | Le schéma, en fichiers SQL numérotés |
| `backend/migrations_comptes/` | Le schéma de la base des comptes |
| `static/js/` | Modules partagés (API, format, routeur, édition, panneau…) |
| `static/js/pages/` | Un module par écran |
| `static/css/style.css` | Toute la feuille de style, écrite à la main |
| `tests/` | Tests pytest et jeu d'essai fictif |
| `lancer.bat` | Lancement Windows en double-clic |

## Le serveur

`create_app()` dans `backend/main.py` construit l'application. Elle reçoit en option le
chemin de la base, du dossier d'échange et de la base des comptes, et le mode (local ou
connecté), ce qui permet aux tests de tout faire tourner sur des fichiers temporaires.
Sans mode local explicite, la connexion est exigée. Au démarrage, la fonction `lifespan`
sauvegarde la base, applique les migrations manquantes, fait de même pour la base des
comptes en mode connecté, puis lance le fil d'export Excel.

## Comptes et droits

Trois dépendances de `deps.py` s'enchaînent sur chaque route. `get_utilisateur` lit le
cookie de session, retrouve la session par l'empreinte du jeton dans la base des comptes
et charge l'utilisateur avec son rôle, ses blocs et ses permissions, relus à chaque
requête ; en mode local, c'est un administrateur implicite. `get_conn` ouvre la connexion
au projet en y attachant le nom de l'utilisateur. `verifier_acces`, posée sur tous les
routeurs par `create_app()`, applique la règle de la route demandée, prise dans la table
`REGLES` de `services/droits.py` par méthode et chemin. Une route absente de la table
n'est ouverte qu'à l'administrateur, et un test vérifie que chaque route y figure.

Certaines règles ont besoin du corps de la requête : le bloc d'un composant créé, le
composant d'une affectation, les champs de budget d'un ensemble, le statut d'un
fournisseur. La table les déclare alors au niveau « écriture » et la route appelle la
vérification fine de `droits` avant le service. L'import applique la même logique ligne
par ligne : une ligne hors des droits de l'utilisateur est refusée et signalée, les autres
s'appliquent.

Les mots de passe (scrypt) et les sessions sont dans `services/authentification.py`, les
comptes et les invitations dans `services/comptes.py`. Les sessions vivent dans la base
des comptes plutôt que dans un cookie signé : la déconnexion, la désactivation d'un compte
ou un nouveau lien les ferment vraiment, et aucun secret de signature n'est à gérer. Les
échecs de connexion sont comptés en mémoire, par identifiant et par adresse IP, ce qui
suppose un seul processus. Comme toutes les routes tournent dans un pool de fils fixe et
que scrypt est lent à dessein, la connexion et l'invitation passent par
`authentification.limiter_connexions()` : au-delà de six traitements simultanés, la requête
est refusée aussitôt au lieu d'occuper un fil, sans quoi une rafale gèlerait l'application
(voir [SECURITE.md](SECURITE.md)).

`securite.py` installe un middleware qui s'exécute avant tous les autres. Il refuse une
écriture dont l'en-tête `Origin` ne désigne pas le serveur lui-même, et, en mode local,
toute requête qui ne vient pas du poste ou n'est pas adressée à `127.0.0.1` ou
`localhost`. Il ajoute à chaque réponse une politique de sécurité du contenu (scripts et
styles de l'outil seulement, aucun cadre), `X-Content-Type-Options: nosniff`, et
`Cache-Control: no-store` sur l'API.

Un middleware fait deux choses. Toute écriture réussie sur l'API (POST, PATCH, PUT, DELETE
avec un statut inférieur à 400) signale au planificateur qu'un export est à refaire. Les
fichiers statiques sont servis avec `Cache-Control: no-cache`, pour qu'un navigateur ne
garde pas d'anciens modules après une mise à jour.

Les erreurs sont toutes traduites en une réponse `{"erreur": "message en français"}`, sans
trace Python. Une `ErreurMetier` porte son propre code HTTP (400 par défaut, 404 pour
`Introuvable`, 409 pour `Conflit`). Les erreurs de validation Pydantic donnent un 422 au
message traduit champ par champ. Une contrainte SQLite refusée donne un 409. Toute autre
exception est journalisée avec sa trace et renvoie un 500 générique.

Chaque requête ouvre sa propre connexion SQLite (`deps.get_conn`) et la ferme à la fin. La
connexion est en autocommit : les transactions s'ouvrent explicitement avec
`db.transaction(conn)`, qui prend le verrou d'écriture dès l'ouverture (`BEGIN IMMEDIATE`)
et annule tout en cas d'exception. `PRAGMA foreign_keys = ON`, `journal_mode = WAL` et
`busy_timeout = 5000` sont posés à chaque ouverture : deux écritures simultanées
s'attendent au plus cinq secondes au lieu d'échouer.

## Routes et services

Une route ne fait que trois choses : valider le corps avec un modèle Pydantic à champs
fermés (`extra="forbid"`), appeler un service, arrondir la réponse. Tout le reste est dans
les services.

| Service | Domaine |
|---|---|
| `composants`, `reclassement` | Composants, identifiants, fiche, reclassement dans un autre bloc |
| `attributs`, `attributs_requetes`, `attributs_analyse` | Caractéristiques paramétrables, filtres et tris sur attribut, écran d'analyse |
| `blocs`, `parametres`, `listes` | Blocs fonctionnels, paramètres du projet, listes de valeurs |
| `ensembles`, `ensembles_arbre`, `ensembles_copie` | Ensembles et affectations, arborescence et budgets, duplication |
| `commandes`, `receptions`, `mouvements`, `demandes_devis` | Achats, réceptions, stock, préparation des demandes de devis |
| `fournisseurs`, `fournisseurs_liste` | Fournisseurs, comparaison avec une liste Excel |
| `documents`, `corbeille` | Fichiers joints, corbeille et accord des fichiers après restauration |
| `import_lecture`, `import_colonnes`, `import_analyse`, `import_doublons`, `import_application`, `import_depots`, `modeles` | Travail en équipe par Excel |
| `export_excel`, `export_composants` | Export complet automatique, export de la liste filtrée |
| `pilotage`, `sante` | Tableau de bord, état du serveur |
| `historique`, `journal` | Frise d'un composant, journal global, écriture journalisée |
| `recherche` | Recherche globale |
| `authentification`, `comptes`, `droits` | Mots de passe et sessions, comptes et invitations, table des droits et vérifications |
| `tableur` | Outils communs aux classeurs produits (aucune cellule exportée n'est une formule) |
| `nettoyage`, `suppressions`, `sauvegardes` | Contrôles de qualité, suppressions physiques, sauvegardes et archive |

Une fonction de service dépasse rarement cinquante lignes. Quand elle grossit, on la
découpe ; plusieurs domaines sont déjà répartis sur plusieurs fichiers pour cette raison.

## Les calculs

La règle est de calculer dans la base. `v_composant` produit, pour chaque composant, la
quantité à acheter, le PU HT, le total, les quantités commandées et reçues, le stock,
l'avancement. Les autres vues s'appuient sur elle : `v_bloc`, `v_ensemble`,
`v_ensemble_cumul`, `v_commande`, `v_pilotage`… Aucune vue n'arrondit. L'arrondi à deux
décimales se fait une seule fois, par `round_output()` au moment de renvoyer la réponse,
ou dans l'export. Arrondir un PU HT avant de le multiplier fausse les totaux de quelques
centimes, et c'est exactement ce que les tests vérifient sur le jeu d'essai.

Trois calculs font exception et vivent en Python, parce qu'ils s'expriment mal en SQL : la
répartition récursive des budgets d'ensemble (`ensembles_arbre`), l'assemblage de la frise
d'un composant (`historique`) et la détection des doublons à l'import
(`import_doublons`, qui compare des libellés). Ils ne stockent rien et sont recalculés à
chaque lecture.

Deux montants ne se comparent jamais avec `==` : on tolère 0,01 €.

## Le journal

Toute modification passe par `journal.write_journal()` ou `journal.update_with_journal()`.
La seconde compare champ par champ l'état actuel et les valeurs demandées, n'écrit que ce
qui change réellement, et laisse une ligne de journal par champ modifié avec l'ancienne et
la nouvelle valeur. Chaque ligne porte l'horodatage local, la table et la clé concernées,
l'origine (`interface` ou `import`), l'auteur et, pour un import, le lot qui l'a produite.
L'auteur n'est pas passé en paramètre : `write_journal()` le lit sur la connexion
(`db.auteur(conn)`), où `get_conn` l'a posé.

Certaines clés sont composées, et la frise d'un composant s'appuie sur ces formats :

| Table journalisée | Clé | Exemple |
|---|---|---|
| `affectation` | `ENSEMBLE:COMPOSANT` | `CHASSIS:ROB-ALI-003` |
| `composant_attribut` | `COMPOSANT:ATTRIBUT` | `ROB-ALI-003:tension` |
| `valeur_liste` | `LISTE:CODE` | `criticite:Bloquant` |
| `commande`, champ `ligne N` | numéro de commande, valeur = composant | `CMD-004` |
| `commande` ou `composant`, champ `document N` | cible, valeur = nom du fichier | `CMD-004` |

Une suppression physique écrit une ligne au champ `suppression`, dont l'ancienne valeur est
un résumé JSON de ce qui a été supprimé. Le journal se lit dans la fiche d'un composant et
dans Paramètres › Historique.

## Le schéma et ses migrations

Le schéma est construit par les fichiers `backend/migrations/NNN_nom.sql`, appliqués dans
l'ordre au démarrage, chacun dans sa propre transaction avec l'enregistrement de son numéro
dans `schema_version`. Une migration appliquée n'est jamais modifiée : toute évolution est
un nouveau fichier.

Une migration qui reconstruit une table (SQLite ne sait pas tout faire par `ALTER TABLE`)
commence par la ligne `-- nomentrace: reconstruction`. Les clés étrangères sont alors
suspendues le temps du script, puis vérifiées avant la validation. Elle doit supprimer et
recréer les vues qui dépendent de la table.

Les valeurs des listes paramétrables sont contrôlées par des déclencheurs qui refusent une
valeur absente de `valeur_liste`. Les listes figées (statuts de commande, de ligne, de
montage, base de prix, sens d'un mouvement) sont des contraintes `CHECK`. Une expression
`WITH` est interdite dans un déclencheur SQLite : c'est pourquoi le refus des cycles dans
l'arbre des ensembles est fait par le service, la base ne refusant que le cas d'un
ensemble parent de lui-même.

## Les fichiers

Les documents joints sont écrits sous `echange/documents/commandes/<numéro>/` ou
`echange/documents/composants/<identifiant>/`, sous un nom nettoyé, avec leur taille et
leur empreinte SHA-256 en base. Un même fichier ne peut pas être joint deux fois à la même
cible. Retirer un document l'archive, le fichier reste. Seule la suppression d'une
commande supprime des fiches de document ; leurs fichiers partent alors dans
`_corbeille/`, nommés `<empreinte>_<nom>`. Après une restauration,
`corbeille.verifier_documents()` compare la base et le disque, remet en place ce qui
manque et range ce qui est de trop.

L'export Excel complet est confié à `PlanificateurExport`, un fil unique qui attend deux
secondes de calme après la dernière écriture avant d'exporter, pour ne pas réécrire le
classeur à chaque frappe. Si le fichier est verrouillé par Excel, il réessaie toutes les
trente secondes. L'écriture passe par un fichier temporaire renommé à la fin.

## L'import Excel

Le travail en équipe par Excel passe par quatre étapes, chacune dans son service.
`modeles` génère un classeur par bloc ou par ensemble, avec les valeurs actuelles et des
listes déroulantes. `import_lecture` lit un classeur déposé et reconnaît ses colonnes
(`import_colonnes`). `import_analyse` compare chaque ligne à la base et la classe
(nouveau, modifié, identique, doublon, affectation, entité inconnue, invalide) ; il
n'écrit que dans `import_lot` et `import_ligne`. `import_application` applique ce que
l'utilisateur a retenu, en une transaction, après une sauvegarde, et refuse une ligne dont
un champ a changé en base depuis l'analyse.

## L'interface

Le front est fait de modules ES natifs chargés directement par le navigateur. Quelques
règles le structurent.

Tous les appels réseau passent par `static/js/api.js` ; aucun `fetch` ailleurs. Une erreur
de l'API y devient une exception `ErreurApi` dont le message est celui du serveur, affiché
dans le bandeau d'erreur par `ui.afficherErreur()`.

Le routage se fait par le hash de l'adresse (`#/composants?bloc=ALI`), dans
`router.js`. `app.js` associe chaque chemin à la fonction d'affichage d'une page de
`static/js/pages/`. Une page reçoit un conteneur et les paramètres de l'adresse, et
reconstruit son contenu ; l'état qui mérite d'être partagé (filtres, tri, fiche ouverte,
onglet) est écrit dans l'adresse par `remplacerRoute()`.

Les éléments se construisent avec `el(balise, attributs, ...enfants)` de `ui.js`, sans
gabarit HTML. `format.js` centralise le format français : espace fine insécable comme
séparateur de milliers, virgule décimale, euro après le nombre, dates JJ/MM/AAAA, libellés
accentués des valeurs stockées sans accents. `edition.js` gère l'édition d'une cellule sur
place, `panneau.js` le panneau latéral unique, `formulaire.js` les champs et la lecture
d'un formulaire.

`session.js` charge une fois l'utilisateur connecté (`GET /api/session`) avant le premier
affichage. Il pose sur `body` des classes (`peut-ecrire`, `est-admin`, `peut-achats`,
`peut-ensembles`) qui masquent par CSS les éléments marqués `si-ecriture`, `si-admin`,
`si-achats` ou `si-ensembles`, et fournit `ecritBloc()` pour ce qui dépend du bloc d'un
composant. Masquer n'est qu'un confort : le serveur refuse de toute façon. Une réponse 401
ramène à `connexion.html`, page à part qui sert aussi à choisir son mot de passe depuis
un lien d'invitation (le jeton est placé après `#`, donc jamais envoyé au serveur ni
écrit dans ses journaux). Une adresse saisie par un utilisateur ne devient un lien que si
elle est en http ou https (`ui.lienExterne()`).

La base fait foi : aucune donnée métier n'est gardée dans le navigateur. `localStorage` ne
sert qu'à retenir l'état du menu latéral. Le CSS est un seul fichier, dont les couleurs et
les espacements sont des variables, et le HTML ne porte pas de style en ligne.

## Les tests

`pytest` couvre la logique métier : calculs, conversions HT et TTC, écarts d'affectation,
moteur d'import, identifiants, arborescence et budgets, historique, sauvegardes et
corbeille. Il n'y a pas de test d'interface. Chaque test travaille sur une base temporaire
créée par les fixtures de `tests/conftest.py`, jamais sur `data/`.

Les fixtures `client` et `client_essai` lancent l'application en mode local, avec les
en-têtes d'un navigateur du poste. `tests/test_comptes.py` la lance en mode connecté pour
éprouver la connexion, les invitations, chaque rôle sur chaque famille de routes, le
contrôle d'origine et les en-têtes ; le coût de scrypt y est abaissé pour la vitesse.

Les tests qui ont besoin d'une base remplie utilisent `tests/jeu_essai.py` : un projet de
robot fictif de soixante composants répartis en neuf blocs, dont le total estimé vaut
3 184,98 € HT pour un budget de 3 000 €. Les fixtures `conn_essai` et `client_essai`
donnent une connexion ou un client HTTP sur cette base. Ce jeu n'est jamais chargé par
l'application.

## Ajouter une fonctionnalité

Le chemin habituel, du bas vers le haut :

1. Si le schéma change, écrire une nouvelle migration numérotée, et mettre à jour
   [MODELE.md](MODELE.md).
2. Écrire le calcul dans une vue si c'est possible, sans arrondi.
3. Écrire le service : transaction explicite, journal de chaque modification, erreurs
   métier en français.
4. Ajouter le modèle Pydantic du corps de requête et la route, qui arrondit sa réponse,
   puis sa règle d'accès dans `REGLES` (`services/droits.py`).
5. Écrire les tests pytest, sur le jeu d'essai si une base remplie est utile.
6. Ajouter l'appel dans `api.js`, puis l'écran ou la section dans `static/js/pages/`.
7. Vérifier `ruff check`, `ruff format` et `pytest`.

## Pour les évolutions prévues

L'hébergement et le multi-projet sont décrits dans
[FEUILLE_DE_ROUTE.md](FEUILLE_DE_ROUTE.md).

Une connexion par un compte externe (Microsoft, GitHub) s'ajoutera comme un fournisseur de
plus dans la table `identite`, rattaché à un utilisateur existant : le reste des comptes
et des droits n'en dépend pas.

SQLite en mode WAL supporte bien une quinzaine d'utilisateurs, à condition que les
écritures restent courtes, ce qu'elles sont. Le planificateur d'export est un fil unique
dans le processus : l'application doit tourner en un seul processus Uvicorn, sans
plusieurs workers.

Pour héberger plusieurs projets sur un même serveur, la piste retenue est une base par
projet, avec son dossier d'échange, plutôt qu'une colonne de projet dans chaque table. Le
code reste mono-base, et aucune donnée ne peut passer d'un projet à l'autre par un filtre
oublié. Il faudra choisir la base selon le projet demandé (c'est `get_conn` qui s'en
chargera) et appliquer les migrations à chaque base. Les comptes sont déjà dans une base
commune où les rôles sont attribués projet par projet (`acces.projet`).
