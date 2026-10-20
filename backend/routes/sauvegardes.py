"""Routes des sauvegardes : liste, sauvegarde immédiate, restauration, archive complète."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.deps import Emplacements, Export, get_conn
from backend.services import corbeille, sauvegardes

router = APIRouter(prefix="/api/sauvegardes", tags=["sauvegardes"])


@router.get("")
def read_sauvegardes(emp: Emplacements) -> list[dict]:
    return sauvegardes.describe_sauvegardes(emp.sauvegardes)


@router.get("/archive")
def read_archive(emp: Emplacements) -> FileResponse:
    """Base et documents du projet dans un zip temporaire, supprimé une fois envoyé."""
    chemin = sauvegardes.build_archive(emp.base, emp.documents)
    return FileResponse(
        chemin,
        media_type="application/zip",
        filename=sauvegardes.nom_archive(),
        background=BackgroundTask(chemin.unlink, missing_ok=True),
    )


@router.get("/corbeille")
def read_corbeille(emp: Emplacements) -> dict:
    return corbeille.describe_corbeille(emp.documents)


@router.post("/corbeille/vider")
def vider_corbeille(
    emp: Emplacements, conn: Annotated[sqlite3.Connection, Depends(get_conn)]
) -> dict:
    return corbeille.vider_corbeille(conn, emp.documents)


@router.post("", status_code=201)
def create_sauvegarde(emp: Emplacements) -> dict:
    chemin = sauvegardes.create_sauvegarde(emp.base, emp.sauvegardes)
    return {"nom": chemin.name if chemin else None}


@router.post("/{nom}/restaurer")
def restore_sauvegarde(nom: str, emp: Emplacements, export: Export) -> dict:
    resultat = sauvegardes.restore_sauvegarde(emp.base, emp.sauvegardes, nom, emp.documents)
    export.signaler()
    return resultat
