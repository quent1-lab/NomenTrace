"""Routes de l'écran nettoyage : contrôles, actions en lot, suppressions, purge du journal."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import PurgeJournal, TraitementLot
from backend.services import nettoyage, suppressions

router = APIRouter(prefix="/api/nettoyage", tags=["nettoyage"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def _emplacements(request: Request) -> suppressions.Emplacements:
    etat = request.app.state
    return suppressions.Emplacements(
        etat.chemin_base, etat.dossier_echange / "sauvegardes", etat.dossier_documents
    )


@router.get("/composants")
def read_controles_composants(conn: Conn) -> dict:
    return nettoyage.list_controles_composants(conn)


@router.post("/composants")
def process_composants(corps: TraitementLot, request: Request, conn: Conn) -> dict:
    return suppressions.process_composants(
        conn, _emplacements(request), corps.cles, corps.action, corps.simuler
    )


@router.get("/commandes")
def read_controles_commandes(conn: Conn) -> dict:
    return round_output(nettoyage.list_controles_commandes(conn))


@router.post("/commandes")
def process_commandes(corps: TraitementLot, request: Request, conn: Conn) -> dict:
    return suppressions.process_commandes(
        conn, _emplacements(request), corps.cles, corps.action, corps.simuler
    )


@router.get("/entites")
def read_entites_supprimables(conn: Conn) -> list[dict]:
    return suppressions.list_entites_supprimables(conn)


@router.delete("/entites/{type_entite}/{cle:path}")
def delete_entite(type_entite: str, cle: str, request: Request, conn: Conn) -> dict:
    suppressions.delete_entite(conn, _emplacements(request), type_entite, cle)
    return {"statut": "supprimé"}


@router.post("/journal/purge")
def purge_journal(_confirmation: PurgeJournal, request: Request, conn: Conn) -> dict:
    return {"lignes_supprimees": suppressions.purge_journal(conn, _emplacements(request))}
