"""Aiguillage des adresses : le projet de la requête est lu dans le chemin /p/<code>/….

Installé à l'extérieur de toutes les autres couches, l'aiguillage retire le préfixe avant
elles : contrôle d'origine, droits (table REGLES), export programmé et routes voient les
adresses habituelles en /api/, et le projet est posé dans `request.state.projet`.

Un code mal formé ou inconnu est refusé ici, sans qu'aucune base soit ouverte : le code
d'adresse n'est jamais un chemin de fichier. Une adresse sans préfixe porte le projet de
l'instance, ce qui garde valables les onglets ouverts et le contrôle de santé.
"""

import json
import re

from starlette.types import ASGIApp, Receive, Scope, Send

# Code d'adresse : minuscules, chiffres et tirets, figé à la création du projet.
MOTIF_CODE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")

PREFIXE = "/p/"


def code_valide(code: str) -> bool:
    """Le code respecte le motif d'adresse (aucun point, aucune barre, aucune majuscule)."""
    return MOTIF_CODE.fullmatch(code) is not None


class AiguillageProjet:
    """Middleware ASGI : retire /p/<code> du chemin et pose le projet de la requête."""

    def __init__(self, app: ASGIApp, projets: frozenset[str], defaut: str) -> None:
        self.app = app
        self.projets = projets
        self.defaut = defaut

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chemin: str = scope["path"]
        if chemin in ("/", "/index.html"):
            await _redirection(send, f"{PREFIXE}{self.defaut}/")
            return
        if chemin != "/p" and not chemin.startswith(PREFIXE):
            await self.app(_avec_projet(scope, chemin, self.defaut), receive, send)
            return
        code, barre, reste = chemin[len(PREFIXE) :].partition("/")
        if not code_valide(code) or code not in self.projets:
            await _introuvable(send)
            return
        if not barre:
            await _redirection(send, f"{PREFIXE}{code}/")
            return
        await self.app(_avec_projet(scope, "/" + reste, code), receive, send)


def _avec_projet(scope: Scope, chemin: str, code: str) -> Scope:
    """Copie de la portée avec le chemin sans préfixe et le projet dans l'état de la requête."""
    nouvelle = dict(scope)
    if chemin != scope["path"]:
        nouvelle["path"] = chemin
        prefixe = f"{PREFIXE}{code}".encode()
        brut: bytes = scope.get("raw_path") or b""
        nouvelle["raw_path"] = brut[len(prefixe) :] if brut.startswith(prefixe) else chemin.encode()
    etat = dict(scope.get("state") or {})
    etat["projet"] = code
    nouvelle["state"] = etat
    return nouvelle


async def _redirection(send: Send, adresse: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [(b"location", adresse.encode()), (b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def _introuvable(send: Send) -> None:
    corps = json.dumps({"erreur": "Projet introuvable."}, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(corps)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corps})
