-- 012 : nettoyage de la base.
-- Un bloc peut être archivé : il n'est plus proposé à la création de composant.
-- Un composant reclassé dans un autre bloc est archivé et pointe vers son remplaçant.
-- v_qualite_composant calcule les contrôles de qualité et les traces qui empêchent une
-- suppression physique ; le repérage des doublons, lui, se fait en Python.

ALTER TABLE bloc ADD COLUMN archive INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1));
ALTER TABLE composant ADD COLUMN remplace_par TEXT REFERENCES composant(id);

-- v_bloc expose désormais la colonne archive.
DROP VIEW v_bloc;
CREATE VIEW v_bloc AS
SELECT bl.code,
       bl.nom,
       bl.ordre,
       bl.responsable,
       bl.description,
       bl.budget_cible_ht,
       bl.archive,
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

-- Contrôles de qualité de chaque composant, archivés compris (1 = anomalie), et traces
-- qui interdisent sa suppression physique.
CREATE VIEW v_qualite_composant AS
SELECT c.id,
       c.bloc_code,
       c.fonction,
       c.designation,
       c.ref_fabricant,
       c.mode_appro,
       c.fournisseur_nom,
       c.archive,
       c.remplace_par,
       CASE WHEN LENGTH(TRIM(c.designation)) < 4 THEN 1 ELSE 0 END    AS designation_courte,
       CASE WHEN TRIM(c.fonction) = '' THEN 1 ELSE 0 END               AS fonction_vide,
       CASE WHEN c.mode_appro = 'Achat' AND c.pu_releve IS NULL THEN 1 ELSE 0 END
                                                                       AS achat_sans_prix,
       CASE WHEN c.mode_appro = 'Achat' AND c.fournisseur_nom IS NULL THEN 1 ELSE 0 END
                                                                       AS achat_sans_fournisseur,
       CASE WHEN c.qte_besoin = 0 THEN 1 ELSE 0 END                    AS besoin_nul,
       CASE WHEN TRIM(COALESCE(c.lien_produit, '')) <> ''
             AND LOWER(TRIM(c.lien_produit)) NOT LIKE 'http://_%'
             AND LOWER(TRIM(c.lien_produit)) NOT LIKE 'https://_%' THEN 1 ELSE 0 END
                                                                       AS lien_invalide,
       CASE WHEN EXISTS (
                SELECT 1 FROM valeur_liste v
                WHERE v.actif = 0
                  AND ((v.liste = 'mode_appro' AND v.code = c.mode_appro)
                    OR (v.liste = 'statut_appro' AND v.code = c.statut_appro)
                    OR (v.liste = 'statut_choix' AND v.code = c.statut_choix)
                    OR (v.liste = 'criticite' AND v.code = c.criticite)))
            THEN 1 ELSE 0 END                                          AS valeur_desactivee,
       CASE WHEN EXISTS (
                SELECT 1 FROM fournisseur f WHERE f.nom = c.fournisseur_nom AND f.archive = 1)
            THEN 1 ELSE 0 END                                          AS fournisseur_archive,
       (SELECT COUNT(*) FROM ligne_commande l WHERE l.composant_id = c.id) AS nb_lignes_commande,
       (SELECT COUNT(*) FROM mouvement_stock m WHERE m.composant_id = c.id) AS nb_mouvements,
       (SELECT COUNT(*) FROM document d WHERE d.composant_id = c.id)       AS nb_documents,
       (SELECT COUNT(*) FROM composant r WHERE r.remplace_par = c.id)      AS nb_remplaces
FROM composant c;
