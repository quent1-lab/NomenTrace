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
def dossier_echange(tmp_path: Path) -> Path:
    """Dossier d'échange temporaire : exports et sauvegardes des tests n'en sortent pas."""
    return tmp_path / "echange"


@pytest.fixture
def client(chemin_base: Path, dossier_echange: Path) -> Iterator[TestClient]:
    """Client HTTP sur une application branchée sur une base temporaire vide."""
    app = create_app(chemin_base, fichier_import=None, dossier_echange=dossier_echange)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_spoc(chemin_base: Path, dossier_echange: Path) -> Iterator[TestClient]:
    """Client HTTP sur une base temporaire peuplée par le fichier de départ."""
    app = create_app(chemin_base, fichier_import=FICHIER_SPOC, dossier_echange=dossier_echange)
    with TestClient(app) as test_client:
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
