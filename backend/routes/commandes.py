"""Routes des commandes, de leurs lignes et des mouvements de stock."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import (
    CommandeCreation,
    CommandeModif,
    LigneCreation,
    LigneModif,
    MouvementCreation,
)
from backend.services import commandes, mouvements

router = APIRouter(prefix="/api", tags=["achats et stock"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/commandes")
def read_commandes(
    conn: Conn, statut: str | None = None, fournisseur: str | None = None
) -> list[dict]:
    return round_output(commandes.list_commandes(conn, statut, fournisseur))


@router.post("/commandes", status_code=201)
def create_commande(corps: CommandeCreation, conn: Conn) -> dict:
    return round_output(commandes.create_commande(conn, corps.model_dump()))


@router.patch("/commandes/{numero}")
def update_commande(numero: str, corps: CommandeModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(commandes.patch_commande(conn, numero, modifications))


@router.delete("/commandes/{numero}")
def archive_commande(numero: str, conn: Conn) -> dict:
    commandes.archive_commande(conn, numero)
    return {"statut": "archivé"}


@router.get("/commandes/{numero}/lignes")
def read_lignes(numero: str, conn: Conn) -> list[dict]:
    return round_output(commandes.list_lignes(conn, numero))


@router.post("/commandes/{numero}/lignes", status_code=201)
def create_ligne(numero: str, corps: LigneCreation, conn: Conn) -> dict:
    return round_output(commandes.create_ligne(conn, numero, corps.model_dump()))


@router.patch("/commandes/{numero}/lignes/{identifiant}")
def update_ligne(numero: str, identifiant: int, corps: LigneModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(commandes.patch_ligne(conn, numero, identifiant, modifications))


@router.delete("/commandes/{numero}/lignes/{identifiant}")
def delete_ligne(numero: str, identifiant: int, conn: Conn) -> dict:
    commandes.delete_ligne(conn, numero, identifiant)
    return {"statut": "supprimé"}


@router.get("/mouvements")
def read_mouvements(
    conn: Conn,
    composant: str | None = None,
    type_mouvement: str | None = None,
    ensemble: str | None = None,
) -> list[dict]:
    return mouvements.list_mouvements(conn, composant, type_mouvement, ensemble)


@router.post("/mouvements", status_code=201)
def create_mouvement(corps: MouvementCreation, conn: Conn) -> dict:
    return mouvements.create_mouvement(conn, corps.model_dump())
