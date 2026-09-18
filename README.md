# Nomentrace

Nomentrace — nomenclature et traçabilité — est un outil web local de suivi de
nomenclature, d'approvisionnement et de montage pour des projets techniques. L'outil est
générique : chaque instance suit un projet donné, dont le nom est enregistré dans les
paramètres de la base et non dans le code. La première instance suit le projet SPOC.

Chaque composant porte un identifiant stable, et tout ce qui lui arrive — chiffrage,
devis, commande, réception, affectation à un ensemble, montage — reste rattaché à cet
identifiant.

## Lancement

Double-cliquer sur `lancer.bat`. Au premier lancement, le script crée l'environnement
Python `.venv` s'il n'existe pas (Python 3.14 requis) et installe les dépendances. Il
démarre ensuite le serveur sur http://127.0.0.1:8000 et ouvre le navigateur.

Pour arrêter Nomentrace, fermer la fenêtre du script.

L'application est mono-utilisateur, sans authentification, et n'écoute que sur la machine
locale.

## Où sont les données

- `data/nomentrace.db` : la base SQLite, seule source de vérité.
- `echange/exports/` : l'Excel régénéré automatiquement à partir de la base.
- `echange/sauvegardes/` : les sauvegardes de la base.
- `echange/modeles/` et `echange/imports/` : les fichiers échangés avec l'équipe.

Aucun de ces fichiers n'est versionné dans git.

## Dépendances

Listées et épinglées dans `requirements.txt`. Chart.js 4.5.1 est inclus dans
`static/vendor/chart.min.js` : l'application fonctionne sans accès réseau.
