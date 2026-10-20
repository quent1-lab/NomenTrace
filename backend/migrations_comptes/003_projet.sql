-- 003 : registre des projets servis par l'instance. Chaque projet a sa base et ses dossiers
-- (<data>/projets/<code>/, <echange>/projets/<code>/) ; son code, figé à la création, est
-- celui de son adresse /p/<code>/ et désigne le projet dans acces.projet. Le nom du projet
-- reste dans la base du projet.

CREATE TABLE projet (
    code     TEXT PRIMARY KEY CHECK (
                 length(code) BETWEEN 1 AND 40
                 AND code GLOB '[a-z0-9]*'
                 AND code NOT GLOB '*[^a-z0-9-]*'
             ),
    cree_le  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive  INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);
