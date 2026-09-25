"""Blocs fonctionnels."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import journal

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {"nom", "ordre", "budget_cible_ht", "responsable", "description", "archive"}
)


def list_blocs(conn: sqlite3.Connection, inclure_archives: bool = False) -> list[dict]:
    """Renvoie les blocs avec leurs indicateurs, triés par ordre ; archivés sur demande."""
    return db.fetch_all(
        conn,
        "SELECT * FROM v_bloc WHERE ? OR archive = 0 ORDER BY archive, ordre, code",
        (int(inclure_archives),),
    )


def get_bloc(conn: sqlite3.Connection, code: str) -> dict:
    """Renvoie un bloc avec ses indicateurs."""
    bloc = db.fetch_one(conn, "SELECT * FROM v_bloc WHERE code = ?", (code,))
    if bloc is None:
        raise Introuvable(f"Bloc « {code} » introuvable.")
    return bloc


def check_codes(conn: sqlite3.Connection, codes: list[str]) -> None:
    """Refuse un code de bloc inconnu (les blocs archivés restent acceptés)."""
    connus = {ligne["code"] for ligne in db.fetch_all(conn, "SELECT code FROM bloc")}
    inconnus = sorted(set(codes) - connus)
    if inconnus:
        raise ErreurMetier(f"Bloc inconnu : {', '.join(inconnus)}.")


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
    """Modifie un bloc ; son code, figé dans les identifiants, n'est jamais modifiable.

    Un bloc qui porte encore des composants actifs ne peut pas être archivé.
    """
    with db.transaction(conn):
        if modifications.get("archive") == 1:
            nombre = conn.execute(
                "SELECT COUNT(*) FROM composant WHERE bloc_code = ? AND archive = 0", (code,)
            ).fetchone()[0]
            if nombre:
                raise ErreurMetier(
                    f"Le bloc « {code} » porte encore {nombre} composant(s) actif(s) : "
                    "archivez-les ou reclassez-les d'abord."
                )
        journal.update_with_journal(conn, "bloc", code, modifications, CHAMPS_MODIFIABLES)
    return get_bloc(conn, code)
