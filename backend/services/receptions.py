"""Réception d'une commande : quantités reçues, entrées en stock et statut, en une transaction."""

import sqlite3
from datetime import date
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import commandes, journal

STATUTS_RECEPTIONNABLES: frozenset[str] = frozenset({"Commande", "Livre partiel", "Livre"})


def _check_commande(commande: dict) -> None:
    if commande["type"] != "Commande" or commande["statut"] not in STATUTS_RECEPTIONNABLES:
        raise ErreurMetier(
            "Seule une commande passée (statut Commande ou Livré partiel) peut être "
            "réceptionnée : passer d'abord la commande au statut Commande."
        )


def _receive_line(
    conn: sqlite3.Connection, ligne: dict, qte: int, reception: dict[str, Any]
) -> str | None:
    """Enregistre la réception d'une ligne ; renvoie un avertissement éventuel."""
    recue = ligne["qte_recue"] + qte
    statut = "Recue" if recue >= ligne["qte_commandee"] else "Recue partiel"
    journal.update_with_journal(
        conn,
        "ligne_commande",
        ligne["id"],
        {"qte_recue": recue, "statut_ligne": statut, "date_reception": reception["date"]},
        frozenset({"qte_recue", "statut_ligne", "date_reception"}),
    )
    db.insert_row(
        conn,
        "mouvement_stock",
        {
            "date": reception["date"],
            "composant_id": ligne["composant_id"],
            "sens": "Entree",
            "type_mouvement": "Reception achat",
            "qte": qte,
            "emplacement": reception.get("emplacement"),
            "par_qui": reception.get("par_qui"),
            "commande_numero": ligne["commande_numero"],
        },
    )
    if recue > ligne["qte_commandee"]:
        return (
            f"{ligne['composant_id']} : {recue} reçu(s) pour {ligne['qte_commandee']} "
            "commandé(s). La réception est enregistrée, vérifier le bon de livraison."
        )
    return None


def _new_statut(conn: sqlite3.Connection, numero: str) -> str:
    """Livre si toutes les lignes non annulées sont reçues, sinon Livre partiel."""
    reste = conn.execute(
        "SELECT COUNT(*) FROM ligne_commande WHERE commande_numero = ?"
        " AND statut_ligne <> 'Annulee' AND qte_recue < qte_commandee",
        (numero,),
    ).fetchone()[0]
    return "Livre" if reste == 0 else "Livre partiel"


def receive_commande(conn: sqlite3.Connection, numero: str, reception: dict[str, Any]) -> dict:
    """Réceptionne une livraison : quantités reçues ligne par ligne, stock et statut."""
    reception = {**reception, "date": reception.get("date") or date.today().isoformat()}
    quantites = {ligne["id"]: ligne["qte"] for ligne in reception["lignes"] if ligne["qte"] > 0}
    if not quantites:
        raise ErreurMetier("Aucune quantité reçue n'a été saisie.")
    avertissements = []
    with db.transaction(conn):
        _check_commande(commandes.get_commande(conn, numero))
        lignes = {ligne["id"]: ligne for ligne in commandes.list_lignes(conn, numero)}
        for identifiant, qte in quantites.items():
            ligne = lignes.get(identifiant)
            if ligne is None:
                raise ErreurMetier(
                    f"La ligne {identifiant} n'appartient pas à la commande {numero}."
                )
            if ligne["statut_ligne"] == "Annulee":
                raise ErreurMetier(f"La ligne {identifiant} est annulée : rien à réceptionner.")
            avertissement = _receive_line(conn, ligne, qte, reception)
            if avertissement:
                avertissements.append(avertissement)
        modifs = {"statut": _new_statut(conn, numero)}
        if modifs["statut"] == "Livre":
            modifs["date_reception_reelle"] = reception["date"]
        journal.update_with_journal(
            conn, "commande", numero, modifs, frozenset({"statut", "date_reception_reelle"})
        )
    return {"commande": commandes.get_commande(conn, numero), "avertissements": avertissements}
