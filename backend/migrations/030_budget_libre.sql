-- 030 : budget du projet libre tant que le dossier n'en fixe pas.
-- budget_impose vaut 1 quand la gestion de l'organisme a fixé le budget depuis la page du
-- dossier (propagation.ecrire_budget), 0 sinon : le projet règle alors le sien. Un projet déjà
-- rangé qui porte un budget le tenait jusqu'ici du dossier : il reste imposé.

ALTER TABLE reglages_imposes ADD COLUMN budget_impose INTEGER NOT NULL DEFAULT 0
    CHECK (budget_impose IN (0, 1));

UPDATE reglages_imposes SET budget_impose = 1
WHERE actif = 1
  AND EXISTS (SELECT 1 FROM parametre WHERE cle = 'budget_ht' AND valeur IS NOT NULL);

DROP TRIGGER impose_parametre_insertion;
DROP TRIGGER impose_parametre_modification;
DROP TRIGGER impose_parametre_suppression;

CREATE TRIGGER impose_parametre_insertion BEFORE INSERT ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (NEW.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'prefixe_id')
          OR (NEW.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1)
          OR (NEW.cle = 'budget_ht' AND (SELECT budget_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_modification BEFORE UPDATE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'prefixe_id')
          OR (OLD.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1)
          OR (OLD.cle = 'budget_ht' AND (SELECT budget_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_suppression BEFORE DELETE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'prefixe_id')
          OR (OLD.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1)
          OR (OLD.cle = 'budget_ht' AND (SELECT budget_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;
