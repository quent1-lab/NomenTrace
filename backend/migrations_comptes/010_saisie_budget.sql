-- 010 : unité de saisie des budgets d'un organisme (HT par défaut, ou TTC). Les budgets
-- restent stockés en HT : un montant saisi en TTC est converti au taux de TVA par défaut.

ALTER TABLE organisme ADD COLUMN saisie_budget TEXT NOT NULL DEFAULT 'HT'
    CHECK (saisie_budget IN ('HT', 'TTC'));
