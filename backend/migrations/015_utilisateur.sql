-- 015 : l'outil devient multi-utilisateur. Chaque ligne du journal et chaque fichier
-- importé portent l'utilisateur qui les a produits : son nom affiché au moment de
-- l'écriture, figé, puisque les comptes vivent dans une autre base (aucune clé étrangère
-- ne traverse deux bases). Les lignes antérieures restent vides.

ALTER TABLE journal ADD COLUMN utilisateur TEXT;
ALTER TABLE import_lot ADD COLUMN utilisateur TEXT;
