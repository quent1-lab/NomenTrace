"""Ensembles physiques et affectations des composants."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import composants, ensembles_arbre, journal

CHAMPS_MODIFIABLES: frozenset[str] = frozenset(
    {
        "nom",
        "ordre",
        "description",
        "responsable",
        "statut_montage",
        "parent_code",
        "budget_cible_ht",
        "budget_verrouille",
    }
)
CHAMPS_AFFECTATION: frozenset[str] = frozenset({"qte", "commentaire"})


def list_repartition(conn: sqlite3.Connection, cumul: bool = False) -> list[dict]:
    """Répartition de chaque ensemble par bloc fonctionnel (coût, pièces, composants).

    `cumul` : l'ensemble et tous ses sous-ensembles, au lieu de ses affectations seules.
    """
    vue = "v_ensemble_bloc_cumul" if cumul else "v_ensemble_bloc"
    return db.fetch_all(
        conn,
        f"SELECT r.* FROM {vue} r JOIN bloc b ON b.code = r.bloc_code"  # noqa: S608
        " ORDER BY r.ensemble_code, b.ordre",
    )


def list_incoherences(conn: sqlite3.Connection) -> list[dict]:
    """Incohérences d'affectation, de commande et de montage."""
    return db.fetch_all(
        conn, "SELECT * FROM v_incoherence ORDER BY type, composant_id, ensemble_code"
    )


def verifier_ensemble(conn: sqlite3.Connection, code: str) -> dict:
    """Ligne d'un ensemble non archivé, pour les contrôles ; Introuvable sinon."""
    ligne = db.fetch_one(conn, "SELECT * FROM ensemble WHERE code = ? AND archive = 0", (code,))
    if ligne is None:
        raise Introuvable(f"Ensemble « {code} » introuvable ou archivé.")
    return ligne


def verifier_parent(conn: sqlite3.Connection, code: str, parent_code: str | None) -> None:
    """Refuse un parent inconnu, archivé, ou qui ferait de l'ensemble son propre descendant."""
    if parent_code is None:
        return
    parent = db.fetch_one(conn, "SELECT archive FROM ensemble WHERE code = ?", (parent_code,))
    if parent is None:
        raise ErreurMetier(f"L'ensemble parent « {parent_code} » n'existe pas.")
    if parent["archive"]:
        raise ErreurMetier(f"L'ensemble parent « {parent_code} » est archivé.")
    if parent_code == code or parent_code in ensembles_arbre.list_descendants(conn, code):
        raise Conflit(
            f"« {parent_code} » ne peut pas devenir le parent de « {code} » : c'est "
            f"{'lui-même' if parent_code == code else 'un de ses sous-ensembles'}, "
            "l'arborescence formerait une boucle."
        )


def _verifier_budget(valeurs: dict[str, Any]) -> None:
    """Un budget verrouillé fige une valeur saisie : elle est obligatoire."""
    if valeurs.get("budget_verrouille") and valeurs.get("budget_cible_ht") is None:
        raise ErreurMetier("Saisir un budget cible HT avant de verrouiller le budget.")


def _rang_modification(item: tuple[str, Any]) -> int:
    champ, valeur = item
    if champ != "budget_verrouille":
        return 1
    return 2 if valeur else 0


def create_ensemble(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un ensemble ; le code, fourni par l'utilisateur, doit être unique."""
    code = valeurs["code"]
    with db.transaction(conn):
        if db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ?", (code,)):
            raise Conflit(f"Le code d'ensemble « {code} » est déjà utilisé.")
        verifier_parent(conn, code, valeurs.get("parent_code"))
        _verifier_budget(valeurs)
        db.insert_row(conn, "ensemble", valeurs)
        journal.write_journal(conn, "ensemble", code, "creation", None, "créé")
    return ensembles_arbre.get_ensemble(conn, code)


def patch_ensemble(conn: sqlite3.Connection, code: str, modifications: dict[str, Any]) -> dict:
    """Modifie un ensemble ; son code n'est jamais modifiable."""
    with db.transaction(conn):
        actuel = verifier_ensemble(conn, code)
        if modifications.get("budget_verrouille", False) is None:
            del modifications["budget_verrouille"]
        if "parent_code" in modifications:
            verifier_parent(conn, code, modifications["parent_code"])
        _verifier_budget({**actuel, **modifications})
        # Le verrou se pose après le montant et se lève avant son effacement : la base
        # refuse à tout instant un budget verrouillé sans montant.
        ordonnees = dict(sorted(modifications.items(), key=_rang_modification))
        journal.update_with_journal(conn, "ensemble", code, ordonnees, CHAMPS_MODIFIABLES)
    return ensembles_arbre.get_ensemble(conn, code)


def archive_ensemble(conn: sqlite3.Connection, code: str) -> None:
    """Archive un ensemble, refusé tant qu'il porte des affectations ou des sous-ensembles."""
    with db.transaction(conn):
        verifier_ensemble(conn, code)
        nb = conn.execute(
            "SELECT COUNT(*) FROM affectation WHERE ensemble_code = ?", (code,)
        ).fetchone()[0]
        if nb:
            raise Conflit(
                f"L'ensemble « {code} » porte encore {nb} affectation(s) : retirez-les avant "
                "de l'archiver."
            )
        enfants = conn.execute(
            "SELECT COUNT(*) FROM ensemble WHERE parent_code = ? AND archive = 0", (code,)
        ).fetchone()[0]
        if enfants:
            raise Conflit(
                f"L'ensemble « {code} » a encore {enfants} sous-ensemble(s) : déplacez-les ou "
                "archivez-les avant de l'archiver."
            )
        journal.update_with_journal(conn, "ensemble", code, {"archive": 1}, frozenset({"archive"}))


def list_composants_ensemble(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Renvoie les composants affectés à un ensemble."""
    verifier_ensemble(conn, code)
    return db.fetch_all(
        conn,
        "SELECT ec.*, c.lien_produit FROM v_ensemble_composant ec"
        " JOIN composant c ON c.id = ec.composant_id"
        " WHERE ec.ensemble_code = ? ORDER BY ec.bloc_code, ec.composant_id",
        (code,),
    )


def _cle_affectation(ensemble_code: str, composant_id: str) -> str:
    return f"{ensemble_code}:{composant_id}"


def create_affectation(conn: sqlite3.Connection, code: str, valeurs: dict[str, Any]) -> dict:
    """Affecte un composant à un ensemble ; une seule affectation par couple."""
    composant_id = valeurs["composant_id"]
    with db.transaction(conn):
        verifier_ensemble(conn, code)
        composants.get_composant(conn, composant_id)
        if db.fetch_one(
            conn,
            "SELECT 1 FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
            (code, composant_id),
        ):
            raise Conflit(
                f"{composant_id} est déjà affecté à l'ensemble {code} : modifiez la quantité "
                "de l'affectation existante plutôt que d'en créer une seconde."
            )
        identifiant = db.insert_row(conn, "affectation", {"ensemble_code": code, **valeurs})
        journal.write_journal(
            conn, "affectation", _cle_affectation(code, composant_id), "qte", None, valeurs["qte"]
        )
    return get_affectation(conn, identifiant)


def get_affectation(conn: sqlite3.Connection, identifiant: int) -> dict:
    """Renvoie une affectation avec ses valeurs calculées."""
    ligne = db.fetch_one(
        conn, "SELECT * FROM v_ensemble_composant WHERE affectation_id = ?", (identifiant,)
    )
    if ligne is None:
        raise Introuvable(f"Affectation {identifiant} introuvable.")
    return ligne


def patch_affectation(
    conn: sqlite3.Connection, identifiant: int, modifications: dict[str, Any]
) -> dict:
    """Modifie la quantité ou le commentaire d'une affectation."""
    with db.transaction(conn):
        actuelle = get_affectation(conn, identifiant)
        journal.update_with_journal(
            conn,
            "affectation",
            identifiant,
            modifications,
            CHAMPS_AFFECTATION,
            cle_journal=_cle_affectation(actuelle["ensemble_code"], actuelle["composant_id"]),
        )
    return get_affectation(conn, identifiant)


def delete_affectation(conn: sqlite3.Connection, identifiant: int) -> None:
    """Supprime réellement une affectation : c'est un lien, pas une donnée tracée."""
    with db.transaction(conn):
        ligne = db.fetch_one(conn, "SELECT * FROM affectation WHERE id = ?", (identifiant,))
        if ligne is None:
            raise Introuvable(f"Affectation {identifiant} introuvable.")
        conn.execute("DELETE FROM affectation WHERE id = ?", (identifiant,))
        journal.write_journal(
            conn,
            "affectation",
            _cle_affectation(ligne["ensemble_code"], ligne["composant_id"]),
            "qte",
            ligne["qte"],
            None,
        )
