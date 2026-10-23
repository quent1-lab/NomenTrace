-- 026 : montant réel d'une commande commune lu ligne par ligne (phase 16b).
-- Le suivi de l'établissement donne soit un montant pour toute la commande, réparti au
-- prorata de l'estimé (mode_reel = 'total'), soit un montant sur chacune de ses lignes : la
-- part d'un projet est alors la somme de ses lignes (reel_lignes_ht) plus sa part des frais
-- saisis sur la commune (mode_reel = 'lignes').

ALTER TABLE commune ADD COLUMN mode_reel TEXT NOT NULL DEFAULT 'total'
    CHECK (mode_reel IN ('total', 'lignes'));
ALTER TABLE commune_projet ADD COLUMN reel_lignes_ht REAL CHECK (reel_lignes_ht >= 0);
