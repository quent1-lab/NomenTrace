"""Liste des composants : filtre « Créé par » et modifications en masse (aperçu, tout ou rien)."""

from fastapi.testclient import TestClient

TROIS = ["ESSAI-ALI-003", "ESSAI-ALI-004", "ESSAI-ALI-005"]
NOUVEAU = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Pièce d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 2,
}


def _modifier(client: TestClient, ids: list[str], simuler: bool = True, **corps: object):
    return client.post(
        "/api/composants/lot/modification", json={"ids": ids, "simuler": simuler, **corps}
    )


def _fiche(client: TestClient, identifiant: str) -> dict:
    return client.get(f"/api/composants/{identifiant}").json()["composant"]


# --- Créé par -------------------------------------------------------------------------------


def test_filtre_et_colonne_cree_par(client_essai: TestClient) -> None:
    crees = [client_essai.post("/api/composants", json=NOUVEAU).json()["id"] for _ in range(2)]
    createurs = client_essai.get("/api/composants/createurs").json()
    # Le jeu d'essai est chargé sans journal : ses composants n'ont pas d'auteur connu.
    assert createurs["inconnus"] == 60
    assert len(createurs["createurs"]) == 1
    auteur = createurs["createurs"][0]
    assert auteur["nb"] == 2

    filtres = client_essai.get("/api/composants", params={"cree_par": auteur["nom"]}).json()
    assert [c["id"] for c in filtres] == crees
    assert {c["cree_par"] for c in filtres} == {auteur["nom"]}

    inconnus = client_essai.get("/api/composants", params={"cree_par_inconnu": True}).json()
    assert len(inconnus) == 60
    assert {c["cree_par"] for c in inconnus} == {None}


# --- Modification en masse ------------------------------------------------------------------


def test_apercu_ne_modifie_rien(client_essai: TestClient) -> None:
    recap = _modifier(client_essai, TROIS, modifications={"statut_appro": "Devis demande"}).json()

    assert recap["changent"] == TROIS
    assert recap["a_jour"] == [] and recap["refuses"] == []
    assert recap["applique"] is False
    assert {d["champ"] for d in recap["detail"]} == {"statut_appro"}
    assert recap["detail"][0] == {
        "id": "ESSAI-ALI-003",
        "champ": "statut_appro",
        "avant": "Non lance",
        "apres": "Devis demande",
    }
    assert _fiche(client_essai, "ESSAI-ALI-003")["statut_appro"] == "Non lance"


def test_appliquer_ecrit_et_journalise(client_essai: TestClient) -> None:
    client_essai.patch("/api/composants/ESSAI-ALI-004", json={"statut_appro": "Devis demande"})

    recap = _modifier(
        client_essai, TROIS, simuler=False, modifications={"statut_appro": "Devis demande"}
    ).json()

    assert recap["applique"] is True
    assert recap["changent"] == ["ESSAI-ALI-003", "ESSAI-ALI-005"]
    assert recap["a_jour"] == ["ESSAI-ALI-004"]
    assert {_fiche(client_essai, i)["statut_appro"] for i in TROIS} == {"Devis demande"}
    journal = client_essai.get(
        "/api/journal", params={"table_cible": "composant", "cle_cible": "ESSAI-ALI-005"}
    ).json()
    assert any(j["champ"] == "statut_appro" for j in journal)


def test_tout_ou_rien(client_essai: TestClient) -> None:
    avant = {i: _fiche(client_essai, i)["fournisseur_nom"] for i in TROIS}
    ids = [*TROIS, "ESSAI-ALI-999"]
    recap = _modifier(
        client_essai, ids, simuler=False, modifications={"fournisseur_nom": "Mouser"}
    ).json()

    assert recap["applique"] is False
    assert [r["id"] for r in recap["refuses"]] == ["ESSAI-ALI-999"]
    assert "introuvable" in recap["refuses"][0]["raison"]
    assert recap["changent"]
    assert {i: _fiche(client_essai, i)["fournisseur_nom"] for i in TROIS} == avant


def test_valeur_refusee_pour_toute_la_selection(client_essai: TestClient) -> None:
    recap = _modifier(client_essai, TROIS, modifications={"criticite": "Inexistante"})
    assert recap.status_code == 400


def test_champ_hors_perimetre_refuse(client_essai: TestClient) -> None:
    assert _modifier(client_essai, TROIS, modifications={"qte_besoin": 3}).status_code == 422
    assert _modifier(client_essai, TROIS, modifications={"designation": "x"}).status_code == 422


def test_caracteristiques_posees_et_effacees(client_essai: TestClient) -> None:
    attribut = client_essai.post("/api/attributs", json={"libelle": "Tension", "type": "texte"})
    code = attribut.json()["code"]

    recap = _modifier(client_essai, TROIS, simuler=False, attributs={code: "48 V"}).json()
    assert recap["applique"] is True and recap["changent"] == TROIS
    assert client_essai.get("/api/composants/ESSAI-ALI-003").json()["attributs"][code] == "48 V"

    recap = _modifier(client_essai, TROIS[:1], simuler=False, attributs={code: None}).json()
    assert recap["changent"] == TROIS[:1]
    assert code not in client_essai.get("/api/composants/ESSAI-ALI-003").json()["attributs"]


# --- Affectation en masse -------------------------------------------------------------------


def _affecter(client: TestClient, ids: list[str], simuler: bool = True, **corps: object):
    return client.post(
        "/api/composants/lot/affectation",
        json={"ids": ids, "ensemble_code": "CHASSIS", "simuler": simuler, **corps},
    )


def test_affectation_au_besoin_de_chaque_composant(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    client_essai.post(
        "/api/ensembles/CHASSIS/affectations", json={"composant_id": "ESSAI-ALI-004", "qte": 1}
    )

    apercu = _affecter(client_essai, TROIS).json()
    assert apercu["nouvelles"] == ["ESSAI-ALI-003", "ESSAI-ALI-005"]
    assert apercu["deja"] == ["ESSAI-ALI-004"]
    assert client_essai.get("/api/ensembles/CHASSIS/composants").json()[0]["composant_id"] == (
        "ESSAI-ALI-004"
    )

    recap = _affecter(client_essai, TROIS, simuler=False).json()
    assert recap["applique"] is True
    lignes = {
        ligne["composant_id"]: ligne["qte_affectee"]
        for ligne in client_essai.get("/api/ensembles/CHASSIS/composants").json()
    }
    besoins = {i: _fiche(client_essai, i)["qte_besoin"] for i in TROIS}
    assert lignes == {**besoins, "ESSAI-ALI-004": 1}


def test_affectation_quantite_fixe_et_besoin_nul(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    nul = client_essai.post("/api/composants", json={**NOUVEAU, "qte_besoin": 0}).json()["id"]

    recap = _affecter(client_essai, [*TROIS, nul], simuler=False).json()
    assert recap["applique"] is False
    assert [r["id"] for r in recap["refuses"]] == [nul]
    assert client_essai.get("/api/ensembles/CHASSIS/composants").json() == []

    recap = _affecter(client_essai, [*TROIS, nul], simuler=False, qte=2).json()
    assert recap["applique"] is True
    quantites = {
        ligne["composant_id"]: ligne["qte_affectee"]
        for ligne in client_essai.get("/api/ensembles/CHASSIS/composants").json()
    }
    assert set(quantites.values()) == {2} and len(quantites) == 4


def test_affectation_ensemble_inconnu(client_essai: TestClient) -> None:
    assert _affecter(client_essai, TROIS).status_code == 404
