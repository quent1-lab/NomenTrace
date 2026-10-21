"""Projets servis par l'instance : registre, emplacements, préparation et migration.

Chaque projet a sa base et ses dossiers : `<data>/projets/<code>/nomentrace.db` et
`<echange>/projets/<code>/{documents, exports, imports, modeles, sauvegardes}`. Le registre
des projets vit dans la base commune (celle des comptes) ; le code d'un projet, figé, est
celui de son adresse `/p/<code>/`.

Avant la phase 15a-2, une instance n'avait qu'une base (`NOMENTRACE_BASE`) et un dossier
d'échange à plat. Au démarrage, cette ancienne base est recopiée dans le dossier du projet
de l'instance, puis marquée : l'ancien code refuse alors d'y démarrer. Règle appliquée
(ancienne base × projet inscrit) :

    ancienne base non marquée, projet non inscrit  → migration par copie
    ancienne base non marquée, projet inscrit      → refus de démarrer (état incohérent)
    ancienne base marquée ou absente               → inscription si besoin, base créée si absente
"""

import logging
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend import db
from backend.aiguillage import code_valide
from backend.erreurs import Conflit, ErreurMetier
from backend.services import parametres, sauvegardes
from backend.services.export_excel import PlanificateurExport

journal_log = logging.getLogger(__name__)

NOM_BASE: str = "nomentrace.db"
# Numéro inscrit dans schema_version de l'ancienne base une fois recopiée : plus grand que
# toute migration connue de l'ancien code, qui refuse donc d'y démarrer.
MARQUE_MIGREE: int = 999
# Dossiers de l'ancien échange recopiés dans celui du projet (les exports se régénèrent).
DOSSIERS_REPRIS: tuple[str, ...] = ("documents", "imports", "modeles", "sauvegardes")
# Sous-dossier des sauvegardes de la base commune, qui reste hors des projets.
SAUVEGARDES_COMPTES: str = "comptes"


@dataclass(frozen=True)
class EmplacementsProjet:
    """Base et dossiers d'un projet."""

    code: str
    base: Path
    echange: Path

    @property
    def documents(self) -> Path:
        return self.echange / "documents"

    @property
    def exports(self) -> Path:
        return self.echange / "exports"

    @property
    def imports(self) -> Path:
        return self.echange / "imports"

    @property
    def modeles(self) -> Path:
        return self.echange / "modeles"

    @property
    def sauvegardes(self) -> Path:
        return self.echange / "sauvegardes"


def emplacements(dossier_data: Path, dossier_echange: Path, code: str) -> EmplacementsProjet:
    """Emplacements d'un projet ; le code est vérifié avant de servir de nom de dossier."""
    if not code_valide(code):
        raise ErreurMetier(f"Code de projet invalide : « {code} ».")
    return EmplacementsProjet(
        code,
        dossier_data / "projets" / code / NOM_BASE,
        dossier_echange / "projets" / code,
    )


@dataclass
class Registre:
    """Projets du processus : en ligne (avec leurs emplacements) ou hors ligne (motif)."""

    projets: dict[str, EmplacementsProjet] = field(default_factory=dict)
    hors_ligne: dict[str, str] = field(default_factory=dict)
    # Projets de référence des dossiers : servis pour leurs seuls réglages.
    references: set[str] = field(default_factory=set)


# --- Registre en base -----------------------------------------------------------------------


def list_codes(conn_comptes: sqlite3.Connection) -> list[str]:
    """Codes des projets inscrits et non archivés, dans l'ordre alphabétique."""
    lignes = conn_comptes.execute(
        "SELECT code FROM projet WHERE archive = 0 ORDER BY code"
    ).fetchall()
    return [ligne["code"] for ligne in lignes]


def est_inscrit(conn_comptes: sqlite3.Connection, code: str) -> bool:
    ligne = conn_comptes.execute("SELECT 1 FROM projet WHERE code = ?", (code,)).fetchone()
    return ligne is not None


def inscrire(conn_comptes: sqlite3.Connection, code: str) -> None:
    """Inscrit un projet au registre (sans effet s'il l'est déjà)."""
    conn_comptes.execute("INSERT OR IGNORE INTO projet (code) VALUES (?)", (code,))


# --- Ancienne base unique -------------------------------------------------------------------


def est_marquee(chemin: Path) -> bool:
    """L'ancienne base a déjà été recopiée dans le dossier d'un projet."""
    conn = sqlite3.connect(f"{chemin.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return db.get_version_schema(conn) >= MARQUE_MIGREE
    finally:
        conn.close()


def _marquer(chemin: Path) -> None:
    conn = db.connect(chemin)
    try:
        with db.transaction(conn):
            conn.execute("INSERT INTO schema_version (numero) VALUES (?)", (MARQUE_MIGREE,))
    finally:
        conn.close()


def marquer_si_besoin(chemin: Path) -> None:
    """Marque l'ancienne base comme remplacée, si elle existe et ne l'est pas encore."""
    if chemin.is_file() and not est_marquee(chemin):
        _marquer(chemin)
        journal_log.warning("Ancienne base %s marquée comme remplacée", chemin)


def _renommer(source: Path, cible: Path, essais: int = 10) -> None:
    """Renomme un dossier ; réessaie un court moment si Windows le tient encore.

    Sous Windows, l'antivirus ou l'indexation ouvrent un instant les fichiers qu'on vient
    d'écrire, et le renommage du dossier est alors refusé (accès refusé).
    """
    for essai in range(essais):
        try:
            source.rename(cible)
            return
        except PermissionError:
            if essai == essais - 1:
                raise
            time.sleep(0.1 * (essai + 1))


def _mettre_de_cote(dossier: Path) -> None:
    """Renomme un dossier de projet déjà présent ; rien n'est effacé."""
    if not dossier.exists():
        return
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    cote = dossier.with_name(f"{dossier.name}_avant_migration_{horodatage}")
    try:
        _renommer(dossier, cote)
    except OSError as erreur:
        raise ErreurMetier(
            f"Migration impossible : le dossier « {dossier} » n'a pas pu être mis de côté"
            f" ({erreur}). Fermer les fichiers ouverts (export Excel) et relancer."
        ) from erreur
    journal_log.warning("Dossier %s mis de côté sous %s", dossier, cote.name)


def _copier_echange(ancien_echange: Path, cible: Path) -> None:
    """Recopie les dossiers repris de l'ancien échange (sans les sauvegardes des comptes)."""
    cible.mkdir(parents=True, exist_ok=True)
    for nom in DOSSIERS_REPRIS:
        source = ancien_echange / nom
        if source.is_dir():
            ignorer = shutil.ignore_patterns(SAUVEGARDES_COMPTES) if nom == "sauvegardes" else None
            shutil.copytree(source, cible / nom, ignore=ignorer)


def migrer_ancienne_base(ancienne: Path, ancien_echange: Path, emp: EmplacementsProjet) -> None:
    """Recopie l'ancienne base et son échange dans le dossier du projet, puis la marque.

    La copie se fait dans des dossiers temporaires, effacés à chaque reprise (ce ne sont
    que des copies), puis renommés : une copie interrompue ne laisse rien en place. Un
    dossier de projet complet déjà présent (tentative précédente défaite par un retour
    arrière) est mis de côté. Le marquage vient en dernier.
    """
    dossier_base = emp.base.parent
    temp_base = dossier_base.with_name(f".migration-{emp.code}")
    temp_echange = emp.echange.with_name(f".migration-{emp.code}")
    for temporaire in (temp_base, temp_echange):
        shutil.rmtree(temporaire, ignore_errors=True)
    temp_base.mkdir(parents=True)
    destination = sqlite3.connect(temp_base / NOM_BASE)
    try:
        sauvegardes.copier_base(ancienne, destination)
    finally:
        destination.close()
    _copier_echange(ancien_echange, temp_echange)
    for temporaire, final in ((temp_base, dossier_base), (temp_echange, emp.echange)):
        _mettre_de_cote(final)
        _renommer(temporaire, final)
    _marquer(ancienne)
    journal_log.warning("Ancienne base %s recopiée dans %s, puis marquée", ancienne, emp.base)


def assurer_projet_instance(
    conn_comptes: sqlite3.Connection,
    ancienne: Path,
    ancien_echange: Path,
    emp: EmplacementsProjet,
) -> None:
    """Applique la règle ancienne base × registre pour le projet de l'instance."""
    a_migrer = ancienne.is_file() and not est_marquee(ancienne)
    if a_migrer and est_inscrit(conn_comptes, emp.code):
        raise ErreurMetier(
            f"Refus de démarrer : l'ancienne base {ancienne} n'est pas marquée comme recopiée"
            f" alors que le projet « {emp.code} » est déjà inscrit. La recopier écraserait"
            " les données du projet : vérifier quelle base fait foi avant de relancer."
        )
    if a_migrer:
        migrer_ancienne_base(ancienne, ancien_echange, emp)
    elif not est_inscrit(conn_comptes, emp.code) and not emp.base.exists():
        creer_base(emp)
    inscrire(conn_comptes, emp.code)


def creer_base(emp: EmplacementsProjet) -> None:
    """Crée la base vide d'un nouveau projet, au schéma à jour."""
    conn = db.connect(emp.base)
    try:
        db.apply_migrations(conn)
    finally:
        conn.close()
    journal_log.info("Base du projet « %s » créée : %s", emp.code, emp.base)


class BaseAbsente(RuntimeError):
    """Projet inscrit dont la base a disparu : jamais recréée vide en silence."""


def preparer_projet(emp: EmplacementsProjet) -> int:
    """Sauvegarde puis migrations de la base d'un projet inscrit ; renvoie la version."""
    if not emp.base.is_file():
        raise BaseAbsente(f"base introuvable : {emp.base}")
    sauvegardes.create_sauvegarde(emp.base, emp.sauvegardes)
    conn = db.connect(emp.base, creer=False)
    try:
        return db.apply_migrations(conn)
    finally:
        conn.close()


def charger_registre(
    conn_comptes: sqlite3.Connection, dossier_data: Path, dossier_echange: Path
) -> Registre:
    """Prépare chaque projet inscrit, isolément : un échec ne met hors ligne que lui."""
    registre = Registre()
    for code in list_codes(conn_comptes):
        emp = emplacements(dossier_data, dossier_echange, code)
        try:
            version = preparer_projet(emp)
        except (sqlite3.Error, db.SchemaTropRecent, BaseAbsente, OSError) as erreur:
            journal_log.error("Projet « %s » hors ligne : %s", code, erreur)
            registre.hors_ligne[code] = str(erreur)
            continue
        journal_log.info("Projet « %s » prêt (%s), schéma version %d", code, emp.base, version)
        registre.projets[code] = emp
    registre.references.update(
        ligne[0] for ligne in conn_comptes.execute("SELECT code FROM projet WHERE reference = 1")
    )
    return registre


# --- Création d'un projet à chaud ---------------------------------------------------------------

# Deux créations simultanées du même code : la seconde attend et trouve le code pris.
_VERROU_CREATION = threading.Lock()


def _check_creation(conn_comptes: sqlite3.Connection, emp: EmplacementsProjet) -> None:
    """Code libre partout : registre, comptes, disque. Rien n'est écrit avant ce contrôle."""
    if est_inscrit(conn_comptes, emp.code):
        raise Conflit(f"Le code « {emp.code} » est déjà pris par un projet.")
    if conn_comptes.execute("SELECT 1 FROM acces WHERE projet = ?", (emp.code,)).fetchone():
        raise Conflit(
            f"Des accès existent déjà pour le code « {emp.code} » sans projet inscrit :"
            " choisir un autre code."
        )
    for chemin in (emp.base.parent, emp.echange):
        if chemin.exists():
            raise Conflit(
                f"Le code « {emp.code} » est libre, mais son dossier existe déjà sur le disque"
                f" ({chemin}) : choisir un autre code."
            )


def _inscrire_nouveau(conn_comptes: sqlite3.Connection, inscription: dict[str, Any]) -> None:
    """Dernière étape d'une création : le projet entre au registre, rangé dans son dossier."""
    with db.transaction(conn_comptes):
        conn_comptes.execute(
            "INSERT INTO projet (code, dossier, nom_equipe, reference) VALUES (?, ?, ?, ?)",
            (
                inscription["code"],
                inscription["dossier"],
                inscription["nom_equipe"],
                inscription.get("reference") or 0,
            ),
        )


def creer_projet(
    conn_comptes: sqlite3.Connection,
    dossier_data: Path,
    dossier_echange: Path,
    inscription: dict[str, Any],
    reglages: dict[str, str],
    preparer: Callable[[Path], object] | None = None,
) -> EmplacementsProjet:
    """Crée la base d'un nouveau projet et l'inscrit au registre, sans redémarrage.

    `inscription` : code, dossier, nom_equipe ; `reglages` : paramètres écrits dans la base
    (nom du projet, préfixe) ; `preparer` : dernière préparation de la base neuve (reprise
    d'un projet modèle). La base est préparée dans un dossier temporaire, renommé une fois
    complète ; l'inscription vient en dernier. Un échec ne laisse rien derrière lui.
    """
    emp = emplacements(dossier_data, dossier_echange, str(inscription["code"]))
    with _VERROU_CREATION:
        _check_creation(conn_comptes, emp)
        temporaire = emp.base.parent.with_name(f".creation-{emp.code}")
        shutil.rmtree(temporaire, ignore_errors=True)
        try:
            conn = db.connect(temporaire / NOM_BASE)
            try:
                db.apply_migrations(conn)
                parametres.patch_parametres(conn, reglages)
            finally:
                conn.close()
            if preparer is not None:
                preparer(temporaire / NOM_BASE)
            _renommer(temporaire, emp.base.parent)
            emp.echange.mkdir(parents=True)
            _inscrire_nouveau(conn_comptes, inscription)
        except sqlite3.Error, OSError, ErreurMetier:
            for dossier in (temporaire, emp.base.parent, emp.echange):
                shutil.rmtree(dossier, ignore_errors=True)
            journal_log.exception("Création du projet « %s » annulée", emp.code)
            raise
    journal_log.info("Projet « %s » créé : %s", emp.code, emp.base)
    return emp


def mettre_en_ligne(
    registre: Registre, exports: dict[str, PlanificateurExport], emp: EmplacementsProjet
) -> None:
    """Rend un projet créé à chaud joignable sous /p/<code>/, avec son fil d'export."""
    registre.projets[emp.code] = emp
    if emp.code in registre.references:
        return
    export = PlanificateurExport(emp.base, emp.exports)
    exports[emp.code] = export
    export.start()


def get_nom_equipe(conn_comptes: sqlite3.Connection, code: str) -> str | None:
    """Nom d'équipe d'un projet, affiché après le nom du projet (« SPOC · Équipe »)."""
    ligne = conn_comptes.execute("SELECT nom_equipe FROM projet WHERE code = ?", (code,)).fetchone()
    return ligne["nom_equipe"] if ligne else None
