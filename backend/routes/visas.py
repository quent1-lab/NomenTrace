"""Routes des visas de composants."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_conn
from backend.models import Visas
from backend.services import visas

router = APIRouter(prefix="/api", tags=["visas"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/visas/compte")
def read_compte(conn: Conn) -> dict:
    return {"a_voir": visas.count_a_voir(conn)}


@router.post("/visas")
def create_visas(corps: Visas, conn: Conn) -> dict:
    return {"vises": visas.viser(conn, corps.composants)}
