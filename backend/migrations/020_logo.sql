-- 020 : logo de l'établissement, repris dans les demandes de devis (PDF et Excel).
-- Une seule ligne au plus. L'image est gardée dans la base : elle part avec les sauvegardes.
CREATE TABLE logo (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    type_mime   TEXT NOT NULL CHECK (type_mime IN ('image/png', 'image/jpeg')),
    contenu     BLOB NOT NULL,
    largeur     INTEGER NOT NULL CHECK (largeur > 0),
    hauteur     INTEGER NOT NULL CHECK (hauteur > 0),
    modifie_le  TEXT NOT NULL
);
