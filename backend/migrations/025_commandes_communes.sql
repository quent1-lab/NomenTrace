-- 025 : commandes communes à un dossier (phase 16).
-- Une commande commune est passée à un fournisseur pour plusieurs projets du dossier. Son
-- en-tête et ses frais vivent dans la référence du dossier (tables commune, frais_commune) ;
-- la liste de ses participants aussi (commune_projet). Chaque projet présent a une commande
-- ordinaire, sa copie, marquée par la colonne commune : elle porte ses lignes, seule copie de
-- ces lignes, une copie de l'en-tête, sa part des frais et sa part du montant réel.
-- Les tables existent dans toute base ; seules les références de dossier les remplissent.

ALTER TABLE commande ADD COLUMN commune TEXT;
-- Version de la commune dont la copie a reçu l'en-tête et les parts (services/communes_sync.py).
ALTER TABLE commande ADD COLUMN version_commune INTEGER;
CREATE INDEX idx_commande_commune ON commande(commune);

CREATE TABLE commune (
    numero                  TEXT PRIMARY KEY,
    type                    TEXT NOT NULL DEFAULT 'Commande'
        CHECK (type IN ('Devis', 'Commande')),
    statut                  TEXT NOT NULL DEFAULT 'A demander'
        CHECK (statut IN ('A demander', 'Devis demande', 'Devis recu', 'Devis valide',
                          'Commande', 'Livre partiel', 'Livre', 'Refuse')),
    fournisseur_nom         TEXT NOT NULL,
    demande_par             TEXT,
    date_demande            TEXT,
    date_reception_devis    TEXT,
    date_commande           TEXT,
    livraison_annoncee      TEXT,
    date_reception_reelle   TEXT,
    taux_tva                REAL NOT NULL DEFAULT 0.2 CHECK (taux_tva >= 0 AND taux_tva < 1),
    reference_externe       TEXT,
    lien_document           TEXT,
    commentaire             TEXT,
    date_transmission_suivi TEXT,
    montant_commande_ht     REAL CHECK (montant_commande_ht >= 0),
    date_commande_confirmee INTEGER NOT NULL DEFAULT 0 CHECK (date_commande_confirmee IN (0, 1)),
    livraison_confirmee     INTEGER NOT NULL DEFAULT 0 CHECK (livraison_confirmee IN (0, 1)),
    date_reception_annoncee TEXT,
    commentaire_suivi       TEXT,
    archive                 INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1)),
    -- +1 à toute écriture sur la commune, ligne comprise, avant l'écriture elle-même.
    version                 INTEGER NOT NULL DEFAULT 1,
    -- Déduits par la synchronisation, pour la liste du dossier : statut tenant compte des
    -- réceptions, estimé total (lignes non annulées et frais).
    statut_deduit           TEXT,
    estime_ht               REAL,
    cree_le                 TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

CREATE TABLE commune_projet (
    numero       TEXT NOT NULL REFERENCES commune(numero),
    projet       TEXT NOT NULL,
    numero_local TEXT NOT NULL,
    PRIMARY KEY (numero, projet)
);

CREATE TABLE frais_commune (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    numero      TEXT NOT NULL REFERENCES commune(numero),
    type_frais  TEXT NOT NULL,
    montant_ht  REAL NOT NULL CHECK (montant_ht >= 0),
    commentaire TEXT
);
CREATE INDEX idx_frais_commune ON frais_commune(numero);

CREATE TRIGGER frais_commune_type_insertion BEFORE INSERT ON frais_commune
BEGIN
    SELECT RAISE(ABORT, 'Type de frais inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'type_frais' AND code = NEW.type_frais);
END;

CREATE TRIGGER frais_commune_type_modification BEFORE UPDATE OF type_frais ON frais_commune
BEGIN
    SELECT RAISE(ABORT, 'Type de frais inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'type_frais' AND code = NEW.type_frais);
END;

-- Verrou des copies dans un projet : toute écriture sur une copie, ses lignes, ses frais, ses
-- documents et ses mouvements est refusée, sauf pendant une écriture de la commune
-- (ouverte = 1, posé puis retiré dans la même transaction). Le renommage d'un fournisseur
-- reste possible : ON UPDATE CASCADE ne touche que fournisseur_nom.
CREATE TABLE commune_ecriture (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    ouverte  INTEGER NOT NULL DEFAULT 0 CHECK (ouverte IN (0, 1))
);
INSERT INTO commune_ecriture (id) VALUES (1);

CREATE TRIGGER commune_copie_insertion BEFORE INSERT ON commande
WHEN NEW.commune IS NOT NULL AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : elle se gère depuis la page du dossier');
END;

CREATE TRIGGER commune_copie_modification BEFORE UPDATE OF
    numero, type, statut, demande_par, date_demande, date_reception_devis, date_commande,
    livraison_annoncee, date_reception_reelle, port_ht, taux_tva, reference_externe,
    lien_document, commentaire, archive, date_transmission_suivi, montant_commande_ht,
    date_commande_confirmee, livraison_confirmee, date_reception_annoncee, commentaire_suivi,
    commune, version_commune
ON commande
WHEN (OLD.commune IS NOT NULL OR NEW.commune IS NOT NULL)
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : elle se gère depuis la page du dossier');
END;

CREATE TRIGGER commune_copie_suppression BEFORE DELETE ON commande
WHEN OLD.commune IS NOT NULL AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : elle se gère depuis la page du dossier');
END;

CREATE TRIGGER commune_ligne_insertion BEFORE INSERT ON ligne_commande
WHEN (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses lignes se gèrent depuis la page du dossier');
END;

CREATE TRIGGER commune_ligne_modification BEFORE UPDATE ON ligne_commande
WHEN ((SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
      OR (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL)
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses lignes se gèrent depuis la page du dossier');
END;

CREATE TRIGGER commune_ligne_suppression BEFORE DELETE ON ligne_commande
WHEN (SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses lignes se gèrent depuis la page du dossier');
END;

CREATE TRIGGER commune_frais_insertion BEFORE INSERT ON frais_commande
WHEN (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses frais se règlent depuis la page du dossier');
END;

CREATE TRIGGER commune_frais_modification BEFORE UPDATE ON frais_commande
WHEN ((SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
      OR (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL)
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses frais se règlent depuis la page du dossier');
END;

CREATE TRIGGER commune_frais_suppression BEFORE DELETE ON frais_commande
WHEN (SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses frais se règlent depuis la page du dossier');
END;

-- Documents et réceptions d'une commune : phase 16b. D'ici là, fermés sur les copies.
CREATE TRIGGER commune_document_insertion BEFORE INSERT ON document
WHEN (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses documents se déposent depuis la page du dossier');
END;

CREATE TRIGGER commune_document_modification BEFORE UPDATE ON document
WHEN ((SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
      OR (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL)
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses documents se déposent depuis la page du dossier');
END;

CREATE TRIGGER commune_document_suppression BEFORE DELETE ON document
WHEN (SELECT commune FROM commande WHERE numero = OLD.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : ses documents se déposent depuis la page du dossier');
END;

CREATE TRIGGER commune_mouvement_insertion BEFORE INSERT ON mouvement_stock
WHEN (SELECT commune FROM commande WHERE numero = NEW.commande_numero) IS NOT NULL
     AND (SELECT ouverte = 0 FROM commune_ecriture)
BEGIN
    SELECT RAISE(ABORT, 'commande commune : sa réception n''est pas encore ouverte');
END;
