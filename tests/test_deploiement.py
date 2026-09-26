"""Fichiers de déploiement : ce que pytest peut contrôler sans machine Linux."""

import configparser
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from backend import config

SYSTEMD = config.RACINE / "deploiement" / "systemd"
DONNEES = "/var/lib/nomentrace"


def _service(chemin: Path) -> configparser.SectionProxy:
    lecteur = configparser.ConfigParser(strict=False, interpolation=None)
    lecteur.optionxform = str  # les clés systemd sont sensibles à la casse
    lecteur.read(chemin, encoding="utf-8")
    return lecteur["Service"]


@pytest.mark.parametrize("nom", ["nomentrace.service", "nomentrace-sauvegarde.service"])
def test_les_services_peuvent_ecrire_dans_les_donnees(nom: str) -> None:
    """Bug évité : la sauvegarde nocturne montait les données en lecture seule, et SQLite en
    mode WAL, qui écrit son fichier -shm même pour lire, refusait d'ouvrir la base."""
    service = _service(SYSTEMD / nom)
    assert service.get("ProtectSystem") == "strict"
    assert DONNEES in service.get("ReadWritePaths", "").split()
    assert DONNEES not in service.get("ReadOnlyPaths", "").split()


BASH = shutil.which("bash") if sys.platform != "win32" else None


@pytest.mark.skipif(BASH is None, reason="scripts de déploiement : Linux seulement")
def test_retour_arriere_garde_les_droits_du_dossier_des_donnees(tmp_path: Path) -> None:
    """Bug évité : le retour arrière d'une mise à jour copiait « instantane/base/. » dans le
    dossier des données, qui prenait alors le propriétaire et les droits du dossier de
    copie ; SQLite ne pouvait plus y écrire et le service ne redémarrait pas."""
    donnees = tmp_path / "data"
    donnees.mkdir()
    donnees.chmod(0o750)
    (donnees / "nomentrace.db").write_bytes(b"apres")
    (donnees / "nomentrace.db-wal").write_bytes(b"wal")
    (donnees / "comptes.db").write_bytes(b"comptes apres")
    instantane = tmp_path / "instantane"
    (instantane / "base").mkdir(parents=True)
    (instantane / "comptes").mkdir()
    (instantane / "base").chmod(0o700)
    (instantane / "base" / "nomentrace.db").write_bytes(b"avant")
    (instantane / "comptes" / "comptes.db").write_bytes(b"comptes avant")
    script = config.RACINE / "deploiement" / "mettre_a_jour.sh"
    commande = f'source "{script}" && remettre_bases "{instantane}"'
    environnement = {
        **os.environ,
        "NOMENTRACE_BASE": str(donnees / "nomentrace.db"),
        "NOMENTRACE_COMPTES": str(donnees / "comptes.db"),
    }
    subprocess.run([BASH, "-c", commande], env=environnement, check=True)
    assert stat.S_IMODE(donnees.stat().st_mode) == 0o750
    assert (donnees / "nomentrace.db").read_bytes() == b"avant"
    assert (donnees / "comptes.db").read_bytes() == b"comptes avant"
    assert not (donnees / "nomentrace.db-wal").exists()
