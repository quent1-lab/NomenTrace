"""Fixtures communes : chaque test travaille sur une base temporaire."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def chemin_base(tmp_path: Path) -> Path:
    """Chemin d'une base SQLite temporaire, jamais la base réelle."""
    return tmp_path / "test.db"


@pytest.fixture
def client(chemin_base: Path) -> Iterator[TestClient]:
    """Client HTTP sur une application branchée sur la base temporaire."""
    with TestClient(create_app(chemin_base)) as test_client:
        yield test_client
