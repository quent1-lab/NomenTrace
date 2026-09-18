"""Fournisseurs. Le nom est la clé ; un renommage se propage par ON UPDATE CASCADE."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, Introuvable
from backend.services import journal

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {
        "nom",
        "type",
        "base_prix_defaut",
        "pays",
        "site_web",
        "compte_ecole",
        "delai_moyen_j",
        "commentaire",
    }
)


def list_fournisseurs(conn: sqlite3.Connection) -> list[dict]:
    """Renvoie les fournisseurs non archivés, triés par nom."""
    return db.fetch_all(
        conn, "SELECT * FROM fournisseur WHERE archive = 0 ORDER BY nom COLLATE NOCASE"
    )


def get_fournisseur(conn: sqlite3.Connection, nom: str) -> dict:
    """Renvoie un fournisseur."""
    fournisseur = db.fetch_one(conn, "SELECT * FROM fournisseur WHERE nom = ?", (nom,))
    if fournisseur is None:
        raise Introuvable(f"Fournisseur « {nom} » introuvable.")
    return fournisseur


def create_fournisseur(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un fournisseur ; refuse un nom déjà pris."""
    with db.transaction(conn):
        if db.fetch_one(conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (valeurs["nom"],)):
            raise Conflit(f"Le fournisseur « {valeurs['nom']} » existe déjà.")
        db.insert_row(conn, "fournisseur", valeurs)
        journal.write_journal(conn, "fournisseur", valeurs["nom"], "creation", None, "créé")
    return get_fournisseur(conn, valeurs["nom"])


def patch_fournisseur(conn: sqlite3.Connection, nom: str, modifications: dict[str, Any]) -> dict:
    """Modifie un fournisseur, y compris son nom."""
    nouveau_nom = modifications.get("nom", nom)
    with db.transaction(conn):
        if nouveau_nom != nom and db.fetch_one(
            conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (nouveau_nom,)
        ):
            raise Conflit(f"Le fournisseur « {nouveau_nom} » existe déjà.")
        journal.update_with_journal(conn, "fournisseur", nom, modifications, CHAMPS_MODIFIABLES)
    return get_fournisseur(conn, nouveau_nom)


def ensure_fournisseur(conn: sqlite3.Connection, nom: str | None) -> None:
    """Vérifie qu'un fournisseur désigné existe et n'est pas archivé."""
    if nom is None:
        return
    ligne = db.fetch_one(conn, "SELECT archive FROM fournisseur WHERE nom = ?", (nom,))
    if ligne is None or ligne["archive"]:
        raise Introuvable(f"Fournisseur « {nom} » introuvable.")
