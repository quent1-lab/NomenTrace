"""Fournisseurs. Le nom est la clé ; un renommage se propage par ON UPDATE CASCADE."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, Introuvable
from backend.services import journal
from backend.services.import_colonnes import normaliser_entete

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {
        "nom",
        "type",
        "base_prix_defaut",
        "pays",
        "site_web",
        "numero_compte",
        "categorie",
        "contact",
        "delai_moyen_j",
        "commentaire",
        "statut",
    }
)


def list_fournisseurs(conn: sqlite3.Connection) -> list[dict]:
    """Renvoie les fournisseurs non archivés, triés par nom, avec leur nombre d'usages."""
    return db.fetch_all(
        conn,
        "SELECT f.*,"
        " (SELECT COUNT(*) FROM composant c WHERE c.fournisseur_nom = f.nom AND c.archive = 0)"
        " AS nb_composants,"
        " (SELECT COUNT(*) FROM commande m WHERE m.fournisseur_nom = f.nom AND m.archive = 0)"
        " AS nb_commandes"
        " FROM fournisseur f WHERE f.archive = 0 ORDER BY f.nom COLLATE NOCASE",
    )


def get_fournisseur(conn: sqlite3.Connection, nom: str) -> dict:
    """Renvoie un fournisseur."""
    fournisseur = db.fetch_one(conn, "SELECT * FROM fournisseur WHERE nom = ?", (nom,))
    if fournisseur is None:
        raise Introuvable(f"Fournisseur « {nom} » introuvable.")
    return fournisseur


def get_fiche(conn: sqlite3.Connection, nom: str) -> dict:
    """Fiche d'un fournisseur, archivé compris, avec ses composants et ses commandes."""
    fournisseur = get_fournisseur(conn, nom)
    fournisseur["composants"] = db.fetch_all(
        conn,
        "SELECT id, bloc_code, designation, ref_fabricant, qte_a_acheter, pu_ht, total_ht,"
        " avancement FROM v_composant WHERE fournisseur_nom = ? ORDER BY id",
        (nom,),
    )
    fournisseur["commandes"] = db.fetch_all(
        conn,
        "SELECT numero, type, statut, date_commande, livraison_annoncee, total_ht, engagee"
        " FROM v_commande WHERE fournisseur_nom = ? AND archive = 0 ORDER BY numero DESC",
        (nom,),
    )
    return fournisseur


def _homonyme(conn: sqlite3.Connection, nom: str) -> str | None:
    """Fournisseur actif dont le nom ne diffère que par la casse, les espaces ou la ponctuation."""
    cle = normaliser_entete(nom)
    for (autre,) in conn.execute("SELECT nom FROM fournisseur WHERE archive = 0").fetchall():
        if normaliser_entete(autre) == cle:
            return autre
    return None


def create_fournisseur(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un fournisseur ; refuse un nom déjà pris, réactive un fournisseur archivé.

    Un fournisseur déjà validé et réactivé le reste, même demandé « à valider ».
    """
    nom = valeurs["nom"]
    with db.transaction(conn):
        homonyme = _homonyme(conn, nom)
        if homonyme is not None:
            raise Conflit(f"Le fournisseur « {homonyme} » existe déjà.")
        existant = db.fetch_one(conn, "SELECT statut FROM fournisseur WHERE nom = ?", (nom,))
        if existant is not None:
            renseignes = {cle: v for cle, v in valeurs.items() if v is not None and cle != "nom"}
            if existant["statut"] == "Valide":
                renseignes.pop("statut", None)
            journal.update_with_journal(
                conn,
                "fournisseur",
                nom,
                {**renseignes, "archive": 0},
                CHAMPS_MODIFIABLES | {"archive"},
            )
        else:
            db.insert_row(conn, "fournisseur", valeurs)
            journal.write_journal(conn, "fournisseur", nom, "creation", None, "créé")
    return get_fournisseur(conn, nom)


def patch_fournisseur(conn: sqlite3.Connection, nom: str, modifications: dict[str, Any]) -> dict:
    """Modifie un fournisseur, y compris son nom."""
    nouveau_nom = modifications.get("nom", nom)
    with db.transaction(conn):
        if nouveau_nom != nom and db.fetch_one(
            conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (nouveau_nom,)
        ):
            raise Conflit(f"Le fournisseur « {nouveau_nom} » existe déjà.")
        journal.update_with_journal(conn, "fournisseur", nom, modifications, CHAMPS_MODIFIABLES)
    return get_fournisseur(conn, nouveau_nom)


def archive_fournisseur(conn: sqlite3.Connection, nom: str) -> None:
    """Archive un fournisseur : il disparaît des listes, les composants qui le citent le gardent."""
    with db.transaction(conn):
        get_fournisseur(conn, nom)
        journal.update_with_journal(
            conn, "fournisseur", nom, {"archive": 1}, frozenset({"archive"})
        )


def ensure_fournisseur(conn: sqlite3.Connection, nom: str | None) -> None:
    """Vérifie qu'un fournisseur désigné existe et n'est pas archivé."""
    if nom is None:
        return
    ligne = db.fetch_one(conn, "SELECT archive FROM fournisseur WHERE nom = ?", (nom,))
    if ligne is None or ligne["archive"]:
        raise Introuvable(f"Fournisseur « {nom} » introuvable.")
