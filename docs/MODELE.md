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
| `bloc` | Blocs fonctionnels, avec `budget_cible_ht`. | `code` (2 à 4 lettres) |
| `ensemble` | Ensembles physiques, avec `statut_montage`. | `code` |
| `fournisseur` | Fournisseurs : catégorie, contact pour les devis, numéro de compte client, site, délai, `statut` (`Valide` ou `A valider` : trouvé par l'équipe, à compléter et valider). Le renommage se propage (`ON UPDATE CASCADE`). | `nom` |
| `composant` | Le cœur : quantités, prix relevé, statuts. | `id` (`PREFIXE-BLOC-NNN`) |
| `affectation` | Composant × ensemble, avec la quantité. | `id` ; unique (`ensemble_code`, `composant_id`) |
| `commande` | Devis et commandes, avec `port_ht` et `taux_tva`. | `numero` (`CMD-NNN`) |
| `ligne_commande` | Lignes d'une commande : quantités commandée et reçue, `pu_ht_devis`. | `id` |
| `mouvement_stock` | Entrées et sorties de stock, montages (avec `ensemble_code`). | `id` |
| `document` | Fichiers joints (devis, factures…) rangés dans `echange/documents/`, rattachés à une commande et/ou un composant. | `id` |
| `import_lot`, `import_ligne` | Dépôts de fichiers d'équipe et leurs lignes analysées, en attente ou appliquées. | `id` |
| `journal` | Historique de toutes les modifications : table, clé, champ, ancienne et nouvelle valeur, origine (`interface` ou `import`), lot d'import éventuel. | `id` |

Composants, ensembles, commandes et fournisseurs ne sont jamais supprimés : la colonne
`archive` les retire des listes et des calculs, l'historique reste.

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
| `v_ensemble` | Par ensemble : composants distincts, pièces, coût, avancement d'appro et de montage. |
| `v_ensemble_composant` | Chaque affectation avec coût de ligne, quantité montée, reste à monter. |
| `v_ensemble_bloc` | Répartition de chaque ensemble par bloc. |
| `v_incoherence` | Signalements : sur-affectation, affecté non commandé, monté au-delà de l'affectation, monté sans affectation. |
| `v_commande` | Commandes avec montant des articles, totaux HT/TTC, indicateurs `engagee` et `en_retard`. |
| `v_stock` | Composants dont le stock n'est pas nul, avec leur valeur. |
| `v_repartition_liste` | Nombre de composants et coût par valeur de liste (graphiques). |
| `v_pilotage` | Une ligne : tous les indicateurs du tableau de bord. |

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

## Conventions

- Montants en euros, REAL ; budgets et prix de référence en HT, le TTC est toujours
  calculé. Taux de TVA en fraction (0.2 pour 20 %).
- Dates en texte ISO `AAAA-MM-JJ` ; horodatages ISO à la seconde, heure locale.
- Valeurs énumérées stockées sans accents (`Recu`, `Non lance`) ; l'interface affiche le
  libellé accentué.
- Une migration appliquée n'est jamais modifiée. Une migration qui reconstruit une table
  commence par `-- nomentrace: reconstruction` : les clés étrangères sont suspendues puis
  vérifiées, et les vues dépendantes recréées.
