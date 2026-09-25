"""Reclassement d'un composant dans un autre bloc fonctionnel.

Le bloc est figé dans l'identifiant : reclasser crée un nouveau composant dans le bloc
cible, avec un nouvel identifiant et les mêmes données. L'ancien est archivé et pointe
vers son remplaçant (remplace_par) ; ses affectations passent au nouveau. Les commandes, le
stock et les documents restent sur l'ancien identifiant, qui garde ainsi son historique.
"""

import sqlite3

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import composants, journal

# Colonnes propres à la ligne, qui ne sont pas recopiées sur le remplaçant.
NON_RECOPIEES: frozenset[str] = frozenset(
    {"id", "bloc_code", "cree_le", "modifie_le", "archive", "remplace_par"}
)


def _reporter_affectations(conn: sqlite3.Connection, ancien: str, nouveau: str) -> None:
    """Les affectations de l'ancien composant passent au nouveau, avec une ligne de journal."""
    for affectation in db.fetch_all(
        conn, "SELECT id, ensemble_code FROM affectation WHERE composant_id = ?", (ancien,)
    ):
        conn.execute(
            "UPDATE affectation SET composant_id = ? WHERE id = ?", (nouveau, affectation["id"])
        )
        journal.write_journal(
            conn,
            "affectation",
            f"{affectation['ensemble_code']}:{nouveau}",
            "composant_id",
            ancien,
            nouveau,
        )


def reclasser_composant(conn: sqlite3.Connection, identifiant: str, bloc_cible: str) -> dict:
    """Recrée le composant dans le bloc cible ; renvoie le nouveau composant."""
    with db.transaction(conn, immediate=True):
        composants.get_composant(conn, identifiant)
        ancien = composants.get_existant(conn, identifiant)
        if ancien["bloc_code"] == bloc_cible:
            raise ErreurMetier(f"{identifiant} appartient déjà au bloc « {bloc_cible} ».")
        composants.ensure_bloc_ouvert(conn, bloc_cible)
        nouveau = composants.next_id(conn, bloc_cible)
        valeurs = {cle: v for cle, v in ancien.items() if cle not in NON_RECOPIEES}
        db.insert_row(conn, "composant", {"id": nouveau, "bloc_code": bloc_cible, **valeurs})
        journal.write_journal(
            conn, "composant", nouveau, "creation", None, f"reclassé, remplace {identifiant}"
        )
        _reporter_affectations(conn, identifiant, nouveau)
        journal.update_with_journal(
            conn,
            "composant",
            identifiant,
            {"remplace_par": nouveau, "archive": 1},
            frozenset({"remplace_par", "archive"}),
        )
    return composants.get_composant(conn, nouveau)
