# Guide d'utilisation

Ce guide suit l'ordre dans lequel on se sert de Nomentrace sur un projet réel : on règle le
projet, on saisit la nomenclature, on la range dans des ensembles, on achète, on reçoit, on
monte. L'installation est décrite dans [EXPLOITATION.md](EXPLOITATION.md), le vocabulaire
et les formules de calcul dans [MODELE.md](MODELE.md).

## L'idée de départ

Chaque composant reçoit un identifiant qui ne change plus, par exemple `ROB-ALI-003` : le
préfixe du projet, le code du bloc, un numéro. Tout ce qui arrive ensuite au
composant se rattache à cet identifiant : son prix relevé, le devis où il figure, la
commande, la réception, le stock, l'ensemble où il est monté. Les écrans de l'outil ne
sont que des lectures différentes de cette même histoire.

Deux découpages coexistent et ne se remplacent pas. Le bloc range un composant dans le
découpage de suivi du projet, qu'il soit fonctionnel (alimentation, perception…), par
métier ou par lot ; il est unique et figé dans l'identifiant, il porte un budget. L'ensemble dit où le composant est monté physiquement
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
un message en français ; rien n'est enregistré dans ce cas. Dans un formulaire de
modification, le bouton « Enregistrer » reste grisé tant qu'aucune valeur n'a changé, et le
redevient si l'on revient aux valeurs de départ.

Sur un téléphone, le menu devient un tiroir que le même bouton ouvre par-dessus la page ;
il se referme dès qu'on choisit un écran. Son pied porte le compte, le retour à vos projets et
la déconnexion. Les filtres de la liste des composants se déplient d'un bouton « Filtres »,
la recherche restant visible, et les onglets des paramètres défilent sur une ligne. Les fiches occupent tout l'écran, chaque libellé
au-dessus de sa valeur, et les tableaux larges défilent de côté dans leur cadre, la
première colonne de la liste des composants restant visible. La saisie reste plus
confortable sur un ordinateur.

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
demandant un nouveau lien. En bas de la page de connexion, une ligne présente l'outil et
mène à son code source.

L'en-tête affiche son nom, son rôle et le bouton de déconnexion. Lancé en double-clic sur
un poste (`lancer.bat`), l'outil tourne en mode local : pas de connexion, l'en-tête
indique « Mode local » et tout est permis.

La connexion est la même pour tous les projets du serveur. Celui qui n'a accès qu'à un
projet arrive directement sur son tableau de bord. Les autres arrivent sur l'accueil, qui
range leurs projets par organisme puis par dossier, en cartes : nom du projet et de
l'équipe (« Épreuve · Alpha »), accès, avancement de l'approvisionnement et montant engagé sur
le budget ; tant que rien n'est engagé, la carte montre à la place le coût estimé des
composants. Le bouton « Vos projets » de l'en-tête y ramène depuis n'importe quel projet.

Trois rôles se partagent le travail. Le lecteur consulte tout et télécharge les exports
Excel, sans rien modifier. Le contributeur modifie les composants des blocs
qui lui sont attribués (champs, caractéristiques, affectations, documents, imports), fait
les mouvements de stock et peut proposer un nouveau fournisseur, qui restera « à valider ».
Trois permissions s'ajoutent au cas par cas : « achats » ouvre les commandes, les
réceptions, les demandes de devis et la modification des fiches fournisseurs ;
« ensembles » ouvre la création et la modification de l'arborescence des ensembles ;
« attributs » ouvre Paramètres › Attributs, pour créer et modifier les attributs et leurs
listes de valeurs. L'administrateur a tout le reste : paramètres, blocs, listes, budgets,
validation des fournisseurs, nettoyage, sauvegardes et comptes.

Ce qui n'est pas permis n'apparaît pas : la fiche d'un composant d'un autre bloc s'ouvre
en lecture seule, les boutons de commande disparaissent sans la permission « achats ».

Sur un serveur partagé, l'outil sait qui agit. Le dépôt d'un fichier Excel est signé du
nom de la personne connectée, sans case « Déposé par » à remplir. Les champs « Demandée
par » d'une commande et « Par qui » d'une réception ou d'un mouvement de stock sont
préremplis avec son nom ; on peut les changer quand on agit pour quelqu'un d'autre, par
exemple un colis reçu par un encadrant. En mode local, sans compte, ces champs restent à
saisir. Dans tous les cas, l'historique garde l'auteur réel de chaque modification.

Deux personnes peuvent travailler en même temps. Si quelqu'un modifie un composant pendant
que vous remplissez sa fiche, votre enregistrement est refusé avec le nom de l'autre
personne et l'heure de sa modification : recharger la fiche, puis refaire la vôtre. Rien
n'est écrasé sans qu'on le sache.

## Régler le projet

Paramètres › Projet reçoit le nom du projet, le préfixe des identifiants, le budget HT
total et le taux de TVA par défaut. Le préfixe est obligatoire avant de créer le premier
composant ; le changer plus tard ne renomme pas les composants existants. La section
Établissement reçoit le nom de l'établissement, les adresses de livraison et de facturation
et le contact achats, repris dans les demandes de devis envoyées aux fournisseurs. Un logo,
image PNG ou JPEG de 2 Mo au plus, s'y ajoute : il se place en haut à droite du PDF et du
classeur Excel de chaque demande.

La même page règle les champs obligatoires des composants : lien produit, fournisseur,
référence fabricant, fabricant, prix relevé, au choix. Par défaut, la règle ne vaut que pour
les composants en mode Achat ; elle peut s'étendre à tous. Un attribut se rend obligatoire
dans Paramètres › Attributs. La règle s'applique à la création d'un composant, à l'import et
à toute modification qui vide un champ obligatoire ou fait passer le composant en mode
Achat. Un composant créé avant la règle reste modifiable sur ses autres champs ; l'écran
Nettoyage le signale par « Champ obligatoire manquant ».

Paramètres › Blocs crée les blocs, chacun avec un code de deux à quatre
lettres majuscules, un nom, un ordre d'affichage et, si on le souhaite, un budget cible.
Le code d'un bloc ne se modifie plus après sa création. Un bloc archivé n'accepte plus de
nouveau composant.

Paramètres › Listes de valeurs porte le vocabulaire propre au projet : modes
d'approvisionnement (Achat, Fourni par un partenaire, Fabrication atelier…), statuts
d'approvisionnement et de choix, criticités, types de mouvement de stock. Renommer une
valeur ne change que son libellé ; une valeur désactivée n'est plus proposée à la saisie
mais reste valable sur les composants qui la portent. Quelques valeurs dont dépendent les
calculs (Achat, Bloquant, Réception achat…) sont marquées système, d'un cadenas : on peut les renommer,
pas les supprimer.

Paramètres › Attributs crée des caractéristiques libres pour les composants : une tension,
un matériau, un indice de protection. Chaque attribut a un type (texte, nombre, liste de
valeurs, oui ou non) et éventuellement une unité ; son code et son type sont figés à la
création. Les attributs actifs apparaissent partout : fiche composant, colonnes et filtres
de l'écran Composants, exports, modèles Excel. Un attribut marqué obligatoire est demandé
dès la création d'un composant.

Paramètres › Fournisseurs tient la liste des fournisseurs avec leur catégorie, leur site,
un contact pour les devis et un numéro de compte client. Chaque nom mène à une fiche qui
récapitule les composants et les commandes du fournisseur. Le bouton « Comparer avec une
liste… » lit un classeur Excel de fournisseurs de référence et propose, ligne par ligne,
ce qui peut être créé ou complété ; rien n'est écrit avant « Appliquer ». Un fournisseur
ajouté par l'équipe au fil de l'eau arrive avec le statut « à valider », signalé sur le
tableau de bord jusqu'à ce qu'on complète sa fiche.

## Saisir les composants

L'écran Composants est une table de toute la nomenclature. Le bouton « + Ajouter un
composant » ouvre la création, en deux étapes. La première demande l'essentiel : on
choisit le bloc, et l'identifiant suivant de ce bloc s'affiche en aperçu ; la fonction, la
désignation, le mode d'approvisionnement et la quantité besoin sont obligatoires. « Créer
et continuer » enregistre le composant et lui attribue son identifiant. La seconde étape,
facultative, propose toutes les caractéristiques, l'affectation aux ensembles et le dépôt
de documents, pour que rien ne soit oublié ; « Passer » la saute, et fermer le panneau garde
le composant créé.

Dans un dossier qui met ses composants en commun, la création cherche, pendant qu'on tape
la désignation ou la référence fabricant, les références qui ressemblent chez les autres
équipes du dossier. Une pastille « 2 références dans le dossier » s'affiche sous la
référence, dépliée ; elle se replie d'un clic. Chaque proposition montre la désignation, la
référence, le fabricant, le fournisseur, l'équipe qui l'a saisie, si elle l'a déjà reçue et
combien de fiches techniques elle porte. « Reprendre » préremplit le formulaire avec la
fonction, la désignation, la référence, le fabricant, le fournisseur, le lien, le prix (« relevé
par l'Équipe Bêta », à vérifier), la base du prix, la TVA, les caractéristiques et le bloc
s'il fait partie des vôtres. Les quantités, les statuts, la criticité et les notes restent à
saisir. Le composant reçoit son propre identifiant et son propre prix, sans lien avec
l'original, et ses fiches techniques sont copiées avec lui ; l'historique note la reprise.
La même pastille signale un composant du projet qui porte déjà la même référence, sans
empêcher la création. Une copie par « Dupliquer » ne cherche pas.

La forme des champs texte est contrôlée. Une adresse web collée dans la fonction, la
désignation, la référence fabricant ou le fabricant est refusée (elle va dans Lien produit),
de même qu'un retour à la ligne dans une référence ; le refus vaut aussi pour l'import, ligne
par ligne. Une référence seulement inhabituelle, de plus de 40 caractères ou qui ressemble à
une phrase, est acceptée mais signalée dans l'écran Nettoyage par « Saisie à vérifier », comme
les erreurs saisies avant ce contrôle. Celles-ci ne bloquent pas la modification des autres
champs du composant.

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

Un clic sur une ligne ouvre la fiche. Son en-tête donne la désignation, le bloc et la
fonction, puis des pastilles : la criticité Bloquant, le visa, et le nombre d'actions qui
restent à faire. Un clic sur cette dernière déroule la liste : champs obligatoires à
remplir, prix à relever, saisie à vérifier, pièces du besoin restées hors de tout ensemble
alors que l'affectation est commencée, fiche technique absente pour un composant acheté.
Chaque action mène à l'endroit où la faire. Un composant affecté à aucun ensemble n'a pas
d'action pour autant : c'est un état normal.

Sous les boutons, le suivi montre où en est le composant en cinq étapes : chiffré,
commandé, reçu, affecté, monté. Chaque étape a sa valeur et une fine barre, verte quand
l'étape est faite, orange quand elle est en cours, grise sinon ; la réception indique la
prochaine livraison annoncée et le stock. Au-dessus, une ligne rappelle le calcul de la
quantité à acheter. Viennent ensuite le prix et le fournisseur, puis des onglets :
Détails (statuts, caractéristiques renseignées, note technique), Ensembles (quantités
modifiables, affectation à un nouvel ensemble), Achats, Stock, Documents et Historique. Un
clic sur une étape du suivi ouvre l'onglet correspondant. « Modifier » ouvre les champs et
toutes les caractéristiques, même vides, dans un même formulaire enregistré en une fois.
Reclasser et Archiver sont rangés sous « Plus ».

Un responsable, administrateur ou contributeur qui a la permission achats, vise le
composant en ouvrant sa fiche : il l'a vu tel qu'il est. Le visa se perd dès qu'un champ
ou une caractéristique du composant change ; les affectations, les commandes, le stock et
les documents ne le retirent pas. La case « À voir (sans visa) » de la liste ne garde que
les composants à viser, avec un bouton qui vise toute la liste affichée, et le menu
Composants porte pour les responsables le nombre de composants à voir. Chaque visa entre
dans l'historique du composant.

« Dupliquer » ouvre la création d'un nouveau composant, préremplie avec les champs et les
caractéristiques de celui-ci, dans le même bloc : il reste à changer ce qui diffère. Les
affectations, les documents, la quantité déjà disponible et le statut d'appro ne sont pas
repris, et le nouveau composant reçoit son propre identifiant.

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
où le composant figure. Pendant un envoi, une barre donne l'avancement, puis signale
l'enregistrement sur le serveur ; on peut changer d'écran sans l'interrompre, un bandeau
annonce alors la fin. Fermer ou recharger l'onglet demande confirmation tant qu'un envoi
est en cours. Il en va de même pour les commandes et pour les fichiers Excel de l'équipe.

« Archiver » retire le composant des listes et des calculs sans rien effacer. « Reclasser »
le déplace dans un autre bloc : comme le bloc fait partie de l'identifiant, l'outil crée
un nouveau composant avec les mêmes données, y reporte les affectations et les documents
(fiche technique, plan, photo), et archive l'ancien en pointant vers le nouveau. Les
commandes et le stock restent à l'ancien identifiant, qui garde ainsi son histoire d'achat.

## Organiser les ensembles

L'écran Ensembles présente les ensembles physiques de trois façons, par ses onglets.

Chaque ensemble porte deux montants. Le coût matière vaut toutes les pièces affectées à
leur prix, y compris celles qu'on a déjà en stock : c'est ce que vaut l'ensemble. Le
montant à dépenser en retire le stock déjà disponible : c'est ce que l'ensemble coûtera
réellement en achats. Quand un composant en stock sert à plusieurs ensembles, chacun
profite du stock au prorata de ses pièces. Un composant fabriqué, prêté ou donné n'a rien
à dépenser, et les pièces de rechange restent comptées au niveau du projet seulement.

L'onglet Cartes montre une carte par ensemble et par sous-ensemble : composants, pièces,
coût matière, montant à dépenser, budget et marge (sur la dépense, puis sur le coût
matière), répartition du coût par bloc, avancement de l'approvisionnement et du montage,
statut de montage modifiable directement. La carte d'un ensemble qui a des sous-ensembles
donne des chiffres cumulés, avec sa part propre en second.

L'onglet Arbre donne la hiérarchie complète dans un tableau, depuis la ligne du projet :
coût matière et montant à dépenser cumulés, part propre, budget cible, budget calculé,
marges sur la dépense et sur le coût matière, avancement. C'est l'endroit où l'on arbitre
les budgets (voir plus bas).

L'onglet Schéma dessine le même arbre de gauche à droite, un cadre par ensemble relié à son
parent. Un sélecteur change ce que racontent les couleurs : la dépense face au budget,
l'avancement de l'approvisionnement, celui du montage ou le statut de montage. Un cadre
rouge signale un parent dont le budget est dépassé par ce qu'on y a verrouillé. Un clic
ouvre l'ensemble.

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
(saisir 0 revient au même). La case « Masquer les composants entièrement affectés »,
cochée par défaut, retire de la liste ceux dont tout le besoin est déjà affecté ; ceux de
l'ensemble restent visibles. Un composant qui n'existe pas encore se crée depuis le même
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
budget total, l'un par partie physique, l'autre par bloc, et ne s'additionnent pas.

## Acheter

L'écran Achats liste les devis et les commandes, filtrables par statut, par fournisseur et
par retard de livraison. Une commande a un type (Devis ou Commande) et un statut qui suit
son cycle : à demander, devis demandé, devis reçu, devis validé, commandé, livré en partie,
livré, refusé. Seules les commandes de type Commande au statut commandé ou livré comptent
dans le montant engagé ; un devis n'engage rien. Passer un devis au statut commandé, livré
en partie ou livré en fait une commande : son type change avec son statut.

« + Nouvelle commande » crée une commande vide chez un fournisseur. Sa page permet d'ajouter
des lignes (composant, quantité, PU HT du devis), des frais (livraison, douane, frais de
facturation…, selon la liste Types de frais des paramètres), de renseigner les dates et le
taux de TVA, de joindre les documents (devis, bon de commande, facture, bon de livraison).
Les frais entrent dans le total de la commande et, une fois celle-ci passée, dans le
montant engagé ; ils ne sont pas répartis entre les blocs. Un fournisseur peut recevoir
autant de commandes que nécessaire, chacune avec son numéro.

Des composants peuvent arriver chez ce fournisseur après la demande de devis. Tant que la
commande n'est ni livrée ni refusée, une pastille orange le signale dans le cadre des lignes,
par exemple « 2 composants Mouser restent à commander hors de cette commande ». Elle déplie
la liste de ces composants en mode Achat, avec le reste à commander et le prix connu,
modifiables, et un bouton qui les ajoute tous en une fois. Un composant déjà présent dans un
autre devis en cours est signalé et décoché d'office. Sur une commande déjà passée, les lignes
ajoutées sont « commandées » et un rappel invite à prévenir le fournisseur ou
l'établissement ; transmise au suivi, la commande y reçoit ces lignes au passage suivant.

Dès qu'une commande a des lignes, sa page propose le document à envoyer au fournisseur, en
PDF ou en Excel : la liste des articles à chiffrer (référence, désignation, fabricant,
quantité, lien produit), sans prix, avec une date de réponse souhaitée facultative. L'en-tête
reprend l'établissement, ses adresses et son contact achats, saisis dans Paramètres ›
Projet, la personne connectée comme demandeur et le numéro de compte client noté sur la
fiche du fournisseur.

« Préparer les demandes de devis » part de l'autre bout. Le panneau rassemble les
composants en mode Achat dont il reste des pièces à commander, dans un cadre par
fournisseur, avec la quantité restante et le prix connu. On coche ce qu'on veut demander ;
un composant déjà présent dans une demande en cours est signalé et décoché d'office, pour
ne pas le demander deux fois. Le bouton crée une demande de devis « à demander » par
fournisseur, dont les lignes portent le reste à commander et un PU HT vide, à remplir quand
le devis arrive. Les composants sans fournisseur sont listés à part, avec un lien vers
leur fiche.

### Le suivi de l'établissement

Quand l'établissement passe lui-même les commandes, il tient souvent son propre suivi dans
un classeur imposé, partagé avec l'équipe. Nomentrace le complète et le relit sans en
changer la forme.

Sur la page d'une commande, « Transmettre au suivi » marque un devis reçu comme envoyé à
l'établissement. Dans l'écran Achats, « Suivi de l'établissement » reçoit la dernière
version du fichier. Nomentrace y repère les colonnes par leur titre (fournisseur,
référence, désignation, quantité, montant HT, date du devis, puis les colonnes de
l'établissement) et la légende des couleurs de l'en-tête. Il propose alors, commande par
commande, ce que l'établissement a rempli : passage en commande d'après la couleur de la
ligne, dates de commande et de livraison prévue (confirmées si elles sont en bleu,
estimées sinon), date de réception, montant de la commande, commentaire. Chaque changement
se coche ou se décoche. « Appliquer » enregistre ce qui est retenu et rend le fichier
complété, sous le même nom, à reposer sur l'espace partagé.

Chaque devis transmis y ajoute une ligne par composant (quantité, montant de la ligne,
date du devis) et une par frais. Une colonne masquée à droite du modèle porte la
référence Nomentrace de chaque ligne : c'est elle qui retrouve la ligne au retour, et
une ligne n'est jamais ajoutée deux fois. Quand les lignes prévues par le modèle ne
suffisent pas, des lignes s'insèrent avant le total, dont les sommes s'étendent.

Une ligne saisie à la main, sans référence, peut appartenir à un devis transmis ensuite :
Nomentrace la reconnaît au fournisseur (majuscules, accents et espaces mis à part), puis à
la référence fabricant, à une désignation très proche ou, pour un frais, au montant. Le
panneau propose « Associer 8 lignes à CMD-003 », coché d'office quand chaque ligne de la
commande a trouvé la sienne, et signale les écarts de quantité ou de montant sans jamais
corriger le fichier. Retenue, l'association écrit la référence dans la colonne masquée et la
commande n'est pas ajoutée une seconde fois. Une ligne qui ne correspond à rien est listée
avec son fournisseur et sa désignation, et laissée telle quelle. Les cases que
l'établissement fusionne sur toutes les lignes d'une commande (fournisseur, dates, montant)
se lisent une fois et ne sont jamais réécrites. À chaque passage, les cases
encore vides d'une ligne déjà écrite sont complétées de ce que Nomentrace sait depuis, par
exemple une date de devis saisie après la transmission ; une case remplie, par
l'établissement ou à la main, n'est jamais réécrite.

La date du devis vient du champ « Réception du devis » de la commande. Elle se pose d'elle-même,
à la date du jour, quand la commande passe au statut « Devis reçu » ou quand un document de
type Devis y est joint, si elle était vide. Transmettre au suivi une commande sans date de
devis demande confirmation.

Le montant de la commande saisi par l'établissement, frais compris, remplace l'estimation
dans le montant engagé. Une ligne colorée « livré » ne réceptionne rien : elle note une
réception annoncée, et la réception réelle, avec ses quantités, se saisit dans Nomentrace.

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
bloc ou par ensemble : il reprend les composants existants avec leurs valeurs
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

### Partir de son propre Excel

Une équipe qui tient déjà sa nomenclature dans son propre classeur n'a pas à la recopier à
la main. L'encadré « Partir de votre propre Excel, avec une IA », en haut de l'écran
Imports, guide la conversion en quatre temps.

1. Les blocs du projet doivent exister (Paramètres › Blocs) : l'import refuse un composant
   sans bloc. Fournisseurs et valeurs de liste inconnus, eux, sont proposés à la création.
2. « Télécharger le modèle vierge » donne un modèle sans composant, valable pour tous les
   blocs : la colonne Bloc de chaque ligne dit où ranger le composant.
3. On ouvre l'outil d'IA conversationnel de son choix, on lui joint son Excel et le modèle
   vierge, et on colle la consigne que donne « Copier la consigne ». Elle reprend les
   blocs, les listes de valeurs, les fournisseurs et les caractéristiques actuels du
   projet, et des règles : une ligne par composant, ne rien inventer, laisser la colonne
   ID vide, une adresse web seulement dans Lien produit, le prix tel qu'il est écrit avec
   sa base HT ou TTC. Elle demande d'abord à l'IA d'analyser le fichier sans rien remplir :
   correspondance des colonnes, répartition proposée des composants entre les blocs du
   projet (le fichier d'une équipe les nomme rarement ainsi), informations manquantes et
   questions. On répond, puis l'IA rend le classeur complété et la liste des lignes qu'elle
   a ignorées, trouvées douteuses ou regroupées.
4. On dépose le classeur rendu comme n'importe quel fichier d'équipe. Rien n'est écrit
   avant la revue : c'est là qu'on corrige ce que l'IA a mal compris, en refusant une ligne
   ou une valeur à créer.

La consigne dépend du projet : la recopier après avoir ajouté un bloc, une valeur de liste
ou une caractéristique. Mieux vaut convertir un premier extrait d'une vingtaine de lignes,
le relire dans l'écran de revue, puis le fichier entier.

Les doublons sont repérés en trois temps : même référence fabricant une fois normalisée,
référence de l'un citée dans le texte de l'autre, puis ressemblance des libellés. Deux
libellés qui ne diffèrent que par un nombre (« convertisseur 12 V » et « convertisseur
24 V ») ne sont jamais proposés à la fusion, seulement signalés.

## Suivre le projet

Le tableau de bord ne se saisit pas, il se lit : coût estimé, marge sur budget, lignes à
chiffrer, montant engagé et reste à engager, une jauge de consommation du budget, le coût
par bloc, les dix composants les plus coûteux, la répartition par mode d'approvisionnement
et une série d'alertes cliquables (commandes en retard, composants bloquants non commandés,
écarts d'affectation, fournisseurs à valider…).

La marge sur budget compare le budget au coût estimé de toute la nomenclature : elle dit si
tout rentrera, une fois tout acheté. Son titre change avec la situation. « Marge
restante », en vert, donne ce qui reste sous le budget ; « Dépassement », en rouge, ce qui
le dépasse ; le montant est toujours positif, suivi de sa part du budget. Une marge nulle
est en orange, comme, sur les cartes de bloc, une marge inférieure à 10 % du budget cible.
Dans les tableaux, où la colonne garde un titre fixe, « Marge » est signée : positive en
vert, négative en rouge quand le budget est dépassé. Le reste à engager, lui, compare le
budget aux seules commandes passées : il dit combien on peut encore commander.

L'écran Blocs donne une carte par bloc avec son coût, son budget cible
modifiable sur place, sa marge restante ou son dépassement, et l'avancement des achats.

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

## Organismes, dossiers et projets

Un serveur suit plusieurs projets, rangés sur trois niveaux : l'organisme (une école, un
département), le dossier (une édition d'une épreuve, par exemple « Épreuve 2027 ») et le
projet (le robot d'une équipe). Organismes et dossiers se créent dans l'application : leur
code d'adresse, choisi à la création, ne change plus ; leur nom, si.

L'administrateur du serveur crée les organismes depuis l'accueil (« Nouvel organisme ») et
range les projets « hors dossier », par exemple le projet d'une instance d'avant cette
version. La page d'un organisme liste ses dossiers et ses administrateurs. Ceux-ci ont l'un
de trois profils, valables dans tous les projets de l'organisme : « Gestion complète »
(administrateur partout, crée dossiers et projets), « Lecture de tous les projets », et
« Achats et stock » (commandes, réceptions, stock, prix et imports, dans tous les blocs).
Un profil ne remplace pas le rôle qu'on a déjà dans un projet : le plus fort des deux
s'applique.

La page d'un dossier présente ses projets en tableau, avec leur avancement, leur budget et
leur engagé (le coût estimé, marqué comme tel, tant que rien n'est engagé). « Nouveau projet » demande le nom d'équipe, le code d'adresse et le préfixe
des identifiants (proposés à partir du nom d'équipe, figés ensuite) et, si l'on veut,
l'adresse de l'administrateur du projet, qui reçoit un lien d'invitation. « Reprendre de »
part d'un autre projet du dossier : le nouveau reçoit ses statuts d'appro et de choix et son
arborescence d'ensembles, sans ses composants, ses commandes, son stock ni ses responsables.
Le nom du projet vient du dossier. Le projet est aussitôt en ligne. Les responsables achats du dossier se
choisissent parmi les membres de ses projets : ils voient le résumé de tous les projets du
dossier, sans pouvoir ouvrir ceux dont ils ne sont pas membres.

Un dossier impose à ses projets une partie de leurs réglages : les blocs (code, nom, ordre,
description), les listes « modes d'approvisionnement », « criticités », « types de
mouvement » et « types de frais », les attributs et leurs valeurs, les champs obligatoires,
la TVA par défaut, l'établissement, ses adresses, son contact achats et son logo, et le nom
du projet. Ces réglages communs se modifient depuis la page du dossier, bouton
« Paramètres communs », dans les mêmes écrans que ceux d'un projet ; chaque modification est
aussitôt recopiée dans tous les projets du dossier. Dans un projet rangé, ils restent
visibles mais ne se modifient plus. Le budget global de chaque projet se fixe sur la page du
dossier, en cliquant sur son montant. Restent propres à chaque projet : le budget cible et
le responsable de chaque bloc, les statuts d'appro et de choix, les ensembles, les
fournisseurs et le préfixe des identifiants, choisi à la création.

Le premier projet existant rangé dans un dossier lui donne ses réglages, sans rien changer
chez lui. Les projets créés ou rangés ensuite reçoivent ceux du dossier. Rien ne se perd
dans un projet : une valeur que le dossier retire mais que le projet utilise est désactivée,
pas supprimée, et un bloc qui porte encore des composants reste en place. Un projet qui a
un attribut de même code mais d'un autre type que celui du dossier ne peut pas y être rangé
tant que la différence n'est pas réglée. Sorti d'un dossier, un projet garde ses réglages,
redevenus les siens. La colonne « Réglages communs » de la page du dossier dit si chaque
projet est à jour.

La case « Mettre en commun les composants », dans le panneau Dossier, autorise chaque équipe
du dossier à se voir proposer, à la création d'un composant, les références des autres
équipes (voir « Saisir les composants »). Seuls les administrateurs de l'organisme au profil
« Gestion complète » la règlent ; elle est décochée à la création d'un dossier. Aucune liste
n'est montrée en entier, et quantités, commandes et identifiants restent propres à chaque
équipe. Les membres des projets voient sur la page du dossier si elle est active.

Les fournisseurs sont communs à tout l'organisme. Leur liste se tient depuis la page de
l'organisme, bouton « Fournisseurs », par ses administrateurs aux profils « Gestion
complète » et « Achats et stock » : création, fiches, validation, renommage, archivage,
comparaison avec un classeur. Chaque modification est recopiée dans tous les projets de
l'organisme, où la liste se consulte sans se modifier ; un fournisseur nouveau s'ajoute donc
d'abord à la liste de l'organisme. Un renommage suit les composants et les commandes de
chaque projet. Un fournisseur retiré de la liste reste archivé dans les projets qui le
citent. Au rangement d'un projet, ses fournisseurs absents de la liste la rejoignent ; pour
un nom déjà présent, majuscules et accents mis à part, la fiche de l'organisme fait foi.

### Les commandes communes

Une commande commune regroupe chez un même fournisseur les besoins de plusieurs projets du
dossier, pour ne payer qu'une fois le port ou atteindre un minimum de commande. Elle se
gère depuis la page du dossier, panneau « Commandes communes », par les responsables
achats du dossier et les administrateurs de l'organisme aux profils « Gestion complète » et
« Achats et stock ». Les autres la consultent.

« Nouvelle commande commune » demande le fournisseur, pris dans la liste de l'organisme. Sur
la page de la commande, « Ajouter des composants » propose, projet par projet, les
composants de ce fournisseur qui restent à commander, avec la quantité qui manque ; on coche
ceux qu'on prend. Un composant d'un autre fournisseur s'ajoute à la main, en choisissant le
projet puis le composant. Un projet rejoint la commande avec sa première ligne. Les lignes
se modifient, s'annulent ou se suppriment depuis la même page ; les frais (livraison,
douane…) s'y ajoutent aussi.

Chaque projet présent a dans ses achats sa propre commande, marquée « Commune CC-003 ». Elle
porte ses seules lignes, sa part des frais et sa part du montant réel, et compte dans son
engagé comme toute commande. Elle s'y consulte sans se modifier. Les frais se partagent à
parts égales entre les projets qui ont au moins une ligne non annulée. Le montant réel, saisi
dans « Modifier » une fois connu, se répartit au prorata de l'estimé de chaque projet, ses
lignes plus sa part des frais : avec 300 € de lignes pour un projet, 100 € pour l'autre et
20 € de port, un réel de 410 € donne 302,62 € et 107,38 €. Une ligne sans prix compte pour
zéro dans l'estimé et la page la signale. Le statut « Livré » se déduit des réceptions et ne
se choisit pas.

Une commande commune passée se reçoit des deux côtés. Sur sa page, « Réceptionner » montre
les lignes de tous les projets ; chacune entre dans le stock de son projet. Dans un projet,
« Réceptionner » sur sa propre commande reçoit ses seules lignes. Une ligne reçue d'un côté
ne peut pas l'être une seconde fois de l'autre : si une réception est passée entre
l'ouverture de la saisie et sa validation, Nomentrace la refuse et demande de recharger la
page. La commande d'un projet passe à « Livré » quand ses lignes sont reçues ; la commande
commune, quand toutes le sont.

Les documents (devis, bon de commande, facture) se joignent sur la page de la commune. Chacun
est joint à la commande de chaque projet présent, où il se consulte avec elle et depuis la
fiche de ses composants ; un projet qui rejoint la commande plus tard le reçoit aussi. La
demande de devis, en PDF ou en Excel, reprend les articles de tous les projets, un même
article regroupé avec la somme des quantités.

Une commande commune se transmet au suivi de l'établissement depuis sa page, puis passe par
le bouton « Suivi de l'établissement » du panneau des commandes communes, sur la page du
dossier : on y envoie le classeur, comme pour un projet. La commune y figure par ses lignes de
composants, une par ligne de chaque projet, et par ses frais ; les commandes des projets n'y
figurent pas, pour que l'établissement ne voie pas deux fois la même ligne. Au retour, si
l'établissement a mis un montant sur chaque ligne de la commune, la part de chaque projet est
la somme de ses lignes, plus sa part des frais ; sinon, le montant lu est un total, réparti au
prorata de l'estimé. La page de la commune dit quelle règle s'applique.

Un projet qui a des lignes dans une commande commune active ne peut pas quitter son
dossier : annuler ses lignes ou archiver la commande d'abord. Si un projet présent est hors
ligne, la page le signale et la répartition attend son retour.

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

« Nouvel utilisateur » avec l'adresse d'un compte qui existe déjà, dans un autre projet ou
un organisme, lui ouvre simplement le projet : il garde son mot de passe. « Retirer » lui
ferme le projet sans toucher à son compte. Le nom, le mot de passe et l'activation d'un
compte qui a des droits ailleurs ne se règlent pas depuis un projet, mais par
l'administrateur du serveur.

## Exporter, sauvegarder, restaurer

L'export Excel de toute la base, les sauvegardes, l'archive complète et la corbeille des
documents se gèrent dans Paramètres › Export et sauvegardes. Seul l'administrateur y voit
les sauvegardes, l'archive et la corbeille, qui contiennent toute la base ; les autres y
trouvent l'Excel global. Leur fonctionnement, et la restauration depuis une archive, sont
décrits dans [EXPLOITATION.md](EXPLOITATION.md).
