"""Accès d'un assistant IA par le protocole MCP : ouverture du projet et jetons personnels.

L'administrateur du projet ouvre l'accès aux administrateurs seuls ou à tous les membres
(`projet.mcp_acces`, fermé par défaut). Un membre autorisé crée alors un jeton personnel,
valable pour ce seul projet : le jeton en clair n'est montré qu'une fois, seule son
empreinte SHA-256 est gardée. Le jeton n'ouvre que la route MCP ; les droits sont ceux du
compte, relus à chaque appel, comme l'ouverture du projet.
"""

import logging
import sqlite3

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import authentification, comptes
from backend.services.droits import AccesRefuse, Utilisateur

journal_log = logging.getLogger(__name__)

ACCES: tuple[str, ...] = ("ferme", "admin", "membres")
PREFIXE_JETON = "nt_"


def get_acces(conn: sqlite3.Connection, projet: str) -> str:
    ligne = db.fetch_one(conn, "SELECT mcp_acces FROM projet WHERE code = ?", (projet,))
    return ligne["mcp_acces"] if ligne else "ferme"


def set_acces(conn: sqlite3.Connection, projet: str, acces: str, par: str) -> None:
    if acces not in ACCES:
        raise ErreurMetier(f"Accès inconnu : {acces}.")
    with db.transaction(conn):
        conn.execute("UPDATE projet SET mcp_acces = ? WHERE code = ?", (acces, projet))
        if acces == "ferme":
            # Fermer révoque : rouvrir plus tard ne ressuscite pas d'anciens jetons.
            conn.execute(
                "UPDATE jeton_api SET revoque_le = ? WHERE projet = ? AND revoque_le IS NULL",
                (_maintenant(), projet),
            )
    journal_log.info("Accès MCP du projet %s réglé sur « %s » par %s.", projet, acces, par)


def autorise(utilisateur: Utilisateur, acces: str) -> bool:
    """Le compte peut-il brancher un assistant sur ce projet ?"""
    if utilisateur.role is None:
        return False
    return acces == "membres" or (acces == "admin" and utilisateur.admin)


def exiger_autorise(conn: sqlite3.Connection, utilisateur: Utilisateur, projet: str) -> None:
    acces = get_acces(conn, projet)
    if acces == "ferme":
        raise AccesRefuse("L'accès par un assistant IA n'est pas ouvert sur ce projet.")
    if not autorise(utilisateur, acces):
        raise AccesRefuse("L'accès par un assistant IA est réservé aux administrateurs du projet.")


def _maintenant() -> str:
    return authentification.horodatage(authentification.maintenant())


def create_jeton(conn: sqlite3.Connection, utilisateur: Utilisateur, projet: str, nom: str) -> dict:
    """Nouveau jeton du compte pour ce projet ; le jeton en clair n'est rendu qu'ici."""
    if utilisateur.id is None:
        raise ErreurMetier("Mode local : aucun jeton n'est nécessaire sur ce poste.", 409)
    exiger_autorise(conn, utilisateur, projet)
    nom = nom.strip()
    if not nom:
        raise ErreurMetier("Donner un nom au jeton, par exemple celui de l'ordinateur.")
    jeton = PREFIXE_JETON + authentification.nouveau_jeton()
    with db.transaction(conn):
        curseur = conn.execute(
            "INSERT INTO jeton_api (utilisateur_id, projet, nom, empreinte) VALUES (?, ?, ?, ?)",
            (utilisateur.id, projet, nom, authentification.empreinte_jeton(jeton)),
        )
    journal_log.info("Jeton MCP « %s » créé pour %s sur %s.", nom, utilisateur.nom, projet)
    return {"id": curseur.lastrowid, "nom": nom, "jeton": jeton}


def list_jetons(conn: sqlite3.Connection, utilisateur: Utilisateur, projet: str) -> list[dict]:
    """Jetons actifs : les siens, ou tous ceux du projet pour l'administrateur."""
    requete = (
        "SELECT j.id, j.nom, j.cree_le, j.dernier_usage, u.nom AS proprietaire,"
        " j.utilisateur_id = ? AS a_moi"
        " FROM jeton_api j JOIN utilisateur u ON u.id = j.utilisateur_id"
        " WHERE j.projet = ? AND j.revoque_le IS NULL"
    )
    params: tuple = (utilisateur.id, projet)
    if not utilisateur.admin:
        requete += " AND j.utilisateur_id = ?"
        params = (*params, utilisateur.id)
    lignes = db.fetch_all(conn, requete + " ORDER BY j.cree_le DESC, j.id DESC", params)
    return [{**ligne, "a_moi": bool(ligne["a_moi"])} for ligne in lignes]


def revoke_jeton(
    conn: sqlite3.Connection, utilisateur: Utilisateur, projet: str, identifiant: int
) -> None:
    """Révoque un jeton : le sien, ou n'importe lequel du projet pour l'administrateur."""
    ligne = db.fetch_one(
        conn,
        "SELECT utilisateur_id FROM jeton_api WHERE id = ? AND projet = ? AND revoque_le IS NULL",
        (identifiant, projet),
    )
    if ligne is None:
        raise Introuvable("Jeton introuvable ou déjà révoqué.")
    if ligne["utilisateur_id"] != utilisateur.id and not utilisateur.admin:
        raise AccesRefuse("Seul son propriétaire ou un administrateur révoque ce jeton.")
    with db.transaction(conn):
        conn.execute(
            "UPDATE jeton_api SET revoque_le = ? WHERE id = ?", (_maintenant(), identifiant)
        )
    journal_log.info("Jeton MCP %d révoqué par %s.", identifiant, utilisateur.nom)


def authentifier(conn: sqlite3.Connection, jeton: str, projet: str) -> int | None:
    """Compte d'un jeton valable sur ce projet, ou None (jeton inconnu, révoqué, d'un autre
    projet, compte désactivé, accès fermé ou plus autorisé pour ce compte)."""
    if not jeton.startswith(PREFIXE_JETON):
        return None
    ligne = db.fetch_one(
        conn,
        "SELECT j.id, j.utilisateur_id FROM jeton_api j JOIN utilisateur u"
        " ON u.id = j.utilisateur_id"
        " WHERE j.empreinte = ? AND j.projet = ? AND j.revoque_le IS NULL AND u.actif = 1",
        (authentification.empreinte_jeton(jeton), projet),
    )
    if ligne is None:
        return None
    utilisateur = comptes.get_utilisateur(conn, ligne["utilisateur_id"], projet)
    if not autorise(utilisateur, get_acces(conn, projet)):
        return None
    with db.transaction(conn):
        conn.execute(
            "UPDATE jeton_api SET dernier_usage = ? WHERE id = ?",
            (_maintenant(), ligne["id"]),
        )
    return int(ligne["utilisateur_id"])
