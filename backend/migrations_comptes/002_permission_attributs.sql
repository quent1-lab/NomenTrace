-- nomentrace: reconstruction
-- Troisième permission de contributeur : « attributs » (créer et modifier les attributs et
-- leurs listes de valeurs). SQLite ne modifie pas une contrainte CHECK : la table est
-- reconstruite avec ses lignes.
CREATE TABLE utilisateur_permission_nouvelle (
    utilisateur_id  INTEGER NOT NULL,
    projet          TEXT NOT NULL,
    permission      TEXT NOT NULL CHECK (permission IN ('achats', 'ensembles', 'attributs')),
    PRIMARY KEY (utilisateur_id, projet, permission),
    FOREIGN KEY (utilisateur_id, projet) REFERENCES acces(utilisateur_id, projet)
        ON DELETE CASCADE
);

INSERT INTO utilisateur_permission_nouvelle (utilisateur_id, projet, permission)
SELECT utilisateur_id, projet, permission FROM utilisateur_permission;

DROP TABLE utilisateur_permission;
ALTER TABLE utilisateur_permission_nouvelle RENAME TO utilisateur_permission;
