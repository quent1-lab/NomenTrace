"""Ensembles physiques et affectations des composants."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, Introuvable
from backend.services import composants, journal

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {"nom", "ordre", "description", "responsable", "statut_montage"}
)
CHAMPS_AFFECTATION: frozenset[str] = frozenset({"qte", "commentaire"})


def list_ensembles(conn: sqlite3.Connection) -> list[dict]:
    """Renvoie les ensembles non archivés avec leurs indicateurs, triés par ordre."""
    return db.fetch_all(conn, "SELECT * FROM v_ensemble ORDER BY ordre, code")


def get_ensemble(conn: sqlite3.Connection, code: str) -> dict:
    """Renvoie un ensemble non archivé avec ses indicateurs."""
    ensemble = db.fetch_one(conn, "SELECT * FROM v_ensemble WHERE code = ?", (code,))
    if ensemble is None:
        raise Introuvable(f"Ensemble « {code} » introuvable ou archivé.")
    return ensemble


def create_ensemble(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un ensemble ; le code, fourni par l'utilisateur, doit être unique."""
    code = valeurs["code"]
    with db.transaction(conn):
        if db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ?", (code,)):
            raise Conflit(f"Le code d'ensemble « {code} » est déjà utilisé.")
        db.insert_row(conn, "ensemble", valeurs)
        journal.write_journal(conn, "ensemble", code, "creation", None, "créé")
    return get_ensemble(conn, code)


def patch_ensemble(conn: sqlite3.Connection, code: str, modifications: dict[str, Any]) -> dict:
    """Modifie un ensemble ; son code n'est jamais modifiable."""
    with db.transaction(conn):
        get_ensemble(conn, code)
        journal.update_with_journal(conn, "ensemble", code, modifications, CHAMPS_MODIFIABLES)
    return get_ensemble(conn, code)


def archive_ensemble(conn: sqlite3.Connection, code: str) -> None:
    """Archive un ensemble, refusé tant qu'il porte des affectations."""
    with db.transaction(conn):
        get_ensemble(conn, code)
        nb = conn.execute(
            "SELECT COUNT(*) FROM affectation WHERE ensemble_code = ?", (code,)
        ).fetchone()[0]
        if nb:
            raise Conflit(
                f"L'ensemble « {code} » porte encore {nb} affectation(s) : retirez-les avant "
                "de l'archiver."
            )
        journal.update_with_journal(conn, "ensemble", code, {"archive": 1}, frozenset({"archive"}))


def list_composants_ensemble(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Renvoie les composants affectés à un ensemble."""
    get_ensemble(conn, code)
    return db.fetch_all(
        conn,
        "SELECT * FROM v_ensemble_composant WHERE ensemble_code = ? ORDER BY bloc_code,"
        " composant_id",
        (code,),
    )


def _cle_affectation(ensemble_code: str, composant_id: str) -> str:
    return f"{ensemble_code}:{composant_id}"


def create_affectation(conn: sqlite3.Connection, code: str, valeurs: dict[str, Any]) -> dict:
    """Affecte un composant à un ensemble ; une seule affectation par couple."""
    composant_id = valeurs["composant_id"]
    with db.transaction(conn):
        get_ensemble(conn, code)
        composants.get_composant(conn, composant_id)
        if db.fetch_one(
            conn,
            "SELECT 1 FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
            (code, composant_id),
        ):
            raise Conflit(
                f"{composant_id} est déjà affecté à l'ensemble {code} : modifiez la quantité "
                "de l'affectation existante plutôt que d'en créer une seconde."
            )
        identifiant = db.insert_row(conn, "affectation", {"ensemble_code": code, **valeurs})
        journal.write_journal(
            conn, "affectation", _cle_affectation(code, composant_id), "qte", None, valeurs["qte"]
        )
    return get_affectation(conn, identifiant)


def get_affectation(conn: sqlite3.Connection, identifiant: int) -> dict:
    """Renvoie une affectation avec ses valeurs calculées."""
    ligne = db.fetch_one(
        conn, "SELECT * FROM v_ensemble_composant WHERE affectation_id = ?", (identifiant,)
    )
    if ligne is None:
        raise Introuvable(f"Affectation {identifiant} introuvable.")
    return ligne


def patch_affectation(
    conn: sqlite3.Connection, identifiant: int, modifications: dict[str, Any]
) -> dict:
    """Modifie la quantité ou le commentaire d'une affectation."""
    with db.transaction(conn):
        actuelle = get_affectation(conn, identifiant)
        journal.update_with_journal(
            conn,
            "affectation",
            identifiant,
            modifications,
            CHAMPS_AFFECTATION,
            cle_journal=_cle_affectation(actuelle["ensemble_code"], actuelle["composant_id"]),
        )
    return get_affectation(conn, identifiant)


def delete_affectation(conn: sqlite3.Connection, identifiant: int) -> None:
    """Supprime réellement une affectation : c'est un lien, pas une donnée tracée."""
    with db.transaction(conn):
        ligne = db.fetch_one(conn, "SELECT * FROM affectation WHERE id = ?", (identifiant,))
        if ligne is None:
            raise Introuvable(f"Affectation {identifiant} introuvable.")
        conn.execute("DELETE FROM affectation WHERE id = ?", (identifiant,))
        journal.write_journal(
            conn,
            "affectation",
            _cle_affectation(ligne["ensemble_code"], ligne["composant_id"]),
            "qte",
            ligne["qte"],
            None,
        )
