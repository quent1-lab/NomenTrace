"""Route de la recherche globale."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_conn
from backend.services import recherche

router = APIRouter(prefix="/api", tags=["recherche"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/recherche")
def read_recherche(q: str, conn: Conn) -> list[dict]:
    return recherche.rechercher(conn, q)
