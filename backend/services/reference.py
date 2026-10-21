"""Références : réglages d'un dossier et fournisseurs d'un organisme, et leur propagation.

Chaque dossier a son projet de référence, `ref-<dossier>`, inscrit au registre avec
`reference = 1`. La référence est initialisée par le premier de trois événements : le
rangement d'un projet existant (elle prend ses réglages imposés, le projet ne change pas),
la création d'un projet dans le dossier, ou un réglage des paramètres communs. Ensuite,
tout projet rangé ou créé dans le dossier reçoit la référence, et toute modification de la
référence est propagée à chacun des projets du dossier.

Chaque organisme a de même sa référence, `org-<organisme>`, qui porte la liste commune de
ses fournisseurs (services/fournisseurs_communs.py). Un projet rangé y ajoute ses
fournisseurs absents (union), puis reçoit la liste ; toute modification de la liste est
propagée aux projets de tous les dossiers de l'organisme.
"""

import logging
import sqlite3
from pathlib import Path

from backend import db
from backend.erreurs import Conflit, ErreurMetier
from backend.services import fournisseurs_communs, projets, propagation
from backend.services.projets import EmplacementsProjet, Registre

journal_log = logging.getLogger(__name__)

PREFIXE_REFERENCE = "ref-"
PREFIXE_ORGANISME = "org-"
PREFIXES_RESERVES: tuple[str, ...] = (PREFIXE_REFERENCE, PREFIXE_ORGANISME)


def code_reference(dossier: str) -> str:
    return f"{PREFIXE_REFERENCE}{dossier}"


def code_organisme(organisme: str) -> str:
    return f"{PREFIXE_ORGANISME}{organisme}"


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


def creer_reference_organisme(
    conn: sqlite3.Connection, dossiers: tuple[Path, Path], organisme: str
) -> EmplacementsProjet:
    """Référence d'un organisme : liste de fournisseurs vide, renommages journalisés d'emblée."""
    emp = projets.creer_projet(
        conn,
        *dossiers,
        {
            "code": code_organisme(organisme),
            "dossier": None,
            "nom_equipe": None,
            "reference": 1,
            "organisme": organisme,
        },
        {},
    )
    propagation.marquer_initialisee(emp.base, None)
    return emp


def _nom_projet(conn: sqlite3.Connection, dossier: str) -> str | None:
    ligne = conn.execute("SELECT nom_projet FROM dossier WHERE code = ?", (dossier,)).fetchone()
    return ligne[0] if ligne else None


def _organisme(conn: sqlite3.Connection, dossier: str) -> str | None:
    ligne = conn.execute("SELECT organisme FROM dossier WHERE code = ?", (dossier,)).fetchone()
    return ligne[0] if ligne else None


def _emplacement(registre: Registre, code: str) -> EmplacementsProjet:
    emp = registre.projets.get(code)
    if emp is None:
        raise ErreurMetier(
            f"Le projet « {code} » est hors ligne : réessayer après sa remise en ligne.", 503
        )
    return emp


def _liste_organisme(conn: sqlite3.Connection, registre: Registre, dossier: str) -> Path | None:
    organisme = _organisme(conn, dossier)
    emp = registre.projets.get(code_organisme(organisme)) if organisme else None
    return emp.base if emp else None


def accorder(
    conn: sqlite3.Connection, registre: Registre, code: str, dossier: str
) -> propagation.Rapport:
    """Accorde un projet à la référence de son dossier et à la liste de son organisme."""
    ref = _emplacement(registre, code_reference(dossier))
    emp = _emplacement(registre, code)
    return propagation.synchroniser(
        emp.base,
        ref.base,
        dossier,
        _nom_projet(conn, dossier),
        emp.sauvegardes,
        _liste_organisme(conn, registre, dossier),
    )


def _entrer_dans_l_organisme(
    conn: sqlite3.Connection, registre: Registre, emp: EmplacementsProjet, dossier: str
) -> None:
    """Union de ses fournisseurs à la liste, renommages passés marqués rejoués."""
    liste = _liste_organisme(conn, registre, dossier)
    if liste is None:
        return
    fournisseurs_communs.marquer_renommages(emp.base, liste)
    if fournisseurs_communs.unir(liste, emp.base, f"rangement de {emp.code}"):
        propager_organisme(conn, registre, _organisme(conn, dossier) or "", exclu=emp.code)


def ranger(
    conn: sqlite3.Connection,
    registre: Registre,
    code: str,
    dossier: str,
    ancien_dossier: str | None = None,
) -> dict:
    """Range un projet existant : il donne la référence si elle est neuve, sinon la reçoit.

    Ses fournisseurs rejoignent la liste de l'organisme s'il y entre. Un conflit (attribut
    d'un autre type) refuse le rangement avant toute écriture.
    """
    ref = _emplacement(registre, code_reference(dossier))
    emp = _emplacement(registre, code)
    if propagation.est_initialisee(ref.base):
        erreurs = propagation.conflits(emp.base, ref.base)
        if erreurs:
            raise Conflit("Rangement impossible : " + " ".join(erreurs))
    else:
        nom = propagation.initialiser_reference(ref.base, emp.base, dossier)
        with db.transaction(conn):
            conn.execute("UPDATE dossier SET nom_projet = ? WHERE code = ?", (nom, dossier))
        journal_log.info("Référence du dossier %s prise du projet %s", dossier, code)
    if ancien_dossier is None or _organisme(conn, ancien_dossier) != _organisme(conn, dossier):
        _entrer_dans_l_organisme(conn, registre, emp, dossier)
    return accorder(conn, registre, code, dossier).resume()


def apres_creation(conn: sqlite3.Connection, registre: Registre, code: str, dossier: str) -> None:
    """Projet neuf dans un dossier : il reçoit la référence et la liste de l'organisme."""
    initialiser_si_neuve(registre, dossier)
    liste = _liste_organisme(conn, registre, dossier)
    if liste is not None:
        fournisseurs_communs.marquer_renommages(_emplacement(registre, code).base, liste)
    accorder(conn, registre, code, dossier)


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


def dossiers_de_l_organisme(conn: sqlite3.Connection, organisme: str) -> list[str]:
    lignes = conn.execute(
        "SELECT code FROM dossier WHERE organisme = ? AND archive = 0 ORDER BY code", (organisme,)
    ).fetchall()
    return [ligne[0] for ligne in lignes]


def propager(
    conn: sqlite3.Connection, registre: Registre, dossier: str, exclu: str | None = None
) -> dict[str, dict]:
    """Accorde chaque projet du dossier ; un échec n'arrête pas les autres, il est rapporté."""
    resultats: dict[str, dict] = {}
    for code in projets_du_dossier(conn, dossier):
        if code == exclu:
            continue
        try:
            resultats[code] = accorder(conn, registre, code, dossier).resume()
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error("Projet %s non accordé au dossier %s : %s", code, dossier, erreur)
            resultats[code] = {"erreur": str(erreur)}
    return resultats


def propager_organisme(
    conn: sqlite3.Connection, registre: Registre, organisme: str, exclu: str | None = None
) -> dict[str, dict]:
    resultats: dict[str, dict] = {}
    for dossier in dossiers_de_l_organisme(conn, organisme):
        resultats.update(propager(conn, registre, dossier, exclu))
    return resultats


def etat_des_projets(conn: sqlite3.Connection, registre: Registre, dossier: str) -> dict[str, bool]:
    """À jour ou en retard sur les références, projet par projet (lu dans les bases)."""
    ref = registre.projets.get(code_reference(dossier))
    if ref is None:
        return {}
    voulue = propagation.empreinte_base(
        ref.base, _nom_projet(conn, dossier), _liste_organisme(conn, registre, dossier)
    )
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


def _reprendre_organisme(
    conn: sqlite3.Connection, registre: Registre, dossiers: tuple[Path, Path], organisme: str
) -> None:
    """Organisme d'avant les fournisseurs communs : sa liste est l'union de ses projets rangés."""
    code = code_organisme(organisme)
    if projets.est_inscrit(conn, code):
        return
    emp = creer_reference_organisme(conn, dossiers, organisme)
    registre.projets[code] = emp
    registre.references.add(code)
    for dossier in dossiers_de_l_organisme(conn, organisme):
        for projet in projets_du_dossier(conn, dossier):
            if projet in registre.projets:
                base = registre.projets[projet].base
                fournisseurs_communs.unir(emp.base, base, f"reprise de {projet}")
                fournisseurs_communs.marquer_renommages(base, emp.base)


def reprendre(conn: sqlite3.Connection, registre: Registre, dossiers: tuple[Path, Path]) -> None:
    """Au démarrage : chaque organisme a sa liste, chaque dossier sa référence initialisée,
    et tous les projets sont à jour."""
    for (organisme,) in conn.execute("SELECT code FROM organisme WHERE archive = 0").fetchall():
        try:
            _reprendre_organisme(conn, registre, dossiers, organisme)
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error(
                "Organisme %s : liste non reprise au démarrage : %s", organisme, erreur
            )
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
                    ranger(conn, registre, plus_ancien, dossier, ancien_dossier=dossier)
            propager(conn, registre, dossier)
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error(
                "Dossier %s : référence non reprise au démarrage : %s", dossier, erreur
            )


def apres_reglage_commun(conn: sqlite3.Connection, registre: Registre, code_ref: str) -> dict:
    """Écriture réussie sur une référence : elle fait foi, et chaque projet la reçoit."""
    ligne = conn.execute(
        "SELECT dossier, organisme FROM projet WHERE code = ?", (code_ref,)
    ).fetchone()
    if ligne is None:
        return {}
    if ligne["organisme"] is not None:
        return propager_organisme(conn, registre, ligne["organisme"])
    if ligne["dossier"] is None:
        return {}
    initialiser_si_neuve(registre, ligne["dossier"])
    return propager(conn, registre, ligne["dossier"])


def situation(conn: sqlite3.Connection, conn_projet: sqlite3.Connection, code: str) -> dict:
    """Pour l'interface : la page est-elle une référence, ses réglages sont-ils imposés ?

    `reference` et `imposes` portent le nom du dossier (ou de l'organisme) concerné, ou None ;
    `type_reference` vaut « dossier » ou « organisme ».
    """
    ligne = conn.execute(
        "SELECT p.reference, p.dossier, d.nom, p.organisme, o.nom AS nom_organisme FROM projet p"
        " LEFT JOIN dossier d ON d.code = p.dossier"
        " LEFT JOIN organisme o ON o.code = p.organisme WHERE p.code = ?",
        (code,),
    ).fetchone()
    vide = {"reference": None, "imposes": None, "dossier": None, "organisme": None}
    if ligne is None:
        return {**vide, "type_reference": None}
    if ligne["organisme"] is not None:
        return {
            **vide,
            "reference": ligne["nom_organisme"],
            "organisme": ligne["organisme"],
            "type_reference": "organisme",
        }
    if ligne["dossier"] is None:
        return {**vide, "type_reference": None}
    impose = bool(propagation.etat(conn_projet).get("actif"))
    return {
        **vide,
        "reference": ligne["nom"] if ligne["reference"] else None,
        "imposes": ligne["nom"] if impose else None,
        "dossier": ligne["dossier"],
        "type_reference": "dossier" if ligne["reference"] else None,
    }
