"""Recherche globale : composants, commandes, fournisseurs, ensembles et blocs d'un coup.

Chaque type a sa requête fixe, à paramètres liés ; quelques résultats par type suffisent
pour naviguer, la liste complète reste dans l'écran de chaque type.
"""

import sqlite3

from backend import db
from backend.erreurs import ErreurMetier

LONGUEUR_MIN: int = 2
PAR_TYPE: int = 8

# (type, requête) : chaque requête renvoie cle, titre, detail, archive ; ? = motif LIKE.
REQUETES: tuple[tuple[str, str, int], ...] = (
    (
        "composant",
        "SELECT id AS cle, designation AS titre,"
        " trim(coalesce(ref_fabricant, '') || ' ' || coalesce(fournisseur_nom, '')) AS detail,"
        " archive FROM composant"
        " WHERE id LIKE ? OR designation LIKE ? OR ref_fabricant LIKE ? OR fonction LIKE ?"
        " ORDER BY archive, id LIMIT ?",
        4,
    ),
    (
        "commande",
        "SELECT numero AS cle, type || ' ' || coalesce(fournisseur_nom, '') AS titre,"
        " coalesce(reference_externe, '') AS detail, archive FROM commande"
        " WHERE numero LIKE ? OR fournisseur_nom LIKE ? OR reference_externe LIKE ?"
        " ORDER BY archive, numero DESC LIMIT ?",
        3,
    ),
    (
        "fournisseur",
        "SELECT nom AS cle, nom AS titre, coalesce(categorie, '') AS detail, archive"
        " FROM fournisseur WHERE nom LIKE ? OR categorie LIKE ? ORDER BY archive, nom LIMIT ?",
        2,
    ),
    (
        "ensemble",
        "SELECT code AS cle, nom AS titre, '' AS detail, archive FROM ensemble"
        " WHERE code LIKE ? OR nom LIKE ? ORDER BY archive, ordre, code LIMIT ?",
        2,
    ),
    (
        "bloc",
        "SELECT code AS cle, nom AS titre, '' AS detail, archive FROM bloc"
        " WHERE code LIKE ? OR nom LIKE ? ORDER BY archive, ordre, code LIMIT ?",
        2,
    ),
)


def rechercher(conn: sqlite3.Connection, texte: str) -> list[dict]:
    """Groupes de résultats non vides, dans l'ordre des types."""
    terme = texte.strip()
    if len(terme) < LONGUEUR_MIN:
        raise ErreurMetier(f"Saisir au moins {LONGUEUR_MIN} caractères pour rechercher.")
    motif = f"%{terme}%"
    groupes = []
    for type_resultat, requete, nb_motifs in REQUETES:
        resultats = db.fetch_all(conn, requete, (*[motif] * nb_motifs, PAR_TYPE))
        if resultats:
            groupes.append({"type": type_resultat, "resultats": resultats})
    return groupes
