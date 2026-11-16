"""Réception d'une commande : quantités reçues, entrées en stock et statut, en une transaction."""

import sqlite3
from datetime import date
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier
from backend.services import commandes, communes_sync, journal

STATUTS_RECEPTIONNABLES: frozenset[str] = frozenset({"Commande", "Livre partiel", "Livre"})


def _check_commande(commande: dict) -> None:
    if commande["type"] != "Commande" or commande["statut"] not in STATUTS_RECEPTIONNABLES:
        raise ErreurMetier(
            "Seule une commande passée (statut Commande ou Livré partiel) peut être "
            "réceptionnée : passer d'abord la commande au statut Commande."
        )


def _emplacement(saisie: dict, reception: dict[str, Any]) -> str | None:
    """Celui de la ligne, sinon celui de la livraison ; vide vaut absent."""
    for valeur in (saisie.get("emplacement"), reception.get("emplacement")):
        if valeur and valeur.strip():
            return valeur.strip()
    return None


def _receive_line(
    conn: sqlite3.Connection, ligne: dict, saisie: dict, reception: dict[str, Any]
) -> str | None:
    """Enregistre la réception d'une ligne ; renvoie un avertissement éventuel."""
    qte = saisie["qte"]
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
            # La ligne compte des lots ; le stock compte des pièces.
            "qte": qte * ligne["qte_par_lot"],
            "emplacement": _emplacement(saisie, reception),
            "par_qui": reception.get("par_qui"),
            "commande_numero": ligne["commande_numero"],
        },
    )
    if recue > ligne["qte_commandee"]:
        unite = " lot(s)" if ligne["qte_par_lot"] > 1 else ""
        return (
            f"{ligne['composant_id']} : {recue}{unite} reçu(s) pour {ligne['qte_commandee']} "
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


def check_lue(ligne: dict, lue: int | None) -> None:
    """La saisie porte la quantité reçue qu'elle a lue : un écart veut dire qu'une autre
    réception est passée entre-temps (depuis la commune ou depuis le projet)."""
    if lue is not None and lue != ligne["qte_recue"]:
        raise Conflit(
            f"{ligne['composant_id']} : {ligne['qte_recue']} déjà reçu(s), {lue} lu(s) à"
            " l'ouverture de la réception. Une autre réception est passée entre-temps :"
            " recharger la page avant de saisir."
        )


def _entree(conn: sqlite3.Connection, ligne: dict, saisie: dict, reception: dict) -> dict:
    """Ce que la réception d'une ligne a ajouté au stock, pour le récapitulatif."""
    stock = conn.execute(
        "SELECT stock_actuel FROM v_composant WHERE id = ?", (ligne["composant_id"],)
    ).fetchone()
    return {
        "composant_id": ligne["composant_id"],
        "designation": ligne["designation"],
        "pieces": saisie["qte"] * ligne["qte_par_lot"],
        "stock_actuel": stock[0] if stock else None,
        "emplacement": _emplacement(saisie, reception),
    }


def receive_lignes(
    conn: sqlite3.Connection, numero: str, reception: dict[str, Any]
) -> tuple[list[str], list[dict]]:
    """Réceptionne les lignes d'une commande, dans la transaction de l'appelant ; renvoie
    les avertissements et les entrées en stock. `reception["lignes"]` : id, qte,
    qte_recue_lue et emplacement facultatifs (à défaut, celui de la livraison)."""
    saisies = [ligne for ligne in reception["lignes"] if ligne["qte"] > 0]
    if not saisies:
        raise ErreurMetier("Aucune quantité reçue n'a été saisie.")
    _check_commande(commandes.get_commande(conn, numero))
    lignes = {ligne["id"]: ligne for ligne in commandes.list_lignes(conn, numero)}
    avertissements = []
    for saisie in saisies:
        ligne = lignes.get(saisie["id"])
        if ligne is None:
            raise ErreurMetier(f"La ligne {saisie['id']} n'appartient pas à la commande {numero}.")
        if ligne["statut_ligne"] == "Annulee":
            raise ErreurMetier(f"La ligne {saisie['id']} est annulée : rien à réceptionner.")
        check_lue(ligne, saisie.get("qte_recue_lue"))
        avertissement = _receive_line(conn, ligne, saisie, reception)
        if avertissement:
            avertissements.append(avertissement)
    entrees = [_entree(conn, lignes[saisie["id"]], saisie, reception) for saisie in saisies]
    modifs = {"statut": _new_statut(conn, numero)}
    if modifs["statut"] == "Livre":
        modifs["date_reception_reelle"] = reception["date"]
    journal.update_with_journal(
        conn, "commande", numero, modifs, frozenset({"statut", "date_reception_reelle"})
    )
    return avertissements, entrees


def receive_commande(conn: sqlite3.Connection, numero: str, reception: dict[str, Any]) -> dict:
    """Réceptionne une livraison : quantités reçues ligne par ligne, stock et statut.

    La copie d'une commande commune se reçoit aussi depuis son projet : son verrou est levé
    le temps de la réception (communes_sync.ouverte), seule écriture qu'elle accepte ici.
    """
    reception = {**reception, "date": reception.get("date") or date.today().isoformat()}
    commune = commandes.get_commande(conn, numero).get("commune")
    if commune is not None and any(
        ligne.get("qte_recue_lue") is None for ligne in reception["lignes"] if ligne["qte"] > 0
    ):
        raise ErreurMetier("La réception d'une commande commune doit dire ce qu'elle a lu.")
    with communes_sync.ouverte(conn) if commune else db.transaction(conn):
        avertissements, entrees = receive_lignes(conn, numero, reception)
    return {
        "commande": commandes.get_commande(conn, numero),
        "avertissements": avertissements,
        "entrees": entrees,
    }
