"""Nettoyage : règles de suppression, sauvegarde préalable, reclassement, contrôles de qualité."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\n% document de test\n"
COMPOSANT_LIBRE = "ESSAI-ALI-006"  # ni commande, ni mouvement, ni document dans le jeu d'essai


def _sauvegardes(dossier_echange: Path) -> int:
    return len(list((dossier_echange / "sauvegardes").glob("nomentrace_*.db")))


def _lot(client: TestClient, cible: str, cles: list[str], action: str, simuler: bool = False):
    corps = {"cles": cles, "action": action, "simuler": simuler}
    return client.post(f"/api/nettoyage/{cible}", json=corps)


def _journal(client: TestClient, table: str, cle: str) -> list[dict]:
    return client.get("/api/journal", params={"table_cible": table, "cle_cible": cle}).json()


def _ensemble(client: TestClient, code: str = "CHASSIS") -> str:
    client.post("/api/ensembles", json={"code": code, "nom": f"Ensemble {code}"})
    return code


def _commande(client: TestClient, composant: str = COMPOSANT_LIBRE) -> tuple[str, int]:
    numero = client.post("/api/commandes", json={"fournisseur_nom": "Mouser"}).json()["numero"]
    corps = {"composant_id": composant, "qte_commandee": 2, "pu_ht_devis": 3.0}
    ligne = client.post(f"/api/commandes/{numero}/lignes", json=corps).json()["id"]
    return numero, ligne


def _mouvement(client: TestClient, composant: str, **autres: object) -> None:
    corps = {"date": "2026-02-01", "composant_id": composant, "qte": 1, **autres}
    corps.setdefault("type_mouvement", "Inventaire")
    corps.setdefault("sens", "Entree")
    assert client.post("/api/mouvements", json=corps).status_code == 201


def _deposer(client: TestClient, chemin: str, type_doc: str) -> None:
    fichiers = [("fichiers", ("doc.pdf", PDF))]
    reponse = client.post(chemin, files=fichiers, data={"type_document": type_doc})
    assert reponse.status_code == 201


# --- Composants ---------------------------------------------------------------------------------


def test_composant_sans_trace_supprime_avec_ses_affectations(
    client_essai: TestClient, dossier_echange: Path
) -> None:
    ensemble = _ensemble(client_essai)
    corps = {"composant_id": COMPOSANT_LIBRE, "qte": 1}
    client_essai.post(f"/api/ensembles/{ensemble}/affectations", json=corps)
    avant = _sauvegardes(dossier_echange)

    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE], "supprimer").json()

    assert recap == {"supprimes": [COMPOSANT_LIBRE], "archives": [], "refuses": []}
    assert _sauvegardes(dossier_echange) == avant + 1
    assert client_essai.get(f"/api/composants/{COMPOSANT_LIBRE}").status_code == 404
    assert client_essai.get(f"/api/ensembles/{ensemble}/composants").json() == []
    ligne = next(
        j
        for j in _journal(client_essai, "composant", COMPOSANT_LIBRE)
        if j["champ"] == "suppression"
    )
    resume = json.loads(ligne["ancienne_valeur"])
    assert resume["designation"] == "ATS ERDN40-48"
    assert resume["affectations"] == [{"ensemble_code": ensemble, "qte": 1}]


def test_simulation_ne_touche_a_rien(client_essai: TestClient, dossier_echange: Path) -> None:
    avant = _sauvegardes(dossier_echange)
    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE], "supprimer", simuler=True)
    assert recap.json()["supprimes"] == [COMPOSANT_LIBRE]
    assert _sauvegardes(dossier_echange) == avant
    assert client_essai.get(f"/api/composants/{COMPOSANT_LIBRE}").status_code == 200


@pytest.mark.parametrize("trace", ["ligne de commande", "mouvement de stock", "document joint"])
def test_composant_avec_trace_refuse(client_essai: TestClient, trace: str) -> None:
    if trace == "ligne de commande":
        _commande(client_essai)
    elif trace == "mouvement de stock":
        _mouvement(client_essai, COMPOSANT_LIBRE)
    else:
        _deposer(client_essai, f"/api/composants/{COMPOSANT_LIBRE}/documents", "Fiche technique")

    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE, "ESSAI-ALI-001"], "supprimer")

    resultat = recap.json()
    assert resultat["supprimes"] == ["ESSAI-ALI-001"]
    assert [r["cle"] for r in resultat["refuses"]] == [COMPOSANT_LIBRE]
    assert trace in resultat["refuses"][0]["raison"]
    assert client_essai.get(f"/api/composants/{COMPOSANT_LIBRE}").status_code == 200


def test_archiver_en_lot(client_essai: TestClient) -> None:
    _commande(client_essai)
    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE], "archiver").json()
    assert recap["archives"] == [COMPOSANT_LIBRE]
    assert client_essai.get("/api/composants", params={"q": COMPOSANT_LIBRE}).json() == []
    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE], "archiver").json()
    assert recap["refuses"] == [{"cle": COMPOSANT_LIBRE, "raison": "déjà archivé"}]


# --- Commandes ----------------------------------------------------------------------------------


def test_commande_supprimee_avec_lignes_et_documents(
    client_essai: TestClient, dossier_echange: Path
) -> None:
    numero, _ = _commande(client_essai)
    _deposer(client_essai, f"/api/commandes/{numero}/documents", "Devis")
    fichiers = list((dossier_echange / "documents" / "commandes").rglob("*.pdf"))
    assert len(fichiers) == 1
    avant = _sauvegardes(dossier_echange)

    recap = _lot(client_essai, "commandes", [numero], "supprimer").json()

    assert recap["supprimes"] == [numero]
    assert _sauvegardes(dossier_echange) == avant + 1
    assert client_essai.get(f"/api/commandes/{numero}").status_code == 404
    assert not fichiers[0].exists()
    ligne = next(
        j for j in _journal(client_essai, "commande", numero) if j["champ"] == "suppression"
    )
    resume = json.loads(ligne["ancienne_valeur"])
    assert len(resume["lignes"]) == 1 and len(resume["documents"]) == 1
    # Le composant n'a plus de ligne de commande : il redevient supprimable.
    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE], "supprimer", simuler=True)
    assert recap.json()["supprimes"] == [COMPOSANT_LIBRE]


def test_commande_avec_ligne_recue_refusee(client_essai: TestClient) -> None:
    numero, ligne = _commande(client_essai)
    client_essai.patch(f"/api/commandes/{numero}", json={"statut": "Commande"})
    corps = {"lignes": [{"id": ligne, "qte": 1}]}
    assert client_essai.post(f"/api/commandes/{numero}/reception", json=corps).status_code == 200

    recap = _lot(client_essai, "commandes", [numero], "supprimer").json()

    assert recap["supprimes"] == []
    assert "ligne reçue" in recap["refuses"][0]["raison"]
    assert _lot(client_essai, "commandes", [numero], "archiver").json()["archives"] == [numero]


def test_commande_avec_mouvement_lie_refusee(client_essai: TestClient) -> None:
    numero, _ = _commande(client_essai)
    _mouvement(client_essai, "ESSAI-ALI-001", commande_numero=numero)
    recap = _lot(client_essai, "commandes", [numero], "supprimer").json()
    assert "mouvement de stock lié" in recap["refuses"][0]["raison"]


def test_commandes_listees_archivees_comprises(client_essai: TestClient) -> None:
    numero, _ = _commande(client_essai)
    vide = client_essai.post("/api/commandes", json={}).json()["numero"]
    client_essai.delete(f"/api/commandes/{numero}")
    commandes = {
        c["numero"]: c for c in client_essai.get("/api/nettoyage/commandes").json()["commandes"]
    }
    assert commandes[numero]["archive"] == 1
    assert commandes[vide]["controles"] == ["sans_ligne", "sans_fournisseur"]
    assert commandes[vide]["raison_refus"] is None


# --- Blocs, ensembles, fournisseurs --------------------------------------------------------------


def _supprimer(client: TestClient, type_entite: str, cle: str):
    return client.delete(f"/api/nettoyage/entites/{type_entite}/{cle}")


def test_fournisseur_inutilise_supprime(client_essai: TestClient, dossier_echange: Path) -> None:
    client_essai.post("/api/fournisseurs", json={"nom": "Fournisseur inutile"})
    avant = _sauvegardes(dossier_echange)
    assert _supprimer(client_essai, "fournisseur", "Fournisseur inutile").status_code == 200
    assert _sauvegardes(dossier_echange) == avant + 1
    assert client_essai.get("/api/fournisseurs/Fournisseur inutile").status_code == 404
    lignes = _journal(client_essai, "fournisseur", "Fournisseur inutile")
    assert lignes[0]["champ"] == "suppression"


def test_fournisseur_cite_par_un_composant_archive_refuse(client_essai: TestClient) -> None:
    client_essai.patch(f"/api/composants/{COMPOSANT_LIBRE}", json={"fournisseur_nom": "TME"})
    client_essai.delete(f"/api/composants/{COMPOSANT_LIBRE}")
    for composant in client_essai.get("/api/fournisseurs/TME").json()["composants"]:
        client_essai.patch(f"/api/composants/{composant['id']}", json={"fournisseur_nom": None})
    reponse = _supprimer(client_essai, "fournisseur", "TME")
    assert reponse.status_code == 409
    assert "archivés compris" in reponse.json()["erreur"]


def test_bloc_vide_supprime_bloc_utilise_refuse(client_essai: TestClient) -> None:
    client_essai.post("/api/blocs", json={"code": "VIDE", "nom": "Bloc vide"})
    entites = client_essai.get("/api/nettoyage/entites").json()
    assert {"type": "bloc", "cle": "VIDE", "nom": "Bloc vide", "archive": 0} in entites
    assert _supprimer(client_essai, "bloc", "VIDE").status_code == 200
    assert _supprimer(client_essai, "bloc", "TR").status_code == 409


def test_bloc_avec_composant_archive_refuse(client_essai: TestClient) -> None:
    client_essai.post("/api/blocs", json={"code": "TMP", "nom": "Temporaire"})
    corps = {
        "bloc_code": "TMP",
        "fonction": "Essai",
        "designation": "Pièce",
        "mode_appro": "Achat",
        "qte_besoin": 1,
    }
    identifiant = client_essai.post("/api/composants", json=corps).json()["id"]
    client_essai.delete(f"/api/composants/{identifiant}")
    reponse = _supprimer(client_essai, "bloc", "TMP")
    assert reponse.status_code == 409
    assert "1 composant" in reponse.json()["erreur"]


def test_bloc_archive_ferme_a_la_creation(client_essai: TestClient) -> None:
    refus = client_essai.patch("/api/blocs/TR", json={"archive": 1})
    assert refus.status_code == 400
    client_essai.post("/api/blocs", json={"code": "ARC", "nom": "À archiver"})
    assert client_essai.patch("/api/blocs/ARC", json={"archive": 1}).status_code == 200
    assert "ARC" not in [b["code"] for b in client_essai.get("/api/blocs").json()]
    tous = client_essai.get("/api/blocs", params={"archives": "true"}).json()
    assert next(b for b in tous if b["code"] == "ARC")["archive"] == 1
    corps = {
        "bloc_code": "ARC",
        "fonction": "Essai",
        "designation": "Pièce",
        "mode_appro": "Achat",
        "qte_besoin": 1,
    }
    reponse = client_essai.post("/api/composants", json=corps)
    assert reponse.status_code == 400
    assert "archivé" in reponse.json()["erreur"]


def test_ensemble_regles_de_suppression(client_essai: TestClient) -> None:
    libre, affecte, monte = (
        _ensemble(client_essai, "LIBRE"),
        _ensemble(client_essai, "AFF"),
        _ensemble(client_essai, "MONT"),
    )
    client_essai.post(
        f"/api/ensembles/{affecte}/affectations", json={"composant_id": COMPOSANT_LIBRE, "qte": 1}
    )
    _mouvement(
        client_essai,
        "ESSAI-ALI-001",
        type_mouvement="Sortie montage",
        sens="Sortie",
        ensemble_code=monte,
    )
    assert _supprimer(client_essai, "ensemble", libre).status_code == 200
    assert "affectation" in _supprimer(client_essai, "ensemble", affecte).json()["erreur"]
    assert "montage" in _supprimer(client_essai, "ensemble", monte).json()["erreur"]


def test_entite_inconnue(client_essai: TestClient) -> None:
    assert _supprimer(client_essai, "bloc", "ZZZ").status_code == 404
    assert _supprimer(client_essai, "table", "x").status_code == 404


# --- Journal -----------------------------------------------------------------------------------


def test_vider_le_journal(client_essai: TestClient, dossier_echange: Path) -> None:
    client_essai.patch(f"/api/composants/{COMPOSANT_LIBRE}", json={"qte_besoin": 2})
    avant = _sauvegardes(dossier_echange)
    assert client_essai.post("/api/nettoyage/journal/purge", json={}).status_code == 422
    reponse = client_essai.post("/api/nettoyage/journal/purge", json={"confirmer": True})
    assert reponse.json()["lignes_supprimees"] >= 1
    assert _sauvegardes(dossier_echange) == avant + 1
    journal = client_essai.get("/api/journal").json()
    assert len(journal) == 1
    assert journal[0]["champ"] == "purge"


# --- Reclassement ------------------------------------------------------------------------------


def test_reclassement(client_essai: TestClient) -> None:
    ensemble = _ensemble(client_essai)
    client_essai.post(
        f"/api/ensembles/{ensemble}/affectations", json={"composant_id": COMPOSANT_LIBRE, "qte": 2}
    )
    numero, _ = _commande(client_essai)

    reponse = client_essai.post(
        f"/api/composants/{COMPOSANT_LIBRE}/reclasser", json={"bloc_code": "TR"}
    )

    assert reponse.status_code == 201
    nouveau = reponse.json()
    assert nouveau["id"] == "ESSAI-TR-003"
    assert nouveau["bloc_code"] == "TR"
    assert nouveau["designation"] == "ATS ERDN40-48"
    assert nouveau["qte_affectee"] == 2
    fiche_nouveau = client_essai.get(f"/api/composants/{nouveau['id']}").json()
    assert fiche_nouveau["remplace"] == [COMPOSANT_LIBRE]
    assert fiche_nouveau["lignes_commande"] == []
    fiche_ancien = client_essai.get(f"/api/composants/{COMPOSANT_LIBRE}").json()
    assert fiche_ancien["composant"]["archive"] == 1
    assert fiche_ancien["composant"]["remplace_par"] == "ESSAI-TR-003"
    assert fiche_ancien["affectations"] == []
    assert [ligne["commande_numero"] for ligne in fiche_ancien["lignes_commande"]] == [numero]
    assert any(j["champ"] == "remplace_par" for j in fiche_ancien["journal"])
    assert any("remplace" in (j["nouvelle_valeur"] or "") for j in fiche_nouveau["journal"])
    # Les deux composants sont liés par le reclassement : aucun n'est supprimable.
    recap = _lot(client_essai, "composants", [COMPOSANT_LIBRE, "ESSAI-TR-003"], "supprimer")
    assert len(recap.json()["refuses"]) == 2


def test_reclassement_refuse(client_essai: TestClient) -> None:
    meme = client_essai.post(
        f"/api/composants/{COMPOSANT_LIBRE}/reclasser", json={"bloc_code": "ALI"}
    )
    assert meme.status_code == 400
    absent = client_essai.post(
        f"/api/composants/{COMPOSANT_LIBRE}/reclasser", json={"bloc_code": "ZZZ"}
    )
    assert absent.status_code == 404


# --- Contrôles de qualité ----------------------------------------------------------------------


def _controles(client: TestClient) -> dict[str, dict]:
    reponse = client.get("/api/nettoyage/composants").json()
    return {c["id"]: c for c in reponse["composants"]}


def _creer(client: TestClient, **valeurs: object) -> str:
    corps = {
        "bloc_code": "TR",
        "fonction": "Fonction test",
        "designation": "Pièce de test unique",
        "mode_appro": "Achat",
        "qte_besoin": 1,
        "pu_releve": 1.0,
        "fournisseur_nom": "Mouser",
        **valeurs,
    }
    reponse = client.post("/api/composants", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def test_composant_bien_rempli_sans_anomalie(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai)
    assert _controles(client_essai)[identifiant]["controles"] == []


@pytest.mark.parametrize(
    ("valeurs", "controle"),
    [
        ({"designation": "Vis"}, "designation_courte"),
        ({"pu_releve": None}, "achat_sans_prix"),
        ({"fournisseur_nom": None}, "achat_sans_fournisseur"),
        ({"qte_besoin": 0}, "besoin_nul"),
        ({"lien_produit": "www.exemple.fr/produit"}, "lien_invalide"),
    ],
)
def test_controle_simple(client_essai: TestClient, valeurs: dict, controle: str) -> None:
    identifiant = _creer(client_essai)
    client_essai.patch(f"/api/composants/{identifiant}", json=valeurs)
    assert _controles(client_essai)[identifiant]["controles"] == [controle]


def test_controle_fonction_vide(client_essai: TestClient, chemin_base: Path) -> None:
    # L'API refuse une fonction vide ; un import ancien ou une saisie directe a pu en laisser.
    identifiant = _creer(client_essai)
    conn = sqlite3.connect(chemin_base)
    with conn:
        conn.execute("UPDATE composant SET fonction = '' WHERE id = ?", (identifiant,))
    conn.close()
    assert _controles(client_essai)[identifiant]["controles"] == ["fonction_vide"]


def test_lien_http_accepte(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, lien_produit="HTTPS://exemple.fr/p")
    assert _controles(client_essai)[identifiant]["controles"] == []


def test_controle_doublon(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, designation="Transceiver CAN", ref_fabricant="MCP2562-E/P")
    existant = _controles(client_essai)
    ligne = existant[identifiant]
    assert ligne["controles"] == ["doublon"]
    assert ligne["doublons"][0]["id"] in existant
    assert ligne["doublons"][0]["motif"] == "référence fabricant identique"
    assert identifiant in [d["id"] for d in existant[ligne["doublons"][0]["id"]]["doublons"]]


def test_controle_valeur_desactivee(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai, criticite="Confort")
    client_essai.patch("/api/listes/criticite/Confort", json={"actif": 0})
    assert _controles(client_essai)[identifiant]["controles"] == ["valeur_desactivee"]


def test_controle_fournisseur_archive(client_essai: TestClient) -> None:
    client_essai.post("/api/fournisseurs", json={"nom": "Ancien fournisseur"})
    identifiant = _creer(client_essai, fournisseur_nom="Ancien fournisseur")
    client_essai.delete("/api/fournisseurs/Ancien fournisseur")
    assert _controles(client_essai)[identifiant]["controles"] == ["fournisseur_archive"]


def test_controles_comptent_les_archives(client_essai: TestClient) -> None:
    identifiant = _creer(client_essai)
    client_essai.delete(f"/api/composants/{identifiant}")
    ligne = _controles(client_essai)[identifiant]
    assert ligne["archive"] == 1
    assert ligne["raison_refus"] is None
