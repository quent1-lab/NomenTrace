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


def test_meme_composant_dans_deux_ensembles(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "NACELLE")
    _ensemble(client_spoc, "MAT")
    _affecter(client_spoc, "NACELLE", "SPOC-TR-001", 3)
    _affecter(client_spoc, "MAT", "SPOC-TR-001", 1)
    composant = client_spoc.get("/api/composants/SPOC-TR-001").json()["composant"]
    assert composant["qte_affectee"] == 4
    assert composant["nb_ensembles"] == 2
    cartes = {e["code"]: e for e in client_spoc.get("/api/ensembles").json()}
    assert cartes["NACELLE"]["nb_pieces_total"] == 3
    assert cartes["NACELLE"]["cout_ht"] == 3.39
    assert cartes["MAT"]["cout_ht"] == 1.13


def test_repartition_trois_poles(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "COFFRET")
    for composant in ("SPOC-TR-001", "SPOC-ALI-003", "SPOC-ODB-005"):
        _affecter(client_spoc, "COFFRET", composant, 1)
    repartition = [
        r
        for r in client_spoc.get("/api/ensembles/repartition").json()
        if r["ensemble_code"] == "COFFRET"
    ]
    assert [r["bloc_code"] for r in repartition] == ["TR", "ODB", "ALI"]
    carte = client_spoc.get("/api/ensembles/COFFRET").json()
    assert carte["nb_blocs_representes"] == 3
    assert carte["cout_ht"] == round(1.13 + 34 + 11.95 / 1.2, 2)


def test_appro_ignore_les_composants_hors_achat(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "POSTE")
    _affecter(client_spoc, "POSTE", "SPOC-IHM-001", 1)  # Fourni CEA
    _affecter(client_spoc, "POSTE", "SPOC-IHM-005", 1)  # Achat
    carte = client_spoc.get("/api/ensembles/POSTE").json()
    assert carte["nb_composants_distincts"] == 2
    assert carte["nb_composants_a_acheter"] == 1


def test_incoherences(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "NACELLE")
    _affecter(client_spoc, "NACELLE", "SPOC-ALI-012", 3)  # besoin 1 : sur-affecté
    _affecter(client_spoc, "NACELLE", "SPOC-ALI-002", 1)  # Fabrication PFM : jamais commandé
    _montage(client_spoc, "SPOC-ALI-002", "NACELLE", 2)  # monté 2 pour 1 affecté
    _montage(client_spoc, "SPOC-BMP-001", "NACELLE", 1)  # monté sans affectation
    incoherences = {
        (i["type"], i["composant_id"])
        for i in client_spoc.get("/api/ensembles/incoherences").json()
    }
    assert incoherences == {
        ("sur_affecte", "SPOC-ALI-012"),
        ("affecte_non_commande", "SPOC-ALI-012"),
        ("monte_plus_qu_affecte", "SPOC-ALI-002"),
        ("monte_sans_affectation", "SPOC-BMP-001"),
    }


def test_composant_non_affecte_n_est_pas_une_incoherence(client_spoc: TestClient) -> None:
    assert client_spoc.get("/api/ensembles/incoherences").json() == []


def test_message_de_validation_traduit(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "MAT")
    affectation = _affecter(client_spoc, "MAT", "SPOC-TR-001", 1)
    reponse = client_spoc.patch(
        f"/api/affectations/{affectation['affectation_id']}", json={"qte": 0}
    )
    assert reponse.status_code == 422
    assert reponse.json()["erreur"] == "Données invalides — qte : doit être supérieur à 0"


def test_ensemble_vide(client_spoc: TestClient) -> None:
    _ensemble(client_spoc, "VIDE")
    carte = client_spoc.get("/api/ensembles/VIDE").json()
    assert carte["nb_composants_distincts"] == 0
    assert carte["cout_ht"] == 0
    assert carte["avancement_montage_pct"] is None
