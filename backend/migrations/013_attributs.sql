-- 013 : attributs paramétrables des composants (tension, matériau…).
-- Aucun attribut n'est écrit ici : ce sont des données, créées dans Paramètres › Attributs.
-- Un attribut a un code figé (dérivé du libellé à la création), un type figé et une unité.
-- Une seule valeur par composant et par attribut : valeur_nombre pour le type nombre,
-- valeur_texte sinon (texte libre, code d'une valeur de liste, '1' ou '0' pour un booléen).

CREATE TABLE attribut (
    code    TEXT PRIMARY KEY CHECK (length(code) > 0),
    libelle TEXT NOT NULL CHECK (length(libelle) > 0),
    type    TEXT NOT NULL CHECK (type IN ('texte', 'nombre', 'liste', 'booleen')),
    unite   TEXT,
    ordre   INTEGER NOT NULL DEFAULT 0,
    actif   INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1))
);

-- Valeurs possibles d'un attribut de type liste : renommer ne change que le libellé.
CREATE TABLE attribut_valeur (
    attribut_code TEXT NOT NULL REFERENCES attribut(code),
    code          TEXT NOT NULL CHECK (length(code) > 0),
    libelle       TEXT NOT NULL CHECK (length(libelle) > 0),
    ordre         INTEGER NOT NULL DEFAULT 0,
    actif         INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    PRIMARY KEY (attribut_code, code)
);

CREATE TABLE composant_attribut (
    composant_id  TEXT NOT NULL REFERENCES composant(id),
    attribut_code TEXT NOT NULL REFERENCES attribut(code),
    valeur_texte  TEXT,
    valeur_nombre REAL,
    PRIMARY KEY (composant_id, attribut_code),
    CHECK ((valeur_texte IS NULL) <> (valeur_nombre IS NULL))
);

CREATE INDEX idx_composant_attribut_attribut ON composant_attribut(attribut_code);

-- La valeur est rangée dans la colonne de son type ; une valeur de liste doit exister.
CREATE TRIGGER composant_attribut_insertion BEFORE INSERT ON composant_attribut
BEGIN
    SELECT RAISE(ABORT, 'valeur rangée dans la mauvaise colonne pour ce type d''attribut')
    WHERE ((SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'nombre')
          <> (NEW.valeur_nombre IS NOT NULL);
    SELECT RAISE(ABORT, 'valeur absente de la liste de l''attribut')
    WHERE (SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'liste'
      AND NOT EXISTS (SELECT 1 FROM attribut_valeur
                      WHERE attribut_code = NEW.attribut_code AND code = NEW.valeur_texte);
    SELECT RAISE(ABORT, 'un booléen vaut 1 ou 0')
    WHERE (SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'booleen'
      AND NEW.valeur_texte NOT IN ('1', '0');
END;

CREATE TRIGGER composant_attribut_modification BEFORE UPDATE ON composant_attribut
BEGIN
    SELECT RAISE(ABORT, 'valeur rangée dans la mauvaise colonne pour ce type d''attribut')
    WHERE ((SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'nombre')
          <> (NEW.valeur_nombre IS NOT NULL);
    SELECT RAISE(ABORT, 'valeur absente de la liste de l''attribut')
    WHERE (SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'liste'
      AND NOT EXISTS (SELECT 1 FROM attribut_valeur
                      WHERE attribut_code = NEW.attribut_code AND code = NEW.valeur_texte);
    SELECT RAISE(ABORT, 'un booléen vaut 1 ou 0')
    WHERE (SELECT type FROM attribut WHERE code = NEW.attribut_code) = 'booleen'
      AND NEW.valeur_texte NOT IN ('1', '0');
END;

-- Chaque composant non archivé face à chaque attribut, avec sa valeur ou rien : base de la
-- répartition des valeurs (écran d'analyse des attributs).
CREATE VIEW v_attribut_composant AS
SELECT a.code          AS attribut_code,
       v.id            AS composant_id,
       v.bloc_code,
       v.mode_appro,
       v.qte_besoin,
       v.total_ht,
       ca.valeur_texte,
       ca.valeur_nombre
FROM attribut a
CROSS JOIN v_composant v
LEFT JOIN composant_attribut ca ON ca.composant_id = v.id AND ca.attribut_code = a.code;
