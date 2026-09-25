-- 014 : arborescence d'ensembles et budgets d'ensemble.
-- Un ensemble a au plus un parent (parent_code, prévu dès le schéma initial). La racine de
-- l'arbre n'est pas stockée : c'est un nœud virtuel au nom du projet. Le refus des cycles et
-- des parents archivés est fait par le service (une expression WITH est interdite dans un
-- déclencheur) ; la base refuse seulement qu'un ensemble soit son propre parent.
-- Budget d'ensemble : budget_cible_ht n'est pris en compte que si budget_verrouille = 1 ;
-- sinon le budget est réparti au prorata du coût estimé, recalculé à chaque lecture.

ALTER TABLE ensemble ADD COLUMN budget_cible_ht REAL
    CHECK (budget_cible_ht IS NULL OR budget_cible_ht >= 0);
ALTER TABLE ensemble ADD COLUMN budget_verrouille INTEGER NOT NULL DEFAULT 0
    CHECK (budget_verrouille IN (0, 1) AND (budget_verrouille = 0 OR budget_cible_ht IS NOT NULL));

CREATE INDEX idx_ensemble_parent ON ensemble(parent_code);

CREATE TRIGGER trg_ensemble_parent_insert BEFORE INSERT ON ensemble
WHEN NEW.parent_code = NEW.code
BEGIN
    SELECT RAISE(ABORT, 'Un ensemble ne peut pas être son propre parent.');
END;

CREATE TRIGGER trg_ensemble_parent_update BEFORE UPDATE OF parent_code ON ensemble
WHEN NEW.parent_code = NEW.code
BEGIN
    SELECT RAISE(ABORT, 'Un ensemble ne peut pas être son propre parent.');
END;

-- v_ensemble expose désormais les colonnes de budget. Aucune vue n'en dépend.
DROP VIEW v_ensemble;

CREATE VIEW v_ensemble AS
SELECT e.code,
       e.nom,
       e.ordre,
       e.parent_code,
       e.description,
       e.responsable,
       e.statut_montage,
       e.budget_cible_ht,
       e.budget_verrouille,
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

-- Chaque ensemble non archivé face à lui-même et à chacun de ses descendants non archivés.
-- UNION (et non UNION ALL) : la récursion s'arrête même si un cycle s'était glissé en base.
CREATE VIEW v_ensemble_descendant AS
WITH RECURSIVE descendant(ancetre_code, code) AS (
    SELECT code, code FROM ensemble WHERE archive = 0
    UNION
    SELECT d.ancetre_code, e.code
    FROM descendant d
    JOIN ensemble e ON e.parent_code = d.code AND e.archive = 0
)
SELECT ancetre_code, code FROM descendant;

-- Indicateurs cumulés : un ensemble et tous ses descendants. Mêmes noms de colonnes que
-- v_ensemble. Un composant affecté à plusieurs nœuds de la branche compte une fois dans
-- les comptes de composants distincts, mais toutes ses pièces et tout son coût comptent.
CREATE VIEW v_ensemble_cumul AS
WITH ligne AS (
    SELECT d.ancetre_code, ec.*
    FROM v_ensemble_descendant d
    JOIN v_ensemble_composant ec ON ec.ensemble_code = d.code
)
SELECT e.code,
       (SELECT COUNT(*) - 1 FROM v_ensemble_descendant x WHERE x.ancetre_code = e.code)
                                                       AS nb_sous_ensembles,
       COUNT(DISTINCT l.composant_id)                  AS nb_composants_distincts,
       COALESCE(SUM(l.qte_affectee), 0)                AS nb_pieces_total,
       TOTAL(l.cout_ligne_ht)                          AS cout_ht,
       COUNT(CASE WHEN l.composant_id IS NOT NULL AND l.cout_ligne_ht IS NULL
                  AND l.avancement <> 'Hors achat' THEN 1 END) AS nb_lignes_non_chiffrees,
       COUNT(DISTINCT l.bloc_code)                     AS nb_blocs_representes,
       COUNT(DISTINCT CASE WHEN l.avancement <> 'Hors achat' THEN l.composant_id END)
                                                       AS nb_composants_a_acheter,
       COUNT(DISTINCT CASE WHEN l.avancement = 'Recu' THEN l.composant_id END)
                                                       AS nb_composants_recus,
       COUNT(DISTINCT CASE WHEN l.avancement = 'A commander' THEN l.composant_id END)
                                                       AS nb_composants_non_commandes,
       COALESCE(SUM(MIN(MAX(l.qte_montee, 0), l.qte_affectee)), 0) AS nb_pieces_montees,
       COALESCE(SUM(MIN(MAX(l.qte_montee, 0), l.qte_affectee)), 0) * 100.0
           / NULLIF(SUM(l.qte_affectee), 0)            AS avancement_montage_pct
FROM ensemble e
LEFT JOIN ligne l ON l.ancetre_code = e.code
WHERE e.archive = 0
GROUP BY e.code;

-- Répartition cumulée d'un ensemble et de ses descendants par bloc fonctionnel.
CREATE VIEW v_ensemble_bloc_cumul AS
SELECT d.ancetre_code             AS ensemble_code,
       ec.bloc_code,
       COUNT(DISTINCT ec.composant_id) AS nb_composants,
       SUM(ec.qte_affectee)       AS nb_pieces,
       TOTAL(ec.cout_ligne_ht)    AS cout_ht
FROM v_ensemble_descendant d
JOIN v_ensemble_composant ec ON ec.ensemble_code = d.code
GROUP BY d.ancetre_code, ec.bloc_code;
