"""Champs obligatoires des composants, réglés dans les paramètres."""

from fastapi.testclient import TestClient

ACHAT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 1,
}
LIEN = "https://exemple.test/produit"


def _exiger_lien(client: TestClient, portee: str = "achat") -> None:
    reponse = client.patch(
        "/api/parametres",
        json={"champs_obligatoires": ["lien_produit"], "champs_obligatoires_portee": portee},
    )
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["champs_obligatoires"] == "lien_produit"


def test_creation_refusee_sans_champ_obligatoire(client_essai: TestClient) -> None:
    _exiger_lien(client_essai)
    refus = client_essai.post("/api/composants", json=ACHAT)
    assert refus.status_code == 400
    assert "Lien produit" in refus.json()["erreur"]
    assert (
        client_essai.post("/api/composants", json={**ACHAT, "lien_produit": LIEN}).status_code
        == 201
    )
    # Hors mode Achat, la règle ne s'applique pas, sauf portée « tous ».
    atelier = {**ACHAT, "mode_appro": "Fabrication atelier"}
    assert client_essai.post("/api/composants", json=atelier).status_code == 201
    _exiger_lien(client_essai, "tous")
    assert client_essai.post("/api/composants", json=atelier).status_code == 400


def test_existant_incomplet_reste_modifiable(client_essai: TestClient) -> None:
    cree = client_essai.post("/api/composants", json=ACHAT).json()["id"]
    _exiger_lien(client_essai)
    # Un autre champ se modifie ; vider ou laisser vide le champ obligatoire, non.
    assert client_essai.patch(f"/api/composants/{cree}", json={"fabricant": "X"}).status_code == 200
    assert (
        client_essai.patch(f"/api/composants/{cree}", json={"lien_produit": None}).status_code
        == 400
    )
    assert (
        client_essai.patch(f"/api/composants/{cree}", json={"lien_produit": LIEN}).status_code
        == 200
    )
    assert (
        client_essai.patch(f"/api/composants/{cree}", json={"lien_produit": None}).status_code
        == 400
    )


def test_passage_en_achat_exige_les_champs(client_essai: TestClient) -> None:
    atelier = client_essai.post(
        "/api/composants", json={**ACHAT, "mode_appro": "Fabrication atelier"}
    ).json()["id"]
    _exiger_lien(client_essai)
    passage = client_essai.patch(f"/api/composants/{atelier}", json={"mode_appro": "Achat"})
    assert passage.status_code == 400
    complet = {"mode_appro": "Achat", "lien_produit": LIEN}
    assert client_essai.patch(f"/api/composants/{atelier}", json=complet).status_code == 200


def test_attribut_obligatoire(client_essai: TestClient) -> None:
    code = client_essai.post(
        "/api/attributs", json={"libelle": "Tension", "type": "nombre"}
    ).json()["code"]
    assert client_essai.patch(f"/api/attributs/{code}", json={"obligatoire": 1}).status_code == 200
    refus = client_essai.post("/api/composants", json=ACHAT)
    assert refus.status_code == 400 and "Tension" in refus.json()["erreur"]
    cree = client_essai.post("/api/composants", json={**ACHAT, "attributs": {code: 24}})
    assert cree.status_code == 201, cree.text
    identifiant = cree.json()["id"]
    effacer = client_essai.put(
        f"/api/composants/{identifiant}/attributs", json={"valeurs": {code: None}}
    )
    assert effacer.status_code == 400


def test_nettoyage_signale_les_champs_manquants(client_essai: TestClient) -> None:
    cree = client_essai.post("/api/composants", json=ACHAT).json()["id"]
    _exiger_lien(client_essai)
    controles = client_essai.get("/api/nettoyage/composants").json()
    ligne = next(c for c in controles["composants"] if c["id"] == cree)
    assert "obligatoire_manquant" in ligne["controles"]
    assert ligne["manquants"] == ["Lien produit"]
