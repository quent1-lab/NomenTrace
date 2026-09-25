-- Fiche fournisseur : catégorie d'achat, contact pour les devis, numéro de compte client.
-- « compte_ecole » devient « numero_compte » : le nom de colonne ne présume plus du client.
ALTER TABLE fournisseur RENAME COLUMN compte_ecole TO numero_compte;
ALTER TABLE fournisseur ADD COLUMN categorie TEXT;
ALTER TABLE fournisseur ADD COLUMN contact TEXT;
