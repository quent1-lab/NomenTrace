-- 033 : commandes qui attendent leur réception dans Nomentrace.
-- Par commande passée : le nombre de lignes non annulées encore incomplètes, et l'indicateur
-- « à réceptionner » quand la livraison est acquise (statut Livré, ou arrivée annoncée par le
-- suivi de l'établissement à une date atteinte) alors que des lignes restent à recevoir.
-- Une commande simplement commandée qui attend son colis n'est pas à réceptionner.

CREATE VIEW v_reception_attendue AS
SELECT c.numero,
       COUNT(l.id) AS nb_lignes_a_recevoir,
       CASE WHEN COUNT(l.id) > 0
                 AND (c.statut = 'Livre'
                      OR (c.statut IN ('Commande', 'Livre partiel')
                          AND c.date_reception_annoncee <= date('now', 'localtime')))
            THEN 1 ELSE 0 END AS a_receptionner
FROM commande c
LEFT JOIN ligne_commande l
       ON l.commande_numero = c.numero
      AND l.statut_ligne <> 'Annulee'
      AND l.qte_recue < l.qte_commandee
WHERE c.type = 'Commande'
GROUP BY c.numero;
