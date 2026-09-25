"""Chemins et constantes de Nomentrace, surchargeables par variables d'environnement."""

import os
from pathlib import Path

RACINE: Path = Path(__file__).resolve().parent.parent


def _chemin(variable: str, defaut: Path) -> Path:
    """Renvoie le chemin lu dans la variable d'environnement, ou la valeur par défaut."""
    valeur = os.environ.get(variable)
    return Path(valeur) if valeur else defaut


DOSSIER_DATA: Path = _chemin("NOMENTRACE_DATA", RACINE / "data")
CHEMIN_BASE: Path = _chemin("NOMENTRACE_BASE", DOSSIER_DATA / "nomentrace.db")
DOSSIER_ECHANGE: Path = _chemin("NOMENTRACE_ECHANGE", RACINE / "echange")
DOSSIER_EXPORTS: Path = DOSSIER_ECHANGE / "exports"
DOSSIER_IMPORTS: Path = DOSSIER_ECHANGE / "imports"
DOSSIER_MODELES: Path = DOSSIER_ECHANGE / "modeles"
DOSSIER_SAUVEGARDES: Path = DOSSIER_ECHANGE / "sauvegardes"
DOSSIER_MIGRATIONS: Path = RACINE / "backend" / "migrations"
DOSSIER_STATIC: Path = RACINE / "static"


def lire_port(valeur: str | None, defaut: int = 8000) -> int:
    """Port d'écoute lu dans l'environnement ; refuse clairement une valeur illisible."""
    if not valeur:
        return defaut
    if not valeur.strip().isdigit() or not 1 <= int(valeur) <= 65535:
        raise ValueError(
            f"NOMENTRACE_PORT doit être un entier entre 1 et 65535 (lu : « {valeur} »)."
        )
    return int(valeur)


# Adresse et port d'écoute, lus par `python -m backend` (backend/__main__.py).
HOTE: str = os.environ.get("NOMENTRACE_HOTE") or "127.0.0.1"
PORT: int = lire_port(os.environ.get("NOMENTRACE_PORT"))

FORMAT_LOG: str = "%(asctime)s %(levelname)s %(name)s : %(message)s"
