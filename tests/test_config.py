"""Réglage d'une instance par l'environnement : adresse, port et options de lancement."""

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


@pytest.mark.parametrize(("valeur", "attendu"), [(None, 100), ("", 100), ("32", 32)])
def test_lire_concurrence(valeur: str | None, attendu: int) -> None:
    assert config.lire_concurrence(valeur) == attendu


@pytest.mark.parametrize("valeur", ["abc", "0", "-5", "2.5"])
def test_concurrence_illisible_refusee(valeur: str) -> None:
    with pytest.raises(ValueError, match="NOMENTRACE_CONCURRENCE"):
        config.lire_concurrence(valeur)


def test_lancement_utilise_la_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    appels: list[dict] = []
    monkeypatch.setattr(lancement.uvicorn, "run", lambda app, **options: appels.append(options))
    monkeypatch.setattr(config, "HOTE", "127.0.0.1")
    monkeypatch.setattr(config, "PORT", 8765)
    monkeypatch.setattr(config, "MODE_LOCAL", True)
    monkeypatch.setattr(config, "CONCURRENCE_MAX", 40)
    lancement.main()
    assert len(appels) == 1
    options = appels[0]
    assert (options["host"], options["port"]) == ("127.0.0.1", 8765)
    assert options["server_header"] is False
    assert options["limit_concurrency"] == 40
    # Mode local : aucun proxy attendu, les en-têtes X-Forwarded-* sont ignorés.
    assert options["proxy_headers"] is False


def test_mode_connecte_ne_croit_que_le_proxy_local() -> None:
    options = lancement.options_uvicorn("127.0.0.1", 8000, mode_local=False, concurrence=100)
    assert options["proxy_headers"] is True
    assert options["forwarded_allow_ips"] == "127.0.0.1"
