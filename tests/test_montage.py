"""Montage d'un ensemble : monter, annuler, refus sans stock, statut de montage automatique."""

from fastapi.testclient import TestClient

COMPOSANT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Vis d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 4,
}


def _preparer(client: TestClient, disponible: int = 10, affectee: int = 4) -> str:
    reponse = client.post("/api/composants", json={**COMPOSANT, "qte_disponible": disponible})
    identifiant = reponse.json()["id"]
    client.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    corps = {"composant_id": identifiant, "qte": affectee}
    assert client.post("/api/ensembles/CHASSIS/affectations", json=corps).status_code == 201
    return identifiant


def _monter(client: TestClient, identifiant: str, qte: int, action: str = "montage"):
    corps = {"composant_id": identifiant, "qte": qte}
    return client.post(f"/api/ensembles/CHASSIS/{action}", json=corps)


def _ligne(client: TestClient, identifiant: str) -> dict:
    lignes = client.get("/api/ensembles/CHASSIS/composants").json()
    return next(ligne for ligne in lignes if ligne["composant_id"] == identifiant)


def _statut(client: TestClient) -> str:
    return client.get("/api/ensembles/CHASSIS").json()["statut_montage"]


def test_monter_sort_du_stock_et_passe_en_cours(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    assert _statut(client_essai) == "Non commence"

    reponse = _monter(client_essai, identifiant, 3)

    assert reponse.status_code == 201, reponse.text
    ligne = _ligne(client_essai, identifiant)
    assert (ligne["qte_montee"], ligne["reste_a_monter"], ligne["stock_actuel"]) == (3, 1, 7)
    assert _statut(client_essai) == "En cours"
    sorties = client_essai.get(
        "/api/mouvements", params={"composant": identifiant, "type_mouvement": "Sortie montage"}
    ).json()
    assert [(m["qte"], m["ensemble_code"]) for m in sorties] == [(3, "CHASSIS")]


def test_tout_monter_passe_en_monte(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    _monter(client_essai, identifiant, 4)
    assert _statut(client_essai) == "Monte"


def test_refus_sans_stock_suffisant(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai, disponible=2)

    reponse = _monter(client_essai, identifiant, 3)

    assert reponse.status_code == 400
    assert "stock" in reponse.json()["erreur"]
    assert _ligne(client_essai, identifiant)["qte_montee"] == 0
    assert _statut(client_essai) == "Non commence"


def test_refus_au_dela_du_reste_a_monter(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    reponse = _monter(client_essai, identifiant, 5)
    assert reponse.status_code == 400
    assert "reste" in reponse.json()["erreur"]


def test_refus_composant_non_affecte(client_essai: TestClient) -> None:
    _preparer(client_essai)
    reponse = _monter(client_essai, "ESSAI-ALI-006", 1)
    assert reponse.status_code == 400
    assert "affecté" in reponse.json()["erreur"]


def test_annuler_rend_au_stock_et_redescend_le_statut(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    _monter(client_essai, identifiant, 4)

    assert _monter(client_essai, identifiant, 1, "demontage").status_code == 201
    ligne = _ligne(client_essai, identifiant)
    assert (ligne["qte_montee"], ligne["stock_actuel"]) == (3, 7)
    assert _statut(client_essai) == "En cours"

    _monter(client_essai, identifiant, 3, "demontage")
    assert _statut(client_essai) == "Non commence"
    assert _monter(client_essai, identifiant, 1, "demontage").status_code == 400


def test_valide_reste_valide_tant_que_tout_est_monte(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    _monter(client_essai, identifiant, 4)
    client_essai.patch("/api/ensembles/CHASSIS", json={"statut_montage": "Valide"})

    _monter(client_essai, identifiant, 1, "demontage")
    assert _statut(client_essai) == "En cours"
    _monter(client_essai, identifiant, 1)
    assert _statut(client_essai) == "Monte"


def test_statut_suit_aussi_les_mouvements_saisis_a_la_main(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    corps = {
        "date": "2026-11-16",
        "composant_id": identifiant,
        "type_mouvement": "Sortie montage",
        "ensemble_code": "CHASSIS",
        "qte": 2,
    }
    assert client_essai.post("/api/mouvements", json=corps).status_code == 201
    assert _statut(client_essai) == "En cours"


def test_changement_de_statut_journalise(client_essai: TestClient) -> None:
    identifiant = _preparer(client_essai)
    _monter(client_essai, identifiant, 4)
    journal = client_essai.get(
        "/api/journal", params={"table_cible": "ensemble", "cle_cible": "CHASSIS"}
    ).json()
    statuts = [j["nouvelle_valeur"] for j in journal if j["champ"] == "statut_montage"]
    assert "Monte" in statuts
