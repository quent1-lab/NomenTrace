"""Routes des ensembles et des affectations."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import (
    AffectationCreation,
    AffectationModif,
    EnsembleCreation,
    EnsembleDuplication,
    EnsembleModif,
)
from backend.services import ensembles, ensembles_arbre, ensembles_copie

router = APIRouter(prefix="/api", tags=["ensembles"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/ensembles")
def read_ensembles(conn: Conn) -> list[dict]:
    return round_output(ensembles_arbre.list_ensembles(conn))


@router.get("/ensembles/arbre")
def read_arbre(conn: Conn) -> dict:
    return round_output(ensembles_arbre.get_arbre(conn))


@router.get("/ensembles/repartition")
def read_repartition(conn: Conn, cumul: bool = False) -> list[dict]:
    return round_output(ensembles.list_repartition(conn, cumul))


@router.get("/ensembles/incoherences")
def read_incoherences(conn: Conn) -> list[dict]:
    return ensembles.list_incoherences(conn)


@router.get("/ensembles/{code}")
def read_ensemble(code: str, conn: Conn) -> dict:
    return round_output(ensembles_arbre.get_ensemble(conn, code))


@router.post("/ensembles", status_code=201)
def create_ensemble(corps: EnsembleCreation, conn: Conn) -> dict:
    return round_output(ensembles.create_ensemble(conn, corps.model_dump()))


@router.patch("/ensembles/{code}")
def update_ensemble(code: str, corps: EnsembleModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(ensembles.patch_ensemble(conn, code, modifications))


@router.delete("/ensembles/{code}")
def archive_ensemble(code: str, conn: Conn) -> dict:
    ensembles.archive_ensemble(conn, code)
    return {"statut": "archivé"}


@router.get("/ensembles/{code}/copie")
def read_proposition_copie(code: str, nouveau: str, conn: Conn) -> list[dict]:
    """Sous-ensembles qu'une copie emporterait, avec le code proposé pour chacun."""
    return ensembles_copie.get_proposition(conn, code, nouveau)


@router.post("/ensembles/{code}/copie", status_code=201)
def create_copie(code: str, corps: EnsembleDuplication, conn: Conn) -> dict:
    demande = corps.model_dump()
    if "parent_code" not in corps.model_fields_set:
        del demande["parent_code"]
    return round_output(ensembles_copie.dupliquer_ensemble(conn, code, demande))


@router.get("/ensembles/{code}/composants")
def read_composants_ensemble(code: str, conn: Conn) -> list[dict]:
    return round_output(ensembles.list_composants_ensemble(conn, code))


@router.post("/ensembles/{code}/affectations", status_code=201)
def create_affectation(code: str, corps: AffectationCreation, conn: Conn) -> dict:
    return round_output(ensembles.create_affectation(conn, code, corps.model_dump()))


@router.patch("/affectations/{identifiant}")
def update_affectation(identifiant: int, corps: AffectationModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(ensembles.patch_affectation(conn, identifiant, modifications))


@router.delete("/affectations/{identifiant}")
def delete_affectation(identifiant: int, conn: Conn) -> dict:
    ensembles.delete_affectation(conn, identifiant)
    return {"statut": "supprimé"}
