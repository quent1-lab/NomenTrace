-- 004 : vues de l'écran Ensembles.
-- v_ensemble est recréée pour compter les composants réellement à acheter : un composant
-- fourni ou fabriqué ne sera jamais « reçu » et ne doit pas bloquer la barre d'appro.

DROP VIEW v_ensemble;

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

-- Répartition d'un ensemble par bloc fonctionnel : un ensemble physique mélange des pôles.
CREATE VIEW v_ensemble_bloc AS
SELECT ec.ensemble_code,
       ec.bloc_code,
       COUNT(*)                  AS nb_composants,
       SUM(ec.qte_affectee)      AS nb_pieces,
       TOTAL(ec.cout_ligne_ht)   AS cout_ht
FROM v_ensemble_composant ec
GROUP BY ec.ensemble_code, ec.bloc_code;

-- Incohérences signalées sur l'écran Ensembles. Un composant jamais affecté n'y figure
-- pas : c'est un état normal tant que le travail d'affectation n'est pas fait.
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
