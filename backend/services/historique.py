"""Historique : la frise d'un composant et le journal de tout le projet.

La frise d'un composant assemble ce qui le concerne, quelle que soit la table où c'est
écrit : journal (le composant, ses caractéristiques, ses affectations, ses lignes de
commande, les commandes et documents de commande qui le citent) et mouvements de stock.
Chaque événement porte une catégorie : modification, achat, stock, montage, document.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from backend import db
from backend.services import tableur

CATEGORIES: tuple[str, ...] = ("modification", "achat", "stock", "montage", "document")
ORIGINES: frozenset[str] = frozenset({"interface", "import"})
TAILLE_PAGE_MAX: int = 500

# Journal qui concerne un composant, avec le fichier importé éventuel. Chaque bloc renvoie
# les colonnes du journal, le numéro de commande éventuel et une catégorie ; :id est
# l'identifiant du composant.
SQL_FRISE = """
SELECT e.*, lot.nom_fichier FROM (
SELECT j.*, NULL AS commande_numero,
       CASE WHEN j.champ LIKE 'document %' THEN 'document' ELSE 'modification' END AS categorie
FROM journal j WHERE j.table_cible = 'composant' AND j.cle_cible = :id
UNION ALL
SELECT j.*, NULL, 'modification'
FROM journal j WHERE j.table_cible = 'composant_attribut'
  AND j.cle_cible IN (SELECT :id || ':' || code FROM attribut)
UNION ALL
SELECT j.*, NULL, 'montage'
FROM journal j WHERE j.table_cible = 'affectation'
  AND j.cle_cible IN (SELECT code || ':' || :id FROM ensemble)
UNION ALL
SELECT j.*, j.cle_cible, 'achat'
FROM journal j WHERE j.table_cible = 'commande' AND j.champ LIKE 'ligne %'
  AND (j.nouvelle_valeur = :id OR j.ancienne_valeur = :id)
UNION ALL
SELECT j.*, l.commande_numero, 'achat'
FROM journal j JOIN ligne_commande l ON CAST(l.id AS TEXT) = j.cle_cible
WHERE j.table_cible = 'ligne_commande' AND l.composant_id = :id
UNION ALL
SELECT j.*, j.cle_cible,
       CASE WHEN j.champ LIKE 'document %' THEN 'document' ELSE 'achat' END
FROM journal j WHERE j.table_cible = 'commande'
  AND (j.champ IN ('statut', 'type', 'date_commande', 'livraison_annoncee')
       OR j.champ LIKE 'document %')
  AND j.cle_cible IN (SELECT commande_numero FROM ligne_commande WHERE composant_id = :id)
) e LEFT JOIN import_lot lot ON lot.id = e.lot_id
"""


def list_evenements_composant(conn: sqlite3.Connection, identifiant: str) -> list[dict]:
    """Frise d'un composant, la plus récente en haut."""
    evenements = [
        {**dict(ligne), "source": "journal"}
        for ligne in conn.execute(SQL_FRISE, {"id": identifiant}).fetchall()
    ]
    for mouvement in db.fetch_all(
        conn, "SELECT * FROM mouvement_stock WHERE composant_id = ?", (identifiant,)
    ):
        evenements.append(
            {
                "source": "mouvement",
                "horodatage": mouvement["date"],
                "table_cible": "mouvement_stock",
                "cle_cible": str(mouvement["id"]),
                "champ": None,
                "ancienne_valeur": None,
                "nouvelle_valeur": None,
                "origine": "interface",
                "categorie": "montage" if mouvement["ensemble_code"] else "stock",
                **{
                    cle: mouvement[cle]
                    for cle in (
                        "id",
                        "sens",
                        "type_mouvement",
                        "qte",
                        "ensemble_code",
                        "commande_numero",
                        "emplacement",
                        "par_qui",
                        "commentaire",
                    )
                },
            }
        )
    # Un mouvement n'a qu'une date : il passe après les événements horodatés du même jour.
    evenements.sort(
        key=lambda e: (e["horodatage"], e["source"] == "journal", e["id"]), reverse=True
    )
    return evenements


@dataclass
class FiltresJournal:
    """Filtres de l'historique global ; tous facultatifs."""

    table: str | None = None
    origine: str | None = None
    du: str | None = None
    au: str | None = None
    texte: str | None = None


def _where(filtres: FiltresJournal) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if filtres.table:
        clauses.append("j.table_cible = ?")
        params.append(filtres.table)
    if filtres.origine:
        clauses.append("j.origine = ?")
        params.append(filtres.origine)
    if filtres.du:
        clauses.append("j.horodatage >= ?")
        params.append(filtres.du)
    if filtres.au:
        # Borne incluse : tout le jour « au ».
        clauses.append("substr(j.horodatage, 1, 10) <= ?")
        params.append(filtres.au)
    if filtres.texte:
        clauses.append(
            "(j.cle_cible LIKE ? OR j.champ LIKE ? OR j.ancienne_valeur LIKE ?"
            " OR j.nouvelle_valeur LIKE ?)"
        )
        params.extend([f"%{filtres.texte}%"] * 4)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_journal(
    conn: sqlite3.Connection, filtres: FiltresJournal, page: int = 1, taille: int = 100
) -> dict:
    """Une page du journal filtré, le plus récent en haut, et le nombre total de lignes."""
    taille = min(max(taille, 1), TAILLE_PAGE_MAX)
    page = max(page, 1)
    where, params = _where(filtres)
    total = conn.execute(f"SELECT COUNT(*) FROM journal j{where}", params).fetchone()[0]  # noqa: S608
    lignes = db.fetch_all(
        conn,
        "SELECT j.*, l.nom_fichier FROM journal j LEFT JOIN import_lot l ON l.id = j.lot_id"  # noqa: S608
        f"{where} ORDER BY j.id DESC LIMIT ? OFFSET ?",
        (*params, taille, (page - 1) * taille),
    )
    return {"total": total, "page": page, "taille": taille, "lignes": lignes}


def list_tables(conn: sqlite3.Connection) -> list[str]:
    """Tables présentes dans le journal, pour le filtre."""
    return [
        ligne[0]
        for ligne in conn.execute(
            "SELECT DISTINCT table_cible FROM journal ORDER BY table_cible"
        ).fetchall()
    ]


COLONNES_EXPORT: tuple[tuple[str, str], ...] = (
    ("horodatage", "Date"),
    ("table_cible", "Élément"),
    ("cle_cible", "Clé"),
    ("champ", "Champ"),
    ("ancienne_valeur", "Ancienne valeur"),
    ("nouvelle_valeur", "Nouvelle valeur"),
    ("origine", "Origine"),
    ("utilisateur", "Utilisateur"),
    ("nom_fichier", "Fichier importé"),
)


def build_export_journal(conn: sqlite3.Connection, filtres: FiltresJournal) -> bytes:
    """Classeur Excel de tout le journal filtré (sans pagination)."""
    where, params = _where(filtres)
    lignes = db.fetch_all(
        conn,
        "SELECT j.*, l.nom_fichier FROM journal j LEFT JOIN import_lot l ON l.id = j.lot_id"  # noqa: S608
        f"{where} ORDER BY j.id DESC",
        tuple(params),
    )
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Historique"
    feuille.append([titre for _, titre in COLONNES_EXPORT])
    for ligne in lignes:
        feuille.append([ligne[cle] for cle, _ in COLONNES_EXPORT])
    feuille.freeze_panes = "A2"
    for colonne, largeur in zip("ABCDEFGHI", (20, 16, 24, 22, 30, 30, 11, 18, 30), strict=True):
        feuille.column_dimensions[colonne].width = largeur
    tableur.neutraliser_formules(classeur)
    flux = BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def nom_export(maintenant: datetime | None = None) -> str:
    return f"nomentrace_historique_{(maintenant or datetime.now()):%Y%m%d_%H%M}.xlsx"
