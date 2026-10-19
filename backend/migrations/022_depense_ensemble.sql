-- 022 : coût matière et reste à dépenser d'un ensemble.
-- Le coût matière (cout_ligne_ht, inchangé) vaut toutes les pièces affectées au PU HT, stock
-- interne compris. La dépense (depense_ligne_ht) n'en garde que la part à acheter :
--   * hors mode Achat, rien à dépenser ;
--   * sinon le stock déjà disponible couvre d'abord le besoin, et chaque ensemble en profite
--     au prorata de ses pièces : part achetée = MAX(0, besoin - disponible) / besoin ;
--   * un besoin nul n'achète rien s'il y a du stock, tout sinon.
-- La rechange n'est affectée à aucun ensemble : elle reste dans la dépense du projet seule.
-- Aucun arrondi : il se fait à la sortie de l'API.

DROP VIEW v_incoherence;
DROP VIEW v_ensemble_bloc_cumul;
DROP VIEW v_ensemble_bloc;
DROP VIEW v_ensemble_cumul;
DROP VIEW v_ensemble;
DROP VIEW v_ensemble_composant;

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
       CASE WHEN v.mode_appro <> 'Achat' THEN 0
            WHEN v.qte_besoin > 0
                THEN a.qte * v.pu_ht * MAX(0, v.qte_besoin - v.qte_disponible) * 1.0
                     / v.qte_besoin
            WHEN v.qte_disponible > 0 THEN 0
            ELSE a.qte * v.pu_ht
       END                             AS depense_ligne_ht,
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
       e.budget_cible_ht,
       e.budget_verrouille,
       COUNT(ec.composant_id)                          AS nb_composants_distincts,
       COALESCE(SUM(ec.qte_affectee), 0)               AS nb_pieces_total,
       TOTAL(ec.cout_ligne_ht)                         AS cout_ht,
       TOTAL(ec.depense_ligne_ht)                      AS depense_ht,
       COUNT(CASE WHEN ec.composant_id IS NOT NULL AND ec.cout_ligne_ht IS NULL
                  AND ec.avancement <> 'Hors achat' THEN 1 END) AS nb_lignes_non_chiffrees,
       COUNT(DISTINCT ec.bloc_code)                    AS nb_blocs_representes,
       COUNT(CASE WHEN ec.avancement <> 'Hors achat' THEN 1 END) AS nb_composants_a_acheter,
       COUNT(CASE WHEN ec.avancement = 'Recu' THEN 1 END)        AS nb_composants_recus,
       COUNT(CASE WHEN ec.avancement = 'A commander' THEN 1 END) AS nb_composants_non_commandes,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) AS nb_pieces_montees,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) * 100.0
           / NULLIF(SUM(ec.qte_affectee), 0)           AS avancement_montage_pct
FROM ensemble e
LEFT JOIN v_ensemble_composant ec ON ec.ensemble_code = e.code
WHERE e.archive = 0
GROUP BY e.code;

CREATE VIEW v_ensemble_cumul AS
WITH ligne AS (
    SELECT d.ancetre_code, ec.*
    FROM v_ensemble_descendant d
    JOIN v_ensemble_composant ec ON ec.ensemble_code = d.code
)
SELECT e.code,
       (SELECT COUNT(*) - 1 FROM v_ensemble_descendant x WHERE x.ancetre_code = e.code)
                                                       AS nb_sous_ensembles,
       COUNT(DISTINCT l.composant_id)                  AS nb_composants_distincts,
       COALESCE(SUM(l.qte_affectee), 0)                AS nb_pieces_total,
       TOTAL(l.cout_ligne_ht)                          AS cout_ht,
       TOTAL(l.depense_ligne_ht)                       AS depense_ht,
       COUNT(CASE WHEN l.composant_id IS NOT NULL AND l.cout_ligne_ht IS NULL
                  AND l.avancement <> 'Hors achat' THEN 1 END) AS nb_lignes_non_chiffrees,
       COUNT(DISTINCT l.bloc_code)                     AS nb_blocs_representes,
       COUNT(DISTINCT CASE WHEN l.avancement <> 'Hors achat' THEN l.composant_id END)
                                                       AS nb_composants_a_acheter,
       COUNT(DISTINCT CASE WHEN l.avancement = 'Recu' THEN l.composant_id END)
                                                       AS nb_composants_recus,
       COUNT(DISTINCT CASE WHEN l.avancement = 'A commander' THEN l.composant_id END)
                                                       AS nb_composants_non_commandes,
       COALESCE(SUM(MIN(MAX(l.qte_montee, 0), l.qte_affectee)), 0) AS nb_pieces_montees,
       COALESCE(SUM(MIN(MAX(l.qte_montee, 0), l.qte_affectee)), 0) * 100.0
           / NULLIF(SUM(l.qte_affectee), 0)            AS avancement_montage_pct
FROM ensemble e
LEFT JOIN ligne l ON l.ancetre_code = e.code
WHERE e.archive = 0
GROUP BY e.code;

CREATE VIEW v_ensemble_bloc AS
SELECT ec.ensemble_code,
       ec.bloc_code,
       COUNT(*)                    AS nb_composants,
       SUM(ec.qte_affectee)        AS nb_pieces,
       TOTAL(ec.cout_ligne_ht)     AS cout_ht,
       TOTAL(ec.depense_ligne_ht)  AS depense_ht
FROM v_ensemble_composant ec
GROUP BY ec.ensemble_code, ec.bloc_code;

CREATE VIEW v_ensemble_bloc_cumul AS
SELECT d.ancetre_code              AS ensemble_code,
       ec.bloc_code,
       COUNT(DISTINCT ec.composant_id) AS nb_composants,
       SUM(ec.qte_affectee)        AS nb_pieces,
       TOTAL(ec.cout_ligne_ht)     AS cout_ht,
       TOTAL(ec.depense_ligne_ht)  AS depense_ht
FROM v_ensemble_descendant d
JOIN v_ensemble_composant ec ON ec.ensemble_code = d.code
GROUP BY d.ancetre_code, ec.bloc_code;

CREATE VIEW v_incoherence AS
SELECT 'sur_affecte'           AS type,
       v.id                    AS composant_id,
       NULL                    AS ensemble_code,
       v.designation,
       v.qte_besoin            AS reference,
       v.qte_affectee          AS valeur
FROM v_composant v
WHERE v.nb_ensembles > 0 AND v.qte_affectee > v.qte_besoin
UNION ALL
SELECT 'affecte_non_commande', v.id, NULL, v.designation, v.qte_a_acheter, v.qte_commandee
FROM v_composant v
WHERE v.nb_ensembles > 0 AND v.mode_appro = 'Achat' AND v.avancement = 'A commander'
UNION ALL
SELECT 'monte_plus_qu_affecte', ec.composant_id, ec.ensemble_code, ec.designation,
       ec.qte_affectee, ec.qte_montee
FROM v_ensemble_composant ec
WHERE ec.qte_montee > ec.qte_affectee
UNION ALL
SELECT 'monte_sans_affectation', m.composant_id, m.ensemble_code, c.designation, 0,
       SUM(CASE m.type_mouvement WHEN 'Sortie montage' THEN m.qte ELSE -m.qte END)
FROM mouvement_stock m
JOIN composant c ON c.id = m.composant_id AND c.archive = 0
WHERE m.ensemble_code IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM affectation a
                  WHERE a.ensemble_code = m.ensemble_code AND a.composant_id = m.composant_id)
GROUP BY m.ensemble_code, m.composant_id
HAVING SUM(CASE m.type_mouvement WHEN 'Sortie montage' THEN m.qte ELSE -m.qte END) > 0;
