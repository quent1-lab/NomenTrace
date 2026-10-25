"""Catalogue du dossier (phase 17) : proposer une référence déjà saisie par un autre projet.

Le projet du jeu d'essai (« essai », équipe Alpha) et un projet « beta » sont rangés dans le
dossier « epreuve ». Beta saisit un codeur AS5047D avec sa fiche technique ; Alpha porte déjà
le même codeur (ESSAI-AGI-003). Les grandeurs suivies : ce qu'une recherche montre de beta
(champs, et rien au-delà), selon l'option du dossier ; ce qu'une reprise recopie (champs,
fiche technique au bit près) et ce qu'elle laisse ; le tout-ou-rien de la création.
"""

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.erreurs import ErreurMetier
from backend.main import create_app
from backend.services import authentification, documents
from tests.test_comptes import PROJET, connecter, creer_compte, navigateur
from tests.test_hierarchie import (
    creer_dossier,
    creer_organisme,
    creer_projet,
    membre_organisme,
    ranger,
    serveur,
)
from tests.test_reference import lire

URL = f"/p/{PROJET}/api/composants/catalogue"
FICHE = b"%PDF-1.4\n% fiche technique du codeur\n"
CODEUR = {
    "bloc_code": "AGI",
    "fonction": "Mesure d'angle du bras",
    "designation": "Codeur magnetique AS5047D",
    "ref_fabricant": "AS5047D-ATSM",
    "fabricant": "ams-OSRAM",
    "fournisseur_nom": "Mouser",
    "lien_produit": "https://www.mouser.fr/as5047d",
    "pu_releve": 12.5,
    "base_prix_releve": "HT",
    "mode_appro": "Achat",
    "qte_besoin": 7,
    "qte_rechange": 2,
    "criticite": "Bloquant",
    "note_technique": "Note propre à beta",
}


@pytest.fixture(autouse=True)
def scrypt_rapide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authentification, "SCRYPT_N", 2**10)


@pytest.fixture
def code_projet() -> str:
    return PROJET


@pytest.fixture
def app(
    conn_essai: sqlite3.Connection, dossier_data: Path, dossier_echange: Path
) -> Iterator[FastAPI]:
    conn_essai.close()
    application = create_app(
        dossier_data,
        dossier_echange=dossier_echange,
        mode_local=False,
        chemin_comptes=dossier_data / "comptes.db",
        code_projet=PROJET,
    )
    with navigateur(application):
        creer_organisme(application, "meca", "Mécatronique")
        creer_dossier(application, "meca", {"code": "epreuve", "nom": "Épreuve 2027"})
        yield application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Deux projets rangés, le codeur et sa fiche dans beta, l'administrateur du serveur."""
    ranger(app, PROJET, {"dossier": "epreuve", "nom_equipe": "Alpha"})
    client_ = serveur(app)
    creer_projet(client_)
    reponse = client_.post("/p/beta/api/composants", json=CODEUR)
    assert reponse.status_code == 201, reponse.text
    identifiant = reponse.json()["id"]
    reponse = client_.post(
        f"/p/beta/api/composants/{identifiant}/documents",
        data={"type_document": "Fiche technique"},
        files=[("fichiers", ("as5047d.pdf", FICHE))],
    )
    assert reponse.status_code == 201, reponse.text
    return client_


def partager(client: TestClient, actif: bool = True) -> None:
    reponse = client.patch("/api/dossiers/epreuve", json={"partage_composants": actif})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["partage_composants"] == int(actif)


def chercher(client: TestClient, **saisie: str) -> dict:
    reponse = client.get(URL, params=saisie)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def id_beta(app: FastAPI) -> str:
    return lire(app, "beta", "SELECT id FROM composant WHERE ref_fabricant = 'AS5047D-ATSM'")[0][0]


# --- 1. L'option du dossier ---------------------------------------------------------------------


def test_desactive_par_defaut(client: TestClient) -> None:
    trouve = chercher(client, ref_fabricant="AS5047D-ATSM")
    assert trouve["actif"] is False
    assert trouve["propositions"] == []
    # Le doublon dans le projet reste signalé : c'est sa propre base.
    assert [d["id"] for d in trouve["dans_le_projet"]] == ["ESSAI-AGI-003"]


def test_option_reservee_a_la_gestion(app: FastAPI, client: TestClient) -> None:
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    lecteur = connecter(app, "lecture@ecole.test")
    reponse = lecteur.patch("/api/dossiers/epreuve", json={"partage_composants": True})
    assert reponse.status_code == 403
    assert client.get("/api/dossiers/epreuve").json()["partage_composants"] == 0


# --- 2. Ce qu'une recherche montre ---------------------------------------------------------------


def test_proposition_reduite_a_la_reference(app: FastAPI, client: TestClient) -> None:
    partager(client)
    trouve = chercher(client, designation="Codeur", ref_fabricant="as5047d atsm")
    assert trouve["actif"] is True
    assert len(trouve["propositions"]) == 1
    proposition = trouve["propositions"][0]
    assert proposition == {
        "projet": "beta",
        "id": id_beta(app),
        "equipe": "Beta",
        "designation": "Codeur magnetique AS5047D",
        "ref_fabricant": "AS5047D-ATSM",
        "fabricant": "ams-OSRAM",
        "fournisseur_nom": "Mouser",
        "recu": False,
        "nb_fiches": 1,
        "motif": "référence fabricant identique",
    }


def test_lecture_suit_les_ecritures(client: TestClient) -> None:
    """Les bases lues sont gardées en mémoire : une écriture dans beta doit être vue."""
    partager(client)
    assert chercher(client, ref_fabricant="INA260AIPWR")["propositions"] == []
    corps = {**CODEUR, "designation": "Capteur de courant INA260", "ref_fabricant": "INA260AIPWR"}
    assert client.post("/p/beta/api/composants", json=corps).status_code == 201
    trouve = chercher(client, ref_fabricant="INA260AIPWR")["propositions"]
    assert [p["designation"] for p in trouve] == ["Capteur de courant INA260"]


def test_saisie_trop_courte(client: TestClient) -> None:
    partager(client)
    trouve = chercher(client, designation="Co", ref_fabricant="AS")
    assert trouve == {"actif": True, "propositions": [], "dans_le_projet": []}


def test_archive_et_hors_ligne_ignores(app: FastAPI, client: TestClient) -> None:
    partager(client)
    hors_ligne = app.state.registre.projets.pop("beta")
    assert chercher(client, ref_fabricant="AS5047D-ATSM")["propositions"] == []
    app.state.registre.projets["beta"] = hors_ligne
    reponse = client.delete(f"/p/beta/api/composants/{id_beta(app)}")
    assert reponse.status_code in (200, 204), reponse.text
    assert chercher(client, ref_fabricant="AS5047D-ATSM")["propositions"] == []


def test_lecteur_ne_cherche_pas(app: FastAPI, client: TestClient) -> None:
    partager(client)
    creer_compte(app, "lecteur@ecole.test", "lecteur")
    lecteur = connecter(app, "lecteur@ecole.test")
    assert lecteur.get(URL, params={"ref_fabricant": "AS5047D-ATSM"}).status_code == 403


# --- 3. La reprise -------------------------------------------------------------------------------


def test_reprise_recopie_la_reference_seule(app: FastAPI, client: TestClient) -> None:
    partager(client)
    reponse = client.get(f"{URL}/reprise", params={"source": "beta", "id": id_beta(app)})
    assert reponse.status_code == 200, reponse.text
    reprise = reponse.json()
    assert reprise["equipe"] == "Beta"
    assert reprise["composant"] == {
        "bloc_code": "AGI",
        "fonction": "Mesure d'angle du bras",
        "designation": "Codeur magnetique AS5047D",
        "ref_fabricant": "AS5047D-ATSM",
        "fabricant": "ams-OSRAM",
        "fournisseur_nom": "Mouser",
        "lien_produit": "https://www.mouser.fr/as5047d",
        "pu_releve": 12.5,
        "base_prix_releve": "HT",
        "taux_tva": 0.2,
    }
    assert reprise["fiches"] == [{"nom_origine": "as5047d.pdf", "taille": len(FICHE)}]
    assert len(reprise["date_prix"]) == 10


def test_reprise_refusee_sans_option(app: FastAPI, client: TestClient) -> None:
    reponse = client.get(f"{URL}/reprise", params={"source": "beta", "id": id_beta(app)})
    assert reponse.status_code == 403
    corps = {**CODEUR, "reprise": {"projet": "beta", "id": id_beta(app)}}
    assert client.post(f"/p/{PROJET}/api/composants", json=corps).status_code == 403


def test_reprise_hors_du_dossier(client: TestClient) -> None:
    partager(client)
    reponse = client.get(f"{URL}/reprise", params={"source": "inconnu", "id": "X-1"})
    assert reponse.status_code == 404


def test_creation_copie_la_fiche_technique(app: FastAPI, client: TestClient) -> None:
    partager(client)
    corps = {**CODEUR, "qte_besoin": 3, "reprise": {"projet": "beta", "id": id_beta(app)}}
    reponse = client.post(f"/p/{PROJET}/api/composants", json=corps)
    assert reponse.status_code == 201, reponse.text
    cree = reponse.json()
    assert cree["id"].startswith("ESSAI-AGI-")
    assert cree["qte_besoin"] == 3
    fiches = lire(
        app,
        PROJET,
        "SELECT type_document, nom_origine, empreinte, chemin FROM document WHERE composant_id = ?",
        (cree["id"],),
    )
    assert len(fiches) == 1
    type_document, nom, empreinte, chemin = fiches[0]
    assert (type_document, nom) == ("Fiche technique", "as5047d.pdf")
    assert empreinte == hashlib.sha256(FICHE).hexdigest()
    assert (app.state.registre.projets[PROJET].documents / chemin).read_bytes() == FICHE
    journal = lire(
        app,
        PROJET,
        "SELECT nouvelle_valeur FROM journal WHERE cle_cible = ? AND champ = 'reprise'",
        (cree["id"],),
    )
    assert journal == [("reprise du dossier (Beta)",)]
    # La source n'a pas bougé : une seule fiche, toujours la sienne.
    assert lire(app, "beta", "SELECT COUNT(*) FROM document") == [(1,)]


def test_creation_tout_ou_rien(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    partager(client)
    origine = documents.add_document

    def ecrire_puis_echouer(*args: object, **kwargs: object) -> dict:
        origine(*args, **kwargs)
        raise ErreurMetier("Échec simulé après l'écriture du fichier.")

    monkeypatch.setattr(documents, "add_document", ecrire_puis_echouer)
    avant = lire(app, PROJET, "SELECT COUNT(*) FROM composant")
    corps = {**CODEUR, "reprise": {"projet": "beta", "id": id_beta(app)}}
    reponse = client.post(f"/p/{PROJET}/api/composants", json=corps)
    assert reponse.status_code == 400
    assert lire(app, PROJET, "SELECT COUNT(*) FROM composant") == avant
    assert lire(app, PROJET, "SELECT COUNT(*) FROM document") == [(0,)]
    dossier = app.state.registre.projets[PROJET].documents / "composants"
    assert not dossier.exists() or not any(p.is_file() for p in dossier.rglob("*"))
