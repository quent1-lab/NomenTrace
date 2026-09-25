"""Écran Ensembles : totaux, répartition par bloc, incohérences."""

from fastapi.testclient import TestClient


def _ensemble(client: TestClient, code: str) -> None:
    assert (
        client.post("/api/ensembles", json={"code": code, "nom": code.title()}).status_code == 201
    )


def _affecter(client: TestClient, code: str, composant_id: str, qte: int) -> dict:
    reponse = client.post(
        f"/api/ensembles/{code}/affectations", json={"composant_id": composant_id, "qte": qte}
    )
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def _montage(client: TestClient, composant_id: str, ensemble: str, qte: int) -> None:
    mouvement = {
        "date": "2026-10-01",
        "composant_id": composant_id,
        "sens": "Sortie",
        "type_mouvement": "Sortie montage",
        "qte": qte,
        "ensemble_code": ensemble,
    }
    assert client.post("/api/mouvements", json=mouvement).status_code == 201


def test_meme_composant_dans_deux_ensembles(client_essai: TestClient) -> None:
    _ensemble(client_essai, "NACELLE")
    _ensemble(client_essai, "MAT")
    _affecter(client_essai, "NACELLE", "ESSAI-TR-001", 3)
    _affecter(client_essai, "MAT", "ESSAI-TR-001", 1)
    composant = client_essai.get("/api/composants/ESSAI-TR-001").json()["composant"]
    assert composant["qte_affectee"] == 4
    assert composant["nb_ensembles"] == 2
    cartes = {e["code"]: e for e in client_essai.get("/api/ensembles").json()}
    assert cartes["NACELLE"]["nb_pieces_total"] == 3
    assert cartes["NACELLE"]["cout_ht"] == 3.39
    assert cartes["MAT"]["cout_ht"] == 1.13


def test_repartition_trois_poles(client_essai: TestClient) -> None:
    _ensemble(client_essai, "COFFRET")
    for composant in ("ESSAI-TR-001", "ESSAI-ALI-003", "ESSAI-ODB-005"):
        _affecter(client_essai, "COFFRET", composant, 1)
    repartition = [
        r
        for r in client_essai.get("/api/ensembles/repartition").json()
        if r["ensemble_code"] == "COFFRET"
    ]
    assert [r["bloc_code"] for r in repartition] == ["TR", "ODB", "ALI"]
    carte = client_essai.get("/api/ensembles/COFFRET").json()
    assert carte["nb_blocs_representes"] == 3
    assert carte["cout_ht"] == round(1.13 + 34 + 11.95 / 1.2, 2)


def test_appro_ignore_les_composants_hors_achat(client_essai: TestClient) -> None:
    _ensemble(client_essai, "POSTE")
    _affecter(client_essai, "POSTE", "ESSAI-IHM-001", 1)  # Fourni partenaire
    _affecter(client_essai, "POSTE", "ESSAI-IHM-005", 1)  # Achat
    carte = client_essai.get("/api/ensembles/POSTE").json()
    assert carte["nb_composants_distincts"] == 2
    assert carte["nb_composants_a_acheter"] == 1


def test_incoherences(client_essai: TestClient) -> None:
    _ensemble(client_essai, "NACELLE")
    _affecter(client_essai, "NACELLE", "ESSAI-ALI-012", 3)  # besoin 1 : sur-affecté
    _affecter(client_essai, "NACELLE", "ESSAI-ALI-002", 1)  # Fabrication atelier : jamais commandé
    _montage(client_essai, "ESSAI-ALI-002", "NACELLE", 2)  # monté 2 pour 1 affecté
    _montage(client_essai, "ESSAI-BMP-001", "NACELLE", 1)  # monté sans affectation
    incoherences = {
        (i["type"], i["composant_id"])
        for i in client_essai.get("/api/ensembles/incoherences").json()
    }
    assert incoherences == {
        ("sur_affecte", "ESSAI-ALI-012"),
        ("affecte_non_commande", "ESSAI-ALI-012"),
        ("monte_plus_qu_affecte", "ESSAI-ALI-002"),
        ("monte_sans_affectation", "ESSAI-BMP-001"),
    }


def test_composant_non_affecte_n_est_pas_une_incoherence(client_essai: TestClient) -> None:
    assert client_essai.get("/api/ensembles/incoherences").json() == []


def test_message_de_validation_traduit(client_essai: TestClient) -> None:
    _ensemble(client_essai, "MAT")
    affectation = _affecter(client_essai, "MAT", "ESSAI-TR-001", 1)
    reponse = client_essai.patch(
        f"/api/affectations/{affectation['affectation_id']}", json={"qte": 0}
    )
    assert reponse.status_code == 422
    assert reponse.json()["erreur"] == "Données invalides — qte : doit être supérieur à 0"


def test_ensemble_vide(client_essai: TestClient) -> None:
    _ensemble(client_essai, "VIDE")
    carte = client_essai.get("/api/ensembles/VIDE").json()
    assert carte["nb_composants_distincts"] == 0
    assert carte["cout_ht"] == 0
    assert carte["avancement_montage_pct"] is None
