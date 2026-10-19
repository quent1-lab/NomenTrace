"""Coût matière et reste à dépenser d'un ensemble : le stock interne n'est pas une dépense.

Exemple de référence : moteur à 20 € HT, besoin 10, 4 déjà disponibles, donc 6 à acheter
(120 €). Affecté 6 à l'ensemble A et 4 à l'ensemble B : coût matière 120 € et 80 €, à
dépenser au prorata 72 € et 48 €, soit les 120 € du projet.
"""

import pytest
from fastapi.testclient import TestClient

from tests.test_arborescence import _affecter, _arbre, _ensemble

TOLERANCE = 0.01
MOTEUR = {
    "bloc_code": "ALI",
    "fonction": "Motorisation",
    "designation": "Moteur d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 10,
    "qte_disponible": 4,
    "pu_releve": 20,
    "base_prix_releve": "HT",
}


def _creer(client: TestClient, **valeurs: object) -> str:
    reponse = client.post("/api/composants", json={**MOTEUR, **valeurs})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def _deux_ensembles(client: TestClient, composant: str) -> dict[str, dict]:
    _ensemble(client, "AAA")
    _ensemble(client, "BBB")
    _affecter(client, "AAA", composant, 6)
    _affecter(client, "BBB", composant, 4)
    return _arbre(client)[1]


def test_prorata_du_stock(client_essai: TestClient) -> None:
    moteur = _creer(client_essai)
    ensembles = _deux_ensembles(client_essai, moteur)
    a, b = ensembles["AAA"], ensembles["BBB"]
    assert a["cout_ht"] == pytest.approx(120, abs=TOLERANCE)
    assert b["cout_ht"] == pytest.approx(80, abs=TOLERANCE)
    assert a["depense_ht"] == pytest.approx(72, abs=TOLERANCE)
    assert b["depense_ht"] == pytest.approx(48, abs=TOLERANCE)
    composant = client_essai.get(f"/api/composants/{moteur}").json()["composant"]
    assert a["depense_ht"] + b["depense_ht"] == pytest.approx(composant["total_ht"], abs=TOLERANCE)
    lignes = client_essai.get("/api/ensembles/AAA/composants").json()
    assert lignes[0]["depense_ligne_ht"] == pytest.approx(72, abs=TOLERANCE)


def test_rechange_reste_au_projet(client_essai: TestClient) -> None:
    """Le stock couvre d'abord le besoin ; les 2 pièces de rechange ne vont à aucun ensemble."""
    moteur = _creer(client_essai, qte_rechange=2)
    ensembles = _deux_ensembles(client_essai, moteur)
    assert ensembles["AAA"]["depense_ht"] == pytest.approx(72, abs=TOLERANCE)
    composant = client_essai.get(f"/api/composants/{moteur}").json()["composant"]
    assert composant["total_ht"] == pytest.approx(160, abs=TOLERANCE)


@pytest.mark.parametrize(
    ("valeurs", "attendu"),
    [
        ({"mode_appro": "Fabrication atelier"}, 0),
        ({"qte_disponible": 12}, 0),
        ({"qte_disponible": 0}, 120),
        ({"qte_besoin": 0, "qte_disponible": 0}, 120),
        ({"qte_besoin": 0, "qte_disponible": 3}, 0),
    ],
)
def test_cas_limites(client_essai: TestClient, valeurs: dict, attendu: float) -> None:
    moteur = _creer(client_essai, **valeurs)
    ensembles = _deux_ensembles(client_essai, moteur)
    assert ensembles["AAA"]["cout_ht"] == pytest.approx(120, abs=TOLERANCE)
    assert ensembles["AAA"]["depense_ht"] == pytest.approx(attendu, abs=TOLERANCE)


def test_sans_prix_la_depense_reste_inconnue(client_essai: TestClient) -> None:
    moteur = _creer(client_essai, pu_releve=None)
    ensembles = _deux_ensembles(client_essai, moteur)
    assert ensembles["AAA"]["depense_ht"] == 0
    assert ensembles["AAA"]["nb_lignes_non_chiffrees"] == 1


def test_cumul_racine_et_ecarts(client_essai: TestClient) -> None:
    client_essai.patch("/api/parametres", json={"budget_ht": 1000})
    moteur = _creer(client_essai)
    _ensemble(client_essai, "ROBOT")
    _ensemble(client_essai, "AAA", "ROBOT", budget_cible_ht=100, budget_verrouille=True)
    _affecter(client_essai, "AAA", moteur, 6)
    _affecter(client_essai, "ROBOT", moteur, 4)
    racine, ensembles = _arbre(client_essai)
    robot, a = ensembles["ROBOT"], ensembles["AAA"]
    assert robot["cumul"]["depense_ht"] == pytest.approx(120, abs=TOLERANCE)
    assert robot["depense_ht"] == pytest.approx(48, abs=TOLERANCE)
    assert racine["depense_ht"] == pytest.approx(120, abs=TOLERANCE)
    assert racine["cout_ht"] == pytest.approx(200, abs=TOLERANCE)
    assert racine["ecart_depense_ht"] == pytest.approx(-880, abs=TOLERANCE)
    # Budget verrouillé de 100 € : coût matière 120 € (dépassement), dépense 72 € (marge).
    assert a["ecart_budget_ht"] == pytest.approx(20, abs=TOLERANCE)
    assert a["ecart_depense_ht"] == pytest.approx(-28, abs=TOLERANCE)
    repartition = client_essai.get("/api/ensembles/repartition", params={"cumul": "true"}).json()
    robot_par_bloc = [r for r in repartition if r["ensemble_code"] == "ROBOT"]
    assert sum(r["depense_ht"] for r in robot_par_bloc) == pytest.approx(120, abs=TOLERANCE)
