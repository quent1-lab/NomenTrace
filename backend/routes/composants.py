"""Routes des composants."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from backend.arrondi import round_output
from backend.deps import Connecte, Emplacements, Projet, get_conn, get_conn_comptes
from backend.models import ComposantCreation, ComposantModif, Reclassement, ValeursAttributs
from backend.services import catalogue, composants, droits, export_composants, reclassement
from backend.services.composants import FiltresComposants

router = APIRouter(prefix="/api/composants", tags=["composants"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]
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


# Catalogue du dossier : déclaré avant /{identifiant}, comme l'export.
@router.get("/catalogue")
def search_catalogue(
    conn: Conn,
    comptes: ConnComptes,
    request: Request,
    projet: Projet,
    designation: str | None = None,
    ref_fabricant: str | None = None,
    fonction: str | None = None,
) -> dict:
    saisie = {"designation": designation, "ref_fabricant": ref_fabricant, "fonction": fonction}
    registre = request.app.state.registre
    return catalogue.search_catalogue(conn, comptes, registre, projet, saisie)


@router.get("/catalogue/reprise")
def read_reprise(
    conn: Conn, comptes: ConnComptes, request: Request, projet: Projet, source: str, id: str
) -> dict:
    registre = request.app.state.registre
    return round_output(catalogue.get_reprise(conn, comptes, registre, projet, source, id))


@router.get("/{identifiant}")
def read_composant(identifiant: str, conn: Conn) -> dict:
    return round_output(composants.get_fiche(conn, identifiant))


@router.post("", status_code=201)
def create_composant(
    corps: ComposantCreation,
    conn: Conn,
    utilisateur: Connecte,
    request: Request,
    emp: Emplacements,
    comptes: ConnComptes,
) -> dict:
    droits.exiger_bloc(utilisateur, corps.bloc_code)
    valeurs = corps.model_dump(exclude={"reprise"})
    if corps.reprise is None:
        return round_output(composants.create_composant(conn, valeurs))
    registre = request.app.state.registre
    cree = catalogue.create_avec_reprise(
        conn, comptes, registre, emp, valeurs, corps.reprise.model_dump()
    )
    return round_output(cree)


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
