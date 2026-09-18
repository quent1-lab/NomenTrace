"""Connexion SQLite, migrations et helpers de requête."""

import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend import config

journal_log = logging.getLogger(__name__)

_MOTIF_MIGRATION = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def connect(chemin: Path | None = None) -> sqlite3.Connection:
    """Ouvre une connexion en mode autocommit, clés étrangères actives et journal WAL.

    Les transactions sont ouvertes explicitement avec `transaction()`.
    """
    cible = chemin or config.CHEMIN_BASE
    cible.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cible, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = False) -> Iterator[None]:
    """Exécute le bloc dans une transaction, annulée en cas d'exception."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    """Renvoie toutes les lignes sous forme de dictionnaires."""
    return [dict(ligne) for ligne in conn.execute(sql, params).fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict | None:
    """Renvoie la première ligne sous forme de dictionnaire, ou None."""
    ligne = conn.execute(sql, params).fetchone()
    return dict(ligne) if ligne is not None else None


def insert_row(conn: sqlite3.Connection, table: str, valeurs: dict[str, Any]) -> int:
    """Insère une ligne et renvoie son rowid.

    Les noms de table et de colonnes viennent toujours du code (modèles Pydantic à champs
    fermés), jamais d'une saisie : seules les valeurs sont des paramètres liés.
    """
    colonnes = ", ".join(valeurs)
    marques = ", ".join("?" for _ in valeurs)
    curseur = conn.execute(
        f"INSERT INTO {table} ({colonnes}) VALUES ({marques})",  # noqa: S608
        tuple(valeurs.values()),
    )
    return int(curseur.lastrowid or 0)


def table_existe(conn: sqlite3.Connection, nom: str) -> bool:
    """Indique si une table existe dans la base."""
    ligne = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nom,)
    ).fetchone()
    return ligne is not None


def get_version_schema(conn: sqlite3.Connection) -> int:
    """Renvoie le numéro de la dernière migration appliquée, 0 si aucune."""
    if not table_existe(conn, "schema_version"):
        return 0
    ligne = conn.execute("SELECT MAX(numero) FROM schema_version").fetchone()
    return int(ligne[0]) if ligne[0] is not None else 0


def list_migrations(dossier: Path | None = None) -> list[tuple[int, Path]]:
    """Liste les fichiers de migration triés par numéro."""
    source = dossier or config.DOSSIER_MIGRATIONS
    migrations = []
    for fichier in source.glob("*.sql"):
        correspondance = _MOTIF_MIGRATION.match(fichier.name)
        if correspondance is None:
            journal_log.warning("Fichier de migration ignoré (nom non conforme) : %s", fichier)
            continue
        migrations.append((int(correspondance.group(1)), fichier))
    return sorted(migrations)


def apply_migrations(conn: sqlite3.Connection, dossier: Path | None = None) -> int:
    """Applique dans l'ordre les migrations non encore appliquées.

    Chaque migration et l'enregistrement de son numéro forment une seule transaction.
    Renvoie la version du schéma après application.
    """
    version = get_version_schema(conn)
    for numero, fichier in list_migrations(dossier):
        if numero <= version:
            continue
        script = fichier.read_text(encoding="utf-8")
        conn.executescript("BEGIN;\n" + script)
        try:
            conn.execute("INSERT INTO schema_version (numero) VALUES (?)", (numero,))
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        journal_log.info("Migration %03d appliquée : %s", numero, fichier.name)
        version = numero
    return version
