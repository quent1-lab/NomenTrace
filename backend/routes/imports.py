"""Routes des modèles à remplir et de l'import des fichiers de l'équipe."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from backend.deps import get_conn
from backend.models import ApplicationImport
from backend.services import import_analyse, import_application, import_depots, modeles

router = APIRouter(prefix="/api", tags=["import"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _telecharger(chemin: object) -> FileResponse:
    return FileResponse(chemin, media_type=TYPE_XLSX, filename=chemin.name)  # type: ignore[attr-defined]


@router.get("/blocs/{code}/modele")
def read_modele_bloc(code: str, request: Request, conn: Conn) -> FileResponse:
    dossier = request.app.state.dossier_echange / "modeles"
    return _telecharger(modeles.generate_modele_bloc(conn, dossier, code))


@router.get("/ensembles/{code}/modele")
def read_modele_ensemble(code: str, request: Request, conn: Conn) -> FileResponse:
    dossier = request.app.state.dossier_echange / "modeles"
    return _telecharger(modeles.generate_modele_ensemble(conn, dossier, code))


@router.get("/imports")
def read_depots(conn: Conn) -> list[dict]:
    return import_depots.list_depots(conn)


@router.post("/imports", status_code=201)
async def create_depot(
    request: Request,
    conn: Conn,
    fichiers: Annotated[list[UploadFile], File()],
    depose_par: Annotated[str | None, Form()] = None,
) -> dict:
    contenus = [(f.filename or "fichier.xlsx", await f.read()) for f in fichiers]
    dossier = request.app.state.dossier_echange / "imports"
    depot = import_analyse.analyse_depot(
        conn, dossier, contenus, (depose_par or "").strip() or None
    )
    return {"depot": depot}


@router.get("/imports/{depot}")
def read_depot(depot: int, conn: Conn) -> dict:
    return import_depots.get_depot(conn, depot)


@router.post("/imports/{depot}/appliquer")
def apply_depot(depot: int, corps: ApplicationImport, request: Request, conn: Conn) -> dict:
    return import_application.apply_depot(
        conn,
        request.app.state.chemin_base,
        request.app.state.dossier_echange / "sauvegardes",
        depot,
        corps.decisions,
    )


@router.post("/imports/{depot}/abandonner")
def abandon_depot(depot: int, conn: Conn) -> dict:
    import_depots.abandon_depot(conn, depot)
    return {"statut": "abandonné"}
