"""Base par projet (phase 15a-2) : migration de l'ancienne base unique, registre, isolement.

Une « ancienne instance » reproduit la disposition d'avant 15a-2 : une base remplie à la
racine des données et un dossier d'échange à plat (documents, corbeille, imports,
sauvegardes du projet et des comptes).
"""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config, db
from backend.erreurs import ErreurMetier
from backend.main import create_app
from backend.services import comptes, documents, projets
from tests.conftest import client_local
from tests.jeu_essai import charger_jeu_essai

CODE = config.CODE_PROJET
PDF = b"%PDF-1.4 fiche technique"


@contextmanager
def demarrer(tmp_path: Path) -> Iterator[TestClient]:
    """Démarre l'application (mode local) sur les données et l'échange de tmp_path."""
    app = create_app(tmp_path / "data", tmp_path / "echange", mode_local=True)
    with client_local(app) as client:
        yield client


def _empreinte(chemin: Path) -> dict:
    """Ce qui doit survivre à la copie : lignes par table, séquences, vues, déclencheurs."""
    conn = sqlite3.connect(f"{chemin.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [
            ligne[0]
            for ligne in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name <> 'schema_version'"
            )
        ]
        return {
            "lignes": {
                t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # noqa: S608
                for t in tables
            },
            "sequences": sorted(conn.execute("SELECT name, seq FROM sqlite_sequence").fetchall()),
            "objets": conn.execute(
                "SELECT type, COUNT(*) FROM sqlite_master GROUP BY type ORDER BY type"
            ).fetchall(),
            "integrite": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "blocs": conn.execute("SELECT code FROM bloc ORDER BY code").fetchall(),
        }
    finally:
        conn.close()


@pytest.fixture
def ancienne(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Ancienne instance remplie ; la connexion rendue garde une écriture dans le WAL."""
    base = tmp_path / "data" / "nomentrace.db"
    echange = tmp_path / "echange"
    conn = db.connect(base)
    db.apply_migrations(conn)
    charger_jeu_essai(conn)
    for identifiant in ("ESSAI-IHM-001", "ESSAI-ALI-001"):
        meta = {"composant_id": identifiant, "type_document": "Fiche technique"}
        documents.add_documents(conn, echange / "documents", [(f"{identifiant}.pdf", PDF)], meta)
    (echange / "documents" / "_corbeille").mkdir()
    (echange / "documents" / "_corbeille" / "abc_vieux.pdf").write_bytes(b"%PDF corbeille")
    (echange / "imports").mkdir()
    (echange / "imports" / "lot.xlsx").write_bytes(b"classeur")
    (echange / "sauvegardes" / "comptes").mkdir(parents=True)
    (echange / "sauvegardes" / "comptes" / "nomentrace_20260101_000000.db").write_bytes(b"c")
    (echange / "sauvegardes" / "nomentrace_20260101_000000.db").write_bytes(b"p")
    # Écriture restée dans le journal WAL : une copie du seul fichier principal la perdrait.
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("INSERT INTO bloc (code, nom) VALUES ('WAL', 'Dans le journal')")
    yield conn
    conn.close()


def _projet(tmp_path: Path, code: str = CODE) -> projets.EmplacementsProjet:
    return projets.emplacements(tmp_path / "data", tmp_path / "echange", code)


def _mis_de_cote(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "data" / "projets").glob("*_avant_migration_*"))


# --- Migration de l'ancienne base -----------------------------------------------------------


def test_migration_recopie_tout(ancienne: sqlite3.Connection, tmp_path: Path) -> None:
    base_ancienne = tmp_path / "data" / "nomentrace.db"
    attendu = _empreinte(base_ancienne)
    assert ("WAL",) in attendu["blocs"]
    fiches = db.fetch_all(ancienne, "SELECT chemin FROM document")
    emp = _projet(tmp_path)
    with demarrer(tmp_path) as client:
        composants = client.get(f"/p/{CODE}/api/composants").json()
    assert _empreinte(emp.base) == attendu
    assert len(composants) == 60
    assert len(fiches) == 2
    for fiche in fiches:
        assert (emp.documents / fiche["chemin"]).read_bytes() == PDF
    assert (emp.documents / "_corbeille" / "abc_vieux.pdf").read_bytes() == b"%PDF corbeille"
    assert (emp.imports / "lot.xlsx").is_file()
    assert (emp.sauvegardes / "nomentrace_20260101_000000.db").is_file()
    assert not (emp.sauvegardes / "comptes").exists()
    # L'ancien code refuse désormais l'ancienne base ; l'ancien échange n'est pas touché.
    assert projets.est_marquee(base_ancienne)
    with pytest.raises(db.SchemaTropRecent):
        db.apply_migrations(ancienne)
    assert (tmp_path / "echange" / "documents" / fiches[0]["chemin"]).is_file()


def test_plus_rien_ne_passe_par_l_ancienne_base(
    ancienne: sqlite3.Connection, tmp_path: Path
) -> None:
    """Après la migration, l'ancienne base et l'ancien échange retirés : chaque route qui
    touche aux fichiers marche, et rien ne recrée l'ancienne base."""
    ancienne.close()
    base_ancienne = tmp_path / "data" / "nomentrace.db"
    with demarrer(tmp_path):
        pass
    base_ancienne.unlink()
    for nom in ("documents", "imports", "modeles", "sauvegardes", "exports"):
        shutil.rmtree(tmp_path / "echange" / nom, ignore_errors=True)
    p = f"/p/{CODE}/api"
    with demarrer(tmp_path) as client:
        assert client.post(f"{p}/blocs", json={"code": "OPT", "nom": "Optique"}).status_code == 201
        envoi = client.post(
            f"{p}/composants/ESSAI-IHM-001/documents",
            files={"fichiers": ("plan.pdf", PDF + b" plan", "application/pdf")},
            data={"type_document": "Plan"},
        )
        assert envoi.status_code == 201, envoi.text
        identifiant = envoi.json()["documents"][0]["id"]
        assert client.get(f"{p}/documents/{identifiant}/fichier").content == PDF + b" plan"
        for adresse in (f"{p}/export/classeur", f"{p}/modeles/vierge", f"{p}/sauvegardes/archive"):
            assert client.get(adresse).status_code == 200, adresse
        assert client.post(f"{p}/sauvegardes").status_code == 201
        assert client.post(f"{p}/export").status_code == 200
    assert not base_ancienne.exists()
    assert not (tmp_path / "echange" / "documents").exists()
    assert (_projet(tmp_path).exports / "nomenclature.xlsx").is_file()


def test_migration_interrompue_puis_rejouee(
    ancienne: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attendu = _empreinte(tmp_path / "data" / "nomentrace.db")

    def panne(_: Path) -> None:
        raise OSError("panne simulée avant le marquage")

    monkeypatch.setattr(projets, "_marquer", panne)
    with pytest.raises(OSError, match="panne simulée"), demarrer(tmp_path):
        pass
    monkeypatch.undo()
    with demarrer(tmp_path) as client:
        assert client.get(f"/p/{CODE}/api/sante").status_code == 200
    assert _empreinte(_projet(tmp_path).base) == attendu
    # La copie de la tentative est mise de côté, pas effacée.
    assert len(_mis_de_cote(tmp_path)) == 1


def test_copie_qui_echoue_ne_s_accumule_pas(
    ancienne: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relances en boucle (systemd) d'une copie qui échoue : une seule copie partielle."""

    def panne(*_: object) -> None:
        raise OSError("disque plein simulé")

    monkeypatch.setattr(projets, "_copier_echange", panne)
    for _ in range(3):
        with pytest.raises(OSError, match="disque plein"), demarrer(tmp_path):
            pass
    restes = sorted(chemin.name for chemin in (tmp_path / "data" / "projets").iterdir())
    assert restes == [f".migration-{CODE}"]
    assert not projets.est_marquee(tmp_path / "data" / "nomentrace.db")


def test_retour_arriere_v19_puis_nouvelle_migration(
    ancienne: sqlite3.Connection, tmp_path: Path
) -> None:
    """Le script v1.9 remet l'ancienne base et l'ancienne base commune ; l'ancien code y
    écrit ; la migration suivante doit repartir de l'ancienne base."""
    ancienne.close()
    base_ancienne = tmp_path / "data" / "nomentrace.db"
    instantane = tmp_path / "instantane.db"
    shutil.copy(base_ancienne, instantane)
    with demarrer(tmp_path):
        pass
    shutil.copy(instantane, base_ancienne)
    (tmp_path / "data" / "comptes.db").unlink()
    conn = db.connect(base_ancienne)
    conn.execute("INSERT INTO bloc (code, nom) VALUES ('RET', 'Écrit après le retour')")
    conn.close()
    with demarrer(tmp_path) as client:
        codes = [b["code"] for b in client.get(f"/p/{CODE}/api/blocs").json()]
    assert "RET" in codes
    assert len(_mis_de_cote(tmp_path)) == 1


def test_second_demarrage_ne_recopie_pas(ancienne: sqlite3.Connection, tmp_path: Path) -> None:
    ancienne.close()
    with demarrer(tmp_path) as client:
        client.post(f"/p/{CODE}/api/blocs", json={"code": "OPT", "nom": "Optique"})
    with demarrer(tmp_path) as client:
        codes = [b["code"] for b in client.get(f"/p/{CODE}/api/blocs").json()]
    assert "OPT" in codes
    assert _mis_de_cote(tmp_path) == []


def test_ancienne_base_non_marquee_et_projet_inscrit_refus(
    ancienne: sqlite3.Connection, tmp_path: Path
) -> None:
    """Marque perdue alors que le projet vit déjà : recopier écraserait ses données."""
    ancienne.close()
    with demarrer(tmp_path) as client:
        client.post(f"/p/{CODE}/api/blocs", json={"code": "OPT", "nom": "Optique"})
    conn = db.connect(tmp_path / "data" / "nomentrace.db")
    conn.execute("DELETE FROM schema_version WHERE numero = ?", (projets.MARQUE_MIGREE,))
    conn.close()
    avant = _empreinte(_projet(tmp_path).base)
    with pytest.raises(ErreurMetier, match="Refus de démarrer"), demarrer(tmp_path):
        pass
    assert _empreinte(_projet(tmp_path).base) == avant
    assert _mis_de_cote(tmp_path) == []


def test_instance_neuve(tmp_path: Path) -> None:
    with demarrer(tmp_path) as client:
        sante = client.get(f"/p/{CODE}/api/sante").json()
    derniere = max(numero for numero, _ in db.list_migrations())
    assert sante["version_schema"] == derniere
    conn = db.connect(tmp_path / "data" / "comptes.db")
    assert projets.list_codes(conn) == [CODE]
    conn.close()
    assert not (tmp_path / "data" / "nomentrace.db").exists()


def test_code_d_instance_invalide_refuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="NOMENTRACE_PROJET"):
        create_app(tmp_path / "data", tmp_path / "echange", code_projet="Équipe A")


# --- Isolement des projets ------------------------------------------------------------------


def _migrations_avec_panne(tmp_path: Path) -> Path:
    """Migrations réelles plus une 999-1 qui casse en cours sur un projet ayant le bloc OPT."""
    dossier = tmp_path / "migrations"
    dossier.mkdir()
    for _, fichier in db.list_migrations():
        shutil.copy(fichier, dossier / fichier.name)
    derniere = max(numero for numero, _ in db.list_migrations())
    (dossier / f"{derniere + 1:03d}_panne.sql").write_text(
        "CREATE TABLE trace_panne (code TEXT UNIQUE);\n"
        "INSERT INTO trace_panne SELECT code FROM bloc;\n"
        "INSERT INTO trace_panne VALUES ('OPT');\n",
        encoding="utf-8",
    )
    return dossier


def _deux_projets(tmp_path: Path, en_panne: str) -> None:
    """Projet de l'instance et projet « second », celui `en_panne` portant le bloc OPT."""
    comptes.prepare_base(tmp_path / "data" / "comptes.db")
    conn = db.connect(tmp_path / "data" / "comptes.db")
    for code in (CODE, "second"):
        projets.inscrire(conn, code)
        projets.creer_base(_projet(tmp_path, code))
    conn.close()
    conn = db.connect(_projet(tmp_path, en_panne).base)
    conn.execute("INSERT INTO bloc (code, nom) VALUES ('OPT', 'Optique')")
    conn.close()


def test_projet_en_echec_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _deux_projets(tmp_path, en_panne="second")
    avant = _empreinte(_projet(tmp_path, "second").base)
    monkeypatch.setattr(config, "DOSSIER_MIGRATIONS", _migrations_avec_panne(tmp_path))
    with demarrer(tmp_path) as client:
        assert client.get("/p/second/api/blocs").status_code == 503
        assert client.get(f"/p/{CODE}/api/blocs").status_code == 200
        assert client.get("/api/sante").status_code == 200
        assert client.get("/p/inconnu/api/blocs").status_code == 404
    # Migration annulée entière : la base du projet en échec est intacte.
    assert _empreinte(_projet(tmp_path, "second").base) == avant


def test_projet_de_l_instance_hors_ligne_fait_echouer_la_sante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La santé sans préfixe suit le projet de l'instance : c'est elle que le script de mise
    à jour interroge pour décider du retour arrière."""
    _deux_projets(tmp_path, en_panne=CODE)
    monkeypatch.setattr(config, "DOSSIER_MIGRATIONS", _migrations_avec_panne(tmp_path))
    with demarrer(tmp_path) as client:
        assert client.get("/api/sante").status_code == 503
        assert client.get("/p/second/api/sante").status_code == 200


def test_base_disparue_a_chaud_jamais_recreee(tmp_path: Path) -> None:
    emp = _projet(tmp_path)
    with demarrer(tmp_path) as client:
        client.app.state.exports[CODE].stop()
        for suffixe in ("", "-wal", "-shm"):
            Path(f"{emp.base}{suffixe}").unlink(missing_ok=True)
        for adresse in ("blocs", "export/classeur"):
            with pytest.raises(sqlite3.OperationalError, match="unable to open"):
                client.get(f"/p/{CODE}/api/{adresse}")
    assert not emp.base.exists()


def test_projet_inscrit_sans_base_hors_ligne(tmp_path: Path) -> None:
    _deux_projets(tmp_path, en_panne="second")
    _projet(tmp_path, "second").base.unlink()
    with demarrer(tmp_path) as client:
        assert client.get("/p/second/api/blocs").status_code == 503
    assert not _projet(tmp_path, "second").base.exists()
