"""Arborescence des ensembles et budgets d'ensemble.

La racine de l'arbre n'est pas stockée : c'est un nœud virtuel qui porte le nom du projet
et son budget (`parametre.budget_ht`). Les indicateurs propres et cumulés viennent des vues
`v_ensemble` et `v_ensemble_cumul`.

Le budget d'un ensemble, lui, est calculé ici et jamais stocké : la répartition récursive
se prête mal à une vue. C'est une exception à la règle « les calculs vivent dans des
vues », signalée dans docs/MODELE.md. Règle, appliquée à chaque niveau en partant de la
racine :
1. un enfant verrouillé garde son budget saisi ;
2. le reste du budget du parent est partagé à parts égales entre les enfants non
   verrouillés, vides ou non : on voit ainsi ce qu'il reste à chacun. La part propre du
   parent (ses affectations directes) compte pour une part s'il en a ;
3. si les verrouillés dépassent le budget du parent, les non verrouillés reçoivent 0 et le
   parent porte le dépassement.
Aucun arrondi : il se fait à la sortie de l'API.
"""

import sqlite3
from dataclasses import dataclass

from backend import db
from backend.erreurs import Introuvable
from backend.services import parametres

# Tolérance des comparaisons de montants.
TOLERANCE: float = 0.01


@dataclass(frozen=True)
class NoeudBudget:
    """Ce dont la répartition a besoin pour un ensemble."""

    code: str
    verrouille: bool
    budget_saisi: float | None


@dataclass(frozen=True)
class Repartition:
    """Résultat de la répartition du budget d'un nœud entre ses enfants et sa part propre."""

    parts: dict[str, float | None]
    propre: float | None
    depassement: float | None


def repartir_budget(
    budget: float | None,
    enfants: list[NoeudBudget],
    propre_eligible: bool,
) -> Repartition:
    """Répartit le budget d'un nœud, à parts égales, entre ses enfants et sa part propre.

    `propre_eligible` : le nœud porte des affectations directes, sa part propre compte donc
    pour une part. Sans budget connu, seuls les verrouillés en ont un.
    """
    parts: dict[str, float | None] = {
        e.code: e.budget_saisi for e in enfants if e.verrouille and e.budget_saisi is not None
    }
    libres = [e for e in enfants if e.code not in parts]
    if budget is None:
        parts.update({e.code: None for e in libres})
        return Repartition(parts, None, None)
    reste = budget - sum(v for v in parts.values() if v is not None)
    if reste < -TOLERANCE:
        parts.update({e.code: 0.0 for e in libres})
        return Repartition(parts, 0.0, -reste)
    reste = max(reste, 0.0)
    nb_parts = len(libres) + (1 if propre_eligible else 0)
    parts.update({e.code: reste / nb_parts for e in libres})
    propre = reste - sum(parts[e.code] or 0.0 for e in libres)
    return Repartition(parts, max(propre, 0.0), None)


def _budget_projet(conn: sqlite3.Connection) -> float | None:
    valeur = parametres.get_parametre(conn, "budget_ht")
    return float(valeur) if valeur not in (None, "") else None


def _charger(conn: sqlite3.Connection) -> dict[str, dict]:
    """Ensembles non archivés, indicateurs propres à plat et cumulés sous « cumul »."""
    noeuds = {e["code"]: e for e in db.fetch_all(conn, "SELECT * FROM v_ensemble")}
    for cumul in db.fetch_all(conn, "SELECT * FROM v_ensemble_cumul"):
        code = cumul.pop("code")
        noeuds[code]["nb_sous_ensembles"] = cumul.pop("nb_sous_ensembles")
        noeuds[code]["cumul"] = cumul
    return noeuds


def _enfants_par_parent(noeuds: dict[str, dict]) -> dict[str | None, list[dict]]:
    """Enfants de chaque nœud, triés par ordre ; None désigne la racine du projet."""
    enfants: dict[str | None, list[dict]] = {}
    for noeud in noeuds.values():
        parent = noeud["parent_code"] if noeud["parent_code"] in noeuds else None
        enfants.setdefault(parent, []).append(noeud)
    for liste in enfants.values():
        liste.sort(key=lambda n: (n["ordre"], n["code"]))
    return enfants


def _noeud_budget(noeud: dict) -> NoeudBudget:
    return NoeudBudget(
        code=noeud["code"],
        verrouille=bool(noeud["budget_verrouille"]),
        budget_saisi=noeud["budget_cible_ht"],
    )


def _poser_budgets(
    code: str | None,
    budget: float | None,
    noeuds: dict[str, dict],
    enfants: dict[str | None, list[dict]],
) -> Repartition:
    """Répartit le budget d'un nœud et descend dans ses enfants ; renvoie sa répartition."""
    propres = noeuds[code] if code is not None else None
    repartition = repartir_budget(
        budget,
        [_noeud_budget(e) for e in enfants.get(code, [])],
        bool(propres and propres["nb_composants_distincts"]),
    )
    for enfant in enfants.get(code, []):
        budget_enfant = repartition.parts[enfant["code"]]
        sous = _poser_budgets(enfant["code"], budget_enfant, noeuds, enfants)
        cout = enfant["cumul"]["cout_ht"]
        enfant.update(
            budget_ht=budget_enfant,
            budget_propre_ht=sous.propre,
            depassement_verrouille_ht=sous.depassement,
            ecart_budget_ht=None if budget_enfant is None else cout - budget_enfant,
        )
    return repartition


def _parcourir(
    parent: str | None,
    branche: str | None,
    enfants: dict[str | None, list[dict]],
    sortie: list[dict],
    niveau: int = 1,
) -> None:
    """Ordre d'affichage : parcours en profondeur, frères triés par ordre puis code.

    La branche est le code de l'ensemble de premier niveau dont descend le nœud.
    """
    for noeud in enfants.get(parent, []):
        noeud["niveau"] = niveau
        noeud["branche_code"] = branche or noeud["code"]
        sortie.append(noeud)
        _parcourir(noeud["code"], noeud["branche_code"], enfants, sortie, niveau + 1)


def get_arbre(conn: sqlite3.Connection) -> dict:
    """Racine virtuelle du projet et ensembles dans l'ordre de l'arbre, budgets compris."""
    noeuds = _charger(conn)
    enfants = _enfants_par_parent(noeuds)
    budget = _budget_projet(conn)
    repartition = _poser_budgets(None, budget, noeuds, enfants)
    ensembles: list[dict] = []
    _parcourir(None, None, enfants, ensembles)
    premiers = enfants.get(None, [])
    cout = sum(e["cumul"]["cout_ht"] for e in premiers)
    racine = {
        "nom": parametres.get_parametre(conn, "nom_projet"),
        "budget_ht": budget,
        "cout_ht": cout,
        "ecart_budget_ht": None if budget is None else cout - budget,
        "budget_non_reparti_ht": repartition.propre,
        "depassement_verrouille_ht": repartition.depassement,
        "nb_ensembles": len(ensembles),
        "nb_premier_niveau": len(premiers),
    }
    return {"racine": racine, "ensembles": ensembles}


def list_ensembles(conn: sqlite3.Connection) -> list[dict]:
    """Ensembles non archivés dans l'ordre de l'arbre, avec cumuls et budgets."""
    return get_arbre(conn)["ensembles"]


def get_ensemble(conn: sqlite3.Connection, code: str) -> dict:
    """Un ensemble non archivé avec cumuls, budget, chemin depuis la racine et enfants."""
    ensembles = list_ensembles(conn)
    par_code = {e["code"]: e for e in ensembles}
    ensemble = par_code.get(code)
    if ensemble is None:
        raise Introuvable(f"Ensemble « {code} » introuvable ou archivé.")
    chemin = []
    parent = par_code.get(ensemble["parent_code"])
    while parent is not None:
        chemin.insert(0, {"code": parent["code"], "nom": parent["nom"]})
        parent = par_code.get(parent["parent_code"])
    enfants = [e for e in ensembles if e["parent_code"] == code]
    return {**ensemble, "chemin": chemin, "enfants": enfants}


def list_descendants(conn: sqlite3.Connection, code: str) -> set[str]:
    """Codes des descendants non archivés d'un ensemble, lui exclu."""
    lignes = conn.execute(
        "SELECT code FROM v_ensemble_descendant WHERE ancetre_code = ? AND code <> ?",
        (code, code),
    ).fetchall()
    return {ligne[0] for ligne in lignes}
