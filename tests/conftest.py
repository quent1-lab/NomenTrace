"""Fixtures communes : chaque test travaille sur une base temporaire."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config, db
from backend.main import create_app
from tests.jeu_essai import charger_jeu_essai


@pytest.fixture
def code_projet() -> str:
    """Code du projet de l'instance de test (celui de l'application sans réglage)."""
    return config.CODE_PROJET


@pytest.fixture
def dossier_data(tmp_path: Path) -> Path:
    """Dossier des données temporaire : base commune et bases des projets."""
    return tmp_path / "data"


@pytest.fixture
def chemin_base(dossier_data: Path, code_projet: str) -> Path:
    """Base temporaire du projet de l'instance, jamais la base réelle."""
    return dossier_data / "projets" / code_projet / "nomentrace.db"


@pytest.fixture
def dossier_echange(tmp_path: Path) -> Path:
    """Dossier d'échange temporaire : exports et sauvegardes des tests n'en sortent pas."""
    return tmp_path / "echange"


@pytest.fixture
def echange_projet(dossier_echange: Path, code_projet: str) -> Path:
    """Dossier d'échange du projet de l'instance : documents, exports, sauvegardes."""
    return dossier_echange / "projets" / code_projet


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
def client(dossier_data: Path, dossier_echange: Path) -> Iterator[TestClient]:
    """Client HTTP sur une application en mode local, branchée sur une base temporaire vide."""
    app = create_app(dossier_data, dossier_echange=dossier_echange, mode_local=True)
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
    conn_essai: sqlite3.Connection, dossier_data: Path, dossier_echange: Path
) -> Iterator[TestClient]:
    """Client HTTP sur une application en mode local, branchée sur la base du jeu d'essai."""
    conn_essai.close()
    app = create_app(dossier_data, dossier_echange=dossier_echange, mode_local=True)
    with client_local(app) as test_client:
        yield test_client
