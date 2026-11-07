"""Composants vendus par lot : besoin et stock en pièces, achat en lots entiers au prix du
lot, coût d'un ensemble en pièces au prix de la pièce (ACH-08)."""

import pytest
from fastapi.testclient import TestClient

FOURNISSEUR = "Amazon / StepperOnline"
VIS = {
    "bloc_code": "ALI",
    "fonction": "Fixation",
    "designation": "Vis M3x8, sachet de 100",
    "mode_appro": "Achat",
    "fournisseur_nom": FOURNISSEUR,
    "qte_besoin": 230,
    "qte_par_lot": 100,
    "pu_releve": 12.0,
    "base_prix_releve": "HT",
}


def _creer(client: TestClient, **valeurs: object) -> str:
    reponse = client.post("/api/composants", json={**VIS, **valeurs})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def _composant(client: TestClient, identifiant: str) -> dict:
    return client.get(f"/api/composants/{identifiant}").json()["composant"]


def _commande_passee(client: TestClient, vis: str) -> tuple[str, dict]:
    """Demande de devis, prix du devis saisi, commande passée ; renvoie numéro et ligne."""
    demandes = client.post("/api/demandes-devis", json={"composants": [vis]})
    assert demandes.status_code == 201, demandes.text
    numero = demandes.json()[0]["numero"]
    ligne = client.get(f"/api/commandes/{numero}/lignes").json()[0]
    client.patch(f"/api/commandes/{numero}/lignes/{ligne['id']}", json={"pu_ht_devis": 12.0})
    assert client.patch(f"/api/commandes/{numero}", json={"statut": "Commande"}).status_code == 200
    return numero, client.get(f"/api/commandes/{numero}/lignes").json()[0]


def test_achat_arrondi_au_lot_entier(client_essai: TestClient) -> None:
    vis = _composant(client_essai, _creer(client_essai))
    assert vis["qte_par_lot"] == 100
    assert vis["qte_a_acheter"] == 230
    assert vis["nb_lots_a_acheter"] == 3
    assert vis["prix_lot_ht"] == pytest.approx(12.0)
    assert vis["pu_ht"] == pytest.approx(0.12)
    assert vis["total_ht"] == pytest.approx(36.0)
    assert vis["total_ttc"] == pytest.approx(43.2)


def test_lot_de_un_par_defaut(client_essai: TestClient) -> None:
    sans_lot = {k: v for k, v in VIS.items() if k != "qte_par_lot"}
    reponse = client_essai.post("/api/composants", json={**sans_lot, "pu_releve": 0.15})
    vis = _composant(client_essai, reponse.json()["id"])
    assert vis["qte_par_lot"] == 1
    assert vis["nb_lots_a_acheter"] == 230
    assert vis["total_ht"] == pytest.approx(34.5)


@pytest.mark.parametrize("taille", [0, -3])
def test_lot_vide_refuse(client_essai: TestClient, taille: int) -> None:
    assert (
        client_essai.post("/api/composants", json={**VIS, "qte_par_lot": taille}).status_code == 422
    )


def test_ensemble_compte_les_pieces_au_prix_de_la_piece(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    corps = {"composant_id": vis, "qte": 50}
    assert client_essai.post("/api/ensembles/CHASSIS/affectations", json=corps).status_code == 201
    ensemble = next(e for e in client_essai.get("/api/ensembles").json() if e["code"] == "CHASSIS")
    assert ensemble["cout_ht"] == pytest.approx(6.0)
    assert ensemble["depense_ht"] == pytest.approx(6.0)


def test_demande_de_devis_en_lots(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero = client_essai.post("/api/demandes-devis", json={"composants": [vis]}).json()[0][
        "numero"
    ]
    ligne = client_essai.get(f"/api/commandes/{numero}/lignes").json()[0]
    assert ligne["qte_commandee"] == 3
    assert ligne["qte_par_lot"] == 100
    assert ligne["pu_ht_estime"] == pytest.approx(12.0)


def test_commande_et_reception_en_lots(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero, ligne = _commande_passee(client_essai, vis)
    assert ligne["montant_ligne_ht"] == pytest.approx(36.0)
    assert client_essai.get("/api/pilotage").json()["montant_engage_ht"] == pytest.approx(36.0)
    commandee = _composant(client_essai, vis)
    assert commandee["qte_commandee"] == 300
    assert commandee["avancement"] == "Commande"
    assert commandee["reste_a_commander"] == 0
    corps = {"lignes": [{"id": ligne["id"], "qte": 3}]}
    reponse = client_essai.post(f"/api/commandes/{numero}/reception", json=corps)
    assert reponse.status_code == 200, reponse.text
    recue = _composant(client_essai, vis)
    assert recue["qte_recue"] == 300
    assert recue["stock_actuel"] == 300
    assert recue["avancement"] == "Recu"


def test_reception_au_dela_du_commande_en_lots(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero, ligne = _commande_passee(client_essai, vis)
    corps = {"lignes": [{"id": ligne["id"], "qte": 4}]}
    resultat = client_essai.post(f"/api/commandes/{numero}/reception", json=corps).json()
    assert any("4 lot(s) reçu(s) pour 3 commandé(s)" in a for a in resultat["avertissements"])
    assert _composant(client_essai, vis)["stock_actuel"] == 400


def test_lot_fige_sur_la_ligne(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero, _ = _commande_passee(client_essai, vis)
    corps = {"qte_par_lot": 50, "pu_releve": 6.0}
    assert client_essai.patch(f"/api/composants/{vis}", json=corps).status_code == 200
    assert client_essai.get(f"/api/commandes/{numero}/lignes").json()[0]["qte_par_lot"] == 100
    assert _composant(client_essai, vis)["qte_commandee"] == 300


def test_lot_change_sans_prix_refuse(client_essai: TestClient) -> None:
    """Le prix relevé est celui du lot : changer le lot seul fausserait le total."""
    vis = _creer(client_essai)
    reponse = client_essai.patch(f"/api/composants/{vis}", json={"qte_par_lot": 50})
    assert reponse.status_code == 400
    assert "prix" in reponse.json()["erreur"]
    assert _composant(client_essai, vis)["qte_par_lot"] == 100


def test_lot_change_sans_prix_permis_si_non_chiffre(client_essai: TestClient) -> None:
    vis = _creer(client_essai, pu_releve=None)
    assert client_essai.patch(f"/api/composants/{vis}", json={"qte_par_lot": 50}).status_code == 200
    assert _composant(client_essai, vis)["nb_lots_a_acheter"] == 5


def test_ligne_ajoutee_a_la_main_prend_le_lot(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": FOURNISSEUR}).json()[
        "numero"
    ]
    corps = {"composant_id": vis, "qte_commandee": 2}
    ligne = client_essai.post(f"/api/commandes/{numero}/lignes", json=corps).json()
    assert ligne["qte_par_lot"] == 100


def test_candidats_arrives_apres_la_demande_en_lots(client_essai: TestClient) -> None:
    numero = client_essai.post("/api/commandes", json={"fournisseur_nom": FOURNISSEUR}).json()[
        "numero"
    ]
    vis = _creer(client_essai)
    candidats = client_essai.get(f"/api/commandes/{numero}/candidats").json()
    candidat = next(c for c in candidats if c["id"] == vis)
    assert candidat["reste_a_commander_lots"] == 3


# --- Import, export et catalogue ----------------------------------------------------------------


def test_import_lot_change_avec_son_prix(client_essai: TestClient) -> None:
    from tests.test_import import _appliquer, _decisions_par_defaut, _deposer, _modele, _modifier

    contenu = _modele(client_essai, "/api/blocs/OBS/modele")
    contenu = _modifier(contenu, "ESSAI-OBS-002", "Qté par lot", 10)
    contenu = _modifier(contenu, "ESSAI-OBS-002", "PU relevé", 150)
    depot = _deposer(client_essai, [("obs.xlsx", contenu)])
    resultat = _appliquer(client_essai, depot, _decisions_par_defaut(depot))
    assert resultat["appliquees"] == 1, resultat
    obs = _composant(client_essai, "ESSAI-OBS-002")
    assert (obs["qte_par_lot"], obs["pu_releve"]) == (10, pytest.approx(150))


def test_import_lot_change_sans_prix_refuse(client_essai: TestClient) -> None:
    from tests.test_import import _appliquer, _decisions_par_defaut, _deposer, _modele, _modifier

    contenu = _modifier(
        _modele(client_essai, "/api/blocs/OBS/modele"), "ESSAI-OBS-002", "Qté par lot", 10
    )
    depot = _deposer(client_essai, [("obs.xlsx", contenu)])
    resultat = _appliquer(client_essai, depot, _decisions_par_defaut(depot))
    assert resultat["appliquees"] == 0
    assert "prix" in str(resultat["refus"])
    assert _composant(client_essai, "ESSAI-OBS-002")["qte_par_lot"] == 1


def test_import_sans_colonne_lot_garde_un(client_essai: TestClient) -> None:
    from tests.test_import import _appliquer, _decisions_par_defaut, _deposer, _fichier_libre

    nouveau = {
        "Bloc": "OBS",
        "Fonction": "Mesure",
        "Désignation": "Capteur de pression XP-9000",
        "Mode appro": "Achat",
        "Qté besoin": 1,
    }
    depot = _deposer(client_essai, [("libre.xlsx", _fichier_libre([nouveau]))])
    resultat = _appliquer(client_essai, depot, _decisions_par_defaut(depot))
    assert len(resultat["crees"]) == 1, resultat
    assert _composant(client_essai, resultat["crees"][0])["qte_par_lot"] == 1


def test_export_porte_le_lot(client_essai: TestClient) -> None:
    import io

    from openpyxl import load_workbook

    vis = _creer(client_essai)
    reponse = client_essai.get("/api/composants/export", params={"colonnes": "id,qte_par_lot"})
    assert reponse.status_code == 200, reponse.text
    feuille = load_workbook(io.BytesIO(reponse.content)).active
    lignes = {r[0]: r[1] for r in feuille.iter_rows(values_only=True)}
    assert lignes[vis] == 100


def test_bloc_et_incoherences_comptent_les_lots(client_essai: TestClient) -> None:
    """Point 8 du pré-mortem : le lot vu par v_bloc et v_incoherence, pas seulement v_composant."""

    def cout_ali() -> float:
        return next(b for b in client_essai.get("/api/blocs").json() if b["code"] == "ALI")[
            "cout_ht"
        ]

    avant = cout_ali()
    vis = _creer(client_essai)
    assert cout_ali() - avant == pytest.approx(36.0)
    client_essai.post("/api/ensembles", json={"code": "CHASSIS", "nom": "Châssis"})
    client_essai.post("/api/ensembles/CHASSIS/affectations", json={"composant_id": vis, "qte": 50})

    def incoherences_vis() -> list[dict]:
        return [
            i
            for i in client_essai.get("/api/ensembles/incoherences").json()
            if i["composant_id"] == vis
        ]

    assert [i["type"] for i in incoherences_vis()] == ["affecte_non_commande"]
    _commande_passee(client_essai, vis)
    assert incoherences_vis() == []


def test_devis_a_demander_suit_le_nouveau_lot(client_essai: TestClient) -> None:
    """Une demande pas encore envoyée suit le lot, à pièces égales : 3 lots de 100 font 6 de 50."""
    vis = _creer(client_essai)
    numero = client_essai.post("/api/demandes-devis", json={"composants": [vis]}).json()[0][
        "numero"
    ]
    corps = {"qte_par_lot": 50, "pu_releve": 6.0}
    assert client_essai.patch(f"/api/composants/{vis}", json=corps).status_code == 200
    ligne = client_essai.get(f"/api/commandes/{numero}/lignes").json()[0]
    assert (ligne["qte_par_lot"], ligne["qte_commandee"]) == (50, 6)
    journal = client_essai.get("/api/historique", params={"table": "ligne_commande"}).json()
    champs = {(e["champ"], e["ancienne_valeur"], e["nouvelle_valeur"]) for e in journal["lignes"]}
    assert {("qte_par_lot", "100", "50"), ("qte_commandee", "3", "6")} <= champs


def test_devis_a_demander_arrondit_au_lot_superieur(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero = client_essai.post("/api/demandes-devis", json={"composants": [vis]}).json()[0][
        "numero"
    ]
    client_essai.patch(f"/api/composants/{vis}", json={"qte_par_lot": 250, "pu_releve": 30.0})
    ligne = client_essai.get(f"/api/commandes/{numero}/lignes").json()[0]
    assert (ligne["qte_par_lot"], ligne["qte_commandee"]) == (250, 2)


def test_devis_demande_garde_son_lot(client_essai: TestClient) -> None:
    vis = _creer(client_essai)
    numero = client_essai.post("/api/demandes-devis", json={"composants": [vis]}).json()[0][
        "numero"
    ]
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Devis demande"})
    client_essai.patch(f"/api/composants/{vis}", json={"qte_par_lot": 50, "pu_releve": 6.0})
    ligne = client_essai.get(f"/api/commandes/{numero}/lignes").json()[0]
    assert (ligne["qte_par_lot"], ligne["qte_commandee"]) == (100, 3)
