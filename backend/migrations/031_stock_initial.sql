-- 031 : la quantité déjà disponible d'un composant entre au stock.
-- Un mouvement « Stock initial » (type système, entrée) par composant au plus, tenu par la base
-- quel que soit le chemin d'écriture (fiche, import, reclassement, assistant) : créé quand
-- qte_disponible devient positive, ajusté quand elle change, retiré quand elle revient à zéro
-- ou que le composant est supprimé. Le calcul de qte_a_acheter ne change pas. Ce mouvement ne
-- compte pas comme une trace qui interdit la suppression : il part avec le composant.

-- Un projet rangé dans un dossier refuse d'écrire ses listes imposées (023) : la valeur
-- système s'écrit comme une synchronisation, verrou levé le temps de l'écriture. La base de
-- référence du dossier reçoit la même valeur par cette migration : les synchronisations
-- suivantes la retrouvent des deux côtés.
UPDATE reglages_imposes SET propagation = 1 WHERE id = 1;

INSERT OR IGNORE INTO valeur_liste (liste, code, libelle, ordre, systeme, sens)
VALUES ('type_mouvement', 'Stock initial', 'Stock initial', 4, 1, 'Entree');

UPDATE valeur_liste SET systeme = 1, actif = 1, sens = 'Entree'
WHERE liste = 'type_mouvement' AND code = 'Stock initial';

UPDATE reglages_imposes SET propagation = 0 WHERE id = 1;

-- Reprise de l'existant : archivés compris, comme le ferait le déclencheur.
INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte, commentaire)
SELECT date('now', 'localtime'), id, 'Entree', 'Stock initial', qte_disponible,
       'Quantité déjà disponible du composant'
FROM composant
WHERE qte_disponible > 0;

CREATE TRIGGER stock_initial_creation AFTER INSERT ON composant
WHEN NEW.qte_disponible > 0
BEGIN
    INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte, commentaire)
    VALUES (date('now', 'localtime'), NEW.id, 'Entree', 'Stock initial', NEW.qte_disponible,
            'Quantité déjà disponible du composant');
END;

CREATE TRIGGER stock_initial_modification AFTER UPDATE OF qte_disponible ON composant
WHEN NEW.qte_disponible IS NOT OLD.qte_disponible
BEGIN
    DELETE FROM mouvement_stock
    WHERE composant_id = NEW.id AND type_mouvement = 'Stock initial'
      AND NEW.qte_disponible = 0;
    UPDATE mouvement_stock SET qte = NEW.qte_disponible
    WHERE composant_id = NEW.id AND type_mouvement = 'Stock initial'
      AND NEW.qte_disponible > 0;
    INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte, commentaire)
    SELECT date('now', 'localtime'), NEW.id, 'Entree', 'Stock initial', NEW.qte_disponible,
           'Quantité déjà disponible du composant'
    WHERE NEW.qte_disponible > 0
      AND NOT EXISTS (SELECT 1 FROM mouvement_stock
                      WHERE composant_id = NEW.id AND type_mouvement = 'Stock initial');
END;

CREATE TRIGGER stock_initial_suppression BEFORE DELETE ON composant
BEGIN
    DELETE FROM mouvement_stock
    WHERE composant_id = OLD.id AND type_mouvement = 'Stock initial';
END;

-- Le stock initial ne compte plus parmi les traces qui interdisent la suppression.
DROP VIEW v_qualite_composant;
CREATE VIEW v_qualite_composant AS
SELECT c.id,
       c.bloc_code,
       c.fonction,
       c.designation,
       c.ref_fabricant,
       c.mode_appro,
       c.fournisseur_nom,
       c.archive,
       c.remplace_par,
       CASE WHEN LENGTH(TRIM(c.designation)) < 4 THEN 1 ELSE 0 END    AS designation_courte,
       CASE WHEN TRIM(c.fonction) = '' THEN 1 ELSE 0 END               AS fonction_vide,
       CASE WHEN c.mode_appro = 'Achat' AND c.pu_releve IS NULL THEN 1 ELSE 0 END
                                                                       AS achat_sans_prix,
       CASE WHEN c.mode_appro = 'Achat' AND c.fournisseur_nom IS NULL THEN 1 ELSE 0 END
                                                                       AS achat_sans_fournisseur,
       CASE WHEN c.qte_besoin = 0 THEN 1 ELSE 0 END                    AS besoin_nul,
       CASE WHEN TRIM(COALESCE(c.lien_produit, '')) <> ''
             AND LOWER(TRIM(c.lien_produit)) NOT LIKE 'http://_%'
             AND LOWER(TRIM(c.lien_produit)) NOT LIKE 'https://_%' THEN 1 ELSE 0 END
                                                                       AS lien_invalide,
       CASE WHEN EXISTS (
                SELECT 1 FROM valeur_liste v
                WHERE v.actif = 0
                  AND ((v.liste = 'mode_appro' AND v.code = c.mode_appro)
                    OR (v.liste = 'statut_appro' AND v.code = c.statut_appro)
                    OR (v.liste = 'statut_choix' AND v.code = c.statut_choix)
                    OR (v.liste = 'criticite' AND v.code = c.criticite)))
            THEN 1 ELSE 0 END                                          AS valeur_desactivee,
       CASE WHEN EXISTS (
                SELECT 1 FROM fournisseur f WHERE f.nom = c.fournisseur_nom AND f.archive = 1)
            THEN 1 ELSE 0 END                                          AS fournisseur_archive,
       (SELECT COUNT(*) FROM ligne_commande l WHERE l.composant_id = c.id) AS nb_lignes_commande,
       (SELECT COUNT(*) FROM mouvement_stock m
        WHERE m.composant_id = c.id AND m.type_mouvement <> 'Stock initial') AS nb_mouvements,
       (SELECT COUNT(*) FROM document d WHERE d.composant_id = c.id)       AS nb_documents,
       (SELECT COUNT(*) FROM composant r WHERE r.remplace_par = c.id)      AS nb_remplaces
FROM composant c;
