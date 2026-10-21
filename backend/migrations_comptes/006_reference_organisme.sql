-- 006 : référence d'organisme (phase 15b-3).
-- Chaque organisme a un projet de référence, `org-<organisme>`, qui porte la liste commune de
-- ses fournisseurs, recopiée dans chaque projet de ses dossiers. Ce projet n'appartient à
-- aucun dossier : `organisme` le rattache à son organisme.

ALTER TABLE projet ADD COLUMN organisme TEXT REFERENCES organisme(code);
