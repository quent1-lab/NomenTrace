# Nomentrace

**Nomenclature et traçabilité des composants d'un projet technique.**

Nomentrace est une petite application web, installée sur votre poste, pour suivre la
nomenclature d'un projet (robot, machine, prototype…) : ce qu'il faut acheter, à quel
prix, chez qui, ce qui a été commandé, reçu, affecté et monté. Chaque composant porte un
identifiant stable, et tout ce qui lui arrive — chiffrage, devis, commande, réception,
affectation à un ensemble, montage — reste rattaché à cet identifiant et consultable dans
sa fiche.

L'outil est générique : le nom du projet, le préfixe des identifiants, le budget, le
vocabulaire (modes d'approvisionnement, criticités…) et les fournisseurs sont des données,
saisies dans l'écran Paramètres. Un dépôt cloné démarre sur une base vide.

*A self-hosted web app to track a hardware project's bill of materials, purchasing and
assembly. The interface and documentation are in French.*

## Ce que fait l'outil

- **Tableau de bord** : coût estimé, montant engagé, reste à engager face au budget,
  avancement des achats, alertes (composants à chiffrer, commandes en retard, bloquants
  non commandés, fournisseurs à valider).
- **Composants** : tableau filtrable et triable, modifiable sur place, fiche détaillée avec
  l'historique de chaque changement et les documents joints.
- **Deux découpages** : le *bloc fonctionnel* (à quoi sert le composant, un seul, figé dans
  l'identifiant) et l'*ensemble* physique (où il est monté, plusieurs possibles, avec une
  quantité). Voir [docs/MODELE.md](docs/MODELE.md).
- **Achats** : devis et commandes, réceptions partielles, stock, montage dans les
  ensembles, devis et factures joints.
- **Fournisseurs** : fiche avec contact et numéro de compte, comparaison avec une liste de
  fournisseurs de référence, fournisseurs proposés par l'équipe à valider.
- **Travail en équipe par Excel** : l'outil génère un modèle par bloc ou par ensemble ;
  l'équipe le remplit, on le redépose, et chaque différence est présentée pour être
  acceptée ou refusée (nouveaux composants, doublons probables, modifications).
- **Export Excel** de toute la base, réécrit automatiquement après chaque modification.
- **Sauvegardes** automatiques et restauration depuis l'interface.

## Prérequis

- **Python 3.14** ([python.org](https://www.python.org/downloads/)).
- Un navigateur récent. Aucun accès Internet n'est nécessaire à l'usage.
- Windows pour le lancement en double-clic ; Linux et macOS fonctionnent en ligne de
  commande (voir plus bas).

## Installation et lancement

```
git clone <adresse du dépôt> nomentrace
cd nomentrace
```

**Windows** : double-cliquer sur `lancer.bat`. Au premier lancement, le script crée
l'environnement Python `.venv` et installe les dépendances. Il démarre ensuite le serveur
sur <http://127.0.0.1:8000> et ouvre le navigateur.

**Linux / macOS** :

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

puis ouvrir <http://127.0.0.1:8000>.

À chaque démarrage, Nomentrace sauvegarde la base, applique les éventuelles mises à jour
de schéma, puis régénère l'export Excel.

**Arrêter** : fermer la fenêtre du script (ou `Ctrl+C` dans le terminal). Fermer l'onglet
du navigateur ne suffit pas : le serveur continue de tourner.

## Premiers pas

La base est créée vide au premier lancement, avec seulement un vocabulaire de départ dans
les listes (à adapter).

1. **Paramètres › Projet** : nom du projet, préfixe des identifiants (par exemple `ROB`,
   obligatoire pour créer des composants), budget HT et taux de TVA par défaut.
2. **Paramètres › Blocs fonctionnels** : créer les blocs, chacun avec un code de 2 à 4
   lettres (`ALI` pour l'alimentation…). Les composants s'appelleront `ROB-ALI-001`,
   `ROB-ALI-002`…
3. **Paramètres › Fournisseurs** et **Listes de valeurs** : compléter selon le projet. Une
   liste de fournisseurs existante (classeur Excel) peut être importée par « Comparer avec
   une liste… ».
4. **Composants** : saisir les composants un à un, ou générer un modèle Excel par bloc
   (écran **Imports**), le faire remplir par l'équipe, puis le déposer.
5. **Ensembles** : créer les ensembles physiques et y affecter les composants.

## Où sont les données

| Emplacement | Contenu |
|---|---|
| `data/nomentrace.db` | La base SQLite, **seule source de vérité**. |
| `echange/exports/nomenclature.xlsx` | L'export Excel, régénéré automatiquement. |
| `echange/sauvegardes/` | Les 20 dernières sauvegardes de la base. |
| `echange/documents/` | Les devis, factures et fiches joints aux commandes et aux composants. |
| `echange/modeles/` | Les modèles Excel à remplir, générés à la demande. |
| `echange/imports/` | Une copie de chaque fichier déposé à l'import. |

Aucun de ces fichiers n'est versionné : vos données restent sur votre poste.

## L'Excel exporté

`echange/exports/nomenclature.xlsx` est réécrit environ deux secondes après chaque
modification, et sur demande (Paramètres › Export et sauvegardes). Il contient une feuille
Pilotage, les feuilles Blocs, Ensembles et Affectations, puis une feuille brute par table.

C'est une **copie de lecture** : ce qu'on y modifie ne revient jamais dans l'outil et sera
écrasé au prochain export. Pour faire remonter des données de l'équipe, utiliser les
modèles de l'écran Imports.

**« Export Excel en attente »** dans l'en-tête : le fichier est ouvert dans Excel, qui le
verrouille. L'outil réessaie toutes les 30 secondes ; fermer le classeur suffit, rien
n'est perdu.

## Sauvegarder et restaurer

Une sauvegarde est prise à chaque démarrage et avant chaque restauration ; les 20 plus
récentes sont gardées. On peut en prendre une à tout moment dans Paramètres › Export et
sauvegardes.

**Restaurer** : même écran, bouton « Restaurer » sur la ligne voulue, puis deux
confirmations. L'état courant est d'abord sauvegardé : on peut donc annuler une
restauration. Une sauvegarde prise avec une version plus ancienne de Nomentrace reçoit les
mises à jour de schéma manquantes.

**Les sauvegardes ne contiennent que la base.** Pour une sauvegarde complète hors de la
machine, arrêter Nomentrace puis copier `data/nomentrace.db` et le dossier
`echange/documents/`. Restaurer à la main : arrêter, remettre ces deux éléments en place,
relancer.

## Mettre à jour

```
git pull
```

puis relancer. `lancer.bat` réinstalle les dépendances si `requirements.txt` a changé
(sous Linux / macOS, relancer `pip install -r requirements.txt`). La base est mise à jour
automatiquement au démarrage, après une sauvegarde.

## Problèmes courants

**« le port 8000 est déjà occupé »** : Nomentrace tourne probablement déjà dans une autre
fenêtre — ouvrir <http://127.0.0.1:8000>. Sinon, fermer le programme qui utilise ce port,
ou changer la ligne `set "PORT=8000"` de `lancer.bat`.

**« Python 3.14 est introuvable »** : installer Python 3.14, puis relancer.

## Limites actuelles

- **Mono-utilisateur et local** : pas de comptes ni d'authentification, écoute sur
  127.0.0.1 uniquement. **Ne pas exposer l'application sur un réseau** en l'état.
- Le code d'un bloc et celui d'un ensemble ne changent jamais après création ; le préfixe
  d'identifiant ne s'applique qu'aux composants créés ensuite.
- Le port des commandes compte dans le montant engagé global, mais n'est pas réparti entre
  les blocs.
- L'import par modèle Excel ne crée pas de blocs.
- Interface pensée pour un écran d'ordinateur, pas pour un téléphone.

## Développement

```
.venv\Scripts\python.exe -m pytest          # tests (base temporaire, jamais data/)
.venv\Scripts\python.exe -m ruff check .    # lint
.venv\Scripts\python.exe -m ruff format .   # formatage
```

Sous Linux / macOS, remplacer `.venv\Scripts\python.exe` par `.venv/bin/python`.

- **Backend** : FastAPI et `sqlite3` sans ORM (`backend/`) ; les calculs vivent dans des
  vues SQL, les évolutions de schéma dans des migrations numérotées
  (`backend/migrations/`).
- **Front** : JavaScript sans framework ni étape de build (`static/`) ; Chart.js est inclus
  dans `static/vendor/`.
- **Tests** : pytest ; les tests qui ont besoin d'une base remplie utilisent un projet
  fictif (`tests/jeu_essai.py`).
- Les variables d'environnement `NOMENTRACE_BASE` et `NOMENTRACE_ECHANGE` déplacent la base
  et le dossier d'échange (pratique pour essayer sans toucher à ses données).
- Le modèle de données, les valeurs autorisées et les définitions de calcul sont décrits
  dans [docs/MODELE.md](docs/MODELE.md).

## Licence

Nomentrace est un logiciel libre, distribué sous la licence
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only).
Copyright © 2026 Quentin Cunha.

En résumé : vous pouvez utiliser, étudier, modifier et redistribuer Nomentrace, y compris
dans un cadre commercial. Si vous distribuez une version modifiée, **ou si vous la mettez à
disposition d'autres personnes à travers un réseau** (par exemple hébergée sur un
serveur), vous devez en fournir le code source complet à ses utilisateurs, sous la même
licence. Le texte de la licence fait foi.

Les données que vous saisissez dans l'outil (base, exports, documents) vous appartiennent :
la licence porte sur le code, pas sur elles. Les bibliothèques utilisées (FastAPI,
Uvicorn, Pydantic, openpyxl, Chart.js…) gardent leurs propres licences, compatibles.
