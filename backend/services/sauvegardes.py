"""Sauvegardes de la base par l'API de sauvegarde de sqlite3, et restauration."""

import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import corbeille

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


def copier_base(source: Path, destination: sqlite3.Connection) -> None:
    """Copie cohérente d'une base SQLite, même ouverte, par l'API de sauvegarde."""
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
        copier_base(chemin_base, destination)
    finally:
        destination.close()
    journal_log.info("Sauvegarde créée : %s", cible)
    purge_sauvegardes(dossier)
    return cible


def _ordre(chemin: Path) -> tuple[str, int]:
    """Horodatage puis rang : « _120000-2.db » vient après « _120000.db », prise la même seconde."""
    horodatage, _, rang = chemin.stem.removeprefix(PREFIXE).partition("-")
    return horodatage, int(rang) if rang.isdigit() else 1


def list_sauvegardes(dossier: Path) -> list[Path]:
    """Renvoie les sauvegardes, les plus récentes en premier."""
    return sorted(dossier.glob(f"{PREFIXE}*.db"), key=_ordre, reverse=True)


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


def verifier_base(chemin: Path) -> int:
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


def restore_sauvegarde(
    chemin_base: Path, dossier: Path, nom: str, dossier_documents: Path | None = None
) -> dict:
    """Remplace la base par une sauvegarde, après avoir sauvegardé l'état courant.

    Une sauvegarde plus ancienne que le schéma actuel reçoit les migrations manquantes.
    Les fichiers des documents sont ensuite accordés à la base restaurée (corbeille).
    """
    if not MOTIF_NOM.match(nom) or not (dossier / nom).is_file():
        raise Introuvable(f"Sauvegarde « {nom} » introuvable.")
    source = dossier / nom
    version_source = verifier_base(source)
    # Copie en mémoire d'abord : la sauvegarde de sécurité qui suit peut, par rotation,
    # supprimer la plus ancienne des sauvegardes, qui est peut-être celle qu'on restaure.
    memoire = sqlite3.connect(":memory:")
    try:
        copier_base(source, memoire)
        securite = create_sauvegarde(chemin_base, dossier)
        destination = db.connect(chemin_base)
        try:
            memoire.backup(destination)
            version = db.apply_migrations(destination)
            documents = (
                corbeille.verifier_documents(destination, dossier_documents)
                if dossier_documents is not None
                else None
            )
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
        "documents": documents,
    }


NOM_BASE_ARCHIVE: str = "nomentrace.db"
NOM_COMPTES_ARCHIVE: str = "comptes.db"
DOSSIER_DOCUMENTS_ARCHIVE: str = "documents"
DOSSIER_PROJETS_ARCHIVE: str = "projets"
FICHIERS_IGNORES: frozenset[str] = frozenset({".gitkeep"})


def nom_archive(maintenant: datetime | None = None) -> str:
    """nomentrace_archive_AAAAMMJJ_HHMM.zip"""
    return f"nomentrace_archive_{(maintenant or datetime.now()):%Y%m%d_%H%M}.zip"


def _ajouter_documents(archive: zipfile.ZipFile, dossier_documents: Path, prefixe: str) -> int:
    """Ajoute tout le dossier des documents sous `prefixe` ; renvoie le nombre de fichiers."""
    nombre = 0
    if not dossier_documents.is_dir():
        return nombre
    for chemin in sorted(dossier_documents.rglob("*")):
        if chemin.is_file() and chemin.name not in FICHIERS_IGNORES:
            relatif = chemin.relative_to(dossier_documents).as_posix()
            archive.write(chemin, f"{prefixe}/{relatif}")
            nombre += 1
    return nombre


def _copie_coherente(source: Path) -> Path:
    """Copie d'une base SQLite dans un fichier temporaire, par l'API de sauvegarde."""
    descripteur, temporaire = tempfile.mkstemp(prefix="nomentrace_archive_", suffix=".db")
    os.close(descripteur)
    try:
        destination = sqlite3.connect(temporaire)
        try:
            copier_base(source, destination)
        finally:
            destination.close()
    except sqlite3.Error:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return Path(temporaire)


def _zip_temporaire() -> Path:
    descripteur, chemin = tempfile.mkstemp(prefix="nomentrace_archive_", suffix=".zip")
    os.close(descripteur)
    return Path(chemin)


def _ajouter_base(archive: zipfile.ZipFile, source: Path, nom: str) -> None:
    """Ajoute une copie cohérente d'une base (API de sauvegarde, journal WAL compris)."""
    copie = _copie_coherente(source)
    try:
        archive.write(copie, nom)
    finally:
        copie.unlink(missing_ok=True)


def build_archive(chemin_base: Path, dossier_documents: Path) -> Path:
    """Archive d'un projet dans un fichier temporaire : base et documents, à la racine.

    C'est l'archive téléchargée depuis l'interface. Les bases sont copiées par l'API de
    sauvegarde de sqlite3, jamais en lisant le fichier ouvert. L'appelant la supprime.
    """
    zip_temporaire = _zip_temporaire()
    try:
        with zipfile.ZipFile(zip_temporaire, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _ajouter_base(archive, chemin_base, NOM_BASE_ARCHIVE)
            nombre = _ajouter_documents(archive, dossier_documents, DOSSIER_DOCUMENTS_ARCHIVE)
    except OSError, sqlite3.Error:
        journal_log.exception("Archive du projet impossible")
        zip_temporaire.unlink(missing_ok=True)
        raise
    journal_log.info("Archive du projet construite : base et %d document(s)", nombre)
    return zip_temporaire


def build_archive_serveur(chemin_comptes: Path, projets: list[tuple[str, Path, Path]]) -> Path:
    """Archive complète du serveur : base commune, puis base et documents de chaque projet.

    `projets` donne, pour chaque projet, son code, sa base et son dossier de documents.
    Disposition : comptes.db, projets/<code>/nomentrace.db, projets/<code>/documents/….
    """
    zip_temporaire = _zip_temporaire()
    try:
        with zipfile.ZipFile(zip_temporaire, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if chemin_comptes.is_file():
                _ajouter_base(archive, chemin_comptes, NOM_COMPTES_ARCHIVE)
            nombre = 0
            for code, base, documents in projets:
                racine = f"{DOSSIER_PROJETS_ARCHIVE}/{code}"
                _ajouter_base(archive, base, f"{racine}/{NOM_BASE_ARCHIVE}")
                nombre += _ajouter_documents(
                    archive, documents, f"{racine}/{DOSSIER_DOCUMENTS_ARCHIVE}"
                )
    except OSError, sqlite3.Error:
        journal_log.exception("Archive complète impossible")
        zip_temporaire.unlink(missing_ok=True)
        raise
    journal_log.info(
        "Archive complète construite : base commune, %d projet(s), %d document(s)",
        len(projets),
        nombre,
    )
    return zip_temporaire
