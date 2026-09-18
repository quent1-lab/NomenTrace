"""Mouvements de stock."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import composants

TYPES_MONTAGE: frozenset[str] = frozenset({"Sortie montage", "Retour montage"})


def list_mouvements(
    conn: sqlite3.Connection,
    composant: str | None = None,
    type_mouvement: str | None = None,
    ensemble: str | None = None,
) -> list[dict]:
    """Renvoie les mouvements, les plus récents en premier, filtrés si demandé."""
    return db.fetch_all(
        conn,
        "SELECT m.*, c.designation FROM mouvement_stock m"
        " LEFT JOIN composant c ON c.id = m.composant_id"
        " WHERE (? IS NULL OR m.composant_id = ?) AND (? IS NULL OR m.type_mouvement = ?)"
        " AND (? IS NULL OR m.ensemble_code = ?) ORDER BY m.date DESC, m.id DESC",
        (composant, composant, type_mouvement, type_mouvement, ensemble, ensemble),
    )


def _check_mouvement(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> None:
    """Contrôle la cohérence du mouvement avant de laisser la base trancher."""
    composants.get_composant(conn, valeurs["composant_id"])
    type_mouvement = valeurs["type_mouvement"]
    ensemble = valeurs.get("ensemble_code")
    if type_mouvement in TYPES_MONTAGE and not ensemble:
        raise ErreurMetier(f"Un mouvement « {type_mouvement} » doit désigner un ensemble.")
    if type_mouvement not in TYPES_MONTAGE and ensemble:
        raise ErreurMetier("Seuls les mouvements de montage désignent un ensemble.")
    if type_mouvement == "Sortie montage" and valeurs["sens"] != "Sortie":
        raise ErreurMetier("Une sortie montage est forcément une sortie de stock.")
    if type_mouvement == "Retour montage" and valeurs["sens"] != "Entree":
        raise ErreurMetier("Un retour montage est forcément une entrée en stock.")
    if ensemble and not db.fetch_one(
        conn, "SELECT 1 FROM ensemble WHERE code = ? AND archive = 0", (ensemble,)
    ):
        raise Introuvable(f"Ensemble « {ensemble} » introuvable ou archivé.")
    numero = valeurs.get("commande_numero")
    if numero and not db.fetch_one(conn, "SELECT 1 FROM commande WHERE numero = ?", (numero,)):
        raise Introuvable(f"Commande « {numero} » introuvable.")


def create_mouvement(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Enregistre un mouvement de stock. Un stock négatif est autorisé : il sera signalé."""
    with db.transaction(conn):
        _check_mouvement(conn, valeurs)
        identifiant = db.insert_row(conn, "mouvement_stock", valeurs)
    return db.fetch_one(conn, "SELECT * FROM mouvement_stock WHERE id = ?", (identifiant,)) or {}
