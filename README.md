# Nomentrace

Nomenclature et traçabilité des composants d'un projet technique.

Nomentrace suit la nomenclature d'un projet (un robot, une machine, un prototype) : ce
qu'il faut acheter, à quel prix, chez qui, ce qui a été commandé, reçu, rangé dans quelle
partie de l'ensemble et monté. Chaque composant porte un identifiant stable, par exemple
`ROB-ALI-003`, et tout ce qui lui arrive reste rattaché à cet identifiant : on retrouve
dans sa fiche le devis où il figure, la commande, la réception, le montage, le document
joint, et qui a changé quoi.

L'outil est générique. Le nom du projet, le préfixe des identifiants, le budget, le
vocabulaire (modes d'approvisionnement, criticités, statuts) et les fournisseurs sont des
données saisies dans l'écran Paramètres. Un dépôt cloné démarre sur une base vide.

*A self-hosted web app to track a hardware project's bill of materials, purchasing and
assembly. The interface and documentation are in French.*

## Ce que fait l'outil

La nomenclature se tient dans un tableau filtrable, modifiable sur place, exportable en
Excel, avec des caractéristiques libres (tension, matériau…) qu'on crée soi-même. Chaque
composant appartient à un bloc fonctionnel, qui porte un budget, et peut être monté dans
plusieurs ensembles physiques, rangés en arbre sous le projet ; le budget du projet se
répartit dans cet arbre, avec des montants verrouillables.

Côté achats, l'outil prépare les demandes de devis par fournisseur à partir de ce qu'il
reste à commander, suit les devis et les commandes jusqu'à la réception partielle ou
complète, tient le stock et le montage. Le tableau de bord confronte le coût estimé et le
montant engagé au budget, et signale ce qui coince : composants à chiffrer, commandes en
retard, composants bloquants pas encore commandés.

Pour travailler avec une équipe qui n'ouvre pas l'outil, Nomentrace génère des modèles
Excel par bloc ou par ensemble, puis présente chaque différence du fichier rempli pour
qu'on l'accepte ou la refuse, doublons probables compris. L'historique de toutes les
modifications se consulte par composant ou pour tout le projet, et une recherche globale
(Ctrl+F) trouve composants, commandes, fournisseurs et ensembles.

La base est sauvegardée automatiquement, et un fichier joint n'est jamais effacé : il
passe par une corbeille d'où une restauration le ramène.

## Démarrer

Il faut Python 3.14 et un navigateur récent ; aucun accès Internet n'est nécessaire.

```
git clone https://github.com/quent1-lab/NomenTrace.git nomentrace
cd nomentrace
```

Sous Windows, double-cliquer sur `lancer.bat` : le script prépare l'environnement au
premier lancement, démarre le serveur et ouvre <http://127.0.0.1:8000>. Sous Linux ou
macOS :

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m backend
```

Dans l'outil, commencer par Paramètres › Projet (nom, préfixe des identifiants, budget),
puis Paramètres › Blocs fonctionnels. On peut ensuite saisir les composants.

En l'état, Nomentrace n'a pas de comptes utilisateurs et n'écoute que sur la machine
locale. Il ne faut pas l'exposer sur un réseau avant la phase des comptes, décrite dans la
feuille de route.

## Documentation

| Document | Pour qui, pour quoi |
|---|---|
| [docs/UTILISATION.md](docs/UTILISATION.md) | Le guide d'utilisation, écran par écran |
| [docs/EXPLOITATION.md](docs/EXPLOITATION.md) | Installation, emplacement des données, export Excel, sauvegardes et restauration, mises à jour, problèmes courants |
| [docs/MODELE.md](docs/MODELE.md) | Le modèle de données, les vues, les valeurs autorisées et toutes les formules de calcul |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Comment le code est construit, et comment y ajouter une fonctionnalité |
| [docs/API.md](docs/API.md) | Les routes de l'API JSON |
| [docs/CONTRIBUER.md](docs/CONTRIBUER.md) | Les règles de code, de tests et de documentation |
| [docs/FEUILLE_DE_ROUTE.md](docs/FEUILLE_DE_ROUTE.md) | Ce qui est prévu : comptes, hébergement, rapports, multi-projet |

## Licence

Nomentrace est un logiciel libre, distribué sous la licence
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only).
Copyright © 2026 Quentin Cunha. Le lien « Code source » en bas du menu de l'application
renvoie à ce dépôt ; une version modifiée et hébergée doit pointer vers son propre code.

Vous pouvez utiliser, étudier, modifier et redistribuer Nomentrace, y compris dans un cadre
commercial. Si vous distribuez une version modifiée, ou si vous la mettez à disposition
d'autres personnes à travers un réseau (hébergée sur un serveur, par exemple), vous devez
en fournir le code source complet à ses utilisateurs, sous la même licence. Le texte de la
licence fait foi.

Les données que vous saisissez dans l'outil (base, exports, documents) vous appartiennent :
la licence porte sur le code, pas sur elles. Les bibliothèques utilisées (FastAPI,
Uvicorn, Pydantic, openpyxl, Chart.js) gardent leurs propres licences, compatibles.
