# Feuille de route

Nomentrace est né comme un outil local, pour une personne qui tient la nomenclature d'un
projet sur son poste. L'étape suivante est de le partager avec l'équipe du projet, sur un
serveur. Ce document dit où en est l'outil, ce qui est prévu ensuite, et dans quel ordre ;
les choix techniques qui en découpent déjà la forme sont dans la dernière partie
d'[ARCHITECTURE.md](ARCHITECTURE.md).

## Ce qui est fait

La nomenclature, les deux découpages (blocs fonctionnels et ensembles en arbre), les
budgets, les achats de la demande de devis à la réception, le stock et le montage, les
attributs paramétrables, le travail en équipe par modèles Excel, le nettoyage de la base,
l'historique complet, la recherche globale, les sauvegardes avec leur corbeille de
documents.

Les comptes et les droits aussi. Les comptes sont internes à l'outil : un administrateur
crée chaque utilisateur et lui transmet un lien d'invitation, par lequel la personne
choisit son mot de passe. Le lecteur voit tout ; le contributeur modifie les composants de
ses blocs, avec en plus, au cas par cas, les achats ou l'arborescence des ensembles ;
l'administrateur a le reste. Chaque modification porte son auteur dans le journal, et une
modification faite sur un composant changé entre-temps est signalée au lieu d'écraser
l'autre. Le mode local, sans connexion, reste celui du double-clic sur `lancer.bat`. Le
détail est dans [UTILISATION.md](UTILISATION.md) et [EXPLOITATION.md](EXPLOITATION.md).

## Hébergement

C'est la prochaine étape. L'outil sera hébergé sur une petite machine virtuelle de l'offre gratuite d'Oracle
Cloud, suffisante pour une quinzaine d'utilisateurs. Pas de Docker : un service systemd
fait tourner Uvicorn, Caddy le sert en HTTPS avec un certificat automatique. Un projet par
serveur.

Une sauvegarde quotidienne enverra l'archive complète (base et documents, corbeille
comprise) et la base des comptes hors de la machine, dans un stockage objet, avec trente
jours de rétention. Caddy limitera aussi la taille des requêtes, et Uvicorn ne fera
confiance qu'à lui pour l'adresse IP des visiteurs, dont dépend la limite des tentatives de
connexion. Un
script de mise à jour sauvegardera, installera la nouvelle version, contrôlera qu'elle
répond, et reviendra à la précédente sinon. Le tout sera décrit dans un guide pas à pas,
dans un dossier `deploiement/`.

## Plus tard

Ces évolutions sont retenues, sans ordre ni date arrêtés.

Des rapports PDF : suivi de projet, fiche de montage imprimable d'un ensemble (ce qu'il
faut sortir du stock, avec une case à cocher par ligne), état des achats, bon de commande.

Des jalons : figer l'état du projet à une date, par exemple une revue de conception, pour
comparer plus tard ce qui a dérivé en coût et en avancement.

Une courbe d'engagement dans le temps, sur le tableau de bord : le montant engagé cumulé
mois par mois face au budget, qui montre le rythme de dépense et le risque de manquer
d'argent avant la fin.

La modification en masse des composants depuis l'écran Composants. L'import Excel couvre ce
besoin pour l'instant.

Une fois l'outil hébergé : des étiquettes QR sur les bacs de stock qui ouvrent la fiche du
composant au téléphone, des commentaires sur un composant visibles par l'équipe, une page
« Mes composants » pour chaque responsable.

Plusieurs projets sur un même serveur. La piste retenue est une base par projet, avec son
dossier de documents, d'exports et de sauvegardes, plutôt qu'une colonne de projet dans
chaque table : aucune donnée ne peut alors passer d'un projet à l'autre. Les comptes
vivraient dans une base commune, avec des rôles attribués projet par projet ; un
utilisateur ne verrait ni n'atteindrait, même par une adresse tapée à la main, les projets
où il n'a pas de rôle. La phase des comptes rangera déjà les rôles de cette façon.

Restent enfin quelques idées plus modestes : une alerte par courriel sur les livraisons en
retard, la ventilation du port d'une commande entre les blocs, et des sous-ensembles
réutilisables, montés plusieurs fois avec multiplication des quantités.
