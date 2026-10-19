"""Visa des composants : un responsable signale qu'il a vu un composant tel qu'il est.

Le visa garde la date de modification du composant au moment où il est posé. Il ne vaut plus
dès que cette date change, c'est-à-dire dès qu'un champ ou une caractéristique du composant
est modifié ; affectations, commandes, stock et documents ne la changent pas. Un composant
sans visa valable est « à voir ».
"""

import sqlite3
from datetime import datetime

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import journal

# Fragment de filtre sur v_composant : composants sans visa valable.
CLAUSE_A_VOIR: str = (
    "NOT EXISTS (SELECT 1 FROM visa vi WHERE vi.composant_id = id"
    " AND vi.modifie_le_vise = modifie_le)"
)
LIMITE_LOT: int = 2000


def ids_vises(conn: sqlite3.Connection) -> set[str]:
    """Composants dont le visa vaut encore."""
    lignes = conn.execute(
        "SELECT vi.composant_id FROM visa vi JOIN composant c ON c.id = vi.composant_id"
        " WHERE vi.modifie_le_vise = c.modifie_le"
    ).fetchall()
    return {ligne[0] for ligne in lignes}


def get_visa(conn: sqlite3.Connection, composant_id: str) -> dict | None:
    """Dernier visa du composant, avec `a_jour` faux s'il a été modifié depuis."""
    return db.fetch_one(
        conn,
        "SELECT vi.vise_par, vi.vise_le, vi.modifie_le_vise = c.modifie_le AS a_jour"
        " FROM visa vi JOIN composant c ON c.id = vi.composant_id WHERE vi.composant_id = ?",
        (composant_id,),
    )


def count_a_voir(conn: sqlite3.Connection) -> int:
    """Nombre de composants non archivés sans visa valable."""
    return conn.execute(
        "SELECT COUNT(*) FROM composant c WHERE c.archive = 0 AND NOT EXISTS ("
        "SELECT 1 FROM visa vi WHERE vi.composant_id = c.id AND vi.modifie_le_vise = c.modifie_le)"
    ).fetchone()[0]


def viser(conn: sqlite3.Connection, identifiants: list[str]) -> int:
    """Pose le visa de la personne connectée sur ces composants ; renvoie le nombre visé.

    Un composant déjà visé depuis sa dernière modification est laissé tel quel ; un composant
    archivé ou inconnu fait tout refuser.
    """
    if not identifiants:
        return 0
    if len(identifiants) > LIMITE_LOT:
        raise ErreurMetier(f"{LIMITE_LOT} composants au plus à la fois.")
    auteur = db.auteur(conn)
    maintenant = datetime.now().isoformat(timespec="seconds")
    vises = 0
    with db.transaction(conn):
        deja = ids_vises(conn)
        for identifiant in dict.fromkeys(identifiants):
            composant = db.fetch_one(
                conn,
                "SELECT modifie_le FROM composant WHERE id = ? AND archive = 0",
                (identifiant,),
            )
            if composant is None:
                raise ErreurMetier(f"Composant « {identifiant} » introuvable ou archivé.")
            if identifiant in deja:
                continue
            conn.execute(
                "INSERT INTO visa (composant_id, vise_par, vise_le, modifie_le_vise)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (composant_id) DO UPDATE SET"
                " vise_par = excluded.vise_par, vise_le = excluded.vise_le,"
                " modifie_le_vise = excluded.modifie_le_vise",
                (identifiant, auteur, maintenant, composant["modifie_le"]),
            )
            journal.write_journal(conn, "composant", identifiant, "visa", None, "visé")
            vises += 1
    return vises
