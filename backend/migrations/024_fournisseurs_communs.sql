-- 024 : fournisseurs communs à l'organisme (phase 15b-3).
-- La liste se règle dans la référence de l'organisme et se recopie dans chaque projet rangé,
-- où elle est verrouillée comme les autres réglages imposés. Un renommage dans la référence
-- est journalisé avec un identifiant aléatoire ; chaque projet garde les renommages déjà
-- rejoués chez lui (ses composants et commandes suivent par ON UPDATE CASCADE).

CREATE TABLE renommage_fournisseur (
    rang     INTEGER PRIMARY KEY AUTOINCREMENT,
    id       TEXT NOT NULL UNIQUE,
    ancien   TEXT NOT NULL,
    nouveau  TEXT NOT NULL,
    le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

CREATE TABLE renommage_applique (
    id  TEXT PRIMARY KEY
);

-- Seule une référence (initialisée) journalise ses renommages.
CREATE TRIGGER journal_renommage_fournisseur AFTER UPDATE OF nom ON fournisseur
WHEN NEW.nom IS NOT OLD.nom AND (SELECT initialisee = 1 FROM reglages_imposes)
BEGIN
    INSERT INTO renommage_fournisseur (id, ancien, nouveau)
    VALUES (lower(hex(randomblob(16))), OLD.nom, NEW.nom);
END;

CREATE TRIGGER impose_fournisseur_insertion BEFORE INSERT ON fournisseur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les fournisseurs se règlent dans la liste de l''organisme');
END;

CREATE TRIGGER impose_fournisseur_modification BEFORE UPDATE ON fournisseur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les fournisseurs se règlent dans la liste de l''organisme');
END;

CREATE TRIGGER impose_fournisseur_suppression BEFORE DELETE ON fournisseur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les fournisseurs se règlent dans la liste de l''organisme');
END;
