"""Montage d'un ensemble depuis sa page de montage : monter des pièces, annuler un montage.

Monter crée une « Sortie montage », annuler un « Retour montage » ; le statut de montage de
l'ensemble suit (`ensembles.update_statut_montage`). Comme tout mouvement, une pièce
absente du stock est refusée (`mouvements.insert_mouvement`) ; la page refuse en plus de monter
plus que le reste à monter, ou un composant non affecté à l'ensemble.
"""

import sqlite3
from datetime import date

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import ensembles, mouvements


def _ligne(conn: sqlite3.Connection, code: str, composant: str) -> dict:
    """Ligne de montage du composant dans l'ensemble ; refus s'il n'y est pas affecté."""
    ensembles.verifier_ensemble(conn, code)
    ligne = db.fetch_one(
        conn,
        "SELECT * FROM v_ensemble_composant WHERE ensemble_code = ? AND composant_id = ?",
        (code, composant),
    )
    if ligne is None:
        raise ErreurMetier(f"{composant} n'est pas affecté à l'ensemble {code}.")
    return ligne


def _enregistrer(
    conn: sqlite3.Connection,
    code: str,
    composant: str,
    qte: int,
    type_mouvement: str,
    auteur: str | None,
) -> int:
    valeurs = {
        "date": date.today().isoformat(),
        "composant_id": composant,
        "sens": "Sortie" if type_mouvement == "Sortie montage" else "Entree",
        "type_mouvement": type_mouvement,
        "qte": qte,
        "ensemble_code": code,
        "par_qui": auteur,
    }
    identifiant, _ = mouvements.insert_mouvement(conn, valeurs)
    return identifiant


def monter(
    conn: sqlite3.Connection, code: str, composant: str, qte: int, auteur: str | None
) -> dict:
    """Monte `qte` pièces du composant dans l'ensemble, prises dans le stock."""
    with db.transaction(conn):
        ligne = _ligne(conn, code, composant)
        if qte > ligne["reste_a_monter"]:
            raise ErreurMetier(
                f"Il reste {max(ligne['reste_a_monter'], 0)} pièce(s) de {composant} à monter "
                f"dans {code}, pas {qte}."
            )
        identifiant = _enregistrer(conn, code, composant, qte, "Sortie montage", auteur)
    return mouvements.resultat_mouvement(conn, identifiant, [])


def demonter(
    conn: sqlite3.Connection, code: str, composant: str, qte: int, auteur: str | None
) -> dict:
    """Annule le montage de `qte` pièces : elles reviennent au stock."""
    with db.transaction(conn):
        ligne = _ligne(conn, code, composant)
        if qte > ligne["qte_montee"]:
            raise ErreurMetier(
                f"{max(ligne['qte_montee'], 0)} pièce(s) de {composant} montée(s) dans {code} : "
                f"impossible d'en retirer {qte}."
            )
        identifiant = _enregistrer(conn, code, composant, qte, "Retour montage", auteur)
    return mouvements.resultat_mouvement(conn, identifiant, [])
