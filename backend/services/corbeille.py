"""Corbeille des documents joints : aucun fichier n'est effacé sans retour possible.

Un fichier dont la fiche est supprimée de la base part dans `documents/_corbeille/`, nommé
d'après son empreinte SHA-256 (`<empreinte>_<nom>`) : deux suppressions du même contenu ne
donnent qu'un fichier, et une base restaurée retrouve le sien par l'empreinte qu'elle garde.
Après une restauration, `verifier_documents` remet en place les fichiers manquants et range
dans la corbeille ceux que la base restaurée ne connaît pas.
"""

import hashlib
import logging
import shutil
import sqlite3
from pathlib import Path

from backend import db
from backend.services import journal

journal_log = logging.getLogger(__name__)

DOSSIER_CORBEILLE: str = "_corbeille"
# Sous-dossiers où sont rangés les documents en service.
DOSSIERS_DOCUMENTS: tuple[str, ...] = ("commandes", "composants")


def _corbeille(dossier: Path) -> Path:
    return dossier / DOSSIER_CORBEILLE


def _dans(dossier: Path, relatif: str) -> Path | None:
    """Chemin absolu d'un fichier de document, None s'il sortirait du dossier."""
    chemin = (dossier / relatif).resolve()
    return chemin if chemin.is_relative_to(dossier.resolve()) else None


def _nom_corbeille(empreinte: str, relatif: str) -> str:
    return f"{empreinte}_{Path(relatif).name}"


def _retirer_dossier_vide(dossier: Path, fichier: Path) -> None:
    parent = fichier.parent
    if parent != dossier.resolve() and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def jeter(dossier: Path, documents: list[dict]) -> int:
    """Déplace dans la corbeille les fichiers des documents supprimés ; renvoie leur nombre.

    `documents` : lignes portant `chemin` et `empreinte`.
    """
    corbeille = _corbeille(dossier)
    nombre = 0
    for document in documents:
        fichier = _dans(dossier, document["chemin"])
        if fichier is None or not fichier.is_file():
            journal_log.warning("Document absent, rien à jeter : %s", document["chemin"])
            continue
        try:
            corbeille.mkdir(parents=True, exist_ok=True)
            cible = corbeille / _nom_corbeille(document["empreinte"], document["chemin"])
            if cible.exists():
                fichier.unlink()
            else:
                shutil.move(fichier, cible)
            _retirer_dossier_vide(dossier, fichier)
            nombre += 1
        except OSError as erreur:
            journal_log.warning("Fichier %s non placé dans la corbeille : %s", fichier, erreur)
    return nombre


def _chercher(dossier: Path, empreinte: str) -> Path | None:
    corbeille = _corbeille(dossier)
    if not corbeille.is_dir():
        return None
    return next(corbeille.glob(f"{empreinte}_*"), None)


def _orphelins(dossier: Path, connus: set[Path]) -> list[Path]:
    fichiers = []
    for sous_dossier in DOSSIERS_DOCUMENTS:
        racine = dossier / sous_dossier
        if racine.is_dir():
            fichiers.extend(
                f for f in racine.rglob("*") if f.is_file() and f.resolve() not in connus
            )
    return sorted(fichiers)


def verifier_documents(conn: sqlite3.Connection, dossier: Path) -> dict:
    """Accorde les fichiers à la base : remet en place les manquants depuis la corbeille,
    range dans la corbeille les fichiers que la base ne cite pas.

    Les documents archivés comptent : leur fichier est gardé.
    """
    documents = db.fetch_all(conn, "SELECT id, nom_origine, chemin, empreinte FROM document")
    remis: list[str] = []
    manquants: list[dict] = []
    connus: set[Path] = set()
    for document in documents:
        fichier = _dans(dossier, document["chemin"])
        if fichier is None:
            continue
        connus.add(fichier)
        if fichier.is_file():
            continue
        source = _chercher(dossier, document["empreinte"])
        if source is None:
            manquants.append({"id": document["id"], "nom": document["nom_origine"]})
            continue
        fichier.parent.mkdir(parents=True, exist_ok=True)
        # Copie : la corbeille garde le fichier pour une restauration ultérieure.
        shutil.copy2(source, fichier)
        remis.append(document["nom_origine"])
    orphelins = _orphelins(dossier, connus)
    ranges = jeter(dossier, [_ligne_orpheline(dossier, f) for f in orphelins])
    if remis or manquants or ranges:
        journal_log.info(
            "Documents accordés à la base : %d remis, %d manquants, %d rangés dans la corbeille",
            len(remis),
            len(manquants),
            ranges,
        )
    return {"remis": remis, "manquants": manquants, "ranges_corbeille": ranges}


def _ligne_orpheline(dossier: Path, fichier: Path) -> dict:
    """Un fichier que la base ne cite pas : son empreinte est calculée pour la corbeille."""
    return {
        "chemin": fichier.relative_to(dossier).as_posix(),
        "empreinte": hashlib.sha256(fichier.read_bytes()).hexdigest(),
    }


def describe_corbeille(dossier: Path) -> dict:
    """Nombre de fichiers dans la corbeille et place occupée, en octets."""
    corbeille = _corbeille(dossier)
    fichiers = [f for f in corbeille.iterdir() if f.is_file()] if corbeille.is_dir() else []
    return {"nb_fichiers": len(fichiers), "taille": sum(f.stat().st_size for f in fichiers)}


def vider_corbeille(conn: sqlite3.Connection, dossier: Path) -> dict:
    """Efface définitivement les fichiers de la corbeille, sauf ceux qu'un document cite encore.

    Un document en service a son propre fichier dans son dossier : la copie de la corbeille
    n'est gardée que si ce fichier-là manque (elle permet de le remettre en place).
    """
    manquants = {
        d["empreinte"]
        for d in db.fetch_all(conn, "SELECT chemin, empreinte FROM document")
        if (fichier := _dans(dossier, d["chemin"])) is not None and not fichier.is_file()
    }
    corbeille = _corbeille(dossier)
    effaces, taille = 0, 0
    if corbeille.is_dir():
        for fichier in corbeille.iterdir():
            if not fichier.is_file() or fichier.name.split("_", 1)[0] in manquants:
                continue
            taille += fichier.stat().st_size
            fichier.unlink()
            effaces += 1
    with db.transaction(conn):
        journal.write_journal(conn, "document", DOSSIER_CORBEILLE, "corbeille videe", effaces, None)
    journal_log.info("Corbeille des documents vidée : %d fichier(s), %d octets", effaces, taille)
    return {"effaces": effaces, "taille": taille}
