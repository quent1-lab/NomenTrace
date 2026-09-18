"""Blocs fonctionnels."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Introuvable
from backend.services import journal

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {"nom", "ordre", "budget_cible_ht", "responsable", "description"}
)


def list_blocs(conn: sqlite3.Connection) -> list[dict]:
    """Renvoie les blocs avec leurs indicateurs, triés par ordre."""
    return db.fetch_all(conn, "SELECT * FROM v_bloc ORDER BY ordre, code")


def get_bloc(conn: sqlite3.Connection, code: str) -> dict:
    """Renvoie un bloc avec ses indicateurs."""
    bloc = db.fetch_one(conn, "SELECT * FROM v_bloc WHERE code = ?", (code,))
    if bloc is None:
        raise Introuvable(f"Bloc « {code} » introuvable.")
    return bloc


def patch_bloc(conn: sqlite3.Connection, code: str, modifications: dict[str, Any]) -> dict:
    """Modifie un bloc ; son code, figé dans les identifiants, n'est jamais modifiable."""
    with db.transaction(conn):
        journal.update_with_journal(conn, "bloc", code, modifications, CHAMPS_MODIFIABLES)
    return get_bloc(conn, code)
