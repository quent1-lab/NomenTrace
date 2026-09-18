"""Routes de pilotage, des paramètres, du journal et de l'export."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import ParametresModif
from backend.services import journal, parametres, pilotage

router = APIRouter(prefix="/api", tags=["pilotage"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/pilotage")
def read_pilotage(conn: Conn) -> dict:
    return round_output(pilotage.get_pilotage(conn))


@router.get("/parametres")
def read_parametres(conn: Conn) -> dict:
    return parametres.list_parametres(conn)


@router.patch("/parametres")
def update_parametres(corps: ParametresModif, conn: Conn) -> dict:
    return parametres.patch_parametres(conn, corps.model_dump(exclude_unset=True))


@router.get("/journal")
def read_journal(
    conn: Conn,
    table_cible: str | None = None,
    cle_cible: str | None = None,
    limite: int = 500,
) -> list[dict]:
    return journal.list_journal(conn, table_cible, cle_cible, min(max(limite, 1), 5000))


@router.post("/export")
def create_export(request: Request) -> dict:
    reussi = request.app.state.export.export_now()
    return {"statut": "ok" if reussi else "en_attente"}
