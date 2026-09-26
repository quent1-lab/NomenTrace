# Contribuer

Nomentrace est un logiciel libre sous licence AGPL-3.0. On peut le cloner pour son propre
projet, l'adapter, proposer des corrections. Ce document rassemble les règles que le code
suit aujourd'hui ; une contribution qui les respecte s'intègre sans friction.

## Préparer son poste

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Sous Linux ou macOS, remplacer `.venv\Scripts\python.exe` par `.venv/bin/python` dans
cette commande et les suivantes. Python 3.14 est requis.

Pour travailler sans toucher à ses vraies données, on lance un serveur sur une base et un
dossier d'échange à part :

```
set NOMENTRACE_BASE=C:\temp\essai\nomentrace.db
set NOMENTRACE_ECHANGE=C:\temp\essai\echange
set NOMENTRACE_PORT=8765
.venv\Scripts\python.exe -m backend
```

Une base neuve démarre vide. Pour disposer de données, on peut charger le jeu d'essai des
tests dans cette base depuis un petit script : `tests.jeu_essai.charger_jeu_essai(conn)`
après `backend.db.apply_migrations(conn)`.

## Vérifier avant de proposer

```
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format .
```

Les trois doivent passer. Ruff est réglé dans `pyproject.toml` : lignes de 100 caractères,
cible Python 3.14. Il n'y a pas d'outil de lint pour le JavaScript ; le code suit le style
des modules existants.

L'intégration continue de GitHub (`.github/workflows/tests.yml`) refait ces contrôles sous
Linux à chaque envoi, et passe les scripts de `deploiement/` à `shellcheck`. Une version
ne se publie, par une étiquette `v…`, qu'une fois ce passage au vert : les serveurs qui
suivent les étiquettes l'installent d'eux-mêmes.

## Langue et nommage

Le code parle français, sans accents ni caractères spéciaux : tables, colonnes, fonctions
et variables s'appellent `composant`, `ensemble`, `qte_besoin`, `pu_ht`, `mode_appro`. Les
verbes techniques restent en anglais : `list_composants`, `create_affectation`,
`patch_ensemble`. Les commentaires, les docstrings, les messages d'erreur et l'interface
sont en français accentué.

Les valeurs énumérées sont stockées sans accents (`Recu`, `Non lance`) et affichées
accentuées : par le libellé de `valeur_liste` pour les listes paramétrables, par la table
de `static/js/format.js` pour les listes figées.

Trois mots ne se remplacent jamais l'un par l'autre, ni dans le code ni dans l'interface.
Le bloc est le découpage fonctionnel, un seul par composant, figé dans l'identifiant.
L'ensemble est le découpage physique. L'affectation est le lien entre un composant et un
ensemble, avec sa quantité.

Rien de propre à un projet particulier n'est écrit dans le code : ni nom de projet, ni
préfixe d'identifiant, ni vocabulaire de liste. Ce sont des données. Les tests utilisent un
projet fictif.

## Python

Toute signature publique porte ses annotations de type, retour compris. Pas d'ORM :
`sqlite3`, SQL écrit à la main, `row_factory = sqlite3.Row`. Pydantic sert à valider les
corps de requête, jamais à persister.

Toute requête SQL utilise des paramètres liés. Aucune valeur n'est interpolée dans du SQL,
sans exception. Seul un nom de table ou de colonne peut l'être, et seulement après
validation contre une liste écrite en dur dans le code (c'est ce que font
`journal.CLES_PRIMAIRES` et les listes de colonnes triables). Ruff signale les
constructions suspectes (règle S608).

Pas de `except` nu. Une exception attrapée l'est par son type et journalisée avec le
module `logging`. Un refus métier lève une `ErreurMetier` (ou `Introuvable`, `Conflit`)
avec un message en français, que l'application transforme en réponse JSON.

Les routes ne contiennent ni logique ni SQL. Les services ouvrent leurs transactions
explicitement avec `db.transaction(conn)` et journalisent chaque modification par
`journal.update_with_journal()`. `backend/db.py` ne contient que la connexion, les
migrations et les helpers de requête.

Toute nouvelle route reçoit sa règle d'accès dans la table `REGLES` de
`backend/services/droits.py`. Oubliée, elle serait réservée à l'administrateur, et le test
`test_toutes_les_routes_ont_une_regle` échouerait. Une vérification qui dépend du corps de
la requête (le bloc d'un composant créé, par exemple) se fait dans la route, par une
fonction de `droits`, avant l'appel au service ; l'interface masque en plus ce qui est
interdit, mais ce n'est jamais la protection. Aucune dépendance ne s'ajoute hors de
`requirements.txt`, et tout ajout se justifie.

## Base de données

Une évolution de schéma est un nouveau fichier `backend/migrations/NNN_nom.sql`. Une
migration déjà publiée n'est jamais modifiée. Une migration qui reconstruit une table
commence par `-- nomentrace: reconstruction` et recrée les vues qui en dépendent.

Composants, blocs, ensembles, commandes et fournisseurs s'archivent ; ils portent une
colonne `archive` filtrée en lecture. La suppression physique est réservée à ce qui n'a
laissé aucune trace et passe par `backend/services/suppressions.py`, qui prend une
sauvegarde, travaille en transaction et laisse une ligne de journal. Un fichier joint
n'est jamais effacé : il part dans la corbeille.

Les calculs vivent dans des vues SQL dès que c'est possible, sans aucun arrondi. Un calcul
fait en Python est une exception, signalée dans [MODELE.md](MODELE.md).

## Montants et dates

Les montants sont des REAL en euros. On arrondit à deux décimales une seule fois, à la
sortie de l'API (`round_output`) ou dans un export ; jamais dans une vue, jamais avant une
multiplication. Deux montants ne se comparent pas avec `==` mais à 0,01 près. Le budget et
les prix de référence sont hors taxes ; le TTC est toujours calculé, jamais saisi. Les
taux de TVA sont des fractions.

Les dates sont stockées en texte `AAAA-MM-JJ` et affichées `JJ/MM/AAAA`, la conversion se
faisant côté navigateur. Les horodatages sont en heure locale, à la seconde.

Toute division par zéro (budget nul, rien à acheter) renvoie NULL, affiché « — », jamais
zéro.

## Interface

JavaScript en modules ES natifs, sans étape de construction, sans npm, sans framework, sans
script chargé depuis un autre domaine. Une bibliothèque tierce se place dans
`static/vendor/`, comme Chart.js. Tous les appels au serveur passent par
`static/js/api.js`, tout le formatage des nombres et des dates par `static/js/format.js`.

Le CSS s'écrit dans `static/css/style.css`, avec des variables pour les couleurs et les
espacements, sans style en ligne dans le HTML. La politique de sécurité du contenu interdit
d'ailleurs tout script ou style en ligne. Un texte saisi par un utilisateur s'affiche par
`el()`, jamais par `innerHTML`, et une adresse saisie ne devient un lien que par
`ui.lienExterne()`. Aucune donnée métier n'est gardée dans
`localStorage`. Une erreur s'affiche dans le bandeau visible, pas seulement dans la
console.

## Tests

Les tests portent sur la logique métier, pas sur l'interface. Chacun travaille sur une base
temporaire, jamais sur `data/`. Ceux qui ont besoin d'une base remplie utilisent le jeu
d'essai fictif `tests/jeu_essai.py` par les fixtures `conn_essai` et `client_essai` ; les
autres construisent leurs propres lignes.

Un bug corrigé s'accompagne d'un test qui échouait avant le correctif.

Une formule qui ne donne pas le chiffre attendu ne s'ajuste pas pour le faire tomber : on
cherche pourquoi, et si la définition est en cause, on la discute avant de la changer.

## Commits

Un commit décrit en français ce qu'il change, au présent ou sous forme de titre. Le dépôt ne
contient ni base, ni sauvegarde, ni export, ni document joint : `.gitignore` les exclut, et
il faut veiller à ne pas les forcer.

## Documentation

Une modification visible par l'utilisateur met à jour [UTILISATION.md](UTILISATION.md). Un
changement de schéma, de vue ou de formule met à jour [MODELE.md](MODELE.md). Une nouvelle
route va dans [API.md](API.md).
