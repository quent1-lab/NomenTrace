"""Retrait d'un projet : supprimé s'il est vide (dossiers à la corbeille), archivé sinon."""

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_comptes import PROJET, connecter
from tests.test_hierarchie import _comptes, creer_projet, membre_organisme
from tests.test_reference import (  # noqa: F401
    REF,
    app,
    code_projet,
    range_,
    scrypt_rapide,
)


def inscrit(app: FastAPI, code: str) -> tuple | None:  # noqa: F811
    conn = _comptes(app)
    try:
        ligne = conn.execute("SELECT code, archive FROM projet WHERE code = ?", (code,)).fetchone()
        return tuple(ligne) if ligne else None
    finally:
        conn.close()


def test_projet_vide_supprime_et_mis_a_la_corbeille(
    app: FastAPI,  # noqa: F811
    range_: TestClient,  # noqa: F811
    dossier_data: Path,
    dossier_echange: Path,
) -> None:
    creer_projet(range_)
    reponse = range_.delete("/api/projets/beta")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["action"] == "supprime"
    assert inscrit(app, "beta") is None
    assert "beta" not in app.state.registre.projets
    assert not (dossier_data / "projets" / "beta").exists()
    bases = list((dossier_data / "projets" / "_corbeille").glob("beta_*/nomentrace.db"))
    assert len(bases) == 1
    sauvegardes = list((dossier_echange / "projets" / "_corbeille").glob("beta_*/sauvegardes/*.db"))
    assert sauvegardes, "une sauvegarde est prise avant la suppression"
    assert range_.get("/p/beta/api/sante").status_code == 404
    # Le code est de nouveau libre.
    creer_projet(range_)
    assert inscrit(app, "beta") == ("beta", 0)


def test_projet_avec_composants_archive(app: FastAPI, range_: TestClient) -> None:  # noqa: F811
    base = app.state.registre.projets[PROJET].base
    reponse = range_.delete(f"/api/projets/{PROJET}")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["action"] == "archive" and any("composant" in t for t in corps["traces"])
    assert inscrit(app, PROJET) == (PROJET, 1)
    assert PROJET not in app.state.registre.projets
    conn = sqlite3.connect(base)
    try:
        assert conn.execute("SELECT COUNT(*) FROM composant").fetchone()[0] > 0
    finally:
        conn.close()
    codes = [c["code"] for c in range_.get("/api/dossiers/epreuve").json()["projets"]]
    assert PROJET not in codes


def test_retrait_reserve_a_la_gestion(app: FastAPI, range_: TestClient) -> None:  # noqa: F811
    creer_projet(range_)
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    lecture = connecter(app, "lecture@ecole.test")
    assert lecture.delete("/api/projets/beta").status_code == 403
    assert inscrit(app, "beta") == ("beta", 0)
    assert range_.delete(f"/api/projets/{REF}").status_code in (403, 404)
    assert inscrit(app, REF) is not None


# --- Administrateur du serveur : suppression de ce qu'il veut ----------------------------------


def test_admin_serveur_supprime_un_projet_non_vide(
    app: FastAPI,  # noqa: F811
    range_: TestClient,  # noqa: F811
    dossier_data: Path,
) -> None:
    assert range_.delete(f"/api/projets/{PROJET}?confirmation=mauvais").status_code == 400
    assert inscrit(app, PROJET) == (PROJET, 0)
    reponse = range_.delete(f"/api/projets/{PROJET}?confirmation={PROJET}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["action"] == "supprime"
    assert inscrit(app, PROJET) is None
    assert list((dossier_data / "projets" / "_corbeille").glob(f"{PROJET}_*/nomentrace.db"))


def test_gestion_ne_force_pas(app: FastAPI, range_: TestClient) -> None:  # noqa: F811
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    gestion = connecter(app, "gestion@ecole.test")
    reponse = gestion.delete(f"/api/projets/{PROJET}?confirmation={PROJET}")
    assert reponse.status_code == 403
    assert inscrit(app, PROJET) == (PROJET, 0)


def test_admin_serveur_supprime_un_dossier_entier(
    app: FastAPI,  # noqa: F811
    range_: TestClient,  # noqa: F811
    dossier_data: Path,
) -> None:
    creer_projet(range_)
    assert range_.delete("/api/dossiers/epreuve").status_code == 400
    reponse = range_.delete("/api/dossiers/epreuve?confirmation=epreuve")
    assert reponse.status_code == 200, reponse.text
    assert set(reponse.json()["projets"]) == {PROJET, "beta", REF}
    for code in (PROJET, "beta", REF):
        assert inscrit(app, code) is None
        assert code not in app.state.registre.projets
    assert REF not in app.state.registre.references
    corbeille = {
        p.name.rsplit("_", 2)[0] for p in (dossier_data / "projets" / "_corbeille").iterdir()
    }
    assert {PROJET, "beta", REF} <= corbeille
    assert range_.get("/api/dossiers/epreuve").status_code == 404
    assert range_.get("/api/organismes/meca").status_code == 200


def test_admin_serveur_supprime_un_organisme_entier(
    app: FastAPI,  # noqa: F811
    range_: TestClient,  # noqa: F811
) -> None:
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    reponse = range_.delete("/api/organismes/meca?confirmation=meca")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["dossiers"] == ["epreuve"]
    assert {PROJET, REF, "org-meca"} <= set(reponse.json()["projets"])
    assert range_.get("/api/organismes/meca").status_code == 404
    conn = _comptes(app)
    try:
        assert conn.execute("SELECT COUNT(*) FROM acces_organisme").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM projet").fetchone()[0] == 0
    finally:
        conn.close()


def test_suppression_de_dossier_reservee_au_serveur(app: FastAPI, range_: TestClient) -> None:  # noqa: F811
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    gestion = connecter(app, "gestion@ecole.test")
    assert gestion.delete("/api/dossiers/epreuve?confirmation=epreuve").status_code == 403
    assert gestion.delete("/api/organismes/meca?confirmation=meca").status_code == 403
    assert inscrit(app, PROJET) == (PROJET, 0)
