"""Point d'entrée de l'application Nomentrace."""

import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import config, db
from backend.erreurs import ErreurMetier
from backend.routes import (
    blocs,
    commandes,
    composants,
    documents,
    ensembles,
    fournisseurs,
    imports,
    listes,
    pilotage,
    sante,
)
from backend.routes import (
    sauvegardes as routes_sauvegardes,
)
from backend.services import import_initial, sauvegardes
from backend.services.export_excel import PlanificateurExport

journal_log = logging.getLogger("nomentrace")

METHODES_ECRITURE: frozenset[str] = frozenset({"POST", "PATCH", "PUT", "DELETE"})


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
    return "Données invalides — " + " ; ".join(details)


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


def _prepare_base(base: Path, fichier_import: Path | None, dossier_sauvegardes: Path) -> None:
    """Sauvegarde, migrations puis import initial éventuel, au démarrage."""
    sauvegardes.create_sauvegarde(base, dossier_sauvegardes)
    conn = db.connect(base)
    try:
        version = db.apply_migrations(conn)
        journal_log.info("Base %s prête, schéma version %d", base, version)
        if fichier_import is not None:
            import_initial.run_import_initial(conn, fichier_import)
    finally:
        conn.close()


def create_app(
    chemin_base: Path | None = None,
    fichier_import: Path | None = config.FICHIER_IMPORT_INITIAL,
    dossier_echange: Path | None = None,
) -> FastAPI:
    """Construit l'application.

    Les tests passent une base et un dossier d'échange temporaires ; `fichier_import` à
    None désactive l'import initial.
    """
    _configure_logging()
    base = chemin_base or config.CHEMIN_BASE
    echange = dossier_echange or config.DOSSIER_ECHANGE
    export = PlanificateurExport(base, echange / "exports")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        _prepare_base(base, fichier_import, echange / "sauvegardes")
        export.start()
        export.signaler()
        yield
        export.stop()

    app = FastAPI(title="Nomentrace", lifespan=lifespan)
    app.state.chemin_base = base
    app.state.export = export
    app.state.dossier_documents = echange / "documents"
    app.state.dossier_echange = echange
    _install_error_handlers(app)

    @app.middleware("http")
    async def _signaler_modification(
        request: Request, suite: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Toute écriture réussie sur l'API programme un export Excel."""
        reponse = await suite(request)
        if not request.url.path.startswith("/api/"):
            # Fichiers de l'interface revalidés à chaque chargement : après une mise à jour,
            # le navigateur ne doit pas garder d'anciens modules JavaScript en cache.
            reponse.headers["Cache-Control"] = "no-cache"
        if (
            request.method in METHODES_ECRITURE
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/export"
            and reponse.status_code < 400
        ):
            export.signaler()
        return reponse

    modules = (
        sante,
        pilotage,
        blocs,
        ensembles,
        fournisseurs,
        composants,
        commandes,
        listes,
        documents,
        imports,
        routes_sauvegardes,
    )
    for module in modules:
        app.include_router(module.router)
    app.mount("/", StaticFiles(directory=config.DOSSIER_STATIC, html=True), name="static")
    return app


app = create_app()
