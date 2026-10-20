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


def _ecrire(racine: Path, fichiers: dict[str, bytes]) -> None:
    for relatif, contenu in fichiers.items():
        (racine / relatif).parent.mkdir(parents=True, exist_ok=True)
        (racine / relatif).write_bytes(contenu)


def _contenu(racine: Path) -> dict[str, bytes]:
    return {
        chemin.relative_to(racine).as_posix(): chemin.read_bytes()
        for chemin in racine.rglob("*")
        if chemin.is_file()
    }


def _script(fonction: str, argument: Path, donnees: Path) -> None:
    script = config.RACINE / "deploiement" / "mettre_a_jour.sh"
    environnement = {**os.environ, "NOMENTRACE_BASE": str(donnees / "nomentrace.db")}
    environnement.pop("NOMENTRACE_DATA", None)
    commande = f'source "{script}" && {fonction} "{argument}"'
    subprocess.run([BASH, "-c", commande], env=environnement, check=True)


AVANT = {
    "nomentrace.db": b"ancienne",
    "comptes.db": b"comptes avant",
    "projets/principal/nomentrace.db": b"projet avant",
    "projets/principal/nomentrace.db-wal": b"wal avant",
}


@pytest.mark.skipif(BASH is None, reason="scripts de déploiement : Linux seulement")
def test_mise_a_jour_copie_toutes_les_bases(tmp_path: Path) -> None:
    """Depuis la phase 15a-2, une base par projet : la copie prend tout le dossier."""
    donnees = tmp_path / "data"
    _ecrire(donnees, AVANT)
    _script("copier_bases", tmp_path / "instantane", donnees)
    assert _contenu(tmp_path / "instantane" / "donnees") == AVANT


@pytest.mark.skipif(BASH is None, reason="scripts de déploiement : Linux seulement")
def test_retour_arriere_garde_les_droits_du_dossier_des_donnees(tmp_path: Path) -> None:
    """Bug évité : le retour arrière d'une mise à jour copiait « instantane/base/. » dans le
    dossier des données, qui prenait alors le propriétaire et les droits du dossier de
    copie ; SQLite ne pouvait plus y écrire et le service ne redémarrait pas. Et rien de ce
    qu'a créé la version défaite ne reste, sans imbriquer projets/ dans projets/."""
    donnees = tmp_path / "data"
    donnees.mkdir()
    donnees.chmod(0o750)
    instantane = tmp_path / "instantane"
    _ecrire(instantane / "donnees", AVANT)
    (instantane / "donnees").chmod(0o700)
    _ecrire(
        donnees,
        {
            "nomentrace.db": b"ancienne marquee",
            "comptes.db": b"comptes apres",
            "projets/principal/nomentrace.db": b"projet apres",
            "projets/neuf/nomentrace.db": b"cree par la version defaite",
        },
    )
    _script("remettre_bases", instantane, donnees)
    assert stat.S_IMODE(donnees.stat().st_mode) == 0o750
    assert _contenu(donnees) == AVANT
