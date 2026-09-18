-- 001 : schéma complet de Nomentrace.
-- Valeurs autorisées : voir docs/MODELE.md, section « Valeurs autorisées ».

CREATE TABLE schema_version (
    numero INTEGER NOT NULL
);

CREATE TABLE parametre (
    cle    TEXT PRIMARY KEY,
    valeur TEXT
);

CREATE TABLE bloc (
    code            TEXT PRIMARY KEY,
    nom             TEXT NOT NULL,
    ordre           INTEGER NOT NULL DEFAULT 0,
    budget_cible_ht REAL,
    responsable     TEXT,
    description     TEXT
);

CREATE TABLE ensemble (
    code           TEXT PRIMARY KEY,
    nom            TEXT NOT NULL,
    ordre          INTEGER NOT NULL DEFAULT 0,
    parent_code    TEXT REFERENCES ensemble(code),
    description    TEXT,
    responsable    TEXT,
    statut_montage TEXT NOT NULL DEFAULT 'Non commence'
        CHECK (statut_montage IN ('Non commence', 'En cours', 'Monte', 'Valide')),
    archive        INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

CREATE TABLE fournisseur (
    nom              TEXT PRIMARY KEY,
    type             TEXT,
    base_prix_defaut TEXT CHECK (base_prix_defaut IN ('HT', 'TTC')),
    pays             TEXT,
    site_web         TEXT,
    compte_ecole     TEXT,
    delai_moyen_j    INTEGER CHECK (delai_moyen_j >= 0),
    commentaire      TEXT,
    archive          INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

CREATE TABLE composant (
    id               TEXT PRIMARY KEY,
    bloc_code        TEXT NOT NULL REFERENCES bloc(code),
    fonction         TEXT NOT NULL,
    designation      TEXT NOT NULL,
    ref_fabricant    TEXT,
    fabricant        TEXT,
    mode_appro       TEXT NOT NULL
        CHECK (mode_appro IN ('Achat', 'Stock ecole', 'Fourni PFM', 'Fourni CEA',
                              'Fabrication PFM')),
    fournisseur_nom  TEXT REFERENCES fournisseur(nom) ON UPDATE CASCADE,
    lien_produit     TEXT,
    qte_besoin       INTEGER NOT NULL DEFAULT 0 CHECK (qte_besoin >= 0),
    qte_rechange     INTEGER NOT NULL DEFAULT 0 CHECK (qte_rechange >= 0),
    qte_dispo_ecole  INTEGER NOT NULL DEFAULT 0 CHECK (qte_dispo_ecole >= 0),
    pu_releve        REAL CHECK (pu_releve >= 0),
    base_prix_releve TEXT NOT NULL DEFAULT 'HT' CHECK (base_prix_releve IN ('HT', 'TTC')),
    taux_tva         REAL NOT NULL DEFAULT 0.2 CHECK (taux_tva >= 0 AND taux_tva < 1),
    statut_choix     TEXT CHECK (statut_choix IN ('Acte', 'A confirmer', 'A sourcer')),
    statut_appro     TEXT NOT NULL DEFAULT 'Non lance'
        CHECK (statut_appro IN ('Non lance', 'Devis demande', 'Devis recu', 'A commander',
                                'Commande', 'Recu partiel', 'Recu', 'Stock-PFM',
                                'Hors perimetre', 'Abandonne')),
    criticite        TEXT CHECK (criticite IN ('Bloquant', 'Important', 'Confort')),
    origine_exigence TEXT,
    note_technique   TEXT,
    cree_le          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    modifie_le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive          INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

CREATE TABLE affectation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ensemble_code TEXT NOT NULL REFERENCES ensemble(code),
    composant_id  TEXT NOT NULL REFERENCES composant(id),
    qte           INTEGER NOT NULL CHECK (qte > 0),
    commentaire   TEXT,
    cree_le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    UNIQUE (ensemble_code, composant_id)
);

CREATE TABLE commande (
    numero                TEXT PRIMARY KEY,
    type                  TEXT NOT NULL DEFAULT 'Commande'
        CHECK (type IN ('Devis', 'Commande')),
    statut                TEXT NOT NULL DEFAULT 'A demander'
        CHECK (statut IN ('A demander', 'Devis demande', 'Devis recu', 'Devis valide',
                          'Commande', 'Livre partiel', 'Livre', 'Refuse')),
    fournisseur_nom       TEXT REFERENCES fournisseur(nom) ON UPDATE CASCADE,
    demande_par           TEXT,
    date_demande          TEXT,
    date_reception_devis  TEXT,
    date_commande         TEXT,
    livraison_annoncee    TEXT,
    date_reception_reelle TEXT,
    port_ht               REAL NOT NULL DEFAULT 0 CHECK (port_ht >= 0),
    taux_tva              REAL NOT NULL DEFAULT 0.2 CHECK (taux_tva >= 0 AND taux_tva < 1),
    reference_externe     TEXT,
    lien_document         TEXT,
    commentaire           TEXT,
    archive               INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

CREATE TABLE ligne_commande (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commande_numero TEXT NOT NULL REFERENCES commande(numero),
    composant_id    TEXT NOT NULL REFERENCES composant(id),
    qte_commandee   INTEGER NOT NULL DEFAULT 0 CHECK (qte_commandee >= 0),
    pu_ht_devis     REAL CHECK (pu_ht_devis >= 0),
    qte_recue       INTEGER NOT NULL DEFAULT 0 CHECK (qte_recue >= 0),
    date_reception  TEXT,
    statut_ligne    TEXT NOT NULL DEFAULT 'A commander'
        CHECK (statut_ligne IN ('A commander', 'Commandee', 'Recue partiel', 'Recue',
                                'Annulee')),
    commentaire     TEXT
);

CREATE TABLE mouvement_stock (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    composant_id    TEXT NOT NULL REFERENCES composant(id),
    sens            TEXT NOT NULL CHECK (sens IN ('Entree', 'Sortie')),
    type_mouvement  TEXT NOT NULL
        CHECK (type_mouvement IN ('Reception achat', 'Pret ecole', 'Retour ecole',
                                  'Sortie montage', 'Retour montage', 'Perte ou casse',
                                  'Inventaire')),
    qte             INTEGER NOT NULL CHECK (qte > 0),
    emplacement     TEXT,
    par_qui         TEXT,
    commande_numero TEXT REFERENCES commande(numero),
    ensemble_code   TEXT REFERENCES ensemble(code),
    commentaire     TEXT,
    -- L'ensemble est renseigné pour les mouvements de montage, et seulement pour eux.
    CHECK ((type_mouvement IN ('Sortie montage', 'Retour montage'))
           = (ensemble_code IS NOT NULL)),
    CHECK (type_mouvement <> 'Sortie montage' OR sens = 'Sortie'),
    CHECK (type_mouvement <> 'Retour montage' OR sens = 'Entree')
);

CREATE TABLE journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    table_cible     TEXT NOT NULL,
    cle_cible       TEXT,
    champ           TEXT,
    ancienne_valeur TEXT,
    nouvelle_valeur TEXT,
    origine         TEXT NOT NULL CHECK (origine IN ('interface', 'import'))
);

CREATE INDEX idx_composant_bloc ON composant(bloc_code);
CREATE INDEX idx_composant_mode_appro ON composant(mode_appro);
CREATE INDEX idx_affectation_ensemble ON affectation(ensemble_code);
CREATE INDEX idx_affectation_composant ON affectation(composant_id);
CREATE INDEX idx_ligne_commande_composant ON ligne_commande(composant_id);
CREATE INDEX idx_ligne_commande_commande ON ligne_commande(commande_numero);
CREATE INDEX idx_mouvement_composant ON mouvement_stock(composant_id);
CREATE INDEX idx_mouvement_ensemble ON mouvement_stock(ensemble_code);
CREATE INDEX idx_journal_cible ON journal(table_cible, cle_cible);
