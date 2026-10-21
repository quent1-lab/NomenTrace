-- 023 : réglages imposés par le dossier (phase 15b-2).
-- Un projet rangé dans un dossier reçoit de la référence du dossier ses blocs, ses listes
-- imposées, ses attributs, ses réglages imposés et son logo. Une ligne unique dit si le
-- verrou est posé (actif), si une synchronisation est en cours (propagation, posé puis
-- retiré dans la même transaction), l'empreinte du contenu de référence appliqué, et, dans la
-- base de référence elle-même, si elle a déjà été initialisée.
-- Les déclencheurs refusent toute écriture d'un réglage imposé quand le verrou est posé et
-- qu'aucune synchronisation n'est en cours : aucune route ne peut l'oublier.

CREATE TABLE reglages_imposes (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    actif        INTEGER NOT NULL DEFAULT 0 CHECK (actif IN (0, 1)),
    propagation  INTEGER NOT NULL DEFAULT 0 CHECK (propagation IN (0, 1)),
    initialisee  INTEGER NOT NULL DEFAULT 0 CHECK (initialisee IN (0, 1)),
    dossier      TEXT,
    empreinte    TEXT
);
INSERT INTO reglages_imposes (id) VALUES (1);

-- Bloc : code, nom, ordre, description et archivage imposés ; budget cible et responsable
-- restent au projet.
CREATE TRIGGER impose_bloc_insertion BEFORE INSERT ON bloc
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les blocs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_bloc_modification BEFORE UPDATE OF code, nom, ordre, description, archive ON bloc
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (NEW.code IS NOT OLD.code OR NEW.nom IS NOT OLD.nom OR NEW.ordre IS NOT OLD.ordre
          OR NEW.description IS NOT OLD.description OR NEW.archive IS NOT OLD.archive)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les blocs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_bloc_suppression BEFORE DELETE ON bloc
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les blocs se règlent dans les paramètres communs');
END;

-- Listes imposées : mode d'appro, criticité, type de mouvement, type de frais.
CREATE TRIGGER impose_liste_insertion BEFORE INSERT ON valeur_liste
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND NEW.liste IN ('mode_appro', 'criticite', 'type_mouvement', 'type_frais')
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : cette liste se règle dans les paramètres communs');
END;

CREATE TRIGGER impose_liste_modification BEFORE UPDATE ON valeur_liste
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.liste IN ('mode_appro', 'criticite', 'type_mouvement', 'type_frais')
          OR NEW.liste IN ('mode_appro', 'criticite', 'type_mouvement', 'type_frais'))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : cette liste se règle dans les paramètres communs');
END;

CREATE TRIGGER impose_liste_suppression BEFORE DELETE ON valeur_liste
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND OLD.liste IN ('mode_appro', 'criticite', 'type_mouvement', 'type_frais')
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : cette liste se règle dans les paramètres communs');
END;

-- Attributs et leurs valeurs : entièrement imposés.
CREATE TRIGGER impose_attribut_insertion BEFORE INSERT ON attribut
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_attribut_modification BEFORE UPDATE ON attribut
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_attribut_suppression BEFORE DELETE ON attribut
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_attribut_valeur_insertion BEFORE INSERT ON attribut_valeur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_attribut_valeur_modification BEFORE UPDATE ON attribut_valeur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

CREATE TRIGGER impose_attribut_valeur_suppression BEFORE DELETE ON attribut_valeur
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : les attributs se règlent dans les paramètres communs');
END;

-- Réglages imposés, budget fixé par le dossier et préfixe figé.
CREATE TRIGGER impose_parametre_insertion BEFORE INSERT ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND NEW.cle IN ('nom_projet', 'taux_tva_defaut', 'champs_obligatoires',
                     'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                     'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                     'contact_achats_tel', 'budget_ht', 'prefixe_id')
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_modification BEFORE UPDATE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND (OLD.cle IN ('nom_projet', 'taux_tva_defaut', 'champs_obligatoires',
                      'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                      'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                      'contact_achats_tel', 'budget_ht', 'prefixe_id'))
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

CREATE TRIGGER impose_parametre_suppression BEFORE DELETE ON parametre
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
     AND OLD.cle IN ('nom_projet', 'taux_tva_defaut', 'champs_obligatoires',
                     'champs_obligatoires_portee', 'etablissement_nom', 'adresse_livraison',
                     'adresse_facturation', 'contact_achats_nom', 'contact_achats_mail',
                     'contact_achats_tel', 'budget_ht', 'prefixe_id')
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : il se règle au niveau du dossier');
END;

-- Logo de l'établissement : imposé.
CREATE TRIGGER impose_logo_insertion BEFORE INSERT ON logo
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : le logo se règle dans les paramètres communs');
END;

CREATE TRIGGER impose_logo_modification BEFORE UPDATE ON logo
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : le logo se règle dans les paramètres communs');
END;

CREATE TRIGGER impose_logo_suppression BEFORE DELETE ON logo
WHEN (SELECT actif = 1 AND propagation = 0 FROM reglages_imposes)
BEGIN
    SELECT RAISE(ABORT, 'réglage imposé par le dossier : le logo se règle dans les paramètres communs');
END;
