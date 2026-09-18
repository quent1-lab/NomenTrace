"""Routes des sauvegardes : liste, sauvegarde immédiate, restauration."""

from pathlib import Path

from fastapi import APIRouter, Request

from backend.services import sauvegardes

router = APIRouter(prefix="/api/sauvegardes", tags=["sauvegardes"])


def _dossier(request: Request) -> Path:
    return request.app.state.dossier_echange / "sauvegardes"


@router.get("")
def read_sauvegardes(request: Request) -> list[dict]:
    return sauvegardes.describe_sauvegardes(_dossier(request))


@router.post("", status_code=201)
def create_sauvegarde(request: Request) -> dict:
    chemin = sauvegardes.create_sauvegarde(request.app.state.chemin_base, _dossier(request))
    return {"nom": chemin.name if chemin else None}


@router.post("/{nom}/restaurer")
def restore_sauvegarde(nom: str, request: Request) -> dict:
    resultat = sauvegardes.restore_sauvegarde(request.app.state.chemin_base, _dossier(request), nom)
    request.app.state.export.signaler()
    return resultat
