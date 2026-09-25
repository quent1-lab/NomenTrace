"""Journal des modifications et mise à jour journalisée champ par champ."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Introuvable

ORIGINE_INTERFACE = "interface"
ORIGINE_IMPORT = "import"

# Clé primaire de chaque table modifiable. Les noms de table et de colonne ne viennent
# jamais de l'utilisateur : ils sont validés contre ces listes blanches.
CLES_PRIMAIRES: dict[str, str] = {
    "bloc": "code",
    "ensemble": "code",
    "fournisseur": "nom",
    "composant": "id",
    "affectation": "id",
    "commande": "numero",
    "ligne_commande": "id",
    "parametre": "cle",
    "document": "id",
    "attribut": "code",
}


def _texte(valeur: Any) -> str | None:
    return None if valeur is None else str(valeur)


def write_journal(
    conn: sqlite3.Connection,
    table: str,
    cle: Any,
    champ: str | None,
    ancienne: Any,
    nouvelle: Any,
    origine: str = ORIGINE_INTERFACE,
    lot_id: int | None = None,
) -> None:
    """Écrit une ligne de journal ; `lot_id` relie une modification au fichier importé.

    L'auteur est celui de la connexion, posé par l'application à chaque requête.
    """
    conn.execute(
        "INSERT INTO journal (table_cible, cle_cible, champ, ancienne_valeur, nouvelle_valeur,"
        " origine, lot_id, utilisateur) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            table,
            _texte(cle),
            champ,
            _texte(ancienne),
            _texte(nouvelle),
            origine,
            lot_id,
            db.auteur(conn),
        ),
    )


def differe(ancienne: Any, nouvelle: Any) -> bool:
    """Compare deux valeurs ; les nombres au millionième près, pour ignorer le bruit flottant."""
    if isinstance(ancienne, int | float) and isinstance(nouvelle, int | float):
        return abs(float(ancienne) - float(nouvelle)) > 1e-6
    return ancienne != nouvelle


def update_with_journal(
    conn: sqlite3.Connection,
    table: str,
    cle: Any,
    modifications: dict[str, Any],
    colonnes_autorisees: frozenset[str],
    origine: str = ORIGINE_INTERFACE,
    cle_journal: str | None = None,
    lot_id: int | None = None,
) -> dict[str, Any]:
    """Applique les champs qui changent réellement et journalise chacun d'eux.

    Doit être appelée dans une transaction. `cle_journal` remplace la clé primaire dans le
    journal quand elle n'est pas parlante (affectation). Renvoie les champs modifiés.
    """
    col_cle = CLES_PRIMAIRES[table]
    actuel = db.fetch_one(conn, f"SELECT * FROM {table} WHERE {col_cle} = ?", (cle,))  # noqa: S608
    if actuel is None:
        raise Introuvable(f"{table} « {cle} » introuvable.")
    changes = {}
    for champ, valeur in modifications.items():
        if champ not in colonnes_autorisees:
            raise ValueError(f"Champ non modifiable : {champ}")
        if differe(actuel[champ], valeur):
            changes[champ] = valeur
    # Un changement de clé (renommage de fournisseur) passe en dernier, sinon les mises à
    # jour suivantes ne retrouveraient plus la ligne.
    for champ, valeur in sorted(changes.items(), key=lambda item: item[0] == col_cle):
        conn.execute(
            f"UPDATE {table} SET {champ} = ? WHERE {col_cle} = ?",  # noqa: S608
            (valeur, cle),
        )
        write_journal(
            conn, table, cle_journal or cle, champ, actuel[champ], valeur, origine, lot_id
        )
    return changes


def list_journal(
    conn: sqlite3.Connection,
    table_cible: str | None = None,
    cle_cible: str | None = None,
    limite: int = 500,
) -> list[dict]:
    """Renvoie les dernières lignes du journal, les plus récentes en premier."""
    return db.fetch_all(
        conn,
        "SELECT * FROM journal WHERE (? IS NULL OR table_cible = ?)"
        " AND (? IS NULL OR cle_cible = ?) ORDER BY id DESC LIMIT ?",
        (table_cible, table_cible, cle_cible, cle_cible, limite),
    )
