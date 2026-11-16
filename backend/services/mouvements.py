"""Mouvements de stock et état du stock."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import composants, ensembles, listes

# Types système : leur code est figé dans valeur_liste et dans les vues.
TYPES_MONTAGE: frozenset[str] = frozenset({"Sortie montage", "Retour montage"})
# Tenu par la base depuis composant.qte_disponible (migration 031), jamais saisi à la main.
STOCK_INITIAL = "Stock initial"


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
    """Enregistre un mouvement de stock ; une sortie au-delà du stock est refusée."""
    if valeurs["type_mouvement"] == STOCK_INITIAL:
        raise ErreurMetier(
            "Le stock initial se règle par la quantité déjà disponible, sur la fiche du composant."
        )
    sens = deduce_sens(conn, valeurs["type_mouvement"], valeurs.get("sens"))
    valeurs = {**valeurs, "sens": sens}
    with db.transaction(conn):
        identifiant, avertissements = insert_mouvement(conn, valeurs)
    return resultat_mouvement(conn, identifiant, avertissements)


def _check_stock(conn: sqlite3.Connection, composant: str, qte: int) -> None:
    """Une sortie ne fait jamais passer le stock sous zéro (la base le refuse aussi, 032)."""
    stock = composants.get_composant(conn, composant)["stock_actuel"]
    if qte > stock:
        raise ErreurMetier(
            f"Pas assez de {composant} en stock : {max(stock, 0)} pièce(s) pour {qte} à sortir. "
            "Enregistrer d'abord l'entrée qui manque (réception, inventaire)."
        )


def insert_mouvement(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> tuple[int, list[str]]:
    """Contrôle et insère un mouvement au sens déjà fixé, dans la transaction de l'appelant.

    Un mouvement de montage remet à jour le statut de montage de son ensemble.
    """
    avertissements = _check_mouvement(conn, valeurs)
    if valeurs["sens"] == "Sortie":
        _check_stock(conn, valeurs["composant_id"], valeurs["qte"])
    identifiant = db.insert_row(conn, "mouvement_stock", valeurs)
    if valeurs["type_mouvement"] in TYPES_MONTAGE:
        ensembles.update_statut_montage(conn, valeurs["ensemble_code"])
    return identifiant, avertissements


def resultat_mouvement(
    conn: sqlite3.Connection, identifiant: int, avertissements: list[str]
) -> dict:
    """Le mouvement enregistré et ses avertissements."""
    mouvement = db.fetch_one(conn, "SELECT * FROM mouvement_stock WHERE id = ?", (identifiant,))
    return {"mouvement": mouvement, "avertissements": avertissements}
