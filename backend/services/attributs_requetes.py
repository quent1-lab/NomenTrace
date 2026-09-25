"""Filtres et tri de la liste des composants sur un attribut paramétrable.

Le code d'attribut vient de l'URL : il est d'abord vérifié contre la table attribut, puis
toujours passé en paramètre lié. Seules des expressions SQL fixées ici, choisies selon le
type de l'attribut, entrent dans la requête.
"""

import sqlite3
from typing import Any

from backend.erreurs import ErreurMetier
from backend.services import attributs

OPERATIONS: frozenset[str] = frozenset({"egal", "vide", "renseigne", "entre"})
SOUS_REQUETE: str = "SELECT composant_id FROM composant_attribut WHERE attribut_code = ?"
# Expression de tri selon le type : une liste se trie dans l'ordre de ses valeurs.
EXPRESSIONS_TRI: dict[str, str] = {
    "nombre": "ca.valeur_nombre",
    "liste": "av.ordre",
    "texte": "ca.valeur_texte COLLATE NOCASE",
    "booleen": "ca.valeur_texte",
}


def _borne(attribut: dict, texte: str) -> float | None:
    if not texte.strip():
        return None
    nombre = attributs.lire_nombre(texte)
    if nombre is None:
        raise ErreurMetier(f"{attribut['libelle']} : borne « {texte} » illisible.")
    return nombre


def _clause_egal(attribut: dict, valeur: str) -> tuple[str, list[Any]]:
    # Une valeur désactivée reste filtrable : des composants la portent peut-être encore.
    texte, nombre = attributs.normalize(
        {**attribut, "valeurs": attribut["valeurs"]}, valeur, actuelle=valeur.strip()
    )
    if nombre is not None:
        return f"id IN ({SOUS_REQUETE} AND ABS(valeur_nombre - ?) < 1e-9)", [nombre]
    if attribut["type"] == "texte":
        return f"id IN ({SOUS_REQUETE} AND valeur_texte = ? COLLATE NOCASE)", [texte]
    return f"id IN ({SOUS_REQUETE} AND valeur_texte = ?)", [texte]


def _clause(conn: sqlite3.Connection, filtre: str) -> tuple[str, list[Any]]:
    """« code:vide », « code:renseigne », « code:egal:valeur », « code:entre:min:max »."""
    morceaux = filtre.split(":", 2)
    if len(morceaux) < 2 or morceaux[1] not in OPERATIONS:
        raise ErreurMetier(f"Filtre d'attribut illisible : « {filtre} ».")
    code, operation = morceaux[0], morceaux[1]
    attributs.check_attribut(conn, code)
    attribut = attributs.get_attribut(conn, code)
    reste = morceaux[2] if len(morceaux) > 2 else ""
    if operation == "vide":
        return f"id NOT IN ({SOUS_REQUETE})", [code]
    if operation == "renseigne":
        return f"id IN ({SOUS_REQUETE})", [code]
    if operation == "egal":
        clause, params = _clause_egal(attribut, reste)
        return clause, [code, *params]
    if attribut["type"] != "nombre":
        raise ErreurMetier(f"{attribut['libelle']} : un intervalle ne vaut que pour un nombre.")
    minimum, _, maximum = reste.partition(":")
    bornes = [(">=", _borne(attribut, minimum)), ("<=", _borne(attribut, maximum))]
    conditions, params = [], [code]
    for operateur, borne in bornes:
        if borne is not None:
            conditions.append(f" AND valeur_nombre {operateur} ?")
            params.append(borne)
    return f"id IN ({SOUS_REQUETE}{''.join(conditions)})", params


def build_filtres(conn: sqlite3.Connection, filtres: list[str]) -> tuple[list[str], list[Any]]:
    """Clauses WHERE (sur les colonnes de v_composant) et leurs paramètres."""
    clauses, params = [], []
    for filtre in filtres:
        clause, valeurs = _clause(conn, filtre)
        clauses.append(clause)
        params.extend(valeurs)
    return clauses, params


def build_tri(conn: sqlite3.Connection, code: str) -> tuple[str, list[Any]]:
    """Source de la liste triée sur un attribut : v_composant plus une colonne _tri."""
    attribut = attributs.check_attribut(conn, code)
    expression = EXPRESSIONS_TRI[attribut["type"]]
    source = (
        f"(SELECT v.*, {expression} AS _tri FROM v_composant v"  # noqa: S608
        " LEFT JOIN composant_attribut ca ON ca.composant_id = v.id AND ca.attribut_code = ?"
        " LEFT JOIN attribut_valeur av"
        " ON av.attribut_code = ca.attribut_code AND av.code = ca.valeur_texte)"
    )
    return source, [code]
