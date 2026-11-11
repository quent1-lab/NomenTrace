"""Retrait d'un projet : supprimé s'il n'a laissé aucune trace, archivé sinon.

Un projet sans composant (archivés compris), sans commande, sans mouvement de stock ni
document est supprimé : une sauvegarde de sa base est prise, ses dossiers (base et échange)
partent dans `_corbeille/` à côté des autres projets, d'où on peut les remettre à la main,
et ses lignes de la base commune (accès, jetons, inscription) sont effacées. Un projet qui
porte des traces est seulement archivé : masqué, hors ligne, sa base intacte.

Réservé à qui gère l'organisme du dossier (ou à l'administrateur du serveur pour un projet
hors dossier). Une référence de dossier ou d'organisme ne se retire pas ainsi.
"""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

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


def _supprimer(conn: sqlite3.Connection, emp: EmplacementsProjet, code: str) -> None:
    """Dossiers à la corbeille, puis lignes de la base commune ; rien n'est effacé du disque."""
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    deplaces = []
    try:
        for dossier in (emp.base.parent, emp.echange):
            cible = _mettre_a_la_corbeille(dossier, horodatage)
            if cible is not None:
                deplaces.append((cible, dossier))
        with db.transaction(conn):
            conn.execute("DELETE FROM jeton_api WHERE projet = ?", (code,))
            conn.execute("DELETE FROM acces WHERE projet = ?", (code,))
            conn.execute("DELETE FROM projet WHERE code = ?", (code,))
    except (OSError, sqlite3.Error) as erreur:
        for cible, dossier in reversed(deplaces):
            shutil.move(cible, dossier)
        journal_log.error("Suppression du projet %s annulée : %s", code, erreur)
        raise ErreurMetier(
            f"Suppression du projet impossible ({erreur}) : il est remis en place.", 409
        ) from erreur


def delete_projet(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    code: str,
    registre: Registre,
    exports: dict[str, PlanificateurExport],
) -> dict:
    """Retire un projet ; rend `supprime` (vide) ou `archive` (il portait des traces)."""
    projet = hierarchie.get_projet(conn, code)
    _exiger_droit(conn, compte, projet)
    emp = registre.projets.get(code)
    if emp is None:
        raise ErreurMetier(f"Le projet « {code} » est hors ligne : le retirer plus tard.", 503)
    reste = traces(emp.base)
    if not reste:
        sauvegardes.create_sauvegarde(emp.base, emp.sauvegardes)
    _hors_ligne(registre, exports, code)
    try:
        if reste:
            with db.transaction(conn):
                conn.execute("UPDATE projet SET archive = 1 WHERE code = ?", (code,))
        else:
            _supprimer(conn, emp, code)
    except ErreurMetier, sqlite3.Error:
        projets.mettre_en_ligne(registre, exports, emp)
        raise
    action = "archive" if reste else "supprime"
    journal_log.info("Projet %s %s par %s (%s).", code, action, compte.nom, ", ".join(reste))
    return {"code": code, "action": action, "traces": reste}
