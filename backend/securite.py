"""Protections HTTP communes à toutes les réponses.

- Toute écriture sur l'API doit venir d'une page de Nomentrace : l'en-tête Origin, que les
  navigateurs envoient avec chaque requête d'écriture, doit désigner le serveur lui-même,
  schéma compris. Un site tiers ne peut donc pas faire écrire le navigateur d'un
  utilisateur connecté.
- En mode local, seules les requêtes venues de la machine elle-même et adressées à
  127.0.0.1 ou localhost sont servies : un autre poste du réseau ne peut pas s'en servir,
  et une page piégée ne peut pas l'atteindre par un nom de domaine détourné vers 127.0.0.1.
- Les en-têtes de sécurité interdisent l'exécution de script étranger, l'affichage dans un
  cadre d'un autre site et l'interprétation d'un fichier dans un autre type que le sien.
"""

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from backend import config

journal_log = logging.getLogger(__name__)

METHODES_ECRITURE: frozenset[str] = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Scripts et styles servis par Nomentrace seulement ; ni script en ligne ni lien javascript:.
POLITIQUE_CONTENU = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

EN_TETES: dict[str, str] = {
    "Content-Security-Policy": POLITIQUE_CONTENU,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _hote(valeur: str) -> str:
    """Nom d'hôte sans le port ni les crochets d'une adresse IPv6."""
    return (urlsplit(f"//{valeur}").hostname or "").lower()


def origine_admise(request: Request) -> bool:
    """L'origine de la requête désigne le serveur lui-même (schéma, hôte et port).

    Derrière le proxy, le schéma est celui que le visiteur a employé (X-Forwarded-Proto,
    cru seulement du proxy local) : une page servie en http n'écrit pas sur l'instance https.
    """
    origine = request.headers.get("origin")
    hote = request.headers.get("host")
    if not origine or not hote or origine == "null":
        return False
    parties = urlsplit(origine)
    return parties.scheme == request.url.scheme and parties.netloc.lower() == hote.lower()


def requete_locale(request: Request) -> bool:
    """Requête émise depuis la machine et adressée à la boucle locale."""
    client = request.client.host if request.client else ""
    hote = _hote(request.headers.get("host", ""))
    return client in config.HOTES_LOCAUX and hote in config.HOTES_LOCAUX


def _refus(message: str, statut: int) -> JSONResponse:
    return JSONResponse({"erreur": message}, status_code=statut)


def install_securite(app: FastAPI, mode_local: bool) -> None:
    """Installe le contrôle d'origine, la restriction du mode local et les en-têtes."""

    @app.middleware("http")
    async def _securite(
        request: Request, suite: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        api = request.url.path.startswith("/api/")
        if mode_local and not requete_locale(request):
            journal_log.warning(
                "Mode local : requête refusée de %s pour l'hôte %s.",
                request.client.host if request.client else "?",
                request.headers.get("host"),
            )
            reponse = _refus(
                "Nomentrace est lancé en mode local : il n'accepte que les requêtes de ce poste,"
                " adressées à 127.0.0.1 ou localhost.",
                403,
            )
        elif api and request.method in METHODES_ECRITURE and not origine_admise(request):
            journal_log.warning(
                "Écriture refusée : origine « %s » pour l'hôte « %s » (%s %s).",
                request.headers.get("origin"),
                request.headers.get("host"),
                request.method,
                request.url.path,
            )
            reponse = _refus("Requête refusée : elle ne vient pas d'une page de Nomentrace.", 403)
        else:
            reponse = await suite(request)
        for nom, valeur in EN_TETES.items():
            reponse.headers.setdefault(nom, valeur)
        if api:
            # Données du projet : jamais gardées dans un cache, ni sur un poste partagé.
            reponse.headers["Cache-Control"] = "no-store"
        if request.url.scheme == "https":
            reponse.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return reponse
