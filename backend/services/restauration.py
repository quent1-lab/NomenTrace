"""Restauration d'une archive complète sur le serveur, application arrêtée.

L'archive est celle de la sauvegarde nocturne (base du projet, base des comptes, documents
avec leur corbeille). Rien n'est perdu en la restaurant : les deux bases courantes sont
d'abord sauvegardées, et le dossier des documents courant est mis de côté, pas effacé.
Les migrations manquantes s'appliqueront au prochain démarrage de l'application.
"""

import logging
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from backend.erreurs import ErreurMetier
from backend.services import sauvegardes

journal_log = logging.getLogger(__name__)


def _membres_surs(archive: zipfile.ZipFile) -> list[str]:
    """Noms des fichiers de l'archive, après refus de tout chemin qui sortirait du dossier."""
    noms = [info.filename for info in archive.infolist() if not info.is_dir()]
    for nom in noms:
        chemin = PurePosixPath(nom)
        if chemin.is_absolute() or ".." in chemin.parts or "\\" in nom or ":" in nom:
            raise ErreurMetier(f"Archive refusée : chemin suspect « {nom} ».")
    if sauvegardes.NOM_BASE_ARCHIVE not in noms:
        raise ErreurMetier(
            f"Archive refusée : elle ne contient pas « {sauvegardes.NOM_BASE_ARCHIVE} »."
        )
    return noms


def _verifier_comptes(chemin: Path) -> None:
    """Contrôle que la base des comptes extraite est lisible et intègre."""
    try:
        connexion = sqlite3.connect(chemin)
        try:
            integrite = connexion.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connexion.close()
    except sqlite3.DatabaseError as erreur:
        message = f"La base des comptes de l'archive est illisible ({erreur})."
        raise ErreurMetier(message) from erreur
    if integrite != "ok":
        raise ErreurMetier(f"La base des comptes de l'archive est endommagée : {integrite}.")


def _remplacer_base(source: Path, cible: Path, dossier_sauvegardes: Path) -> str | None:
    """Sauvegarde la base cible puis y recopie la source ; renvoie le nom de la sauvegarde."""
    securite = sauvegardes.create_sauvegarde(cible, dossier_sauvegardes)
    cible.parent.mkdir(parents=True, exist_ok=True)
    destination = sqlite3.connect(cible)
    try:
        sauvegardes.copier_base(source, destination)
    finally:
        destination.close()
    return securite.name if securite else None


def _remplacer_documents(extraits: Path, dossier_documents: Path) -> str | None:
    """Met de côté le dossier des documents courant, puis installe celui de l'archive."""
    mis_de_cote = None
    if dossier_documents.is_dir() and any(dossier_documents.iterdir()):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        cote = dossier_documents.with_name(
            f"{dossier_documents.name}_avant_restauration_{horodatage}"
        )
        dossier_documents.rename(cote)
        mis_de_cote = str(cote)
    elif dossier_documents.is_dir():
        dossier_documents.rmdir()
    dossier_documents.parent.mkdir(parents=True, exist_ok=True)
    if extraits.is_dir():
        extraits.rename(dossier_documents)
    else:
        dossier_documents.mkdir()
    return mis_de_cote


def restore_archive(
    archive: Path,
    chemin_base: Path,
    chemin_comptes: Path,
    dossier_sauvegardes: Path,
    dossier_documents: Path,
    avec_documents: bool = True,
) -> dict:
    """Remplace les bases (et les documents) par le contenu d'une archive complète."""
    try:
        zip_ouvert = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as erreur:
        message = f"« {archive.name} » n'est pas une archive lisible ({erreur})."
        raise ErreurMetier(message) from erreur
    # Extraction à côté des documents : le déplacement final reste sur le même disque.
    dossier_documents.parent.mkdir(parents=True, exist_ok=True)
    with zip_ouvert, tempfile.TemporaryDirectory(dir=dossier_documents.parent) as temporaire:
        noms = _membres_surs(zip_ouvert)
        zip_ouvert.extractall(temporaire)
        extraits = Path(temporaire)
        version = sauvegardes.verifier_base(extraits / sauvegardes.NOM_BASE_ARCHIVE)
        avec_comptes = sauvegardes.NOM_COMPTES_ARCHIVE in noms
        if avec_comptes:
            _verifier_comptes(extraits / sauvegardes.NOM_COMPTES_ARCHIVE)
        resultat = {
            "version_schema": version,
            "securite_base": _remplacer_base(
                extraits / sauvegardes.NOM_BASE_ARCHIVE, chemin_base, dossier_sauvegardes
            ),
            "comptes": avec_comptes,
            "documents_mis_de_cote": None,
        }
        if avec_comptes:
            resultat["securite_comptes"] = _remplacer_base(
                extraits / sauvegardes.NOM_COMPTES_ARCHIVE,
                chemin_comptes,
                dossier_sauvegardes / "comptes",
            )
        if avec_documents:
            resultat["documents_mis_de_cote"] = _remplacer_documents(
                extraits / sauvegardes.DOSSIER_DOCUMENTS_ARCHIVE, dossier_documents
            )
    journal_log.warning("Archive %s restaurée : %s", archive.name, resultat)
    return resultat
