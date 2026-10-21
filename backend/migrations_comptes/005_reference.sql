-- 005 : référence d'un dossier (phase 15b-2).
-- Chaque dossier a un projet de référence, `ref-<dossier>`, dont les réglages imposés
-- (blocs, listes imposées, attributs, réglages de l'établissement, logo) sont recopiés dans
-- chaque projet du dossier. Ce projet n'a pas de composants et n'apparaît pas à l'accueil.

ALTER TABLE projet ADD COLUMN reference INTEGER NOT NULL DEFAULT 0 CHECK (reference IN (0, 1));
