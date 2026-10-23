"""Routes des commandes, de leurs lignes et des mouvements de stock."""

import sqlite3
from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from backend.arrondi import round_output
from backend.deps import Auteur, Projet, UtilisateurRequete, get_conn, get_conn_comptes
from backend.erreurs import ErreurMetier
from backend.models import (
    CommandeCreation,
    CommandeModif,
    DemandesDevis,
    FraisCreation,
    FraisModif,
    LigneCreation,
    LigneModif,
    MouvementCreation,
    Reception,
    RetenuesSuivi,
)
from backend.services import (
    commandes,
    communes,
    demande_document,
    demandes_devis,
    frais,
    mouvements,
    suivi_achats,
)

router = APIRouter(prefix="/api", tags=["achats et stock"])
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
ConnComptes = Annotated[sqlite3.Connection, Depends(get_conn_comptes)]


@router.get("/commandes")
def read_commandes(
    conn: Conn, statut: str | None = None, fournisseur: str | None = None
) -> list[dict]:
    return round_output(commandes.list_commandes(conn, statut, fournisseur))


@router.get("/demandes-devis")
def read_candidats_devis(conn: Conn) -> dict:
    return round_output(demandes_devis.list_candidats(conn))


@router.post("/demandes-devis", status_code=201)
def create_demandes_devis(corps: DemandesDevis, conn: Conn, auteur: Auteur) -> list[dict]:
    return round_output(demandes_devis.create_demandes(conn, corps.composants, auteur))


@router.post("/commandes", status_code=201)
def create_commande(corps: CommandeCreation, conn: Conn, auteur: Auteur) -> dict:
    valeurs = corps.model_dump()
    valeurs["demande_par"] = valeurs["demande_par"] or auteur
    return round_output(commandes.create_commande(conn, valeurs))


@router.get("/commandes/{numero}")
def read_commande(numero: str, conn: Conn) -> dict:
    return round_output(commandes.get_commande(conn, numero))


@router.patch("/commandes/{numero}")
def update_commande(numero: str, corps: CommandeModif, conn: Conn) -> dict:
    modifications = corps.model_dump(exclude_unset=True)
    return round_output(commandes.patch_commande(conn, numero, modifications))


@router.delete("/commandes/{numero}")
def archive_commande(numero: str, conn: Conn) -> dict:
    commandes.archive_commande(conn, numero)
    return {"statut": "archivé"}


TYPES_DOCUMENT = {
    "pdf": (".pdf", "application/pdf", demande_document.build_pdf),
    "xlsx": (
        ".xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        demande_document.build_excel,
    ),
}


@router.get("/commandes/{numero}/demande-devis.{format_document}")
def read_demande_devis(
    numero: str,
    format_document: Literal["pdf", "xlsx"],
    conn: Conn,
    utilisateur: UtilisateurRequete,
    avant: Annotated[date | None, Query()] = None,
) -> Response:
    """Document à envoyer au fournisseur : la liste des articles à chiffrer."""
    extension, type_mime, construire = TYPES_DOCUMENT[format_document]
    demandeur = demande_document.demandeur(conn, utilisateur)
    donnees = demande_document.get_donnees(
        conn, numero, demandeur, avant.isoformat() if avant else None
    )
    nom = demande_document.nom_fichier(donnees, extension)
    return Response(
        construire(donnees),
        media_type=type_mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"},
    )


TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/suivi-achats/analyse")
async def analyse_suivi(fichier: Annotated[UploadFile, File()], conn: Conn) -> dict:
    """Ce que le classeur de suivi de l'établissement ferait changer, sans rien écrire."""
    contenu = await fichier.read()
    return round_output(await run_in_threadpool(suivi_achats.analyse, conn, contenu))


@router.post("/suivi-achats/appliquer")
async def appliquer_suivi(
    fichier: Annotated[UploadFile, File()], retenues: Annotated[str, Form()], conn: Conn
) -> Response:
    """Applique les changements retenus et renvoie le classeur complété, sous le même nom."""
    try:
        choix = RetenuesSuivi.model_validate_json(retenues).root
    except ValidationError as erreur:
        raise ErreurMetier("Choix du suivi illisibles.") from erreur
    contenu = await fichier.read()
    complete = await run_in_threadpool(suivi_achats.appliquer, conn, contenu, choix)
    nom = fichier.filename or "suivi des achats.xlsx"
    return Response(
        complete,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"},
    )


@router.get("/commandes/{numero}/frais")
def read_frais(numero: str, conn: Conn) -> list[dict]:
    return round_output(frais.list_frais(conn, numero))


@router.post("/commandes/{numero}/frais", status_code=201)
def create_frais(numero: str, corps: FraisCreation, conn: Conn) -> dict:
    return round_output(frais.create_frais(conn, numero, corps.model_dump()))


@router.patch("/frais/{identifiant}")
def update_frais(identifiant: int, corps: FraisModif, conn: Conn) -> dict:
    return round_output(frais.patch_frais(conn, identifiant, corps.model_dump(exclude_unset=True)))


@router.delete("/frais/{identifiant}")
def delete_frais(identifiant: int, conn: Conn) -> dict:
    frais.delete_frais(conn, identifiant)
    return {"statut": "retiré"}


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


@router.post("/commandes/{numero}/reception")
def create_reception(
    numero: str,
    corps: Reception,
    request: Request,
    conn: Conn,
    conn_comptes: ConnComptes,
    projet: Projet,
    auteur: Auteur,
) -> dict:
    valeurs = corps.model_dump()
    valeurs["par_qui"] = valeurs["par_qui"] or auteur
    registre = request.app.state.registre
    return round_output(
        communes.receive_dans_le_projet(conn, conn_comptes, registre, projet, numero, valeurs)
    )


@router.get("/stock")
def read_stock(conn: Conn) -> list[dict]:
    return round_output(mouvements.list_stock(conn))


@router.get("/mouvements")
def read_mouvements(
    conn: Conn,
    composant: str | None = None,
    type_mouvement: str | None = None,
    ensemble: str | None = None,
) -> list[dict]:
    return mouvements.list_mouvements(conn, composant, type_mouvement, ensemble)


@router.post("/mouvements", status_code=201)
def create_mouvement(corps: MouvementCreation, conn: Conn, auteur: Auteur) -> dict:
    valeurs = corps.model_dump()
    valeurs["par_qui"] = valeurs["par_qui"] or auteur
    return mouvements.create_mouvement(conn, valeurs)
