"""Corbeille des documents : un fichier supprimé se retrouve après une restauration."""

from pathlib import Path

from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\n% document de test\n"
AUTRE_PDF = b"%PDF-1.4\n% autre document\n"
COMPOSANT = "ESSAI-ALI-006"


def _commande(client: TestClient) -> str:
    numero = client.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()["numero"]
    ligne = {"composant_id": COMPOSANT, "qte_commandee": 1, "pu_ht_devis": 2.0}
    assert client.post(f"/api/commandes/{numero}/lignes", json=ligne).status_code == 201
    return numero


def _deposer(client: TestClient, chemin: str, nom: str, contenu: bytes) -> None:
    reponse = client.post(
        chemin, files=[("fichiers", (nom, contenu))], data={"type_document": "Devis"}
    )
    assert reponse.status_code == 201, reponse.text


def _supprimer_commande(client: TestClient, numero: str) -> None:
    corps = {"cles": [numero], "action": "supprimer", "simuler": False}
    reponse = client.post("/api/nettoyage/commandes", json=corps)
    assert reponse.json()["supprimes"] == [numero], reponse.text


def _documents(dossier_echange: Path, sous_dossier: str) -> list[Path]:
    racine = dossier_echange / "documents" / sous_dossier
    return sorted(f for f in racine.rglob("*") if f.is_file()) if racine.is_dir() else []


def test_suppression_range_le_fichier_dans_la_corbeille(
    client_essai: TestClient, dossier_echange: Path
) -> None:
    numero = _commande(client_essai)
    _deposer(client_essai, f"/api/commandes/{numero}/documents", "devis.pdf", PDF)
    _supprimer_commande(client_essai, numero)
    assert _documents(dossier_echange, "commandes") == []
    corbeille = _documents(dossier_echange, "_corbeille")
    assert len(corbeille) == 1
    assert corbeille[0].name.endswith("_devis.pdf")
    assert corbeille[0].read_bytes() == PDF
    assert client_essai.get("/api/sauvegardes/corbeille").json()["nb_fichiers"] == 1


def test_restauration_remet_le_fichier_supprime(
    client_essai: TestClient, dossier_echange: Path
) -> None:
    numero = _commande(client_essai)
    _deposer(client_essai, f"/api/commandes/{numero}/documents", "devis.pdf", PDF)
    sauvegarde = client_essai.post("/api/sauvegardes").json()["nom"]
    _supprimer_commande(client_essai, numero)

    reponse = client_essai.post(f"/api/sauvegardes/{sauvegarde}/restaurer")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["documents"]["remis"] == ["devis.pdf"]
    assert reponse.json()["documents"]["manquants"] == []
    documents = client_essai.get(f"/api/commandes/{numero}/documents").json()
    fichier = client_essai.get(f"/api/documents/{documents[0]['id']}/fichier")
    assert fichier.status_code == 200
    assert fichier.content == PDF


def test_restauration_range_les_fichiers_inconnus_puis_les_retrouve(
    client_essai: TestClient, dossier_echange: Path
) -> None:
    avant = client_essai.post("/api/sauvegardes").json()["nom"]
    _deposer(client_essai, f"/api/composants/{COMPOSANT}/documents", "fiche.pdf", AUTRE_PDF)
    apres = client_essai.post("/api/sauvegardes").json()["nom"]

    # Retour à un état où le document n'existait pas : son fichier part à la corbeille.
    reponse = client_essai.post(f"/api/sauvegardes/{avant}/restaurer").json()
    assert reponse["documents"]["ranges_corbeille"] == 1
    assert _documents(dossier_echange, "composants") == []

    # Retour à l'état suivant : le fichier est remis en place.
    reponse = client_essai.post(f"/api/sauvegardes/{apres}/restaurer").json()
    assert reponse["documents"]["remis"] == ["fiche.pdf"]
    assert [f.read_bytes() for f in _documents(dossier_echange, "composants")] == [AUTRE_PDF]


def test_fichier_introuvable_signale(client_essai: TestClient, dossier_echange: Path) -> None:
    _deposer(client_essai, f"/api/composants/{COMPOSANT}/documents", "fiche.pdf", PDF)
    sauvegarde = client_essai.post("/api/sauvegardes").json()["nom"]
    for fichier in _documents(dossier_echange, "composants"):
        fichier.unlink()
    reponse = client_essai.post(f"/api/sauvegardes/{sauvegarde}/restaurer").json()
    assert [m["nom"] for m in reponse["documents"]["manquants"]] == ["fiche.pdf"]


def test_vider_la_corbeille(client_essai: TestClient, dossier_echange: Path) -> None:
    numero = _commande(client_essai)
    _deposer(client_essai, f"/api/commandes/{numero}/documents", "devis.pdf", PDF)
    _supprimer_commande(client_essai, numero)

    reponse = client_essai.post("/api/sauvegardes/corbeille/vider")
    assert reponse.json()["effaces"] == 1
    assert _documents(dossier_echange, "_corbeille") == []
    journal = client_essai.get("/api/journal", params={"table_cible": "document"}).json()
    assert any(j["champ"] == "corbeille videe" for j in journal)
