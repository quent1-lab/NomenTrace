"""Routes des commandes communes d'un dossier (phase 16).

Routes communes, hors de tout projet : le service contrôle le dossier visé et le droit
d'acheteur commun (services/communes.py). Une écriture touche les bases de plusieurs
projets : l'export Excel de chacun est relancé.
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.arrondi import round_output
from backend.deps import Compte, get_conn_comptes
from backend.models import (
    CommuneCreation,
    CommuneModif,
    FraisCreation,
    FraisModif,
    LigneCommuneModif,
    LignesCommune,
)
from backend.services import accueil, communes

router = APIRouter(prefix="/api/dossiers/{code}/communes", tags=["communes"])
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


def _apres_ecriture(request: Request, resultat: dict) -> dict:
    for projet in resultat.get("projets", []):
        export = request.app.state.exports.get(projet["projet"])
        if export is not None:
            export.signaler()
    return round_output(resultat)


@router.get("")
def list_communes(code: str, request: Request, compte: Compte, conn: ConnComptes) -> dict:
    return round_output(communes.list_communes(conn, request.app.state.registre, compte, code))


@router.post("", status_code=201)
def create_commune(
    code: str, corps: CommuneCreation, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    registre = request.app.state.registre
    return round_output(
        communes.create_commune(conn, registre, compte, code, corps.model_dump(exclude_none=True))
    )


@router.get("/fournisseurs")
def list_fournisseurs(code: str, request: Request, compte: Compte, conn: ConnComptes) -> list:
    registre = request.app.state.registre
    dossier = communes.dossier_acheteur(conn, compte, code)
    return communes.list_fournisseurs(communes.emplacements(conn, registre, dossier))


@router.get("/{numero}")
def read_commune(
    code: str, numero: str, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    registre = request.app.state.registre
    commune = communes.get_commune(conn, registre, compte, code, numero)
    return round_output({**commune, "compte": accueil.resume_compte(compte)})


@router.patch("/{numero}")
def update_commune(
    code: str,
    numero: str,
    corps: CommuneModif,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    modifs = corps.model_dump(exclude_unset=True)
    resultat = communes.patch_commune(
        conn, request.app.state.registre, compte, code, numero, modifs
    )
    return _apres_ecriture(request, resultat)


@router.delete("/{numero}")
def archive_commune(
    code: str, numero: str, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    registre = request.app.state.registre
    resultat = communes.patch_commune(conn, registre, compte, code, numero, {"archive": 1})
    return _apres_ecriture(request, resultat)


@router.get("/{numero}/candidats")
def list_candidats(
    code: str, numero: str, request: Request, compte: Compte, conn: ConnComptes
) -> list:
    registre = request.app.state.registre
    return round_output(communes.list_candidats(conn, registre, compte, code, numero))


@router.post("/{numero}/lignes", status_code=201)
def create_lignes(
    code: str,
    numero: str,
    corps: LignesCommune,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    lignes = [ligne.model_dump() for ligne in corps.lignes]
    resultat = communes.add_lignes(conn, request.app.state.registre, compte, code, numero, lignes)
    return _apres_ecriture(request, resultat)


@router.patch("/{numero}/lignes/{projet}/{identifiant}")
def update_ligne(
    code: str,
    numero: str,
    projet: str,
    identifiant: int,
    corps: LigneCommuneModif,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    cible = (code, numero, projet, identifiant)
    modifs = corps.model_dump(exclude_unset=True)
    resultat = communes.patch_ligne(conn, request.app.state.registre, compte, cible, modifs)
    return _apres_ecriture(request, resultat)


@router.delete("/{numero}/lignes/{projet}/{identifiant}")
def delete_ligne(
    code: str,
    numero: str,
    projet: str,
    identifiant: int,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    cible = (code, numero, projet, identifiant)
    resultat = communes.delete_ligne(conn, request.app.state.registre, compte, cible)
    return _apres_ecriture(request, resultat)


@router.post("/{numero}/frais", status_code=201)
def create_frais(
    code: str,
    numero: str,
    corps: FraisCreation,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    registre = request.app.state.registre
    cible = (code, numero, None)
    resultat = communes.ecrire_frais(conn, registre, compte, cible, corps.model_dump())
    return _apres_ecriture(request, resultat)


@router.patch("/{numero}/frais/{identifiant}")
def update_frais(
    code: str,
    numero: str,
    identifiant: int,
    corps: FraisModif,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    registre = request.app.state.registre
    modifs = corps.model_dump(exclude_unset=True)
    resultat = communes.ecrire_frais(conn, registre, compte, (code, numero, identifiant), modifs)
    return _apres_ecriture(request, resultat)


@router.delete("/{numero}/frais/{identifiant}")
def delete_frais(
    code: str,
    numero: str,
    identifiant: int,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    registre = request.app.state.registre
    resultat = communes.ecrire_frais(conn, registre, compte, (code, numero, identifiant), None)
    return _apres_ecriture(request, resultat)
