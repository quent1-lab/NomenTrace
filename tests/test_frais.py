"""Frais de commande : livraison, douane, frais de facturation… dans les totaux et l'engagé."""

from fastapi.testclient import TestClient


def _commande_engagee(client: TestClient) -> str:
    numero = client.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()["numero"]
    ligne = {"composant_id": "ESSAI-TR-001", "qte_commandee": 2, "pu_ht_devis": 10}
    client.post(f"/api/commandes/{numero}/lignes", json=ligne)
    return numero


def test_frais_dans_le_total_et_l_engage(client_essai: TestClient) -> None:
    numero = _commande_engagee(client_essai)
    for type_frais, montant in (("Livraison", 7.5), ("Douane", 4.2), ("Facturation", 1.3)):
        cree = client_essai.post(
            f"/api/commandes/{numero}/frais", json={"type_frais": type_frais, "montant_ht": montant}
        )
        assert cree.status_code == 201, cree.text
    commande = client_essai.get(f"/api/commandes/{numero}").json()
    assert commande["montant_frais_ht"] == 13.0
    assert commande["total_ht"] == 33.0
    # Rien d'engagé tant que la commande n'est pas passée.
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 0
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == 33.0
    # Les frais ne sont pas répartis entre les blocs.
    bloc = next(b for b in client_essai.get("/api/blocs").json() if b["code"] == "TR")
    assert bloc["montant_engage_ht"] == 20.0


def test_modifier_et_retirer_un_frais(client_essai: TestClient) -> None:
    numero = _commande_engagee(client_essai)
    frais = client_essai.post(
        f"/api/commandes/{numero}/frais", json={"type_frais": "Livraison", "montant_ht": 5}
    ).json()
    assert (
        client_essai.patch(f"/api/frais/{frais['id']}", json={"montant_ht": 6}).json()["montant_ht"]
        == 6
    )
    liste = client_essai.get(f"/api/commandes/{numero}/frais").json()
    assert liste[0]["type_libelle"] == "Livraison"
    assert client_essai.delete(f"/api/frais/{frais['id']}").status_code == 200
    assert client_essai.get(f"/api/commandes/{numero}").json()["montant_frais_ht"] == 0
    journal = client_essai.get("/api/journal").json()
    assert any(ligne["table_cible"] == "frais_commande" for ligne in journal)


def test_type_de_frais_inconnu_ou_desactive_refuse(client_essai: TestClient) -> None:
    numero = _commande_engagee(client_essai)
    inconnu = {"type_frais": "Pourboire", "montant_ht": 1}
    assert client_essai.post(f"/api/commandes/{numero}/frais", json=inconnu).status_code == 400
    client_essai.patch("/api/listes/type_frais/Dossier", json={"actif": 0})
    desactive = {"type_frais": "Dossier", "montant_ht": 1}
    assert client_essai.post(f"/api/commandes/{numero}/frais", json=desactive).status_code == 400


def test_suppression_d_une_commande_emporte_ses_frais(client_essai: TestClient) -> None:
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()[
        "numero"
    ]
    client_essai.post(
        f"/api/commandes/{numero}/frais", json={"type_frais": "Douane", "montant_ht": 2}
    )
    reponse = client_essai.post(
        "/api/nettoyage/commandes", json={"cles": [numero], "action": "supprimer", "simuler": False}
    )
    assert reponse.status_code == 200, reponse.text
    assert client_essai.get(f"/api/commandes/{numero}").status_code == 404
