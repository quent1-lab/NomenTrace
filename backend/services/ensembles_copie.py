"""Duplication d'un ensemble, avec ou sans ses affectations et ses sous-ensembles.

La copie reprend nom, ordre, responsable, description et, sur demande, les affectations
(quantités et commentaires). Elle ne reprend ni le statut de montage, remis à « Non
commence », ni le budget verrouillé : une copie n'a encore rien de monté ni d'arbitré.
"""

import re
import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier
from backend.services import ensembles, ensembles_arbre, journal

MOTIF_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")
LONGUEUR_CODE: int = 20
COLONNES_COPIEES: tuple[str, ...] = ("nom", "ordre", "description", "responsable")


def _descendants_ordonnes(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Descendants non archivés, chaque parent avant ses enfants."""
    ordre = [e["code"] for e in ensembles_arbre.list_ensembles(conn)]
    descendants = ensembles_arbre.list_descendants(conn, code)
    lignes = {
        e["code"]: e
        for e in db.fetch_all(conn, "SELECT * FROM ensemble WHERE archive = 0")
        if e["code"] in descendants
    }
    return [lignes[c] for c in ordre if c in lignes]


def proposer_code(source: str, ancien: str, nouveau: str) -> str:
    """Code proposé pour la copie d'un sous-ensemble.

    Un code qui commence par celui de l'ensemble copié en prend le nouveau début
    (ROUE-G sous ROUE → ROUE2-G sous ROUE2) ; sinon, le nouveau code est ajouté en suffixe.
    """
    if ancien.startswith(source):
        return (nouveau + ancien[len(source) :])[:LONGUEUR_CODE]
    return f"{ancien}-{nouveau}"[:LONGUEUR_CODE]


def get_proposition(conn: sqlite3.Connection, code: str, nouveau: str) -> list[dict]:
    """Sous-ensembles qui seraient copiés, avec le code proposé pour chacun."""
    ensembles.verifier_ensemble(conn, code)
    return [
        {
            "code": e["code"],
            "nom": e["nom"],
            "code_propose": proposer_code(code, e["code"], nouveau),
        }
        for e in _descendants_ordonnes(conn, code)
    ]


def _verifier_codes(conn: sqlite3.Connection, codes: list[str]) -> None:
    for code in codes:
        if not MOTIF_CODE.match(code) or len(code) > LONGUEUR_CODE:
            raise ErreurMetier(
                f"Code d'ensemble invalide : « {code} » (majuscules, chiffres et tirets, "
                f"{LONGUEUR_CODE} caractères au plus)."
            )
    doublons = {c for c in codes if codes.count(c) > 1}
    if doublons:
        raise ErreurMetier(f"Code donné deux fois : {', '.join(sorted(doublons))}.")
    for code in codes:
        if db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ?", (code,)):
            raise Conflit(f"Le code d'ensemble « {code} » est déjà utilisé.")


def _copier(
    conn: sqlite3.Connection, source: dict, valeurs: dict[str, Any], avec_affectations: bool
) -> None:
    """Crée la copie d'un ensemble et, sur demande, de ses affectations."""
    ligne = {col: source[col] for col in COLONNES_COPIEES}
    ligne.update(valeurs)
    db.insert_row(conn, "ensemble", ligne)
    journal.write_journal(
        conn, "ensemble", ligne["code"], "creation", None, f"copie de {source['code']}"
    )
    if not avec_affectations:
        return
    for affectation in db.fetch_all(
        conn,
        "SELECT composant_id, qte, commentaire FROM affectation WHERE ensemble_code = ?",
        (source["code"],),
    ):
        db.insert_row(conn, "affectation", {"ensemble_code": ligne["code"], **affectation})
        journal.write_journal(
            conn,
            "affectation",
            f"{ligne['code']}:{affectation['composant_id']}",
            "qte",
            None,
            affectation["qte"],
        )


def dupliquer_ensemble(conn: sqlite3.Connection, code: str, demande: dict[str, Any]) -> dict:
    """Duplique un ensemble ; `demande` porte code, nom, parent éventuel, options et codes.

    `codes` associe à chaque sous-ensemble copié son nouveau code ; un code absent reçoit
    le code proposé. Renvoie la copie de l'ensemble de départ.
    """
    with db.transaction(conn, immediate=True):
        source = ensembles.verifier_ensemble(conn, code)
        parent = demande["parent_code"] if "parent_code" in demande else source["parent_code"]
        descendants = _descendants_ordonnes(conn, code) if demande["avec_sous_ensembles"] else []
        nouveaux = {code: demande["code"]}
        for d in descendants:
            nouveaux[d["code"]] = demande["codes"].get(d["code"]) or proposer_code(
                code, d["code"], demande["code"]
            )
        _verifier_codes(conn, list(nouveaux.values()))
        ensembles.verifier_parent(conn, demande["code"], parent)
        _copier(
            conn,
            source,
            {"code": demande["code"], "nom": demande["nom"], "parent_code": parent},
            demande["avec_affectations"],
        )
        for d in descendants:
            valeurs = {"code": nouveaux[d["code"]], "parent_code": nouveaux[d["parent_code"]]}
            _copier(conn, d, valeurs, demande["avec_affectations"])
    return ensembles_arbre.get_ensemble(conn, demande["code"])
