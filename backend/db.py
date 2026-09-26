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


class Connexion(sqlite3.Connection):
    """Connexion SQLite qui connaît l'auteur des écritures, reporté dans le journal."""

    utilisateur: str | None = None


def connect(chemin: Path | None = None, utilisateur: str | None = None) -> Connexion:
    """Ouvre une connexion en mode autocommit, clés étrangères actives et journal WAL.

    Les transactions sont ouvertes explicitement avec `transaction()`. Une écriture
    concurrente attend jusqu'à 5 s que la base se libère avant d'échouer.
    """
    cible = chemin or config.CHEMIN_BASE
    cible.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cible, isolation_level=None, check_same_thread=False, factory=Connexion)
    conn.row_factory = sqlite3.Row
    conn.utilisateur = utilisateur
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def auteur(conn: sqlite3.Connection) -> str | None:
    """Nom de l'utilisateur à l'origine des écritures de cette connexion, s'il est connu."""
    return getattr(conn, "utilisateur", None)


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = True) -> Iterator[None]:
    """Exécute le bloc dans une transaction, annulée en cas d'exception.

    Par défaut la transaction prend le verrou d'écriture dès son ouverture (BEGIN IMMEDIATE) :
    deux écritures simultanées s'attendent au lieu d'échouer au moment d'écrire.
    """
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


class SchemaTropRecent(RuntimeError):
    """La base a reçu des migrations que ce code ne connaît pas."""


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


# Première ligne d'une migration qui reconstruit des tables : les clés étrangères sont
# suspendues le temps de la migration (le PRAGMA est sans effet dans une transaction),
# puis vérifiées avant validation.
MARQUEUR_RECONSTRUCTION = "-- nomentrace: reconstruction"


def _apply_migration(conn: sqlite3.Connection, numero: int, script: str) -> None:
    """Exécute une migration et enregistre son numéro dans une seule transaction."""
    try:
        conn.executescript("BEGIN;\n" + script)
        conn.execute("INSERT INTO schema_version (numero) VALUES (?)", (numero,))
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(
                f"Clés étrangères invalides après migration : {violations}"
            )
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def apply_migrations(conn: sqlite3.Connection, dossier: Path | None = None) -> int:
    """Applique dans l'ordre les migrations non encore appliquées.

    Chaque migration et l'enregistrement de son numéro forment une seule transaction.
    Renvoie la version du schéma après application. Refuse une base dont le schéma est
    plus récent que ce code : une version antérieure de l'outil la lirait de travers.
    """
    version = get_version_schema(conn)
    migrations = list_migrations(dossier)
    derniere = max((numero for numero, _ in migrations), default=0)
    if version > derniere:
        raise SchemaTropRecent(
            f"La base est au schéma {version}, plus récent que cette version de Nomentrace"
            f" (schéma {derniere}) : installer une version plus récente, ou restaurer une"
            " sauvegarde antérieure à la mise à jour."
        )
    for numero, fichier in migrations:
        if numero <= version:
            continue
        script = fichier.read_text(encoding="utf-8")
        reconstruction = script.startswith(MARQUEUR_RECONSTRUCTION)
        if reconstruction:
            conn.execute("PRAGMA foreign_keys = OFF")
        try:
            _apply_migration(conn, numero, script)
        finally:
            if reconstruction:
                conn.execute("PRAGMA foreign_keys = ON")
        journal_log.info("Migration %03d appliquée : %s", numero, fichier.name)
        version = numero
    return version
