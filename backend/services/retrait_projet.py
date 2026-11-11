"""Retrait d'un projet, d'un dossier ou d'un organisme ; rien n'est effacé du disque.

Projet, par la gestion de l'organisme (l'administrateur du serveur hors dossier) : sans
composant (archivés compris), commande, mouvement de stock ni document, il est supprimé ;
sinon il est seulement archivé (masqué, hors ligne, base intacte).

L'administrateur du serveur supprime ce qu'il veut, même non vide, en confirmant par le code :
un projet, un dossier (ses projets, archivés compris, et ses paramètres communs) ou un
organisme (ses dossiers, leurs projets et sa liste de fournisseurs).

Supprimer, c'est : sauvegarde de chaque base, mise hors ligne, dossiers (base et échange)
déplacés dans `_corbeille/` à côté des autres projets, puis lignes de la base commune effacées
en une transaction. Un échec remet tout en place. Une référence ne se retire pas seule.
"""

import logging
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import hierarchie, projets, reference, sauvegardes
from backend.services.droits import AccesRefuse, Utilisateur
from backend.services.export_excel import PlanificateurExport
from backend.services.projets import EmplacementsProjet, Registre

journal_log = logging.getLogger(__name__)

CORBEILLE = "_corbeille"
# Ce qui fait d'un projet autre chose qu'une coquille vide (libellé, requête écrite ici).
TRACES: tuple[tuple[str, str], ...] = (
    ("composant", "SELECT COUNT(*) FROM composant"),
    ("commande", "SELECT COUNT(*) FROM commande"),
    ("mouvement de stock", "SELECT COUNT(*) FROM mouvement_stock"),
    ("document", "SELECT COUNT(*) FROM document"),
)


def _exiger_droit(conn: sqlite3.Connection, compte: Utilisateur, projet: dict) -> None:
    if reference.est_reference(conn, projet["code"]):
        raise AccesRefuse("Une référence ne se retire pas.")
    if projet["organisme"]:
        hierarchie.exiger_gestion(conn, compte, projet["organisme"])
    else:
        hierarchie.exiger_serveur(compte)


def traces(base: Path) -> list[str]:
    """Ce que le projet contient encore, en clair ; liste vide pour un projet vide."""
    conn = db.connect(base, creer=False)
    try:
        resultat = []
        for libelle, requete in TRACES:
            nombre = conn.execute(requete).fetchone()[0]
            if nombre:
                resultat.append(f"{nombre} {libelle}{'s' if nombre > 1 else ''}")
        return resultat
    finally:
        conn.close()


def _mettre_a_la_corbeille(dossier: Path, horodatage: str) -> Path | None:
    if not dossier.exists():
        return None
    corbeille = dossier.parent / CORBEILLE
    corbeille.mkdir(exist_ok=True)
    cible = corbeille / f"{dossier.name}_{horodatage}"
    shutil.move(dossier, cible)
    return cible


def _hors_ligne(registre: Registre, exports: dict[str, PlanificateurExport], code: str) -> None:
    export = exports.pop(code, None)
    if export is not None:
        export.stop()
    registre.projets.pop(code, None)


@dataclass
class Retrait:
    """Projets mis hors ligne et dossiers déplacés : tout se remet en place sur un échec."""

    registre: Registre
    exports: dict[str, PlanificateurExport]
    horodatage: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    en_ligne: list[EmplacementsProjet] = field(default_factory=list)
    deplaces: list[tuple[Path, Path]] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

    def retirer(self, emp: EmplacementsProjet) -> None:
        """Sauvegarde, mise hors ligne, puis base et échange du projet à la corbeille."""
        if emp.base.is_file():
            sauvegardes.create_sauvegarde(emp.base, emp.sauvegardes)
        if emp.code in self.registre.projets:
            self.en_ligne.append(emp)
        _hors_ligne(self.registre, self.exports, emp.code)
        self.codes.append(emp.code)
        for dossier in (emp.base.parent, emp.echange):
            cible = _mettre_a_la_corbeille(dossier, self.horodatage)
            if cible is not None:
                self.deplaces.append((cible, dossier))

    def annuler(self) -> None:
        for cible, dossier in reversed(self.deplaces):
            shutil.move(cible, dossier)
        for emp in self.en_ligne:
            projets.mettre_en_ligne(self.registre, self.exports, emp)

    def terminer(self) -> None:
        """Lignes effacées : les codes sortent aussi du registre (références, hors ligne)."""
        for code in self.codes:
            self.registre.references.discard(code)
            self.registre.hors_ligne.pop(code, None)


def _effacer_projets(conn: sqlite3.Connection, codes: list[str]) -> None:
    """Lignes de la base commune des projets retirés ; à appeler dans une transaction."""
    for code in codes:
        conn.execute("DELETE FROM jeton_api WHERE projet = ?", (code,))
        conn.execute("DELETE FROM acces WHERE projet = ?", (code,))
        conn.execute("DELETE FROM projet WHERE code = ?", (code,))


def _executer(
    conn: sqlite3.Connection,
    retrait: Retrait,
    emplacements: list[EmplacementsProjet],
    effacer: Callable[[], None],
) -> None:
    """Retire les projets puis efface les lignes en une transaction ; tout ou rien."""
    try:
        for emp in emplacements:
            retrait.retirer(emp)
        with db.transaction(conn):
            effacer()
    except (OSError, sqlite3.Error) as erreur:
        retrait.annuler()
        journal_log.error("Suppression annulée, tout est remis en place : %s", erreur)
        raise ErreurMetier(
            f"Suppression impossible ({erreur}) : tout est remis en place.", 409
        ) from erreur
    retrait.terminer()


def _emplacement(registre: Registre, dossiers: tuple[Path, Path], code: str) -> EmplacementsProjet:
    return registre.projets.get(code) or projets.emplacements(*dossiers, code)


def _exiger_confirmation(confirmation: str | None, code: str) -> None:
    if confirmation != code:
        raise ErreurMetier(f"Confirmer en tapant le code exact : « {code} ».")


def delete_projet(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    code: str,
    registre: Registre,
    exports: dict[str, PlanificateurExport],
    confirmation: str | None = None,
) -> dict:
    """Retire un projet : supprimé s'il est vide, archivé sinon.

    Avec `confirmation` (le code tapé), l'administrateur du serveur le supprime même non vide.
    """
    projet = hierarchie.get_projet(conn, code)
    _exiger_droit(conn, compte, projet)
    forcer = confirmation is not None
    if forcer:
        hierarchie.exiger_serveur(compte)
        _exiger_confirmation(confirmation, code)
    emp = registre.projets.get(code)
    if emp is None:
        raise ErreurMetier(f"Le projet « {code} » est hors ligne : le retirer plus tard.", 503)
    reste = traces(emp.base)
    if reste and not forcer:
        with db.transaction(conn):
            conn.execute("UPDATE projet SET archive = 1 WHERE code = ?", (code,))
        _hors_ligne(registre, exports, code)
        action = "archive"
    else:
        _executer(conn, Retrait(registre, exports), [emp], lambda: _effacer_projets(conn, [code]))
        action = "supprime"
    journal_log.info("Projet %s %s par %s (%s).", code, action, compte.nom, ", ".join(reste))
    return {"code": code, "action": action, "traces": reste}


def _codes(conn: sqlite3.Connection, requete: str, params: tuple) -> list[str]:
    return [ligne[0] for ligne in conn.execute(requete, params).fetchall()]


def _effacer_dossiers(conn: sqlite3.Connection, dossiers: list[str]) -> None:
    for dossier in dossiers:
        conn.execute("DELETE FROM acces_dossier WHERE dossier = ?", (dossier,))
        conn.execute("DELETE FROM dossier WHERE code = ?", (dossier,))


def delete_dossier(
    conn: sqlite3.Connection, compte: Utilisateur, code: str, etat: Any, confirmation: str | None
) -> dict:
    """Administrateur du serveur : le dossier, ses projets (archivés compris) et ses
    paramètres communs partent à la corbeille ; ses lignes de la base commune sont effacées."""
    hierarchie.exiger_serveur(compte)
    hierarchie.get_dossier(conn, code)
    _exiger_confirmation(confirmation, code)
    codes = _codes(conn, "SELECT code FROM projet WHERE dossier = ?", (code,))
    dossiers = (etat.dossier_data, etat.dossier_echange)

    def effacer() -> None:
        _effacer_projets(conn, codes)
        _effacer_dossiers(conn, [code])

    emplacements = [_emplacement(etat.registre, dossiers, c) for c in codes]
    _executer(conn, Retrait(etat.registre, etat.exports), emplacements, effacer)
    journal_log.info("Dossier %s supprimé par %s (projets : %s).", code, compte.nom, codes)
    return {"code": code, "projets": codes}


def delete_organisme(
    conn: sqlite3.Connection, compte: Utilisateur, code: str, etat: Any, confirmation: str | None
) -> dict:
    """Administrateur du serveur : l'organisme, ses dossiers, leurs projets et sa liste de
    fournisseurs partent à la corbeille ; ses lignes de la base commune sont effacées."""
    hierarchie.exiger_serveur(compte)
    hierarchie.get_organisme(conn, code)
    _exiger_confirmation(confirmation, code)
    dossiers_org = _codes(conn, "SELECT code FROM dossier WHERE organisme = ?", (code,))
    codes = _codes(
        conn,
        "SELECT code FROM projet WHERE organisme = ?"
        " OR dossier IN (SELECT code FROM dossier WHERE organisme = ?)",
        (code, code),
    )
    dossiers = (etat.dossier_data, etat.dossier_echange)

    def effacer() -> None:
        _effacer_projets(conn, codes)
        _effacer_dossiers(conn, dossiers_org)
        conn.execute("DELETE FROM acces_organisme WHERE organisme = ?", (code,))
        conn.execute("DELETE FROM organisme WHERE code = ?", (code,))

    emplacements = [_emplacement(etat.registre, dossiers, c) for c in codes]
    _executer(conn, Retrait(etat.registre, etat.exports), emplacements, effacer)
    journal_log.info("Organisme %s supprimé par %s (projets : %s).", code, compte.nom, codes)
    return {"code": code, "dossiers": dossiers_org, "projets": codes}
