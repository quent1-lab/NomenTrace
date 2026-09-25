"""Réglage d'une instance par l'environnement : adresse et port de lancement."""

import pytest

from backend import __main__ as lancement
from backend import config


@pytest.mark.parametrize(("valeur", "attendu"), [(None, 8000), ("", 8000), ("8765", 8765)])
def test_lire_port(valeur: str | None, attendu: int) -> None:
    assert config.lire_port(valeur) == attendu


@pytest.mark.parametrize("valeur", ["abc", "0", "70000", "-1", "80.5"])
def test_port_illisible_refuse(valeur: str) -> None:
    with pytest.raises(ValueError, match="NOMENTRACE_PORT"):
        config.lire_port(valeur)


def test_lancement_utilise_la_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    appels: list[dict] = []
    monkeypatch.setattr(lancement.uvicorn, "run", lambda app, **options: appels.append(options))
    monkeypatch.setattr(config, "HOTE", "127.0.0.1")
    monkeypatch.setattr(config, "PORT", 8765)
    lancement.main()
    assert appels == [{"host": "127.0.0.1", "port": 8765, "server_header": False}]
