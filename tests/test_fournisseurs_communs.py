"""Fournisseurs communs à l'organisme (phase 15b-3).

Le projet du jeu d'essai, rangé dans le dossier « epreuve » de l'organisme « meca », donne la
liste de l'organisme. Les grandeurs suivies : les fiches de fournisseurs, champ par champ, et
le nombre de composants cités par chaque fournisseur, qui ne doit jamais changer en silence.
"""

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from backend.services import authentification, import_application, propagation, reference
from tests.test_comptes import PROJET, connecter, creer_compte, navigateur
from tests.test_hierarchie import (
    _comptes,
    creer_dossier,
    creer_organisme,
    creer_projet,
    membre_organisme,
    ranger,
    serveur,
)
from tests.test_reference import base, contenu, lire, nb_journal

ORG = "org-meca"
FICHES = "SELECT * FROM fournisseur ORDER BY nom"
CITES = (
    "SELECT fournisseur_nom, COUNT(*) FROM composant WHERE fournisseur_nom IS NOT NULL"
    " GROUP BY fournisseur_nom ORDER BY fournisseur_nom"
)


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
def range_(app: FastAPI) -> TestClient:
    ranger(app, PROJET, {"dossier": "epreuve", "nom_equipe": "Alpha"})
    return serveur(app)


def ecrire(app: FastAPI, code: str, requete: str, params: tuple = ()) -> None:
    """Écriture directe dans un projet, verrou levé le temps de la transaction."""
    conn = db.connect(base(app, code), creer=False)
    try:
        with db.transaction(conn):
            conn.execute("UPDATE reglages_imposes SET propagation = 1")
            conn.execute(requete, params)
            conn.execute("UPDATE reglages_imposes SET propagation = 0")
    finally:
        conn.close()


def composant(client: TestClient, projet: str, fournisseur: str) -> str:
    corps = {
        "bloc_code": "ALI",
        "fonction": "Essai",
        "designation": f"Pièce {fournisseur}",
        "qte_besoin": 1,
        "mode_appro": "Achat",
        "fournisseur_nom": fournisseur,
    }
    reponse = client.post(f"/p/{projet}/api/composants", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


# --- 1. Le premier projet rangé donne la liste -------------------------------------------------


def test_premier_rangement_donne_la_liste(app: FastAPI) -> None:
    avant = contenu(base(app, PROJET))
    ranger(app, PROJET, {"dossier": "epreuve", "nom_equipe": "Alpha"})
    assert contenu(base(app, PROJET)) == avant
    assert lire(app, ORG, FICHES) == lire(app, PROJET, FICHES)
    assert len(lire(app, ORG, FICHES)) >= 5


# --- 2. Union au rangement d'un second projet ---------------------------------------------------


def test_second_projet_rejoint_la_liste(app: FastAPI, range_: TestClient) -> None:
    creer_projet(range_)
    ranger(app, "beta", {"dossier": None})
    ecrire(app, "beta", "INSERT INTO fournisseur (nom, contact) VALUES ('Nouveau', 'x')")
    ecrire(app, "beta", "UPDATE fournisseur SET contact = 'autre' WHERE nom = 'Farnell'")
    ecrire(app, "beta", "UPDATE fournisseur SET nom = 'MOUSER' WHERE nom = 'Mouser'")
    composant(range_, "beta", "MOUSER")
    essai_avant = lire(app, PROJET, FICHES)
    ranger(app, "beta", {"dossier": "epreuve"})
    # « Nouveau » rejoint la liste et descend dans le premier projet, qui ne change pas sinon.
    assert "Nouveau" in {f[0] for f in lire(app, ORG, FICHES)}
    essai = lire(app, PROJET, FICHES)
    assert [f for f in essai if f[0] != "Nouveau"] == essai_avant
    # Pour les fiches communes, l'organisme gagne ; « MOUSER » est le « Mouser » de la liste.
    assert lire(app, "beta", FICHES) == lire(app, ORG, FICHES)
    assert lire(app, "beta", CITES) == [("Mouser", 1)]


# --- 3. Une modification de la liste atteint tout l'organisme, et lui seul ----------------------


def test_modification_de_la_liste_propagee(app: FastAPI, range_: TestClient) -> None:
    creer_dossier(app, "meca", {"code": "epreuve-b", "nom": "Autre dossier"})
    creer_projet(range_, "gamma", "epreuve-b")
    creer_organisme(app, "autre", "Autre école")
    creer_dossier(app, "autre", {"code": "ailleurs", "nom": "Ailleurs"})
    creer_projet(range_, "delta", "ailleurs")
    ailleurs = lire(app, "delta", FICHES)
    reponse = range_.patch(f"/p/{ORG}/api/fournisseurs/Farnell", json={"contact": "achats@farnell"})
    assert reponse.status_code == 200, reponse.text
    for code in (PROJET, "gamma"):
        assert lire(app, code, "SELECT contact FROM fournisseur WHERE nom = 'Farnell'") == [
            ("achats@farnell",)
        ]
    assert lire(app, "delta", FICHES) == ailleurs


# --- 4. Renommages ------------------------------------------------------------------------------


def test_renommage_suivi_par_les_composants(app: FastAPI, range_: TestClient) -> None:
    cites = dict(lire(app, PROJET, CITES))
    reponse = range_.patch(f"/p/{ORG}/api/fournisseurs/Farnell", json={"nom": "Farnell France"})
    assert reponse.status_code == 200, reponse.text
    apres = dict(lire(app, PROJET, CITES))
    assert apres["Farnell France"] == cites["Farnell"]
    assert "Farnell" not in apres
    assert lire(app, PROJET, "SELECT COUNT(*) FROM fournisseur WHERE nom = 'Farnell'") == [(0,)]
    avant = nb_journal(app, PROJET)
    conn = _comptes(app)
    try:
        reference.propager(conn, app.state.registre, "epreuve")
    finally:
        conn.close()
    assert nb_journal(app, PROJET) == avant


def test_chaine_de_renommages_rejouee(
    app: FastAPI, range_: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    creer_projet(range_)
    composant(range_, "beta", "TME")
    vraie = propagation.synchroniser

    def sans_beta(projet: Path, *args: object, **kwargs: object) -> propagation.Rapport:
        if projet.parent.name == "beta":
            raise sqlite3.OperationalError("hors ligne")
        return vraie(projet, *args, **kwargs)

    monkeypatch.setattr(propagation, "synchroniser", sans_beta)
    assert range_.patch(f"/p/{ORG}/api/fournisseurs/TME", json={"nom": "TME B"}).status_code == 200
    assert (
        range_.patch(f"/p/{ORG}/api/fournisseurs/TME B", json={"nom": "TME C"}).status_code == 200
    )
    monkeypatch.setattr(propagation, "synchroniser", vraie)
    conn = _comptes(app)
    try:
        reference.propager(conn, app.state.registre, "epreuve")
    finally:
        conn.close()
    assert lire(app, "beta", CITES) == [("TME C", 1)]


def test_recreation_sous_l_ancien_nom(app: FastAPI, range_: TestClient) -> None:
    """Point 1 du débat : un projet qui entre après un renommage n'en subit pas le rejeu."""
    creer_projet(range_)
    ranger(app, "beta", {"dossier": None})
    composant(range_, "beta", "Mouser")
    assert (
        range_.patch(f"/p/{ORG}/api/fournisseurs/Mouser", json={"nom": "Mouser EU"}).status_code
        == 200
    )
    assert range_.post(f"/p/{ORG}/api/fournisseurs", json={"nom": "Mouser"}).status_code == 201
    ranger(app, "beta", {"dossier": "epreuve"})
    assert lire(app, "beta", CITES) == [("Mouser", 1)]


def test_renommage_vers_un_nom_present_fusionne(app: FastAPI, range_: TestClient) -> None:
    """Point 3 : le nouveau nom existe déjà dans le projet → les citations y passent."""
    cites = dict(lire(app, PROJET, CITES))
    assert range_.delete(f"/p/{ORG}/api/nettoyage/entites/fournisseur/Digikey").status_code == 200
    assert lire(app, PROJET, "SELECT archive FROM fournisseur WHERE nom = 'Digikey'") == [(1,)]
    reponse = range_.patch(f"/p/{ORG}/api/fournisseurs/Mouser", json={"nom": "Digikey"})
    assert reponse.status_code == 200, reponse.text
    apres = dict(lire(app, PROJET, CITES))
    assert apres["Digikey"] == cites["Digikey"] + cites["Mouser"]
    assert "Mouser" not in apres


# --- 5. Retrait de la liste ---------------------------------------------------------------------


def test_retrait_archive_ou_supprime(app: FastAPI, range_: TestClient) -> None:
    ecrire(app, PROJET, "UPDATE composant SET archive = 1 WHERE fournisseur_nom = 'TME'")
    assert range_.post(f"/p/{ORG}/api/fournisseurs", json={"nom": "Inutile"}).status_code == 201
    assert lire(app, PROJET, "SELECT nom FROM fournisseur WHERE nom = 'Inutile'") == [("Inutile",)]
    cites = lire(app, PROJET, CITES)
    for nom in ("Inutile", "TME", "Farnell"):
        reponse = range_.delete(f"/p/{ORG}/api/nettoyage/entites/fournisseur/{nom}")
        assert reponse.status_code == 200, (nom, reponse.text)
    fiches = {f["nom"]: f for f in _fiches(app, PROJET)}
    assert "Inutile" not in fiches
    assert fiches["TME"]["archive"] == 1  # cité par des composants archivés seulement
    assert fiches["Farnell"]["archive"] == 1
    assert lire(app, PROJET, CITES) == cites


def _fiches(app: FastAPI, code: str) -> list[dict]:
    conn = db.connect(base(app, code), creer=False)
    try:
        return db.fetch_all(conn, FICHES)
    finally:
        conn.close()


# --- 6. Verrou dans un projet rangé -------------------------------------------------------------


def test_liste_verrouillee_dans_un_projet(app: FastAPI, range_: TestClient) -> None:
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    avant = lire(app, PROJET, FICHES)
    for methode, adresse, corps in (
        ("POST", "/api/fournisseurs", {"nom": "Neuf"}),
        ("PATCH", "/api/fournisseurs/Farnell", {"contact": "x"}),
        ("DELETE", "/api/fournisseurs/Atelier", None),
    ):
        reponse = admin.request(methode, f"/p/{PROJET}{adresse}", json=corps)
        assert reponse.status_code in (403, 409), (adresse, reponse.text)
    assert lire(app, PROJET, FICHES) == avant
    conn = db.connect(base(app, PROJET), creer=False)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="liste de l'organisme"):
            conn.execute("UPDATE fournisseur SET contact = 'x' WHERE nom = 'Farnell'")
        with pytest.raises(import_application.LigneRefusee, match="liste de l'organisme"):
            import_application._creer_entite(conn, {"type": "fournisseur", "nom": "Neuf"}, None)
    finally:
        conn.close()


# --- 7. Droits dans la référence de l'organisme -------------------------------------------------


def test_droits_sur_la_liste(app: FastAPI, range_: TestClient) -> None:
    assert range_.post(f"/p/{ORG}/api/fournisseurs", json={"nom": "Proposé"}).status_code == 201
    ecrire(app, ORG, "UPDATE fournisseur SET statut = 'A valider' WHERE nom = 'Proposé'")
    membre_organisme(app, "achats@ecole.test", "meca", "achats_stock")
    achats = connecter(app, "achats@ecole.test")
    valide = achats.patch(f"/p/{ORG}/api/fournisseurs/Proposé", json={"statut": "Valide"})
    assert valide.status_code == 200, valide.text
    assert achats.get(f"/p/{ORG}/api/composants").status_code == 404
    assert achats.get(f"/p/{ORG}/api/sauvegardes").status_code == 404
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    lecture = connecter(app, "lecture@ecole.test")
    assert lecture.get(f"/p/{ORG}/api/fournisseurs").status_code == 200
    assert (
        lecture.patch(f"/p/{ORG}/api/fournisseurs/Farnell", json={"contact": "x"}).status_code
        == 403
    )
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin_projet = connecter(app, "admin@ecole.test")
    assert admin_projet.get(f"/p/{ORG}/api/fournisseurs").status_code == 403


# --- Reprise d'un organisme d'avant les fournisseurs communs (point 2) -------------------------


def test_reprise_d_un_organisme_existant(app: FastAPI, range_: TestClient) -> None:
    creer_projet(range_)
    ecrire(app, "beta", "INSERT INTO fournisseur (nom) VALUES ('Propre à beta')")
    # L'organisme perd sa liste, comme avant la migration 006.
    conn = _comptes(app)
    try:
        with db.transaction(conn):
            conn.execute("DELETE FROM projet WHERE code = ?", (ORG,))
        emp = app.state.registre.projets.pop(ORG)
        shutil.rmtree(emp.base.parent)
        shutil.rmtree(emp.echange, ignore_errors=True)
        reference.reprendre(
            conn, app.state.registre, (app.state.dossier_data, app.state.dossier_echange)
        )
    finally:
        conn.close()
    noms = {f[0] for f in lire(app, ORG, FICHES)}
    assert "Propre à beta" in noms
    for code in (PROJET, "beta"):
        assert {f[0] for f in lire(app, code, FICHES)} == noms
        assert lire(app, code, "SELECT COUNT(*) FROM fournisseur WHERE archive = 1") == [(0,)]
