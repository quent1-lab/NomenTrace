"""Sauvegardes de la base par l'API de sauvegarde de sqlite3."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

journal_log = logging.getLogger(__name__)

NB_CONSERVEES: int = 20
PREFIXE: str = "nomentrace_"


def create_sauvegarde(chemin_base: Path, dossier: Path) -> Path | None:
    """Copie la base dans le dossier de sauvegardes, puis ne garde que les 20 dernières.

    Renvoie le chemin de la sauvegarde, ou None si la base n'existe pas encore.
    """
    if not chemin_base.exists():
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    cible = dossier / f"{PREFIXE}{horodatage}.db"
    source = sqlite3.connect(chemin_base)
    destination = sqlite3.connect(cible)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    journal_log.info("Sauvegarde créée : %s", cible)
    purge_sauvegardes(dossier)
    return cible


def list_sauvegardes(dossier: Path) -> list[Path]:
    """Renvoie les sauvegardes, les plus récentes en premier."""
    return sorted(dossier.glob(f"{PREFIXE}*.db"), reverse=True)


def purge_sauvegardes(dossier: Path, nb_conservees: int = NB_CONSERVEES) -> None:
    """Supprime les sauvegardes au-delà des plus récentes."""
    for ancienne in list_sauvegardes(dossier)[nb_conservees:]:
        try:
            ancienne.unlink()
        except OSError as erreur:
            journal_log.warning("Sauvegarde %s non supprimée : %s", ancienne, erreur)
