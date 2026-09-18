"""Fixtures communes : chaque test travaille sur une base temporaire."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config, db
from backend.main import create_app
from backend.services import import_initial

FICHIER_SPOC: Path = config.RACINE / "SPOC_base_airtable.xlsx"


@pytest.fixture
def chemin_base(tmp_path: Path) -> Path:
    """Chemin d'une base SQLite temporaire, jamais la base réelle."""
    return tmp_path / "test.db"


@pytest.fixture
def client(chemin_base: Path) -> Iterator[TestClient]:
    """Client HTTP sur une application branchée sur une base temporaire vide."""
    with TestClient(create_app(chemin_base, fichier_import=None)) as test_client:
        yield test_client


@pytest.fixture
def conn_vide(chemin_base: Path) -> Iterator[sqlite3.Connection]:
    """Base temporaire au schéma complet, sans aucune donnée."""
    conn = db.connect(chemin_base)
    db.apply_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn_spoc(conn_vide: sqlite3.Connection) -> sqlite3.Connection:
    """Base temporaire peuplée par l'import du fichier de départ, lu en lecture seule."""
    import_initial.run_import_initial(conn_vide, FICHIER_SPOC)
    return conn_vide
