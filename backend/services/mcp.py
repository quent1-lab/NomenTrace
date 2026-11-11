"""Protocole MCP (Model Context Protocol), réduit à ce qu'un assistant IA utilise.

Transport HTTP « streamable » sans flux : chaque message JSON-RPC arrive par un POST et sa
réponse repart en JSON. Méthodes servies : initialize, ping, tools/list, tools/call ; une
notification reçoit 202 sans corps.

Un outil appelle sa route dans le processus (`appeler_route`) : la requête traverse toutes
les couches de l'application (aiguillage, origine, droits, export), avec l'identité du
compte posée dans la portée ASGI sous `CLE_PORTEE`, qu'aucune requête venue du réseau ne
peut porter.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import FastAPI

from backend.services import mcp_outils

journal_log = logging.getLogger(__name__)

CLE_PORTEE = "nomentrace.mcp"
VERSIONS: tuple[str, ...] = ("2025-11-25", "2025-06-18", "2025-03-26")
CONSIGNES = (
    "Nomentrace suit la nomenclature, les achats et le montage d'un projet. Un composant porte"
    " un identifiant stable ; il appartient à un seul bloc (découpage de suivi) et peut être"
    " affecté à plusieurs ensembles (découpage physique) avec une quantité. Montants en euros"
    " HT, dates AAAA-MM-JJ. Lire list_listes avant d'écrire une valeur de liste : seuls les"
    " codes actifs sont acceptés. Toute écriture est journalisée au nom du compte, suivi de"
    " « (IA) »."
)

# Codes d'erreur JSON-RPC.
REQUETE_INVALIDE = -32600
METHODE_INCONNUE = -32601
PARAMETRES_INVALIDES = -32602


@dataclass(frozen=True)
class Contexte:
    """Ce qu'il faut pour appeler une route au nom du compte."""

    app: FastAPI
    projet: str
    schema: str
    hote: str
    client: tuple[str, int] | None
    utilisateur_id: int | None


class ErreurProtocole(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- Appel d'une route dans le processus -----------------------------------------------------


async def appeler_route(
    ctx: Contexte, methode: str, chemin: str, requete: dict[str, Any], corps: dict | None
) -> tuple[int, Any]:
    """Appelle une route de l'API du projet ; rend le statut et le corps JSON décodé."""
    donnees = b"" if corps is None else json.dumps(corps).encode()
    entetes = [
        (b"host", ctx.hote.encode("latin-1")),
        (b"origin", f"{ctx.schema}://{ctx.hote}".encode("latin-1")),
        (b"accept", b"application/json"),
    ]
    if corps is not None:
        entetes += [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(donnees)).encode()),
        ]
    adresse = f"/p/{ctx.projet}{chemin}"
    portee = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": methode,
        "scheme": ctx.schema,
        "path": adresse,
        "raw_path": adresse.encode(),
        "root_path": "",
        "query_string": urlencode(
            {k: v for k, v in requete.items() if v is not None}, doseq=True
        ).encode(),
        "headers": entetes,
        "client": ctx.client,
        "server": None,
        CLE_PORTEE: {"utilisateur_id": ctx.utilisateur_id},
    }
    envoye = False
    fini = asyncio.Event()
    statut = 500
    morceaux: list[bytes] = []

    async def recevoir() -> dict:
        nonlocal envoye
        if not envoye:
            envoye = True
            return {"type": "http.request", "body": donnees, "more_body": False}
        await fini.wait()
        return {"type": "http.disconnect"}

    async def emettre(message: dict) -> None:
        nonlocal statut
        if message["type"] == "http.response.start":
            statut = message["status"]
        elif message["type"] == "http.response.body":
            morceaux.append(message.get("body", b""))
            if not message.get("more_body"):
                fini.set()

    await ctx.app(portee, recevoir, emettre)
    fini.set()
    brut = b"".join(morceaux)
    try:
        return statut, json.loads(brut) if brut else None
    except json.JSONDecodeError:
        return statut, brut.decode("utf-8", errors="replace")


# --- Méthodes du protocole -------------------------------------------------------------------


def _initialiser(ctx: Contexte, params: dict) -> dict:
    demandee = params.get("protocolVersion")
    return {
        "protocolVersion": demandee if demandee in VERSIONS else VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": "nomentrace",
            "title": "Nomentrace",
            "version": str(ctx.app.version),
        },
        "instructions": CONSIGNES,
    }


def _lister_outils(ctx: Contexte) -> dict:
    schemas = mcp_outils.schemas(ctx.app)
    return {
        "tools": [
            {
                "name": outil.nom,
                "description": outil.description,
                "inputSchema": schemas[outil.nom].entree,
                "annotations": {
                    "readOnlyHint": outil.lecture,
                    "destructiveHint": False,
                    "idempotentHint": outil.lecture or outil.methode in ("PUT", "PATCH"),
                    "openWorldHint": False,
                },
            }
            for outil in mcp_outils.OUTILS
        ]
    }


def _chemin(outil: mcp_outils.Outil, arguments: dict) -> str:
    """Remplit les paramètres du chemin, échappés (un nom de fournisseur peut contenir « / »)."""
    chemin = mcp_outils.chemin_openapi(outil.chemin)
    for nom, valeur in arguments.items():
        chemin = chemin.replace(f"{{{nom}}}", quote(str(valeur), safe=""))
    return chemin


async def _appeler_outil(ctx: Contexte, params: dict) -> dict:
    outil = mcp_outils.PAR_NOM.get(params.get("name", ""))
    if outil is None:
        raise ErreurProtocole(PARAMETRES_INVALIDES, f"Outil inconnu : {params.get('name')}.")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ErreurProtocole(PARAMETRES_INVALIDES, "Les arguments doivent être un objet.")
    schema = mcp_outils.schemas(ctx.app)[outil.nom]
    inconnus = set(arguments) - set(schema.entree["properties"])
    if inconnus:
        return _resultat_erreur(f"Arguments non acceptés : {', '.join(sorted(inconnus))}.")
    manquants = [argument for argument, _ in schema.chemin if argument not in arguments]
    if manquants:
        return _resultat_erreur(f"Arguments obligatoires manquants : {', '.join(manquants)}.")
    chemin = _chemin(outil, {param: arguments[argument] for argument, param in schema.chemin})
    requete = {nom: arguments[nom] for nom in schema.requete if nom in arguments}
    corps = None
    if outil.methode != "GET":
        corps = {nom: arguments[nom] for nom in schema.corps if nom in arguments}
    statut, reponse = await appeler_route(ctx, outil.methode, chemin, requete, corps)
    if statut >= 400:
        message = reponse.get("erreur") if isinstance(reponse, dict) else None
        return _resultat_erreur(message or f"Erreur {statut}.")
    texte = json.dumps(reponse, ensure_ascii=False)
    resultat: dict[str, Any] = {"content": [{"type": "text", "text": texte}], "isError": False}
    if isinstance(reponse, dict):
        resultat["structuredContent"] = reponse
    return resultat


def _resultat_erreur(message: str) -> dict:
    """Erreur métier : rendue à l'assistant comme un résultat, pour qu'il corrige son appel."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


async def traiter(ctx: Contexte, message: Any) -> dict | None:
    """Traite un message JSON-RPC ; None pour une notification (pas de réponse)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _erreur(None, REQUETE_INVALIDE, "Message JSON-RPC 2.0 attendu.")
    methode = message.get("method")
    if "id" not in message:
        return None
    identifiant = message["id"]
    params = message.get("params") or {}
    try:
        match methode:
            case "initialize":
                resultat = _initialiser(ctx, params)
            case "ping":
                resultat = {}
            case "tools/list":
                resultat = _lister_outils(ctx)
            case "tools/call":
                resultat = await _appeler_outil(ctx, params)
                journal_log.info(
                    "MCP %s : outil %s (%s).",
                    ctx.projet,
                    params.get("name"),
                    "erreur" if resultat.get("isError") else "fait",
                )
            case _:
                raise ErreurProtocole(METHODE_INCONNUE, f"Méthode inconnue : {methode}.")
    except ErreurProtocole as erreur:
        return _erreur(identifiant, erreur.code, erreur.message)
    return {"jsonrpc": "2.0", "id": identifiant, "result": resultat}


def erreur_lecture() -> dict:
    return _erreur(None, -32700, "Corps illisible : JSON attendu.")


def _erreur(identifiant: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": identifiant, "error": {"code": code, "message": message}}
