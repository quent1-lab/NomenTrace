-- Fournisseurs à valider : un fournisseur trouvé par l'équipe (saisie d'un composant,
-- fichier d'import) est créé « A valider », puis complété et validé par une personne
-- autorisée. Les fournisseurs déjà présents sont considérés comme validés.
ALTER TABLE fournisseur ADD COLUMN statut TEXT NOT NULL DEFAULT 'Valide'
    CHECK (statut IN ('Valide', 'A valider'));
