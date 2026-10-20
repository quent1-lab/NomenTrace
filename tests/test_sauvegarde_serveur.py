"""Sauvegarde nocturne et restauration sur le serveur : `python -m backend.sauvegarde`."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from backend import config, db
from backend import sauvegarde as ligne_de_commande
from backend.erreurs import ErreurMetier
from backend.services import comptes, projets, restauration


@pytest.fixture
def instance(
    conn_essai: sqlite3.Connection,
    chemin_base: Path,
    dossier_data: Path,
    dossier_echange: Path,
    echange_projet: Path,
    code_projet: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Instance de serveur sur le jeu d'essai : projet inscrit, comptes et documents."""
    conn_essai.close()
    monkeypatch.setattr(config, "DOSSIER_DATA", dossier_data)
    monkeypatch.setattr(config, "CHEMIN_ANCIENNE_BASE", dossier_data / "nomentrace.db")
    monkeypatch.setattr(config, "CHEMIN_COMPTES", dossier_data / "comptes.db")
    monkeypatch.setattr(config, "DOSSIER_ECHANGE", dossier_echange)
    comptes.prepare_base(config.CHEMIN_COMPTES)
    conn = db.connect(config.CHEMIN_COMPTES)
    comptes.ensure_admin(conn, code_projet, "chef@ecole.test", "Chef")
    projets.inscrire(conn, code_projet)
    conn.close()
    documents = echange_projet / "documents"
    (documents / "commandes").mkdir(parents=True)
    (documents / "commandes" / "devis.pdf").write_bytes(b"%PDF devis")
    (documents / "_corbeille").mkdir()
    (documents / "_corbeille" / "abc123").write_bytes(b"%PDF ancien")
    monkeypatch.setattr(ligne_de_commande, "serveur_actif", lambda hote, port: False)
    return chemin_base


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


def _cible() -> restauration.Cible:
    return restauration.Cible(
        config.CHEMIN_COMPTES,
        config.DOSSIER_DATA,
        config.DOSSIER_ECHANGE,
        config.CHEMIN_ANCIENNE_BASE,
    )


def _inscrits() -> list[str]:
    conn = db.connect(config.CHEMIN_COMPTES)
    try:
        return projets.list_codes(conn)
    finally:
        conn.close()


def test_archive_serveur_complete(instance: Path, tmp_path: Path, code_projet: str) -> None:
    cible = tmp_path / "sortie" / "nuit.zip"
    assert ligne_de_commande.main(["archive", str(cible)]) == 0
    racine = f"projets/{code_projet}"
    with zipfile.ZipFile(cible) as archive:
        noms = set(archive.namelist())
    assert {"comptes.db", f"{racine}/nomentrace.db"} <= noms
    # La corbeille voyage avec les documents : une restauration ne perd aucun fichier.
    assert {
        f"{racine}/documents/commandes/devis.pdf",
        f"{racine}/documents/_corbeille/abc123",
    } <= noms


def test_restaurer_remet_bases_et_documents(
    instance: Path, tmp_path: Path, echange_projet: Path, code_projet: str
) -> None:
    cible = tmp_path / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    # Après la sauvegarde : un composant en moins, un compte en plus, un document changé.
    conn = db.connect(instance)
    conn.execute("DELETE FROM affectation WHERE composant_id = 'ESSAI-IHM-001'")
    conn.execute("DELETE FROM composant WHERE id = 'ESSAI-IHM-001'")
    conn.close()
    conn = db.connect(config.CHEMIN_COMPTES)
    comptes.ensure_admin(conn, code_projet, "autre@ecole.test", "Autre")
    conn.close()
    documents = echange_projet / "documents"
    (documents / "commandes" / "nouveau.pdf").write_bytes(b"%PDF nouveau")

    assert ligne_de_commande.main(["restaurer", str(cible)]) == 0

    assert _compter(instance, "composant") == 60
    assert _compter(config.CHEMIN_COMPTES, "utilisateur") == 1
    assert not (documents / "commandes" / "nouveau.pdf").exists()
    assert (documents / "_corbeille" / "abc123").read_bytes() == b"%PDF ancien"
    # Rien n'est perdu : les documents courants sont mis de côté, les bases sauvegardées.
    mis_de_cote = list(echange_projet.glob("documents_avant_restauration_*"))
    assert len(mis_de_cote) == 1
    assert (mis_de_cote[0] / "commandes" / "nouveau.pdf").is_file()
    assert list((echange_projet / "sauvegardes").glob("nomentrace_*.db"))
    assert list((config.DOSSIER_ECHANGE / "sauvegardes" / "comptes").glob("nomentrace_*.db"))
    assert _inscrits() == [code_projet]


def test_restaurer_sans_documents(instance: Path, tmp_path: Path, echange_projet: Path) -> None:
    cible = tmp_path / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    documents = echange_projet / "documents"
    (documents / "commandes" / "nouveau.pdf").write_bytes(b"%PDF nouveau")
    assert ligne_de_commande.main(["restaurer", str(cible), "--sans-documents"]) == 0
    assert (documents / "commandes" / "nouveau.pdf").is_file()
    assert not list(echange_projet.glob("documents_avant_restauration_*"))


def test_restaurer_refuse_si_le_service_tourne(
    instance: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cible = tmp_path / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    monkeypatch.setattr(ligne_de_commande, "serveur_actif", lambda hote, port: True)
    assert ligne_de_commande.main(["restaurer", str(cible)]) == 1
    assert "Arrêter le service" in capsys.readouterr().err


def test_archive_v2_restauree_sur_une_instance_vide(
    instance: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code_projet: str
) -> None:
    cible = tmp_path / "nuit.zip"
    ligne_de_commande.main(["archive", str(cible)])
    vide = tmp_path / "neuve"
    monkeypatch.setattr(config, "DOSSIER_DATA", vide / "data")
    monkeypatch.setattr(config, "CHEMIN_ANCIENNE_BASE", vide / "data" / "nomentrace.db")
    monkeypatch.setattr(config, "CHEMIN_COMPTES", vide / "data" / "comptes.db")
    monkeypatch.setattr(config, "DOSSIER_ECHANGE", vide / "echange")
    assert ligne_de_commande.main(["restaurer", str(cible)]) == 0
    base = vide / "data" / "projets" / code_projet / "nomentrace.db"
    assert _compter(base, "composant") == 60
    assert _compter(config.CHEMIN_COMPTES, "utilisateur") == 1
    devis = vide / "echange" / "projets" / code_projet / "documents" / "commandes" / "devis.pdf"
    assert devis.read_bytes() == b"%PDF devis"
    assert _inscrits() == [code_projet]
    assert not config.CHEMIN_ANCIENNE_BASE.exists()


def _archive_v1(chemin: Path, base: Path, avec_comptes_anciens: Path | None) -> None:
    """Archive au format d'avant la phase 15a-2 : base et documents à la racine."""
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.write(base, "nomentrace.db")
        archive.writestr("documents/commandes/ancien.pdf", b"%PDF v1")
        if avec_comptes_anciens is not None:
            archive.write(avec_comptes_anciens, "comptes.db")


def _comptes_v1(chemin: Path, code: str) -> None:
    """Base des comptes au schéma d'avant le registre des projets (migrations 001 et 002)."""
    anciennes = chemin.parent / "migrations_v1"
    anciennes.mkdir()
    for numero, fichier in db.list_migrations(config.DOSSIER_MIGRATIONS_COMPTES):
        if numero <= 2:
            (anciennes / fichier.name).write_bytes(fichier.read_bytes())
    conn = db.connect(chemin)
    db.apply_migrations(conn, anciennes)
    conn.close()


def test_archive_v1_va_au_projet_et_garde_le_registre(
    instance: Path, tmp_path: Path, echange_projet: Path, code_projet: str
) -> None:
    """Les archives nocturnes d'avant 15a-2 restent restaurables : la base va au projet de
    l'instance, jamais à l'ancienne base, et un second projet inscrit reste inscrit."""
    conn = db.connect(config.CHEMIN_COMPTES)
    projets.inscrire(conn, "second")
    conn.close()
    ancienne = config.CHEMIN_ANCIENNE_BASE
    copie = tmp_path / "copie_v1.db"
    destination = sqlite3.connect(copie)
    sqlite3.connect(instance).backup(destination)
    destination.close()
    comptes_v1 = tmp_path / "v1" / "comptes.db"
    comptes_v1.parent.mkdir()
    _comptes_v1(comptes_v1, code_projet)
    archive = tmp_path / "nuit_v1.zip"
    _archive_v1(archive, copie, comptes_v1)
    conn = db.connect(instance)
    conn.execute("DELETE FROM affectation WHERE composant_id = 'ESSAI-IHM-001'")
    conn.execute("DELETE FROM composant WHERE id = 'ESSAI-IHM-001'")
    conn.close()

    assert ligne_de_commande.main(["restaurer", str(archive)]) == 0

    assert _compter(instance, "composant") == 60
    assert not ancienne.exists()
    assert (echange_projet / "documents" / "commandes" / "ancien.pdf").read_bytes() == b"%PDF v1"
    assert _inscrits() == sorted([code_projet, "second"])


def test_archive_v1_marque_une_ancienne_base_non_recopiee(instance: Path, tmp_path: Path) -> None:
    """Restaurer sur un serveur pas encore migré : l'archive fait foi, l'ancienne base est
    marquée pour ne pas être recopiée par-dessus au démarrage suivant."""
    ancienne = config.CHEMIN_ANCIENNE_BASE
    destination = sqlite3.connect(ancienne)
    sqlite3.connect(instance).backup(destination)
    destination.close()
    archive = tmp_path / "nuit_v1.zip"
    _archive_v1(archive, instance, None)
    assert not projets.est_marquee(ancienne)
    assert ligne_de_commande.main(["restaurer", str(archive)]) == 0
    assert projets.est_marquee(ancienne)


@pytest.mark.parametrize(
    "contenu",
    [
        {"nomentrace.db": b"", "../hors.txt": b"x"},
        {"nomentrace.db": b"", "/etc/hors.txt": b"x"},
        {"documents/a.pdf": b"x"},
        {"nomentrace.db": b"pas une base"},
        {"projets/Majuscule/nomentrace.db": b""},
        {"projets/x/nomentrace.db": b"pas une base"},
    ],
)
def test_archive_suspecte_refusee(
    instance: Path, tmp_path: Path, code_projet: str, contenu: dict[str, bytes]
) -> None:
    piege = tmp_path / "piege.zip"
    with zipfile.ZipFile(piege, "w") as archive:
        for nom, donnees in contenu.items():
            archive.writestr(nom, donnees)
    avant = _compter(instance, "composant")
    with pytest.raises(ErreurMetier):
        restauration.restore_archive(piege, _cible(), code_projet)
    assert _compter(instance, "composant") == avant
    assert not (tmp_path / "hors.txt").exists()
    assert _inscrits() == [code_projet]


def test_archive_aux_deux_formats_refusee(instance: Path, tmp_path: Path, code_projet: str) -> None:
    piege = tmp_path / "mele.zip"
    with zipfile.ZipFile(piege, "w") as archive:
        archive.write(instance, "nomentrace.db")
        archive.write(instance, f"projets/{code_projet}/nomentrace.db")
    with pytest.raises(ErreurMetier, match="deux formats"):
        restauration.restore_archive(piege, _cible(), code_projet)


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
