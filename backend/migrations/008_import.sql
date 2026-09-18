-- 008 : import des fichiers de l'équipe et fusion assistée.
-- Un dépôt regroupe un ou plusieurs fichiers ; chaque fichier est un lot, chaque ligne
-- utile du fichier une proposition. Rien n'est appliqué sans décision explicite.

CREATE TABLE import_lot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    depot           INTEGER NOT NULL,           -- id du premier lot du dépôt
    horodatage      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    nom_fichier     TEXT NOT NULL,
    fichier_copie   TEXT,                       -- copie conservée dans echange/imports/
    depose_par      TEXT,
    bloc_devine     TEXT,
    ensemble_devine TEXT,
    statut          TEXT NOT NULL DEFAULT 'analyse'
        CHECK (statut IN ('analyse', 'applique', 'abandonne'))
);

CREATE TABLE import_ligne (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id        INTEGER NOT NULL REFERENCES import_lot(id),
    numero_ligne  INTEGER NOT NULL,
    categorie     TEXT NOT NULL
        CHECK (categorie IN ('IDENTIQUE', 'MODIFIE', 'NOUVEAU', 'DOUBLON', 'INCONNU',
                             'INVALIDE', 'CREATION_AFFECTATION', 'MODIF_AFFECTATION',
                             'SUPPRESSION_AFFECTATION')),
    composant_id  TEXT,
    donnees_json  TEXT NOT NULL,
    score         REAL,
    decision      TEXT,
    applique_le   TEXT
);

CREATE INDEX idx_import_lot_depot ON import_lot(depot);
CREATE INDEX idx_import_ligne_lot ON import_ligne(lot_id);

ALTER TABLE journal ADD COLUMN lot_id INTEGER REFERENCES import_lot(id);
