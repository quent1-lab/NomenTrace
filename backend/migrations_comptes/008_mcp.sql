-- 008 : accès d'un assistant IA par le protocole MCP.
-- mcp_acces : qui peut brancher un assistant sur le projet. Fermé par défaut ; l'administrateur
-- du projet l'ouvre pour les administrateurs seuls ou pour tous les membres.
-- jeton_api : jeton personnel d'un compte pour un seul projet. Seule son empreinte SHA-256
-- est gardée ; le jeton en clair n'est montré qu'une fois, à sa création.

ALTER TABLE projet ADD COLUMN mcp_acces TEXT NOT NULL DEFAULT 'ferme'
    CHECK (mcp_acces IN ('ferme', 'admin', 'membres'));

CREATE TABLE jeton_api (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    projet          TEXT NOT NULL REFERENCES projet(code),
    nom             TEXT NOT NULL,
    empreinte       TEXT NOT NULL UNIQUE,
    cree_le         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    dernier_usage   TEXT,
    revoque_le      TEXT
);

CREATE INDEX jeton_api_utilisateur ON jeton_api (utilisateur_id, projet);
