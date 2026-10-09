-- Un attribut peut être rendu obligatoire pour les composants (par défaut : facultatif).
-- Les champs de base obligatoires et la portée de la règle sont des paramètres
-- (champs_obligatoires, champs_obligatoires_portee).
ALTER TABLE attribut ADD COLUMN obligatoire INTEGER NOT NULL DEFAULT 0
    CHECK (obligatoire IN (0, 1));
