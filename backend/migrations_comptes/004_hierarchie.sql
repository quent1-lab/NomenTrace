-- 004 : hiérarchie organisme › dossier › projet, et droits qui en descendent.
-- Organismes et dossiers sont des données saisies dans l'application : code d'adresse figé
-- à la création (/o/<code>/, /d/<code>/), nom modifiable. Un projet sans dossier reste
-- visible de l'administrateur du serveur, qui le range.

CREATE TABLE organisme (
    code     TEXT PRIMARY KEY CHECK (
                 length(code) BETWEEN 1 AND 40
                 AND code GLOB '[a-z0-9]*'
                 AND code NOT GLOB '*[^a-z0-9-]*'
             ),
    nom      TEXT NOT NULL CHECK (length(nom) > 0),
    cree_le  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive  INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

-- nom_projet : nom imposé aux projets du dossier (« SPOC »), écrit dans chaque projet créé.
CREATE TABLE dossier (
    code        TEXT PRIMARY KEY CHECK (
                    length(code) BETWEEN 1 AND 40
                    AND code GLOB '[a-z0-9]*'
                    AND code NOT GLOB '*[^a-z0-9-]*'
                ),
    organisme   TEXT NOT NULL REFERENCES organisme(code),
    nom         TEXT NOT NULL CHECK (length(nom) > 0),
    nom_projet  TEXT,
    cree_le     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive     INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);
CREATE INDEX idx_dossier_organisme ON dossier(organisme);

ALTER TABLE projet ADD COLUMN dossier TEXT REFERENCES dossier(code);
ALTER TABLE projet ADD COLUMN nom_equipe TEXT;

-- Profil d'un administrateur d'organisme, valable dans tous les projets de l'organisme :
-- gestion (administrateur), lecture (lecteur), achats_stock (contributeur de tous les blocs
-- avec la permission achats).
CREATE TABLE acces_organisme (
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    organisme       TEXT NOT NULL REFERENCES organisme(code),
    profil          TEXT NOT NULL CHECK (profil IN ('gestion', 'lecture', 'achats_stock')),
    PRIMARY KEY (utilisateur_id, organisme)
);

-- Rôle d'un compte dans un dossier : responsable achats (page du dossier, résumé des
-- projets ; ses droits sur les commandes communes viendront avec elles).
CREATE TABLE acces_dossier (
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    dossier         TEXT NOT NULL REFERENCES dossier(code),
    role            TEXT NOT NULL CHECK (role IN ('responsable_achats')),
    PRIMARY KEY (utilisateur_id, dossier)
);

-- Administrateur du serveur : crée les organismes, range les projets, administre partout.
ALTER TABLE utilisateur ADD COLUMN admin_serveur INTEGER NOT NULL DEFAULT 0
    CHECK (admin_serveur IN (0, 1));
