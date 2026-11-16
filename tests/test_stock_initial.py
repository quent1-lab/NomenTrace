"""Stock initial : la quantité déjà disponible d'un composant entre au stock.

Un seul mouvement « Stock initial » par composant, tenu par la base : créé quand la quantité
devient positive, ajusté quand elle change, retiré quand elle revient à zéro.
"""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend import db

COMPOSANT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 4,
}


def _creer(client: TestClient, **valeurs: object) -> str:
    reponse = client.post("/api/composants", json={**COMPOSANT, **valeurs})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def _initiaux(client: TestClient, identifiant: str) -> list[dict]:
    params = {"composant": identifiant, "type_mouvement": "Stock initial"}
    return client.get("/api/mouvements", params=params).json()


def _stock(client: TestClient, identifiant: str) -> int:
    return client.get(f"/api/composants/{identifiant}").json()["composant"]["stock_actuel"]


def test_quantite_disponible_entre_au_stock(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, qte_disponible=4)

    mouvements = _initiaux(client_essai, identifiant)
    assert [(m["sens"], m["qte"]) for m in mouvements] == [("Entree", 4)]
    assert _stock(client_essai, identifiant) == 4
    stock = {ligne["id"]: ligne for ligne in client_essai.get("/api/stock").json()}
    assert stock[identifiant]["stock_actuel"] == 4
    # Le calcul de l'achat ne change pas : rien à acheter.
    fiche = client_essai.get(f"/api/composants/{identifiant}").json()["composant"]
    assert fiche["qte_a_acheter"] == 0


def test_sans_quantite_disponible_aucun_mouvement(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai)
    assert _initiaux(client_essai, identifiant) == []


def test_modifier_la_quantite_ajuste_le_meme_mouvement(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, qte_disponible=4)
    premier = _initiaux(client_essai, identifiant)[0]["id"]

    client_essai.patch(f"/api/composants/{identifiant}", json={"qte_disponible": 6})
    mouvements = _initiaux(client_essai, identifiant)
    assert [(m["id"], m["qte"]) for m in mouvements] == [(premier, 6)]
    assert _stock(client_essai, identifiant) == 6

    client_essai.patch(f"/api/composants/{identifiant}", json={"qte_disponible": 0})
    assert _initiaux(client_essai, identifiant) == []
    assert _stock(client_essai, identifiant) == 0

    client_essai.patch(f"/api/composants/{identifiant}", json={"qte_disponible": 2})
    assert [m["qte"] for m in _initiaux(client_essai, identifiant)] == [2]


def test_stock_initial_permet_le_montage(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, qte_disponible=4)
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    corps = {"composant_id": identifiant, "qte": 4}
    client_essai.post("/api/ensembles/CHASSIS/affectations", json=corps)

    sortie = {
        "date": "2026-11-16",
        "composant_id": identifiant,
        "type_mouvement": "Sortie montage",
        "ensemble_code": "CHASSIS",
        "qte": 4,
    }
    reponse = client_essai.post("/api/mouvements", json=sortie)
    assert reponse.status_code == 201
    assert reponse.json()["avertissements"] == []
    assert _stock(client_essai, identifiant) == 0


def test_stock_initial_refuse_en_saisie_manuelle(client_essai: TestClient) -> None:
    corps = {
        "date": "2026-11-16",
        "composant_id": "ESSAI-ALI-006",
        "type_mouvement": "Stock initial",
        "qte": 3,
    }
    reponse = client_essai.post("/api/mouvements", json=corps)
    assert reponse.status_code == 400
    assert "déjà disponible" in reponse.json()["erreur"]


def test_stock_initial_n_empeche_pas_la_suppression(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, qte_disponible=4)
    corps = {"cles": [identifiant], "action": "supprimer", "simuler": False}
    recap = client_essai.post("/api/nettoyage/composants", json=corps).json()
    assert recap["supprimes"] == [identifiant]
    assert client_essai.get("/api/mouvements", params={"composant": identifiant}).json() == []


def test_migration_reprend_les_quantites_existantes(tmp_path: Path) -> None:
    from tests.jeu_essai import charger_jeu_essai

    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= 30:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(tmp_path / "base.db")
    db.apply_migrations(conn, anciennes)
    charger_jeu_essai(conn)
    conn.execute("UPDATE composant SET qte_disponible = 5 WHERE id = 'ESSAI-ALI-006'")
    conn.commit()

    db.apply_migrations(conn)

    lignes = conn.execute(
        "SELECT composant_id, sens, qte FROM mouvement_stock WHERE type_mouvement = 'Stock initial'"
    ).fetchall()
    assert [tuple(ligne) for ligne in lignes] == [("ESSAI-ALI-006", "Entree", 5)]
    systeme = db.fetch_one(
        conn,
        "SELECT systeme, sens FROM valeur_liste WHERE liste = 'type_mouvement'"
        " AND code = 'Stock initial'",
    )
    assert systeme == {"systeme": 1, "sens": "Entree"}
    conn.close()


def test_migration_dans_un_projet_aux_listes_imposees(tmp_path: Path) -> None:
    """Un projet rangé dans un dossier refuse d'écrire ses listes imposées : la migration
    ajoute pourtant le type système « Stock initial » (constaté en mise à jour, v1.19)."""
    from tests.jeu_essai import charger_jeu_essai

    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= 30:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(tmp_path / "base.db")
    db.apply_migrations(conn, anciennes)
    charger_jeu_essai(conn)
    conn.execute("UPDATE composant SET qte_disponible = 2 WHERE id = 'ESSAI-ALI-006'")
    conn.execute("UPDATE reglages_imposes SET actif = 1, dossier = 'D1' WHERE id = 1")
    conn.commit()

    db.apply_migrations(conn)

    assert db.get_version_schema(conn) >= 31
    ligne = db.fetch_one(
        conn,
        "SELECT systeme, sens FROM valeur_liste WHERE liste = 'type_mouvement'"
        " AND code = 'Stock initial'",
    )
    assert ligne == {"systeme": 1, "sens": "Entree"}
    verrou = db.fetch_one(conn, "SELECT actif, propagation FROM reglages_imposes")
    assert verrou == {"actif": 1, "propagation": 0}
    conn.close()


def test_un_seul_mouvement_initial_par_composant(conn_essai: sqlite3.Connection) -> None:
    """Même écrit directement en base (import, reclassement), le mouvement reste unique."""
    conn_essai.execute("UPDATE composant SET qte_disponible = 3 WHERE id = 'ESSAI-ALI-006'")
    conn_essai.execute("UPDATE composant SET qte_disponible = 7 WHERE id = 'ESSAI-ALI-006'")
    lignes = conn_essai.execute(
        "SELECT qte FROM mouvement_stock WHERE composant_id = 'ESSAI-ALI-006'"
        " AND type_mouvement = 'Stock initial'"
    ).fetchall()
    assert [ligne[0] for ligne in lignes] == [7]
