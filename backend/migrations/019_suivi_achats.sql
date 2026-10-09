-- 019 : suivi des achats tenu par l'établissement (classeur aller-retour).
-- La commande garde ce que ce suivi lui apprend : date de transmission au suivi, montant réel
-- de la commande (frais compris), dates confirmées ou estimées, réception annoncée,
-- commentaire. Le montant réel, une fois connu, remplace l'estimation dans le montant engagé.

ALTER TABLE commande ADD COLUMN date_transmission_suivi TEXT;
ALTER TABLE commande ADD COLUMN montant_commande_ht REAL CHECK (montant_commande_ht >= 0);
ALTER TABLE commande ADD COLUMN date_commande_confirmee INTEGER NOT NULL DEFAULT 0
    CHECK (date_commande_confirmee IN (0, 1));
ALTER TABLE commande ADD COLUMN livraison_confirmee INTEGER NOT NULL DEFAULT 0
    CHECK (livraison_confirmee IN (0, 1));
ALTER TABLE commande ADD COLUMN date_reception_annoncee TEXT;
ALTER TABLE commande ADD COLUMN commentaire_suivi TEXT;

-- v_commande est relue telle quelle (c.* reprend les nouvelles colonnes) ; v_pilotage change
-- de calcul du montant engagé.
DROP VIEW v_pilotage;
CREATE VIEW v_pilotage AS
WITH
param AS (
    SELECT CAST((SELECT valeur FROM parametre WHERE cle = 'budget_ht') AS REAL) AS budget_ht
),
comp AS (
    SELECT COUNT(*)                                                  AS nb_composants,
           COUNT(CASE WHEN mode_appro = 'Achat' THEN 1 END)          AS nb_achat,
           COUNT(CASE WHEN mode_appro <> 'Achat' THEN 1 END)         AS nb_hors_achat,
           COALESCE(SUM(a_chiffrer), 0)                              AS nb_a_chiffrer,
           COUNT(CASE WHEN criticite = 'Bloquant'
                       AND avancement IN ('A commander', 'Commande') THEN 1 END)
                                                                     AS nb_bloquants_ouverts,
           TOTAL(total_ht)                                           AS cout_ht,
           TOTAL(total_ttc)                                          AS cout_ttc,
           TOTAL(MAX(stock_actuel, 0) * pu_ht)                       AS valeur_stock,
           COUNT(CASE WHEN avancement = 'Recu' THEN 1 END) * 100.0
               / NULLIF(COUNT(CASE WHEN avancement <> 'Hors achat' THEN 1 END), 0)
                                                                     AS avancement_appro_pct,
           COUNT(CASE WHEN qte_affectee = 0 THEN 1 END)              AS nb_composants_non_affectes,
           COUNT(CASE WHEN nb_ensembles > 0 AND ecart_affectation <> 0 THEN 1 END)
                                                                 AS nb_composants_ecart_affectation
    FROM v_composant
),
engage AS (
    -- Par commande engagée : le montant réel saisi par l'établissement s'il est connu,
    -- sinon lignes + frais (v_commande.total_ht).
    SELECT TOTAL(COALESCE(montant_commande_ht, total_ht)) AS montant_engage_ht
    FROM v_commande
    WHERE engagee = 1
),
cmd AS (
    SELECT COUNT(*) AS nb_commandes,
           COUNT(CASE WHEN statut IN ('Devis demande', 'Devis recu', 'Devis valide',
                                      'Commande', 'Livre partiel') THEN 1 END)
               AS nb_commandes_en_cours,
           COUNT(CASE WHEN livraison_annoncee < date('now', 'localtime')
                       AND date_reception_reelle IS NULL
                       AND statut NOT IN ('Livre', 'Refuse') THEN 1 END)
               AS nb_commandes_retard
    FROM commande
    WHERE archive = 0
)
SELECT comp.*,
       param.budget_ht,
       comp.cout_ht - param.budget_ht                                AS ecart_budget_ht,
       (comp.cout_ht - param.budget_ht) * 100.0 / NULLIF(param.budget_ht, 0)
                                                                     AS ecart_budget_pct,
       comp.cout_ht * 100.0 / NULLIF(param.budget_ht, 0)             AS consommation_pct,
       engage.montant_engage_ht,
       param.budget_ht - engage.montant_engage_ht                    AS reste_a_engager_ht,
       cmd.*,
       (SELECT COUNT(*) FROM ensemble WHERE archive = 0)             AS nb_ensembles
FROM comp, param, engage, cmd;
