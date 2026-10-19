-- 021 : visa d'un composant par un responsable (administrateur ou permission achats).
-- Le visa dit « vu tel qu'il est » : il garde la date de modification du composant au moment
-- où il a été posé, et ne vaut plus dès que cette date change (champ ou caractéristique
-- modifié). Un seul visa par composant, le dernier posé ; tout le monde le voit.
CREATE TABLE visa (
    composant_id     TEXT PRIMARY KEY REFERENCES composant(id) ON DELETE CASCADE,
    vise_par         TEXT,
    vise_le          TEXT NOT NULL,
    modifie_le_vise  TEXT NOT NULL
);
