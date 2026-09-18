-- 002 : vues de calcul.
-- Aucun ROUND() ici : l'arrondi se fait à la sortie de l'API ou de l'export.
-- Définitions : docs/MODELE.md, section « Définitions de calcul communes ».

-- Lignes des commandes engagées : type Commande, statut Commande, Livre partiel ou
-- Livre, non archivées, hors lignes annulées. C'est la seule base de qte_commandee,
-- qte_recue et des montants engagés : un devis n'engage rien.
CREATE VIEW v_ligne_engagee AS
SELECT l.*
FROM ligne_commande l
JOIN commande c ON c.numero = l.commande_numero
WHERE c.archive = 0
  AND c.type = 'Commande'
  AND c.statut IN ('Commande', 'Livre partiel', 'Livre')
  AND l.statut_ligne <> 'Annulee';

CREATE VIEW v_composant AS
WITH
achats AS (
    SELECT composant_id,
           SUM(qte_commandee)                          AS qte_commandee,
           SUM(qte_recue)                              AS qte_recue,
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
base AS (
    SELECT c.*,
           MAX(0, c.qte_besoin + c.qte_rechange - c.qte_dispo_ecole) AS qte_a_acheter,
           CASE WHEN c.base_prix_releve = 'TTC' THEN c.pu_releve / (1 + c.taux_tva)
                ELSE c.pu_releve END                                  AS pu_ht,
           COALESCE(ac.qte_commandee, 0)       AS qte_commandee,
           COALESCE(ac.qte_recue, 0)           AS qte_recue,
           COALESCE(ac.montant_commande_ht, 0) AS montant_commande_ht,
           COALESCE(s.stock_actuel, 0)         AS stock_actuel,
           COALESCE(af.qte_affectee, 0)        AS qte_affectee,
           COALESCE(af.nb_ensembles, 0)        AS nb_ensembles
    FROM composant c
    LEFT JOIN achats ac ON ac.composant_id = c.id
    LEFT JOIN stock s   ON s.composant_id = c.id
    LEFT JOIN affect af ON af.composant_id = c.id
    WHERE c.archive = 0
)
SELECT b.*,
       b.pu_ht * (1 + b.taux_tva) AS pu_ttc,
       CASE WHEN b.mode_appro = 'Achat' THEN b.qte_a_acheter * b.pu_ht ELSE 0 END
           AS total_ht,
       CASE WHEN b.mode_appro = 'Achat' THEN b.qte_a_acheter * b.pu_ht * (1 + b.taux_tva)
            ELSE 0 END
           AS total_ttc,
       b.qte_besoin - b.qte_affectee                AS ecart_affectation,
       MAX(0, b.qte_a_acheter - b.qte_commandee)    AS reste_a_commander,
       MAX(0, b.qte_commandee - b.qte_recue)        AS reste_a_recevoir,
       CASE WHEN b.mode_appro = 'Achat' AND b.pu_releve IS NULL THEN 1 ELSE 0 END
           AS a_chiffrer,
       CASE WHEN b.mode_appro <> 'Achat' OR b.qte_a_acheter = 0 THEN 'Hors achat'
            WHEN b.qte_recue >= b.qte_a_acheter THEN 'Recu'
            WHEN b.qte_commandee > 0 THEN 'Commande'
            ELSE 'A commander' END                  AS avancement
FROM base b;

CREATE VIEW v_bloc AS
SELECT bl.code,
       bl.nom,
       bl.ordre,
       bl.responsable,
       bl.description,
       bl.budget_cible_ht,
       COUNT(v.id)                                   AS nb_composants,
       COALESCE(SUM(v.a_chiffrer), 0)                AS nb_a_chiffrer,
       TOTAL(v.total_ht)                             AS cout_ht,
       TOTAL(v.total_ttc)                            AS cout_ttc,
       TOTAL(v.montant_commande_ht)                  AS montant_engage_ht,
       TOTAL(v.total_ht) - bl.budget_cible_ht        AS ecart_budget,
       (TOTAL(v.total_ht) - bl.budget_cible_ht) * 100.0 / NULLIF(bl.budget_cible_ht, 0)
                                                     AS ecart_pct,
       COUNT(CASE WHEN v.avancement = 'Recu' THEN 1 END)        AS nb_recus,
       COUNT(CASE WHEN v.avancement = 'A commander' THEN 1 END) AS nb_a_commander,
       COUNT(CASE WHEN v.avancement = 'Recu' THEN 1 END) * 100.0
           / NULLIF(COUNT(CASE WHEN v.avancement <> 'Hors achat' THEN 1 END), 0)
                                                     AS avancement_pct
FROM bloc bl
LEFT JOIN v_composant v ON v.bloc_code = bl.code
GROUP BY bl.code;

CREATE VIEW v_ensemble_composant AS
WITH montage AS (
    -- Sens inverse du stock : une Sortie montage est une pièce montée.
    SELECT ensemble_code, composant_id,
           SUM(CASE type_mouvement WHEN 'Sortie montage' THEN qte
                                   WHEN 'Retour montage' THEN -qte
                                   ELSE 0 END) AS qte_montee
    FROM mouvement_stock
    WHERE ensemble_code IS NOT NULL
    GROUP BY ensemble_code, composant_id
)
SELECT a.id                            AS affectation_id,
       a.ensemble_code,
       e.nom                           AS ensemble_nom,
       a.composant_id,
       v.designation,
       v.bloc_code,
       a.qte                           AS qte_affectee,
       v.pu_ht,
       a.qte * v.pu_ht                 AS cout_ligne_ht,
       COALESCE(m.qte_montee, 0)       AS qte_montee,
       a.qte - COALESCE(m.qte_montee, 0) AS reste_a_monter,
       v.statut_appro,
       v.avancement,
       v.stock_actuel,
       a.commentaire
FROM affectation a
JOIN ensemble e    ON e.code = a.ensemble_code AND e.archive = 0
JOIN v_composant v ON v.id = a.composant_id
LEFT JOIN montage m ON m.ensemble_code = a.ensemble_code
                   AND m.composant_id = a.composant_id;

CREATE VIEW v_ensemble AS
SELECT e.code,
       e.nom,
       e.ordre,
       e.parent_code,
       e.description,
       e.responsable,
       e.statut_montage,
       COUNT(ec.composant_id)                          AS nb_composants_distincts,
       COALESCE(SUM(ec.qte_affectee), 0)               AS nb_pieces_total,
       TOTAL(ec.cout_ligne_ht)                         AS cout_ht,
       COUNT(CASE WHEN ec.composant_id IS NOT NULL AND ec.cout_ligne_ht IS NULL
                  AND ec.avancement <> 'Hors achat' THEN 1 END) AS nb_lignes_non_chiffrees,
       COUNT(DISTINCT ec.bloc_code)                    AS nb_blocs_representes,
       COUNT(CASE WHEN ec.avancement = 'Recu' THEN 1 END)        AS nb_composants_recus,
       COUNT(CASE WHEN ec.avancement = 'A commander' THEN 1 END) AS nb_composants_non_commandes,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) AS nb_pieces_montees,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) * 100.0
           / NULLIF(SUM(ec.qte_affectee), 0)           AS avancement_montage_pct
FROM ensemble e
LEFT JOIN v_ensemble_composant ec ON ec.ensemble_code = e.code
WHERE e.archive = 0
GROUP BY e.code;

CREATE VIEW v_pilotage AS
WITH
param AS (
    SELECT CAST((SELECT valeur FROM parametre WHERE cle = 'budget_ht') AS REAL) AS budget_ht
),
comp AS (
    SELECT COUNT(*)                                                  AS nb_composants,
           COUNT(CASE WHEN mode_appro = 'Achat' THEN 1 END)          AS nb_achat,
           COUNT(CASE WHEN mode_appro = 'Stock ecole' THEN 1 END)    AS nb_stock_ecole,
           COUNT(CASE WHEN mode_appro = 'Fourni PFM' THEN 1 END)     AS nb_fourni_pfm,
           COUNT(CASE WHEN mode_appro = 'Fourni CEA' THEN 1 END)     AS nb_fourni_cea,
           COUNT(CASE WHEN mode_appro = 'Fabrication PFM' THEN 1 END) AS nb_fabrication_pfm,
           COUNT(CASE WHEN statut_choix = 'Acte' THEN 1 END)         AS nb_acte,
           COUNT(CASE WHEN statut_choix = 'A confirmer' THEN 1 END)  AS nb_a_confirmer,
           COUNT(CASE WHEN statut_choix = 'A sourcer' THEN 1 END)    AS nb_a_sourcer,
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
    SELECT (SELECT TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0)) FROM v_ligne_engagee)
         + (SELECT TOTAL(port_ht) FROM commande
            WHERE archive = 0 AND type = 'Commande'
              AND statut IN ('Commande', 'Livre partiel', 'Livre')) AS montant_engage_ht
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
