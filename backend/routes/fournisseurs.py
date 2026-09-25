"""Routes des fournisseurs."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import ApplicationListeFournisseurs, FournisseurCreation, FournisseurModif
from backend.services import fournisseurs, fournisseurs_liste

router = APIRouter(prefix="/api/fournisseurs", tags=["fournisseurs"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_fournisseurs(conn: Conn) -> list[dict]:
    return fournisseurs.list_fournisseurs(conn)


@router.post("", status_code=201)
def create_fournisseur(corps: FournisseurCreation, conn: Conn) -> dict:
    return fournisseurs.create_fournisseur(conn, corps.model_dump())


@router.post("/comparaison")
async def compare_liste(fichier: Annotated[UploadFile, File()], conn: Conn) -> dict:
    lus = fournisseurs_liste.read_liste(await fichier.read())
    return fournisseurs_liste.compare_liste(conn, lus)


@router.post("/comparaison/appliquer")
def apply_liste(corps: ApplicationListeFournisseurs, conn: Conn) -> dict:
    return fournisseurs_liste.apply_liste(
        conn,
        [c.model_dump() for c in corps.creations],
        [
            {"nom": c.nom, "champs": c.champs.model_dump(exclude_unset=True)}
            for c in corps.completions
        ],
    )


@router.get("/{nom:path}")
def read_fiche(nom: str, conn: Conn) -> dict:
    return round_output(fournisseurs.get_fiche(conn, nom))


@router.delete("/{nom:path}")
def archive_fournisseur(nom: str, conn: Conn) -> dict:
    fournisseurs.archive_fournisseur(conn, nom)
    return {"statut": "archivé"}


@router.patch("/{nom:path}")
def update_fournisseur(nom: str, corps: FournisseurModif, conn: Conn) -> dict:
    return fournisseurs.patch_fournisseur(conn, nom, corps.model_dump(exclude_unset=True))
