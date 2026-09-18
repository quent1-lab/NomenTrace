"""Tests du socle : santé et format des erreurs."""

from fastapi.testclient import TestClient


def test_sante_repond_ok(client: TestClient) -> None:
    reponse = client.get("/api/sante")
    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "ok"


def test_route_inconnue_renvoie_erreur_en_francais(client: TestClient) -> None:
    reponse = client.get("/api/inexistant")
    assert reponse.status_code == 404
    assert "erreur" in reponse.json()


def test_page_servie_avec_titre(client: TestClient) -> None:
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "<title>Nomentrace</title>" in reponse.text
