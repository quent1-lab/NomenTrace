"""Routes des sauvegardes : liste, sauvegarde immédiate, restauration, archive complète."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.services import sauvegardes

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


@router.post("", status_code=201)
def create_sauvegarde(request: Request) -> dict:
    chemin = sauvegardes.create_sauvegarde(request.app.state.chemin_base, _dossier(request))
    return {"nom": chemin.name if chemin else None}


@router.post("/{nom}/restaurer")
def restore_sauvegarde(nom: str, request: Request) -> dict:
    resultat = sauvegardes.restore_sauvegarde(request.app.state.chemin_base, _dossier(request), nom)
    request.app.state.export.signaler()
    return resultat
