-- 027 : une commande au statut commandé, livré en partie ou livré est de type Commande.
-- Jusqu'ici, passer le statut d'un devis à « Commande » laissait son type à « Devis » : la
-- commande n'était pas engagée et ses composants restaient à commander. Les commandes déjà
-- dans ce cas passent au type Commande et leurs lignes « A commander » deviennent
-- « Commandee », comme lors d'un passage en commande ; chaque changement est journalisé.
-- Les copies des commandes communes, tenues par leur commune, ne sont pas touchées.

CREATE TEMP TABLE a_rattraper AS
SELECT numero FROM commande
WHERE type = 'Devis' AND statut IN ('Commande', 'Livre partiel', 'Livre') AND commune IS NULL;

INSERT INTO journal (table_cible, cle_cible, champ, ancienne_valeur, nouvelle_valeur, origine)
SELECT 'commande', numero, 'type', 'Devis', 'Commande', 'interface' FROM a_rattraper;

INSERT INTO journal (table_cible, cle_cible, champ, ancienne_valeur, nouvelle_valeur, origine)
SELECT 'ligne_commande', id, 'statut_ligne', 'A commander', 'Commandee', 'interface'
FROM ligne_commande
WHERE statut_ligne = 'A commander' AND commande_numero IN (SELECT numero FROM a_rattraper);

UPDATE ligne_commande SET statut_ligne = 'Commandee'
WHERE statut_ligne = 'A commander' AND commande_numero IN (SELECT numero FROM a_rattraper);

UPDATE commande SET type = 'Commande' WHERE numero IN (SELECT numero FROM a_rattraper);

DROP TABLE a_rattraper;
