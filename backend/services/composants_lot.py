"""Modifications en masse depuis la liste des composants : champs, caractéristiques, affectation.

Toujours en deux temps : un aperçu (`simuler`), qui compte ce qui change, ce qui est déjà à
jour et ce qui est refusé avec sa raison, puis l'application, tout ou rien. L'aperçu exécute
réellement chaque modification dans une transaction annulée à la fin : il rencontre les mêmes
refus que l'application (droits par bloc, champs obligatoires, valeurs). Chaque composant est
isolé par un point de reprise : son refus n'entraîne pas les autres dans l'aperçu.
"""

import sqlite3
from collections.abc import Callable
from typing import Any

from backend.erreurs import ErreurMetier
from backend.services import attributs, composants, droits, ensembles


def _uniques(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def _isoler(conn: sqlite3.Connection, action: Callable[[], Any]) -> tuple[Any, str | None]:
    """Exécute `action` sous un point de reprise ; renvoie (résultat, raison du refus)."""
    conn.execute("SAVEPOINT lot")
    try:
        resultat = action()
    except (ErreurMetier, sqlite3.IntegrityError) as erreur:
        conn.execute("ROLLBACK TO lot")
        conn.execute("RELEASE lot")
        return None, str(erreur)
    conn.execute("RELEASE lot")
    return resultat, None


def _executer(conn: sqlite3.Connection, simuler: bool, traiter: Callable[[], dict]) -> dict:
    """Ouvre la transaction et traite ; valide si on applique et que rien n'est refusé."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        recap = traiter()
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    recap["applique"] = not simuler and not recap["refuses"]
    conn.execute("COMMIT" if recap["applique"] else "ROLLBACK")
    return recap


def _etat(conn: sqlite3.Connection, identifiant: str, champs: list[str]) -> dict[str, Any]:
    """Valeurs comparées avant et après : champs modifiés et caractéristiques."""
    fiche = composants.get_composant(conn, identifiant)
    valeurs = attributs.get_valeurs(conn, identifiant)
    return {
        **{champ: fiche[champ] for champ in champs},
        **{f"{attributs.PREFIXE_CHAMP}{c}": v for c, v in valeurs.items()},
    }


def _ecarts(identifiant: str, avant: dict, apres: dict) -> list[dict]:
    champs = dict.fromkeys([*avant, *apres])
    return [
        {"id": identifiant, "champ": champ, "avant": avant.get(champ), "apres": apres.get(champ)}
        for champ in champs
        if avant.get(champ) != apres.get(champ)
    ]


def _valider_valeurs(conn: sqlite3.Connection, modifications: dict[str, Any]) -> None:
    """Une valeur de liste inconnue ou désactivée refuse toute la demande, avant tout essai."""
    composants.check_listes_saisies(conn, {k: v for k, v in modifications.items() if v is not None})


def modifier_lot(
    conn: sqlite3.Connection,
    utilisateur: droits.Utilisateur,
    ids: list[str],
    modifications: dict[str, Any],
    caracteristiques: dict[str, Any],
    simuler: bool,
) -> dict:
    """Pose les mêmes champs et caractéristiques sur chaque composant de la sélection."""
    if not modifications and not caracteristiques:
        raise ErreurMetier("Aucun champ à modifier : choisir au moins une valeur.")
    _valider_valeurs(conn, modifications)
    champs = list(modifications)

    def traiter() -> dict:
        recap: dict[str, Any] = {"changent": [], "a_jour": [], "refuses": [], "detail": []}
        for identifiant in _uniques(ids):

            def un(identifiant: str = identifiant) -> tuple[bool, list[dict]]:
                droits.exiger_composant(conn, utilisateur, identifiant)
                avant = _etat(conn, identifiant, champs)
                actuel = composants.get_composant(conn, identifiant)
                change = composants.modifier_composant(
                    conn, actuel, dict(modifications), dict(caracteristiques)
                )
                return change, _ecarts(identifiant, avant, _etat(conn, identifiant, champs))

            resultat, raison = _isoler(conn, un)
            if raison is not None:
                recap["refuses"].append({"id": identifiant, "raison": raison})
            elif resultat[0]:
                recap["changent"].append(identifiant)
                recap["detail"].extend(resultat[1])
            else:
                recap["a_jour"].append(identifiant)
        return recap

    return _executer(conn, simuler, traiter)


def affecter_lot(
    conn: sqlite3.Connection,
    utilisateur: droits.Utilisateur,
    ids: list[str],
    ensemble_code: str,
    qte: int | None,
    simuler: bool,
) -> dict:
    """Affecte chaque composant à l'ensemble : quantité fixe, ou son besoin si `qte` est vide.

    Un composant déjà affecté à cet ensemble garde son affectation telle quelle.
    """
    ensembles.verifier_ensemble(conn, ensemble_code)

    def traiter() -> dict:
        recap: dict[str, Any] = {"nouvelles": [], "deja": [], "refuses": []}
        for identifiant in _uniques(ids):

            def un(identifiant: str = identifiant) -> bool:
                droits.exiger_composant(conn, utilisateur, identifiant)
                fiche = composants.get_composant(conn, identifiant)
                if conn.execute(
                    "SELECT 1 FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
                    (ensemble_code, identifiant),
                ).fetchone():
                    return False
                quantite = qte if qte is not None else fiche["qte_besoin"]
                if quantite <= 0:
                    raise ErreurMetier(
                        "besoin nul : choisir une quantité fixe pour affecter ce composant."
                    )
                valeurs = {"composant_id": identifiant, "qte": quantite}
                ensembles.insert_affectation(conn, ensemble_code, valeurs)
                return True

            nouvelle, raison = _isoler(conn, un)
            if raison is not None:
                recap["refuses"].append({"id": identifiant, "raison": raison})
            else:
                recap["nouvelles" if nouvelle else "deja"].append(identifiant)
        return recap

    return _executer(conn, simuler, traiter)
