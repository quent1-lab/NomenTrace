"""Routes des commandes communes d'un dossier (phase 16).

Routes communes, hors de tout projet : le service contrôle le dossier visé et le droit
d'acheteur commun (services/communes.py). Une écriture touche les bases de plusieurs
projets : l'export Excel de chacun est relancé.
"""

import sqlite3
from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from backend.arrondi import round_output
from backend.deps import Compte, get_conn_comptes
from backend.erreurs import ErreurMetier
from backend.models import (
    CommuneCreation,
    CommuneModif,
    FraisCreation,
    FraisModif,
    LigneCommuneModif,
    LignesCommune,
    ReceptionCommune,
    RetenuesSuivi,
)
from backend.services import (
    accueil,
    communes,
    communes_documents,
    demande_document,
    documents,
    suivi_communes,
)

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


@router.post("/{numero}/reception")
def create_reception(
    code: str,
    numero: str,
    corps: ReceptionCommune,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    valeurs = corps.model_dump()
    valeurs["par_qui"] = valeurs["par_qui"] or (None if compte.local else compte.nom)
    registre = request.app.state.registre
    resultat = communes.receive_commune(conn, registre, compte, (code, numero), valeurs)
    return _apres_ecriture(request, resultat)


TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/suivi/analyse")
async def analyse_suivi(
    code: str,
    fichier: Annotated[UploadFile, File()],
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> dict:
    """Ce que le classeur de l'établissement ferait changer aux communes, sans rien écrire."""
    contenu = await fichier.read()
    registre = request.app.state.registre
    resultat = await run_in_threadpool(
        suivi_communes.analyse, conn, registre, compte, code, contenu
    )
    return round_output(resultat)


@router.post("/suivi/appliquer")
async def appliquer_suivi(
    code: str,
    fichier: Annotated[UploadFile, File()],
    retenues: Annotated[str, Form()],
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> Response:
    """Applique les changements retenus et renvoie le classeur complété, sous le même nom."""
    try:
        choix = RetenuesSuivi.model_validate_json(retenues).root
    except ValidationError as erreur:
        raise ErreurMetier("Choix du suivi illisibles.") from erreur
    contenu = await fichier.read()
    registre = request.app.state.registre
    complete = await run_in_threadpool(
        suivi_communes.appliquer, conn, registre, compte, code, (contenu, choix)
    )
    nom = fichier.filename or "suivi des achats.xlsx"
    return Response(
        complete,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"},
    )


DOCUMENTS = {
    "pdf": (".pdf", "application/pdf", demande_document.build_pdf),
    "xlsx": (".xlsx", TYPE_XLSX, demande_document.build_excel),
}


@router.get("/{numero}/demande-devis.{format_document}")
def read_demande_devis(
    code: str,
    numero: str,
    format_document: Literal["pdf", "xlsx"],
    request: Request,
    compte: Compte,
    conn: ConnComptes,
    avant: Annotated[date | None, Query()] = None,
) -> Response:
    """Document à envoyer au fournisseur : les articles de tous les projets, regroupés."""
    extension, type_mime, construire = DOCUMENTS[format_document]
    registre = request.app.state.registre
    donnees = communes.get_demande_devis(
        conn, registre, compte, (code, numero), avant.isoformat() if avant else None
    )
    nom = demande_document.nom_fichier(donnees, extension)
    return Response(
        construire(donnees),
        media_type=type_mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"},
    )


@router.post("/{numero}/documents", status_code=201)
async def create_documents(
    code: str,
    numero: str,
    fichiers: Annotated[list[UploadFile], File()],
    type_document: Annotated[str, Form()],
    request: Request,
    compte: Compte,
    conn: ConnComptes,
    commentaire: Annotated[str | None, Form()] = None,
) -> dict:
    """Joint chaque fichier à la copie de chaque projet de la commune."""
    registre = request.app.state.registre
    emp, participants = communes.contexte_documents(conn, registre, compte, (code, numero, True))
    contenus = [
        (f.filename or "document", await f.read(documents.TAILLE_MAX + 1)) for f in fichiers
    ]
    meta = {"type_document": type_document, "commentaire": commentaire}
    return await run_in_threadpool(
        communes_documents.deposer, emp, participants, compte.nom, (contenus, meta)
    )


@router.delete("/{numero}/documents/{empreinte}")
def delete_document(
    code: str, numero: str, empreinte: str, request: Request, compte: Compte, conn: ConnComptes
) -> dict:
    registre = request.app.state.registre
    emp, participants = communes.contexte_documents(conn, registre, compte, (code, numero, True))
    return communes_documents.retirer(emp, participants, compte.nom, empreinte)


@router.get("/{numero}/documents/{projet}/{identifiant}/fichier")
def read_fichier(
    code: str,
    numero: str,
    projet: str,
    identifiant: int,
    request: Request,
    compte: Compte,
    conn: ConnComptes,
) -> FileResponse:
    registre = request.app.state.registre
    emp, participants = communes.contexte_documents(conn, registre, compte, (code, numero, False))
    fichier = communes_documents.fichier(emp, participants, projet, identifiant)
    return FileResponse(
        fichier["chemin"],
        media_type=fichier["type_mime"] or "application/octet-stream",
        filename=fichier["nom"],
        content_disposition_type="inline" if fichier["en_ligne"] else "attachment",
    )
