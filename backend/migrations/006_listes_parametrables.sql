-- nomentrace: reconstruction
-- 006 : listes de valeurs paramétrables.
-- Les valeurs propres à un projet (modes d'approvisionnement, statuts d'appro, statuts de
-- choix, criticités, types de mouvement) quittent les contraintes CHECK pour la table
-- valeur_liste, modifiable depuis l'écran Paramètres. Les valeurs dont dépendent les
-- calculs sont marquées « système » : non supprimables, code figé.
-- La colonne qte_dispo_ecole devient qte_disponible (quantité déjà disponible sans achat).
-- Les tables composant et mouvement_stock sont reconstruites (SQLite ne sait pas retirer
-- une contrainte CHECK) ; les vues qui en dépendent sont recréées à l'identique.

CREATE TABLE valeur_liste (
    liste   TEXT NOT NULL
        CHECK (liste IN ('mode_appro', 'statut_appro', 'statut_choix', 'criticite',
                         'type_mouvement')),
    code    TEXT NOT NULL CHECK (length(code) > 0),
    libelle TEXT NOT NULL CHECK (length(libelle) > 0),
    ordre   INTEGER NOT NULL DEFAULT 0,
    actif   INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    systeme INTEGER NOT NULL DEFAULT 0 CHECK (systeme IN (0, 1)),
    -- Sens imposé d'un type de mouvement ; NULL = libre (inventaire).
    sens    TEXT CHECK (sens IN ('Entree', 'Sortie')),
    PRIMARY KEY (liste, code)
);

-- Valeurs génériques, présentes dans toute instance.
INSERT INTO valeur_liste (liste, code, libelle, ordre, systeme, sens) VALUES
    ('mode_appro', 'Achat', 'Achat', 1, 1, NULL),
    ('statut_appro', 'Non lance', 'Non lancé', 1, 1, NULL),
    ('statut_appro', 'Devis demande', 'Devis demandé', 2, 0, NULL),
    ('statut_appro', 'Devis recu', 'Devis reçu', 3, 0, NULL),
    ('statut_appro', 'A commander', 'À commander', 4, 0, NULL),
    ('statut_appro', 'Commande', 'Commandé', 5, 0, NULL),
    ('statut_appro', 'Recu partiel', 'Reçu partiel', 6, 0, NULL),
    ('statut_appro', 'Recu', 'Reçu', 7, 0, NULL),
    ('statut_appro', 'Hors perimetre', 'Hors périmètre', 20, 0, NULL),
    ('statut_appro', 'Abandonne', 'Abandonné', 21, 0, NULL),
    ('statut_choix', 'Acte', 'Acté', 1, 0, NULL),
    ('statut_choix', 'A confirmer', 'À confirmer', 2, 0, NULL),
    ('statut_choix', 'A sourcer', 'À sourcer', 3, 0, NULL),
    ('criticite', 'Bloquant', 'Bloquant', 1, 1, NULL),
    ('criticite', 'Important', 'Important', 2, 0, NULL),
    ('criticite', 'Confort', 'Confort', 3, 0, NULL),
    ('type_mouvement', 'Reception achat', 'Réception achat', 1, 1, 'Entree'),
    ('type_mouvement', 'Sortie montage', 'Sortie montage', 2, 1, 'Sortie'),
    ('type_mouvement', 'Retour montage', 'Retour montage', 3, 1, 'Entree'),
    ('type_mouvement', 'Perte ou casse', 'Perte ou casse', 10, 0, 'Sortie'),
    ('type_mouvement', 'Inventaire', 'Inventaire', 20, 1, NULL);

-- Compatibilité : une base déjà peuplée sous le schéma 001 garde tout le vocabulaire que
-- ses contraintes CHECK autorisaient. Une base neuve (vide à ce stade) ne les reçoit pas.
INSERT INTO valeur_liste (liste, code, libelle, ordre, sens)
SELECT v.liste, v.code, v.libelle, v.ordre, v.sens
FROM (
    SELECT 'mode_appro' AS liste, 'Stock ecole' AS code, 'Stock école' AS libelle,
           2 AS ordre, NULL AS sens
    UNION ALL SELECT 'mode_appro', 'Fourni PFM', 'Fourni PFM', 3, NULL
    UNION ALL SELECT 'mode_appro', 'Fourni CEA', 'Fourni CEA', 4, NULL
    UNION ALL SELECT 'mode_appro', 'Fabrication PFM', 'Fabrication PFM', 5, NULL
    UNION ALL SELECT 'statut_appro', 'Stock-PFM', 'Stock PFM', 8, NULL
    UNION ALL SELECT 'type_mouvement', 'Pret ecole', 'Prêt école', 4, 'Entree'
    UNION ALL SELECT 'type_mouvement', 'Retour ecole', 'Retour école', 5, 'Sortie'
) v
WHERE EXISTS (SELECT 1 FROM composant);

-- Filet de sécurité : toute valeur réellement utilisée reste valide.
INSERT OR IGNORE INTO valeur_liste (liste, code, libelle, ordre)
SELECT DISTINCT 'mode_appro', mode_appro, mode_appro, 50 FROM composant
UNION SELECT DISTINCT 'statut_appro', statut_appro, statut_appro, 50 FROM composant
UNION SELECT DISTINCT 'statut_choix', statut_choix, statut_choix, 50 FROM composant
    WHERE statut_choix IS NOT NULL
UNION SELECT DISTINCT 'criticite', criticite, criticite, 50 FROM composant
    WHERE criticite IS NOT NULL;
INSERT OR IGNORE INTO valeur_liste (liste, code, libelle, ordre, sens)
SELECT DISTINCT 'type_mouvement', type_mouvement, type_mouvement, 50, sens
FROM mouvement_stock;

-- --- Suppression des vues qui dépendent des tables reconstruites --------------------------

DROP VIEW v_pilotage;
DROP VIEW v_stock;
DROP VIEW v_incoherence;
DROP VIEW v_ensemble_bloc;
DROP VIEW v_ensemble;
DROP VIEW v_bloc;
DROP VIEW v_ensemble_composant;
DROP VIEW v_composant;

-- --- Reconstruction de composant ------------------------------------------------------------

CREATE TABLE composant_nouveau (
    id               TEXT PRIMARY KEY,
    bloc_code        TEXT NOT NULL REFERENCES bloc(code),
    fonction         TEXT NOT NULL,
    designation      TEXT NOT NULL,
    ref_fabricant    TEXT,
    fabricant        TEXT,
    mode_appro       TEXT NOT NULL,
    fournisseur_nom  TEXT REFERENCES fournisseur(nom) ON UPDATE CASCADE,
    lien_produit     TEXT,
    qte_besoin       INTEGER NOT NULL DEFAULT 0 CHECK (qte_besoin >= 0),
    qte_rechange     INTEGER NOT NULL DEFAULT 0 CHECK (qte_rechange >= 0),
    qte_disponible   INTEGER NOT NULL DEFAULT 0 CHECK (qte_disponible >= 0),
    pu_releve        REAL CHECK (pu_releve >= 0),
    base_prix_releve TEXT NOT NULL DEFAULT 'HT' CHECK (base_prix_releve IN ('HT', 'TTC')),
    taux_tva         REAL NOT NULL DEFAULT 0.2 CHECK (taux_tva >= 0 AND taux_tva < 1),
    statut_choix     TEXT,
    statut_appro     TEXT NOT NULL DEFAULT 'Non lance',
    criticite        TEXT,
    origine_exigence TEXT,
    note_technique   TEXT,
    cree_le          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    modifie_le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    archive          INTEGER NOT NULL DEFAULT 0 CHECK (archive IN (0, 1))
);

INSERT INTO composant_nouveau (
    id, bloc_code, fonction, designation, ref_fabricant, fabricant, mode_appro,
    fournisseur_nom, lien_produit, qte_besoin, qte_rechange, qte_disponible, pu_releve,
    base_prix_releve, taux_tva, statut_choix, statut_appro, criticite, origine_exigence,
    note_technique, cree_le, modifie_le, archive)
SELECT
    id, bloc_code, fonction, designation, ref_fabricant, fabricant, mode_appro,
    fournisseur_nom, lien_produit, qte_besoin, qte_rechange, qte_dispo_ecole, pu_releve,
    base_prix_releve, taux_tva, statut_choix, statut_appro, criticite, origine_exigence,
    note_technique, cree_le, modifie_le, archive
FROM composant;

DROP TABLE composant;
ALTER TABLE composant_nouveau RENAME TO composant;
CREATE INDEX idx_composant_bloc ON composant(bloc_code);
CREATE INDEX idx_composant_mode_appro ON composant(mode_appro);

-- --- Reconstruction de mouvement_stock ------------------------------------------------------

CREATE TABLE mouvement_stock_nouveau (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    composant_id    TEXT NOT NULL REFERENCES composant(id),
    sens            TEXT NOT NULL CHECK (sens IN ('Entree', 'Sortie')),
    type_mouvement  TEXT NOT NULL,
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

INSERT INTO mouvement_stock_nouveau (
    id, date, composant_id, sens, type_mouvement, qte, emplacement, par_qui,
    commande_numero, ensemble_code, commentaire)
SELECT id, date, composant_id, sens, type_mouvement, qte, emplacement, par_qui,
       commande_numero, ensemble_code, commentaire
FROM mouvement_stock;

DROP TABLE mouvement_stock;
ALTER TABLE mouvement_stock_nouveau RENAME TO mouvement_stock;
CREATE INDEX idx_mouvement_composant ON mouvement_stock(composant_id);
CREATE INDEX idx_mouvement_ensemble ON mouvement_stock(ensemble_code);

-- --- Contrôle des valeurs par déclencheurs -----------------------------------------------------
-- Une valeur désactivée reste acceptée (les données existantes restent valides) ; c'est
-- l'API qui refuse de l'utiliser pour une nouvelle saisie.

CREATE TRIGGER composant_listes_insertion BEFORE INSERT ON composant
BEGIN
    SELECT RAISE(ABORT, 'Mode d''approvisionnement inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'mode_appro' AND code = NEW.mode_appro);
    SELECT RAISE(ABORT, 'Statut d''appro inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'statut_appro' AND code = NEW.statut_appro);
    SELECT RAISE(ABORT, 'Statut de choix inconnu')
    WHERE NEW.statut_choix IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'statut_choix' AND code = NEW.statut_choix);
    SELECT RAISE(ABORT, 'Criticité inconnue')
    WHERE NEW.criticite IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'criticite' AND code = NEW.criticite);
END;

CREATE TRIGGER composant_listes_modification
BEFORE UPDATE OF mode_appro, statut_appro, statut_choix, criticite ON composant
BEGIN
    SELECT RAISE(ABORT, 'Mode d''approvisionnement inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'mode_appro' AND code = NEW.mode_appro);
    SELECT RAISE(ABORT, 'Statut d''appro inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'statut_appro' AND code = NEW.statut_appro);
    SELECT RAISE(ABORT, 'Statut de choix inconnu')
    WHERE NEW.statut_choix IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'statut_choix' AND code = NEW.statut_choix);
    SELECT RAISE(ABORT, 'Criticité inconnue')
    WHERE NEW.criticite IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'criticite' AND code = NEW.criticite);
END;

CREATE TRIGGER mouvement_type_insertion BEFORE INSERT ON mouvement_stock
BEGIN
    SELECT RAISE(ABORT, 'Type de mouvement inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'type_mouvement' AND code = NEW.type_mouvement);
    SELECT RAISE(ABORT, 'Sens incompatible avec le type de mouvement')
    WHERE (SELECT sens FROM valeur_liste
           WHERE liste = 'type_mouvement' AND code = NEW.type_mouvement) <> NEW.sens;
END;

-- --- Vues recréées (définitions inchangées, qte_disponible remplace qte_dispo_ecole) --------

CREATE VIEW v_composant AS
WITH
achats AS (
    SELECT composant_id,
           SUM(qte_commandee)                              AS qte_commandee,
           SUM(qte_recue)                                  AS qte_recue,
           TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0)) AS montant_commande_ht
    FROM v_ligne_engagee
    GROUP BY composant_id
),
stock AS (
    SELECT composant_id,
           SUM(CASE sens WHEN 'Entree' THEN qte ELSE -qte END) AS stock_actuel
    FROM mouvement_stock
    GROUP BY composant_id
),
affect AS (
    SELECT a.composant_id,
           SUM(a.qte)                       AS qte_affectee,
           COUNT(DISTINCT a.ensemble_code)  AS nb_ensembles
    FROM affectation a
    JOIN ensemble e ON e.code = a.ensemble_code AND e.archive = 0
    GROUP BY a.composant_id
),
base AS (
    SELECT c.*,
           MAX(0, c.qte_besoin + c.qte_rechange - c.qte_disponible) AS qte_a_acheter,
           CASE WHEN c.base_prix_releve = 'TTC' THEN c.pu_releve / (1 + c.taux_tva)
                ELSE c.pu_releve END                                  AS pu_ht,
           COALESCE(ac.qte_commandee, 0)       AS qte_commandee,
           COALESCE(ac.qte_recue, 0)           AS qte_recue,
           COALESCE(ac.montant_commande_ht, 0) AS montant_commande_ht,
           COALESCE(s.stock_actuel, 0)         AS stock_actuel,
           COALESCE(af.qte_affectee, 0)        AS qte_affectee,
           COALESCE(af.nb_ensembles, 0)        AS nb_ensembles
    FROM composant c
    LEFT JOIN achats ac ON ac.composant_id = c.id
    LEFT JOIN stock s   ON s.composant_id = c.id
    LEFT JOIN affect af ON af.composant_id = c.id
    WHERE c.archive = 0
)
SELECT b.*,
       b.pu_ht * (1 + b.taux_tva) AS pu_ttc,
       CASE WHEN b.mode_appro = 'Achat' THEN b.qte_a_acheter * b.pu_ht ELSE 0 END
           AS total_ht,
       CASE WHEN b.mode_appro = 'Achat' THEN b.qte_a_acheter * b.pu_ht * (1 + b.taux_tva)
            ELSE 0 END
           AS total_ttc,
       b.qte_besoin - b.qte_affectee                AS ecart_affectation,
       MAX(0, b.qte_a_acheter - b.qte_commandee)    AS reste_a_commander,
       MAX(0, b.qte_commandee - b.qte_recue)        AS reste_a_recevoir,
       CASE WHEN b.mode_appro = 'Achat' AND b.pu_releve IS NULL THEN 1 ELSE 0 END
           AS a_chiffrer,
       CASE WHEN b.mode_appro <> 'Achat' OR b.qte_a_acheter = 0 THEN 'Hors achat'
            WHEN b.qte_recue >= b.qte_a_acheter THEN 'Recu'
            WHEN b.qte_commandee > 0 THEN 'Commande'
            ELSE 'A commander' END                  AS avancement
FROM base b;

CREATE VIEW v_bloc AS
SELECT bl.code,
       bl.nom,
       bl.ordre,
       bl.responsable,
       bl.description,
       bl.budget_cible_ht,
       COUNT(v.id)                                   AS nb_composants,
       COALESCE(SUM(v.a_chiffrer), 0)                AS nb_a_chiffrer,
       TOTAL(v.total_ht)                             AS cout_ht,
       TOTAL(v.total_ttc)                            AS cout_ttc,
       TOTAL(v.montant_commande_ht)                  AS montant_engage_ht,
       TOTAL(v.total_ht) - bl.budget_cible_ht        AS ecart_budget,
       (TOTAL(v.total_ht) - bl.budget_cible_ht) * 100.0 / NULLIF(bl.budget_cible_ht, 0)
                                                     AS ecart_pct,
       COUNT(CASE WHEN v.avancement = 'Recu' THEN 1 END)        AS nb_recus,
       COUNT(CASE WHEN v.avancement = 'A commander' THEN 1 END) AS nb_a_commander,
       COUNT(CASE WHEN v.avancement = 'Recu' THEN 1 END) * 100.0
           / NULLIF(COUNT(CASE WHEN v.avancement <> 'Hors achat' THEN 1 END), 0)
                                                     AS avancement_pct
FROM bloc bl
LEFT JOIN v_composant v ON v.bloc_code = bl.code
GROUP BY bl.code;

CREATE VIEW v_ensemble_composant AS
WITH montage AS (
    -- Sens inverse du stock : une Sortie montage est une pièce montée.
    SELECT ensemble_code, composant_id,
           SUM(CASE type_mouvement WHEN 'Sortie montage' THEN qte
                                   WHEN 'Retour montage' THEN -qte
                                   ELSE 0 END) AS qte_montee
    FROM mouvement_stock
    WHERE ensemble_code IS NOT NULL
    GROUP BY ensemble_code, composant_id
)
SELECT a.id                            AS affectation_id,
       a.ensemble_code,
       e.nom                           AS ensemble_nom,
       a.composant_id,
       v.designation,
       v.bloc_code,
       a.qte                           AS qte_affectee,
       v.pu_ht,
       a.qte * v.pu_ht                 AS cout_ligne_ht,
       COALESCE(m.qte_montee, 0)       AS qte_montee,
       a.qte - COALESCE(m.qte_montee, 0) AS reste_a_monter,
       v.statut_appro,
       v.avancement,
       v.stock_actuel,
       a.commentaire
FROM affectation a
JOIN ensemble e    ON e.code = a.ensemble_code AND e.archive = 0
JOIN v_composant v ON v.id = a.composant_id
LEFT JOIN montage m ON m.ensemble_code = a.ensemble_code
                   AND m.composant_id = a.composant_id;

CREATE VIEW v_ensemble AS
SELECT e.code,
       e.nom,
       e.ordre,
       e.parent_code,
       e.description,
       e.responsable,
       e.statut_montage,
       COUNT(ec.composant_id)                          AS nb_composants_distincts,
       COALESCE(SUM(ec.qte_affectee), 0)               AS nb_pieces_total,
       TOTAL(ec.cout_ligne_ht)                         AS cout_ht,
       COUNT(CASE WHEN ec.composant_id IS NOT NULL AND ec.cout_ligne_ht IS NULL
                  AND ec.avancement <> 'Hors achat' THEN 1 END) AS nb_lignes_non_chiffrees,
       COUNT(DISTINCT ec.bloc_code)                    AS nb_blocs_representes,
       COUNT(CASE WHEN ec.avancement <> 'Hors achat' THEN 1 END) AS nb_composants_a_acheter,
       COUNT(CASE WHEN ec.avancement = 'Recu' THEN 1 END)        AS nb_composants_recus,
       COUNT(CASE WHEN ec.avancement = 'A commander' THEN 1 END) AS nb_composants_non_commandes,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) AS nb_pieces_montees,
       COALESCE(SUM(MIN(MAX(ec.qte_montee, 0), ec.qte_affectee)), 0) * 100.0
           / NULLIF(SUM(ec.qte_affectee), 0)           AS avancement_montage_pct
FROM ensemble e
LEFT JOIN v_ensemble_composant ec ON ec.ensemble_code = e.code
WHERE e.archive = 0
GROUP BY e.code;

CREATE VIEW v_ensemble_bloc AS
SELECT ec.ensemble_code,
       ec.bloc_code,
       COUNT(*)                  AS nb_composants,
       SUM(ec.qte_affectee)      AS nb_pieces,
       TOTAL(ec.cout_ligne_ht)   AS cout_ht
FROM v_ensemble_composant ec
GROUP BY ec.ensemble_code, ec.bloc_code;

CREATE VIEW v_incoherence AS
SELECT 'sur_affecte'           AS type,
       v.id                    AS composant_id,
       NULL                    AS ensemble_code,
       v.designation,
       v.qte_besoin            AS reference,
       v.qte_affectee          AS valeur
FROM v_composant v
WHERE v.nb_ensembles > 0 AND v.qte_affectee > v.qte_besoin
UNION ALL
SELECT 'affecte_non_commande', v.id, NULL, v.designation, v.qte_a_acheter, v.qte_commandee
FROM v_composant v
WHERE v.nb_ensembles > 0 AND v.mode_appro = 'Achat' AND v.avancement = 'A commander'
UNION ALL
SELECT 'monte_plus_qu_affecte', ec.composant_id, ec.ensemble_code, ec.designation,
       ec.qte_affectee, ec.qte_montee
FROM v_ensemble_composant ec
WHERE ec.qte_montee > ec.qte_affectee
UNION ALL
SELECT 'monte_sans_affectation', m.composant_id, m.ensemble_code, c.designation, 0,
       SUM(CASE m.type_mouvement WHEN 'Sortie montage' THEN m.qte ELSE -m.qte END)
FROM mouvement_stock m
JOIN composant c ON c.id = m.composant_id AND c.archive = 0
WHERE m.ensemble_code IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM affectation a
                  WHERE a.ensemble_code = m.ensemble_code AND a.composant_id = m.composant_id)
GROUP BY m.ensemble_code, m.composant_id
HAVING SUM(CASE m.type_mouvement WHEN 'Sortie montage' THEN m.qte ELSE -m.qte END) > 0;

CREATE VIEW v_stock AS
SELECT v.id,
       v.designation,
       v.bloc_code,
       v.stock_actuel,
       v.pu_ht,
       v.stock_actuel * v.pu_ht AS valeur_ht,
       (SELECT m.emplacement FROM mouvement_stock m
        WHERE m.composant_id = v.id AND m.emplacement IS NOT NULL
        ORDER BY m.date DESC, m.id DESC LIMIT 1)          AS emplacement,
       (SELECT MAX(m.date) FROM mouvement_stock m
        WHERE m.composant_id = v.id)                      AS dernier_mouvement
FROM v_composant v
WHERE v.stock_actuel <> 0;

CREATE VIEW v_pilotage AS
WITH
param AS (
    SELECT CAST((SELECT valeur FROM parametre WHERE cle = 'budget_ht') AS REAL) AS budget_ht
),
comp AS (
    SELECT COUNT(*)                                                  AS nb_composants,
           COUNT(CASE WHEN mode_appro = 'Achat' THEN 1 END)          AS nb_achat,
           COUNT(CASE WHEN mode_appro <> 'Achat' THEN 1 END)         AS nb_hors_achat,
           COALESCE(SUM(a_chiffrer), 0)                              AS nb_a_chiffrer,
           COUNT(CASE WHEN criticite = 'Bloquant'
                       AND avancement IN ('A commander', 'Commande') THEN 1 END)
                                                                     AS nb_bloquants_ouverts,
           TOTAL(total_ht)                                           AS cout_ht,
           TOTAL(total_ttc)                                          AS cout_ttc,
           TOTAL(MAX(stock_actuel, 0) * pu_ht)                       AS valeur_stock,
           COUNT(CASE WHEN avancement = 'Recu' THEN 1 END) * 100.0
               / NULLIF(COUNT(CASE WHEN avancement <> 'Hors achat' THEN 1 END), 0)
                                                                     AS avancement_appro_pct,
           COUNT(CASE WHEN qte_affectee = 0 THEN 1 END)              AS nb_composants_non_affectes,
           COUNT(CASE WHEN nb_ensembles > 0 AND ecart_affectation <> 0 THEN 1 END)
                                                                 AS nb_composants_ecart_affectation
    FROM v_composant
),
engage AS (
    SELECT (SELECT TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0)) FROM v_ligne_engagee)
         + (SELECT TOTAL(port_ht) FROM commande
            WHERE archive = 0 AND type = 'Commande'
              AND statut IN ('Commande', 'Livre partiel', 'Livre')) AS montant_engage_ht
),
cmd AS (
    SELECT COUNT(*) AS nb_commandes,
           COUNT(CASE WHEN statut IN ('Devis demande', 'Devis recu', 'Devis valide',
                                      'Commande', 'Livre partiel') THEN 1 END)
               AS nb_commandes_en_cours,
           COUNT(CASE WHEN livraison_annoncee < date('now', 'localtime')
                       AND date_reception_reelle IS NULL
                       AND statut NOT IN ('Livre', 'Refuse') THEN 1 END)
               AS nb_commandes_retard
    FROM commande
    WHERE archive = 0
)
SELECT comp.*,
       param.budget_ht,
       comp.cout_ht - param.budget_ht                                AS ecart_budget_ht,
       (comp.cout_ht - param.budget_ht) * 100.0 / NULLIF(param.budget_ht, 0)
                                                                     AS ecart_budget_pct,
       comp.cout_ht * 100.0 / NULLIF(param.budget_ht, 0)             AS consommation_pct,
       engage.montant_engage_ht,
       param.budget_ht - engage.montant_engage_ht                    AS reste_a_engager_ht,
       cmd.*,
       (SELECT COUNT(*) FROM ensemble WHERE archive = 0)             AS nb_ensembles
FROM comp, param, engage, cmd;

-- Répartitions par valeur de liste : remplacent les compteurs figés par mode et par statut.
CREATE VIEW v_repartition_liste AS
SELECT 'mode_appro' AS liste, mode_appro AS code, COUNT(*) AS nb, TOTAL(total_ht) AS cout_ht
FROM v_composant GROUP BY mode_appro
UNION ALL
SELECT 'statut_choix', statut_choix, COUNT(*), TOTAL(total_ht)
FROM v_composant WHERE statut_choix IS NOT NULL GROUP BY statut_choix
UNION ALL
SELECT 'statut_appro', statut_appro, COUNT(*), TOTAL(total_ht)
FROM v_composant GROUP BY statut_appro;
