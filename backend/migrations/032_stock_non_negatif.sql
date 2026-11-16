-- 032 : un stock ne devient jamais négatif.
-- La base refuse toute écriture qui fait baisser le stock d'un composant sous zéro : une sortie
-- de trop (montage, perte, inventaire), une entrée retirée ou réduite (stock initial ramené
-- sous ce qui a déjà servi). Une écriture qui fait monter le stock reste permise, même si une
-- base ancienne porte déjà un stock négatif : c'est elle qui le corrige.

CREATE TRIGGER stock_non_negatif_insertion AFTER INSERT ON mouvement_stock
WHEN NEW.sens = 'Sortie'
 AND (SELECT TOTAL(CASE sens WHEN 'Entree' THEN qte ELSE -qte END)
      FROM mouvement_stock WHERE composant_id = NEW.composant_id) < 0
BEGIN
    SELECT RAISE(ABORT, 'stock insuffisant : le stock du composant deviendrait négatif');
END;

CREATE TRIGGER stock_non_negatif_modification AFTER UPDATE ON mouvement_stock
WHEN (CASE NEW.sens WHEN 'Entree' THEN NEW.qte ELSE -NEW.qte END)
     < (CASE OLD.sens WHEN 'Entree' THEN OLD.qte ELSE -OLD.qte END)
 AND (SELECT TOTAL(CASE sens WHEN 'Entree' THEN qte ELSE -qte END)
      FROM mouvement_stock WHERE composant_id = NEW.composant_id) < 0
BEGIN
    SELECT RAISE(ABORT, 'stock insuffisant : le stock du composant deviendrait négatif');
END;

CREATE TRIGGER stock_non_negatif_suppression AFTER DELETE ON mouvement_stock
WHEN OLD.sens = 'Entree'
 AND (SELECT TOTAL(CASE sens WHEN 'Entree' THEN qte ELSE -qte END)
      FROM mouvement_stock WHERE composant_id = OLD.composant_id) < 0
BEGIN
    SELECT RAISE(ABORT, 'stock insuffisant : le stock du composant deviendrait négatif');
END;
