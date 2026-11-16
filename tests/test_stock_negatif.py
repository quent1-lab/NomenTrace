"""Un stock ne devient jamais négatif, quel que soit le chemin d'écriture."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import db

COMPOSANT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Pièce d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 4,
}


def _creer(client: TestClient, disponible: int) -> str:
    reponse = client.post("/api/composants", json={**COMPOSANT, "qte_disponible": disponible})
    return reponse.json()["id"]


def _stock(client: TestClient, identifiant: str) -> int:
    return client.get(f"/api/composants/{identifiant}").json()["composant"]["stock_actuel"]


def _sortie(client: TestClient, identifiant: str, qte: int, **autres: object):
    corps = {"date": "2026-11-16", "composant_id": identifiant, "qte": qte, **autres}
    corps.setdefault("type_mouvement", "Perte ou casse")
    return client.post("/api/mouvements", json=corps)


@pytest.mark.parametrize(
    "type_mouvement",
    [{"type_mouvement": "Perte ou casse"}, {"type_mouvement": "Inventaire", "sens": "Sortie"}],
)
def test_sortie_au_dela_du_stock_refusee(client_essai: TestClient, type_mouvement: dict) -> None:
    identifiant = _creer(client_essai, 2)

    reponse = _sortie(client_essai, identifiant, 3, **type_mouvement)

    assert reponse.status_code == 400
    assert "stock" in reponse.json()["erreur"]
    assert _stock(client_essai, identifiant) == 2


def test_sortie_qui_vide_le_stock_acceptee(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, 2)
    assert _sortie(client_essai, identifiant, 2).status_code == 201
    assert _stock(client_essai, identifiant) == 0


def test_sortie_de_montage_sans_stock_refusee(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, 0)
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    corps = {"composant_id": identifiant, "qte": 2}
    client_essai.post("/api/ensembles/CHASSIS/affectations", json=corps)

    reponse = _sortie(
        client_essai, identifiant, 1, type_mouvement="Sortie montage", ensemble_code="CHASSIS"
    )

    assert reponse.status_code == 400
    assert _stock(client_essai, identifiant) == 0


def test_baisser_le_disponible_deja_utilise_refuse(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, 4)
    _sortie(client_essai, identifiant, 3)

    reponse = client_essai.patch(f"/api/composants/{identifiant}", json={"qte_disponible": 0})

    assert reponse.status_code == 400
    assert "stock" in reponse.json()["erreur"]
    fiche = client_essai.get(f"/api/composants/{identifiant}").json()["composant"]
    assert (fiche["qte_disponible"], fiche["stock_actuel"]) == (4, 1)
    # Une baisse que le stock couvre encore reste permise.
    assert (
        client_essai.patch(f"/api/composants/{identifiant}", json={"qte_disponible": 3}).status_code
        == 200
    )
    assert _stock(client_essai, identifiant) == 0


def test_la_base_refuse_meme_en_ecriture_directe(conn_essai: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="négatif"):
        conn_essai.execute(
            "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte)"
            " VALUES ('2026-11-16', 'ESSAI-ALI-006', 'Sortie', 'Perte ou casse', 1)"
        )


def test_stock_deja_negatif_accepte_une_entree(tmp_path: Path) -> None:
    """Une base ancienne peut porter un stock négatif : une entrée doit pouvoir le corriger."""
    from tests.jeu_essai import charger_jeu_essai

    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= 31:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(tmp_path / "base.db")
    db.apply_migrations(conn, anciennes)
    charger_jeu_essai(conn)
    conn.execute(
        "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte)"
        " VALUES ('2026-11-01', 'ESSAI-ALI-006', 'Sortie', 'Perte ou casse', 3)"
    )
    conn.commit()
    db.apply_migrations(conn)

    conn.execute(
        "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte)"
        " VALUES ('2026-11-16', 'ESSAI-ALI-006', 'Entree', 'Inventaire', 1)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte)"
            " VALUES ('2026-11-16', 'ESSAI-ALI-006', 'Sortie', 'Perte ou casse', 1)"
        )
    conn.close()
