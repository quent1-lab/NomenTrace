-- nomentrace: reconstruction
-- 018 : frais d'une commande (livraison, douane, frais de facturation…), en lignes typées,
-- à la place du seul port. Le type vient d'une nouvelle liste paramétrable, type_frais.
--
-- valeur_liste est recréée pour élargir sa contrainte de liste. Elle n'est pas renommée :
-- une copie temporaire garde ses lignes, puis la table est recréée sous son propre nom, si
-- bien que la vue v_qualite_composant et les déclencheurs qui la citent restent valables.
--
-- Le port déjà saisi devient un frais « Livraison » ; la colonne commande.port_ht reste,
-- toujours à 0, pour ne pas reconstruire commande et toutes les vues qui en dépendent.

CREATE TEMP TABLE valeur_liste_copie AS SELECT * FROM valeur_liste;
DROP TABLE valeur_liste;
CREATE TABLE valeur_liste (
    liste   TEXT NOT NULL
        CHECK (liste IN ('mode_appro', 'statut_appro', 'statut_choix', 'criticite',
                         'type_mouvement', 'type_frais')),
    code    TEXT NOT NULL CHECK (length(code) > 0),
    libelle TEXT NOT NULL CHECK (length(libelle) > 0),
    ordre   INTEGER NOT NULL DEFAULT 0,
    actif   INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    systeme INTEGER NOT NULL DEFAULT 0 CHECK (systeme IN (0, 1)),
    -- Sens imposé d'un type de mouvement ; NULL = libre (inventaire).
    sens    TEXT CHECK (sens IN ('Entree', 'Sortie')),
    PRIMARY KEY (liste, code)
);
INSERT INTO valeur_liste (liste, code, libelle, ordre, actif, systeme, sens)
SELECT liste, code, libelle, ordre, actif, systeme, sens FROM valeur_liste_copie;
DROP TABLE valeur_liste_copie;

-- Vocabulaire de départ, modifiable dans Paramètres › Listes de valeurs.
INSERT INTO valeur_liste (liste, code, libelle, ordre) VALUES
    ('type_frais', 'Livraison', 'Livraison', 1),
    ('type_frais', 'Douane', 'Douane', 2),
    ('type_frais', 'Facturation', 'Frais de facturation', 3),
    ('type_frais', 'Dossier', 'Frais de dossier', 4),
    ('type_frais', 'Autre', 'Autre', 5);

CREATE TABLE frais_commande (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commande_numero TEXT NOT NULL REFERENCES commande(numero),
    type_frais      TEXT NOT NULL,
    montant_ht      REAL NOT NULL CHECK (montant_ht >= 0),
    commentaire     TEXT
);
CREATE INDEX idx_frais_commande ON frais_commande(commande_numero);

CREATE TRIGGER frais_type_insertion BEFORE INSERT ON frais_commande
BEGIN
    SELECT RAISE(ABORT, 'Type de frais inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'type_frais' AND code = NEW.type_frais);
END;

CREATE TRIGGER frais_type_modification BEFORE UPDATE OF type_frais ON frais_commande
BEGIN
    SELECT RAISE(ABORT, 'Type de frais inconnu')
    WHERE NOT EXISTS (SELECT 1 FROM valeur_liste
                      WHERE liste = 'type_frais' AND code = NEW.type_frais);
END;

INSERT INTO frais_commande (commande_numero, type_frais, montant_ht, commentaire)
SELECT numero, 'Livraison', port_ht, 'Port repris de l''ancienne saisie'
FROM commande WHERE port_ht > 0;
UPDATE commande SET port_ht = 0 WHERE port_ht <> 0;

-- Totaux d'une commande : articles + frais. Aucun arrondi ici.
DROP VIEW v_commande;
CREATE VIEW v_commande AS
WITH lignes AS (
    SELECT commande_numero,
           COUNT(*)                                         AS nb_lignes,
           TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0))  AS montant_articles_ht
    FROM ligne_commande
    WHERE statut_ligne <> 'Annulee'
    GROUP BY commande_numero
),
frais AS (
    SELECT commande_numero, TOTAL(montant_ht) AS montant_frais_ht
    FROM frais_commande
    GROUP BY commande_numero
)
SELECT c.*,
       COALESCE(l.nb_lignes, 0)                        AS nb_lignes,
       COALESCE(l.montant_articles_ht, 0)              AS montant_articles_ht,
       COALESCE(f.montant_frais_ht, 0)                 AS montant_frais_ht,
       COALESCE(l.montant_articles_ht, 0) + COALESCE(f.montant_frais_ht, 0) AS total_ht,
       (COALESCE(l.montant_articles_ht, 0) + COALESCE(f.montant_frais_ht, 0)) * (1 + c.taux_tva)
                                                       AS total_ttc,
       CASE WHEN c.livraison_annoncee < date('now', 'localtime')
             AND c.date_reception_reelle IS NULL
             AND c.statut NOT IN ('Livre', 'Refuse') THEN 1 ELSE 0 END AS en_retard,
       CASE WHEN c.type = 'Commande'
             AND c.statut IN ('Commande', 'Livre partiel', 'Livre') THEN 1 ELSE 0 END
                                                       AS engagee
FROM commande c
LEFT JOIN lignes l ON l.commande_numero = c.numero
LEFT JOIN frais f ON f.commande_numero = c.numero
WHERE c.archive = 0;

-- Montant engagé global : lignes engagées + tous les frais des commandes engagées.
DROP VIEW v_pilotage;
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
         + (SELECT TOTAL(f.montant_ht) FROM frais_commande f
            JOIN commande c ON c.numero = f.commande_numero
            WHERE c.archive = 0 AND c.type = 'Commande'
              AND c.statut IN ('Commande', 'Livre partiel', 'Livre')) AS montant_engage_ht
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
