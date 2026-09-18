"""Routes des documents joints aux commandes et aux composants."""

import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from backend.deps import get_conn
from backend.erreurs import ErreurMetier
from backend.models import DocumentModif
from backend.services import documents

router = APIRouter(prefix="/api", tags=["documents"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
journal_log = logging.getLogger(__name__)


async def _deposer(
    request: Request,
    conn: sqlite3.Connection,
    fichiers: list[UploadFile],
    meta: dict,
) -> dict:
    """Enregistre chaque fichier ; un refus n'empêche pas les autres d'être joints."""
    documents.ensure_cible(conn, meta.get("commande_numero"), meta.get("composant_id"))
    joints, erreurs = [], []
    for fichier in fichiers:
        contenu = await fichier.read(documents.TAILLE_MAX + 1)
        nom = fichier.filename or "document"
        try:
            dossier = request.app.state.dossier_documents
            joints.append(documents.add_document(conn, dossier, (nom, contenu), meta))
        except ErreurMetier as erreur:
            journal_log.info("Document refusé (%s) : %s", nom, erreur.message)
            erreurs.append(erreur.message)
    if not joints:
        raise ErreurMetier(" ".join(erreurs) or "Aucun fichier reçu.")
    return {"documents": joints, "erreurs": erreurs}


@router.get("/commandes/{numero}/documents")
def read_documents_commande(numero: str, conn: Conn) -> list[dict]:
    return documents.list_documents_commande(conn, numero)


@router.post("/commandes/{numero}/documents", status_code=201)
async def create_documents_commande(
    numero: str,
    request: Request,
    conn: Conn,
    fichiers: Annotated[list[UploadFile], File()],
    type_document: Annotated[str, Form()],
    commentaire: Annotated[str | None, Form()] = None,
) -> dict:
    meta = {"commande_numero": numero, "type_document": type_document, "commentaire": commentaire}
    return await _deposer(request, conn, fichiers, meta)


@router.get("/composants/{identifiant}/documents")
def read_documents_composant(identifiant: str, conn: Conn) -> list[dict]:
    return documents.list_documents_composant(conn, identifiant)


@router.post("/composants/{identifiant}/documents", status_code=201)
async def create_documents_composant(
    identifiant: str,
    request: Request,
    conn: Conn,
    fichiers: Annotated[list[UploadFile], File()],
    type_document: Annotated[str, Form()],
    commentaire: Annotated[str | None, Form()] = None,
) -> dict:
    meta = {"composant_id": identifiant, "type_document": type_document, "commentaire": commentaire}
    return await _deposer(request, conn, fichiers, meta)


@router.get("/documents/{identifiant}/fichier")
def read_fichier(identifiant: int, request: Request, conn: Conn) -> FileResponse:
    fichier = documents.get_fichier(conn, request.app.state.dossier_documents, identifiant)
    return FileResponse(
        fichier["chemin"],
        media_type=fichier["type_mime"] or "application/octet-stream",
        filename=fichier["nom"],
        content_disposition_type="inline" if fichier["en_ligne"] else "attachment",
    )


@router.patch("/documents/{identifiant}")
def update_document(identifiant: int, corps: DocumentModif, conn: Conn) -> dict:
    return documents.patch_document(conn, identifiant, corps.model_dump(exclude_unset=True))


@router.delete("/documents/{identifiant}")
def archive_document(identifiant: int, conn: Conn) -> dict:
    documents.archive_document(conn, identifiant)
    return {"statut": "retiré"}
