"""Tests de l'API : identifiants, journal, affectations, filtres, format des erreurs."""

from fastapi.testclient import TestClient

NOUVEAU_COMPOSANT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 1,
}


def _creer_ensemble(client: TestClient, code: str) -> None:
    reponse = client.post("/api/ensembles", json={"code": code, "nom": f"Ensemble {code}"})
    assert reponse.status_code == 201, reponse.text


def _affecter(client: TestClient, code: str, composant_id: str, qte: int) -> dict:
    reponse = client.post(
        f"/api/ensembles/{code}/affectations", json={"composant_id": composant_id, "qte": qte}
    )
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def test_identifiants_generes_se_suivent(client_essai: TestClient) -> None:
    identifiants = [
        client_essai.post("/api/composants", json=NOUVEAU_COMPOSANT).json()["id"] for _ in range(3)
    ]
    assert identifiants == ["ESSAI-ALI-021", "ESSAI-ALI-022", "ESSAI-ALI-023"]


def test_apercu_identifiant(client_essai: TestClient) -> None:
    assert client_essai.get("/api/blocs/ALI/prochain-id").json() == {"id": "ESSAI-ALI-021"}
    assert client_essai.get("/api/blocs/ALI/prochain-id").json() == {"id": "ESSAI-ALI-021"}
    assert client_essai.get("/api/blocs/XXX/prochain-id").status_code == 404


def test_identifiant_compte_les_archives(client_essai: TestClient) -> None:
    assert client_essai.delete("/api/composants/ESSAI-ALI-020").status_code == 200
    reponse = client_essai.post("/api/composants", json=NOUVEAU_COMPOSANT)
    assert reponse.json()["id"] == "ESSAI-ALI-021"


def test_identifiant_suit_le_prefixe(client_essai: TestClient) -> None:
    assert client_essai.patch("/api/parametres", json={"prefixe_id": "ROB"}).status_code == 200
    reponse = client_essai.post("/api/composants", json=NOUVEAU_COMPOSANT)
    assert reponse.json()["id"] == "ROB-ALI-001"


def test_creation_refuse_un_identifiant_fourni(client_essai: TestClient) -> None:
    reponse = client_essai.post("/api/composants", json={**NOUVEAU_COMPOSANT, "id": "X-1"})
    assert reponse.status_code == 422
    assert "erreur" in reponse.json()


def test_patch_journalise_chaque_champ_modifie(client_essai: TestClient) -> None:
    cible = "/api/journal?table_cible=composant&cle_cible=ESSAI-TR-001"
    avant = len(client_essai.get(cible).json())
    modifs = {"qte_besoin": 6, "criticite": "Bloquant", "pu_releve": 1.13}
    reponse = client_essai.patch("/api/composants/ESSAI-TR-001", json=modifs)
    assert reponse.status_code == 200
    lignes = client_essai.get(cible).json()
    assert len(lignes) - avant == 2
    assert {ligne["champ"] for ligne in lignes[:2]} == {"qte_besoin", "criticite"}


def test_patch_sans_changement_n_ecrit_rien(client_essai: TestClient) -> None:
    cible = "/api/journal?table_cible=composant&cle_cible=ESSAI-TR-001"
    avant = len(client_essai.get(cible).json())
    client_essai.patch("/api/composants/ESSAI-TR-001", json={"qte_besoin": 4})
    assert len(client_essai.get(cible).json()) == avant


def test_double_affectation_refusee_lisiblement(client_essai: TestClient) -> None:
    _creer_ensemble(client_essai, "NACELLE")
    _affecter(client_essai, "NACELLE", "ESSAI-TR-001", 1)
    reponse = client_essai.post(
        "/api/ensembles/NACELLE/affectations", json={"composant_id": "ESSAI-TR-001", "qte": 1}
    )
    assert reponse.status_code == 409
    assert "déjà affecté" in reponse.json()["erreur"]


def test_affectation_peut_depasser_le_besoin(client_essai: TestClient) -> None:
    _creer_ensemble(client_essai, "MAT")
    affectation = _affecter(client_essai, "MAT", "ESSAI-ODB-001", 5)
    assert affectation["qte_affectee"] == 5


def test_archivage_ensemble_affecte_refuse(client_essai: TestClient) -> None:
    _creer_ensemble(client_essai, "COFFRET")
    affectation = _affecter(client_essai, "COFFRET", "ESSAI-ALI-001", 1)
    reponse = client_essai.delete("/api/ensembles/COFFRET")
    assert reponse.status_code == 409
    assert "affectation" in reponse.json()["erreur"]
    client_essai.delete(f"/api/affectations/{affectation['affectation_id']}")
    assert client_essai.delete("/api/ensembles/COFFRET").status_code == 200


def test_affectations_journalisees(client_essai: TestClient) -> None:
    _creer_ensemble(client_essai, "BUMPER")
    affectation = _affecter(client_essai, "BUMPER", "ESSAI-BMP-001", 1)
    client_essai.patch(f"/api/affectations/{affectation['affectation_id']}", json={"qte": 2})
    client_essai.delete(f"/api/affectations/{affectation['affectation_id']}")
    lignes = client_essai.get(
        "/api/journal?table_cible=affectation&cle_cible=BUMPER:ESSAI-BMP-001"
    ).json()
    assert [(ligne["ancienne_valeur"], ligne["nouvelle_valeur"]) for ligne in lignes] == [
        ("2", None),
        ("1", "2"),
        (None, "1"),
    ]


def test_filtres_combines(client_essai: TestClient) -> None:
    ali = client_essai.get("/api/composants?bloc=ALI").json()
    assert len(ali) == 20
    a_chiffrer = client_essai.get("/api/composants?a_chiffrer=true").json()
    assert len(a_chiffrer) == 11
    assert len(client_essai.get("/api/composants?bloc=ALI&a_chiffrer=true").json()) == 6
    _creer_ensemble(client_essai, "NACELLE")
    _affecter(client_essai, "NACELLE", "ESSAI-ALI-010", 3)  # besoin 3 : pas d'écart
    _affecter(client_essai, "NACELLE", "ESSAI-ALI-011", 1)  # besoin 3 : écart
    assert len(client_essai.get("/api/composants?non_affecte=true").json()) == 58
    ecarts = client_essai.get("/api/composants?ecart_affectation=true").json()
    assert [c["id"] for c in ecarts] == ["ESSAI-ALI-011"]
    ensemble = client_essai.get("/api/composants?ensemble=NACELLE&bloc=ALI").json()
    assert len(ensemble) == 2
    recherche = client_essai.get("/api/composants?q=mcp2562").json()
    assert [c["id"] for c in recherche] == ["ESSAI-TR-001"]


def test_tri_hors_liste_blanche_refuse(client_essai: TestClient) -> None:
    reponse = client_essai.get("/api/composants?tri=id;DROP TABLE composant")
    assert reponse.status_code == 400
    assert "erreur" in reponse.json()


def test_tri_par_total_decroissant(client_essai: TestClient) -> None:
    premiers = client_essai.get("/api/composants?tri=total_ht&ordre=desc").json()[:2]
    assert [c["id"] for c in premiers] == ["ESSAI-OBS-001", "ESSAI-MEC-004"]


def test_montants_arrondis_a_la_sortie(client_essai: TestClient) -> None:
    composant = client_essai.get("/api/composants/ESSAI-ODB-005").json()["composant"]
    assert composant["pu_ht"] == 9.96
    assert composant["taux_tva"] == 0.2
    assert client_essai.get("/api/pilotage").json()["cout_ht"] == 3184.98


def test_erreur_de_validation_au_format_francais(client_essai: TestClient) -> None:
    reponse = client_essai.patch("/api/composants/ESSAI-TR-001", json={"qte_besoin": -1})
    assert reponse.status_code == 422
    assert set(reponse.json()) == {"erreur"}


def test_composant_inconnu(client_essai: TestClient) -> None:
    reponse = client_essai.get("/api/composants/ESSAI-XXX-999")
    assert reponse.status_code == 404
    assert "introuvable" in reponse.json()["erreur"]


def test_renommage_fournisseur_en_cascade(client_essai: TestClient) -> None:
    reponse = client_essai.patch("/api/fournisseurs/Kubii", json={"nom": "Kubii SAS", "pays": "FR"})
    assert reponse.status_code == 200
    assert reponse.json()["nom"] == "Kubii SAS"
    composant = client_essai.get("/api/composants/ESSAI-ODB-001").json()["composant"]
    assert composant["fournisseur_nom"] == "Kubii SAS"


def test_commande_numero_genere_et_engagement(client_essai: TestClient) -> None:
    commande = client_essai.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()
    assert commande["numero"] == "CMD-001"
    ligne = {"composant_id": "ESSAI-TR-001", "qte_commandee": 4, "pu_ht_devis": 1.13}
    assert client_essai.post("/api/commandes/CMD-001/lignes", json=ligne).status_code == 201
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 0
    client_essai.patch("/api/commandes/CMD-001", json={"statut": "Commande", "port_ht": 10})
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 14.52
    assert client_essai.get("/api/commandes").json()[0]["total_ht"] == 14.52


def test_mouvement_montage_sans_ensemble_refuse(client_essai: TestClient) -> None:
    mouvement = {
        "date": "2026-10-01",
        "composant_id": "ESSAI-TR-001",
        "sens": "Sortie",
        "type_mouvement": "Sortie montage",
        "qte": 1,
    }
    reponse = client_essai.post("/api/mouvements", json=mouvement)
    assert reponse.status_code == 400
    assert "ensemble" in reponse.json()["erreur"]


def test_parametres(client_essai: TestClient) -> None:
    assert client_essai.get("/api/parametres").json()["nom_projet"] == "Projet d'essai"
    assert client_essai.patch("/api/parametres", json={"budget_ht": 3500}).status_code == 200
    assert client_essai.get("/api/pilotage").json()["ecart_budget_ht"] == -315.02
