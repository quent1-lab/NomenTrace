"""Route de santé."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.deps import get_conn
from backend.models import SanteReponse
from backend.services import sante

router = APIRouter(prefix="/api", tags=["santé"])


@router.get("/sante", response_model=SanteReponse)
def read_sante(request: Request, conn: Annotated[sqlite3.Connection, Depends(get_conn)]) -> dict:
    """Indique que le serveur répond, avec la version du schéma et l'état de l'export."""
    return sante.get_sante(conn, request.app.state.export.en_attente)
