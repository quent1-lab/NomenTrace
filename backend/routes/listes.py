"""Routes des listes de valeurs paramétrables."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_conn
from backend.models import ValeurListeCreation, ValeurListeModif
from backend.services import listes

router = APIRouter(prefix="/api/listes", tags=["listes"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_listes(conn: Conn) -> dict:
    return listes.list_listes(conn)


@router.post("/{liste}", status_code=201)
def create_valeur(liste: str, corps: ValeurListeCreation, conn: Conn) -> dict:
    return listes.create_valeur(conn, liste, corps.model_dump(exclude_unset=True))


@router.patch("/{liste}/{code}")
def update_valeur(liste: str, code: str, corps: ValeurListeModif, conn: Conn) -> dict:
    return listes.patch_valeur(conn, liste, code, corps.model_dump(exclude_unset=True))


@router.delete("/{liste}/{code}")
def delete_valeur(liste: str, code: str, conn: Conn) -> dict:
    listes.delete_valeur(conn, liste, code)
    return {"statut": "supprimé"}
