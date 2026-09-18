"""Consultation des dépôts d'import : liste, détail des propositions, abandon."""

import json
import sqlite3
from collections import Counter

from backend import db
from backend.erreurs import ErreurMetier, Introuvable

ORDRE_CATEGORIES: tuple[str, ...] = (
    "NOUVELLE_ENTITE",
    "MODIFIE",
    "DOUBLON",
    "NOUVEAU",
    "CREATION_AFFECTATION",
    "MODIF_AFFECTATION",
    "SUPPRESSION_AFFECTATION",
    "INCONNU",
    "INVALIDE",
    "IDENTIQUE",
)


def list_depots(conn: sqlite3.Connection) -> list[dict]:
    """Dépôts, les plus récents en premier, avec leurs fichiers et le décompte par catégorie."""
    lots = db.fetch_all(conn, "SELECT * FROM import_lot ORDER BY depot DESC, id")
    comptes = db.fetch_all(
        conn,
        "SELECT l.depot, g.categorie, COUNT(*) AS nb FROM import_ligne g"
        " JOIN import_lot l ON l.id = g.lot_id GROUP BY l.depot, g.categorie",
    )
    depots: dict[int, dict] = {}
    for lot in lots:
        depot = depots.setdefault(
            lot["depot"],
            {
                "depot": lot["depot"],
                "horodatage": lot["horodatage"],
                "statut": lot["statut"],
                "depose_par": lot["depose_par"],
                "fichiers": [],
                "resume": {},
            },
        )
        depot["fichiers"].append(lot["nom_fichier"])
    for compte in comptes:
        depots[compte["depot"]]["resume"][compte["categorie"]] = compte["nb"]
    return list(depots.values())


def get_lots(conn: sqlite3.Connection, depot: int) -> list[dict]:
    lots = db.fetch_all(conn, "SELECT * FROM import_lot WHERE depot = ? ORDER BY id", (depot,))
    if not lots:
        raise Introuvable(f"Dépôt {depot} introuvable.")
    return lots


def list_lignes(conn: sqlite3.Connection, depot: int) -> list[dict]:
    """Propositions du dépôt dans l'ordre des fichiers et des lignes, données décodées."""
    lignes = db.fetch_all(
        conn,
        "SELECT g.* FROM import_ligne g JOIN import_lot l ON l.id = g.lot_id"
        " WHERE l.depot = ? ORDER BY g.lot_id, g.numero_ligne, g.id",
        (depot,),
    )
    for ligne in lignes:
        ligne["donnees"] = json.loads(ligne.pop("donnees_json"))
        ligne["decision"] = json.loads(ligne["decision"]) if ligne["decision"] else None
    return lignes


def get_depot(conn: sqlite3.Connection, depot: int) -> dict:
    lots = get_lots(conn, depot)
    lignes = list_lignes(conn, depot)
    resume = Counter(ligne["categorie"] for ligne in lignes)
    return {
        "depot": depot,
        "statut": lots[0]["statut"],
        "lots": lots,
        "resume": {c: resume[c] for c in ORDRE_CATEGORIES if resume[c]},
        "lignes": lignes,
    }


def abandon_depot(conn: sqlite3.Connection, depot: int) -> None:
    """Abandonne un dépôt non appliqué : ses propositions restent consultables."""
    with db.transaction(conn):
        lots = get_lots(conn, depot)
        if lots[0]["statut"] != "analyse":
            raise ErreurMetier(f"Le dépôt {depot} est déjà {lots[0]['statut']}.")
        conn.execute("UPDATE import_lot SET statut = 'abandonne' WHERE depot = ?", (depot,))
