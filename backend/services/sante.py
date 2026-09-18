"""État de santé de l'application."""

import sqlite3

from backend import db


def get_sante(conn: sqlite3.Connection, export_en_attente: bool = False) -> dict:
    """Renvoie le statut, la version du schéma, le nom du projet et l'état de l'export."""
    nom_projet = None
    if db.table_existe(conn, "parametre"):
        ligne = db.fetch_one(conn, "SELECT valeur FROM parametre WHERE cle = ?", ("nom_projet",))
        nom_projet = ligne["valeur"] if ligne else None
    return {
        "statut": "ok",
        "version_schema": db.get_version_schema(conn),
        "nom_projet": nom_projet,
        "export_en_attente": export_en_attente,
    }
