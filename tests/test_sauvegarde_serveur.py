"""Sauvegarde nocturne et restauration sur le serveur : `python -m backend.sauvegarde`."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from backend import config, db
from backend import sauvegarde as ligne_de_commande
from backend.erreurs import ErreurMetier
from backend.services import comptes, restauration


@pytest.fixture
def instance(
    conn_essai: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Instance de serveur sur le jeu d'essai : base, comptes et documents temporaires."""
    chemin_base = Path(conn_essai.execute("PRAGMA database_list").fetchone()["file"])
    conn_essai.close()
    echange = tmp_path / "echange"
    monkeypatch.setattr(config, "CHEMIN_BASE", chemin_base)
    monkeypatch.setattr(config, "CHEMIN_COMPTES", tmp_path / "comptes.db")
    monkeypatch.setattr(config, "DOSSIER_ECHANGE", echange)
    monkeypatch.setattr(config, "DOSSIER_SAUVEGARDES", echange / "sauvegardes")
    comptes.prepare_base(config.CHEMIN_COMPTES)
    conn = db.connect(config.CHEMIN_COMPTES)
    comptes.ensure_admin(conn, "essai", "chef@ecole.test", "Chef")
    conn.close()
    (echange / "documents" / "commandes").mkdir(parents=True)
    (echange / "documents" / "commandes" / "devis.pdf").write_bytes(b"%PDF devis")
    (echange / "documents" / "_corbeille").mkdir()
    (echange / "documents" / "_corbeille" / "abc123").write_bytes(b"%PDF ancien")
    monkeypatch.setattr(ligne_de_commande, "serveur_actif", lambda hote, port: False)
    return tmp_path


REQUETES_COMPTE = {
    "composant": "SELECT COUNT(*) FROM composant",
    "utilisateur": "SELECT COUNT(*) FROM utilisateur",
}


def _compter(chemin: Path, table: str) -> int:
    conn = sqlite3.connect(chemin)
    try:
        return conn.execute(REQUETES_COMPTE[table]).fetchone()[0]
    finally:
        conn.close()


def test_archive_serveur_complete(instance: Path) -> None:
    cible = instance / "sortie" / "nuit.zip"
    assert ligne_de_commande.main(["archive", str(cible)]) == 0
    with zipfile.ZipFile(cible) as archive:
        noms = set(archive.namelist())
    assert {"nomentrace.db", "comptes.db"} <= noms
    # La corbeille voyage avec les documents : une restauration ne perd aucun fichier.
    assert {"documents/commandes/devis.pdf", "documents/_corbeille/abc123"} <= noms


def test_restaurer_remet_bases_et_documents(instance: Path) -> None:
    cible = instance / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    # Après la sauvegarde : un composant en moins, un compte en plus, un document changé.
    conn = db.connect(config.CHEMIN_BASE)
    conn.execute("DELETE FROM affectation WHERE composant_id = 'ESSAI-IHM-001'")
    conn.execute("DELETE FROM composant WHERE id = 'ESSAI-IHM-001'")
    conn.close()
    conn = db.connect(config.CHEMIN_COMPTES)
    comptes.ensure_admin(conn, "essai", "autre@ecole.test", "Autre")
    conn.close()
    documents = config.DOSSIER_ECHANGE / "documents"
    (documents / "commandes" / "nouveau.pdf").write_bytes(b"%PDF nouveau")

    assert ligne_de_commande.main(["restaurer", str(cible)]) == 0

    assert _compter(config.CHEMIN_BASE, "composant") == 60
    assert _compter(config.CHEMIN_COMPTES, "utilisateur") == 1
    assert not (documents / "commandes" / "nouveau.pdf").exists()
    assert (documents / "_corbeille" / "abc123").read_bytes() == b"%PDF ancien"
    # Rien n'est perdu : les documents courants sont mis de côté, les bases sauvegardées.
    mis_de_cote = list(config.DOSSIER_ECHANGE.glob("documents_avant_restauration_*"))
    assert len(mis_de_cote) == 1
    assert (mis_de_cote[0] / "commandes" / "nouveau.pdf").is_file()
    assert list(config.DOSSIER_SAUVEGARDES.glob("nomentrace_*.db"))
    assert list((config.DOSSIER_SAUVEGARDES / "comptes").glob("nomentrace_*.db"))


def test_restaurer_sans_documents(instance: Path) -> None:
    cible = instance / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    documents = config.DOSSIER_ECHANGE / "documents"
    (documents / "commandes" / "nouveau.pdf").write_bytes(b"%PDF nouveau")
    assert ligne_de_commande.main(["restaurer", str(cible), "--sans-documents"]) == 0
    assert (documents / "commandes" / "nouveau.pdf").is_file()
    assert not list(config.DOSSIER_ECHANGE.glob("documents_avant_restauration_*"))


def test_restaurer_refuse_si_le_service_tourne(
    instance: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cible = instance / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    monkeypatch.setattr(ligne_de_commande, "serveur_actif", lambda hote, port: True)
    assert ligne_de_commande.main(["restaurer", str(cible)]) == 1
    assert "Arrêter le service" in capsys.readouterr().err


@pytest.mark.parametrize(
    "contenu",
    [
        {"nomentrace.db": b"", "../hors.txt": b"x"},
        {"nomentrace.db": b"", "/etc/hors.txt": b"x"},
        {"documents/a.pdf": b"x"},
        {"nomentrace.db": b"pas une base"},
    ],
)
def test_archive_suspecte_refusee(instance: Path, contenu: dict[str, bytes]) -> None:
    piege = instance / "piege.zip"
    with zipfile.ZipFile(piege, "w") as archive:
        for nom, donnees in contenu.items():
            archive.writestr(nom, donnees)
    avant = _compter(config.CHEMIN_BASE, "composant")
    with pytest.raises(ErreurMetier):
        restauration.restore_archive(
            piege,
            config.CHEMIN_BASE,
            config.CHEMIN_COMPTES,
            config.DOSSIER_SAUVEGARDES,
            config.DOSSIER_ECHANGE / "documents",
        )
    assert _compter(config.CHEMIN_BASE, "composant") == avant
    assert not (instance / "hors.txt").exists()


def test_version_anterieure_refuse_un_schema_plus_recent(tmp_path: Path) -> None:
    """Bug évité : après un retour à une version antérieure, l'ancien code démarrait sur une
    base déjà migrée par la version suivante et la lisait de travers."""
    base = tmp_path / "base.db"
    conn = db.connect(base)
    db.apply_migrations(conn)
    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations():
        if numero <= 5:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    with pytest.raises(db.SchemaTropRecent, match="plus récent"):
        db.apply_migrations(conn, anciennes)
    conn.close()
