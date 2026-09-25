"""Fixtures communes : chaque test travaille sur une base temporaire."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from tests.jeu_essai import charger_jeu_essai


@pytest.fixture
def chemin_base(tmp_path: Path) -> Path:
    """Chemin d'une base SQLite temporaire, jamais la base réelle."""
    return tmp_path / "test.db"


@pytest.fixture
def dossier_echange(tmp_path: Path) -> Path:
    """Dossier d'échange temporaire : exports et sauvegardes des tests n'en sortent pas."""
    return tmp_path / "echange"


# Le client de test se présente comme un navigateur du poste local, sur une page de Nomentrace :
# c'est ce que le mode local et le contrôle d'origine des écritures exigent.
ADRESSE_LOCALE = "http://127.0.0.1:8000"


def client_local(app: FastAPI) -> TestClient:
    return TestClient(
        app,
        base_url=ADRESSE_LOCALE,
        client=("127.0.0.1", 50000),
        headers={"Origin": ADRESSE_LOCALE},
    )


@pytest.fixture
def client(chemin_base: Path, dossier_echange: Path) -> Iterator[TestClient]:
    """Client HTTP sur une application en mode local, branchée sur une base temporaire vide."""
    app = create_app(chemin_base, dossier_echange=dossier_echange, mode_local=True)
    with client_local(app) as test_client:
        yield test_client


@pytest.fixture
def conn_vide(chemin_base: Path) -> Iterator[sqlite3.Connection]:
    """Base temporaire au schéma complet, sans aucune donnée."""
    conn = db.connect(chemin_base)
    db.apply_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn_essai(conn_vide: sqlite3.Connection) -> sqlite3.Connection:
    """Base temporaire remplie par le jeu d'essai fictif."""
    charger_jeu_essai(conn_vide)
    return conn_vide


@pytest.fixture
def client_essai(
    conn_essai: sqlite3.Connection, chemin_base: Path, dossier_echange: Path
) -> Iterator[TestClient]:
    """Client HTTP sur une application en mode local, branchée sur la base du jeu d'essai."""
    conn_essai.close()
    app = create_app(chemin_base, dossier_echange=dossier_echange, mode_local=True)
    with client_local(app) as test_client:
        yield test_client
