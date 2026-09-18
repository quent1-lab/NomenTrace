"""Mouvements de stock et état du stock."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import composants, listes

# Types système : leur code est figé dans valeur_liste et dans les vues.
TYPES_MONTAGE: frozenset[str] = frozenset({"Sortie montage", "Retour montage"})


def list_mouvements(
    conn: sqlite3.Connection,
    composant: str | None = None,
    type_mouvement: str | None = None,
    ensemble: str | None = None,
) -> list[dict]:
    """Renvoie les mouvements, les plus récents en premier, filtrés si demandé."""
    return db.fetch_all(
        conn,
        "SELECT m.*, c.designation FROM mouvement_stock m"
        " LEFT JOIN composant c ON c.id = m.composant_id"
        " WHERE (? IS NULL OR m.composant_id = ?) AND (? IS NULL OR m.type_mouvement = ?)"
        " AND (? IS NULL OR m.ensemble_code = ?) ORDER BY m.date DESC, m.id DESC",
        (composant, composant, type_mouvement, type_mouvement, ensemble, ensemble),
    )


def list_stock(conn: sqlite3.Connection) -> list[dict]:
    """Composants dont le stock est non nul (négatif compris), avec leur emplacement."""
    return db.fetch_all(conn, "SELECT * FROM v_stock ORDER BY stock_actuel < 0 DESC, id")


def deduce_sens(conn: sqlite3.Connection, type_mouvement: str, sens: str | None) -> str:
    """Sens du mouvement : imposé par le type, sinon (inventaire…) il doit être précisé."""
    listes.check_valeur(conn, "type_mouvement", type_mouvement)
    impose = listes.get_sens(conn, type_mouvement)
    if impose is None:
        if sens is None:
            raise ErreurMetier(
                f"Pour un mouvement « {type_mouvement} », préciser le sens : entrée ou sortie."
            )
        return sens
    if sens is not None and sens != impose:
        raise ErreurMetier(
            f"Un mouvement « {type_mouvement} » est forcément une "
            f"{'entrée' if impose == 'Entree' else 'sortie'} de stock."
        )
    return impose


def _check_mouvement(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> list[str]:
    """Contrôle la cohérence du mouvement ; renvoie les avertissements non bloquants."""
    composants.get_composant(conn, valeurs["composant_id"])
    type_mouvement = valeurs["type_mouvement"]
    ensemble = valeurs.get("ensemble_code")
    if type_mouvement in TYPES_MONTAGE and not ensemble:
        raise ErreurMetier(f"Un mouvement « {type_mouvement} » doit désigner un ensemble.")
    if type_mouvement not in TYPES_MONTAGE and ensemble:
        raise ErreurMetier("Seuls les mouvements de montage désignent un ensemble.")
    if ensemble and not db.fetch_one(
        conn, "SELECT 1 FROM ensemble WHERE code = ? AND archive = 0", (ensemble,)
    ):
        raise Introuvable(f"Ensemble « {ensemble} » introuvable ou archivé.")
    numero = valeurs.get("commande_numero")
    if numero and not db.fetch_one(conn, "SELECT 1 FROM commande WHERE numero = ?", (numero,)):
        raise Introuvable(f"Commande « {numero} » introuvable.")
    avertissements = []
    if ensemble and not db.fetch_one(
        conn,
        "SELECT 1 FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
        (ensemble, valeurs["composant_id"]),
    ):
        avertissements.append(
            f"{valeurs['composant_id']} n'est pas affecté à l'ensemble {ensemble} : le mouvement "
            "est enregistré et signalé dans la cohérence des ensembles."
        )
    return avertissements


def create_mouvement(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Enregistre un mouvement de stock. Un stock négatif est autorisé et signalé."""
    sens = deduce_sens(conn, valeurs["type_mouvement"], valeurs.get("sens"))
    valeurs = {**valeurs, "sens": sens}
    with db.transaction(conn):
        avertissements = _check_mouvement(conn, valeurs)
        identifiant = db.insert_row(conn, "mouvement_stock", valeurs)
    stock = composants.get_composant(conn, valeurs["composant_id"])["stock_actuel"]
    if stock < 0:
        avertissements.append(
            f"Le stock de {valeurs['composant_id']} devient négatif ({stock}) : une entrée a "
            "probablement été oubliée."
        )
    mouvement = db.fetch_one(conn, "SELECT * FROM mouvement_stock WHERE id = ?", (identifiant,))
    return {"mouvement": mouvement, "avertissements": avertissements}
