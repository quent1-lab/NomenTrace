# Feuille de route

Nomentrace est né comme un outil local, pour une personne qui tient la nomenclature d'un
projet sur son poste. Il se partage désormais avec l'équipe du projet, sur un serveur.
Ce document dit où en est l'outil, ce qui est prévu ensuite, et dans quel ordre ;
les choix techniques qui en découpent déjà la forme sont dans la dernière partie
d'[ARCHITECTURE.md](ARCHITECTURE.md).

## Ce qui est fait

La nomenclature, les deux découpages (blocs et ensembles en arbre), les
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
détail est dans [UTILISATION.md](UTILISATION.md) et [EXPLOITATION.md](EXPLOITATION.md) ;
un audit de sécurité a suivi, consigné dans [SECURITE.md](SECURITE.md).

Et l'hébergement. Le dossier [deploiement/](../deploiement/README.md) installe l'outil sur
une petite machine virtuelle, éprouvée sur l'offre gratuite d'Oracle Cloud : un service
systemd fait tourner Uvicorn, Caddy le sert en HTTPS avec un certificat automatique, un
projet par serveur. Chaque nuit, l'archive complète, base des comptes comprise, est
chiffrée pour une clé que seul l'administrateur détient, puis envoyée dans un stockage
objet hors de la machine, gardée trente jours. Les mises à jour suivent les versions
publiées par étiquette, après le passage de l'intégration continue ; une version qui ne
répond pas est défaite d'elle-même, bases comprises. Installation, rôles, sauvegarde,
restauration, mise à jour et retour arrière ont été vérifiés sur une vraie machine.

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
où il n'a pas de rôle. Les rôles sont déjà rangés projet par projet dans la base des
comptes.

Restent enfin quelques idées plus modestes : une alerte par courriel sur les livraisons en
retard, la ventilation du port d'une commande entre les blocs, et des sous-ensembles
réutilisables, montés plusieurs fois avec multiplication des quantités.
