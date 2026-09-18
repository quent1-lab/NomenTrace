# Nomentrace

Nomentrace — nomenclature et traçabilité — est un outil web local de suivi de
nomenclature, d'approvisionnement et de montage pour des projets techniques. Chaque
composant porte un identifiant stable, et tout ce qui lui arrive — chiffrage, devis,
commande, réception, affectation à un ensemble, montage — reste rattaché à cet
identifiant et consultable dans sa fiche.

L'outil est générique : une instance suit un projet, dont le nom, le préfixe
d'identifiant, le budget et le vocabulaire (modes d'appro, criticités…) sont des données
de la base, modifiables dans l'écran Paramètres. La première instance suit le projet SPOC.

Le modèle de données et les définitions de calcul sont décrits dans
[docs/MODELE.md](docs/MODELE.md).

## Lancer et arrêter

**Lancer** : double-cliquer sur `lancer.bat`. Au premier lancement, le script crée
l'environnement Python `.venv` (Python 3.14 requis) et installe les dépendances. Il
démarre ensuite le serveur sur <http://127.0.0.1:8000> et ouvre le navigateur.

À chaque démarrage, Nomentrace sauvegarde la base, applique les éventuelles migrations
de schéma, puis régénère l'export Excel.

**Arrêter** : fermer la fenêtre du script (ou `Ctrl+C` dedans). Fermer l'onglet du
navigateur ne suffit pas : le serveur continue de tourner.

L'application est mono-utilisateur, sans authentification, et n'écoute que sur la
machine locale (127.0.0.1) : elle n'est pas joignable depuis un autre poste.

## Où sont les données

| Emplacement | Contenu |
|---|---|
| `data/nomentrace.db` | La base SQLite, **seule source de vérité**. |
| `echange/exports/nomenclature.xlsx` | L'export Excel, régénéré automatiquement. |
| `echange/sauvegardes/` | Les 20 dernières sauvegardes de la base. |
| `echange/documents/` | Les devis, factures et fiches joints aux commandes et aux composants. |
| `echange/modeles/` | Les modèles Excel à remplir, générés à la demande. |
| `echange/imports/` | Une copie de chaque fichier déposé à l'import. |

Aucun de ces fichiers n'est versionné dans git.

## L'Excel exporté

`echange/exports/nomenclature.xlsx` est réécrit deux secondes environ après chaque
modification, et sur demande (Paramètres › Export et sauvegardes › « Exporter
maintenant »). Il contient une feuille Pilotage (indicateurs), les feuilles Blocs,
Ensembles et Affectations (calculées), puis une feuille brute par table.

C'est une **copie de lecture** : ce qu'on y modifie ne revient jamais dans l'outil et
sera écrasé au prochain export. Pour faire remonter des données de l'équipe, utiliser les
modèles de l'écran Imports.

**« Export Excel en attente »** dans l'en-tête : le fichier est ouvert dans Excel, qui le
verrouille. L'outil réessaie toutes les 30 secondes ; fermer le classeur suffit, rien
n'est perdu (la base, elle, est à jour).

## Sauvegarder et restaurer

Une sauvegarde est prise automatiquement à chaque démarrage et avant chaque restauration ;
les 20 plus récentes sont gardées. On peut en prendre une à tout moment : Paramètres ›
Export et sauvegardes › « Sauvegarder maintenant ».

**Restaurer** : dans la même page, bouton « Restaurer » sur la ligne voulue, puis deux
confirmations. L'état courant est d'abord sauvegardé (il apparaît en tête de liste : on
peut donc annuler une restauration en restaurant cette sauvegarde). Une sauvegarde prise
avec une version plus ancienne de Nomentrace reçoit les migrations manquantes.

**Les sauvegardes ne contiennent que la base.** Les fichiers joints restent dans
`echange/documents/`. Pour une sauvegarde complète hors de la machine (clé USB, disque
réseau), arrêter Nomentrace puis copier :

- `data/nomentrace.db` ;
- le dossier `echange/documents/` en entier.

Restaurer à la main : arrêter Nomentrace, remettre ces deux éléments en place, relancer.

## Problèmes courants

**« le port 8000 est déjà occupé »** au lancement : Nomentrace tourne probablement déjà
dans une autre fenêtre — ouvrir <http://127.0.0.1:8000>. Sinon, un autre programme utilise
ce port : le fermer, ou lancer sur un autre port en modifiant la ligne `set "PORT=8000"`
de `lancer.bat`.

**« Python 3.14 est introuvable »** : installer Python 3.14 depuis python.org, puis
relancer.

## Mettre à jour les dépendances

Les versions sont épinglées dans `requirements.txt`. Pour en changer une :

1. modifier la version dans `requirements.txt` ;
2. relancer `lancer.bat` : il détecte le changement et réinstalle ;
3. vérifier que les tests passent : `.venv\Scripts\python.exe -m pytest`.

Chart.js (4.5.1) est inclus dans `static/vendor/chart.min.js` : l'application fonctionne
sans accès réseau. Pour le mettre à jour, remplacer ce fichier par la version `.umd.min.js`
publiée.

## Repartir pour un autre projet

Une instance suit un seul projet. Pour un nouveau projet :

1. copier le dossier de l'outil ailleurs, **sans** `data/`, `echange/` ni `.venv/` ;
2. supprimer de la copie le fichier de départ `SPOC_base_airtable.xlsx` : sinon il est
   importé au premier démarrage sur une base vide ;
3. lancer `lancer.bat` : la base est créée sans aucune donnée, avec un vocabulaire de
   base dans les listes (valeurs système et quelques statuts génériques, à adapter) ;
4. dans Paramètres › Projet, renseigner le nom du projet, le préfixe des identifiants
   (obligatoire pour créer des composants), le budget et la TVA par défaut ;
5. créer les blocs fonctionnels, puis compléter les listes de valeurs et les
   fournisseurs ;
6. saisir les composants un à un, ou générer un modèle par bloc (écran Imports) et le
   faire remplir.

## Limites connues

- Mono-utilisateur et local : pas de comptes, pas d'accès réseau, pas de travail
  simultané sur deux postes.
- Le code d'un bloc et celui d'un ensemble ne changent jamais après création ; un bloc
  ne se supprime pas.
- Le préfixe d'identifiant ne s'applique qu'aux composants créés ensuite : les
  identifiants existants ne sont jamais renommés.
- Le port des commandes entre dans le montant engagé global, mais n'est pas ventilé par
  bloc : la somme des blocs peut être inférieure au total.
- L'import ne crée pas de blocs : un bloc inconnu dans un fichier est signalé.
- Les sauvegardes automatiques ne couvrent pas les documents joints (voir plus haut).
- L'interface est pensée pour un écran de bureau, pas pour un téléphone.

## Pour les développeurs

```
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format .
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Les variables d'environnement `NOMENTRACE_BASE`, `NOMENTRACE_ECHANGE` et
`NOMENTRACE_IMPORT_INITIAL` déplacent la base, le dossier d'échange et le fichier de
départ (utile pour essayer sans toucher aux vraies données). Les règles du projet sont
dans `docs/MODELE.md`.
