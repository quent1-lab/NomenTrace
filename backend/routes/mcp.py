"""Routes de l'accès par un assistant IA : réglage, jetons personnels, et la route MCP."""

import json
import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from backend import db
from backend.deps import Connecte, get_conn_comptes, get_projet
from backend.models import JetonApiCreation, McpReglage
from backend.services import jetons_api, mcp

journal_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mcp"])
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


@router.get("/mcp/reglage")
def read_reglage(request: Request, compte: Connecte, conn: ConnComptes) -> dict:
    projet = get_projet(request)
    acces = jetons_api.get_acces(conn, projet)
    return {
        "acces": acces,
        "autorise": jetons_api.autorise(compte, acces),
        "jetons": [] if compte.local else jetons_api.list_jetons(conn, compte, projet),
    }


@router.patch("/mcp/reglage")
def update_reglage(
    corps: McpReglage, request: Request, compte: Connecte, conn: ConnComptes
) -> dict:
    jetons_api.set_acces(conn, get_projet(request), corps.acces, compte.nom)
    return read_reglage(request, compte, conn)


@router.post("/mcp/jetons", status_code=201)
def create_jeton(
    corps: JetonApiCreation, request: Request, compte: Connecte, conn: ConnComptes
) -> dict:
    return jetons_api.create_jeton(conn, compte, get_projet(request), corps.nom)


@router.delete("/mcp/jetons/{identifiant}", status_code=204)
def delete_jeton(
    identifiant: int, request: Request, compte: Connecte, conn: ConnComptes
) -> Response:
    jetons_api.revoke_jeton(conn, compte, get_projet(request), identifiant)
    return Response(status_code=204)


def _refus_jeton(message: str) -> JSONResponse:
    return JSONResponse(
        {"erreur": message}, status_code=401, headers={"WWW-Authenticate": 'Bearer realm="mcp"'}
    )


def _compte_du_jeton(request: Request, projet: str) -> int | None:
    entete = request.headers.get("authorization", "")
    schema, _, jeton = entete.partition(" ")
    if schema.lower() != "bearer" or not jeton.strip():
        return None
    conn = db.connect(request.app.state.chemin_comptes)
    try:
        return jetons_api.authentifier(conn, jeton.strip(), projet)
    finally:
        conn.close()


@router.post("/mcp")
async def post_mcp(request: Request) -> Response:
    """Point d'entrée MCP : jeton personnel exigé, sauf en mode local (poste seul)."""
    projet = get_projet(request)
    etat = request.app.state
    if projet in etat.registre.references:
        return JSONResponse({"erreur": "Pas d'assistant IA sur des paramètres communs."}, 404)
    if etat.mode_local:
        conn = db.connect(etat.chemin_comptes)
        try:
            ouvert = jetons_api.get_acces(conn, projet) != "ferme"
        finally:
            conn.close()
        if not ouvert:
            return JSONResponse(
                {"erreur": "L'accès par un assistant IA n'est pas ouvert sur ce projet."}, 403
            )
        utilisateur_id = None
    else:
        utilisateur_id = _compte_du_jeton(request, projet)
        if utilisateur_id is None:
            return _refus_jeton("Jeton absent, inconnu, révoqué ou sans accès à ce projet.")
    try:
        message = json.loads(await request.body())
    except json.JSONDecodeError, UnicodeDecodeError:
        return JSONResponse(mcp.erreur_lecture(), status_code=400)
    ctx = mcp.Contexte(
        app=request.app,
        projet=projet,
        schema=request.url.scheme,
        hote=request.headers.get("host", ""),
        client=(request.client.host, request.client.port) if request.client else None,
        utilisateur_id=utilisateur_id,
    )
    reponse = await mcp.traiter(ctx, message)
    if reponse is None:
        return Response(status_code=202)
    return JSONResponse(reponse)
