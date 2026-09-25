"""Routes des attributs paramétrables et de la répartition de leurs valeurs."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.arrondi import round_output
from backend.deps import get_conn
from backend.models import (
    AttributCreation,
    AttributModif,
    AttributValeurCreation,
    AttributValeurModif,
)
from backend.services import attributs, attributs_analyse

router = APIRouter(prefix="/api/attributs", tags=["attributs"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("")
def read_attributs(conn: Conn) -> list[dict]:
    return attributs.list_attributs(conn)


@router.post("", status_code=201)
def create_attribut(corps: AttributCreation, conn: Conn) -> dict:
    return attributs.create_attribut(conn, corps.model_dump())


@router.patch("/{code}")
def update_attribut(code: str, corps: AttributModif, conn: Conn) -> dict:
    return attributs.patch_attribut(conn, code, corps.model_dump(exclude_unset=True))


@router.post("/{code}/valeurs", status_code=201)
def create_valeur(code: str, corps: AttributValeurCreation, conn: Conn) -> dict:
    return attributs.create_valeur(conn, code, corps.libelle)


@router.patch("/{code}/valeurs/{valeur:path}")
def update_valeur(code: str, valeur: str, corps: AttributValeurModif, conn: Conn) -> dict:
    return attributs.patch_valeur(conn, code, valeur, corps.model_dump(exclude_unset=True))


@router.get("/{code}/repartition")
def read_repartition(
    code: str,
    conn: Conn,
    bloc: str | None = None,
    ensemble: str | None = None,
    mode_appro: str | None = None,
) -> dict:
    filtres = {"bloc": bloc, "ensemble": ensemble, "mode_appro": mode_appro}
    return round_output(attributs_analyse.get_repartition(conn, code, filtres))


@router.get("/{code}/calcul")
def read_calcul(
    code: str,
    conn: Conn,
    bloc: str | None = None,
    ensemble: str | None = None,
    mode_appro: str | None = None,
) -> dict:
    # Valeurs d'attribut, pas des montants : aucun arrondi à deux décimales.
    filtres = {"bloc": bloc, "ensemble": ensemble, "mode_appro": mode_appro}
    return attributs_analyse.get_calcul(conn, code, filtres)
