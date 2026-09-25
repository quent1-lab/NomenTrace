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

HOTE: str = os.environ.get("NOMENTRACE_HOTE", "127.0.0.1")
PORT: int = int(os.environ.get("NOMENTRACE_PORT", "8000"))

FORMAT_LOG: str = "%(asctime)s %(levelname)s %(name)s : %(message)s"
