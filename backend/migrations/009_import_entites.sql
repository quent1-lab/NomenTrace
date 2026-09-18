-- nomentrace: reconstruction
-- 009 : l'import peut proposer de créer des fournisseurs, des valeurs de liste et des
-- ensembles cités par les fichiers de l'équipe (catégorie NOUVELLE_ENTITE).
-- import_ligne est reconstruite pour élargir sa contrainte de catégorie ; aucune vue n'en
-- dépend.

CREATE TABLE import_ligne_nouvelle (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id        INTEGER NOT NULL REFERENCES import_lot(id),
    numero_ligne  INTEGER NOT NULL,
    categorie     TEXT NOT NULL
        CHECK (categorie IN ('IDENTIQUE', 'MODIFIE', 'NOUVEAU', 'DOUBLON', 'INCONNU',
                             'INVALIDE', 'CREATION_AFFECTATION', 'MODIF_AFFECTATION',
                             'SUPPRESSION_AFFECTATION', 'NOUVELLE_ENTITE')),
    composant_id  TEXT,
    donnees_json  TEXT NOT NULL,
    score         REAL,
    decision      TEXT,
    applique_le   TEXT
);

INSERT INTO import_ligne_nouvelle
SELECT id, lot_id, numero_ligne, categorie, composant_id, donnees_json, score, decision,
       applique_le
FROM import_ligne;

DROP TABLE import_ligne;
ALTER TABLE import_ligne_nouvelle RENAME TO import_ligne;
CREATE INDEX idx_import_ligne_lot ON import_ligne(lot_id);
