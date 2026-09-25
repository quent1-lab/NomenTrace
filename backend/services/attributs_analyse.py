"""Répartition des valeurs d'un attribut : composants, pièces et coût HT par valeur.

Générique : la tension n'est qu'un attribut parmi d'autres. Le calcul part de la vue
v_attribut_composant ; les filtres (bloc, ensemble, mode d'appro) sont des paramètres liés.
"""

import sqlite3
from typing import Any

from backend import db
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
