-- 007 : mise en commun des composants d'un dossier (phase 17).
-- Activée, chaque projet du dossier se voit proposer, à la création d'un composant, les
-- références qui ressemblent chez les autres projets du dossier. Désactivée par défaut :
-- rien n'est montré à une autre équipe sans décision de l'organisme.

ALTER TABLE dossier ADD COLUMN partage_composants INTEGER NOT NULL DEFAULT 0
    CHECK (partage_composants IN (0, 1));
