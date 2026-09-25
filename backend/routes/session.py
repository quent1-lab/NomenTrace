"""Routes de connexion, de déconnexion et d'invitation."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from backend.deps import COOKIE_SESSION, Connecte, get_conn, get_conn_comptes
from backend.erreurs import ErreurMetier
from backend.models import Connexion, InvitationAcceptation, InvitationVerification
from backend.services import authentification, comptes, parametres

router = APIRouter(prefix="/api", tags=["session"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


def _adresse(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


def _ouvrir(
    request: Request, reponse: Response, conn: sqlite3.Connection, utilisateur_id: int
) -> dict:
    """Ouvre la session si le compte a accès au projet, et pose le cookie."""
    utilisateur = comptes.get_utilisateur(conn, utilisateur_id, request.app.state.code_projet)
    if utilisateur.role is None:
        raise ErreurMetier("Votre compte n'a pas accès à ce projet.", 403)
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
    utilisateur_id = authentification.login(
        conn,
        request.app.state.limiteurs,
        corps.identifiant,
        corps.mot_de_passe,
        _adresse(request),
    )
    return _ouvrir(request, reponse, conn, utilisateur_id)


@router.get("/session")
def read_session(request: Request, utilisateur: Connecte, conn: Conn) -> dict:
    nom_projet = parametres.get_parametre(conn, "nom_projet") if utilisateur.role else None
    return {
        "utilisateur": utilisateur.description(),
        "nom_projet": nom_projet,
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
    utilisateur_id = comptes.accept_invitation(conn, corps.jeton, corps.mot_de_passe)
    return _ouvrir(request, reponse, conn, utilisateur_id)
