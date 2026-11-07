-- 028 : composants vendus par lot.
-- Le composant porte la taille de son lot (1 par défaut) et son prix relevé devient celui
-- du lot. Besoin, stock, affectations et montage restent comptés en pièces ; l'achat se
-- fait en lots entiers, le surplus entre au stock.
-- Une ligne de commande compte des lots : `qte_commandee` et `qte_recue` en lots,
-- `pu_ht_devis` au prix d'un lot, et `qte_par_lot` figé à la création de la ligne, pour
-- qu'un changement ultérieur du lot du composant ne réécrive pas les commandes passées.
-- Avec un lot de 1 partout, chaque grandeur de v_composant garde sa valeur.

ALTER TABLE composant
    ADD COLUMN qte_par_lot INTEGER NOT NULL DEFAULT 1 CHECK (qte_par_lot >= 1);

ALTER TABLE ligne_commande
    ADD COLUMN qte_par_lot INTEGER NOT NULL DEFAULT 1 CHECK (qte_par_lot >= 1);

DROP VIEW v_composant;

-- Quantités du composant en pièces (lots × taille du lot de chaque ligne), montant des
-- lignes inchangé (lots × prix d'un lot). Nombre de lots arrondi au supérieur en entiers :
-- (a + l - 1) / l, sans dépendre de la fonction ceil() de SQLite.
CREATE VIEW v_composant AS
WITH
achats AS (
    SELECT composant_id,
           SUM(qte_commandee * qte_par_lot)                AS qte_commandee,
           SUM(qte_recue * qte_par_lot)                    AS qte_recue,
           TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0)) AS montant_commande_ht
    FROM v_ligne_engagee
    GROUP BY composant_id
),
stock AS (
    SELECT composant_id,
           SUM(CASE sens WHEN 'Entree' THEN qte ELSE -qte END) AS stock_actuel
    FROM mouvement_stock
    GROUP BY composant_id
),
affect AS (
    SELECT a.composant_id,
           SUM(a.qte)                       AS qte_affectee,
           COUNT(DISTINCT a.ensemble_code)  AS nb_ensembles
    FROM affectation a
    JOIN ensemble e ON e.code = a.ensemble_code AND e.archive = 0
    GROUP BY a.composant_id
),
prix AS (
    SELECT c.*,
           MAX(0, c.qte_besoin + c.qte_rechange - c.qte_disponible) AS qte_a_acheter,
           CASE WHEN c.base_prix_releve = 'TTC' THEN c.pu_releve / (1 + c.taux_tva)
                ELSE c.pu_releve END                                  AS prix_lot_ht
    FROM composant c
    WHERE c.archive = 0
),
base AS (
    SELECT p.*,
           p.prix_lot_ht / p.qte_par_lot                              AS pu_ht,
           (p.qte_a_acheter + p.qte_par_lot - 1) / p.qte_par_lot      AS nb_lots_a_acheter,
           COALESCE(ac.qte_commandee, 0)       AS qte_commandee,
           COALESCE(ac.qte_recue, 0)           AS qte_recue,
           COALESCE(ac.montant_commande_ht, 0) AS montant_commande_ht,
           COALESCE(s.stock_actuel, 0)         AS stock_actuel,
           COALESCE(af.qte_affectee, 0)        AS qte_affectee,
           COALESCE(af.nb_ensembles, 0)        AS nb_ensembles
    FROM prix p
    LEFT JOIN achats ac ON ac.composant_id = p.id
    LEFT JOIN stock s   ON s.composant_id = p.id
    LEFT JOIN affect af ON af.composant_id = p.id
)
SELECT b.*,
       b.pu_ht * (1 + b.taux_tva) AS pu_ttc,
       CASE WHEN b.mode_appro = 'Achat' THEN b.nb_lots_a_acheter * b.prix_lot_ht ELSE 0 END
           AS total_ht,
       CASE WHEN b.mode_appro = 'Achat'
            THEN b.nb_lots_a_acheter * b.prix_lot_ht * (1 + b.taux_tva) ELSE 0 END
           AS total_ttc,
       b.qte_besoin - b.qte_affectee                AS ecart_affectation,
       MAX(0, b.qte_a_acheter - b.qte_commandee)    AS reste_a_commander,
       (MAX(0, b.qte_a_acheter - b.qte_commandee) + b.qte_par_lot - 1) / b.qte_par_lot
           AS reste_a_commander_lots,
       MAX(0, b.qte_commandee - b.qte_recue)        AS reste_a_recevoir,
       CASE WHEN b.mode_appro = 'Achat' AND b.pu_releve IS NULL THEN 1 ELSE 0 END
           AS a_chiffrer,
       CASE WHEN b.mode_appro <> 'Achat' OR b.qte_a_acheter = 0 THEN 'Hors achat'
            WHEN b.qte_recue >= b.qte_a_acheter THEN 'Recu'
            WHEN b.qte_commandee > 0 THEN 'Commande'
            ELSE 'A commander' END                  AS avancement
FROM base b;
