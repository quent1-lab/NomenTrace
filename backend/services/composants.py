"""Composants : liste filtrée, fiche, création avec identifiant généré, modification, archivage."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import fournisseurs, journal, listes, parametres

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {
        "fonction",
        "designation",
        "mode_appro",
        "qte_besoin",
        "ref_fabricant",
        "fabricant",
        "fournisseur_nom",
        "lien_produit",
        "qte_rechange",
        "qte_disponible",
        "pu_releve",
        "base_prix_releve",
        "taux_tva",
        "statut_choix",
        "statut_appro",
        "criticite",
        "origine_exigence",
        "note_technique",
    }
)

# Colonnes de v_composant autorisées pour le tri : seule tolérance d'interpolation SQL.
COLONNES_TRI: frozenset[str] = frozenset(
    {
        "id",
        "bloc_code",
        "fonction",
        "designation",
        "ref_fabricant",
        "mode_appro",
        "fournisseur_nom",
        "qte_a_acheter",
        "qte_affectee",
        "pu_ht",
        "total_ht",
        "statut_choix",
        "statut_appro",
        "criticite",
        "avancement",
        "stock_actuel",
    }
)


@dataclass
class FiltresComposants:
    """Filtres cumulables de la liste des composants."""

    bloc: str | None = None
    ensemble: str | None = None
    mode_appro: str | None = None
    statut_appro: str | None = None
    statut_choix: str | None = None
    criticite: str | None = None
    fournisseur: str | None = None
    a_chiffrer: bool = False
    non_affecte: bool = False
    ecart_affectation: bool = False
    q: str | None = None
    tri: str = "id"
    ordre: str = "asc"


def _where(filtres: FiltresComposants) -> tuple[str, list[Any]]:
    """Construit la clause WHERE à partir de fragments fixes et de paramètres liés."""
    clauses: list[str] = []
    params: list[Any] = []
    egalites = {
        "bloc_code": filtres.bloc,
        "mode_appro": filtres.mode_appro,
        "statut_appro": filtres.statut_appro,
        "statut_choix": filtres.statut_choix,
        "criticite": filtres.criticite,
        "fournisseur_nom": filtres.fournisseur,
    }
    for colonne, valeur in egalites.items():
        if valeur is not None:
            clauses.append(f"{colonne} = ?")
            params.append(valeur)
    if filtres.ensemble is not None:
        clauses.append("id IN (SELECT composant_id FROM affectation WHERE ensemble_code = ?)")
        params.append(filtres.ensemble)
    if filtres.a_chiffrer:
        clauses.append("a_chiffrer = 1")
    if filtres.non_affecte:
        clauses.append("qte_affectee = 0")
    if filtres.ecart_affectation:
        clauses.append("nb_ensembles > 0 AND ecart_affectation <> 0")
    if filtres.q:
        clauses.append(
            "(id LIKE ? OR fonction LIKE ? OR designation LIKE ? OR ref_fabricant LIKE ?"
            " OR fabricant LIKE ?)"
        )
        params.extend([f"%{filtres.q}%"] * 5)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_composants(conn: sqlite3.Connection, filtres: FiltresComposants) -> list[dict]:
    """Renvoie les composants de v_composant correspondant à tous les filtres."""
    if filtres.tri not in COLONNES_TRI:
        raise ErreurMetier(f"Tri impossible sur « {filtres.tri} ».")
    if filtres.ordre not in ("asc", "desc"):
        raise ErreurMetier("L'ordre de tri doit valoir « asc » ou « desc ».")
    where, params = _where(filtres)
    sql = (
        f"SELECT * FROM v_composant{where}"  # noqa: S608
        f" ORDER BY {filtres.tri} IS NULL, {filtres.tri} {filtres.ordre.upper()}, id"
    )
    return db.fetch_all(conn, sql, tuple(params))


def get_composant(conn: sqlite3.Connection, identifiant: str) -> dict:
    """Renvoie un composant non archivé tel que calculé par v_composant."""
    composant = db.fetch_one(conn, "SELECT * FROM v_composant WHERE id = ?", (identifiant,))
    if composant is None:
        raise Introuvable(f"Composant « {identifiant} » introuvable ou archivé.")
    return composant


def get_fiche(conn: sqlite3.Connection, identifiant: str) -> dict:
    """Renvoie la fiche complète : composant, affectations, commandes, mouvements, journal."""
    composant = get_composant(conn, identifiant)
    cle = (identifiant,)
    return {
        "composant": composant,
        "affectations": db.fetch_all(
            conn,
            "SELECT * FROM v_ensemble_composant WHERE composant_id = ? ORDER BY ensemble_code",
            cle,
        ),
        "lignes_commande": db.fetch_all(
            conn,
            "SELECT l.*, c.type, c.statut, c.fournisseur_nom, c.date_commande"
            " FROM ligne_commande l JOIN commande c ON c.numero = l.commande_numero"
            " WHERE l.composant_id = ? AND c.archive = 0 ORDER BY l.id",
            cle,
        ),
        "mouvements": db.fetch_all(
            conn, "SELECT * FROM mouvement_stock WHERE composant_id = ? ORDER BY date, id", cle
        ),
        "journal": db.fetch_all(
            conn,
            "SELECT j.*, l.nom_fichier FROM journal j LEFT JOIN import_lot l ON l.id = j.lot_id"
            " WHERE (j.table_cible = 'composant' AND j.cle_cible = ?)"
            " OR (j.table_cible = 'affectation' AND j.cle_cible LIKE '%:' || ?) ORDER BY j.id DESC",
            (identifiant, identifiant),
        ),
    }


def next_id(conn: sqlite3.Connection, bloc_code: str) -> str:
    """Prochain identifiant du bloc : plus grand numéro existant plus un, archivés compris."""
    racine = f"{parametres.get_prefixe_id(conn)}-{bloc_code}-"
    numeros = [0]
    for (identifiant,) in conn.execute(
        "SELECT id FROM composant WHERE bloc_code = ?", (bloc_code,)
    ).fetchall():
        suffixe = identifiant[len(racine) :] if identifiant.startswith(racine) else ""
        if suffixe.isdigit():
            numeros.append(int(suffixe))
    return f"{racine}{max(numeros) + 1:03d}"


CHAMPS_LISTES: tuple[str, ...] = ("mode_appro", "statut_appro", "statut_choix", "criticite")


def _check_listes(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> None:
    """Chaque valeur de liste saisie doit exister et être active."""
    for champ in CHAMPS_LISTES:
        if champ in valeurs:
            listes.check_valeur(conn, champ, valeurs[champ])


def _ensure_bloc(conn: sqlite3.Connection, code: str) -> None:
    if db.fetch_one(conn, "SELECT 1 FROM bloc WHERE code = ?", (code,)) is None:
        raise Introuvable(f"Bloc « {code} » introuvable.")


def preview_id(conn: sqlite3.Connection, bloc_code: str) -> str:
    """Identifiant qu'aurait un composant créé maintenant dans ce bloc (indicatif)."""
    _ensure_bloc(conn, bloc_code)
    return next_id(conn, bloc_code)


def insert_composant(
    conn: sqlite3.Connection,
    valeurs: dict[str, Any],
    origine: str = journal.ORIGINE_INTERFACE,
    lot_id: int | None = None,
) -> str:
    """Insère un composant avec un identifiant généré. À appeler dans une transaction."""
    _ensure_bloc(conn, valeurs["bloc_code"])
    _check_listes(conn, valeurs)
    fournisseurs.ensure_fournisseur(conn, valeurs.get("fournisseur_nom"))
    if valeurs.get("taux_tva") is None:
        valeurs = {**valeurs, "taux_tva": parametres.get_taux_tva_defaut(conn)}
    identifiant = next_id(conn, valeurs["bloc_code"])
    db.insert_row(conn, "composant", {"id": identifiant, **valeurs})
    journal.write_journal(conn, "composant", identifiant, "creation", None, "créé", origine, lot_id)
    return identifiant


def create_composant(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un composant ; l'identifiant est généré et inséré dans la même transaction."""
    with db.transaction(conn, immediate=True):
        identifiant = insert_composant(conn, valeurs)
    return get_composant(conn, identifiant)


def patch_composant(
    conn: sqlite3.Connection, identifiant: str, modifications: dict[str, Any]
) -> dict:
    """Modifie un composant non archivé, champ par champ, avec journal."""
    with db.transaction(conn):
        actuel = get_composant(conn, identifiant)
        # Une valeur désactivée déjà portée par le composant reste acceptée telle quelle.
        _check_listes(
            conn, {k: v for k, v in modifications.items() if k in CHAMPS_LISTES and v != actuel[k]}
        )
        if "fournisseur_nom" in modifications:
            fournisseurs.ensure_fournisseur(conn, modifications["fournisseur_nom"])
        changes = journal.update_with_journal(
            conn, "composant", identifiant, modifications, CHAMPS_MODIFIABLES
        )
        if changes:
            conn.execute(
                "UPDATE composant SET modifie_le = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), identifiant),
            )
    return get_composant(conn, identifiant)


def archive_composant(conn: sqlite3.Connection, identifiant: str) -> None:
    """Archive un composant : il disparaît des listes mais reste en base."""
    with db.transaction(conn):
        get_composant(conn, identifiant)
        journal.update_with_journal(
            conn, "composant", identifiant, {"archive": 1}, frozenset({"archive"})
        )
