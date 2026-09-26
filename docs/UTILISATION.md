# Guide d'utilisation

Ce guide suit l'ordre dans lequel on se sert de Nomentrace sur un projet réel : on règle le
projet, on saisit la nomenclature, on la range dans des ensembles, on achète, on reçoit, on
monte. L'installation est décrite dans [EXPLOITATION.md](EXPLOITATION.md), le vocabulaire
et les formules de calcul dans [MODELE.md](MODELE.md).

## L'idée de départ

Chaque composant reçoit un identifiant qui ne change plus, par exemple `ROB-ALI-003` : le
préfixe du projet, le code du bloc fonctionnel, un numéro. Tout ce qui arrive ensuite au
composant se rattache à cet identifiant : son prix relevé, le devis où il figure, la
commande, la réception, le stock, l'ensemble où il est monté. Les écrans de l'outil ne
sont que des lectures différentes de cette même histoire.

Deux découpages coexistent et ne se remplacent pas. Le bloc fonctionnel dit à quoi sert
un composant (alimentation, perception, mécanique…) ; il est unique et figé dans
l'identifiant, il porte un budget. L'ensemble dit où le composant est monté physiquement
(châssis, coffret, roue gauche) ; un même composant peut entrer dans plusieurs ensembles,
avec une quantité pour chacun. Ce lien s'appelle une affectation.

Un composant sans affectation n'est pas une anomalie. Tant que le travail de montage n'est
pas préparé, c'est l'état normal, et l'outil ne le signale jamais comme une alerte.

## L'interface en général

Le menu de gauche mène aux écrans ; son bouton en haut à gauche le réduit à une colonne
d'icônes ou le masque. L'en-tête rappelle le nom du projet et l'état de l'export Excel.

La recherche globale, au centre de l'en-tête, trouve à la fois des composants (identifiant,
désignation, référence, fonction), des commandes, des fournisseurs, des ensembles et des
blocs. Ctrl+F ou la touche « / » y placent le curseur, les flèches parcourent les
résultats, Entrée ouvre le résultat surligné, Échap referme. Comme Ctrl+F est pris par
l'outil, la recherche du navigateur dans la page s'obtient en appuyant une seconde fois sur
Ctrl+F quand le curseur est déjà dans le champ.

Les fiches et les formulaires s'ouvrent dans un panneau à droite, fermé par la croix ou
par Échap. Dans les tableaux, une colonne soulignée se modifie sur place : un clic sur la
cellule, la saisie, puis Entrée ou un clic ailleurs pour enregistrer, Échap pour annuler.
Une erreur (valeur refusée, conflit) s'affiche dans un bandeau rouge sous l'en-tête, avec
un message en français ; rien n'est enregistré dans ce cas.

Les montants s'affichent en euros, au format français, hors taxes sauf mention contraire.
Les filtres, le tri et la fiche ouverte sont gardés dans l'adresse de la page : on peut
la mettre en favori ou l'envoyer à quelqu'un qui a accès au même serveur.

## Se connecter

Sur un serveur partagé, on entre avec son adresse mail et son mot de passe. Le premier
accès passe par le lien d'invitation reçu d'un administrateur : il ouvre une page où l'on
choisit son mot de passe, puis l'outil s'ouvre directement. Sous le champ, les exigences se
cochent au fil de la saisie : douze caractères au moins, avec minuscule, majuscule, chiffre
et caractère spécial, ou bien une phrase de vingt caractères ou plus ; ni son nom ni son
adresse ; pas un mot de passe courant. Si plusieurs personnes se connectent au même
instant, l'outil peut demander de patienter quelques secondes. Le lien ne sert qu'une fois et
expire au bout de trois jours. Un mot de passe oublié se règle de la même manière, en
demandant un nouveau lien.

L'en-tête affiche son nom, son rôle et le bouton de déconnexion. Lancé en double-clic sur
un poste (`lancer.bat`), l'outil tourne en mode local : pas de connexion, l'en-tête
indique « Mode local » et tout est permis.

Trois rôles se partagent le travail. Le lecteur consulte tout et télécharge les exports
Excel, sans rien modifier. Le contributeur modifie les composants des blocs fonctionnels
qui lui sont attribués (champs, caractéristiques, affectations, documents, imports), fait
les mouvements de stock et peut proposer un nouveau fournisseur, qui restera « à valider ».
Deux permissions s'ajoutent au cas par cas : « achats » ouvre les commandes, les
réceptions, les demandes de devis et la modification des fiches fournisseurs ; « ensembles
» ouvre la création et la modification de l'arborescence des ensembles. L'administrateur a
tout le reste : paramètres, blocs, listes, attributs, budgets, validation des
fournisseurs, nettoyage, sauvegardes et comptes.

Ce qui n'est pas permis n'apparaît pas : la fiche d'un composant d'un autre bloc s'ouvre
en lecture seule, les boutons de commande disparaissent sans la permission « achats ».

Deux personnes peuvent travailler en même temps. Si quelqu'un modifie un composant pendant
que vous remplissez sa fiche, votre enregistrement est refusé avec le nom de l'autre
personne et l'heure de sa modification : recharger la fiche, puis refaire la vôtre. Rien
n'est écrasé sans qu'on le sache.

## Régler le projet

Paramètres › Projet reçoit le nom du projet, le préfixe des identifiants, le budget HT
total et le taux de TVA par défaut. Le préfixe est obligatoire avant de créer le premier
composant ; le changer plus tard ne renomme pas les composants existants.

Paramètres › Blocs fonctionnels crée les blocs, chacun avec un code de deux à quatre
lettres majuscules, un nom, un ordre d'affichage et, si on le souhaite, un budget cible.
Le code d'un bloc ne se modifie plus après sa création. Un bloc archivé n'accepte plus de
nouveau composant.

Paramètres › Listes de valeurs porte le vocabulaire propre au projet : modes
d'approvisionnement (Achat, Fourni par un partenaire, Fabrication atelier…), statuts
d'approvisionnement et de choix, criticités, types de mouvement de stock. Renommer une
valeur ne change que son libellé ; une valeur désactivée n'est plus proposée à la saisie
mais reste valable sur les composants qui la portent. Quelques valeurs dont dépendent les
calculs (Achat, Bloquant, Réception achat…) sont marquées système : on peut les renommer,
pas les supprimer.

Paramètres › Attributs crée des caractéristiques libres pour les composants : une tension,
un matériau, un indice de protection. Chaque attribut a un type (texte, nombre, liste de
valeurs, oui ou non) et éventuellement une unité ; son code et son type sont figés à la
création. Les attributs actifs apparaissent partout : fiche composant, colonnes et filtres
de l'écran Composants, exports, modèles Excel.

Paramètres › Fournisseurs tient la liste des fournisseurs avec leur catégorie, leur site,
un contact pour les devis et un numéro de compte client. Chaque nom mène à une fiche qui
récapitule les composants et les commandes du fournisseur. Le bouton « Comparer avec une
liste… » lit un classeur Excel de fournisseurs de référence et propose, ligne par ligne,
ce qui peut être créé ou complété ; rien n'est écrit avant « Appliquer ». Un fournisseur
ajouté par l'équipe au fil de l'eau arrive avec le statut « à valider », signalé sur le
tableau de bord jusqu'à ce qu'on complète sa fiche.

## Saisir les composants

L'écran Composants est une table de toute la nomenclature. Le bouton « + Ajouter un
composant » ouvre le formulaire de création : on choisit le bloc, et l'identifiant suivant
de ce bloc s'affiche en aperçu ; il est attribué définitivement à l'enregistrement. La
fonction, la désignation, le mode d'approvisionnement et la quantité besoin sont
obligatoires.

Le prix se saisit tel qu'on l'a relevé, en HT ou en TTC. L'outil en déduit le PU HT avec le
taux de TVA du composant. Les quantités se lisent ainsi : on achète le besoin plus la
rechange, moins ce qui est déjà disponible sans achat (un stock existant, un prêt). Un
composant en mode Achat sans prix apparaît « à chiffrer » ; son coût manque au total, et
le tableau de bord le compte.

Au-dessus de la table, les filtres se cumulent : texte libre, bloc, ensemble, mode
d'approvisionnement, statuts, criticité, fournisseur, composants à chiffrer ou non
affectés. Filtrer sur un ensemble qui a des sous-ensembles les inclut ; la case « avec ses
sous-ensembles » permet de s'en tenir à ses affectations directes. La ligne des
caractéristiques ajoute des filtres sur les attributs (égal à, vide, renseigné, intervalle
pour un nombre) et le choix des colonnes d'attributs à afficher. Un clic sur un en-tête
trie la colonne. La ligne de total en pied de table suit les filtres.

Le bouton « Exporter » produit un classeur Excel de la liste exactement telle qu'elle est
affichée : mêmes filtres, même tri, mêmes colonnes, avec le total.

### La fiche d'un composant

Un clic sur une ligne ouvre la fiche. On y trouve tous les champs, modifiables par
« Modifier », les caractéristiques, les ensembles où le composant est affecté (quantités
modifiables, affectation à un nouvel ensemble), ses lignes de devis et de commande, ses
documents, ses mouvements de stock et son historique.

L'historique est une frise, la plus récente en haut, qui rassemble tout ce qui concerne le
composant, où que ce soit écrit : champs modifiés, caractéristiques, ajout à un devis,
changements de statut de la commande, quantités reçues, mouvements de stock, affectations
et montages, documents joints. Une pastille renvoie vers la source de chaque événement
(la commande CMD-004, l'ensemble CHASSIS…), et des cases masquent une catégorie. Une
modification venue d'un import Excel renvoie vers le fichier qui l'a apportée. Les
mouvements de stock n'ont qu'une date, sans heure : ils se placent au jour où ils ont eu
lieu, pas au moment où ils ont été saisis.

Les documents propres au composant (fiche technique, plan, photo) se déposent dans la
section Documents. La même section montre aussi, en lecture, les documents des commandes
où le composant figure.

« Archiver » retire le composant des listes et des calculs sans rien effacer. « Reclasser »
le déplace dans un autre bloc : comme le bloc fait partie de l'identifiant, l'outil crée
un nouveau composant avec les mêmes données, reporte les affectations, et archive
l'ancien en pointant vers le nouveau. Les commandes, le stock et les documents restent à
l'ancien identifiant, qui garde ainsi son histoire.

## Organiser les ensembles

L'écran Ensembles présente les ensembles physiques de trois façons, par ses onglets.

L'onglet Cartes montre une carte par ensemble et par sous-ensemble : composants, pièces,
coût, budget, répartition du coût par bloc fonctionnel, avancement de l'approvisionnement
et du montage, statut de montage modifiable directement. La carte d'un ensemble qui a des
sous-ensembles donne des chiffres cumulés, avec sa part propre en second.

L'onglet Arbre donne la hiérarchie complète dans un tableau, depuis la ligne du projet :
coût cumulé, part propre, budget cible, budget calculé, écart, avancement. C'est l'endroit
où l'on arbitre les budgets (voir plus bas).

L'onglet Schéma dessine le même arbre de gauche à droite, un cadre par ensemble relié à son
parent. Un sélecteur change ce que racontent les couleurs : l'écart au budget, l'avancement
de l'approvisionnement, celui du montage ou le statut de montage. Un cadre rouge signale un
parent dont le budget est dépassé par ce qu'on y a verrouillé. Un clic ouvre l'ensemble.

Le bouton « + Nouvel ensemble » demande un code (majuscules, chiffres et tirets, figé
ensuite), un nom, l'ensemble parent éventuel et un ordre d'affichage parmi ses frères. Un
ensemble a au plus un parent. L'outil refuse de ranger un ensemble sous l'un de ses propres
sous-ensembles, et refuse d'archiver un ensemble qui a encore des affectations ou des
sous-ensembles.

### La page d'un ensemble

Elle reprend les chiffres de la carte, liste les sous-ensembles, puis les composants
affectés directement, groupables par bloc. Une quantité affectée se modifie en cliquant
dessus ; la croix retire le composant. La liste de montage, en bas, montre ce qu'il reste à
monter avec l'état du stock : prêt à monter, en partie en stock, en attente de livraison,
pas encore commandé.

« + Affecter un composant » ouvre un sélecteur avec recherche. Pour chaque composant, il
montre son besoin, la quantité déjà affectée ailleurs et celle affectée ici, ce qui fait
voir tout de suite une sur-affectation. Les composants déjà présents dans l'ensemble sont
en tête : leur quantité s'enregistre dès qu'on quitte le champ, et « Retirer » les enlève
(saisir 0 revient au même). Un composant qui n'existe pas encore se crée depuis le même
panneau.

« Dupliquer » copie l'ensemble sous un nouveau code, avec ou sans ses affectations et, au
choix, avec tous ses sous-ensembles. Les codes des sous-ensembles copiés sont proposés
d'après le nouveau code (`ROUE-G` sous `ROUE` devient `ROUE2-G` sous `ROUE2`) et restent
modifiables. La copie repart au statut « Non commencé » et ne reprend pas de budget
verrouillé. Si un seul des codes est déjà pris, rien n'est créé.

L'encadré Cohérence, en bas de l'écran Ensembles, liste sans dramatiser les composants
affectés au-delà de leur besoin, ceux qui sont affectés mais pas encore commandés, et les
montages qui dépassent l'affectation ou qui n'ont pas d'affectation.

### Les budgets d'ensemble

Le budget du projet descend l'arbre. À chaque niveau, un sous-ensemble verrouillé garde le
montant qu'on lui a donné ; les composants affectés directement à l'ensemble parent
prennent leur coût estimé ; le reste est partagé à parts égales entre les sous-ensembles
non verrouillés, qu'ils portent déjà des composants ou non. Un sous-ensemble encore vide
reçoit donc sa part, ce qui montre ce qu'il reste à dépenser pour lui.

Exemple : un ensemble reçoit 1 000 €, ses propres composants coûtent 100 €, un de ses
trois sous-ensembles est verrouillé à 300 €. Les deux autres reçoivent chacun 300 €.

Dans l'onglet Arbre, un clic sur la case « Budget cible » d'un ensemble permet d'y saisir un
montant : l'ensemble est alors verrouillé, ce qu'indique un cadenas. Vider la case le
déverrouille et son budget redevient calculé. Le budget du projet lui-même se modifie dans
Paramètres › Projet. Si les montants verrouillés et les composants propres dépassent le
budget d'un parent, ses autres sous-ensembles reçoivent zéro et une alerte s'affiche sur
lui.

Ces budgets d'ensemble ne remplacent pas les budgets de bloc. Les deux découpent le même
budget total, l'un par partie physique, l'autre par fonction, et ne s'additionnent pas.

## Acheter

L'écran Achats liste les devis et les commandes, filtrables par statut, par fournisseur et
par retard de livraison. Une commande a un type (Devis ou Commande) et un statut qui suit
son cycle : à demander, devis demandé, devis reçu, devis validé, commandé, livré en partie,
livré, refusé. Seules les commandes de type Commande au statut commandé ou livré comptent
dans le montant engagé ; un devis n'engage rien.

« + Nouvelle commande » crée une commande vide chez un fournisseur. Sa page permet d'ajouter
des lignes (composant, quantité, PU HT du devis), de renseigner les dates, le port et le
taux de TVA, de joindre les documents (devis, bon de commande, facture, bon de livraison).

« Préparer les demandes de devis » part de l'autre bout. Le panneau rassemble les
composants en mode Achat dont il reste des pièces à commander, dans un cadre par
fournisseur, avec la quantité restante et le prix connu. On coche ce qu'on veut demander ;
un composant déjà présent dans une demande en cours est signalé et décoché d'office, pour
ne pas le demander deux fois. Le bouton crée une demande de devis « à demander » par
fournisseur, dont les lignes portent le reste à commander et un PU HT vide, à remplir quand
le devis arrive. Les composants sans fournisseur sont listés à part, avec un lien vers
leur fiche.

### Recevoir

Sur la page d'une commande, « Réceptionner » ouvre la saisie de la livraison : la date,
l'emplacement de rangement, la personne qui reçoit, et la quantité reçue pour chaque ligne.
Une réception partielle est normale. Chaque réception crée un mouvement d'entrée en stock,
et le statut de la commande passe tout seul à « livré en partie » ou « livré ». Une ligne
dont des pièces ont été reçues ne se supprime plus ; on la passe au statut Annulée si
besoin.

## Stock et montage

L'écran Stock montre l'état du stock de chaque composant et le journal des mouvements,
filtrable par type et par ensemble. « + Nouveau mouvement » enregistre à la main un
inventaire, un prêt, une sortie ou un retour de montage. Une sortie de montage vers un
ensemble compte comme une pièce montée dans cet ensemble ; c'est elle qui fait avancer la
barre de montage.

## Analyser les caractéristiques

L'écran Attributs choisit une caractéristique et montre la répartition des composants par
valeur : nombre de composants, de pièces, coût HT, et la part « non renseigné ». On peut
restreindre à un bloc, un ensemble ou un mode d'approvisionnement. Un clic sur une valeur
ouvre l'écran Composants filtré sur elle. Pour un attribut numérique, les options avancées
calculent la somme et la moyenne, pondérées ou non par le nombre de pièces. C'est ainsi
qu'on obtient, par exemple, la liste des tensions présentes dans un projet.

## Travailler avec l'équipe par Excel

Tout le monde n'a pas besoin d'ouvrir l'outil. L'écran Imports génère un modèle Excel par
bloc fonctionnel ou par ensemble : il reprend les composants existants avec leurs valeurs
actuelles, des listes déroulantes pour les champs à valeurs fixes, et des lignes vides pour
les ajouts. Le modèle d'ensemble ajoute une colonne « Qté dans cet ensemble » ; c'est celui
qu'on donne à la personne qui monte cette partie.

Les fichiers remplis se redéposent sur le même écran, un ou plusieurs à la fois. L'analyse
ne modifie rien. Elle classe chaque ligne : composant nouveau, modifié, identique,
doublon probable d'un existant, affectation à créer ou à changer, fournisseur ou valeur de
liste inconnus à créer, ligne invalide. La page de revue présente ces propositions, champ
par champ pour les modifications ; on coche ce qu'on accepte, puis on applique.
L'application se fait en une seule transaction, après une sauvegarde. Si la base a changé
entre l'analyse et l'application sur un champ concerné, la ligne est refusée plutôt
qu'écrasée.

Les doublons sont repérés en trois temps : même référence fabricant une fois normalisée,
référence de l'un citée dans le texte de l'autre, puis ressemblance des libellés. Deux
libellés qui ne diffèrent que par un nombre (« convertisseur 12 V » et « convertisseur
24 V ») ne sont jamais proposés à la fusion, seulement signalés.

## Suivre le projet

Le tableau de bord ne se saisit pas, il se lit : coût estimé, écart au budget, lignes à
chiffrer, montant engagé et reste à engager, une jauge de consommation du budget, le coût
par bloc, les dix composants les plus coûteux, la répartition par mode d'approvisionnement
et une série d'alertes cliquables (commandes en retard, composants bloquants non commandés,
écarts d'affectation, fournisseurs à valider…).

L'écran Blocs donne une carte par bloc fonctionnel avec son coût, son budget cible
modifiable sur place, le montant engagé et l'avancement des achats.

Paramètres › Historique lit tout le journal du projet, cent lignes par page, les plus
récentes en haut. La colonne « Par » donne l'auteur de chaque modification (les lignes
antérieures aux comptes n'en ont pas). On filtre par type d'élément, par origine
(interface ou import), par période et par texte. Chaque clé mène à l'élément concerné, et « Exporter la sélection »
produit un classeur Excel des lignes filtrées.

## Nettoyer la base

Le bouton « Nettoyage de la base », dans Paramètres, ouvre un écran de contrôle. Il liste
les composants mal remplis (désignation trop courte, fonction vide, achat sans prix ou sans
fournisseur, besoin nul, lien invalide, valeur de liste désactivée, fournisseur archivé,
doublon probable) et permet de les archiver ou de les supprimer en lot. Il fait de même
pour les commandes et devis, et pour les blocs, ensembles et fournisseurs inutilisés.

La règle est simple : on archive tout, et on ne supprime que ce qui n'a laissé aucune
trace. Un composant qui figure sur une commande, qui a bougé en stock ou qui porte un
document ne se supprime pas. Chaque suppression prend d'abord une sauvegarde et laisse
dans le journal un résumé de ce qui a été supprimé. Les fichiers joints d'une commande
supprimée partent dans la corbeille des documents, d'où une restauration peut les
ramener.

Le même écran permet de vider le journal, pour repartir d'un historique propre après une
phase d'essais. Une sauvegarde est prise avant, et une ligne trace la purge.

## Gérer les comptes

Paramètres › Utilisateurs, réservé à l'administrateur, liste les comptes avec leur rôle,
leurs blocs, leurs permissions et leur état : invitation en attente, dernière connexion,
désactivé. « Nouvel utilisateur » crée un compte à partir de son adresse mail et d'un nom
affiché, qui apparaîtra dans l'historique à chacune de ses modifications et doit donc
rester distinctif. Le lien d'invitation s'affiche alors une seule fois, avec un bouton pour
le copier ; il faut le transmettre soi-même.

« Modifier » change le nom, le rôle, les blocs et les permissions ; l'effet est immédiat,
même pour une session ouverte. Un compte ne se supprime pas, il se désactive, ce qui ferme
ses sessions et garde son nom dans l'historique. « Nouveau lien » efface le mot de passe
actuel et en donne un nouveau à choisir : c'est la réponse à un mot de passe oublié. Le
dernier administrateur actif ne peut être ni désactivé ni rétrogradé.

## Exporter, sauvegarder, restaurer

L'export Excel de toute la base, les sauvegardes, l'archive complète et la corbeille des
documents se gèrent dans Paramètres › Export et sauvegardes. Seul l'administrateur y voit
les sauvegardes, l'archive et la corbeille, qui contiennent toute la base ; les autres y
trouvent l'Excel global. Leur fonctionnement, et la restauration depuis une archive, sont
décrits dans [EXPLOITATION.md](EXPLOITATION.md).
