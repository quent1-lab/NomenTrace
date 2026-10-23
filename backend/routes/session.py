"""Routes de connexion, de déconnexion et d'invitation.

La connexion est commune à tous les projets : elle n'ouvre aucune base de projet et répond
même si le projet de l'instance est hors ligne. Seule la lecture de la session (droits dans
le projet de la page) passe par la base du projet.
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from backend.deps import COOKIE_SESSION, Connecte, get_conn, get_conn_comptes, get_projet
from backend.erreurs import ErreurMetier
from backend.models import Connexion, InvitationAcceptation, InvitationVerification
from backend.services import (
    authentification,
    comptes,
    hierarchie,
    parametres,
    projets,
    reference,
)

router = APIRouter(prefix="/api", tags=["session"])
router_projet = APIRouter(prefix="/api", tags=["session"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


def _adresse(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


def _ouvrir(
    request: Request, reponse: Response, conn: sqlite3.Connection, utilisateur_id: int
) -> dict:
    """Ouvre la session si le compte a au moins un accès, et pose le cookie."""
    if not comptes.a_un_acces(conn, utilisateur_id):
        raise ErreurMetier("Votre compte n'a accès à aucun projet.", 403)
    utilisateur = comptes.get_utilisateur(conn, utilisateur_id, get_projet(request))
    precedente = request.cookies.get(COOKIE_SESSION)
    if precedente:
        # Une nouvelle connexion remplace la session que ce navigateur avait peut-être.
        authentification.close_session(conn, precedente)
    session = authentification.open_session(conn, utilisateur_id, _adresse(request))
    reponse.set_cookie(
        COOKIE_SESSION,
        session.jeton,
        max_age=int(authentification.DUREE_SESSION.total_seconds()),
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return {"utilisateur": utilisateur.description()}


@router.post("/session")
def create_session(
    corps: Connexion, request: Request, reponse: Response, conn: ConnComptes
) -> dict:
    # La place est réservée avant le hachage (lent) : au-delà de quelques connexions à la
    # fois, la requête est refusée aussitôt, sans bloquer le reste de l'application.
    with authentification.limiter_connexions():
        utilisateur_id = authentification.login(
            conn,
            request.app.state.limiteurs,
            corps.identifiant,
            corps.mot_de_passe,
            _adresse(request),
        )
        return _ouvrir(request, reponse, conn, utilisateur_id)


@router_projet.get("/session")
def read_session(
    request: Request, utilisateur: Connecte, conn: Conn, conn_comptes: ConnComptes
) -> dict:
    nom_projet = parametres.get_parametre(conn, "nom_projet") if utilisateur.role else None
    situation = reference.situation(conn_comptes, conn, get_projet(request))
    # La page du dossier (commandes communes) ne s'ouvre qu'à qui voit le dossier.
    dossier = situation["dossier"] and hierarchie.get_dossier(conn_comptes, situation["dossier"])
    return {
        "utilisateur": utilisateur.description(),
        "nom_projet": nom_projet,
        "nom_equipe": projets.get_nom_equipe(conn_comptes, get_projet(request)),
        **situation,
        "voit_dossier": bool(dossier)
        and hierarchie.voit_dossier(conn_comptes, utilisateur, dossier),
        "mode_local": request.app.state.mode_local,
    }


@router.delete("/session")
def delete_session(request: Request, reponse: Response, conn: ConnComptes) -> dict:
    jeton = request.cookies.get(COOKIE_SESSION)
    if jeton:
        authentification.close_session(conn, jeton)
    reponse.delete_cookie(COOKIE_SESSION, path="/")
    return {"statut": "déconnecté"}


@router.post("/invitation/verifier")
def read_invitation(corps: InvitationVerification, conn: ConnComptes) -> dict:
    return comptes.get_invitation(conn, corps.jeton)


@router.post("/invitation")
def accept_invitation(
    corps: InvitationAcceptation, request: Request, reponse: Response, conn: ConnComptes
) -> dict:
    with authentification.limiter_connexions():
        utilisateur_id = comptes.accept_invitation(conn, corps.jeton, corps.mot_de_passe)
        return _ouvrir(request, reponse, conn, utilisateur_id)
