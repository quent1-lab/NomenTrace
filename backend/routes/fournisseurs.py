"""Routes des fournisseurs."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_conn
from backend.models import FournisseurCreation, FournisseurModif
from backend.services import fournisseurs

router = APIRouter(prefix="/api/fournisseurs", tags=["fournisseurs"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_fournisseurs(conn: Conn) -> list[dict]:
    return fournisseurs.list_fournisseurs(conn)


@router.post("", status_code=201)
def create_fournisseur(corps: FournisseurCreation, conn: Conn) -> dict:
    return fournisseurs.create_fournisseur(conn, corps.model_dump())


@router.patch("/{nom}")
def update_fournisseur(nom: str, corps: FournisseurModif, conn: Conn) -> dict:
    return fournisseurs.patch_fournisseur(conn, nom, corps.model_dump(exclude_unset=True))
