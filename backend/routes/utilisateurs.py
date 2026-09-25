"""Routes de gestion des comptes, réservées à l'administrateur."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.deps import Connecte, exiger_mode_connecte, get_conn, get_conn_comptes
from backend.models import UtilisateurCreation, UtilisateurModif
from backend.services import blocs, comptes

router = APIRouter(
    prefix="/api/utilisateurs",
    tags=["utilisateurs"],
    dependencies=[Depends(exiger_mode_connecte)],
)
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


@router.get("")
def read_utilisateurs(request: Request, conn: ConnComptes) -> list[dict]:
    return comptes.list_utilisateurs(conn, request.app.state.code_projet)


@router.post("", status_code=201)
def create_utilisateur(
    corps: UtilisateurCreation, request: Request, moi: Connecte, conn: ConnComptes, projet: Conn
) -> dict:
    blocs.check_codes(projet, corps.blocs)
    return comptes.create_utilisateur(
        conn, request.app.state.code_projet, corps.model_dump(), moi.nom
    )


@router.patch("/{identifiant}")
def update_utilisateur(
    identifiant: int, corps: UtilisateurModif, request: Request, conn: ConnComptes, projet: Conn
) -> dict:
    if corps.blocs is not None:
        blocs.check_codes(projet, corps.blocs)
    modifs = corps.model_dump(exclude_unset=True)
    return comptes.patch_utilisateur(conn, request.app.state.code_projet, identifiant, modifs)


@router.post("/{identifiant}/invitation")
def renew_invitation(identifiant: int, request: Request, moi: Connecte, conn: ConnComptes) -> dict:
    return comptes.renew_invitation(conn, request.app.state.code_projet, identifiant, moi.nom)
