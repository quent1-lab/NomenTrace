"""Routes des sauvegardes : liste, sauvegarde immédiate, restauration, archive complète."""

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.deps import get_conn
from backend.services import corbeille, sauvegardes

router = APIRouter(prefix="/api/sauvegardes", tags=["sauvegardes"])


def _dossier(request: Request) -> Path:
    return request.app.state.dossier_echange / "sauvegardes"


@router.get("")
def read_sauvegardes(request: Request) -> list[dict]:
    return sauvegardes.describe_sauvegardes(_dossier(request))


@router.get("/archive")
def read_archive(request: Request) -> FileResponse:
    """Base et documents dans un zip temporaire, supprimé une fois envoyé."""
    chemin = sauvegardes.build_archive(
        request.app.state.chemin_base, request.app.state.dossier_documents
    )
    return FileResponse(
        chemin,
        media_type="application/zip",
        filename=sauvegardes.nom_archive(),
        background=BackgroundTask(chemin.unlink, missing_ok=True),
    )


@router.get("/corbeille")
def read_corbeille(request: Request) -> dict:
    return corbeille.describe_corbeille(request.app.state.dossier_documents)


@router.post("/corbeille/vider")
def vider_corbeille(
    request: Request, conn: Annotated[sqlite3.Connection, Depends(get_conn)]
) -> dict:
    return corbeille.vider_corbeille(conn, request.app.state.dossier_documents)


@router.post("", status_code=201)
def create_sauvegarde(request: Request) -> dict:
    chemin = sauvegardes.create_sauvegarde(request.app.state.chemin_base, _dossier(request))
    return {"nom": chemin.name if chemin else None}


@router.post("/{nom}/restaurer")
def restore_sauvegarde(nom: str, request: Request) -> dict:
    etat = request.app.state
    resultat = sauvegardes.restore_sauvegarde(
        etat.chemin_base, _dossier(request), nom, etat.dossier_documents
    )
    request.app.state.export.signaler()
    return resultat
