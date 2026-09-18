"""Listes de valeurs paramétrables : neutralité de l'outil et gestion des valeurs."""

import sqlite3

from fastapi.testclient import TestClient

from backend import db


def _codes(conn: sqlite3.Connection, liste: str) -> set[str]:
    lignes = conn.execute("SELECT code FROM valeur_liste WHERE liste = ?", (liste,)).fetchall()
    return {ligne[0] for ligne in lignes}


def test_base_neuve_sans_vocabulaire_de_projet(conn_vide: sqlite3.Connection) -> None:
    assert _codes(conn_vide, "mode_appro") == {"Achat"}
    assert "Stock-PFM" not in _codes(conn_vide, "statut_appro")
    assert _codes(conn_vide, "type_mouvement") == {
        "Reception achat",
        "Sortie montage",
        "Retour montage",
        "Perte ou casse",
        "Inventaire",
    }


def test_import_initial_ajoute_le_vocabulaire_de_l_instance(conn_spoc: sqlite3.Connection) -> None:
    assert {"Fourni PFM", "Fourni CEA", "Fabrication PFM", "Stock ecole"} <= _codes(
        conn_spoc, "mode_appro"
    )
    sens = dict(
        conn_spoc.execute(
            "SELECT code, sens FROM valeur_liste WHERE liste = 'type_mouvement'"
        ).fetchall()
    )
    assert sens["Pret ecole"] == "Entree"
    assert sens["Retour ecole"] == "Sortie"


def test_colonne_quantite_disponible(conn_spoc: sqlite3.Connection) -> None:
    colonnes = {ligne[1] for ligne in conn_spoc.execute("PRAGMA table_info(composant)")}
    assert "qte_disponible" in colonnes
    assert "qte_dispo_ecole" not in colonnes
    pilotage = db.fetch_one(conn_spoc, "SELECT cout_ht FROM v_pilotage")
    assert pilotage is not None
    assert abs(pilotage["cout_ht"] - 3184.98) < 0.01


def test_declencheur_refuse_une_valeur_inconnue(conn_spoc: sqlite3.Connection) -> None:
    try:
        conn_spoc.execute("UPDATE composant SET mode_appro = 'Inconnu' WHERE id = 'SPOC-TR-001'")
    except sqlite3.IntegrityError as erreur:
        assert "inconnu" in str(erreur)
    else:
        raise AssertionError("valeur inconnue acceptée")


def test_ajout_renommage_et_utilisation_d_une_valeur(client_spoc: TestClient) -> None:
    reponse = client_spoc.post("/api/listes/mode_appro", json={"libelle": "Prêt fournisseur"})
    assert reponse.status_code == 201
    assert reponse.json()["code"] == "Pret fournisseur"
    modif = {"mode_appro": "Pret fournisseur"}
    assert client_spoc.patch("/api/composants/SPOC-TR-001", json=modif).status_code == 200
    renomme = client_spoc.patch(
        "/api/listes/mode_appro/Pret fournisseur", json={"libelle": "Prêté par le fournisseur"}
    )
    assert renomme.json()["libelle"] == "Prêté par le fournisseur"
    composant = client_spoc.get("/api/composants/SPOC-TR-001").json()["composant"]
    assert composant["mode_appro"] == "Pret fournisseur"
    assert composant["total_ht"] == 0


def test_valeur_desactivee_refusee_en_saisie(client_spoc: TestClient) -> None:
    client_spoc.patch("/api/listes/mode_appro/Fourni CEA", json={"actif": 0})
    reponse = client_spoc.patch("/api/composants/SPOC-TR-001", json={"mode_appro": "Fourni CEA"})
    assert reponse.status_code == 400
    assert "désactivé" in reponse.json()["erreur"]
    # Le composant qui la porte déjà reste modifiable.
    reponse = client_spoc.patch("/api/composants/SPOC-IHM-001", json={"qte_besoin": 2})
    assert reponse.status_code == 200


def test_valeur_systeme_protegee(client_spoc: TestClient) -> None:
    assert client_spoc.delete("/api/listes/mode_appro/Achat").status_code == 400
    assert client_spoc.patch("/api/listes/mode_appro/Achat", json={"actif": 0}).status_code == 400
    reponse = client_spoc.patch("/api/listes/mode_appro/Achat", json={"libelle": "Acheté"})
    assert reponse.status_code == 200


def test_suppression_refusee_si_utilisee(client_spoc: TestClient) -> None:
    reponse = client_spoc.delete("/api/listes/mode_appro/Fourni PFM")
    assert reponse.status_code == 409
    assert "désactiver" in reponse.json()["erreur"]
    assert client_spoc.delete("/api/listes/mode_appro/Stock ecole").status_code == 200


def test_nouveau_type_de_mouvement_et_son_sens(client_spoc: TestClient) -> None:
    corps = {"libelle": "Don", "sens": "Entree"}
    assert client_spoc.post("/api/listes/type_mouvement", json=corps).status_code == 201
    mouvement = {
        "date": "2026-10-01",
        "composant_id": "SPOC-TR-001",
        "type_mouvement": "Don",
        "qte": 2,
    }
    resultat = client_spoc.post("/api/mouvements", json=mouvement).json()
    assert resultat["mouvement"]["sens"] == "Entree"
    sans_sens = client_spoc.post("/api/listes/type_mouvement", json={"libelle": "Transfert"})
    assert sans_sens.status_code == 400


def test_liste_inconnue(client_spoc: TestClient) -> None:
    assert client_spoc.post("/api/listes/inconnue", json={"libelle": "x"}).status_code == 404
