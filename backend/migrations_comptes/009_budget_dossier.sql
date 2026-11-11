-- 009 : enveloppe budgétaire d'un dossier (HT), fixée par la gestion de l'organisme.
-- Elle ne se répartit pas d'elle-même : la page du dossier la montre avec la somme des
-- budgets de ses projets et ce qui reste à répartir.

ALTER TABLE dossier ADD COLUMN budget_ht REAL CHECK (budget_ht IS NULL OR budget_ht >= 0);
