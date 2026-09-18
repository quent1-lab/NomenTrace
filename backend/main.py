"""Point d'entrée de l'application Nomentrace."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import config, db
from backend.routes import sante

journal_log = logging.getLogger("nomentrace")


def _configure_logging() -> None:
    """Configure la journalisation au niveau INFO, avec horodatage."""
    logging.basicConfig(level=logging.INFO, format=config.FORMAT_LOG)


def _install_error_handlers(app: FastAPI) -> None:
    """Traduit toutes les erreurs en {"erreur": "..."} sans trace Python."""

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Requête refusée."
        if exc.status_code == 404 and message == "Not Found":
            message = "Ressource introuvable."
        return JSONResponse({"erreur": message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for erreur in exc.errors():
            champ = ".".join(str(p) for p in erreur.get("loc", ()) if p != "body")
            details.append(f"{champ} : {erreur.get('msg', 'valeur invalide')}")
        message = "Données invalides — " + " ; ".join(details)
        return JSONResponse({"erreur": message}, status_code=422)

    @app.exception_handler(Exception)
    async def _inattendue(_: Request, exc: Exception) -> JSONResponse:
        journal_log.exception("Erreur inattendue : %s", exc)
        return JSONResponse(
            {"erreur": "Erreur interne du serveur, consulter le journal."}, status_code=500
        )


def create_app(chemin_base: Path | None = None) -> FastAPI:
    """Construit l'application ; `chemin_base` permet aux tests d'utiliser une base temporaire."""
    _configure_logging()
    base = chemin_base or config.CHEMIN_BASE

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = db.connect(base)
        try:
            version = db.apply_migrations(conn)
            journal_log.info("Base %s prête, schéma version %d", base, version)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Nomentrace", lifespan=lifespan)
    app.state.chemin_base = base
    _install_error_handlers(app)
    app.include_router(sante.router)
    app.mount("/", StaticFiles(directory=config.DOSSIER_STATIC, html=True), name="static")
    return app


app = create_app()
