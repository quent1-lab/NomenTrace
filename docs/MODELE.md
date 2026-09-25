# Modèle de données de Nomentrace

Ce document décrit la base SQLite (`data/nomentrace.db`) : les tables, les vues de calcul
et les définitions des indicateurs. Le schéma est construit par les migrations numérotées
de `backend/migrations/` ; la table `schema_version` retient la dernière appliquée.

## Bloc fonctionnel et ensemble : deux découpages différents

Un composant est rangé de deux façons indépendantes.

- **Bloc fonctionnel** : à quoi sert le composant. Un seul bloc par composant, choisi à
  la création et figé dans l'identifiant (`ROB-ALI-003` appartient au bloc `ALI`). Le
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
| `parametre` | Réglages de l'instance : `nom_projet`, `prefixe_id`, `budget_ht`, `taux_tva_defaut` (stockés en texte). | `cle` |
| `valeur_liste` | Listes paramétrables : `mode_appro`, `statut_appro`, `statut_choix`, `criticite`, `type_mouvement`. `systeme = 1` : valeur utilisée par les calculs, ni supprimable ni désactivable. `sens` : sens imposé d'un type de mouvement (`Entree`, `Sortie` ou NULL = libre). | `liste`, `code` |
| `bloc` | Blocs fonctionnels, avec `budget_cible_ht` ; `archive` ferme le bloc aux nouveaux composants. | `code` (2 à 4 lettres) |
| `ensemble` | Ensembles physiques, avec `statut_montage` ; `parent_code` désigne l'ensemble parent (un seul, ou aucun pour un ensemble de premier niveau) ; `budget_cible_ht` et `budget_verrouille` pour le budget d'ensemble. | `code` |
| `fournisseur` | Fournisseurs : catégorie, contact pour les devis, numéro de compte client, site, délai, `statut` (`Valide` ou `A valider` : trouvé par l'équipe, à compléter et valider). Le renommage se propage (`ON UPDATE CASCADE`). | `nom` |
| `composant` | Le cœur : quantités, prix relevé, statuts ; `remplace_par` désigne le remplaçant d'un composant reclassé. | `id` (`PREFIXE-BLOC-NNN`) |
| `attribut` | Caractéristiques paramétrables des composants (tension, matériau…) : `libelle`, `type` (`texte`, `nombre`, `liste`, `booleen`), `unite`, `ordre`, `actif`. Code dérivé du libellé et type figés à la création. | `code` |
| `attribut_valeur` | Valeurs possibles d'un attribut de type liste ; renommer ne change que le libellé. | `attribut_code`, `code` |
| `composant_attribut` | Valeur d'un attribut pour un composant : `valeur_nombre` pour le type nombre, `valeur_texte` sinon (texte, code de liste, `1`/`0` pour un booléen). Une seule valeur par couple. | `composant_id`, `attribut_code` |
| `affectation` | Composant × ensemble, avec la quantité. | `id` ; unique (`ensemble_code`, `composant_id`) |
| `commande` | Devis et commandes, avec `port_ht` et `taux_tva`. | `numero` (`CMD-NNN`) |
| `ligne_commande` | Lignes d'une commande : quantités commandée et reçue, `pu_ht_devis`. | `id` |
| `mouvement_stock` | Entrées et sorties de stock, montages (avec `ensemble_code`). | `id` |
| `document` | Fichiers joints (devis, factures…) rangés dans `echange/documents/`, rattachés à une commande et/ou un composant. | `id` |
| `import_lot`, `import_ligne` | Dépôts de fichiers d'équipe et leurs lignes analysées, en attente ou appliquées. | `id` |
| `journal` | Historique de toutes les modifications : table, clé, champ, ancienne et nouvelle valeur, origine (`interface` ou `import`), lot d'import éventuel. | `id` |

Composants, blocs, ensembles, commandes et fournisseurs portent une colonne `archive` qui
les retire des listes et des calculs ; l'historique reste. Un bloc archivé n'accepte plus
de nouveau composant.

La suppression physique est réservée à ce qui n'a laissé aucune trace (écran Nettoyage) :

| Élément | Supprimable si | Part avec lui |
|---|---|---|
| Composant | aucune ligne de commande, aucun mouvement de stock, aucun document, aucun reclassement | ses affectations |
| Commande | aucune ligne reçue, aucun mouvement de stock lié | ses lignes, ses documents et leurs fichiers |
| Fournisseur | cité par aucun composant ni aucune commande, archivés compris | — |
| Bloc | aucun composant, archivés compris | — |
| Ensemble | aucune affectation, aucun mouvement de montage, aucun sous-ensemble | — |

Chaque suppression prend d'abord une sauvegarde de la base et laisse une ligne de journal
(champ `suppression`, ancienne valeur = résumé JSON de la ligne supprimée). Vider le
journal (après sauvegarde) le laisse avec une seule ligne, qui trace la purge.

**Reclassement.** Le bloc est figé dans l'identifiant : reclasser un composant dans un
autre bloc crée un nouveau composant (nouvel identifiant, mêmes données). L'ancien est
archivé et sa colonne `remplace_par` désigne le nouveau ; ses affectations passent au
nouveau, ses commandes, son stock et ses documents lui restent.

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
| `v_ensemble_composant` | Chaque affectation avec coût de ligne, quantité montée, reste à monter. |
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
`type_mouvement` (avec son sens imposé, ou libre). Des déclencheurs refusent une valeur
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
montant_engage_ht    = global  : lignes engagées + port_ht des commandes engagées
                       par bloc : lignes engagées seules (le port n'est pas ventilé,
                       la somme des blocs peut donc être inférieure au global)
reste_a_engager_ht   = budget_ht - montant_engage_ht       (peut être négatif)
consommation_pct     = cout_ht / budget_ht * 100           (estimé, pas engagé)
ecart_budget_ht      = cout_ht - budget_ht                 (positif = dépassement)
ecart_budget_pct     = ecart_budget_ht / budget_ht * 100
bloquant ouvert      = criticite 'Bloquant' et avancement 'A commander' ou 'Commande'
valeur_stock         = somme de MAX(stock_actuel, 0) * pu_ht
avancement_appro_pct = nb 'Recu' / nb dont avancement <> 'Hors achat' * 100
```

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
2. reste = budget du parent - somme des budgets verrouillés, réparti entre les enfants
   non verrouillés et la part propre du parent (ses affectations directes), au prorata
   de leur coût estimé cumulé (cout_ht de v_ensemble_cumul ; cout_ht propre pour la
   part propre) ;
3. si tous ces coûts sont nuls : parts égales ; la part propre n'entre dans ce partage
   que si le parent porte des affectations directes ;
4. si les verrouillés dépassent le budget du parent (tolérance 0,01 €), les non
   verrouillés reçoivent 0 et le dépassement est signalé sur le parent.
part propre du budget = reste - somme des parts des enfants non verrouillés
ecart_budget_ht       = coût cumulé - budget de l'ensemble   (positif = dépassement)
```

Sans budget de projet, seuls les ensembles verrouillés ont un budget, et leurs
descendants. Un budget verrouillé exige un montant saisi ; déverrouillé, le montant saisi
est conservé mais ignoré.

**Exception à la règle des vues** : ce budget n'est pas calculé par une vue SQL, parce
qu'une répartition récursive au prorata s'y exprime mal. Il est recalculé à chaque
lecture, sans arrondi et sans rien stocker, par `backend/services/ensembles_arbre.py`.

## Conventions

- Montants en euros, REAL ; budgets et prix de référence en HT, le TTC est toujours
  calculé. Taux de TVA en fraction (0.2 pour 20 %).
- Dates en texte ISO `AAAA-MM-JJ` ; horodatages ISO à la seconde, heure locale.
- Valeurs énumérées stockées sans accents (`Recu`, `Non lance`) ; l'interface affiche le
  libellé accentué.
- Une migration appliquée n'est jamais modifiée. Une migration qui reconstruit une table
  commence par `-- nomentrace: reconstruction` : les clés étrangères sont suspendues puis
  vérifiées, et les vues dépendantes recréées.
