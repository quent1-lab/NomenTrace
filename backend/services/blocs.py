"""Blocs fonctionnels."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, Introuvable
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


def create_bloc(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un bloc ; son code, figé dans les identifiants, ne changera plus."""
    code = valeurs["code"]
    with db.transaction(conn):
        if db.fetch_one(conn, "SELECT 1 FROM bloc WHERE code = ?", (code,)):
            raise Conflit(f"Le code de bloc « {code} » est déjà utilisé.")
        if valeurs.get("ordre") is None:
            valeurs = {
                **valeurs,
                "ordre": conn.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM bloc").fetchone()[0],
            }
        db.insert_row(conn, "bloc", valeurs)
        journal.write_journal(conn, "bloc", code, "creation", None, "créé")
    return get_bloc(conn, code)


def patch_bloc(conn: sqlite3.Connection, code: str, modifications: dict[str, Any]) -> dict:
    """Modifie un bloc ; son code, figé dans les identifiants, n'est jamais modifiable."""
    with db.transaction(conn):
        journal.update_with_journal(conn, "bloc", code, modifications, CHAMPS_MODIFIABLES)
    return get_bloc(conn, code)
