"""Accès d'un assistant IA par le protocole MCP : ouverture, jetons, outils, limites.

Projet fictif du jeu d'essai, en mode connecté (tests/test_comptes.py) ; un test en mode
local à la fin.
"""

import asyncio
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from backend.services import droits, mcp, mcp_outils
from tests.conftest import client_local
from tests.test_comptes import (  # noqa: F401  # noqa: F401
    ADRESSE,
    PROJET,
    admin,
    app,
    chemin_comptes,
    code_projet,
    connecter,
    creer_compte,
    lecteur,
    scrypt_rapide,
)

MCP = f"/p/{PROJET}/api/mcp"
COMPOSANT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant posé par l'assistant",
    "mode_appro": "Achat",
    "qte_besoin": 2,
}


def ouvrir(client: TestClient, acces: str) -> None:
    reponse = client.patch(f"/p/{PROJET}/api/mcp/reglage", json={"acces": acces})
    assert reponse.status_code == 200, reponse.text


def jeton(client: TestClient, nom: str = "Portable") -> str:
    reponse = client.post(f"/p/{PROJET}/api/mcp/jetons", json={"nom": nom})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["jeton"]


def assistant(app: FastAPI, cle: str) -> TestClient:  # noqa: F811
    """Client MCP hors navigateur : ni cookie, ni Origin, le jeton dans l'en-tête."""
    return TestClient(app, base_url=ADRESSE, headers={"Authorization": f"Bearer {cle}"})


def rpc(client: TestClient, methode: str, params: dict | None = None, ident: int = 1) -> dict:
    corps = {"jsonrpc": "2.0", "id": ident, "method": methode, "params": params or {}}
    reponse = client.post(MCP, json=corps)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def outil(client: TestClient, nom: str, arguments: dict) -> dict:
    return rpc(client, "tools/call", {"name": nom, "arguments": arguments})["result"]


def lire(app: FastAPI, requete: str, params: tuple = ()) -> list[tuple]:  # noqa: F811
    conn = db.connect(app.state.registre.projets[PROJET].base, creer=False)
    try:
        return [tuple(ligne) for ligne in conn.execute(requete, params).fetchall()]
    finally:
        conn.close()


# --- Ouverture et jetons -------------------------------------------------------------------------


def test_ferme_par_defaut(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    assert admin.get(f"/p/{PROJET}/api/mcp/reglage").json()["acces"] == "ferme"
    assert admin.post(f"/p/{PROJET}/api/mcp/jetons", json={"nom": "x"}).status_code == 403
    sans_jeton = TestClient(app, base_url=ADRESSE)
    reponse = sans_jeton.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert reponse.status_code == 401
    assert reponse.headers["www-authenticate"].startswith("Bearer")


def test_ouvert_aux_administrateurs_seuls(
    app: FastAPI,  # noqa: F811
    admin: TestClient,  # noqa: F811
    lecteur: TestClient,  # noqa: F811
) -> None:
    ouvrir(admin, "admin")
    assert lecteur.post(f"/p/{PROJET}/api/mcp/jetons", json={"nom": "x"}).status_code == 403
    assert (
        lecteur.patch(f"/p/{PROJET}/api/mcp/reglage", json={"acces": "membres"}).status_code == 403
    )
    cle = jeton(admin)
    assert cle.startswith("nt_")
    assert rpc(assistant(app, cle), "ping")["result"] == {}


def test_jeton_garde_en_empreinte_seulement(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    cle = jeton(admin)
    conn = sqlite3.connect(app.state.chemin_comptes)
    try:
        assert cle not in str(conn.execute("SELECT * FROM jeton_api").fetchall())
    finally:
        conn.close()
    assert "jeton" not in admin.get(f"/p/{PROJET}/api/mcp/reglage").json()["jetons"][0]


def test_revocation_et_fermeture(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    premier, second = jeton(admin, "Un"), jeton(admin, "Deux")
    ident = admin.get(f"/p/{PROJET}/api/mcp/reglage").json()["jetons"][0]["id"]
    assert admin.delete(f"/p/{PROJET}/api/mcp/jetons/{ident}").status_code == 204
    assert (
        assistant(app, second)
        .post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        .status_code
        == 401
    )
    assert rpc(assistant(app, premier), "ping")["result"] == {}
    # Fermer révoque tout : rouvrir ne rend pas vie aux anciens jetons.
    ouvrir(admin, "ferme")
    ouvrir(admin, "admin")
    reponse = assistant(app, premier).post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert reponse.status_code == 401


def test_jeton_n_ouvre_pas_l_api(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    """Le jeton n'est lu que par la route MCP : l'API REST reste fermée sans session."""
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    assert client.get(f"/p/{PROJET}/api/composants").status_code == 401
    entetes = {"Origin": ADRESSE}
    assert (
        client.post(f"/p/{PROJET}/api/composants", json=COMPOSANT, headers=entetes).status_code
        == 401
    )


def test_origine_etrangere_refusee(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    reponse = client.post(
        MCP,
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Origin": "https://piege.example"},
    )
    assert reponse.status_code == 403


# --- Protocole et outils -------------------------------------------------------------------------


def test_initialisation_et_liste_des_outils(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    init = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in init["result"]["capabilities"]
    notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert client.post(MCP, json=notification).status_code == 202
    outils = {o["name"]: o for o in rpc(client, "tools/list")["result"]["tools"]}
    assert set(outils) == set(mcp_outils.PAR_NOM)
    assert outils["list_composants"]["annotations"]["readOnlyHint"] is True
    assert outils["create_composant"]["annotations"]["readOnlyHint"] is False
    assert {"bloc_code", "designation"} <= set(
        outils["create_composant"]["inputSchema"]["required"]
    )
    proprietes = outils["update_ensemble"]["inputSchema"]["properties"]
    assert "code" in proprietes and "budget_cible_ht" not in proprietes


def test_lecture_et_ecriture_journalisee(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    liste = outil(client, "list_composants", {"bloc": "ALI"})
    assert liste["isError"] is False and "ALI" in liste["content"][0]["text"]
    cree = outil(client, "create_composant", COMPOSANT)
    assert cree["isError"] is False, cree
    identifiant = cree["structuredContent"]["id"]
    fiche = outil(client, "get_composant", {"identifiant": identifiant})
    assert fiche["structuredContent"]["composant"]["designation"] == COMPOSANT["designation"]
    auteurs = lire(
        app, "SELECT DISTINCT utilisateur FROM journal WHERE cle_cible = ?", (identifiant,)
    )
    assert auteurs == [("admin (IA)",)]


def test_erreur_metier_rendue_a_l_assistant(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    resultat = outil(client, "create_composant", {**COMPOSANT, "qte_besoin": -1})
    assert resultat["isError"] is True and resultat["content"][0]["text"]
    resultat = outil(client, "get_composant", {"identifiant": "INCONNU-001"})
    assert resultat["isError"] is True


def test_budgets_refuses(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "admin")
    client = assistant(app, jeton(admin))
    code = "MCP-1"
    assert outil(client, "create_ensemble", {"code": code, "nom": "Châssis"})["isError"] is False
    avant = lire(app, "SELECT budget_cible_ht FROM ensemble WHERE code = ?", (code,))
    resultat = outil(client, "update_ensemble", {"code": code, "budget_cible_ht": 999})
    assert resultat["isError"] is True and "budget_cible_ht" in resultat["content"][0]["text"]
    assert lire(app, "SELECT budget_cible_ht FROM ensemble WHERE code = ?", (code,)) == avant


def test_droits_du_compte(app: FastAPI, admin: TestClient, lecteur: TestClient) -> None:  # noqa: F811
    ouvrir(admin, "membres")
    client = assistant(app, jeton(lecteur))
    assert outil(client, "list_composants", {})["isError"] is False
    resultat = outil(client, "create_composant", COMPOSANT)
    assert resultat["isError"] is True
    assert lire(
        app, "SELECT COUNT(*) FROM composant WHERE designation = ?", (COMPOSANT["designation"],)
    ) == [(0,)]


def test_route_hors_liste_refusee_meme_marquee(app: FastAPI, admin: TestClient) -> None:  # noqa: F811
    """Défense en profondeur : une requête marquée MCP ne sort pas de la liste des outils."""
    conn = sqlite3.connect(app.state.chemin_comptes)
    try:
        ident = conn.execute("SELECT id FROM utilisateur WHERE nom = 'admin'").fetchone()[0]
    finally:
        conn.close()
    identifiant = lire(app, "SELECT id FROM composant LIMIT 1")[0][0]
    ctx = mcp.Contexte(app, PROJET, "https", "nomentrace.test", ("127.0.0.1", 1), ident)
    statut, _ = asyncio.run(
        mcp.appeler_route(ctx, "DELETE", f"/api/composants/{identifiant}", {}, None)
    )
    assert statut == 403
    statut, _ = asyncio.run(mcp.appeler_route(ctx, "GET", "/api/utilisateurs", {}, None))
    assert statut == 403
    assert lire(app, "SELECT COUNT(*) FROM composant WHERE id = ?", (identifiant,)) == [(1,)]


def test_outils_sans_suppression_ni_administration() -> None:
    for o in mcp_outils.OUTILS:
        assert o.methode != "DELETE", o.nom
        regle = droits.REGLES[(o.methode, o.chemin)]
        assert regle.niveau != "admin", o.nom


# --- Mode local ----------------------------------------------------------------------------------


def test_mode_local_sans_jeton_mais_ouverture_exigee(
    conn_essai: sqlite3.Connection, dossier_data: Path, dossier_echange: Path
) -> None:
    conn_essai.close()
    application = create_app(dossier_data, dossier_echange=dossier_echange, mode_local=True)
    with client_local(application) as client:
        projet = next(iter(application.state.registre.projets))
        corps = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_pilotage", "arguments": {}},
        }
        assert client.post(f"/p/{projet}/api/mcp", json=corps).status_code == 403
        client.patch(f"/p/{projet}/api/mcp/reglage", json={"acces": "admin"})
        reponse = client.post(f"/p/{projet}/api/mcp", json=corps)
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["result"]["isError"] is False
