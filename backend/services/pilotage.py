"""Indicateurs globaux de pilotage."""

import sqlite3

from backend import db


def get_pilotage(conn: sqlite3.Connection) -> dict:
    """Renvoie la ligne unique de v_pilotage."""
    return db.fetch_one(conn, "SELECT * FROM v_pilotage") or {}
