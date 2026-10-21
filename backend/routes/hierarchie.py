"""Routes communes : accueil, organismes, dossiers et rangement des projets.

Elles n'ouvrent la base d'aucun projet pour vérifier les droits : le service contrôle
l'organisme ou le dossier visé (services/hierarchie.py).
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.arrondi import round_output
from backend.deps import Compte, get_conn_comptes
from backend.models import (
    DossierCreation,
    DossierModif,
    MembreOrganisme,
    OrganismeCreation,
    OrganismeModif,
    ProfilModif,
    ProjetCreation,
    ProjetModif,
    ResponsableAchats,
)
from backend.services import accueil, hierarchie, projets, reference

router = APIRouter(prefix="/api", tags=["hierarchie"])
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


@router.get("/accueil")
def read_accueil(request: Request, compte: Compte, conn: ConnComptes) -> dict:
    return round_output(accueil.get_accueil(conn, request.app.state.registre, compte))


# --- Organismes ---------------------------------------------------------------------------------


@router.post("/organismes", status_code=201)
def create_organisme(corps: OrganismeCreation, compte: Compte, conn: ConnComptes) -> dict:
    return hierarchie.create_organisme(conn, compte, corps.code, corps.nom)


@router.get("/organismes/{code}")
def read_organisme(code: str, request: Request, compte: Compte, conn: ConnComptes) -> dict:
    vue = accueil.get_vue_organisme(conn, request.app.state.registre, compte, code)
    return round_output(vue)


@router.patch("/organismes/{code}")
def update_organisme(code: str, corps: OrganismeModif, compte: Compte, conn: ConnComptes) -> dict:
    return hierarchie.patch_organisme(conn, compte, code, corps.nom)


@router.post("/organismes/{code}/dossiers", status_code=201)
def create_dossier(
    code: str, corps: DossierCreation, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    etat = request.app.state
    dossier, emp = hierarchie.create_dossier(
        conn, compte, code, corps.model_dump(), (etat.dossier_data, etat.dossier_echange)
    )
    etat.registre.references.add(emp.code)
    projets.mettre_en_ligne(etat.registre, etat.exports, emp)
    return dossier


@router.post("/organismes/{code}/membres", status_code=201)
def create_membre(code: str, corps: MembreOrganisme, compte: Compte, conn: ConnComptes) -> dict:
    return hierarchie.invite_membre(conn, compte, code, corps.model_dump())


@router.patch("/organismes/{code}/membres/{identifiant}")
def update_membre(
    code: str, identifiant: int, corps: ProfilModif, compte: Compte, conn: ConnComptes
) -> dict:
    hierarchie.set_profil(conn, compte, code, identifiant, corps.profil)
    return {"statut": "modifié"}


@router.delete("/organismes/{code}/membres/{identifiant}")
def delete_membre(code: str, identifiant: int, compte: Compte, conn: ConnComptes) -> dict:
    hierarchie.retirer_membre(conn, compte, code, identifiant)
    return {"statut": "retiré"}


# --- Dossiers et projets ------------------------------------------------------------------------


@router.get("/dossiers/{code}")
def read_dossier(code: str, request: Request, compte: Compte, conn: ConnComptes) -> dict:
    return round_output(accueil.get_vue_dossier(conn, request.app.state.registre, compte, code))


@router.patch("/dossiers/{code}")
def update_dossier(
    code: str, corps: DossierModif, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    dossier = hierarchie.patch_dossier(conn, compte, code, corps.model_dump(exclude_unset=True))
    return {**dossier, "propagation": reference.propager(conn, request.app.state.registre, code)}


@router.post("/dossiers/{code}/projets", status_code=201)
def create_projet(
    code: str, corps: ProjetCreation, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    etat = request.app.state
    emp, invitation = hierarchie.create_projet(
        conn, compte, code, corps.model_dump(), (etat.dossier_data, etat.dossier_echange)
    )
    projets.mettre_en_ligne(etat.registre, etat.exports, emp)
    reference.initialiser_si_neuve(etat.registre, code)
    reference.accorder(conn, etat.registre, emp.code, code)
    return {"code": emp.code, "invitation": invitation}


@router.post("/dossiers/{code}/responsables", status_code=201)
def create_responsable(
    code: str, corps: ResponsableAchats, compte: Compte, conn: ConnComptes
) -> dict:
    hierarchie.add_responsable(conn, compte, code, corps.utilisateur_id)
    return {"statut": "ajouté"}


@router.delete("/dossiers/{code}/responsables/{identifiant}")
def delete_responsable(code: str, identifiant: int, compte: Compte, conn: ConnComptes) -> dict:
    hierarchie.retirer_responsable(conn, compte, code, identifiant)
    return {"statut": "retiré"}


@router.patch("/projets/{code}")
def update_projet(
    code: str, corps: ProjetModif, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    modifs = corps.model_dump(exclude_unset=True)
    return hierarchie.patch_projet(conn, compte, code, modifs, request.app.state.registre)
