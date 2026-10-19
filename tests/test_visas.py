"""Visa des composants : posé par un responsable, perdu à la modification suivante."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend import db
from backend.services import visas

C1, C2 = "ESSAI-ALI-001", "ESSAI-ALI-003"


def _a_voir(client: TestClient) -> list[str]:
    return [c["id"] for c in client.get("/api/composants", params={"a_voir": "true"}).json()]


def _vieillir(chemin_base: Path, identifiant: str) -> None:
    """Recule la date de modification : faite dans la même seconde, la suivante la garderait."""
    conn = db.connect(chemin_base)
    conn.execute(
        "UPDATE composant SET modifie_le = '2026-01-01T00:00:00' WHERE id = ?", (identifiant,)
    )
    conn.commit()
    conn.close()


def test_visa_pose_puis_perdu_a_la_modification(
    client_essai: TestClient, chemin_base: Path
) -> None:
    total = len(client_essai.get("/api/composants").json())
    assert client_essai.get("/api/visas/compte").json() == {"a_voir": total}
    _vieillir(chemin_base, C1)
    reponse = client_essai.post("/api/visas", json={"composants": [C1, C2]})
    assert reponse.json() == {"vises": 2}
    assert C1 not in _a_voir(client_essai)
    assert client_essai.get("/api/visas/compte").json() == {"a_voir": total - 2}
    fiche = client_essai.get(f"/api/composants/{C1}").json()
    assert fiche["visa"]["a_jour"] == 1 and fiche["visa"]["vise_par"] == "local"
    assert any(e["champ"] == "visa" for e in fiche["historique"])
    liste = {c["id"]: c["vise"] for c in client_essai.get("/api/composants").json()}
    assert liste[C1] is True
    # Déjà visé : rien à refaire.
    assert client_essai.post("/api/visas", json={"composants": [C1]}).json() == {"vises": 0}
    # Une modification du composant retire le visa.
    assert client_essai.patch(f"/api/composants/{C1}", json={"pu_releve": 9.5}).status_code == 200
    assert C1 in _a_voir(client_essai)
    assert client_essai.get(f"/api/composants/{C1}").json()["visa"]["a_jour"] == 0


def test_affectation_ne_retire_pas_le_visa(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "NACELLE", "nom": "Nacelle"})
    client_essai.post("/api/visas", json={"composants": [C2]})
    reponse = client_essai.post(
        "/api/ensembles/NACELLE/affectations", json={"composant_id": C2, "qte": 1}
    )
    assert reponse.status_code == 201, reponse.text
    assert C2 not in _a_voir(client_essai)


def test_visa_refuse(client_essai: TestClient) -> None:
    assert client_essai.post("/api/visas", json={"composants": []}).status_code == 422
    refus = client_essai.post("/api/visas", json={"composants": [C1, "ESSAI-ALI-999"]})
    assert refus.status_code == 400
    # Tout ou rien : C1 n'a pas été visé.
    assert C1 in _a_voir(client_essai)


def test_compte_sans_les_archives(client_essai: TestClient, chemin_base: Path) -> None:
    conn = db.connect(chemin_base)
    try:
        avant = visas.count_a_voir(conn)
        client_essai.delete(f"/api/composants/{C1}")
        assert visas.count_a_voir(conn) == avant - 1
    finally:
        conn.close()
    assert client_essai.post("/api/visas", json={"composants": [C1]}).status_code == 400
