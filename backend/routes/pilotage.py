"""Routes de pilotage, des paramètres, du journal et de l'export."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.erreurs import Introuvable
from backend.models import ParametresModif
from backend.services import export_excel, historique, journal, logo, parametres, pilotage
from backend.services.historique import FiltresJournal

router = APIRouter(prefix="/api", tags=["pilotage"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/pilotage")
def read_pilotage(conn: Conn) -> dict:
    return round_output(pilotage.get_pilotage(conn))


@router.get("/parametres")
def read_parametres(conn: Conn) -> dict:
    return parametres.list_parametres(conn)


@router.patch("/parametres")
def update_parametres(corps: ParametresModif, conn: Conn) -> dict:
    return parametres.patch_parametres(conn, corps.model_dump(exclude_unset=True))


@router.get("/parametres/logo")
def read_logo(conn: Conn) -> Response:
    image = logo.get_logo(conn)
    if image is None:
        raise Introuvable("Aucun logo enregistré.")
    return Response(
        image["contenu"], media_type=image["type_mime"], headers={"Cache-Control": "no-cache"}
    )


@router.get("/parametres/logo/infos")
def read_logo_infos(conn: Conn) -> dict:
    image = logo.get_logo(conn)
    if image is None:
        return {"present": False}
    return {
        "present": True,
        "largeur": image["largeur"],
        "hauteur": image["hauteur"],
        "modifie_le": image["modifie_le"],
    }


@router.post("/parametres/logo")
async def update_logo(fichier: Annotated[UploadFile, File()], conn: Conn) -> dict:
    contenu = await fichier.read(logo.TAILLE_MAX + 1)
    return await run_in_threadpool(logo.set_logo, conn, contenu)


@router.delete("/parametres/logo")
def delete_logo(conn: Conn) -> dict:
    logo.delete_logo(conn)
    return {"statut": "retiré"}


@router.get("/journal")
def read_journal(
    conn: Conn,
    table_cible: str | None = None,
    cle_cible: str | None = None,
    limite: int = 500,
) -> list[dict]:
    return journal.list_journal(conn, table_cible, cle_cible, min(max(limite, 1), 5000))


@router.get("/historique")
def read_historique(
    conn: Conn,
    filtres: Annotated[FiltresJournal, Depends()],
    page: int = 1,
    taille: int = 100,
) -> dict:
    return historique.list_journal(conn, filtres, page, taille)


@router.get("/historique/tables")
def read_tables_historique(conn: Conn) -> list[str]:
    return historique.list_tables(conn)


@router.get("/historique/export")
def read_export_historique(conn: Conn, filtres: Annotated[FiltresJournal, Depends()]) -> Response:
    contenu = historique.build_export_journal(conn, filtres)
    return Response(
        contenu,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{historique.nom_export()}"'},
    )


@router.post("/export")
def create_export(request: Request) -> dict:
    reussi = request.app.state.export.export_now()
    return {"statut": "ok" if reussi else "en_attente"}


@router.get("/export/classeur")
def read_export_classeur(request: Request) -> Response:
    """Classeur d'export complet, régénéré à la demande ; rien n'est écrit dans echange/."""
    contenu = export_excel.build_export_bytes(request.app.state.chemin_base)
    nom = export_excel.nom_telechargement()
    return Response(
        contenu,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )
