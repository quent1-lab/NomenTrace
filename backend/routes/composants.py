"""Routes des composants."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import ComposantCreation, ComposantModif
from backend.services import composants
from backend.services.composants import FiltresComposants

router = APIRouter(prefix="/api/composants", tags=["composants"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_composants(conn: Conn, filtres: Annotated[FiltresComposants, Depends()]) -> list[dict]:
    return round_output(composants.list_composants(conn, filtres))


@router.get("/{identifiant}")
def read_composant(identifiant: str, conn: Conn) -> dict:
    return round_output(composants.get_fiche(conn, identifiant))


@router.post("", status_code=201)
def create_composant(corps: ComposantCreation, conn: Conn) -> dict:
    return round_output(composants.create_composant(conn, corps.model_dump()))


@router.patch("/{identifiant}")
def update_composant(identifiant: str, corps: ComposantModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(composants.patch_composant(conn, identifiant, modifications))


@router.delete("/{identifiant}")
def archive_composant(identifiant: str, conn: Conn) -> dict:
    composants.archive_composant(conn, identifiant)
    return {"statut": "archivé"}
