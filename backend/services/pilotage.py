"""Indicateurs globaux de pilotage."""

import sqlite3

from backend import db


def get_pilotage(conn: sqlite3.Connection) -> dict:
    """Renvoie la ligne unique de v_pilotage, et le nombre de fournisseurs à valider."""
    pilotage = db.fetch_one(conn, "SELECT * FROM v_pilotage") or {}
    pilotage["nb_fournisseurs_a_valider"] = conn.execute(
        "SELECT COUNT(*) FROM fournisseur WHERE archive = 0 AND statut = 'A valider'"
    ).fetchone()[0]
    return pilotage
