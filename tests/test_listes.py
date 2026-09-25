"""Listes de valeurs paramétrables : neutralité de l'outil et gestion des valeurs."""

import sqlite3

from fastapi.testclient import TestClient

from backend import db


def _codes(conn: sqlite3.Connection, liste: str) -> set[str]:
    lignes = conn.execute("SELECT code FROM valeur_liste WHERE liste = ?", (liste,)).fetchall()
    return {ligne[0] for ligne in lignes}


def test_base_neuve_sans_vocabulaire_de_projet(conn_vide: sqlite3.Connection) -> None:
    assert _codes(conn_vide, "mode_appro") == {"Achat"}
    assert "Stock atelier" not in _codes(conn_vide, "statut_appro")
    assert _codes(conn_vide, "type_mouvement") == {
        "Reception achat",
        "Sortie montage",
        "Retour montage",
        "Perte ou casse",
        "Inventaire",
    }


def test_colonne_quantite_disponible(conn_essai: sqlite3.Connection) -> None:
    colonnes = {ligne[1] for ligne in conn_essai.execute("PRAGMA table_info(composant)")}
    assert "qte_disponible" in colonnes
    assert "qte_dispo_ecole" not in colonnes
    pilotage = db.fetch_one(conn_essai, "SELECT cout_ht FROM v_pilotage")
    assert pilotage is not None
    assert abs(pilotage["cout_ht"] - 3184.98) < 0.01


def test_declencheur_refuse_une_valeur_inconnue(conn_essai: sqlite3.Connection) -> None:
    try:
        conn_essai.execute("UPDATE composant SET mode_appro = 'Inconnu' WHERE id = 'ESSAI-TR-001'")
    except sqlite3.IntegrityError as erreur:
        assert "inconnu" in str(erreur)
    else:
        raise AssertionError("valeur inconnue acceptée")


def test_ajout_renommage_et_utilisation_d_une_valeur(client_essai: TestClient) -> None:
    reponse = client_essai.post("/api/listes/mode_appro", json={"libelle": "Prêt fournisseur"})
    assert reponse.status_code == 201
    assert reponse.json()["code"] == "Pret fournisseur"
    modif = {"mode_appro": "Pret fournisseur"}
    assert client_essai.patch("/api/composants/ESSAI-TR-001", json=modif).status_code == 200
    renomme = client_essai.patch(
        "/api/listes/mode_appro/Pret fournisseur", json={"libelle": "Prêté par le fournisseur"}
    )
    assert renomme.json()["libelle"] == "Prêté par le fournisseur"
    composant = client_essai.get("/api/composants/ESSAI-TR-001").json()["composant"]
    assert composant["mode_appro"] == "Pret fournisseur"
    assert composant["total_ht"] == 0


def test_valeur_desactivee_refusee_en_saisie(client_essai: TestClient) -> None:
    client_essai.patch("/api/listes/mode_appro/Fourni partenaire", json={"actif": 0})
    reponse = client_essai.patch(
        "/api/composants/ESSAI-TR-001", json={"mode_appro": "Fourni partenaire"}
    )
    assert reponse.status_code == 400
    assert "désactivé" in reponse.json()["erreur"]
    # Le composant qui la porte déjà reste modifiable.
    reponse = client_essai.patch("/api/composants/ESSAI-IHM-001", json={"qte_besoin": 2})
    assert reponse.status_code == 200


def test_valeur_systeme_protegee(client_essai: TestClient) -> None:
    assert client_essai.delete("/api/listes/mode_appro/Achat").status_code == 400
    assert client_essai.patch("/api/listes/mode_appro/Achat", json={"actif": 0}).status_code == 400
    reponse = client_essai.patch("/api/listes/mode_appro/Achat", json={"libelle": "Acheté"})
    assert reponse.status_code == 200


def test_suppression_refusee_si_utilisee(client_essai: TestClient) -> None:
    reponse = client_essai.delete("/api/listes/mode_appro/Fourni atelier")
    assert reponse.status_code == 409
    assert "désactiver" in reponse.json()["erreur"]
    assert client_essai.delete("/api/listes/mode_appro/Stock interne").status_code == 200


def test_nouveau_type_de_mouvement_et_son_sens(client_essai: TestClient) -> None:
    corps = {"libelle": "Don", "sens": "Entree"}
    assert client_essai.post("/api/listes/type_mouvement", json=corps).status_code == 201
    mouvement = {
        "date": "2026-10-01",
        "composant_id": "ESSAI-TR-001",
        "type_mouvement": "Don",
        "qte": 2,
    }
    resultat = client_essai.post("/api/mouvements", json=mouvement).json()
    assert resultat["mouvement"]["sens"] == "Entree"
    sans_sens = client_essai.post("/api/listes/type_mouvement", json={"libelle": "Transfert"})
    assert sans_sens.status_code == 400


def test_liste_inconnue(client_essai: TestClient) -> None:
    assert client_essai.post("/api/listes/inconnue", json={"libelle": "x"}).status_code == 404
