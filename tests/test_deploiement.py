"""Fichiers de déploiement : ce que pytest peut contrôler sans machine Linux."""

import configparser
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
