"""Route de santé."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.deps import UtilisateurRequete, get_conn
from backend.models import SanteReponse
from backend.services import sante

router = APIRouter(prefix="/api", tags=["santé"])


@router.get("/sante", response_model=SanteReponse)
def read_sante(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
    utilisateur: UtilisateurRequete,
) -> dict:
    """Indique que le serveur répond ; le nom du projet et l'export restent aux connectés."""
    etat = sante.get_sante(conn, request.app.state.export.en_attente)
    if utilisateur is None or utilisateur.role is None:
        etat.update(nom_projet=None, export_en_attente=False)
    return etat
