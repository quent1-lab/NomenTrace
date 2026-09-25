"""Routes des composants."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from backend.arrondi import round_output
from backend.deps import Connecte, get_conn
from backend.models import ComposantCreation, ComposantModif, Reclassement, ValeursAttributs
from backend.services import composants, droits, export_composants, reclassement
from backend.services.composants import FiltresComposants

router = APIRouter(prefix="/api/composants", tags=["composants"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Filtres d'attribut, répétables : ?attr=tension:egal:24&attr=materiau:vide
FiltresAttributs = Annotated[list[str] | None, Query()]


def _filtres(filtres: FiltresComposants, attr: list[str] | None) -> FiltresComposants:
    filtres.attr = attr or []
    return filtres


@router.get("")
def read_composants(
    conn: Conn, filtres: Annotated[FiltresComposants, Depends()], attr: FiltresAttributs = None
) -> list[dict]:
    return round_output(composants.list_composants(conn, _filtres(filtres, attr)))


# Déclarée avant /{identifiant}, sinon « export » serait lu comme un identifiant.
@router.get("/export")
def export_composants_filtres(
    conn: Conn,
    filtres: Annotated[FiltresComposants, Depends()],
    colonnes: str | None = None,
    attr: FiltresAttributs = None,
) -> Response:
    contenu = export_composants.build_export_composants(
        conn, _filtres(filtres, attr), export_composants.parse_colonnes(conn, colonnes)
    )
    nom = export_composants.nom_fichier()
    return Response(
        contenu,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/{identifiant}")
def read_composant(identifiant: str, conn: Conn) -> dict:
    return round_output(composants.get_fiche(conn, identifiant))


@router.post("", status_code=201)
def create_composant(corps: ComposantCreation, conn: Conn, utilisateur: Connecte) -> dict:
    droits.exiger_bloc(utilisateur, corps.bloc_code)
    return round_output(composants.create_composant(conn, corps.model_dump()))


@router.patch("/{identifiant}")
def update_composant(identifiant: str, corps: ComposantModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(composants.patch_composant(conn, identifiant, modifications))


@router.delete("/{identifiant}")
def archive_composant(identifiant: str, conn: Conn) -> dict:
    composants.archive_composant(conn, identifiant)
    return {"statut": "archivé"}


@router.post("/{identifiant}/reclasser", status_code=201)
def reclasser_composant(identifiant: str, corps: Reclassement, conn: Conn) -> dict:
    return round_output(reclassement.reclasser_composant(conn, identifiant, corps.bloc_code))


@router.put("/{identifiant}/attributs")
def update_attributs(identifiant: str, corps: ValeursAttributs, conn: Conn) -> dict:
    return composants.patch_attributs(conn, identifiant, corps.valeurs)
