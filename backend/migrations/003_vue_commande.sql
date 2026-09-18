-- 003 : vue des commandes avec leurs totaux et l'indicateur de retard.
-- Aucun arrondi ici. Définition du retard : docs/MODELE.md.

CREATE VIEW v_commande AS
WITH lignes AS (
    SELECT commande_numero,
           COUNT(*)                                         AS nb_lignes,
           TOTAL(qte_commandee * COALESCE(pu_ht_devis, 0))  AS montant_articles_ht
    FROM ligne_commande
    WHERE statut_ligne <> 'Annulee'
    GROUP BY commande_numero
)
SELECT c.*,
       COALESCE(l.nb_lignes, 0)                        AS nb_lignes,
       COALESCE(l.montant_articles_ht, 0)              AS montant_articles_ht,
       COALESCE(l.montant_articles_ht, 0) + c.port_ht  AS total_ht,
       (COALESCE(l.montant_articles_ht, 0) + c.port_ht) * (1 + c.taux_tva) AS total_ttc,
       CASE WHEN c.livraison_annoncee < date('now', 'localtime')
             AND c.date_reception_reelle IS NULL
             AND c.statut NOT IN ('Livre', 'Refuse') THEN 1 ELSE 0 END AS en_retard,
       CASE WHEN c.type = 'Commande'
             AND c.statut IN ('Commande', 'Livre partiel', 'Livre') THEN 1 ELSE 0 END
                                                       AS engagee
FROM commande c
LEFT JOIN lignes l ON l.commande_numero = c.numero
WHERE c.archive = 0;
