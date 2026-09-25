"""Tests des fournisseurs : fiche détaillée et comparaison avec une liste Excel."""

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook


def _liste(lignes: list[tuple]) -> bytes:
    """Classeur au format de la liste des fournisseurs autorisés : titre, vide, en-têtes."""
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(("FOURNISSEURS RÉFÉRENCÉS", None, None, None, None, None))
    feuille.append(())
    feuille.append(("CATEGORIE", "SOUS-CATEGORIE", "NOM", "SITE WEB", "CONTACT DEVIS", "N° COMPTE"))
    for ligne in lignes:
        feuille.append(ligne)
    feuille.append(())
    feuille.append(("CONSIGNES",))
    feuille.append(("Demandez des devis au nom de l'école.",))
    sortie = io.BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


def _comparer(client: TestClient, contenu: bytes) -> dict:
    reponse = client.post("/api/fournisseurs/comparaison", files={"fichier": ("f.xlsx", contenu)})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_fiche_fournisseur(client_spoc: TestClient) -> None:
    fiche = client_spoc.get("/api/fournisseurs/Farnell").json()
    assert fiche["nom"] == "Farnell"
    assert len(fiche["composants"]) == 7
    assert {"id", "designation", "total_ht", "avancement"} <= set(fiche["composants"][0])
    assert fiche["commandes"] == []
    assert "numero_compte" in fiche and "contact" in fiche and "categorie" in fiche


def test_fiche_fournisseur_archive_reste_lisible(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Amazon / StepperOnline"})
    client.delete("/api/fournisseurs/Amazon%20%2F%20StepperOnline")
    fiche = client.get("/api/fournisseurs/Amazon%20%2F%20StepperOnline")
    assert fiche.status_code == 200
    assert fiche.json()["archive"] == 1
    assert client.get("/api/fournisseurs/Inconnu").status_code == 404


def test_contact_categorie_et_compte_modifiables(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Farnell", "numero_compte": "759460"})
    reponse = client.patch(
        "/api/fournisseurs/Farnell",
        json={"categorie": "ELECTRONIQUE", "contact": "ventes@farnell.com\nSAV : sav@farnell.com"},
    )
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["contact"].splitlines()[1] == "SAV : sav@farnell.com"
    assert reponse.json()["numero_compte"] == "759460"


def test_lecture_de_la_liste(client: TestClient) -> None:
    resultat = _comparer(
        client,
        _liste(
            [
                (
                    "ELECTRONIQUE",
                    "FOURNITURES",
                    "EUROMAKERS",
                    "https://euro-makers.com/fr/",
                    None,
                    "CU1",
                ),
                ("IMPRESSION 3D", "FOURNITURES", "EUROMAKERS", None, "contact@euro.com", None),
                (
                    "MECANIQUE",
                    "TRANSMISSION",
                    "ATLANTA",
                    "www.atlanta.fr \nwww.neugart.com",
                    None,
                    30,
                ),
                ("MECANIQUE", "MATIERE", "LCM", "www.lcm.com", None, "01713465"),
            ]
        ),
    )
    nouveaux = {f["nom"]: f for f in resultat["nouveaux"]}
    assert set(nouveaux) == {"EUROMAKERS", "ATLANTA", "LCM"}
    assert nouveaux["EUROMAKERS"]["categorie"] == "ELECTRONIQUE / IMPRESSION 3D"
    assert nouveaux["EUROMAKERS"]["contact"] == "contact@euro.com"
    assert nouveaux["ATLANTA"]["site_web"] == "https://www.atlanta.fr"
    assert nouveaux["ATLANTA"]["commentaire"] == "Autres sites : https://www.neugart.com"
    assert nouveaux["ATLANTA"]["numero_compte"] == "30"
    assert nouveaux["LCM"]["numero_compte"] == "01713465"
    assert "sous_categorie" not in nouveaux["LCM"]


def test_comparaison_classe_les_fournisseurs(client: TestClient) -> None:
    for nom in ("Farnell", "Conrad", "RS Components", "PFM"):
        client.post("/api/fournisseurs", json={"nom": nom, "site_web": "https://fr.farnell.com"})
    resultat = _comparer(
        client,
        _liste(
            [
                ("ELECTRONIQUE", None, "FARNELL", "fr.farnell.com", "ventes@farnell.com", None),
                ("ELECTRONIQUE", None, "CONRAD  ELECTRONIQUE", None, None, 511958258),
                ("ELECTRONIQUE", None, "rs  components", None, None, None),
                ("MECANIQUE", None, "IGUS", "www.igus.fr", None, None),
            ]
        ),
    )
    presents = {e["nom"]: e for e in resultat["presents"]}
    assert set(presents) == {"Farnell", "RS Components"}
    # Même site écrit autrement : pas une différence.
    assert set(presents["Farnell"]["differences"]) == {"categorie", "contact"}
    assert [(e["nom"], e["liste"]["nom"]) for e in resultat["probables"]] == [
        ("Conrad", "CONRAD ELECTRONIQUE")
    ]
    assert [f["nom"] for f in resultat["nouveaux"]] == ["IGUS"]
    assert resultat["absents"] == ["PFM"]
    # Rien n'est écrit par la comparaison.
    assert len(client.get("/api/fournisseurs").json()) == 4


def test_application_cree_complete_et_reactive(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Farnell"})
    client.post("/api/fournisseurs", json={"nom": "Conrad"})
    client.delete("/api/fournisseurs/Conrad")
    reponse = client.post(
        "/api/fournisseurs/comparaison/appliquer",
        json={
            "creations": [{"nom": "IGUS", "categorie": "MECANIQUE", "numero_compte": "8120471"}],
            "completions": [
                {"nom": "Farnell", "champs": {"contact": "ventes@farnell.com"}},
                {"nom": "Conrad", "champs": {"numero_compte": "511958258"}},
            ],
        },
    )
    assert reponse.status_code == 200, reponse.text
    assert reponse.json() == {"crees": 1, "completes": 2}
    fournisseurs = {f["nom"]: f for f in client.get("/api/fournisseurs").json()}
    assert fournisseurs["IGUS"]["numero_compte"] == "8120471"
    assert fournisseurs["Farnell"]["contact"] == "ventes@farnell.com"
    assert fournisseurs["Conrad"]["numero_compte"] == "511958258"
    journal = client.get("/api/journal?table_cible=fournisseur&cle_cible=Farnell").json()
    assert any(ligne["champ"] == "contact" for ligne in journal)


def test_application_tout_ou_rien(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Farnell"})
    reponse = client.post(
        "/api/fournisseurs/comparaison/appliquer",
        json={"creations": [{"nom": "IGUS"}, {"nom": "Farnell"}], "completions": []},
    )
    assert reponse.status_code == 409
    assert all(f["nom"] != "IGUS" for f in client.get("/api/fournisseurs").json())


def test_liste_illisible_ou_sans_colonne_nom(client: TestClient) -> None:
    reponse = client.post(
        "/api/fournisseurs/comparaison", files={"fichier": ("f.xlsx", b"pas un classeur")}
    )
    assert reponse.status_code == 400
    classeur = Workbook()
    classeur.active.append(("Désignation", "Prix"))
    sortie = io.BytesIO()
    classeur.save(sortie)
    reponse = client.post(
        "/api/fournisseurs/comparaison", files={"fichier": ("f.xlsx", sortie.getvalue())}
    )
    assert reponse.status_code == 400
    assert "Nom" in reponse.json()["erreur"]


# --- Fournisseurs à valider ---------------------------------------------------------------


def test_fournisseur_a_valider_puis_valide(client: TestClient) -> None:
    assert client.post("/api/fournisseurs", json={"nom": "Farnell"}).json()["statut"] == "Valide"
    cree = client.post("/api/fournisseurs", json={"nom": "Bossard", "statut": "A valider"})
    assert cree.status_code == 201, cree.text
    assert cree.json()["statut"] == "A valider"
    assert client.get("/api/pilotage").json()["nb_fournisseurs_a_valider"] == 1
    reponse = client.patch("/api/fournisseurs/Bossard", json={"statut": "Valide", "pays": "Suisse"})
    assert reponse.json()["statut"] == "Valide"
    assert client.get("/api/pilotage").json()["nb_fournisseurs_a_valider"] == 0
    journal = client.get("/api/journal?table_cible=fournisseur&cle_cible=Bossard").json()
    assert any(
        ligne["champ"] == "statut" and ligne["nouvelle_valeur"] == "Valide" for ligne in journal
    )
    assert client.patch("/api/fournisseurs/Bossard", json={"statut": "Douteux"}).status_code == 422


def test_composant_avec_fournisseur_a_valider(client_spoc: TestClient) -> None:
    client_spoc.post("/api/fournisseurs", json={"nom": "Bossard", "statut": "A valider"})
    reponse = client_spoc.post(
        "/api/composants",
        json={
            "bloc_code": "ALI",
            "fonction": "Fixation",
            "designation": "Écrou M6",
            "mode_appro": "Achat",
            "qte_besoin": 4,
            "fournisseur_nom": "Bossard",
        },
    )
    assert reponse.status_code == 201, reponse.text
    fiche = client_spoc.get("/api/fournisseurs/Bossard").json()
    assert [c["id"] for c in fiche["composants"]] == [reponse.json()["id"]]


def test_homonyme_refuse(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "RS Components"})
    reponse = client.post(
        "/api/fournisseurs", json={"nom": "rs  components", "statut": "A valider"}
    )
    assert reponse.status_code == 409
    assert "RS Components" in reponse.json()["erreur"]


def test_reactivation_garde_la_validation(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Farnell"})
    client.delete("/api/fournisseurs/Farnell")
    reponse = client.post("/api/fournisseurs", json={"nom": "Farnell", "statut": "A valider"})
    assert reponse.status_code == 201
    assert reponse.json()["statut"] == "Valide"


def test_liste_de_reference_propose_la_validation(client: TestClient) -> None:
    client.post("/api/fournisseurs", json={"nom": "Igus", "statut": "A valider"})
    resultat = _comparer(
        client, _liste([("MECANIQUE", None, "IGUS", "www.igus.fr", None, 8120471)])
    )
    assert resultat["presents"][0]["a_valider"] is True
    client.post(
        "/api/fournisseurs/comparaison/appliquer",
        json={"completions": [{"nom": "Igus", "champs": {"statut": "Valide"}}]},
    )
    assert client.get("/api/fournisseurs/Igus").json()["statut"] == "Valide"
