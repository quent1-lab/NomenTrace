"""Plafond d'un envoi : une requête trop grosse est refusée avant d'être reçue.

Sans cette couche, Starlette lit tout le corps multipart, l'écrit dans un fichier temporaire,
et la route ne refuse qu'ensuite : l'utilisateur attend la fin d'un envoi voué au refus.
Ici, une longueur annoncée au-delà du plafond est refusée dès l'en-tête, sans rien lire ; un
corps sans longueur annoncée est compté pendant la lecture et coupé au plafond.

La taille maximale d'un document, réglée par projet sous ce plafond, est contrôlée par
`services/documents.py` ; l'interface vérifie les deux avant d'envoyer.
"""

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

journal_log = logging.getLogger(__name__)

MO: int = 1024 * 1024


class EnvoiTropGros(Exception):
    """Levée pendant la lecture d'un corps sans longueur annoncée qui dépasse le plafond."""


def message_plafond(plafond: int) -> str:
    """Message d'erreur du plafond, en Mo entiers."""
    return f"Envoi trop volumineux : {plafond // MO} Mo au plus à la fois."


class LimiteEnvoi:
    """Middleware ASGI : refuse en 413 tout corps de requête au-delà de `plafond` octets."""

    def __init__(self, app: ASGIApp, plafond: int) -> None:
        self.app = app
        self.plafond = plafond

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        annoncee = dict(scope["headers"]).get(b"content-length")
        if annoncee is not None and annoncee.isdigit() and int(annoncee) > self.plafond:
            journal_log.info(
                "Envoi refusé avant lecture : %s octets (%s).", annoncee, scope["path"]
            )
            await _refus(send, message_plafond(self.plafond))
            return
        recu = 0
        depasse = commence = False

        async def lire() -> Message:
            nonlocal recu, depasse
            message = await receive()
            recu += len(message.get("body", b""))
            if recu > self.plafond:
                depasse = True
                raise EnvoiTropGros
            return message

        async def envoyer(message: Message) -> None:
            # FastAPI traduit l'interruption de lecture en 400 : la réponse est remplacée.
            nonlocal commence
            if depasse:
                if not commence:
                    commence = True
                    journal_log.info(
                        "Envoi coupé au plafond pendant la lecture (%s).", scope["path"]
                    )
                    await _refus(send, message_plafond(self.plafond))
                return
            commence = commence or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, lire, envoyer)
        except EnvoiTropGros:
            if not commence:
                journal_log.info("Envoi coupé au plafond pendant la lecture (%s).", scope["path"])
                await _refus(send, message_plafond(self.plafond))


async def _refus(send: Send, message: str) -> None:
    corps = json.dumps({"erreur": message}, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(corps)).encode()),
                (b"connection", b"close"),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corps})
