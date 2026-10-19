"""Actions à faire sur un composant, données par sa fiche (pastille « N actions »)."""

from fastapi.testclient import TestClient

ACHAT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 3,
}


def _creer(client: TestClient, **valeurs: object) -> str:
    reponse = client.post("/api/composants", json={**ACHAT, **valeurs})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def _codes(client: TestClient, identifiant: str) -> list[str]:
    return [a["code"] for a in client.get(f"/api/composants/{identifiant}").json()["actions"]]


def test_achat_sans_prix_ni_fiche_technique(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai)
    actions = client_essai.get(f"/api/composants/{identifiant}").json()["actions"]
    assert [a["code"] for a in actions] == ["a_chiffrer", "fiche_technique"]
    assert actions[1]["onglet"] == "documents"
    depot = client_essai.post(
        f"/api/composants/{identifiant}/documents",
        files=[("fichiers", ("fiche.pdf", b"%PDF-1.4 essai"))],
        data={"type_document": "Fiche technique"},
    )
    assert depot.status_code in (200, 201), depot.text
    assert "fiche_technique" not in _codes(client_essai, identifiant)


def test_hors_achat_sans_action(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, mode_appro="Fabrication atelier")
    assert _codes(client_essai, identifiant) == []


def test_champ_obligatoire_manquant(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, pu_releve=10)
    client_essai.patch("/api/parametres", json={"champs_obligatoires": ["lien_produit"]})
    actions = client_essai.get(f"/api/composants/{identifiant}").json()["actions"]
    assert actions[0]["code"] == "obligatoire"
    assert "Lien produit" in actions[0]["texte"]


def test_aucune_affectation_n_est_pas_une_action(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, pu_releve=10)
    assert "affectation" not in _codes(client_essai, identifiant)
    client_essai.post("/api/ensembles", json={"code": "NACELLE", "nom": "Nacelle"})
    client_essai.post(
        "/api/ensembles/NACELLE/affectations", json={"composant_id": identifiant, "qte": 1}
    )
    actions = client_essai.get(f"/api/composants/{identifiant}").json()["actions"]
    affectation = next(a for a in actions if a["code"] == "affectation")
    assert affectation["texte"].startswith("2 pièce(s)")
    assert affectation["onglet"] == "ensembles"
