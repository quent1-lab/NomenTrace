"""Tests de l'écran Paramètres : projet, blocs, fournisseurs, sauvegardes et restauration."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import modeles, sauvegardes

# --- Paramètres du projet ---------------------------------------------------------------


def test_parametres_modifiables_et_journalises(client: TestClient) -> None:
    reponse = client.patch(
        "/api/parametres",
        json={
            "nom_projet": "Robot",
            "prefixe_id": "ROB",
            "budget_ht": 1500,
            "taux_tva_defaut": 0.2,
        },
    )
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["nom_projet"] == "Robot"
    assert client.get("/api/sante").json()["nom_projet"] == "Robot"
    journal = client.get("/api/journal?table_cible=parametre").json()
    assert {ligne["cle_cible"] for ligne in journal} >= {"nom_projet", "prefixe_id", "budget_ht"}


@pytest.mark.parametrize(
    "corps",
    [
        {"prefixe_id": "rob"},
        {"prefixe_id": "AB-CD"},
        {"budget_ht": -1},
        {"taux_tva_defaut": 20},
        {"nom_projet": ""},
        {"inconnu": 1},
    ],
)
def test_parametres_invalides_refuses(client: TestClient, corps: dict) -> None:
    reponse = client.patch("/api/parametres", json=corps)
    assert reponse.status_code == 422
    assert "erreur" in reponse.json()


# --- Blocs ------------------------------------------------------------------------------


def test_creation_bloc_puis_identifiant(client: TestClient) -> None:
    client.patch("/api/parametres", json={"prefixe_id": "ROB"})
    reponse = client.post("/api/blocs", json={"code": "MEC", "nom": "Mécanique"})
    assert reponse.status_code == 201, reponse.text
    assert reponse.json()["ordre"] == 1
    second = client.post("/api/blocs", json={"code": "ELEC", "nom": "Électronique"}).json()
    assert second["ordre"] == 2
    assert client.get("/api/blocs/MEC/prochain-id").json() == {"id": "ROB-MEC-001"}


@pytest.mark.parametrize("code", ["M", "MECAN", "mec", "ME1", "M-E"])
def test_code_bloc_invalide_refuse(client: TestClient, code: str) -> None:
    reponse = client.post("/api/blocs", json={"code": code, "nom": "Essai"})
    assert reponse.status_code == 422


def test_code_bloc_en_double_refuse(client: TestClient) -> None:
    assert client.post("/api/blocs", json={"code": "MEC", "nom": "A"}).status_code == 201
    reponse = client.post("/api/blocs", json={"code": "MEC", "nom": "B"})
    assert reponse.status_code == 409
    assert "déjà utilisé" in reponse.json()["erreur"]


def test_code_bloc_non_modifiable(client: TestClient) -> None:
    client.post("/api/blocs", json={"code": "MEC", "nom": "A"})
    assert client.patch("/api/blocs/MEC", json={"code": "MAC"}).status_code == 422


# --- Fournisseurs -----------------------------------------------------------------------


def test_fournisseur_renomme_en_cascade(client_spoc: TestClient) -> None:
    avant = client_spoc.get("/api/composants?fournisseur=Farnell").json()
    nb = next(f for f in client_spoc.get("/api/fournisseurs").json() if f["nom"] == "Farnell")
    assert nb["nb_composants"] == len(avant) > 0
    reponse = client_spoc.patch("/api/fournisseurs/Farnell", json={"nom": "Farnell FR"})
    assert reponse.status_code == 200, reponse.text
    apres = client_spoc.get("/api/composants", params={"fournisseur": "Farnell FR"}).json()
    assert [c["id"] for c in apres] == [c["id"] for c in avant]


def test_fournisseur_archive_puis_reactive(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Atelier", "pays": "France"})
    assert client.delete("/api/fournisseurs/Atelier").status_code == 200
    assert all(f["nom"] != "Atelier" for f in client.get("/api/fournisseurs").json())
    reponse = client.post("/api/fournisseurs", json={"nom": "Atelier", "delai_moyen_j": 5})
    assert reponse.status_code == 201, reponse.text
    assert reponse.json()["archive"] == 0
    assert reponse.json()["pays"] == "France"
    assert reponse.json()["delai_moyen_j"] == 5
    assert client.post("/api/fournisseurs", json={"nom": "Atelier"}).status_code == 409


def test_fournisseur_inconnu(client: TestClient) -> None:
    assert client.delete("/api/fournisseurs/Personne").status_code == 404


# --- Sauvegardes et restauration --------------------------------------------------------


def test_sauvegarde_immediate_listee(client: TestClient) -> None:
    avant = client.get("/api/sauvegardes").json()
    reponse = client.post("/api/sauvegardes")
    assert reponse.status_code == 201
    liste = client.get("/api/sauvegardes").json()
    assert len(liste) == len(avant) + 1
    assert liste[0]["nom"] == reponse.json()["nom"]
    assert liste[0]["taille"] > 0


def test_restauration_remet_l_etat_et_garde_l_etat_courant(client: TestClient) -> None:
    client.patch("/api/parametres", json={"nom_projet": "Avant"})
    nom = client.post("/api/sauvegardes").json()["nom"]
    client.patch("/api/parametres", json={"nom_projet": "Après"})

    reponse = client.post(f"/api/sauvegardes/{nom}/restaurer")
    assert reponse.status_code == 200, reponse.text
    assert client.get("/api/parametres").json()["nom_projet"] == "Avant"

    # L'état écrasé a été sauvegardé juste avant : on peut revenir en arrière.
    securite = reponse.json()["securite"]
    assert client.post(f"/api/sauvegardes/{securite}/restaurer").status_code == 200
    assert client.get("/api/parametres").json()["nom_projet"] == "Après"


@pytest.mark.parametrize("nom", ["test.db", "nomentrace_20250101_000000.db"])
def test_restauration_nom_invalide_ou_absent(client: TestClient, nom: str) -> None:
    reponse = client.post(f"/api/sauvegardes/{nom}/restaurer")
    assert reponse.status_code == 404
    assert "erreur" in reponse.json()


def _base_version(chemin: Path, version: int, migrations: Path) -> None:
    """Base au schéma arrêté à une version donnée, avec un paramètre reconnaissable."""
    migrations.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= version:
            (migrations / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(chemin)
    try:
        db.apply_migrations(conn, migrations)
        conn.execute("INSERT INTO parametre (cle, valeur) VALUES ('nom_projet', 'Ancien')")
        conn.commit()
    finally:
        conn.close()


def test_restauration_ancienne_version_recoit_les_migrations(tmp_path: Path) -> None:
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    _base_version(dossier / "nomentrace_20240101_120000.db", 5, tmp_path / "migrations")
    base = tmp_path / "base.db"
    conn = db.connect(base)
    derniere = db.apply_migrations(conn)
    conn.close()

    resultat = sauvegardes.restore_sauvegarde(base, dossier, "nomentrace_20240101_120000.db")

    assert resultat["version_sauvegarde"] == 5
    assert resultat["version_schema"] == derniere
    conn = db.connect(base)
    try:
        assert db.get_version_schema(conn) == derniere
        assert conn.execute("SELECT COUNT(*) FROM valeur_liste").fetchone()[0] > 0
        valeur = conn.execute("SELECT valeur FROM parametre WHERE cle = 'nom_projet'").fetchone()
        assert valeur[0] == "Ancien"
    finally:
        conn.close()


def test_restauration_de_la_plus_ancienne_malgre_la_rotation(tmp_path: Path) -> None:
    """Bug évité : la sauvegarde de sécurité purgeait la sauvegarde en cours de restauration."""
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    base = tmp_path / "base.db"
    conn = db.connect(base)
    db.apply_migrations(conn)
    conn.close()
    for rang in range(sauvegardes.NB_CONSERVEES):
        cible = dossier / f"nomentrace_2024010{rang // 10}_12{rang % 10:02d}00.db"
        copie = sqlite3.connect(cible)
        sauvegardes._copier(base, copie)
        copie.close()
    plus_ancienne = sauvegardes.list_sauvegardes(dossier)[-1].name

    sauvegardes.restore_sauvegarde(base, dossier, plus_ancienne)

    assert not (dossier / plus_ancienne).exists()  # purgée par la rotation…
    conn = db.connect(base)
    assert db.get_version_schema(conn) > 0  # … mais restaurée intacte.
    conn.close()


def test_restauration_refuse_un_fichier_non_nomentrace(tmp_path: Path) -> None:
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    (dossier / "nomentrace_20240101_120000.db").write_bytes(b"pas une base")
    base = tmp_path / "base.db"
    conn = db.connect(base)
    db.apply_migrations(conn)
    conn.close()
    with pytest.raises(ErreurMetier):
        sauvegardes.restore_sauvegarde(base, dossier, "nomentrace_20240101_120000.db")
    with pytest.raises(Introuvable):
        sauvegardes.restore_sauvegarde(base, dossier, "../base.db")


def test_restauration_refuse_un_schema_plus_recent(tmp_path: Path) -> None:
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    futur = dossier / "nomentrace_20240101_120000.db"
    conn = db.connect(futur)
    db.apply_migrations(conn)
    conn.execute("INSERT INTO schema_version (numero) VALUES (999)")
    conn.commit()
    conn.close()
    base = tmp_path / "base.db"
    with pytest.raises(ErreurMetier, match="plus récente"):
        sauvegardes.restore_sauvegarde(base, dossier, futur.name)


def test_deux_sauvegardes_dans_la_meme_seconde(tmp_path: Path) -> None:
    base = tmp_path / "base.db"
    conn = db.connect(base)
    db.apply_migrations(conn)
    conn.close()
    premiere = sauvegardes.create_sauvegarde(base, tmp_path / "s")
    seconde = sauvegardes.create_sauvegarde(base, tmp_path / "s")
    assert premiere != seconde
    assert len(sauvegardes.list_sauvegardes(tmp_path / "s")) == 2


# --- Modèles Excel ----------------------------------------------------------------------


def test_modele_verrouille_enregistre_a_cote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug évité : un modèle du jour ouvert dans Excel faisait échouer le téléchargement."""
    enregistrements: list[str] = []

    def enregistrer(_: Workbook, chemin: Path) -> None:
        enregistrements.append(Path(chemin).name)
        if len(enregistrements) == 1:
            raise PermissionError("fichier ouvert")

    monkeypatch.setattr(Workbook, "save", enregistrer)
    chemin = modeles._enregistrer(Workbook(), tmp_path, "bloc", "MEC")
    assert len(enregistrements) == 2
    assert chemin.name == enregistrements[1] != enregistrements[0]
