"""Pages communes : accueil après connexion, page d'un dossier, page d'un organisme.

Chaque projet visible y est une carte : nom, équipe, accès du compte et résumé (avancement
de l'approvisionnement, budget, engagé, coût estimé), lu dans la base du projet. Un projet
hors ligne ou illisible garde sa carte, marquée, sans résumé : l'accueil ne tombe pas pour un
projet.

Ce que chacun voit :
- administrateur du serveur : tout, projets hors dossier compris ;
- profil d'organisme : tous les dossiers et projets de l'organisme ;
- responsable achats : son dossier et le résumé de tous ses projets ;
- membre d'un projet : ses projets, rangés sous leur organisme et leur dossier.
"""

import logging
import sqlite3
from typing import Any

from backend import db
from backend.services import comptes, hierarchie, parametres, reference
from backend.services.droits import Utilisateur
from backend.services.projets import Registre

journal_log = logging.getLogger(__name__)

CHAMPS_RESUME: tuple[str, ...] = (
    "avancement_appro_pct",
    "budget_ht",
    "montant_engage_ht",
    "cout_ht",
)


def _resume(registre: Registre, code: str) -> tuple[dict | None, str | None]:
    """Résumé et nom du projet lus dans sa base ; (None, None) s'il est hors ligne ou illisible."""
    emp = registre.projets.get(code)
    if emp is None:
        return None, None
    try:
        conn = db.connect(emp.base, creer=False)
        try:
            ligne = db.fetch_one(conn, "SELECT * FROM v_pilotage") or {}
            nom = parametres.get_parametre(conn, "nom_projet")
        finally:
            conn.close()
    except sqlite3.Error as erreur:
        journal_log.error("Résumé du projet « %s » illisible : %s", code, erreur)
        return None, None
    return {champ: ligne.get(champ) for champ in CHAMPS_RESUME}, nom


def _role(conn: sqlite3.Connection, compte: Utilisateur, code: str) -> str | None:
    if compte.local:
        return compte.role
    return comptes.get_utilisateur(conn, compte.id or 0, code).role


def carte(conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, projet: dict) -> dict:
    resume, nom_projet = _resume(registre, projet["code"])
    return {
        "code": projet["code"],
        "nom_projet": nom_projet,
        "nom_equipe": projet["nom_equipe"],
        "acces": _role(conn, compte, projet["code"]),
        "hors_ligne": projet["code"] not in registre.projets,
        "resume": resume,
    }


def _projets(conn: sqlite3.Connection) -> list[dict]:
    return db.fetch_all(
        conn,
        "SELECT p.code, p.dossier, p.nom_equipe, d.organisme FROM projet p"
        " LEFT JOIN dossier d ON d.code = p.dossier WHERE p.archive = 0 AND p.reference = 0"
        " ORDER BY p.nom_equipe IS NULL, p.nom_equipe, p.code",
    )


def _roles_du_compte(conn: sqlite3.Connection, compte: Utilisateur) -> dict[str, Any]:
    """Profils d'organisme, dossiers de responsable et projets directs du compte."""
    if compte.id is None:
        return {"profils": {}, "responsables": set(), "directs": set()}
    uid = (compte.id,)
    return {
        "profils": dict(
            conn.execute(
                "SELECT organisme, profil FROM acces_organisme WHERE utilisateur_id = ?", uid
            ).fetchall()
        ),
        "responsables": {
            r[0]
            for r in conn.execute(
                "SELECT dossier FROM acces_dossier WHERE utilisateur_id = ?", uid
            ).fetchall()
        },
        "directs": {
            r[0]
            for r in conn.execute(
                "SELECT projet FROM acces WHERE utilisateur_id = ?", uid
            ).fetchall()
        },
    }


def _visible(compte: Utilisateur, roles: dict[str, Any], projet: dict) -> bool:
    return (
        compte.admin_serveur
        or projet["code"] in roles["directs"]
        or (projet["organisme"] is not None and projet["organisme"] in roles["profils"])
        or (projet["dossier"] is not None and projet["dossier"] in roles["responsables"])
    )


def _destination(
    compte: Utilisateur, roles: dict, cartes: list[dict], nb_organismes: int
) -> str | None:
    """Projet où envoyer directement le compte, quand l'accueil n'aurait qu'une carte."""
    if len(cartes) != 1:
        return None
    seul_membre = not (compte.admin_serveur or roles["profils"] or roles["responsables"])
    serveur_sans_structure = compte.admin_serveur and nb_organismes == 0
    return f"/p/{cartes[0]['code']}/" if seul_membre or serveur_sans_structure else None


def _compte(compte: Utilisateur) -> dict:
    return {"nom": compte.nom, "admin_serveur": compte.admin_serveur, "local": compte.local}


def get_accueil(conn: sqlite3.Connection, registre: Registre, compte: Utilisateur) -> dict:
    roles = _roles_du_compte(conn, compte)
    projets = [p for p in _projets(conn) if _visible(compte, roles, p)]
    organismes = db.fetch_all(
        conn, "SELECT code, nom FROM organisme WHERE archive = 0 ORDER BY nom"
    )
    dossiers = db.fetch_all(
        conn, "SELECT code, organisme, nom FROM dossier WHERE archive = 0 ORDER BY nom"
    )
    cartes = {p["code"]: carte(conn, registre, compte, p) for p in projets}
    resultat = []
    for org in organismes:
        voit_tout = compte.admin_serveur or org["code"] in roles["profils"]
        sous_dossiers = []
        for dos in (d for d in dossiers if d["organisme"] == org["code"]):
            liste = [cartes[p["code"]] for p in projets if p["dossier"] == dos["code"]]
            if liste or voit_tout or dos["code"] in roles["responsables"]:
                page = voit_tout or dos["code"] in roles["responsables"]
                sous_dossiers.append({**dos, "page": page, "projets": liste})
        if sous_dossiers or voit_tout:
            resultat.append(
                {
                    **org,
                    "profil": roles["profils"].get(org["code"]),
                    "gestion": hierarchie.peut_gerer(conn, compte, org["code"]),
                    "page": voit_tout,
                    "dossiers": sous_dossiers,
                }
            )
    hors_dossier = [cartes[p["code"]] for p in projets if p["dossier"] is None]
    return {
        "compte": _compte(compte),
        "organismes": resultat,
        "hors_dossier": hors_dossier,
        "destination": _destination(compte, roles, list(cartes.values()), len(organismes)),
    }


def get_vue_dossier(
    conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, code: str
) -> dict:
    dossier = hierarchie.get_dossier(conn, code)
    hierarchie.exiger_vue_dossier(conn, compte, dossier)
    gestion = hierarchie.peut_gerer(conn, compte, dossier["organisme"])
    projets = [p for p in _projets(conn) if p["dossier"] == code]
    responsables = db.fetch_all(
        conn,
        "SELECT u.id, u.nom FROM acces_dossier a JOIN utilisateur u ON u.id = a.utilisateur_id"
        " WHERE a.dossier = ? ORDER BY u.nom",
        (code,),
    )
    return {
        **dossier,
        "organisme": hierarchie.get_organisme(conn, dossier["organisme"]),
        "compte": _compte(compte),
        "gestion": gestion,
        "reference": reference.code_reference(code) if gestion else None,
        "a_jour": reference.etat_des_projets(conn, registre, code) if gestion else {},
        "projets": [carte(conn, registre, compte, p) for p in projets],
        "responsables": responsables,
        "candidats": hierarchie.list_candidats(conn, code) if gestion else [],
    }


def get_vue_organisme(
    conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, code: str
) -> dict:
    organisme = hierarchie.get_organisme(conn, code)
    hierarchie.exiger_vue_organisme(conn, compte, code)
    gestion = hierarchie.peut_gerer(conn, compte, code)
    projets = _projets(conn)
    dossiers = []
    for dos in db.fetch_all(
        conn,
        "SELECT code, nom, nom_projet FROM dossier WHERE organisme = ? AND archive = 0"
        " ORDER BY nom",
        (code,),
    ):
        codes = [p["code"] for p in projets if p["dossier"] == dos["code"]]
        budgets = [(_resume(registre, c)[0] or {}).get("budget_ht") for c in codes]
        connus = [b for b in budgets if b is not None]
        dossiers.append(
            {**dos, "nb_projets": len(codes), "budget_ht": sum(connus) if connus else None}
        )
    membres = (
        db.fetch_all(
            conn,
            "SELECT u.id, u.nom, u.identifiant, a.profil FROM acces_organisme a"
            " JOIN utilisateur u ON u.id = a.utilisateur_id WHERE a.organisme = ? ORDER BY u.nom",
            (code,),
        )
        if gestion
        else []
    )
    return {
        **organisme,
        "compte": _compte(compte),
        "gestion": gestion,
        "fournisseurs": reference.code_organisme(code),
        "dossiers": dossiers,
        "membres": membres,
    }
