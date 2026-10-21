"""Restauration d'une archive complète sur le serveur, application arrêtée.

Deux formats sont acceptés. L'archive du serveur (depuis la phase 15a-2) contient la base
commune `comptes.db` et, pour chaque projet, `projets/<code>/nomentrace.db` et ses
documents sous `projets/<code>/documents/`. L'archive d'un seul projet (sauvegardes
nocturnes d'avant 15a-2, archive téléchargée depuis l'interface) a sa base et ses documents
à la racine, avec ou sans `comptes.db` : elle va au projet désigné, par défaut celui de
l'instance.

Rien n'est perdu en restaurant : les bases courantes sont d'abord sauvegardées, les
dossiers de documents courants mis de côté, pas effacés. Les projets inscrits avant la
restauration restent inscrits, même absents de l'archive. Les migrations manquantes
s'appliqueront au prochain démarrage de l'application.
"""

import logging
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from backend import db
from backend.aiguillage import code_valide
from backend.erreurs import ErreurMetier
from backend.services import comptes, projets, sauvegardes

journal_log = logging.getLogger(__name__)

MOTIF_BASE_PROJET = re.compile(r"^projets/([^/]+)/nomentrace\.db$")


@dataclass(frozen=True)
class Cible:
    """Où installer ce que l'archive contient."""

    chemin_comptes: Path
    dossier_data: Path
    dossier_echange: Path
    ancienne_base: Path


def _membres_surs(archive: zipfile.ZipFile) -> list[str]:
    """Noms des fichiers de l'archive, après refus de tout chemin qui sortirait du dossier."""
    noms = [info.filename for info in archive.infolist() if not info.is_dir()]
    for nom in noms:
        chemin = PurePosixPath(nom)
        if chemin.is_absolute() or ".." in chemin.parts or "\\" in nom or ":" in nom:
            raise ErreurMetier(f"Archive refusée : chemin suspect « {nom} ».")
    return noms


def _projets_de_l_archive(noms: list[str], projet: str) -> dict[str, tuple[str, str]]:
    """Code → (base, dossier des documents) dans l'archive, selon son format."""
    par_projet = {m.group(1): m.group(0) for nom in noms if (m := MOTIF_BASE_PROJET.match(nom))}
    if par_projet and sauvegardes.NOM_BASE_ARCHIVE in noms:
        raise ErreurMetier("Archive refusée : elle mêle les deux formats d'archive.")
    if not par_projet:
        if sauvegardes.NOM_BASE_ARCHIVE not in noms:
            raise ErreurMetier(
                f"Archive refusée : elle ne contient ni « {sauvegardes.NOM_BASE_ARCHIVE} » ni"
                " base de projet."
            )
        return {projet: (sauvegardes.NOM_BASE_ARCHIVE, sauvegardes.DOSSIER_DOCUMENTS_ARCHIVE)}
    for code in par_projet:
        if not code_valide(code):
            raise ErreurMetier(f"Archive refusée : code de projet invalide « {code} ».")
    return {
        code: (base, f"{sauvegardes.DOSSIER_PROJETS_ARCHIVE}/{code}/documents")
        for code, base in sorted(par_projet.items())
    }


def _verifier_comptes(chemin: Path) -> None:
    """Contrôle que la base commune extraite est lisible et intègre."""
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


# Structure gardée d'une restauration de la base commune : organismes, dossiers, rangement.
REQUETES_STRUCTURE: dict[str, str] = {
    "organisme": "SELECT code, nom FROM organisme",
    "dossier": "SELECT code, organisme, nom, nom_projet FROM dossier",
    "projet": "SELECT code, dossier, nom_equipe FROM projet WHERE archive = 0",
}


def _lire_structure(chemin_comptes: Path) -> dict[str, list[dict]]:
    """Structure de la base commune en place ; vide si elle n'en a pas encore."""
    if not chemin_comptes.is_file():
        return {table: [] for table in REQUETES_STRUCTURE}
    conn = db.connect(chemin_comptes)
    try:
        return {
            table: db.fetch_all(conn, requete) if db.table_existe(conn, table) else []
            for table, requete in REQUETES_STRUCTURE.items()
        }
    finally:
        conn.close()


def _reporter_structure(conn: sqlite3.Connection, structure: dict[str, list[dict]]) -> None:
    """Remet organismes, dossiers et rangement d'avant ; comptes et accès restent ceux de
    l'archive. Un projet créé après l'archive reste ainsi inscrit et rangé."""
    with db.transaction(conn):
        conn.executemany(
            "INSERT OR IGNORE INTO organisme (code, nom) VALUES (:code, :nom)",
            structure["organisme"],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO dossier (code, organisme, nom, nom_projet)"
            " VALUES (:code, :organisme, :nom, :nom_projet)",
            structure["dossier"],
        )
        conn.executemany(
            "INSERT INTO projet (code, dossier, nom_equipe) VALUES (:code, :dossier, :nom_equipe)"
            " ON CONFLICT (code) DO UPDATE SET dossier = excluded.dossier,"
            " nom_equipe = excluded.nom_equipe",
            [{"dossier": None, "nom_equipe": None, **ligne} for ligne in structure["projet"]],
        )


def _restaurer_comptes(extraite: Path, cible: Cible) -> str | None:
    """Remplace la base commune, puis la remet à jour et y garde la structure d'avant."""
    structure = _lire_structure(cible.chemin_comptes)
    securite = _remplacer_base(
        extraite,
        cible.chemin_comptes,
        cible.dossier_echange / "sauvegardes" / projets.SAUVEGARDES_COMPTES,
    )
    comptes.prepare_base(cible.chemin_comptes)
    conn = db.connect(cible.chemin_comptes)
    try:
        _reporter_structure(conn, structure)
    finally:
        conn.close()
    return securite


def _restaurer_projet(
    extraits: Path, code: str, membres: tuple[str, str], cible: Cible, avec_documents: bool
) -> dict:
    """Remplace la base (et les documents) d'un projet par ceux de l'archive."""
    emp = projets.emplacements(cible.dossier_data, cible.dossier_echange, code)
    base, documents = membres
    resultat = {
        "version_schema": sauvegardes.verifier_base(extraits / base),
        "securite_base": _remplacer_base(extraits / base, emp.base, emp.sauvegardes),
        "documents_mis_de_cote": None,
    }
    if avec_documents:
        resultat["documents_mis_de_cote"] = _remplacer_documents(
            extraits / documents, emp.documents
        )
    return resultat


def _inscrire(cible: Cible, codes: list[str]) -> None:
    comptes.prepare_base(cible.chemin_comptes)
    conn = db.connect(cible.chemin_comptes)
    try:
        for code in codes:
            projets.inscrire(conn, code)
    finally:
        conn.close()


def restore_archive(archive: Path, cible: Cible, projet: str, avec_documents: bool = True) -> dict:
    """Remplace la base commune et les projets contenus dans l'archive.

    `projet` désigne le projet qui reçoit une archive d'un seul projet. L'ancienne base
    unique, si elle n'a pas encore été recopiée, est marquée : l'archive fait foi.
    """
    try:
        zip_ouvert = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as erreur:
        message = f"« {archive.name} » n'est pas une archive lisible ({erreur})."
        raise ErreurMetier(message) from erreur
    cible.dossier_echange.mkdir(parents=True, exist_ok=True)
    with zip_ouvert, tempfile.TemporaryDirectory(dir=cible.dossier_echange) as temporaire:
        noms = _membres_surs(zip_ouvert)
        a_restaurer = _projets_de_l_archive(noms, projet)
        zip_ouvert.extractall(temporaire)
        extraits = Path(temporaire)
        # Tout est contrôlé avant la première écriture.
        for base, _ in a_restaurer.values():
            sauvegardes.verifier_base(extraits / base)
        avec_comptes = sauvegardes.NOM_COMPTES_ARCHIVE in noms
        if avec_comptes:
            _verifier_comptes(extraits / sauvegardes.NOM_COMPTES_ARCHIVE)
        resultat: dict = {"comptes": avec_comptes, "securite_comptes": None, "projets": {}}
        if avec_comptes:
            resultat["securite_comptes"] = _restaurer_comptes(
                extraits / sauvegardes.NOM_COMPTES_ARCHIVE, cible
            )
        for code, membres in a_restaurer.items():
            resultat["projets"][code] = _restaurer_projet(
                extraits, code, membres, cible, avec_documents
            )
    _inscrire(cible, list(a_restaurer))
    projets.marquer_si_besoin(cible.ancienne_base)
    journal_log.warning("Archive %s restaurée : %s", archive.name, resultat)
    return resultat
