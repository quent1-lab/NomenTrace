"""Routes des blocs fonctionnels."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import BlocCreation, BlocModif
from backend.services import blocs, composants

router = APIRouter(prefix="/api/blocs", tags=["blocs"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_blocs(conn: Conn) -> list[dict]:
    return round_output(blocs.list_blocs(conn))


@router.post("", status_code=201)
def create_bloc(corps: BlocCreation, conn: Conn) -> dict:
    return round_output(blocs.create_bloc(conn, corps.model_dump()))


@router.get("/{code}/prochain-id")
def read_prochain_id(code: str, conn: Conn) -> dict:
    return {"id": composants.preview_id(conn, code)}


@router.patch("/{code}")
def update_bloc(code: str, corps: BlocModif, conn: Conn) -> dict:
    return round_output(blocs.patch_bloc(conn, code, corps.model_dump(exclude_unset=True)))
