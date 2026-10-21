"""Route de santé."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.deps import Emplacements, UtilisateurRequete, get_conn
from backend.models import SanteReponse
from backend.services import sante

router = APIRouter(prefix="/api", tags=["santé"])


@router.get("/sante", response_model=SanteReponse)
def read_sante(
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
    utilisateur: UtilisateurRequete,
    emp: Emplacements,
    request: Request,
) -> dict:
    """Indique que le serveur répond ; le nom du projet et l'export restent aux connectés.

    Sans préfixe, c'est le projet de l'instance : hors ligne, la réponse est 503, ce qui
    fait échouer le contrôle de santé d'une mise à jour et déclenche son retour arrière.
    """
    # La référence d'un dossier n'a pas d'export Excel.
    export = request.app.state.exports.get(emp.code)
    etat = sante.get_sante(conn, export.en_attente if export else False)
    if utilisateur is None or utilisateur.role is None:
        etat.update(nom_projet=None, export_en_attente=False)
    return etat
