"""Point d'entrée de l'application Nomentrace."""

import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import config, db
from backend.aiguillage import AiguillageProjet, code_valide
from backend.deps import verifier_acces, verifier_acces_commun
from backend.erreurs import ErreurMetier
from backend.routes import (
    attributs,
    blocs,
    commandes,
    composants,
    documents,
    ensembles,
    fournisseurs,
    hierarchie,
    imports,
    listes,
    nettoyage,
    pilotage,
    recherche,
    sante,
    session,
    utilisateurs,
    visas,
)
from backend.routes import (
    sauvegardes as routes_sauvegardes,
)
from backend.securite import install_securite
from backend.services import authentification, comptes, projets, reference, sauvegardes
from backend.services.export_excel import PlanificateurExport

journal_log = logging.getLogger("nomentrace")

METHODES_ECRITURE: frozenset[str] = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Écritures qui ne touchent pas aux données du projet : elles ne relancent pas l'export.
SANS_EXPORT: tuple[str, ...] = (
    "/api/export",
    "/api/session",
    "/api/invitation",
    "/api/utilisateurs",
    "/api/accueil",
    "/api/organismes",
    "/api/dossiers",
    "/api/projets",
)

# Routes de l'API, dans l'ordre d'inclusion ; chacune a sa règle dans services/droits.py.
# Routes d'un projet : droits lus dans la base du projet de la requête.
MODULES = (
    sante,
    utilisateurs,
    pilotage,
    attributs,
    blocs,
    ensembles,
    fournisseurs,
    composants,
    commandes,
    listes,
    documents,
    imports,
    nettoyage,
    routes_sauvegardes,
    recherche,
    visas,
)
ROUTEURS_PROJET = (session.router_projet, *(module.router for module in MODULES))
# Routes communes : connexion, accueil, organismes, dossiers ; aucune base de projet.
ROUTEURS_COMMUNS = (session.router, hierarchie.router)


def _configure_logging() -> None:
    """Configure la journalisation au niveau INFO, avec horodatage."""
    logging.basicConfig(level=logging.INFO, format=config.FORMAT_LOG)


# Messages Pydantic les plus courants, traduits ; les autres gardent leur texte d'origine.
MESSAGES_VALIDATION: dict[str, str] = {
    "missing": "champ obligatoire manquant",
    "greater_than": "doit être supérieur à {gt}",
    "greater_than_equal": "doit être supérieur ou égal à {ge}",
    "less_than": "doit être inférieur à {lt}",
    "int_parsing": "un nombre entier est attendu",
    "int_from_float": "un nombre entier est attendu",
    "float_parsing": "un nombre est attendu",
    "string_too_short": "ne doit pas être vide",
    "string_too_long": "trop long ({max_length} caractères au plus)",
    "string_pattern_mismatch": "format invalide",
    "literal_error": "valeur non autorisée ; valeurs possibles : {expected}",
    "extra_forbidden": "champ inconnu",
    "bool_parsing": "vrai ou faux attendu",
    "value_error": "{error}",
}


def _message_validation(exc: RequestValidationError) -> str:
    details = []
    for erreur in exc.errors():
        champ = ".".join(str(p) for p in erreur.get("loc", ()) if p not in ("body", "query"))
        modele = MESSAGES_VALIDATION.get(erreur.get("type", ""))
        try:
            message = modele.format(**erreur.get("ctx", {})) if modele else erreur.get("msg")
        except KeyError:
            message = erreur.get("msg", "valeur invalide")
        details.append(f"{champ} : {message}")
    return "Données invalides (" + " ; ".join(details) + ")."


def _install_error_handlers(app: FastAPI) -> None:
    """Traduit toutes les erreurs en {"erreur": "..."} sans trace Python."""

    @app.exception_handler(ErreurMetier)
    async def _metier(_: Request, exc: ErreurMetier) -> JSONResponse:
        return JSONResponse({"erreur": exc.message}, status_code=exc.statut)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Requête refusée."
        if exc.status_code == 404 and message == "Not Found":
            message = "Ressource introuvable."
        if exc.status_code == 405:
            message = "Méthode non autorisée sur cette ressource."
        return JSONResponse({"erreur": message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"erreur": _message_validation(exc)}, status_code=422)

    @app.exception_handler(sqlite3.IntegrityError)
    async def _integrite(_: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
        journal_log.warning("Contrainte de base refusée : %s", exc)
        return JSONResponse(
            {"erreur": f"Opération refusée par une contrainte de la base ({exc})."},
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def _inattendue(_: Request, exc: Exception) -> JSONResponse:
        journal_log.exception("Erreur inattendue : %s", exc)
        return JSONResponse(
            {"erreur": "Erreur interne du serveur, consulter le journal."}, status_code=500
        )


def _preparer_comptes(chemin: Path, dossier_sauvegardes: Path) -> None:
    """Sauvegarde et migrations de la base commune (comptes et registre des projets).

    Ses sauvegardes vont dans un dossier à part : elles ne se mêlent pas à celles des
    projets et ne peuvent pas être restaurées à leur place depuis l'interface.
    """
    sauvegardes.create_sauvegarde(chemin, dossier_sauvegardes)
    version = comptes.prepare_base(chemin)
    journal_log.info("Base commune %s prête, schéma version %d", chemin, version)


def _preparer_projets(etat: Any, ancienne_base: Path) -> None:
    """Projet de l'instance (migration de l'ancienne base au besoin), puis chaque projet.

    Le registre est rempli sur place : l'aiguillage en garde la référence.
    """
    _preparer_comptes(etat.chemin_comptes, etat.dossier_echange / "sauvegardes" / "comptes")
    conn = db.connect(etat.chemin_comptes)
    try:
        instance = projets.emplacements(etat.dossier_data, etat.dossier_echange, etat.code_projet)
        projets.assurer_projet_instance(conn, ancienne_base, etat.dossier_echange, instance)
        charge = projets.charger_registre(conn, etat.dossier_data, etat.dossier_echange)
        if not etat.mode_local and comptes.count_admins(conn, etat.code_projet) == 0:
            journal_log.warning(
                "Aucun administrateur pour le projet « %s » : en créer un avec "
                "« python -m backend.comptes creer-admin ADRESSE --nom NOM ».",
                etat.code_projet,
            )
    finally:
        conn.close()
    etat.registre.projets.update(charge.projets)
    etat.registre.hors_ligne.update(charge.hors_ligne)
    etat.registre.references.update(charge.references)
    conn = db.connect(etat.chemin_comptes)
    try:
        reference.reprendre(conn, etat.registre, (etat.dossier_data, etat.dossier_echange))
    finally:
        conn.close()
    for code, emp in etat.registre.projets.items():
        if code not in etat.registre.references:
            etat.exports[code] = PlanificateurExport(emp.base, emp.exports)


def _propager_reglage_commun(etat: Any, code_ref: str) -> None:
    """Un réglage commun a changé : chaque projet du dossier le reçoit aussitôt."""
    conn = db.connect(etat.chemin_comptes)
    try:
        reference.apres_reglage_commun(conn, etat.registre, code_ref)
    finally:
        conn.close()


def create_app(
    dossier_data: Path | None = None,
    dossier_echange: Path | None = None,
    *,
    mode_local: bool | None = None,
    chemin_comptes: Path | None = None,
    code_projet: str | None = None,
    chemin_ancienne_base: Path | None = None,
) -> FastAPI:
    """Construit l'application.

    Les tests passent un dossier de données, un dossier d'échange et une base commune
    temporaires. Sans mode local explicite, la connexion est exigée.
    """
    _configure_logging()
    data = dossier_data or config.DOSSIER_DATA
    echange = dossier_echange or config.DOSSIER_ECHANGE
    local = config.MODE_LOCAL if mode_local is None else mode_local
    projet = code_projet or config.CODE_PROJET
    if not code_valide(projet):
        raise ValueError(
            f"NOMENTRACE_PROJET doit contenir des minuscules, des chiffres et des tirets"
            f" (lu : « {projet} »)."
        )
    # Un dossier de données explicite (tests) porte aussi sa base commune et son ancienne base.
    if chemin_ancienne_base is None:
        chemin_ancienne_base = (
            data / projets.NOM_BASE if dossier_data else config.CHEMIN_ANCIENNE_BASE
        )
    if chemin_comptes is None:
        chemin_comptes = data / "comptes.db" if dossier_data else config.CHEMIN_COMPTES

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        _preparer_projets(application.state, chemin_ancienne_base)
        if local:
            journal_log.warning(
                "Mode local : aucune connexion demandée, requêtes acceptées depuis ce poste seul."
            )
        for export in application.state.exports.values():
            export.start()
            export.signaler()
        yield
        for export in application.state.exports.values():
            export.stop()

    # La documentation interactive de l'API n'est publiée qu'en mode local.
    documentation = {} if local else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Nomentrace", lifespan=lifespan, **documentation)
    app.state.dossier_data = data
    app.state.dossier_echange = echange
    app.state.mode_local = local
    app.state.chemin_comptes = chemin_comptes
    app.state.code_projet = projet
    app.state.registre = projets.Registre()
    app.state.exports = {}
    app.state.limiteurs = authentification.Limiteurs()
    _install_error_handlers(app)

    @app.middleware("http")
    async def _signaler_modification(
        request: Request, suite: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Toute écriture réussie sur l'API programme l'export Excel de son projet."""
        reponse = await suite(request)
        if not request.url.path.startswith("/api/"):
            # Fichiers de l'interface revalidés à chaque chargement : après une mise à jour,
            # le navigateur ne doit pas garder d'anciens modules JavaScript en cache.
            reponse.headers["Cache-Control"] = "no-cache"
        projet = getattr(request.state, "projet", None)
        if (
            projet in app.state.registre.references
            and request.method in METHODES_ECRITURE
            and request.url.path.startswith("/api/")
            and reponse.status_code < 400
        ):
            await run_in_threadpool(_propager_reglage_commun, app.state, projet)
        export = app.state.exports.get(projet)
        if (
            export is not None
            and request.method in METHODES_ECRITURE
            and request.url.path.startswith("/api/")
            and not request.url.path.startswith(SANS_EXPORT)
            and reponse.status_code < 400
        ):
            export.signaler()
        return reponse

    for routeur in ROUTEURS_COMMUNS:
        app.include_router(routeur, dependencies=[Depends(verifier_acces_commun)])
    for routeur in ROUTEURS_PROJET:
        app.include_router(routeur, dependencies=[Depends(verifier_acces)])
    # Installé en dernier, donc exécuté en premier : les refus d'origine passent avant tout.
    install_securite(app, local)
    # Plus extérieur encore : le préfixe /p/<code> est retiré avant toute autre couche.
    app.add_middleware(AiguillageProjet, registre=app.state.registre, defaut=projet)
    app.mount("/", StaticFiles(directory=config.DOSSIER_STATIC, html=True), name="static")
    return app


app = create_app()
