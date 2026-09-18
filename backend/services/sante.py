"""État de santé de l'application."""

import sqlite3

from backend import db


def get_sante(conn: sqlite3.Connection) -> dict:
    """Renvoie le statut, la version du schéma et le nom du projet suivi."""
    nom_projet = None
    if db.table_existe(conn, "parametre"):
        ligne = db.fetch_one(conn, "SELECT valeur FROM parametre WHERE cle = ?", ("nom_projet",))
        nom_projet = ligne["valeur"] if ligne else None
    return {
        "statut": "ok",
        "version_schema": db.get_version_schema(conn),
        "nom_projet": nom_projet,
    }
