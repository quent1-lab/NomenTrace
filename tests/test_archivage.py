"""Archiver et désarchiver un composant, un ensemble, une commande, un fournisseur ; documents
échangés en base64 (assistant IA)."""

import base64

from fastapi.testclient import TestClient

from backend.services import documents

PDF = b"%PDF-1.4\n% fiche technique de test\n"


def _ids_composants(client: TestClient) -> set[str]:
    return {c["id"] for c in client.get("/api/composants").json()}


def test_composant_archive_puis_desarchive(client_essai: TestClient) -> None:
    cout_avant = client_essai.get("/api/pilotage").json()["cout_ht"]
    assert client_essai.post("/api/composants/ESSAI-ALI-001/archiver").status_code == 200
    assert "ESSAI-ALI-001" not in _ids_composants(client_essai)
    fiche = client_essai.get("/api/composants/ESSAI-ALI-001").json()["composant"]
    assert fiche["archive"] == 1 and fiche["archive_le"] is not None

    reponse = client_essai.post("/api/composants/ESSAI-ALI-001/desarchiver")
    assert reponse.status_code == 200, reponse.text
    assert "ESSAI-ALI-001" in _ids_composants(client_essai)
    assert abs(client_essai.get("/api/pilotage").json()["cout_ht"] - cout_avant) < 0.01
    journal = client_essai.get(
        "/api/journal", params={"cle_cible": "ESSAI-ALI-001", "table_cible": "composant"}
    ).json()
    assert [(j["champ"], j["nouvelle_valeur"]) for j in journal[:2]] == [
        ("archive", "0"),
        ("archive", "1"),
    ]


def test_desarchiver_un_composant_actif_refuse(client_essai: TestClient) -> None:
    reponse = client_essai.post("/api/composants/ESSAI-ALI-001/desarchiver")
    assert reponse.status_code == 409
    assert "n'est pas archivé" in reponse.json()["erreur"]


def test_composant_reclasse_reste_archive(client_essai: TestClient) -> None:
    nouveau = client_essai.post(
        "/api/composants/ESSAI-ALI-002/reclasser", json={"bloc_code": "TR"}
    ).json()
    reponse = client_essai.post("/api/composants/ESSAI-ALI-002/desarchiver")
    assert reponse.status_code == 409
    assert nouveau["id"] in reponse.json()["erreur"]


def test_composant_d_un_bloc_archive_refuse(client_essai: TestClient) -> None:
    client_essai.post("/api/composants/ESSAI-ALI-003/archiver")
    # Le bloc ne s'archive qu'une fois vide : on archive tous ses composants.
    for identifiant in [c["id"] for c in client_essai.get("/api/composants").json()]:
        if identifiant.startswith("ESSAI-ALI-"):
            client_essai.post(f"/api/composants/{identifiant}/archiver")
    assert client_essai.patch("/api/blocs/ALI", json={"archive": 1}).status_code == 200
    reponse = client_essai.post("/api/composants/ESSAI-ALI-003/desarchiver")
    assert reponse.status_code == 409
    assert "bloc" in reponse.json()["erreur"]


def test_ensemble_archive_lisible_puis_desarchive(client_essai: TestClient) -> None:
    client_essai.post("/api/ensembles", json={"code": "PARENT", "nom": "Parent"})
    client_essai.post(
        "/api/ensembles", json={"code": "ENFANT", "nom": "Enfant", "parent_code": "PARENT"}
    )
    assert client_essai.post("/api/ensembles/ENFANT/archiver").status_code == 200
    assert client_essai.post("/api/ensembles/PARENT/archiver").status_code == 200
    lu = client_essai.get("/api/ensembles/ENFANT").json()
    assert lu["archive"] == 1 and lu["archive_le"] is not None

    reponse = client_essai.post("/api/ensembles/ENFANT/desarchiver")
    assert reponse.status_code == 409 and "PARENT" in reponse.json()["erreur"]
    assert client_essai.post("/api/ensembles/PARENT/desarchiver").status_code == 200
    assert client_essai.post("/api/ensembles/ENFANT/desarchiver").status_code == 200
    assert client_essai.get("/api/ensembles/ENFANT").json()["archive"] == 0


def test_commande_archivee_lisible_puis_desarchivee(client_essai: TestClient) -> None:
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()[
        "numero"
    ]
    assert client_essai.post(f"/api/commandes/{numero}/archiver").status_code == 200
    lue = client_essai.get(f"/api/commandes/{numero}").json()
    assert lue["archive"] == 1 and lue["fournisseur_nom"] == "Mouser"
    assert numero not in {c["numero"] for c in client_essai.get("/api/commandes").json()}
    assert client_essai.post(f"/api/commandes/{numero}/desarchiver").status_code == 200
    assert numero in {c["numero"] for c in client_essai.get("/api/commandes").json()}


def test_fournisseur_desarchive(client_essai: TestClient) -> None:
    client_essai.post("/api/fournisseurs", json={"nom": "Atelier voisin"})
    assert client_essai.post("/api/fournisseurs/Atelier voisin/archiver").status_code == 200
    fiche = client_essai.get("/api/fournisseurs/Atelier voisin").json()
    assert fiche["archive"] == 1 and fiche["archive_le"] is not None
    assert client_essai.post("/api/fournisseurs/Atelier voisin/desarchiver").status_code == 200
    noms = {f["nom"] for f in client_essai.get("/api/fournisseurs").json()}
    assert "Atelier voisin" in noms


# --- Documents en base64 ------------------------------------------------------------------------


def _joindre(client: TestClient, contenu: bytes, nom: str = "Fiche.pdf"):
    corps = {
        "nom": nom,
        "type_document": "Fiche technique",
        "contenu_base64": base64.b64encode(contenu).decode(),
    }
    return client.post("/api/composants/ESSAI-ALI-001/documents/contenu", json=corps)


def test_document_joint_et_relu_en_base64(client_essai: TestClient) -> None:
    reponse = _joindre(client_essai, PDF)
    assert reponse.status_code == 201, reponse.text
    identifiant = reponse.json()["id"]
    lu = client_essai.get(f"/api/documents/{identifiant}/contenu").json()
    assert base64.b64decode(lu["contenu_base64"]) == PDF
    assert lu["nom_origine"] == "Fiche.pdf" and lu["type_mime"] == "application/pdf"
    assert client_essai.get(f"/api/documents/{identifiant}/fichier").content == PDF


def test_document_base64_plafonne(client_essai: TestClient) -> None:
    plafond = documents.TAILLE_MAX_CONTENU_MO * 1024 * 1024
    reponse = _joindre(client_essai, b"%PDF" + b"0" * plafond)
    assert reponse.status_code == 400
    assert "5 Mo" in reponse.json()["erreur"]
    assert _joindre(client_essai, b"%PDF" + b"0" * (plafond - 8)).status_code == 201


def test_document_base64_invalide(client_essai: TestClient) -> None:
    corps = {"nom": "x.pdf", "type_document": "Fiche technique", "contenu_base64": "pas du base64!"}
    reponse = client_essai.post("/api/composants/ESSAI-ALI-001/documents/contenu", json=corps)
    assert reponse.status_code == 400
    assert "base64" in reponse.json()["erreur"]


def test_document_trop_lourd_pour_la_lecture(client_essai: TestClient) -> None:
    plafond = documents.TAILLE_MAX_CONTENU_MO * 1024 * 1024
    reponse = client_essai.post(
        "/api/composants/ESSAI-ALI-001/documents",
        files=[("fichiers", ("Gros.pdf", b"%PDF" + b"0" * plafond))],
        data={"type_document": "Fiche technique"},
    )
    assert reponse.status_code == 201, reponse.text
    identifiant = reponse.json()["documents"][0]["id"]
    lu = client_essai.get(f"/api/documents/{identifiant}/contenu")
    assert lu.status_code == 400 and "interface" in lu.json()["erreur"]
