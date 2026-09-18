-- 007 : documents joints.
-- Un document est rattaché soit à une commande (devis, bon de commande, facture, bon de
-- livraison), soit à un composant (fiche technique, plan, photo). Le fichier lui-même est
-- rangé dans echange/documents/ ; la base garde son chemin relatif, sa taille et son
-- empreinte SHA-256. Un document n'est jamais supprimé : il est archivé.

CREATE TABLE document (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commande_numero TEXT REFERENCES commande(numero),
    composant_id    TEXT REFERENCES composant(id),
    type_document   TEXT NOT NULL
        CHECK (type_document IN ('Devis', 'Bon de commande', 'Facture', 'Bon de livraison',
                                 'Fiche technique', 'Plan', 'Photo', 'Autre')),
    nom_origine     TEXT NOT NULL,
    chemin          TEXT NOT NULL UNIQUE,
    type_mime       TEXT,
    taille          INTEGER NOT NULL CHECK (taille >= 0),
    empreinte       TEXT NOT NULL,
    commentaire     TEXT,
    ajoute_le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive         INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1)),
    -- Rattaché à exactement une cible.
    CHECK ((commande_numero IS NULL) <> (composant_id IS NULL))
);

CREATE INDEX idx_document_commande ON document(commande_numero);
CREATE INDEX idx_document_composant ON document(composant_id);

-- Documents visibles depuis un composant : les siens, et ceux des commandes où il figure.
CREATE VIEW v_document_composant AS
SELECT d.*, d.composant_id AS pour_composant, 'composant' AS source
FROM document d
WHERE d.archive = 0 AND d.composant_id IS NOT NULL
UNION ALL
SELECT DISTINCT d.*, l.composant_id AS pour_composant, 'commande' AS source
FROM document d
JOIN ligne_commande l ON l.commande_numero = d.commande_numero
JOIN commande c ON c.numero = d.commande_numero AND c.archive = 0
WHERE d.archive = 0;
