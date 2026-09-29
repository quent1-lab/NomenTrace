-- Les documents propres à un composant reclassé (fiche technique, plan, photo) décrivent la
-- pièce : ils suivent désormais le remplaçant. Les composants déjà reclassés les reçoivent
-- ici, au bout de la chaîne s'il y a eu plusieurs reclassements. Le fichier ne bouge pas ;
-- chaque changement de rattachement laisse une ligne de journal.
CREATE TEMP TABLE reclassement_final AS
WITH RECURSIVE chaine(origine, cible) AS (
    SELECT id, remplace_par FROM composant WHERE remplace_par IS NOT NULL
    UNION ALL
    SELECT chaine.origine, c.remplace_par
    FROM chaine JOIN composant c ON c.id = chaine.cible
    WHERE c.remplace_par IS NOT NULL
)
SELECT origine, cible FROM chaine
WHERE cible NOT IN (SELECT id FROM composant WHERE remplace_par IS NOT NULL);

INSERT INTO journal (table_cible, cle_cible, champ, ancienne_valeur, nouvelle_valeur,
                     origine, utilisateur)
SELECT 'document', d.id, 'composant_id', d.composant_id, r.cible, 'interface',
       'Nomentrace (mise à jour)'
FROM document d JOIN reclassement_final r ON r.origine = d.composant_id;

UPDATE document
SET composant_id = (SELECT cible FROM reclassement_final WHERE origine = document.composant_id)
WHERE composant_id IN (SELECT origine FROM reclassement_final);

DROP TABLE reclassement_final;
