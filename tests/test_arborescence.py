"""Arborescence d'ensembles : cycles, indicateurs cumulés, budgets d'ensemble."""

import pytest
from fastapi.testclient import TestClient

from backend.services.ensembles_arbre import NoeudBudget, repartir_budget

# PU HT du jeu d'essai : 1,13 € et 34 €.
PU_TR = 1.13
PU_ALI = 34.0


def _ensemble(client: TestClient, code: str, parent: str | None = None, **autres: object) -> None:
    corps = {"code": code, "nom": code.title(), "parent_code": parent, **autres}
    reponse = client.post("/api/ensembles", json=corps)
    assert reponse.status_code == 201, reponse.text


def _affecter(client: TestClient, code: str, composant_id: str, qte: int) -> None:
    corps = {"composant_id": composant_id, "qte": qte}
    reponse = client.post(f"/api/ensembles/{code}/affectations", json=corps)
    assert reponse.status_code == 201, reponse.text


def _arbre(client: TestClient) -> tuple[dict, dict[str, dict]]:
    arbre = client.get("/api/ensembles/arbre").json()
    return arbre["racine"], {e["code"]: e for e in arbre["ensembles"]}


def _trois_niveaux(client: TestClient) -> None:
    _ensemble(client, "ROBOT")
    _ensemble(client, "CHASSIS", "ROBOT")
    _ensemble(client, "ROUE", "CHASSIS")


# --- Arborescence -----------------------------------------------------------------------------


def test_refus_de_cycle(client_essai: TestClient) -> None:
    _trois_niveaux(client_essai)
    for parent in ("ROUE", "CHASSIS", "ROBOT"):
        reponse = client_essai.patch("/api/ensembles/ROBOT", json={"parent_code": parent})
        assert reponse.status_code == 409, parent
        assert "boucle" in reponse.json()["erreur"]
    assert _arbre(client_essai)[1]["ROBOT"]["parent_code"] is None


def test_deplacer_un_sous_ensemble(client_essai: TestClient) -> None:
    _trois_niveaux(client_essai)
    _ensemble(client_essai, "MAT")
    reponse = client_essai.patch("/api/ensembles/CHASSIS", json={"parent_code": "MAT"})
    assert reponse.status_code == 200
    assert reponse.json()["chemin"] == [{"code": "MAT", "nom": "Mat"}]
    ordre = [(e["code"], e["niveau"]) for e in client_essai.get("/api/ensembles").json()]
    assert ordre == [("MAT", 1), ("CHASSIS", 2), ("ROUE", 3), ("ROBOT", 1)]


def test_parent_archive_ou_inconnu_refuse(client_essai: TestClient) -> None:
    _ensemble(client_essai, "VIEUX")
    assert client_essai.delete("/api/ensembles/VIEUX").status_code == 200
    reponse = client_essai.post(
        "/api/ensembles", json={"code": "NEUF", "nom": "Neuf", "parent_code": "VIEUX"}
    )
    assert reponse.status_code == 400
    assert "archivé" in reponse.json()["erreur"]
    reponse = client_essai.post(
        "/api/ensembles", json={"code": "NEUF", "nom": "Neuf", "parent_code": "ZZZ"}
    )
    assert reponse.status_code == 400


def test_archiver_un_parent_refuse(client_essai: TestClient) -> None:
    _trois_niveaux(client_essai)
    reponse = client_essai.delete("/api/ensembles/CHASSIS")
    assert reponse.status_code == 409
    assert "sous-ensemble" in reponse.json()["erreur"]
    assert client_essai.delete("/api/ensembles/ROUE").status_code == 200
    assert client_essai.delete("/api/ensembles/CHASSIS").status_code == 200


def test_indicateurs_cumules_sur_trois_niveaux(client_essai: TestClient) -> None:
    _trois_niveaux(client_essai)
    _affecter(client_essai, "ROBOT", "ESSAI-TR-001", 1)
    _affecter(client_essai, "CHASSIS", "ESSAI-ALI-003", 2)
    _affecter(client_essai, "ROUE", "ESSAI-TR-001", 3)
    _, noeuds = _arbre(client_essai)
    robot, chassis, roue = noeuds["ROBOT"], noeuds["CHASSIS"], noeuds["ROUE"]
    # Propre : les affectations du nœud seules.
    assert robot["nb_pieces_total"] == 1
    assert robot["cout_ht"] == PU_TR
    # Cumulé : le nœud et tous ses descendants ; un composant présent deux fois compte une
    # seule fois comme composant distinct, mais toutes ses pièces comptent.
    assert robot["cumul"]["nb_composants_distincts"] == 2
    assert robot["cumul"]["nb_pieces_total"] == 6
    assert robot["cumul"]["cout_ht"] == pytest.approx(4 * PU_TR + 2 * PU_ALI, abs=0.01)
    assert chassis["cumul"]["nb_pieces_total"] == 5
    assert chassis["cumul"]["cout_ht"] == pytest.approx(3 * PU_TR + 2 * PU_ALI, abs=0.01)
    assert roue["cumul"]["cout_ht"] == pytest.approx(3 * PU_TR, abs=0.01)
    assert (robot["nb_sous_ensembles"], chassis["nb_sous_ensembles"]) == (2, 1)
    assert (robot["niveau"], chassis["niveau"], roue["niveau"]) == (1, 2, 3)
    assert roue["branche_code"] == "ROBOT"
    repartition = client_essai.get("/api/ensembles/repartition", params={"cumul": True}).json()
    blocs_robot = {
        r["bloc_code"]: r["nb_pieces"] for r in repartition if r["ensemble_code"] == "ROBOT"
    }
    assert blocs_robot == {"TR": 4, "ALI": 2}


def test_archive_sort_des_cumuls(client_essai: TestClient) -> None:
    _ensemble(client_essai, "ROBOT")
    _ensemble(client_essai, "CAPOT", "ROBOT")
    _affecter(client_essai, "ROBOT", "ESSAI-TR-001", 1)
    assert client_essai.delete("/api/ensembles/CAPOT").status_code == 200
    robot = client_essai.get("/api/ensembles/ROBOT").json()
    assert robot["nb_sous_ensembles"] == 0
    assert robot["enfants"] == []
    assert robot["cumul"]["nb_pieces_total"] == 1


# --- Budgets : règle de répartition -----------------------------------------------------------


def _noeud(code: str, verrou: float | None = None) -> NoeudBudget:
    return NoeudBudget(code, verrou is not None, verrou)


def test_parts_egales_entre_les_enfants() -> None:
    resultat = repartir_budget(900, [_noeud("A"), _noeud("B"), _noeud("C")], False)
    assert resultat.parts == {"A": 300, "B": 300, "C": 300}
    assert resultat.propre == pytest.approx(0)
    assert resultat.depassement is None


def test_part_propre_si_le_parent_a_des_affectations() -> None:
    avec_propre = repartir_budget(900, [_noeud("A"), _noeud("B")], True)
    assert avec_propre.parts == {"A": 300, "B": 300}
    assert avec_propre.propre == pytest.approx(300)


def test_verrouille_garde_son_budget() -> None:
    enfants = [_noeud("A", verrou=700), _noeud("B"), _noeud("C")]
    resultat = repartir_budget(1000, enfants, False)
    assert resultat.parts == {"A": 700, "B": pytest.approx(150), "C": pytest.approx(150)}
    assert resultat.propre == pytest.approx(0)


def test_tout_verrouille_le_reste_va_au_parent() -> None:
    resultat = repartir_budget(1000, [_noeud("A", verrou=600)], False)
    assert resultat.parts == {"A": 600}
    assert resultat.propre == pytest.approx(400)


def test_depassement_des_verrouilles() -> None:
    enfants = [_noeud("A", verrou=800), _noeud("B", verrou=500), _noeud("C")]
    resultat = repartir_budget(1000, enfants, True)
    assert resultat.parts == {"A": 800, "B": 500, "C": 0}
    assert resultat.propre == 0
    assert resultat.depassement == pytest.approx(300)


def test_sans_budget_seuls_les_verrouilles_en_ont_un() -> None:
    resultat = repartir_budget(None, [_noeud("A", verrou=50), _noeud("B")], False)
    assert resultat.parts == {"A": 50, "B": None}
    assert resultat.propre is None


# --- Budgets : de bout en bout ----------------------------------------------------------------


def test_racine_porte_le_budget_du_projet(client_essai: TestClient) -> None:
    racine, _ = _arbre(client_essai)
    assert racine["nom"] == "Projet d'essai"
    assert racine["budget_ht"] == 3000
    assert racine["nb_ensembles"] == 0
    assert racine["budget_non_reparti_ht"] == 3000
    client_essai.patch("/api/parametres", json={"budget_ht": 3500})
    assert _arbre(client_essai)[0]["budget_ht"] == 3500


def test_budgets_sur_l_arbre(client_essai: TestClient) -> None:
    _trois_niveaux(client_essai)
    _ensemble(client_essai, "MAT")
    _affecter(client_essai, "CHASSIS", "ESSAI-ALI-003", 1)  # 34 €
    _affecter(client_essai, "ROUE", "ESSAI-ALI-003", 2)  # 68 €
    _affecter(client_essai, "MAT", "ESSAI-ALI-003", 1)  # 34 €
    racine, noeuds = _arbre(client_essai)
    # Racine : 3000 € à parts égales entre ROBOT et MAT, quels que soient leurs coûts.
    assert noeuds["ROBOT"]["budget_ht"] == pytest.approx(1500, abs=0.01)
    assert noeuds["MAT"]["budget_ht"] == pytest.approx(1500, abs=0.01)
    # ROBOT sans affectation propre : tout va à CHASSIS.
    assert noeuds["CHASSIS"]["budget_ht"] == pytest.approx(1500, abs=0.01)
    # CHASSIS porte une affectation : sa part propre et ROUE ont une part chacun.
    assert noeuds["ROUE"]["budget_ht"] == pytest.approx(750, abs=0.01)
    assert noeuds["CHASSIS"]["budget_propre_ht"] == pytest.approx(750, abs=0.01)
    assert noeuds["ROUE"]["ecart_budget_ht"] == pytest.approx(68 - 750, abs=0.01)
    assert racine["budget_non_reparti_ht"] == pytest.approx(0, abs=0.01)

    # Verrouiller MAT à 1000 € : ROBOT reçoit le reste.
    reponse = client_essai.patch(
        "/api/ensembles/MAT", json={"budget_cible_ht": 1000, "budget_verrouille": True}
    )
    assert reponse.status_code == 200, reponse.text
    _, noeuds = _arbre(client_essai)
    assert noeuds["MAT"]["budget_ht"] == 1000
    assert noeuds["ROBOT"]["budget_ht"] == pytest.approx(2000, abs=0.01)

    # Déverrouiller en effaçant le montant, dans la même requête.
    reponse = client_essai.patch(
        "/api/ensembles/MAT", json={"budget_cible_ht": None, "budget_verrouille": False}
    )
    assert reponse.status_code == 200, reponse.text
    assert _arbre(client_essai)[1]["MAT"]["budget_ht"] == pytest.approx(1500, abs=0.01)


def test_depassement_signale_sur_le_parent(client_essai: TestClient) -> None:
    _ensemble(client_essai, "A", budget_cible_ht=2000, budget_verrouille=True)
    _ensemble(client_essai, "B", budget_cible_ht=1500, budget_verrouille=True)
    _ensemble(client_essai, "C")
    racine, noeuds = _arbre(client_essai)
    assert racine["depassement_verrouille_ht"] == 500
    assert noeuds["C"]["budget_ht"] == 0


def test_verrou_sans_montant_refuse(client_essai: TestClient) -> None:
    reponse = client_essai.post(
        "/api/ensembles", json={"code": "A", "nom": "A", "budget_verrouille": True}
    )
    assert reponse.status_code == 400
    assert "budget" in reponse.json()["erreur"]
    _ensemble(client_essai, "A")
    assert (
        client_essai.patch("/api/ensembles/A", json={"budget_verrouille": True}).status_code == 400
    )
