"""Frais d'une commande : livraison, douane, frais de facturation… (liste type_frais).

Chaque frais est une ligne typée, en HT. Il compte dans le total de la commande et, une fois
la commande engagée, dans le montant engagé global ; il n'est pas réparti entre les blocs.
"""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Introuvable
from backend.services import commandes, journal, listes

CHAMPS_FRAIS: frozenset[str] = frozenset({"type_frais", "montant_ht", "commentaire"})


def list_frais(conn: sqlite3.Connection, numero: str) -> list[dict]:
    """Frais d'une commande non archivée, avec le libellé de leur type."""
    commandes.get_commande(conn, numero)
    return db.fetch_all(
        conn,
        "SELECT f.*, v.libelle AS type_libelle FROM frais_commande f"
        " LEFT JOIN valeur_liste v ON v.liste = 'type_frais' AND v.code = f.type_frais"
        " WHERE f.commande_numero = ? ORDER BY f.id",
        (numero,),
    )


def get_frais(conn: sqlite3.Connection, identifiant: int) -> dict:
    frais = db.fetch_one(conn, "SELECT * FROM frais_commande WHERE id = ?", (identifiant,))
    if frais is None:
        raise Introuvable(f"Frais n° {identifiant} introuvable.")
    commandes.get_commande(conn, frais["commande_numero"])
    return frais


def _cle(frais: dict) -> str:
    return f"{frais['commande_numero']}:{frais['id']}"


def create_frais(conn: sqlite3.Connection, numero: str, valeurs: dict[str, Any]) -> dict:
    """Ajoute un frais à une commande ; le type doit être une valeur active de la liste."""
    with db.transaction(conn):
        commandes.get_commande(conn, numero)
        listes.check_valeur(conn, "type_frais", valeurs["type_frais"])
        identifiant = db.insert_row(conn, "frais_commande", {"commande_numero": numero, **valeurs})
        cree = get_frais(conn, identifiant)
        journal.write_journal(
            conn, "frais_commande", _cle(cree), "montant_ht", None, cree["montant_ht"]
        )
    return cree


def patch_frais(conn: sqlite3.Connection, identifiant: int, modifications: dict[str, Any]) -> dict:
    with db.transaction(conn):
        frais = get_frais(conn, identifiant)
        if modifications.get("type_frais", frais["type_frais"]) != frais["type_frais"]:
            listes.check_valeur(conn, "type_frais", modifications["type_frais"])
        journal.update_with_journal(
            conn,
            "frais_commande",
            identifiant,
            modifications,
            CHAMPS_FRAIS,
            cle_journal=_cle(frais),
        )
    return get_frais(conn, identifiant)


def delete_frais(conn: sqlite3.Connection, identifiant: int) -> None:
    """Retire un frais ; le journal garde son type et son montant."""
    with db.transaction(conn):
        frais = get_frais(conn, identifiant)
        conn.execute("DELETE FROM frais_commande WHERE id = ?", (identifiant,))
        journal.write_journal(
            conn,
            "frais_commande",
            _cle(frais),
            "montant_ht",
            f"{frais['type_frais']} {frais['montant_ht']}",
            None,
        )
