# Modèle de données de Nomentrace

Ce document décrit la base SQLite d'un projet (`data/projets/<code>/nomentrace.db`) : les
tables, les vues de calcul
et les définitions des indicateurs. Le schéma est construit par les migrations numérotées
de `backend/migrations/` ; la table `schema_version` retient la dernière appliquée.
L'usage des écrans est décrit dans [UTILISATION.md](UTILISATION.md), l'organisation du
code dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Bloc et ensemble : deux découpages différents

Un composant est rangé de deux façons indépendantes.

- **Bloc** : le découpage de suivi du projet (par fonction, par métier, par lot, selon le
  projet). Un seul bloc par composant, choisi à la création et figé dans l'identifiant (`ROB-ALI-003` appartient au bloc `ALI`). Le
  bloc porte un budget cible et sert au suivi budgétaire.
- **Ensemble** : où le composant est monté physiquement. Un composant peut entrer dans
  plusieurs ensembles, ou dans aucun ; le lien, appelé **affectation**, porte une
  quantité.

Exemple : un robot avec un bloc `ALI` (alimentation) et deux ensembles physiques,
« Châssis avant » et « Châssis arrière ».

| Composant | Bloc | Besoin | Affectations |
|---|---|---|---|
| `ROB-ALI-003` Fusible 10 A | ALI | 6 | Châssis avant : 2, Châssis arrière : 4 |
| `ROB-ALI-007` Convertisseur 24→12 V | ALI | 1 | Châssis arrière : 1 |
| `ROB-ALI-009` Batterie de rechange | ALI | 1 | aucune (rangée en stock) |

Le bloc ALI totalise les trois composants et leur coût. Chaque ensemble ne voit que ce
qui y est affecté. L'écart d'affectation du fusible est 6 − (2 + 4) = 0. La batterie sans
affectation n'est pas une anomalie : c'est un état normal.

## Tables

| Table | Rôle | Clé |
|---|---|---|
| `parametre` | Réglages de l'instance : `nom_projet`, `prefixe_id`, `budget_ht`, `taux_tva_defaut`, `champs_obligatoires` (champs de base séparés par des virgules), `champs_obligatoires_portee` (`achat` ou `tous`), stockés en texte. | `cle` |
| `valeur_liste` | Listes paramétrables : `mode_appro`, `statut_appro`, `statut_choix`, `criticite`, `type_mouvement`, `type_frais`. `systeme = 1` : valeur utilisée par les calculs, ni supprimable ni désactivable. `sens` : sens imposé d'un type de mouvement (`Entree`, `Sortie` ou NULL = libre). | `liste`, `code` |
| `bloc` | Blocs, avec `budget_cible_ht` ; `archive` ferme le bloc aux nouveaux composants. | `code` (2 à 4 lettres) |
| `ensemble` | Ensembles physiques, avec `statut_montage` ; `parent_code` désigne l'ensemble parent (un seul, ou aucun pour un ensemble de premier niveau) ; `budget_cible_ht` et `budget_verrouille` pour le budget d'ensemble. | `code` |
| `fournisseur` | Fournisseurs : catégorie, contact pour les devis, numéro de compte client, site, délai, `statut` (`Valide` ou `A valider` : trouvé par l'équipe, à compléter et valider). Le renommage se propage (`ON UPDATE CASCADE`). | `nom` |
| `composant` | Le cœur : quantités, prix relevé, statuts ; `remplace_par` désigne le remplaçant d'un composant reclassé. | `id` (`PREFIXE-BLOC-NNN`) |
| `attribut` | Caractéristiques paramétrables des composants (tension, matériau…) : `libelle`, `type` (`texte`, `nombre`, `liste`, `booleen`), `unite`, `ordre`, `actif`, `obligatoire`. Code dérivé du libellé et type figés à la création. | `code` |
| `attribut_valeur` | Valeurs possibles d'un attribut de type liste ; renommer ne change que le libellé. | `attribut_code`, `code` |
| `composant_attribut` | Valeur d'un attribut pour un composant : `valeur_nombre` pour le type nombre, `valeur_texte` sinon (texte, code de liste, `1`/`0` pour un booléen). Une seule valeur par couple. | `composant_id`, `attribut_code` |
| `affectation` | Composant × ensemble, avec la quantité. | `id` ; unique (`ensemble_code`, `composant_id`) |
| `commande` | Devis et commandes, avec `taux_tva`. `port_ht` est obsolète et vaut toujours 0 : le port est devenu un frais (migration 018). | `numero` (`CMD-NNN`) |
| `commande` (suivi) | Champs appris du suivi de l'établissement : `date_transmission_suivi`, `montant_commande_ht` (montant réel, frais compris), `date_commande_confirmee`, `livraison_confirmee`, `date_reception_annoncee`, `commentaire_suivi`. | |
| `frais_commande` | Frais d'une commande : `type_frais` (liste paramétrable), `montant_ht`, `commentaire`. | `id` |
| `ligne_commande` | Lignes d'une commande : quantités commandée et reçue, `pu_ht_devis`. | `id` |
| `mouvement_stock` | Entrées et sorties de stock, montages (avec `ensemble_code`). | `id` |
| `visa` | Visa d'un composant par un responsable : `vise_par` (nom affiché), `vise_le`, `modifie_le_vise` (date de modification du composant quand le visa a été posé). Le visa vaut tant que `modifie_le_vise` égale `composant.modifie_le` ; un composant sans visa valable est « à voir ». | `composant_id` |
| `logo` | Logo de l'établissement repris dans les demandes de devis : une ligne au plus (`id = 1`), `type_mime` (`image/png` ou `image/jpeg`), `contenu` (l'image, gardée en base pour partir avec les sauvegardes), `largeur` et `hauteur` en pixels. | `id` |
| `document` | Fichiers joints (devis, factures…) rangés dans `echange/documents/`, rattachés à une commande et/ou un composant. | `id` |
| `import_lot`, `import_ligne` | Dépôts de fichiers d'équipe et leurs lignes analysées, en attente ou appliquées ; `import_lot.utilisateur` nomme qui a déposé le fichier dans l'outil. | `id` |
| `journal` | Historique de toutes les modifications : table, clé, champ, ancienne et nouvelle valeur, origine (`interface` ou `import`), lot d'import éventuel, `utilisateur` (nom affiché de l'auteur au moment de l'écriture, `local` en mode local, vide avant la migration 015). | `id` |

Composants, blocs, ensembles, commandes et fournisseurs portent une colonne `archive` qui
les retire des listes et des calculs ; l'historique reste. Un bloc archivé n'accepte plus
de nouveau composant.

La suppression physique est réservée à ce qui n'a laissé aucune trace (écran Nettoyage) :

| Élément | Supprimable si | Part avec lui |
|---|---|---|
| Composant | aucune ligne de commande, aucun mouvement de stock, aucun document, aucun reclassement | ses affectations |
| Commande | aucune ligne reçue, aucun mouvement de stock lié | ses lignes et ses documents ; leurs fichiers vont à la corbeille (`echange/documents/_corbeille/`) |
| Fournisseur | cité par aucun composant ni aucune commande, archivés compris | — |
| Bloc | aucun composant, archivés compris | — |
| Ensemble | aucune affectation, aucun mouvement de montage, aucun sous-ensemble | — |

Chaque suppression prend d'abord une sauvegarde de la base et laisse une ligne de journal
(champ `suppression`, ancienne valeur = résumé JSON de la ligne supprimée). Vider le
journal (après sauvegarde) le laisse avec une seule ligne, qui trace la purge.

**Reclassement.** Le bloc est figé dans l'identifiant : reclasser un composant dans un
autre bloc crée un nouveau composant (nouvel identifiant, mêmes données). L'ancien est
archivé et sa colonne `remplace_par` désigne le nouveau. Ses affectations et ses documents
propres (fiche technique, plan, photo) passent au nouveau, le fichier restant où il est ;
ses commandes et son stock lui restent. La migration 016 a rattaché de même les documents
des composants reclassés auparavant.

Des déclencheurs refusent, sur `composant` et `mouvement_stock`, une valeur absente de
`valeur_liste`. Les listes figées (statuts de commande, de ligne, de montage, base de
prix HT/TTC, sens) sont des contraintes `CHECK`.

## Vues

Les calculs métier vivent dans des vues, en pleine précision : **aucune vue n'arrondit**.
L'arrondi à deux décimales se fait une seule fois, dans la réponse de l'API ou dans
l'export.

| Vue | Contenu |
|---|---|
| `v_composant` | Chaque composant non archivé avec ses quantités calculées, prix HT/TTC, totaux, avancement. |
| `v_ligne_engagee` | Lignes non annulées des commandes engagées. |
| `v_bloc` | Par bloc : nombre de composants, à chiffrer, coût HT/TTC, engagé, écart au budget cible, avancement. |
| `v_ensemble` | Par ensemble : composants distincts, pièces, coût, avancement d'appro et de montage, sur ses affectations seules (indicateurs « propres »). |
| `v_ensemble_descendant` | Chaque ensemble face à lui-même et à tous ses descendants non archivés (requête récursive). |
| `v_ensemble_cumul` | Mêmes indicateurs que `v_ensemble`, « cumulés » : l'ensemble et tous ses descendants, plus le nombre de sous-ensembles. |
| `v_ensemble_bloc_cumul` | Répartition par bloc d'un ensemble et de ses descendants. |
| `v_ensemble_composant` | Chaque affectation avec coût matière de ligne, part à dépenser, quantité montée, reste à monter. |
| `v_ensemble_bloc` | Répartition de chaque ensemble par bloc. |
| `v_incoherence` | Signalements : sur-affectation, affecté non commandé, monté au-delà de l'affectation, monté sans affectation. |
| `v_commande` | Commandes avec montant des articles, totaux HT/TTC, indicateurs `engagee` et `en_retard`. |
| `v_stock` | Composants dont le stock n'est pas nul, avec leur valeur. |
| `v_repartition_liste` | Nombre de composants et coût par valeur de liste (graphiques). |
| `v_pilotage` | Une ligne : tous les indicateurs du tableau de bord. |
| `v_attribut_composant` | Chaque composant non archivé face à chaque attribut, avec sa valeur ou rien : base de la répartition des valeurs (écran Attributs). |
| `v_qualite_composant` | Chaque composant, archivés compris : contrôles de qualité (désignation trop courte, fonction vide, achat sans prix ou sans fournisseur, besoin nul, lien invalide, valeur de liste désactivée, fournisseur archivé) et traces qui interdisent sa suppression. Les doublons probables sont repérés à part, par le moteur de l'import. |

## Valeurs autorisées

Deux sortes de listes.

**Listes figées**, qui pilotent le fonctionnement de l'outil (contraintes CHECK) :

```
base_prix_releve  HT | TTC
commande.type     Devis | Commande
commande.statut   A demander | Devis demande | Devis recu | Devis valide | Commande |
                  Livre partiel | Livre | Refuse
statut_ligne      A commander | Commandee | Recue partiel | Recue | Annulee
sens              Entree | Sortie
statut_montage    Non commence | En cours | Monte | Valide
```

**Listes paramétrables**, propres au projet suivi, dans la table `valeur_liste` et gérées
depuis l'écran Paramètres : `mode_appro`, `statut_appro`, `statut_choix`, `criticite`,
`type_mouvement` (avec son sens imposé, ou libre), `type_frais`. Des déclencheurs refusent une valeur
absente de la liste ; l'API refuse en plus une valeur désactivée pour une nouvelle saisie.
Le code stocké ne change jamais : renommer une valeur ne modifie que son libellé.

Valeurs **système**, dont dépendent les calculs et les vues : ni supprimables ni
désactivables, code figé.

```
mode_appro        Achat
statut_appro      Non lance (valeur par défaut)
criticite         Bloquant
type_mouvement    Reception achat (Entree) | Sortie montage (Sortie) |
                  Retour montage (Entree) | Inventaire (sens libre)
```

Aucune valeur propre à un projet n'est écrite dans le code : le vocabulaire d'une instance
est une donnée, saisie dans l'écran Paramètres.

## Définitions de calcul communes

Quantités et prix d'un composant (`v_composant`) :

```
qte_a_acheter      = MAX(0, qte_besoin + qte_rechange - qte_disponible)
pu_ht              = pu_releve / (1 + taux_tva)   si base_prix_releve = 'TTC'
                     pu_releve                    sinon
pu_ttc             = pu_ht * (1 + taux_tva)
total_ht           = qte_a_acheter * pu_ht        si mode_appro = 'Achat', sinon 0
qte_commandee      = somme des qte_commandee des lignes engagées
qte_recue          = somme des qte_recue des lignes engagées
stock_actuel       = somme des mouvements (Entree en +, Sortie en -)
qte_affectee       = somme des quantités d'affectation (ensembles non archivés)
ecart_affectation  = qte_besoin - qte_affectee
reste_a_commander  = MAX(0, qte_a_acheter - qte_commandee)
reste_a_recevoir   = MAX(0, qte_commandee - qte_recue)
a_chiffrer         = mode_appro = 'Achat' et pu_releve absent
```

Avancement d'un composant, évalué dans cet ordre :

```
'Hors achat'   si mode_appro <> 'Achat' ou qte_a_acheter = 0
'Recu'         si qte_recue >= qte_a_acheter
'Commande'     si qte_commandee > 0
'A commander'  sinon
```

Commandes :

```
commande engagée   = non archivée, type 'Commande', statut 'Commande', 'Livre partiel'
                     ou 'Livre' ; ses lignes 'Annulee' sont exclues
commande en cours  = non archivée, statut 'Devis demande', 'Devis recu', 'Devis valide',
                     'Commande' ou 'Livre partiel'
commande en retard = non archivée, livraison_annoncee dépassée, pas de date de
                     réception réelle, statut ni 'Livre' ni 'Refuse'
```

Budget et pilotage (`v_pilotage`, `v_bloc`) :

```
cout_ht              = somme des total_ht                  (coût estimé)
montant_engage_ht    = global  : par commande engagée, montant_commande_ht s'il est connu
                       (montant réel saisi par l'établissement), sinon lignes + frais
                       par bloc : lignes engagées seules (les frais ne sont pas ventilés,
                       la somme des blocs peut donc être inférieure au global)
reste_a_engager_ht   = budget_ht - montant_engage_ht       (peut être négatif)
consommation_pct     = cout_ht / budget_ht * 100           (estimé, pas engagé)
ecart_budget_ht      = cout_ht - budget_ht                 (positif = dépassement)
ecart_budget_pct     = ecart_budget_ht / budget_ht * 100
                       (l'interface affiche la marge, budget - coût = -ecart_budget_ht :
                        « Marge restante » ou « Dépassement », marge signée en tableau)
bloquant ouvert      = criticite 'Bloquant' et avancement 'A commander' ou 'Commande'
valeur_stock         = somme de MAX(stock_actuel, 0) * pu_ht
avancement_appro_pct = nb 'Recu' / nb dont avancement <> 'Hors achat' * 100
```

Coût et dépense d'un ensemble (`v_ensemble_composant`, sommés dans `v_ensemble`,
`v_ensemble_cumul` et les répartitions par bloc) :

```
cout_ligne_ht        = qte_affectee * pu_ht              (coût matière, stock compris)
part_achetee         = 0 si mode_appro <> 'Achat'
                       sinon MAX(0, qte_besoin - qte_disponible) / qte_besoin
                       (besoin nul : 0 s'il y a du stock, 1 sinon)
depense_ligne_ht     = cout_ligne_ht * part_achetee      (NULL sans prix)
cout_ht, depense_ht  = sommes des lignes de l'ensemble (propre) ou de sa branche (cumul)
```

Le stock déjà disponible couvre d'abord le besoin, et chaque ensemble en profite au
prorata de ses pièces : un moteur à 20 € HT, besoin 10, 4 disponibles, affecté 6 à A et 4
à B, coûte 120 € et 80 € en matière, et fait dépenser 72 € et 48 €, soit les 120 € achetés.
La rechange n'est affectée à aucun ensemble : elle reste dans la dépense du projet
(`total_ht`), pas dans celle des ensembles.

Montage (`v_ensemble_composant`, `v_ensemble`) :

```
qte_montee           = mouvements 'Sortie montage' - 'Retour montage' vers l'ensemble
reste_a_monter       = qte_affectee - qte_montee
nb_pieces_montees    = somme de MIN(MAX(qte_montee, 0), qte_affectee)
```

Toute division par zéro (budget nul, rien à acheter) donne NULL, affiché « — », jamais 0.

## Arborescence et budgets d'ensemble

Un ensemble a au plus un parent. La racine de l'arbre n'est pas stockée : c'est un nœud
virtuel qui porte le nom du projet (`parametre.nom_projet`) et rassemble les ensembles de
premier niveau. La profondeur est libre. Le service refuse un cycle (un ensemble ne peut
pas devenir le descendant de lui-même) et un parent archivé ; un ensemble qui a des
sous-ensembles non archivés ne peut pas être archivé.

Les affectations restent propres à chaque ensemble. Ses indicateurs sont donnés deux
fois : « propres » (`v_ensemble`, ses affectations seules) et « cumulés »
(`v_ensemble_cumul`, lui et tous ses descendants). Dans le cumul, un composant affecté à
plusieurs nœuds de la branche compte une fois parmi les composants distincts, mais toutes
ses pièces et tout son coût comptent.

Le budget d'un ensemble est un découpage du budget du projet parallèle aux budgets de
bloc : les deux découpent le même budget total, l'un par partie physique, l'autre par
fonction. Il est réparti à chaque niveau, en partant de la racine (budget de la racine =
`parametre.budget_ht`) :

```
1. un enfant verrouillé (budget_verrouille = 1) garde son budget_cible_ht ;
2. les composants affectés directement au parent prennent leur coût estimé (cout_ht
   propre), rien de plus ;
3. reste = budget du parent - budgets verrouillés - coût propre, partagé à parts égales
   entre les enfants non verrouillés, qu'ils portent des composants ou non ; sans
   enfant non verrouillé, le reste demeure au parent ;
4. si verrouillés et coût propre dépassent le budget du parent (tolérance 0,01 €), les
   non verrouillés reçoivent 0 et le dépassement est signalé sur le parent.
part propre du budget = coût propre (+ le reste s'il n'y a aucun enfant non verrouillé)
ecart_depense_ht      = dépense cumulée - budget de l'ensemble   (positif = dépassement)
ecart_budget_ht       = coût matière cumulé - budget de l'ensemble
```

La répartition s'appuie sur le coût matière ; l'interface compare le budget d'abord au
montant à dépenser, puis au coût matière.

Sans budget de projet, seuls les ensembles verrouillés ont un budget, et leurs
descendants. Un budget verrouillé exige un montant saisi ; déverrouillé, le montant saisi
est conservé mais ignoré.

**Exception à la règle des vues** : ce budget n'est pas calculé par une vue SQL, parce
qu'une répartition récursive s'y exprime mal. Il est recalculé à chaque
lecture, sans arrondi et sans rien stocker, par `backend/services/ensembles_arbre.py`.

## Base commune

Les comptes et le registre des projets vivent dans une base SQLite séparée
(`data/comptes.db`), avec ses propres migrations dans `backend/migrations_comptes/`. Aucune
clé étrangère ne la relie aux bases des projets : le journal garde le nom de l'auteur tel
qu'il était, en texte. Plusieurs projets partagent ainsi les mêmes comptes, et la
restauration de la base d'un projet ne touche pas aux comptes.

| Table | Rôle | Clé |
|---|---|---|
| `utilisateur` | Identité interne : `identifiant` (adresse mail, jamais utilisée pour écrire), `nom` affiché, unique, `actif`, `derniere_connexion`. | `id` |
| `identite` | Moyens de connexion d'un utilisateur. Seul `mot_de_passe` existe : `secret` est l'empreinte scrypt `scrypt$N$r$p$sel$hash`. Une connexion par un compte externe s'ajoutera ici. | `id` ; unique (`fournisseur`, `sujet`) |
| `acces` | Rôle d'un utilisateur dans un projet (`lecteur`, `contributeur`, `administrateur`). Sans ligne, le projet lui est fermé. | `utilisateur_id`, `projet` |
| `utilisateur_bloc` | Blocs dont un contributeur modifie les composants. | `utilisateur_id`, `projet`, `bloc_code` |
| `utilisateur_permission` | Permissions en plus d'un contributeur : `achats`, `ensembles`, `attributs`. | `utilisateur_id`, `projet`, `permission` |
| `invitation` | Liens d'invitation : empreinte SHA-256 du jeton, `expire_le` (72 heures), `utilisee_le`. | `id` |
| `session` | Sessions ouvertes : empreinte SHA-256 du jeton du cookie, `expire_le` (14 jours), adresse IP. | `empreinte` |
| `projet` | Registre des projets servis : `code` (minuscules, chiffres et tirets, 40 au plus), `dossier` (vide : hors dossier), `nom_equipe`, `cree_le`, `archive`. Chaque projet inscrit a sa base `data/projets/<code>/nomentrace.db` et son dossier `echange/projets/<code>/`. | `code` |
| `organisme` | Organisme : `code` d'adresse (`/o/<code>/`), `nom`, `archive`. | `code` |
| `dossier` | Dossier d'un organisme : `code` d'adresse (`/d/<code>/`), `organisme`, `nom`, `nom_projet` (donné aux projets créés dans le dossier), `archive`. | `code` |
| `acces_organisme` | Profil d'un compte dans un organisme : `gestion`, `lecture` ou `achats_stock`. | `utilisateur_id`, `organisme` |
| `acces_dossier` | Rôle d'un compte dans un dossier : `responsable_achats`. | `utilisateur_id`, `dossier` |

Le code d'un projet est celui de son adresse, `/p/<code>/`, et celui que portent `acces`,
`utilisateur_bloc` et `utilisateur_permission`. Il est figé à la création ; le nom du
projet, qui peut changer, reste dans la base du projet. Le projet de l'instance vient de
`NOMENTRACE_PROJET` et est inscrit au premier lancement.

`utilisateur.admin_serveur` désigne l'administrateur du serveur, nommé en ligne de commande.
Le rôle d'un compte dans un projet est le plus fort de son rôle direct (`acces`) et de son
profil dans l'organisme du dossier du projet : `gestion` vaut administrateur, `lecture`
lecteur, `achats_stock` contributeur de tous les blocs avec la permission achats. Blocs et
permissions s'additionnent. L'administrateur du serveur est administrateur partout. Un
projet hors dossier n'hérite d'aucun profil.

`projet.reference` marque le projet de référence d'un dossier, `ref-<dossier>`, créé avec
le dossier : une base au schéma complet, sans composants, absente de l'accueil, qui porte
les réglages communs. Le code d'un dossier compte 30 caractères au plus et le préfixe `ref-`
est réservé.

`projet.organisme` rattache à son organisme la référence `org-<organisme>`, créée avec lui,
qui porte la liste commune des fournisseurs (code d'organisme : 36 caractères au plus,
préfixe `org-` réservé). Dans chaque base, `renommage_fournisseur` journalise, dans une
référence, chaque renommage avec un identifiant aléatoire, et `renommage_applique` garde,
dans un projet, les renommages déjà rejoués chez lui ; la table `fournisseur` d'un projet
rangé est verrouillée par déclencheurs comme les autres réglages imposés.

Dans chaque base de projet, la table `reglages_imposes` (une ligne) porte le verrou des
réglages imposés : `actif` (projet rangé dans un dossier), `propagation` (synchronisation en
cours, posé et retiré dans la même transaction), `dossier`, `empreinte` (empreinte SHA-256
du contenu imposé de la référence appliqué au projet) et, dans une référence,
`initialisee`. Des déclencheurs refusent toute écriture d'un réglage imposé quand le verrou
est posé hors synchronisation : blocs (code, nom, ordre, description, archive), valeurs des
listes `mode_appro`, `criticite`, `type_mouvement`, `type_frais`, attributs et leurs
valeurs, paramètres de l'établissement, TVA, champs obligatoires, nom du projet, budget,
préfixe, logo. Un projet est à jour quand son empreinte égale celle de la référence, relue à
chaque contrôle.

## Commandes communes

Une commande commune d'un dossier a son en-tête et ses frais dans la référence du dossier,
ses lignes dans les projets. Les tables `commune`, `commune_projet` et `frais_commune`
existent dans toute base mais ne sont remplies que dans une référence de dossier.

| Table | Rôle | Clé |
|---|---|---|
| `commune` | En-tête : `numero` (`CC-NNN`), mêmes champs qu'une commande, `version` (augmentée à chaque écriture, ligne comprise), `statut_deduit` et `estime_ht` (recalculés) | `numero` |
| `commune_projet` | Projets présents et numéro local (`CMD-NNN`) de leur copie | `numero`, `projet` |
| `frais_commune` | Frais de la commune, typés comme `frais_commande` | `id` |

Dans chaque projet présent, une commande ordinaire, sa copie, porte `commune` (le numéro
`CC-NNN`) et `version_commune`. Ses lignes sont les seules lignes de ce projet dans la
commune. Tout le reste s'en déduit et y est réécrit par la synchronisation : l'en-tête
recopié, le statut, une ligne de `frais_commande` par frais de la commune pour la part du
projet, et `montant_commande_ht` pour sa part du montant réel. Les vues du projet comptent
la copie comme toute commande, sans changement.

```
n                  = nombre de projets ayant au moins une ligne non annulée
part de frais      = montant du frais / n pour ces projets, 0 pour les autres
estime_projet      = somme(qte_commandee * pu_ht_devis) des lignes non annulées
                     (prix absent : 0) + ses parts de frais
part du réel       = reel * estime_projet / somme des estimés,
                     ou reel / n si la somme des estimés est nulle ;
                     le dernier projet prend le reste : la somme des parts vaut le réel
statut de la copie = statut de la commune, sauf une fois la commune passée (Commande,
                     Livre partiel, Livre) : Livre si toutes ses lignes non annulées sont
                     reçues, Livre partiel si une réception a eu lieu, Commande sinon
```

Les parts sont stockées en pleine précision. Une écriture augmente d'abord la version de la
commune, puis écrit dans le projet, puis synchronise ; une synchronisation n'écrit une
copie que si la version n'a pas bougé depuis sa lecture. Une copie de version inférieure
est rattrapée à l'ouverture de la commune et au démarrage. La table `commune_ecriture` (une
ligne, `ouverte`) porte le verrou : des déclencheurs refusent toute écriture locale sur une
copie, ses lignes, ses frais, ses documents et ses mouvements de stock, hors des écritures
de la commune. Le renommage d'un fournisseur passe, par `ON UPDATE CASCADE`.

## Historique

La frise de la fiche d'un composant est assemblée en Python (`backend/services/historique.py`)
à partir du journal (le composant, ses caractéristiques, ses affectations, ses lignes de
commande, les commandes et leurs documents) et des mouvements de stock ; chaque événement
porte une catégorie : modification, achat, stock, montage, document. L'onglet Paramètres ›
Historique lit le journal entier, filtré et paginé, exportable en Excel.

## Conventions

- Montants en euros, REAL ; budgets et prix de référence en HT, le TTC est toujours
  calculé. Taux de TVA en fraction (0.2 pour 20 %).
- Dates en texte ISO `AAAA-MM-JJ` ; horodatages ISO à la seconde, heure locale.
- Valeurs énumérées stockées sans accents (`Recu`, `Non lance`) ; l'interface affiche le
  libellé accentué.
- Une migration appliquée n'est jamais modifiée. Une migration qui reconstruit une table
  commence par `-- nomentrace: reconstruction` : les clés étrangères sont suspendues puis
  vérifiées, et les vues dépendantes recréées.
