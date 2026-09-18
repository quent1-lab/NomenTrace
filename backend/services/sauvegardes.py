"""Sauvegardes de la base par l'API de sauvegarde de sqlite3, et restauration."""

import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from backend import db
from backend.erreurs import ErreurMetier, Introuvable

journal_log = logging.getLogger(__name__)

NB_CONSERVEES: int = 20
PREFIXE: str = "nomentrace_"
MOTIF_NOM = re.compile(r"^nomentrace_\d{8}_\d{6}(-\d+)?\.db$")


def _cible_libre(dossier: Path) -> Path:
    """Nom horodaté, suffixé si une sauvegarde a déjà été prise dans la même seconde."""
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    cible, rang = dossier / f"{PREFIXE}{horodatage}.db", 2
    while cible.exists():
        cible, rang = dossier / f"{PREFIXE}{horodatage}-{rang}.db", rang + 1
    return cible


def _copier(source: Path, destination: sqlite3.Connection) -> None:
    connexion = sqlite3.connect(source)
    try:
        connexion.backup(destination)
    finally:
        connexion.close()


def create_sauvegarde(chemin_base: Path, dossier: Path) -> Path | None:
    """Copie la base dans le dossier de sauvegardes, puis ne garde que les 20 dernières.

    Renvoie le chemin de la sauvegarde, ou None si la base n'existe pas encore.
    """
    if not chemin_base.exists():
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    cible = _cible_libre(dossier)
    destination = sqlite3.connect(cible)
    try:
        _copier(chemin_base, destination)
    finally:
        destination.close()
    journal_log.info("Sauvegarde créée : %s", cible)
    purge_sauvegardes(dossier)
    return cible


def list_sauvegardes(dossier: Path) -> list[Path]:
    """Renvoie les sauvegardes, les plus récentes en premier."""
    return sorted(dossier.glob(f"{PREFIXE}*.db"), reverse=True)


def describe_sauvegardes(dossier: Path) -> list[dict]:
    """Nom, date et taille de chaque sauvegarde, les plus récentes en premier."""
    resultat = []
    for chemin in list_sauvegardes(dossier):
        info = chemin.stat()
        resultat.append(
            {
                "nom": chemin.name,
                "date": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
                "taille": info.st_size,
            }
        )
    return resultat


def purge_sauvegardes(dossier: Path, nb_conservees: int = NB_CONSERVEES) -> None:
    """Supprime les sauvegardes au-delà des plus récentes."""
    for ancienne in list_sauvegardes(dossier)[nb_conservees:]:
        try:
            ancienne.unlink()
        except OSError as erreur:
            journal_log.warning("Sauvegarde %s non supprimée : %s", ancienne, erreur)


def _verifier(chemin: Path) -> int:
    """Contrôle qu'une sauvegarde est une base Nomentrace saine ; renvoie sa version."""
    try:
        connexion = sqlite3.connect(chemin)
        try:
            integrite = connexion.execute("PRAGMA integrity_check").fetchone()[0]
            version = db.get_version_schema(connexion)
        finally:
            connexion.close()
    except sqlite3.DatabaseError as erreur:
        raise ErreurMetier(f"« {chemin.name} » n'est pas une base lisible ({erreur}).") from erreur
    if integrite != "ok":
        raise ErreurMetier(f"« {chemin.name} » est endommagée : {integrite}.")
    if version == 0:
        raise ErreurMetier(f"« {chemin.name} » n'est pas une base Nomentrace.")
    derniere = max((numero for numero, _ in db.list_migrations()), default=0)
    if version > derniere:
        raise ErreurMetier(
            f"« {chemin.name} » vient d'une version plus récente de Nomentrace "
            f"(schéma {version}, cette version connaît le schéma {derniere})."
        )
    return version


def restore_sauvegarde(chemin_base: Path, dossier: Path, nom: str) -> dict:
    """Remplace la base par une sauvegarde, après avoir sauvegardé l'état courant.

    Une sauvegarde plus ancienne que le schéma actuel reçoit les migrations manquantes.
    """
    if not MOTIF_NOM.match(nom) or not (dossier / nom).is_file():
        raise Introuvable(f"Sauvegarde « {nom} » introuvable.")
    source = dossier / nom
    version_source = _verifier(source)
    # Copie en mémoire d'abord : la sauvegarde de sécurité qui suit peut, par rotation,
    # supprimer la plus ancienne des sauvegardes, qui est peut-être celle qu'on restaure.
    memoire = sqlite3.connect(":memory:")
    try:
        _copier(source, memoire)
        securite = create_sauvegarde(chemin_base, dossier)
        destination = db.connect(chemin_base)
        try:
            memoire.backup(destination)
            version = db.apply_migrations(destination)
        finally:
            destination.close()
    finally:
        memoire.close()
    journal_log.warning("Base restaurée depuis %s (état précédent : %s)", nom, securite)
    return {
        "restauree": nom,
        "securite": securite.name if securite else None,
        "version_sauvegarde": version_source,
        "version_schema": version,
    }
