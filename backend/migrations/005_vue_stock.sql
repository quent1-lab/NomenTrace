-- 005 : état du stock, avec le dernier emplacement connu de chaque composant.

CREATE VIEW v_stock AS
SELECT v.id,
       v.designation,
       v.bloc_code,
       v.stock_actuel,
       v.pu_ht,
       v.stock_actuel * v.pu_ht AS valeur_ht,
       (SELECT m.emplacement FROM mouvement_stock m
        WHERE m.composant_id = v.id AND m.emplacement IS NOT NULL
        ORDER BY m.date DESC, m.id DESC LIMIT 1)          AS emplacement,
       (SELECT MAX(m.date) FROM mouvement_stock m
        WHERE m.composant_id = v.id)                      AS dernier_mouvement
FROM v_composant v
WHERE v.stock_actuel <> 0;
