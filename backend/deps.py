"""Dépendances FastAPI partagées par les routes : connexions, utilisateur, droits."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import authentification, comptes, droits
from backend.services.droits import Utilisateur
from backend.services.export_excel import PlanificateurExport
from backend.services.projets import EmplacementsProjet

COOKIE_SESSION = "nomentrace_session"


def get_projet(request: Request) -> str:
    """Code du projet de la requête, posé par l'aiguillage d'après l'adresse /p/<code>/."""
    return request.state.projet


Projet = Annotated[str, Depends(get_projet)]

# Routes servies sous la référence d'un dossier : ses seuls réglages communs.
ROUTES_REFERENCE: tuple[str, ...] = (
    "/api/session",
    "/api/sante",
    "/api/blocs",
    "/api/listes",
    "/api/attributs",
    "/api/parametres",
    "/api/journal",
    "/api/historique",
)


def get_emplacements(request: Request) -> EmplacementsProjet:
    """Base et dossiers du projet de la requête ; 503 s'il est hors ligne."""
    code = get_projet(request)
    registre = request.app.state.registre
    emp = registre.projets.get(code)
    if code in registre.references and not request.scope["path"].startswith(ROUTES_REFERENCE):
        raise Introuvable("La référence d'un dossier ne sert que ses réglages communs.")
    if emp is None:
        raise ErreurMetier(
            f"Le projet « {code} » est hors ligne : sa base n'a pas pu être préparée au"
            " démarrage. Voir le journal du serveur.",
            503,
        )
    return emp


Emplacements = Annotated[EmplacementsProjet, Depends(get_emplacements)]


def get_export(request: Request, emp: Emplacements) -> PlanificateurExport:
    """Planificateur de l'export Excel du projet de la requête."""
    return request.app.state.exports[emp.code]


Export = Annotated[PlanificateurExport, Depends(get_export)]


def get_conn_comptes(request: Request) -> Iterator[sqlite3.Connection]:
    """Connexion à la base des comptes pour la durée de la requête."""
    conn = db.connect(request.app.state.chemin_comptes)
    try:
        yield conn
    finally:
        conn.close()


def get_utilisateur(request: Request) -> Utilisateur | None:
    """Utilisateur de la requête : implicite en mode local, sinon lu depuis la session.

    Les droits sont relus dans la base à chaque requête : un rôle retiré ou un compte
    désactivé prend effet immédiatement, sans attendre la fin de la session.
    """
    if request.app.state.mode_local:
        return droits.UTILISATEUR_LOCAL
    jeton = request.cookies.get(COOKIE_SESSION)
    if not jeton:
        return None
    conn = db.connect(request.app.state.chemin_comptes)
    try:
        utilisateur_id = authentification.get_session(conn, jeton)
        if utilisateur_id is None:
            return None
        return comptes.get_utilisateur(conn, utilisateur_id, get_projet(request))
    finally:
        conn.close()


UtilisateurRequete = Annotated[Utilisateur | None, Depends(get_utilisateur)]


def get_conn(emp: Emplacements, utilisateur: UtilisateurRequete) -> Iterator[sqlite3.Connection]:
    """Connexion à la base du projet ; ses écritures sont journalisées au nom de l'utilisateur.

    La base doit exister : une requête n'en crée jamais une vide.
    """
    conn = db.connect(emp.base, utilisateur.nom if utilisateur else None, creer=False)
    try:
        yield conn
    finally:
        conn.close()


def verifier_acces(
    request: Request,
    utilisateur: UtilisateurRequete,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> None:
    """Applique la règle de la route demandée (table REGLES de services/droits.py)."""
    route = request.scope.get("route")
    regle = droits.get_regle(request.method, getattr(route, "path", ""))
    droits.verifier(regle, utilisateur, conn, request.path_params)


def exiger_mode_connecte(request: Request) -> None:
    """Routes des comptes : sans objet en mode local, où aucun compte n'existe."""
    if request.app.state.mode_local:
        raise ErreurMetier("Mode local : aucun compte à gérer, la connexion est désactivée.", 409)


def get_connecte(utilisateur: UtilisateurRequete) -> Utilisateur:
    """Utilisateur d'une route qui exige une connexion (déjà vérifiée par verifier_acces)."""
    if utilisateur is None:
        raise droits.NonConnecte()
    return utilisateur


Connecte = Annotated[Utilisateur, Depends(get_connecte)]


def get_auteur(utilisateur: UtilisateurRequete) -> str | None:
    """Nom de l'utilisateur connecté, qui signe une action ; None en mode local (sans compte).

    Sert de valeur par défaut aux champs « déposé par », « demandée par », « par qui » : en
    mode connecté, on sait qui agit, il n'y a plus à le saisir.
    """
    if utilisateur is None or utilisateur.local:
        return None
    return utilisateur.nom


Auteur = Annotated[str | None, Depends(get_auteur)]


# --- Routes communes : hors de tout projet ------------------------------------------------------


def get_compte(request: Request) -> Utilisateur | None:
    """Compte de la requête, sans rôle de projet ; implicite en mode local.

    Les routes communes (accueil, organismes, dossiers, connexion) n'ouvrent aucune base de
    projet : elles répondent même si le projet de l'instance est hors ligne.
    """
    if request.app.state.mode_local:
        return droits.UTILISATEUR_LOCAL
    jeton = request.cookies.get(COOKIE_SESSION)
    if not jeton:
        return None
    conn = db.connect(request.app.state.chemin_comptes)
    try:
        utilisateur_id = authentification.get_session(conn, jeton)
        return comptes.get_compte(conn, utilisateur_id) if utilisateur_id is not None else None
    finally:
        conn.close()


CompteRequete = Annotated[Utilisateur | None, Depends(get_compte)]


def verifier_acces_commun(request: Request, compte: CompteRequete) -> None:
    """Règle d'une route commune (table REGLES) ; le contrôle fin est fait par le service."""
    route = request.scope.get("route")
    regle = droits.get_regle(request.method, getattr(route, "path", ""))
    droits.verifier(regle, compte, None, request.path_params)


def get_compte_connecte(compte: CompteRequete) -> Utilisateur:
    if compte is None:
        raise droits.NonConnecte()
    return compte


Compte = Annotated[Utilisateur, Depends(get_compte_connecte)]
