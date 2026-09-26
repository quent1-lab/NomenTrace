"""Dépendances FastAPI partagées par les routes : connexions, utilisateur, droits."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import authentification, comptes, droits
from backend.services.droits import Utilisateur

COOKIE_SESSION = "nomentrace_session"


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
        return comptes.get_utilisateur(conn, utilisateur_id, request.app.state.code_projet)
    finally:
        conn.close()


UtilisateurRequete = Annotated[Utilisateur | None, Depends(get_utilisateur)]


def get_conn(request: Request, utilisateur: UtilisateurRequete) -> Iterator[sqlite3.Connection]:
    """Connexion à la base du projet ; ses écritures sont journalisées au nom de l'utilisateur."""
    conn = db.connect(request.app.state.chemin_base, utilisateur.nom if utilisateur else None)
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
