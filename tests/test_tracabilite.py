"""Phase 12 bis : historiques, duplication d'ensemble, demandes de devis, recherche globale."""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.services.ensembles_copie import proposer_code

PDF = b"%PDF-1.4\n% document de test\n"


def _ensemble(client: TestClient, code: str, parent: str | None = None) -> None:
    corps = {"code": code, "nom": code.title(), "parent_code": parent}
    assert client.post("/api/ensembles", json=corps).status_code == 201


def _affecter(client: TestClient, code: str, composant_id: str, qte: int) -> None:
    corps = {"composant_id": composant_id, "qte": qte}
    assert client.post(f"/api/ensembles/{code}/affectations", json=corps).status_code == 201


# --- Historique d'un composant ----------------------------------------------------------------


def test_frise_d_un_composant(client_essai: TestClient) -> None:
    composant = "ESSAI-ALI-006"
    client_essai.patch(f"/api/composants/{composant}", json={"qte_besoin": 2})
    _ensemble(client_essai, "CHASSIS")
    _affecter(client_essai, "CHASSIS", composant, 2)
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()[
        "numero"
    ]
    corps = {"composant_id": composant, "qte_commandee": 2, "pu_ht_devis": 3.0}
    client_essai.post(f"/api/commandes/{numero}/lignes", json=corps)
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    reception = {"date": "2026-10-02", "lignes": []}
    lignes = client_essai.get(f"/api/commandes/{numero}/lignes").json()
    reception["lignes"] = [{"id": lignes[0]["id"], "qte": 2}]
    assert (
        client_essai.post(f"/api/commandes/{numero}/reception", json=reception).status_code == 200
    )
    client_essai.post(
        f"/api/composants/{composant}/documents",
        files=[("fichiers", ("fiche.pdf", PDF))],
        data={"type_document": "Fiche technique"},
    )
    mouvement = {
        "date": "2099-01-01",
        "composant_id": composant,
        "type_mouvement": "Sortie montage",
        "sens": "Sortie",
        "qte": 1,
        "ensemble_code": "CHASSIS",
    }
    assert client_essai.post("/api/mouvements", json=mouvement).status_code == 201

    frise = client_essai.get(f"/api/composants/{composant}").json()["historique"]
    categories = {e["categorie"] for e in frise}
    assert categories >= {"modification", "achat", "stock", "montage", "document"}
    # La plus récente en haut : le montage daté de 2099 passe devant tout le reste.
    assert frise[0]["type_mouvement"] == "Sortie montage"
    horodatages = [e["horodatage"] for e in frise]
    assert horodatages == sorted(horodatages, reverse=True)
    achats = [e for e in frise if e["categorie"] == "achat"]
    assert all(e["commande_numero"] == numero for e in achats)
    assert any(e["champ"] == "statut" and e["nouvelle_valeur"] == "Commande" for e in achats)
    assert any(e["champ"] == "qte_recue" for e in achats)


def test_frise_ne_melange_pas_les_composants(client_essai: TestClient) -> None:
    client_essai.patch("/api/composants/ESSAI-ALI-006", json={"qte_besoin": 2})
    frise = client_essai.get("/api/composants/ESSAI-ALI-007").json()["historique"]
    assert all(e["cle_cible"] != "ESSAI-ALI-006" for e in frise)


# --- Historique global -----------------------------------------------------------------------


def test_historique_global_filtres_et_pages(client_essai: TestClient) -> None:
    for besoin in (2, 3, 4):
        client_essai.patch("/api/composants/ESSAI-ALI-006", json={"qte_besoin": besoin})
    _ensemble(client_essai, "MAT")
    tout = client_essai.get("/api/historique").json()
    assert tout["total"] >= 4
    composants = client_essai.get(
        "/api/historique", params={"table": "composant", "texte": "ALI-006"}
    ).json()
    assert composants["total"] == 3
    assert [ligne["nouvelle_valeur"] for ligne in composants["lignes"]] == ["4", "3", "2"]
    page2 = client_essai.get(
        "/api/historique", params={"table": "composant", "texte": "ALI-006", "taille": 2, "page": 2}
    ).json()
    assert [ligne["nouvelle_valeur"] for ligne in page2["lignes"]] == ["2"]
    assert client_essai.get("/api/historique", params={"origine": "import"}).json()["total"] == 0
    assert client_essai.get("/api/historique", params={"au": "2000-01-01"}).json()["total"] == 0
    assert "ensemble" in client_essai.get("/api/historique/tables").json()


def test_export_de_l_historique(client_essai: TestClient) -> None:
    client_essai.patch("/api/composants/ESSAI-ALI-006", json={"qte_besoin": 2})
    reponse = client_essai.get("/api/historique/export", params={"table": "composant"})
    assert reponse.status_code == 200
    feuille = load_workbook(BytesIO(reponse.content)).active
    lignes = list(feuille.values)
    assert lignes[0][0] == "Date"
    assert len(lignes) == 2
    assert lignes[1][2] == "ESSAI-ALI-006"


# --- Duplication d'un ensemble ---------------------------------------------------------------


def test_proposer_code() -> None:
    assert proposer_code("ROUE", "ROUE-G", "ROUE2") == "ROUE2-G"
    assert proposer_code("CHASSIS", "AXE", "CHASSIS2") == "AXE-CHASSIS2"


def test_dupliquer_sans_sous_ensembles(client_essai: TestClient) -> None:
    _ensemble(client_essai, "ROBOT")
    _ensemble(client_essai, "ROUE", "ROBOT")
    _ensemble(client_essai, "ROUE-MOTEUR", "ROUE")
    _affecter(client_essai, "ROUE", "ESSAI-TR-001", 2)
    client_essai.patch("/api/ensembles/ROUE", json={"statut_montage": "Monte"})
    corps = {"code": "ROUE2", "nom": "Roue droite"}
    reponse = client_essai.post("/api/ensembles/ROUE/copie", json=corps)
    assert reponse.status_code == 201, reponse.text
    copie = reponse.json()
    assert copie["parent_code"] == "ROBOT"
    assert copie["statut_montage"] == "Non commence"
    assert copie["nb_pieces_total"] == 2
    assert copie["enfants"] == []


def test_dupliquer_avec_sous_ensembles(client_essai: TestClient) -> None:
    _ensemble(client_essai, "ROUE")
    _ensemble(client_essai, "ROUE-MOTEUR", "ROUE")
    _ensemble(client_essai, "CAPTEUR", "ROUE-MOTEUR")
    _affecter(client_essai, "CAPTEUR", "ESSAI-TR-001", 1)
    proposition = client_essai.get("/api/ensembles/ROUE/copie", params={"nouveau": "ROUE2"}).json()
    assert [p["code_propose"] for p in proposition] == ["ROUE2-MOTEUR", "CAPTEUR-ROUE2"]
    corps = {
        "code": "ROUE2",
        "nom": "Roue 2",
        "parent_code": None,
        "avec_sous_ensembles": True,
        "avec_affectations": False,
        "codes": {"CAPTEUR": "CAPT2"},
    }
    reponse = client_essai.post("/api/ensembles/ROUE/copie", json=corps)
    assert reponse.status_code == 201, reponse.text
    arbre = {e["code"]: e for e in client_essai.get("/api/ensembles").json()}
    assert arbre["ROUE2-MOTEUR"]["parent_code"] == "ROUE2"
    assert arbre["CAPT2"]["parent_code"] == "ROUE2-MOTEUR"
    assert arbre["CAPT2"]["nb_composants_distincts"] == 0


def test_dupliquer_refuse_un_code_pris(client_essai: TestClient) -> None:
    _ensemble(client_essai, "ROUE")
    _ensemble(client_essai, "ROUE-G", "ROUE")
    _ensemble(client_essai, "MAT")
    corps = {"code": "ROUE2", "nom": "Roue 2", "avec_sous_ensembles": True}
    corps["codes"] = {"ROUE-G": "MAT"}
    reponse = client_essai.post("/api/ensembles/ROUE/copie", json=corps)
    assert reponse.status_code == 409
    # Rien n'a été créé : la copie est tout ou rien.
    codes = {e["code"] for e in client_essai.get("/api/ensembles").json()}
    assert "ROUE2" not in codes


# --- Demandes de devis -----------------------------------------------------------------------


def test_candidats_regroupes_par_fournisseur(client_essai: TestClient) -> None:
    candidats = client_essai.get("/api/demandes-devis").json()
    mouser = next(g for g in candidats["fournisseurs"] if g["fournisseur_nom"] == "Mouser")
    assert {ligne["id"] for ligne in mouser["lignes"]} == {
        "ESSAI-AGI-003",
        "ESSAI-ALI-006",
        "ESSAI-TR-001",
    }
    assert "ESSAI-ALI-007" in {ligne["id"] for ligne in candidats["sans_fournisseur"]}


def test_creer_les_demandes_de_devis(client_essai: TestClient) -> None:
    reponse = client_essai.post(
        "/api/demandes-devis",
        json={"composants": ["ESSAI-TR-001", "ESSAI-ALI-006", "ESSAI-ODB-005"]},
    )
    assert reponse.status_code == 201, reponse.text
    creees = {c["fournisseur_nom"]: c for c in reponse.json()}
    assert set(creees) == {"Mouser", "Kubii"}
    assert all(c["type"] == "Devis" and c["statut"] == "A demander" for c in creees.values())
    lignes = client_essai.get(f"/api/commandes/{creees['Mouser']['numero']}/lignes").json()
    assert {(ligne["composant_id"], ligne["qte_commandee"]) for ligne in lignes} == {
        ("ESSAI-TR-001", 4),
        ("ESSAI-ALI-006", 1),
    }
    assert all(ligne["pu_ht_devis"] is None for ligne in lignes)
    # Le devis ouvert est signalé : on ne le redemande pas sans le voir.
    candidats = client_essai.get("/api/demandes-devis").json()
    mouser = next(g for g in candidats["fournisseurs"] if g["fournisseur_nom"] == "Mouser")
    tr = next(ligne for ligne in mouser["lignes"] if ligne["id"] == "ESSAI-TR-001")
    assert tr["demandes_ouvertes"] == [creees["Mouser"]["numero"]]


def test_demande_refusee_sans_fournisseur(client_essai: TestClient) -> None:
    reponse = client_essai.post("/api/demandes-devis", json={"composants": ["ESSAI-ALI-007"]})
    assert reponse.status_code == 400
    assert "fournisseur" in reponse.json()["erreur"]
    assert client_essai.get("/api/commandes").json() == []


# --- Filtre par ensemble avec ses sous-ensembles ---------------------------------------------


def test_filtre_ensemble_avec_ses_sous_ensembles(client_essai: TestClient) -> None:
    _ensemble(client_essai, "ROBOT")
    _ensemble(client_essai, "ROUE", "ROBOT")
    _affecter(client_essai, "ROBOT", "ESSAI-TR-001", 1)
    _affecter(client_essai, "ROUE", "ESSAI-ALI-003", 1)
    ids = {
        c["id"] for c in client_essai.get("/api/composants", params={"ensemble": "ROBOT"}).json()
    }
    assert ids == {"ESSAI-TR-001", "ESSAI-ALI-003"}
    seul = client_essai.get(
        "/api/composants", params={"ensemble": "ROBOT", "ensemble_seul": True}
    ).json()
    assert {c["id"] for c in seul} == {"ESSAI-TR-001"}


# --- Recherche globale -----------------------------------------------------------------------


def test_recherche_tous_types(client_essai: TestClient) -> None:
    _ensemble(client_essai, "MOUSSE")
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()[
        "numero"
    ]
    groupes = {
        g["type"]: g["resultats"]
        for g in client_essai.get("/api/recherche", params={"q": "mous"}).json()
    }
    assert "Mouser" in {r["cle"] for r in groupes["fournisseur"]}
    assert numero in {r["cle"] for r in groupes["commande"]}
    assert "MOUSSE" in {r["cle"] for r in groupes["ensemble"]}
    composants = client_essai.get("/api/recherche", params={"q": "ALI-006"}).json()
    assert composants[0]["type"] == "composant"
    assert composants[0]["resultats"][0]["cle"] == "ESSAI-ALI-006"


def test_recherche_texte_trop_court(client_essai: TestClient) -> None:
    reponse = client_essai.get("/api/recherche", params={"q": " a "})
    assert reponse.status_code == 400
