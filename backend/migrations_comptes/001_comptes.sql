-- Base des comptes, distincte de la base du projet : elle pourra servir plusieurs projets,
-- chacun désigné par un code stable (NOMENTRACE_PROJET). Aucun mot de passe en clair, aucun
-- jeton en clair : seules leurs empreintes sont stockées.

CREATE TABLE schema_version (
    numero INTEGER NOT NULL
);

-- L'identité est interne à Nomentrace, indépendante du moyen de connexion.
CREATE TABLE utilisateur (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant         TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- adresse mail, jamais utilisée pour écrire
    nom                 TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- nom affiché, reporté dans le journal
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    derniere_connexion  TEXT,
    cree_le             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    modifie_le          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

-- Moyens de connexion d'un utilisateur. Pour l'instant, le mot de passe seul : le sujet est
-- l'identifiant interne, le secret l'empreinte scrypt avec son sel et ses paramètres.
-- Un fournisseur externe (compte Microsoft, GitHub) s'ajoutera ici, rattaché au même
-- utilisateur.
CREATE TABLE identite (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    fournisseur     TEXT NOT NULL CHECK (fournisseur IN ('mot_de_passe')),
    sujet           TEXT NOT NULL,
    secret          TEXT,
    cree_le         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    UNIQUE (fournisseur, sujet),
    UNIQUE (utilisateur_id, fournisseur)
);

-- Rôle d'un utilisateur dans un projet. Sans ligne ici, le projet lui est fermé.
CREATE TABLE acces (
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    projet          TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('lecteur', 'contributeur', 'administrateur')),
    PRIMARY KEY (utilisateur_id, projet)
);

-- Blocs fonctionnels dont un contributeur peut modifier les composants.
CREATE TABLE utilisateur_bloc (
    utilisateur_id  INTEGER NOT NULL,
    projet          TEXT NOT NULL,
    bloc_code       TEXT NOT NULL,
    PRIMARY KEY (utilisateur_id, projet, bloc_code),
    FOREIGN KEY (utilisateur_id, projet) REFERENCES acces(utilisateur_id, projet)
        ON DELETE CASCADE
);

-- Droits accordés en plus à un contributeur : achats (commandes, fournisseurs) et
-- ensembles (création et modification de l'arborescence).
CREATE TABLE utilisateur_permission (
    utilisateur_id  INTEGER NOT NULL,
    projet          TEXT NOT NULL,
    permission      TEXT NOT NULL CHECK (permission IN ('achats', 'ensembles')),
    PRIMARY KEY (utilisateur_id, projet, permission),
    FOREIGN KEY (utilisateur_id, projet) REFERENCES acces(utilisateur_id, projet)
        ON DELETE CASCADE
);

-- Lien d'invitation à usage unique, par lequel une personne choisit son mot de passe.
CREATE TABLE invitation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    empreinte       TEXT NOT NULL UNIQUE,
    cree_par        TEXT,
    cree_le         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    expire_le       TEXT NOT NULL,
    utilisee_le     TEXT
);
CREATE INDEX idx_invitation_utilisateur ON invitation(utilisateur_id);

-- Sessions ouvertes : le navigateur garde le jeton, la base son empreinte. Supprimer la
-- ligne ferme la session, où qu'elle soit.
CREATE TABLE session (
    empreinte       TEXT PRIMARY KEY,
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    cree_le         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    expire_le       TEXT NOT NULL,
    adresse_ip      TEXT
);
CREATE INDEX idx_session_utilisateur ON session(utilisateur_id);
