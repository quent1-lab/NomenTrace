"""Achats et stock : réception, mouvements, lien avec le montage des ensembles."""

from fastapi.testclient import TestClient


def _commande_deux_lignes(client: TestClient) -> tuple[str, list[int]]:
    commande = client.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()
    numero = commande["numero"]
    lignes = []
    for composant, qte, pu in (("ESSAI-TR-001", 4, 1.13), ("ESSAI-ALI-006", 1, 30.7)):
        corps = {"composant_id": composant, "qte_commandee": qte, "pu_ht_devis": pu}
        lignes.append(client.post(f"/api/commandes/{numero}/lignes", json=corps).json()["id"])
    return numero, lignes


def _stock(client: TestClient, composant: str) -> int:
    return client.get(f"/api/composants/{composant}").json()["composant"]["stock_actuel"]


def test_passage_en_commande_engage_et_marque_les_lignes(client_essai: TestClient) -> None:
    numero, _ = _commande_deux_lignes(client_essai)
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 0
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 35.22
    lignes = client_essai.get(f"/api/commandes/{numero}/lignes").json()
    assert {ligne["statut_ligne"] for ligne in lignes} == {"Commandee"}
    assert client_essai.get(f"/api/commandes/{numero}").json()["date_commande"] is not None


def test_reception_refusee_avant_commande(client_essai: TestClient) -> None:
    numero, lignes = _commande_deux_lignes(client_essai)
    corps = {"lignes": [{"id": lignes[0], "qte": 1}]}
    reponse = client_essai.post(f"/api/commandes/{numero}/reception", json=corps)
    assert reponse.status_code == 400
    assert "statut Commande" in reponse.json()["erreur"]


def test_reception_partielle_puis_complete(client_essai: TestClient) -> None:
    numero, lignes = _commande_deux_lignes(client_essai)
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    corps = {
        "date": "2026-10-02",
        "emplacement": "Armoire A",
        "lignes": [{"id": lignes[0], "qte": 3}],
    }
    resultat = client_essai.post(f"/api/commandes/{numero}/reception", json=corps).json()
    assert resultat["commande"]["statut"] == "Livre partiel"
    assert _stock(client_essai, "ESSAI-TR-001") == 3
    mouvements = client_essai.get("/api/mouvements?composant=ESSAI-TR-001").json()
    assert len(mouvements) == 1
    assert mouvements[0]["type_mouvement"] == "Reception achat"
    assert mouvements[0]["commande_numero"] == numero
    reste = {"lignes": [{"id": lignes[0], "qte": 1}, {"id": lignes[1], "qte": 1}]}
    resultat = client_essai.post(f"/api/commandes/{numero}/reception", json=reste).json()
    assert resultat["commande"]["statut"] == "Livre"
    assert resultat["commande"]["date_reception_reelle"] is not None
    assert _stock(client_essai, "ESSAI-TR-001") == 4
    assert (
        client_essai.get("/api/composants/ESSAI-TR-001").json()["composant"]["avancement"] == "Recu"
    )
    assert len(client_essai.get("/api/mouvements?type_mouvement=Reception achat").json()) == 3


def test_reception_excedentaire_signalee(client_essai: TestClient) -> None:
    numero, lignes = _commande_deux_lignes(client_essai)
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    corps = {"lignes": [{"id": lignes[1], "qte": 2}]}
    resultat = client_essai.post(f"/api/commandes/{numero}/reception", json=corps).json()
    assert len(resultat["avertissements"]) == 1
    assert _stock(client_essai, "ESSAI-ALI-006") == 2


def test_sortie_montage_alimente_le_montage(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "NACELLE", "nom": "Nacelle"})
    client_essai.post(
        "/api/ensembles/NACELLE/affectations", json={"composant_id": "ESSAI-TR-001", "qte": 3}
    )
    entree = {
        "date": "2026-10-05",
        "composant_id": "ESSAI-TR-001",
        "type_mouvement": "Pret",
        "qte": 4,
    }
    assert client_essai.post("/api/mouvements", json=entree).json()["mouvement"]["sens"] == "Entree"
    sortie = {
        "date": "2026-10-06",
        "composant_id": "ESSAI-TR-001",
        "type_mouvement": "Sortie montage",
        "qte": 2,
        "ensemble_code": "NACELLE",
    }
    resultat = client_essai.post("/api/mouvements", json=sortie).json()
    assert resultat["avertissements"] == []
    assert _stock(client_essai, "ESSAI-TR-001") == 2
    ligne = client_essai.get("/api/ensembles/NACELLE/composants").json()[0]
    assert (ligne["qte_montee"], ligne["reste_a_monter"]) == (2, 1)
    assert client_essai.get("/api/ensembles/NACELLE").json()["nb_pieces_montees"] == 2


def test_sens_impose_par_le_type(client_essai: TestClient) -> None:
    mouvement = {
        "date": "2026-10-05",
        "composant_id": "ESSAI-TR-001",
        "type_mouvement": "Perte ou casse",
        "sens": "Entree",
        "qte": 1,
    }
    reponse = client_essai.post("/api/mouvements", json=mouvement)
    assert reponse.status_code == 400
    assert "sortie" in reponse.json()["erreur"]


def test_inventaire_exige_un_sens(client_essai: TestClient) -> None:
    mouvement = {
        "date": "2026-10-05",
        "composant_id": "ESSAI-TR-001",
        "type_mouvement": "Inventaire",
        "qte": 1,
    }
    assert client_essai.post("/api/mouvements", json=mouvement).status_code == 400


def test_stock_negatif_autorise_et_signale(client_essai: TestClient) -> None:
    mouvement = {
        "date": "2026-10-05",
        "composant_id": "ESSAI-TR-002",
        "type_mouvement": "Perte ou casse",
        "qte": 1,
    }
    resultat = client_essai.post("/api/mouvements", json=mouvement).json()
    assert "négatif" in resultat["avertissements"][0]
    stock = client_essai.get("/api/stock").json()
    assert [(s["id"], s["stock_actuel"]) for s in stock] == [("ESSAI-TR-002", -1)]


def test_montage_sans_affectation_signale(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "MAT", "nom": "Mât"})
    mouvement = {
        "date": "2026-10-05",
        "composant_id": "ESSAI-BMP-001",
        "type_mouvement": "Sortie montage",
        "qte": 1,
        "ensemble_code": "MAT",
    }
    resultat = client_essai.post("/api/mouvements", json=mouvement).json()
    assert any("n'est pas affecté" in a for a in resultat["avertissements"])


def test_lignes_indiquent_les_ensembles_en_attente(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "NACELLE", "nom": "Nacelle"})
    client_essai.post(
        "/api/ensembles/NACELLE/affectations", json={"composant_id": "ESSAI-TR-001", "qte": 3}
    )
    numero, _ = _commande_deux_lignes(client_essai)
    lignes = client_essai.get(f"/api/commandes/{numero}/lignes").json()
    assert lignes[0]["ensembles"] == [{"code": "NACELLE", "qte": 3}]
    assert lignes[1]["ensembles"] == []
