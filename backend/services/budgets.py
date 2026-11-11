"""Budgets saisis en HT ou en TTC selon l'organisme ; toujours stockés et calculés en HT.

Un organisme choisit l'unité de saisie de ses budgets (`organisme.saisie_budget`). Un budget
saisi en TTC est converti en HT au taux de TVA par défaut du projet ou du dossier (celui des
paramètres communs), une seule fois, à l'écriture ; l'équivalent TTC affiché est recalculé
du HT au même taux. Aucun arrondi ici : il se fait à la réponse de l'API.
"""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import parametres, reference
from backend.services.projets import Registre

SAISIES: tuple[str, ...] = ("HT", "TTC")


def en_ht(ttc: float, taux: float) -> float:
    return ttc / (1 + taux)


def en_ttc(ht: float | None, taux: float) -> float | None:
    return None if ht is None else ht * (1 + taux)


def taux_du_projet(base: Any) -> float:
    conn = db.connect(base, creer=False)
    try:
        return parametres.get_taux_tva_defaut(conn)
    finally:
        conn.close()


def taux_du_dossier(registre: Registre, dossier: str) -> float:
    """Taux de TVA par défaut des paramètres communs du dossier (0,2 s'ils sont hors ligne)."""
    ref = registre.projets.get(reference.code_reference(dossier))
    return taux_du_projet(ref.base) if ref is not None else 0.2


def taux_pour_projet(conn: sqlite3.Connection, registre: Registre, code: str) -> float:
    """Taux d'un projet : celui de son dossier s'il est rangé (imposé), sinon le sien."""
    ligne = db.fetch_one(conn, "SELECT dossier FROM projet WHERE code = ?", (code,))
    if ligne and ligne["dossier"]:
        return taux_du_dossier(registre, ligne["dossier"])
    emp = registre.projets.get(code)
    return taux_du_projet(emp.base) if emp is not None else 0.2


def avec_ttc(conn: sqlite3.Connection, valeurs: dict) -> dict:
    """Paramètres d'un projet, avec l'équivalent TTC de son budget (taux par défaut)."""
    budget = valeurs.get("budget_ht")
    taux = parametres.get_taux_tva_defaut(conn)
    return {**valeurs, "budget_ttc": en_ttc(None if budget is None else float(budget), taux)}


def saisie_du_dossier(conn: sqlite3.Connection, dossier: str | None) -> str:
    if dossier is None:
        return "HT"
    ligne = db.fetch_one(
        conn,
        "SELECT o.saisie_budget FROM dossier d JOIN organisme o ON o.code = d.organisme"
        " WHERE d.code = ?",
        (dossier,),
    )
    return ligne["saisie_budget"] if ligne else "HT"


def convertir(modifs: dict[str, Any], taux: float, cle_ht: str = "budget_ht") -> dict[str, Any]:
    """Remplace `budget_ttc` par son équivalent HT sous `cle_ht` ; refuse les deux à la fois."""
    if "budget_ttc" not in modifs:
        return modifs
    if cle_ht in modifs:
        raise ErreurMetier("Donner le budget en HT ou en TTC, pas les deux.")
    resultat = {k: v for k, v in modifs.items() if k != "budget_ttc"}
    ttc = modifs["budget_ttc"]
    resultat[cle_ht] = None if ttc is None else en_ht(ttc, taux)
    return resultat
