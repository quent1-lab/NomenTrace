"""Route de santé."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_conn
from backend.models import SanteReponse
from backend.services import sante

router = APIRouter(prefix="/api", tags=["santé"])


@router.get("/sante", response_model=SanteReponse)
def read_sante(conn: Annotated[sqlite3.Connection, Depends(get_conn)]) -> dict:
    """Indique que le serveur répond, avec la version du schéma et le nom du projet."""
    return sante.get_sante(conn)
