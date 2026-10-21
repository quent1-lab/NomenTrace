"""Référence d'un dossier : création, initialisation, rangement des projets, propagation.

Chaque dossier a son projet de référence, `ref-<dossier>`, inscrit au registre avec
`reference = 1`. La référence est initialisée par le premier de trois événements : le
rangement d'un projet existant (elle prend ses réglages imposés, le projet ne change pas),
la création d'un projet dans le dossier, ou un réglage des paramètres communs. Ensuite,
tout projet rangé ou créé dans le dossier reçoit la référence, et toute modification de la
référence est propagée à chacun des projets du dossier.
"""

import logging
import sqlite3
from pathlib import Path

from backend import db
from backend.erreurs import Conflit, ErreurMetier
from backend.services import projets, propagation
from backend.services.projets import EmplacementsProjet, Registre

journal_log = logging.getLogger(__name__)

PREFIXE_REFERENCE = "ref-"


def code_reference(dossier: str) -> str:
    return f"{PREFIXE_REFERENCE}{dossier}"


def est_reference(conn: sqlite3.Connection, code: str) -> bool:
    ligne = conn.execute("SELECT reference FROM projet WHERE code = ?", (code,)).fetchone()
    return bool(ligne and ligne[0])


def creer_reference(
    conn: sqlite3.Connection, dossiers: tuple[Path, Path], dossier: str
) -> EmplacementsProjet:
    """Base de référence vide d'un nouveau dossier (schéma à jour, valeurs système)."""
    return projets.creer_projet(
        conn,
        *dossiers,
        {"code": code_reference(dossier), "dossier": dossier, "nom_equipe": None, "reference": 1},
        {},
    )


def _nom_projet(conn: sqlite3.Connection, dossier: str) -> str | None:
    ligne = conn.execute("SELECT nom_projet FROM dossier WHERE code = ?", (dossier,)).fetchone()
    return ligne[0] if ligne else None


def _emplacement(registre: Registre, code: str) -> EmplacementsProjet:
    emp = registre.projets.get(code)
    if emp is None:
        raise ErreurMetier(
            f"Le projet « {code} » est hors ligne : réessayer après sa remise en ligne.", 503
        )
    return emp


def accorder(
    conn: sqlite3.Connection, registre: Registre, code: str, dossier: str
) -> propagation.Rapport:
    """Accorde un projet à la référence de son dossier (sans effet s'il est à jour)."""
    ref = _emplacement(registre, code_reference(dossier))
    emp = _emplacement(registre, code)
    return propagation.synchroniser(
        emp.base, ref.base, dossier, _nom_projet(conn, dossier), emp.sauvegardes
    )


def ranger(conn: sqlite3.Connection, registre: Registre, code: str, dossier: str) -> dict:
    """Range un projet existant : il donne la référence si elle est neuve, sinon la reçoit.

    Un conflit (attribut d'un autre type) refuse le rangement avant toute écriture.
    """
    ref = _emplacement(registre, code_reference(dossier))
    emp = _emplacement(registre, code)
    if not propagation.est_initialisee(ref.base):
        nom = propagation.initialiser_reference(ref.base, emp.base, dossier)
        with db.transaction(conn):
            conn.execute("UPDATE dossier SET nom_projet = ? WHERE code = ?", (nom, dossier))
        journal_log.info("Référence du dossier %s prise du projet %s", dossier, code)
    else:
        erreurs = propagation.conflits(emp.base, ref.base)
        if erreurs:
            raise Conflit("Rangement impossible : " + " ".join(erreurs))
    return accorder(conn, registre, code, dossier).resume()


def sortir(registre: Registre, code: str) -> None:
    propagation.lever_verrou(_emplacement(registre, code).base)


def initialiser_si_neuve(registre: Registre, dossier: str) -> None:
    """Création d'un projet ou réglage commun : la référence telle qu'elle est fait foi."""
    ref = _emplacement(registre, code_reference(dossier))
    if not propagation.est_initialisee(ref.base):
        propagation.marquer_initialisee(ref.base, dossier)


def projets_du_dossier(conn: sqlite3.Connection, dossier: str) -> list[str]:
    lignes = conn.execute(
        "SELECT code FROM projet WHERE dossier = ? AND reference = 0 AND archive = 0 ORDER BY code",
        (dossier,),
    ).fetchall()
    return [ligne[0] for ligne in lignes]


def propager(conn: sqlite3.Connection, registre: Registre, dossier: str) -> dict[str, dict]:
    """Accorde chaque projet du dossier ; un échec n'arrête pas les autres, il est rapporté."""
    resultats: dict[str, dict] = {}
    for code in projets_du_dossier(conn, dossier):
        try:
            resultats[code] = accorder(conn, registre, code, dossier).resume()
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error("Projet %s non accordé au dossier %s : %s", code, dossier, erreur)
            resultats[code] = {"erreur": str(erreur)}
    return resultats


def etat_des_projets(conn: sqlite3.Connection, registre: Registre, dossier: str) -> dict[str, bool]:
    """À jour ou en retard sur la référence, projet par projet (lu dans les bases)."""
    ref = registre.projets.get(code_reference(dossier))
    if ref is None:
        return {}
    voulue = propagation.empreinte_base(ref.base, _nom_projet(conn, dossier))
    resultat = {}
    for code in projets_du_dossier(conn, dossier):
        emp = registre.projets.get(code)
        if emp is None:
            resultat[code] = False
            continue
        lecture = db.connect(emp.base, creer=False)
        try:
            resultat[code] = propagation.etat(lecture).get("empreinte") == voulue
        finally:
            lecture.close()
    return resultat


def reprendre(conn: sqlite3.Connection, registre: Registre, dossiers: tuple[Path, Path]) -> None:
    """Au démarrage : chaque dossier a sa référence, initialisée, et ses projets à jour."""
    for (dossier,) in conn.execute("SELECT code FROM dossier WHERE archive = 0").fetchall():
        code_ref = code_reference(dossier)
        try:
            if not projets.est_inscrit(conn, code_ref):
                registre.projets[code_ref] = creer_reference(conn, dossiers, dossier)
                registre.references.add(code_ref)
            ref = registre.projets.get(code_ref)
            if ref is None:
                continue
            premiers = projets_du_dossier(conn, dossier)
            if not propagation.est_initialisee(ref.base) and premiers:
                plus_ancien = conn.execute(
                    "SELECT code FROM projet WHERE dossier = ? AND reference = 0 AND archive = 0"
                    " ORDER BY cree_le, code LIMIT 1",
                    (dossier,),
                ).fetchone()[0]
                if plus_ancien in registre.projets:
                    ranger(conn, registre, plus_ancien, dossier)
            propager(conn, registre, dossier)
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error(
                "Dossier %s : référence non reprise au démarrage : %s", dossier, erreur
            )


def apres_reglage_commun(conn: sqlite3.Connection, registre: Registre, code_ref: str) -> dict:
    """Écriture réussie sur une référence : elle fait foi, et chaque projet la reçoit."""
    ligne = conn.execute("SELECT dossier FROM projet WHERE code = ?", (code_ref,)).fetchone()
    if ligne is None or ligne[0] is None:
        return {}
    initialiser_si_neuve(registre, ligne[0])
    return propager(conn, registre, ligne[0])


def situation(conn: sqlite3.Connection, conn_projet: sqlite3.Connection, code: str) -> dict:
    """Pour l'interface : la page est-elle une référence, ses réglages sont-ils imposés ?

    `reference` et `imposes` portent le nom du dossier concerné, ou None.
    """
    ligne = conn.execute(
        "SELECT p.reference, p.dossier, d.nom FROM projet p"
        " LEFT JOIN dossier d ON d.code = p.dossier WHERE p.code = ?",
        (code,),
    ).fetchone()
    if ligne is None or ligne["dossier"] is None:
        return {"reference": None, "imposes": None, "dossier": None}
    impose = bool(propagation.etat(conn_projet).get("actif"))
    return {
        "reference": ligne["nom"] if ligne["reference"] else None,
        "imposes": ligne["nom"] if impose else None,
        "dossier": ligne["dossier"],
    }
