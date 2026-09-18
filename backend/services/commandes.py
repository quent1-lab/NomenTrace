"""Commandes et lignes de commande."""

import re
import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, Introuvable
from backend.services import composants, fournisseurs, journal, parametres

CHAMPS_COMMANDE: frozenset[str] = frozenset(
    {
        "type",
        "statut",
        "fournisseur_nom",
        "demande_par",
        "date_demande",
        "date_reception_devis",
        "date_commande",
        "livraison_annoncee",
        "date_reception_reelle",
        "port_ht",
        "taux_tva",
        "reference_externe",
        "lien_document",
        "commentaire",
    }
)
CHAMPS_LIGNE: frozenset[str] = frozenset(
    {"qte_commandee", "pu_ht_devis", "qte_recue", "date_reception", "statut_ligne", "commentaire"}
)
_MOTIF_NUMERO = re.compile(r"^CMD-(\d+)$")


def list_commandes(
    conn: sqlite3.Connection, statut: str | None = None, fournisseur: str | None = None
) -> list[dict]:
    """Renvoie les commandes non archivées avec leurs totaux."""
    return db.fetch_all(
        conn,
        "SELECT * FROM v_commande WHERE (? IS NULL OR statut = ?)"
        " AND (? IS NULL OR fournisseur_nom = ?) ORDER BY numero DESC",
        (statut, statut, fournisseur, fournisseur),
    )


def get_commande(conn: sqlite3.Connection, numero: str) -> dict:
    """Renvoie une commande non archivée avec ses totaux."""
    commande = db.fetch_one(conn, "SELECT * FROM v_commande WHERE numero = ?", (numero,))
    if commande is None:
        raise Introuvable(f"Commande « {numero} » introuvable ou archivée.")
    return commande


def next_numero(conn: sqlite3.Connection) -> str:
    """Prochain numéro CMD-NNN : plus grand numéro existant plus un, archivées comprises."""
    numeros = [0]
    for (numero,) in conn.execute("SELECT numero FROM commande").fetchall():
        correspondance = _MOTIF_NUMERO.match(numero)
        if correspondance:
            numeros.append(int(correspondance.group(1)))
    return f"CMD-{max(numeros) + 1:03d}"


def create_commande(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée une commande avec un numéro généré par le serveur."""
    with db.transaction(conn, immediate=True):
        fournisseurs.ensure_fournisseur(conn, valeurs.get("fournisseur_nom"))
        if valeurs.get("taux_tva") is None:
            valeurs["taux_tva"] = parametres.get_taux_tva_defaut(conn)
        numero = next_numero(conn)
        db.insert_row(conn, "commande", {"numero": numero, **valeurs})
        journal.write_journal(conn, "commande", numero, "creation", None, "créée")
    return get_commande(conn, numero)


def patch_commande(conn: sqlite3.Connection, numero: str, modifications: dict[str, Any]) -> dict:
    """Modifie une commande non archivée."""
    with db.transaction(conn):
        get_commande(conn, numero)
        if "fournisseur_nom" in modifications:
            fournisseurs.ensure_fournisseur(conn, modifications["fournisseur_nom"])
        journal.update_with_journal(conn, "commande", numero, modifications, CHAMPS_COMMANDE)
    return get_commande(conn, numero)


def archive_commande(conn: sqlite3.Connection, numero: str) -> None:
    """Archive une commande."""
    with db.transaction(conn):
        get_commande(conn, numero)
        journal.update_with_journal(
            conn, "commande", numero, {"archive": 1}, frozenset({"archive"})
        )


def list_lignes(conn: sqlite3.Connection, numero: str) -> list[dict]:
    """Renvoie les lignes d'une commande, avec la désignation et le montant de chaque ligne."""
    get_commande(conn, numero)
    return db.fetch_all(
        conn,
        "SELECT l.*, c.designation, c.bloc_code, c.pu_ht AS pu_ht_estime,"
        " l.qte_commandee * l.pu_ht_devis AS montant_ligne_ht"
        " FROM ligne_commande l LEFT JOIN v_composant c ON c.id = l.composant_id"
        " WHERE l.commande_numero = ? ORDER BY l.id",
        (numero,),
    )


def _get_ligne(conn: sqlite3.Connection, numero: str, identifiant: int) -> dict:
    ligne = db.fetch_one(
        conn,
        "SELECT * FROM ligne_commande WHERE id = ? AND commande_numero = ?",
        (identifiant, numero),
    )
    if ligne is None:
        raise Introuvable(f"Ligne {identifiant} introuvable dans la commande {numero}.")
    return ligne


def create_ligne(conn: sqlite3.Connection, numero: str, valeurs: dict[str, Any]) -> dict:
    """Ajoute une ligne à une commande."""
    with db.transaction(conn):
        get_commande(conn, numero)
        composants.get_composant(conn, valeurs["composant_id"])
        identifiant = db.insert_row(conn, "ligne_commande", {"commande_numero": numero, **valeurs})
        journal.write_journal(
            conn, "commande", numero, f"ligne {identifiant}", None, valeurs["composant_id"]
        )
    return _get_ligne(conn, numero, identifiant)


def patch_ligne(
    conn: sqlite3.Connection, numero: str, identifiant: int, modifications: dict[str, Any]
) -> dict:
    """Modifie une ligne de commande."""
    with db.transaction(conn):
        _get_ligne(conn, numero, identifiant)
        journal.update_with_journal(
            conn, "ligne_commande", identifiant, modifications, CHAMPS_LIGNE
        )
    return _get_ligne(conn, numero, identifiant)


def delete_ligne(conn: sqlite3.Connection, numero: str, identifiant: int) -> None:
    """Supprime une ligne, refusé si des pièces ont déjà été reçues."""
    with db.transaction(conn):
        ligne = _get_ligne(conn, numero, identifiant)
        if ligne["qte_recue"] > 0:
            raise Conflit(
                "Des pièces ont déjà été reçues sur cette ligne : elle ne peut pas être "
                "supprimée. Passez-la au statut Annulee si besoin."
            )
        conn.execute("DELETE FROM ligne_commande WHERE id = ?", (identifiant,))
        journal.write_journal(
            conn, "commande", numero, f"ligne {identifiant}", ligne["composant_id"], None
        )
