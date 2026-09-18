"""Dépendances FastAPI partagées par les routes."""

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from backend import db


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Ouvre une connexion SQLite pour la durée de la requête."""
    conn = db.connect(request.app.state.chemin_base)
    try:
        yield conn
    finally:
        conn.close()
