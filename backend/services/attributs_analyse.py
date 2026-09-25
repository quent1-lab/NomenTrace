"""Répartition des valeurs d'un attribut : composants, pièces et coût HT par valeur.

Générique : la tension n'est qu'un attribut parmi d'autres. Le calcul part de la vue
v_attribut_composant ; les filtres (bloc, ensemble, mode d'appro) sont des paramètres liés.
"""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import attributs


def get_repartition(
    conn: sqlite3.Connection, code: str, filtres: dict[str, str | None]
) -> dict[str, Any]:
    """Une ligne par valeur, plus « non renseigné » ; les nombres sont triés par valeur."""
    attribut = attributs.get_attribut(conn, code)
    lignes = db.fetch_all(
        conn,
        "SELECT valeur_texte, valeur_nombre,"
        " COUNT(*) AS nb_composants,"
        " TOTAL(qte_besoin) AS nb_pieces,"
        " TOTAL(total_ht) AS cout_ht"
        " FROM v_attribut_composant"
        " WHERE attribut_code = ?"
        " AND (? IS NULL OR bloc_code = ?)"
        " AND (? IS NULL OR mode_appro = ?)"
        " AND (? IS NULL OR composant_id IN"
        "      (SELECT composant_id FROM affectation WHERE ensemble_code = ?))"
        " GROUP BY valeur_texte, valeur_nombre",
        (
            code,
            filtres.get("bloc"),
            filtres.get("bloc"),
            filtres.get("mode_appro"),
            filtres.get("mode_appro"),
            filtres.get("ensemble"),
            filtres.get("ensemble"),
        ),
    )
    ordre_liste = {v["code"]: v["ordre"] for v in attribut["valeurs"]}
    libelles = {v["code"]: v["libelle"] for v in attribut["valeurs"]}
    valeurs, non_renseigne = [], None
    for ligne in lignes:
        valeur = (
            ligne["valeur_nombre"] if ligne["valeur_nombre"] is not None else ligne["valeur_texte"]
        )
        chiffres = {
            "nb_composants": ligne["nb_composants"],
            "nb_pieces": int(ligne["nb_pieces"]),
            "cout_ht": ligne["cout_ht"],
        }
        if valeur is None:
            non_renseigne = chiffres
            continue
        libelle = libelles.get(valeur, valeur) if attribut["type"] == "liste" else valeur
        if attribut["type"] == "booleen":
            libelle = "Oui" if valeur == "1" else "Non"
        valeurs.append({"valeur": valeur, "libelle": libelle, **chiffres})
    if attribut["type"] == "nombre":
        valeurs.sort(key=lambda v: v["valeur"])
    elif attribut["type"] == "liste":
        valeurs.sort(key=lambda v: (ordre_liste.get(v["valeur"], 0), str(v["libelle"])))
    else:
        valeurs.sort(key=lambda v: str(v["libelle"]).lower())
    vide = {"nb_composants": 0, "nb_pieces": 0, "cout_ht": 0.0}
    return {"attribut": attribut, "valeurs": valeurs, "non_renseigne": non_renseigne or vide}


def get_calcul(
    conn: sqlite3.Connection, code: str, filtres: dict[str, str | None]
) -> dict[str, Any]:
    """Somme et moyenne d'un attribut nombre sur les composants filtrés, simples et pondérées.

    La pondération compte chaque composant autant de fois que de pièces : la quantité de
    besoin, ou la quantité affectée quand un ensemble est choisi. Les composants sans valeur
    ne sont pas comptés ; une moyenne sans aucune valeur vaut NULL.
    """
    attribut = attributs.get_attribut(conn, code)
    if attribut["type"] != "nombre":
        raise ErreurMetier(f"« {attribut['libelle']} » n'est pas un attribut de type nombre.")
    ensemble = filtres.get("ensemble")
    resultat = db.fetch_one(
        conn,
        "SELECT COUNT(valeur_nombre) AS nb_renseignes,"
        " COUNT(*) - COUNT(valeur_nombre) AS nb_non_renseignes,"
        " TOTAL(CASE WHEN valeur_nombre IS NOT NULL THEN qte END) AS nb_pieces,"
        " SUM(valeur_nombre) AS somme,"
        " AVG(valeur_nombre) AS moyenne,"
        " SUM(valeur_nombre * qte) AS somme_ponderee,"
        " SUM(valeur_nombre * qte)"
        "   / NULLIF(TOTAL(CASE WHEN valeur_nombre IS NOT NULL THEN qte END), 0)"
        "   AS moyenne_ponderee"
        " FROM (SELECT v.valeur_nombre,"
        "        CASE WHEN ? IS NULL THEN v.qte_besoin ELSE a.qte END AS qte"
        "       FROM v_attribut_composant v"
        "       LEFT JOIN affectation a"
        "         ON a.composant_id = v.composant_id AND a.ensemble_code = ?"
        "       WHERE v.attribut_code = ?"
        "         AND (? IS NULL OR v.bloc_code = ?)"
        "         AND (? IS NULL OR v.mode_appro = ?)"
        "         AND (? IS NULL OR a.id IS NOT NULL))",
        (
            ensemble,
            ensemble,
            code,
            filtres.get("bloc"),
            filtres.get("bloc"),
            filtres.get("mode_appro"),
            filtres.get("mode_appro"),
            ensemble,
        ),
    )
    return {
        **(resultat or {}),
        "nb_pieces": int((resultat or {}).get("nb_pieces") or 0),
        "quantite": "affectee" if ensemble else "besoin",
    }
