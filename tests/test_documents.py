"""Documents joints : dépôt, consultation depuis la commande et depuis le composant."""

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\n% devis de test\n"


def _commande_avec_ligne(client: TestClient, composant: str = "ESSAI-TR-001") -> str:
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


def test_devis_joint_a_une_commande(client_essai: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_essai)
    reponse = _deposer(
        client_essai, f"/api/commandes/{numero}/documents", [("Devis Mouser.pdf", PDF)], "Devis"
    )
    assert reponse.status_code == 201
    document = reponse.json()["documents"][0]
    assert document["chemin"] == f"commandes/{numero}/Devis_Mouser.pdf"
    assert (dossier_echange / "documents" / document["chemin"]).read_bytes() == PDF
    fichier = client_essai.get(f"/api/documents/{document['id']}/fichier")
    assert fichier.content == PDF
    assert fichier.headers["content-type"] == "application/pdf"
    assert fichier.headers["content-disposition"].startswith("inline")


def test_composant_voit_les_devis_de_ses_commandes(client_essai: TestClient) -> None:
    numero = _commande_avec_ligne(client_essai, "ESSAI-TR-001")
    _deposer(client_essai, f"/api/commandes/{numero}/documents", [("devis.pdf", PDF)], "Devis")
    fiche = b"%PDF-1.4\n% fiche technique\n"
    _deposer(
        client_essai,
        "/api/composants/ESSAI-TR-001/documents",
        [("mcp2562.pdf", fiche)],
        "Fiche technique",
    )
    liste = client_essai.get("/api/composants/ESSAI-TR-001/documents").json()
    assert [(d["source"], d["type_document"]) for d in liste] == [
        ("composant", "Fiche technique"),
        ("commande", "Devis"),
    ]
    assert liste[1]["commande_numero"] == numero
    assert client_essai.get("/api/composants/ESSAI-ALI-001/documents").json() == []


def test_doublon_refuse_et_autres_fichiers_joints(client_essai: TestClient) -> None:
    numero = _commande_avec_ligne(client_essai)
    chemin = f"/api/commandes/{numero}/documents"
    _deposer(client_essai, chemin, [("devis.pdf", PDF)], "Devis")
    reponse = _deposer(
        client_essai, chemin, [("copie.pdf", PDF), ("bl.pdf", b"%PDF autre")], "Bon de livraison"
    )
    assert reponse.status_code == 201
    resultat = reponse.json()
    assert [d["nom_origine"] for d in resultat["documents"]] == ["bl.pdf"]
    assert "déjà joint" in resultat["erreurs"][0]


def test_extension_refusee(client_essai: TestClient) -> None:
    numero = _commande_avec_ligne(client_essai)
    reponse = _deposer(
        client_essai, f"/api/commandes/{numero}/documents", [("script.exe", b"MZ")], "Autre"
    )
    assert reponse.status_code == 400
    assert "non accepté" in reponse.json()["erreur"]


def test_nom_de_fichier_assaini(client_essai: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_essai)
    reponse = _deposer(
        client_essai,
        f"/api/commandes/{numero}/documents",
        [("..\\..\\évil devis.pdf", PDF)],
        "Devis",
    )
    document = reponse.json()["documents"][0]
    assert document["chemin"] == f"commandes/{numero}/evil_devis.pdf"
    assert (dossier_echange / "documents" / document["chemin"]).is_file()


def test_meme_nom_suffixe(client_essai: TestClient) -> None:
    numero = _commande_avec_ligne(client_essai)
    chemin = f"/api/commandes/{numero}/documents"
    _deposer(client_essai, chemin, [("devis.pdf", PDF)], "Devis")
    reponse = _deposer(client_essai, chemin, [("devis.pdf", b"%PDF version 2")], "Devis")
    assert reponse.json()["documents"][0]["chemin"].endswith("devis-2.pdf")


def test_retrait_archive_le_document(client_essai: TestClient, dossier_echange: Path) -> None:
    numero = _commande_avec_ligne(client_essai)
    document = _deposer(
        client_essai, f"/api/commandes/{numero}/documents", [("devis.pdf", PDF)], "Devis"
    ).json()["documents"][0]
    assert client_essai.delete(f"/api/documents/{document['id']}").status_code == 200
    assert client_essai.get(f"/api/commandes/{numero}/documents").json() == []
    assert (dossier_echange / "documents" / document["chemin"]).is_file()
    assert client_essai.get(f"/api/documents/{document['id']}/fichier").status_code == 404


def test_cible_inconnue(client_essai: TestClient) -> None:
    reponse = _deposer(
        client_essai, "/api/commandes/CMD-999/documents", [("devis.pdf", PDF)], "Devis"
    )
    assert reponse.status_code == 404


def test_type_de_document_modifiable(client_essai: TestClient) -> None:
    numero = _commande_avec_ligne(client_essai)
    document = _deposer(
        client_essai, f"/api/commandes/{numero}/documents", [("piece.pdf", PDF)], "Autre"
    ).json()["documents"][0]
    reponse = client_essai.patch(
        f"/api/documents/{document['id']}", json={"type_document": "Facture"}
    )
    assert reponse.json()["type_document"] == "Facture"


def test_reclassement_emporte_les_documents_du_composant(client_essai: TestClient) -> None:
    """Bug évité : la fiche technique restait sur l'ancien identifiant, archivé, après un
    reclassement ; le remplaçant n'avait plus aucun document."""
    depot = _deposer(
        client_essai,
        "/api/composants/ESSAI-ALI-001/documents",
        [("Fiche alim.pdf", PDF)],
        "Fiche technique",
    )
    document = depot.json()["documents"][0]
    nouveau = client_essai.post(
        "/api/composants/ESSAI-ALI-001/reclasser", json={"bloc_code": "TR"}
    ).json()["id"]
    documents_nouveau = client_essai.get(f"/api/composants/{nouveau}/documents").json()
    assert [d["id"] for d in documents_nouveau] == [document["id"]]
    assert client_essai.get("/api/composants/ESSAI-ALI-001/documents").json() == []
    # Le fichier n'a pas bougé : il s'ouvre toujours.
    assert client_essai.get(f"/api/documents/{document['id']}/fichier").content == PDF
    journal = client_essai.get("/api/journal").json()
    assert any(
        ligne["table_cible"] == "document"
        and ligne["ancienne_valeur"] == "ESSAI-ALI-001"
        and ligne["nouvelle_valeur"] == nouveau
        for ligne in journal
    )


def test_mise_a_jour_rattache_les_documents_des_composants_deja_reclasses(
    tmp_path: Path,
) -> None:
    """Les composants reclassés avant ce correctif retrouvent leurs documents, au bout de la
    chaîne s'ils ont été reclassés deux fois."""
    from backend import db
    from tests.jeu_essai import charger_jeu_essai

    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= 15:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(tmp_path / "base.db")
    db.apply_migrations(conn, anciennes)
    charger_jeu_essai(conn)
    conn.execute(
        "INSERT INTO document (composant_id, type_document, nom_origine, chemin, taille,"
        " empreinte) VALUES ('ESSAI-ALI-001', 'Fiche technique', 'fiche.pdf',"
        " 'composants/ESSAI-ALI-001/fiche.pdf', 10, 'abc')"
    )
    conn.execute(
        "UPDATE composant SET remplace_par = 'ESSAI-TR-001', archive = 1 WHERE id = 'ESSAI-ALI-001'"
    )
    conn.execute(
        "UPDATE composant SET remplace_par = 'ESSAI-TR-002', archive = 1 WHERE id = 'ESSAI-TR-001'"
    )

    db.apply_migrations(conn)

    rattache = conn.execute("SELECT composant_id, chemin FROM document").fetchone()
    assert tuple(rattache) == ("ESSAI-TR-002", "composants/ESSAI-ALI-001/fiche.pdf")
    trace = conn.execute(
        "SELECT ancienne_valeur, nouvelle_valeur FROM journal WHERE table_cible = 'document'"
    ).fetchall()
    assert [tuple(t) for t in trace] == [("ESSAI-ALI-001", "ESSAI-TR-002")]
    conn.close()


def test_depot_ne_fige_pas_le_serveur(
    client_essai: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug évité : l'enregistrement des fichiers tournait dans la boucle d'événements ; un gros
    dépôt figeait le serveur pour tous les utilisateurs jusqu'à la fin."""
    from backend.services import documents

    original = documents.add_document
    commence = threading.Event()

    def lent(*args: object, **kwargs: object) -> dict:
        commence.set()
        time.sleep(1.5)
        return original(*args, **kwargs)

    monkeypatch.setattr(documents, "add_document", lent)
    transport = httpx.ASGITransport(app=client_essai.app, client=("127.0.0.1", 50001))
    fins: dict[str, float] = {}

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8000",
            headers={"Origin": "http://127.0.0.1:8000"},
        ) as client:

            async def deposer() -> None:
                reponse = await client.post(
                    "/api/composants/ESSAI-ALI-001/documents",
                    files=[("fichiers", ("fiche.pdf", PDF))],
                    data={"type_document": "Fiche technique"},
                )
                assert reponse.status_code == 201
                fins["depot"] = time.monotonic()

            async def consulter() -> None:
                # Attend que l'enregistrement ait commencé : s'il figeait la boucle, ce test
                # ne reprendrait la main qu'une fois le dépôt terminé.
                while not commence.is_set():
                    await asyncio.sleep(0.02)
                assert (await client.get("/api/sante")).status_code == 200
                fins["sante"] = time.monotonic()

            await asyncio.gather(deposer(), consulter())

    asyncio.run(scenario())
    assert fins["sante"] < fins["depot"] - 0.5
