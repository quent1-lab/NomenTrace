"""Listes de valeurs paramétrables : modes d'appro, statuts, criticités, types de mouvement.

Les valeurs « système » portent les calculs (Achat, Bloquant, les mouvements de réception,
de montage et d'inventaire) : leur code est figé et elles ne peuvent être ni supprimées ni
désactivées. Les autres se créent, se renomment, se désactivent ou, si elles ne servent
nulle part, se suppriment.
"""

import sqlite3
import unicodedata
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import journal

LISTES: dict[str, str] = {
    "mode_appro": "Mode d'approvisionnement",
    "statut_appro": "Statut d'appro",
    "statut_choix": "Statut de choix",
    "criticite": "Criticité",
    "type_mouvement": "Type de mouvement",
}

# Où chaque liste est utilisée : pour refuser la suppression d'une valeur en service.
UTILISATIONS: dict[str, tuple[str, str]] = {
    "mode_appro": ("composant", "mode_appro"),
    "statut_appro": ("composant", "statut_appro"),
    "statut_choix": ("composant", "statut_choix"),
    "criticite": ("composant", "criticite"),
    "type_mouvement": ("mouvement_stock", "type_mouvement"),
}


def _check_liste(liste: str) -> None:
    if liste not in LISTES:
        raise Introuvable(f"Liste « {liste} » inconnue.")


def list_listes(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Toutes les listes, avec leurs valeurs triées par ordre (actives et inactives)."""
    lignes = db.fetch_all(conn, "SELECT * FROM valeur_liste ORDER BY liste, ordre, libelle")
    return {liste: [v for v in lignes if v["liste"] == liste] for liste in LISTES}


def get_valeur(conn: sqlite3.Connection, liste: str, code: str) -> dict:
    _check_liste(liste)
    valeur = db.fetch_one(
        conn, "SELECT * FROM valeur_liste WHERE liste = ? AND code = ?", (liste, code)
    )
    if valeur is None:
        raise Introuvable(f"Valeur « {code} » introuvable dans la liste {LISTES[liste]}.")
    return valeur


def check_valeur(conn: sqlite3.Connection, liste: str, code: str | None) -> None:
    """Refuse une valeur inconnue ou désactivée pour une nouvelle saisie."""
    if code is None:
        return
    valeur = db.fetch_one(
        conn, "SELECT actif FROM valeur_liste WHERE liste = ? AND code = ?", (liste, code)
    )
    if valeur is None:
        raise ErreurMetier(f"{LISTES[liste]} : « {code} » n'existe pas dans la liste.")
    if not valeur["actif"]:
        raise ErreurMetier(f"{LISTES[liste]} : « {code} » est désactivé.")


def get_sens(conn: sqlite3.Connection, type_mouvement: str) -> str | None:
    """Sens imposé par un type de mouvement, None s'il est libre (inventaire)."""
    return get_valeur(conn, "type_mouvement", type_mouvement)["sens"]


def code_depuis_libelle(libelle: str) -> str:
    """Code stocké : le libellé sans accents, comme les valeurs d'origine."""
    decompose = unicodedata.normalize("NFKD", libelle.strip())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def create_valeur(conn: sqlite3.Connection, liste: str, valeurs: dict[str, Any]) -> dict:
    """Ajoute une valeur en fin de liste ; son code est dérivé du libellé."""
    _check_liste(liste)
    if liste == "type_mouvement" and "sens" not in valeurs:
        raise ErreurMetier("Préciser le sens du type de mouvement (entrée, sortie ou libre).")
    if liste != "type_mouvement" and valeurs.get("sens"):
        raise ErreurMetier("Seuls les types de mouvement ont un sens.")
    code = code_depuis_libelle(valeurs["libelle"])
    with db.transaction(conn):
        if db.fetch_one(
            conn, "SELECT 1 FROM valeur_liste WHERE liste = ? AND code = ?", (liste, code)
        ):
            raise Conflit(f"La valeur « {code} » existe déjà dans la liste {LISTES[liste]}.")
        ordre = conn.execute(
            "SELECT COALESCE(MAX(ordre), 0) + 1 FROM valeur_liste WHERE liste = ?", (liste,)
        ).fetchone()[0]
        db.insert_row(
            conn,
            "valeur_liste",
            {
                "liste": liste,
                "code": code,
                "libelle": valeurs["libelle"].strip(),
                "ordre": ordre,
                "sens": valeurs.get("sens"),
            },
        )
        journal.write_journal(conn, "valeur_liste", f"{liste}:{code}", "creation", None, "créée")
    return get_valeur(conn, liste, code)


def patch_valeur(
    conn: sqlite3.Connection, liste: str, code: str, modifications: dict[str, Any]
) -> dict:
    """Modifie le libellé, l'ordre, l'état actif ou le sens d'une valeur."""
    with db.transaction(conn):
        actuelle = get_valeur(conn, liste, code)
        if actuelle["systeme"] and modifications.get("actif") == 0:
            raise ErreurMetier(
                f"« {actuelle['libelle']} » est une valeur système : elle reste active."
            )
        if "sens" in modifications and (liste != "type_mouvement" or actuelle["systeme"]):
            raise ErreurMetier("Le sens ne se modifie que sur un type de mouvement non système.")
        for champ, valeur in modifications.items():
            if valeur == actuelle[champ]:
                continue
            conn.execute(
                f"UPDATE valeur_liste SET {champ} = ? WHERE liste = ? AND code = ?",  # noqa: S608
                (valeur, liste, code),
            )
            journal.write_journal(
                conn, "valeur_liste", f"{liste}:{code}", champ, actuelle[champ], valeur
            )
    return get_valeur(conn, liste, code)


def delete_valeur(conn: sqlite3.Connection, liste: str, code: str) -> None:
    """Supprime une valeur non système qui n'est utilisée nulle part."""
    with db.transaction(conn):
        actuelle = get_valeur(conn, liste, code)
        if actuelle["systeme"]:
            raise ErreurMetier(
                f"« {actuelle['libelle']} » est une valeur système : non supprimable."
            )
        table, colonne = UTILISATIONS[liste]
        nb = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {colonne} = ?",  # noqa: S608
            (code,),
        ).fetchone()[0]
        if nb:
            raise Conflit(
                f"« {actuelle['libelle']} » est utilisée {nb} fois : la désactiver plutôt que "
                "la supprimer, pour garder l'historique."
            )
        conn.execute("DELETE FROM valeur_liste WHERE liste = ? AND code = ?", (liste, code))
        journal.write_journal(conn, "valeur_liste", f"{liste}:{code}", "suppression", code, None)
