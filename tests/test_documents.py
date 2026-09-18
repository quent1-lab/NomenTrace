"""Documents joints : dépôt, consultation depuis la commande et depuis le composant."""

from pathlib import Path

from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\n% devis de test\n"


def _commande_avec_ligne(client: TestClient, composant: str = "SPOC-TR-001") -> str:
    numero = client.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()["numero"]
    ligne = {"composant_id": composant, "qte_commandee": 4, "pu_ht_devis": 1.13}
    client.post(f"/api/commandes/{numero}/lignes", json=ligne)
    return numero


def _deposer(client: TestClient, chemin: str, fichiers: list[tuple[str, bytes]], type_doc: str):
    return client.post(
        chemin,
        files=[("fichiers", (nom, contenu)) for nom, contenu in fichiers],
        data={"type_document": type_doc},
    )


def test_devis_joint_a_une_commande(client_spoc: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_spoc)
    reponse = _deposer(
        client_spoc, f"/api/commandes/{numero}/documents", [("Devis Mouser.pdf", PDF)], "Devis"
    )
    assert reponse.status_code == 201
    document = reponse.json()["documents"][0]
    assert document["chemin"] == f"commandes/{numero}/Devis_Mouser.pdf"
    assert (dossier_echange / "documents" / document["chemin"]).read_bytes() == PDF
    fichier = client_spoc.get(f"/api/documents/{document['id']}/fichier")
    assert fichier.content == PDF
    assert fichier.headers["content-type"] == "application/pdf"
    assert fichier.headers["content-disposition"].startswith("inline")


def test_composant_voit_les_devis_de_ses_commandes(client_spoc: TestClient) -> None:
    numero = _commande_avec_ligne(client_spoc, "SPOC-TR-001")
    _deposer(client_spoc, f"/api/commandes/{numero}/documents", [("devis.pdf", PDF)], "Devis")
    fiche = b"%PDF-1.4\n% fiche technique\n"
    _deposer(
        client_spoc,
        "/api/composants/SPOC-TR-001/documents",
        [("mcp2562.pdf", fiche)],
        "Fiche technique",
    )
    liste = client_spoc.get("/api/composants/SPOC-TR-001/documents").json()
    assert [(d["source"], d["type_document"]) for d in liste] == [
        ("composant", "Fiche technique"),
        ("commande", "Devis"),
    ]
    assert liste[1]["commande_numero"] == numero
    assert client_spoc.get("/api/composants/SPOC-ALI-001/documents").json() == []


def test_doublon_refuse_et_autres_fichiers_joints(client_spoc: TestClient) -> None:
    numero = _commande_avec_ligne(client_spoc)
    chemin = f"/api/commandes/{numero}/documents"
    _deposer(client_spoc, chemin, [("devis.pdf", PDF)], "Devis")
    reponse = _deposer(
        client_spoc, chemin, [("copie.pdf", PDF), ("bl.pdf", b"%PDF autre")], "Bon de livraison"
    )
    assert reponse.status_code == 201
    resultat = reponse.json()
    assert [d["nom_origine"] for d in resultat["documents"]] == ["bl.pdf"]
    assert "déjà joint" in resultat["erreurs"][0]


def test_extension_refusee(client_spoc: TestClient) -> None:
    numero = _commande_avec_ligne(client_spoc)
    reponse = _deposer(
        client_spoc, f"/api/commandes/{numero}/documents", [("script.exe", b"MZ")], "Autre"
    )
    assert reponse.status_code == 400
    assert "non accepté" in reponse.json()["erreur"]


def test_nom_de_fichier_assaini(client_spoc: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_spoc)
    reponse = _deposer(
        client_spoc,
        f"/api/commandes/{numero}/documents",
        [("..\\..\\évil devis.pdf", PDF)],
        "Devis",
    )
    document = reponse.json()["documents"][0]
    assert document["chemin"] == f"commandes/{numero}/evil_devis.pdf"
    assert (dossier_echange / "documents" / document["chemin"]).is_file()


def test_meme_nom_suffixe(client_spoc: TestClient) -> None:
    numero = _commande_avec_ligne(client_spoc)
    chemin = f"/api/commandes/{numero}/documents"
    _deposer(client_spoc, chemin, [("devis.pdf", PDF)], "Devis")
    reponse = _deposer(client_spoc, chemin, [("devis.pdf", b"%PDF version 2")], "Devis")
    assert reponse.json()["documents"][0]["chemin"].endswith("devis-2.pdf")


def test_retrait_archive_le_document(client_spoc: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_spoc)
    document = _deposer(
        client_spoc, f"/api/commandes/{numero}/documents", [("devis.pdf", PDF)], "Devis"
    ).json()["documents"][0]
    assert client_spoc.delete(f"/api/documents/{document['id']}").status_code == 200
    assert client_spoc.get(f"/api/commandes/{numero}/documents").json() == []
    assert (dossier_echange / "documents" / document["chemin"]).is_file()
    assert client_spoc.get(f"/api/documents/{document['id']}/fichier").status_code == 404


def test_cible_inconnue(client_spoc: TestClient) -> None:
    reponse = _deposer(
        client_spoc, "/api/commandes/CMD-999/documents", [("devis.pdf", PDF)], "Devis"
    )
    assert reponse.status_code == 404


def test_type_de_document_modifiable(client_spoc: TestClient) -> None:
    numero = _commande_avec_ligne(client_spoc)
    document = _deposer(
        client_spoc, f"/api/commandes/{numero}/documents", [("piece.pdf", PDF)], "Autre"
    ).json()["documents"][0]
    reponse = client_spoc.patch(
        f"/api/documents/{document['id']}", json={"type_document": "Facture"}
    )
    assert reponse.json()["type_document"] == "Facture"
