"""Composants : liste filtrée, fiche, création avec identifiant généré, modification, archivage."""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import (
    attributs,
    attributs_requetes,
    fournisseurs,
    historique,
    journal,
    listes,
    parametres,
)

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
    # Par défaut, un ensemble inclut ses sous-ensembles ; vrai = ses affectations seules.
    ensemble_seul: bool = False
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
    # Filtres d'attribut « code:operation[:valeur] », renseignés par la route (paramètre
    # répété ?attr=…) : hors du constructeur pour que FastAPI ne les lise pas comme un corps.
    attr: list[str] = field(default_factory=list, init=False)


def _where(conn: sqlite3.Connection, filtres: FiltresComposants) -> tuple[str, list[Any]]:
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
    if filtres.ensemble is not None and filtres.ensemble_seul:
        clauses.append("id IN (SELECT composant_id FROM affectation WHERE ensemble_code = ?)")
        params.append(filtres.ensemble)
    elif filtres.ensemble is not None:
        clauses.append(
            "id IN (SELECT a.composant_id FROM affectation a"
            " JOIN v_ensemble_descendant d ON d.code = a.ensemble_code WHERE d.ancetre_code = ?)"
        )
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
    clauses_attr, params_attr = attributs_requetes.build_filtres(conn, filtres.attr)
    clauses.extend(clauses_attr)
    params.extend(params_attr)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_composants(conn: sqlite3.Connection, filtres: FiltresComposants) -> list[dict]:
    """Renvoie les composants de v_composant correspondant à tous les filtres.

    Chaque composant porte ses valeurs d'attributs ({code: valeur}) sous « attributs ».
    Le tri « attr:code » trie sur un attribut, après vérification du code.
    """
    if filtres.ordre not in ("asc", "desc"):
        raise ErreurMetier("L'ordre de tri doit valoir « asc » ou « desc ».")
    source, params_source, tri = "v_composant", [], filtres.tri
    if filtres.tri.startswith(attributs.PREFIXE_CHAMP):
        code = filtres.tri.removeprefix(attributs.PREFIXE_CHAMP)
        source, params_source = attributs_requetes.build_tri(conn, code)
        tri = "_tri"
    elif filtres.tri not in COLONNES_TRI:
        raise ErreurMetier(f"Tri impossible sur « {filtres.tri} ».")
    where, params = _where(conn, filtres)
    sql = (
        f"SELECT * FROM {source}{where}"  # noqa: S608
        f" ORDER BY {tri} IS NULL, {tri} {filtres.ordre.upper()}, id"
    )
    lignes = db.fetch_all(conn, sql, (*params_source, *params))
    valeurs = attributs.valeurs_par_composant(conn)
    for ligne in lignes:
        ligne.pop("_tri", None)
        ligne["attributs"] = valeurs.get(ligne["id"], {})
    return lignes


def get_composant(conn: sqlite3.Connection, identifiant: str) -> dict:
    """Renvoie un composant non archivé tel que calculé par v_composant."""
    composant = db.fetch_one(conn, "SELECT * FROM v_composant WHERE id = ?", (identifiant,))
    if composant is None:
        raise Introuvable(f"Composant « {identifiant} » introuvable ou archivé.")
    return composant


def get_existant(conn: sqlite3.Connection, identifiant: str) -> dict:
    """Renvoie la ligne brute d'un composant, archivé compris."""
    composant = db.fetch_one(conn, "SELECT * FROM composant WHERE id = ?", (identifiant,))
    if composant is None:
        raise Introuvable(f"Composant « {identifiant} » introuvable.")
    return composant


def get_fiche(conn: sqlite3.Connection, identifiant: str) -> dict:
    """Renvoie la fiche complète : composant, affectations, commandes, mouvements, journal.

    Un composant archivé garde une fiche en lecture seule : c'est son historique (celui d'un
    composant reclassé dans un autre bloc, par exemple). `remplace` liste les composants
    archivés que celui-ci remplace.
    """
    composant = db.fetch_one(conn, "SELECT * FROM v_composant WHERE id = ?", (identifiant,))
    affectations_sql = (
        "SELECT * FROM v_ensemble_composant WHERE composant_id = ? ORDER BY ensemble_code"
    )
    if composant is None:
        composant = get_existant(conn, identifiant)
        affectations_sql = (
            "SELECT a.id AS affectation_id, a.ensemble_code, e.nom AS ensemble_nom,"
            " a.qte AS qte_affectee FROM affectation a JOIN ensemble e ON e.code = a.ensemble_code"
            " WHERE a.composant_id = ? ORDER BY a.ensemble_code"
        )
    cle = (identifiant,)
    return {
        "composant": composant,
        "remplace": [
            ligne["id"]
            for ligne in db.fetch_all(
                conn, "SELECT id FROM composant WHERE remplace_par = ? ORDER BY id", cle
            )
        ],
        "attributs": attributs.get_valeurs(conn, identifiant),
        "affectations": db.fetch_all(conn, affectations_sql, cle),
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
        "historique": historique.list_evenements_composant(conn, identifiant),
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


def ensure_bloc_ouvert(conn: sqlite3.Connection, code: str) -> None:
    """Un nouveau composant ne peut entrer que dans un bloc existant et non archivé."""
    bloc = db.fetch_one(conn, "SELECT archive FROM bloc WHERE code = ?", (code,))
    if bloc is None:
        raise Introuvable(f"Bloc « {code} » introuvable.")
    if bloc["archive"]:
        raise ErreurMetier(f"Le bloc « {code} » est archivé : il n'accepte plus de composant.")


def preview_id(conn: sqlite3.Connection, bloc_code: str) -> str:
    """Identifiant qu'aurait un composant créé maintenant dans ce bloc (indicatif)."""
    ensure_bloc_ouvert(conn, bloc_code)
    return next_id(conn, bloc_code)


def insert_composant(
    conn: sqlite3.Connection,
    valeurs: dict[str, Any],
    origine: str = journal.ORIGINE_INTERFACE,
    lot_id: int | None = None,
) -> str:
    """Insère un composant avec un identifiant généré. À appeler dans une transaction."""
    ensure_bloc_ouvert(conn, valeurs["bloc_code"])
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
    with db.transaction(conn):
        identifiant = insert_composant(conn, valeurs)
    return get_composant(conn, identifiant)


def patch_composant(
    conn: sqlite3.Connection, identifiant: str, modifications: dict[str, Any]
) -> dict:
    """Modifie un composant non archivé, champ par champ, avec journal.

    Si `modifie_le` est fourni et que le composant a été modifié depuis, rien n'est écrit :
    la modification de l'autre personne est signalée au lieu d'être écrasée.
    """
    modifications = dict(modifications)
    lu = modifications.pop("modifie_le", None)
    with db.transaction(conn):
        actuel = get_composant(conn, identifiant)
        if lu is not None and lu != actuel["modifie_le"]:
            raise Conflit(_message_conflit(conn, identifiant))
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


def _message_conflit(conn: sqlite3.Connection, identifiant: str) -> str:
    derniere = db.fetch_one(
        conn,
        "SELECT utilisateur, horodatage FROM journal WHERE table_cible = 'composant'"
        " AND cle_cible = ? ORDER BY id DESC LIMIT 1",
        (identifiant,),
    )
    auteur = f" par {derniere['utilisateur']}" if derniere and derniere["utilisateur"] else ""
    quand = f" à {derniere['horodatage'][11:16]}" if derniere else ""
    return (
        f"{identifiant} a été modifié{auteur}{quand} pendant votre saisie. Recharger la fiche"
        " pour voir sa version actuelle, puis refaire la modification."
    )


def patch_attributs(conn: sqlite3.Connection, identifiant: str, valeurs: dict[str, Any]) -> dict:
    """Enregistre les caractéristiques d'un composant non archivé ; None efface une valeur."""
    with db.transaction(conn):
        get_composant(conn, identifiant)
        if attributs.set_valeurs(conn, identifiant, valeurs):
            conn.execute(
                "UPDATE composant SET modifie_le = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), identifiant),
            )
    return attributs.get_valeurs(conn, identifiant)


def archive_composant(conn: sqlite3.Connection, identifiant: str) -> None:
    """Archive un composant : il disparaît des listes mais reste en base."""
    with db.transaction(conn):
        get_composant(conn, identifiant)
        journal.update_with_journal(
            conn, "composant", identifiant, {"archive": 1}, frozenset({"archive"})
        )
