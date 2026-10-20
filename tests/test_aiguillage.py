"""Projet dans l'adresse (phase 15a-1) : /p/<code>/… porte le projet de la requête.

Le préfixe est retiré avant toute autre couche : contrôle d'origine, droits et export voient
les adresses habituelles en /api/. Un code inconnu ou mal formé n'ouvre aucune base.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _prefixe(client: TestClient) -> str:
    return f"/p/{client.app.state.code_projet}"


def _fichiers(racine: Path) -> set[Path]:
    return {chemin for chemin in racine.rglob("*")}


def test_api_prefixee_repond_comme_sans_prefixe(client: TestClient) -> None:
    sans = client.get("/api/sante")
    avec = client.get(f"{_prefixe(client)}/api/sante")
    assert avec.status_code == 200
    assert avec.json() == sans.json()


def test_ecriture_prefixee_sans_origine_refusee(client: TestClient) -> None:
    reponse = client.post(
        f"{_prefixe(client)}/api/blocs",
        json={"code": "MEC", "nom": "Mécanique"},
        headers={"Origin": ""},
    )
    assert reponse.status_code == 403
    assert client.get("/api/blocs").json() == []


def test_ecriture_prefixee_admise_et_exportee(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signaux: list[bool] = []
    monkeypatch.setattr(
        client.app.state.exports[client.app.state.code_projet],
        "signaler",
        lambda: signaux.append(True),
    )
    reponse = client.post(f"{_prefixe(client)}/api/blocs", json={"code": "MEC", "nom": "Méca"})
    assert reponse.status_code == 201, reponse.text
    assert [b["code"] for b in client.get(f"{_prefixe(client)}/api/blocs").json()] == ["MEC"]
    assert signaux == [True]


@pytest.mark.parametrize(
    "adresse",
    [
        "/p/inconnu/api/sante",
        "/p/inconnu/",
        "/p/Majuscule/api/sante",
        "/p/..%2Fdata/api/sante",
        "/p/-tiret/api/sante",
        "/p//api/sante",
        "/p",
    ],
)
def test_code_inconnu_ou_mal_forme_404_sans_fichier(
    client: TestClient, tmp_path: Path, adresse: str
) -> None:
    avant = _fichiers(tmp_path)
    reponse = client.get(adresse, follow_redirects=False)
    assert reponse.status_code == 404
    assert "erreur" in reponse.json()
    assert _fichiers(tmp_path) == avant


def test_racine_redirige_vers_le_projet(client: TestClient) -> None:
    for adresse in ("/", "/index.html"):
        reponse = client.get(adresse, follow_redirects=False)
        assert reponse.status_code == 302
        assert reponse.headers["location"] == f"{_prefixe(client)}/"


def test_projet_sans_barre_finale_redirige(client: TestClient) -> None:
    reponse = client.get(_prefixe(client), follow_redirects=False)
    assert reponse.status_code == 302
    assert reponse.headers["location"] == f"{_prefixe(client)}/"


def test_interface_servie_sous_le_projet(client: TestClient) -> None:
    reponse = client.get(f"{_prefixe(client)}/")
    assert reponse.status_code == 200
    assert "<title>Nomentrace" in reponse.text
    assert client.get(f"{_prefixe(client)}/connexion.html").status_code == 200
    assert client.get("/connexion.html").status_code == 200
    assert client.get("/js/api.js").status_code == 200
