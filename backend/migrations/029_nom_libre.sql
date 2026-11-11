-- 029 : nom du projet libre quand le dossier n'en donne pas.
-- nom_impose vaut 1 quand le dossier fixe le nom de ses projets, 0 sinon ; la synchronisation
-- le tient à jour. Les déclencheurs des paramètres ne bloquent plus le nom que dans le
-- premier cas.

ALTER TABLE reglages_imposes ADD COLUMN nom_impose INTEGER NOT NULL DEFAULT 1
    CHECK (nom_impose IN (0, 1));

DROP TRIGGER impose_parametre_insertion;
DROP TRIGGER impose_parametre_modification;
DROP TRIGGER impose_parametre_suppression;

CREATE TRIGGER impose_parametre_insertion BEFORE INSERT ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (NEW.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'budget_ht', 'prefixe_id')
          OR (NEW.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_modification BEFORE UPDATE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'budget_ht', 'prefixe_id')
          OR (OLD.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_suppression BEFORE DELETE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.cle IN ('taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'budget_ht', 'prefixe_id')
          OR (OLD.cle = 'nom_projet' AND (SELECT nom_impose FROM reglages_imposes) = 1))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;
