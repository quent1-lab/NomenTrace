"""Actions à faire sur un composant, résumées par la pastille de sa fiche.

Chaque action dit ce qui manque et l'onglet de la fiche où y remédier. Un composant affecté
à aucun ensemble n'en porte pas : c'est un état normal. Seule une affectation commencée mais
incomplète (des pièces du besoin restent hors de tout ensemble) en devient une.
"""

import sqlite3

from backend import db
from backend.services import obligatoires, saisie

MODE_ACHAT = "Achat"


def _a_une_fiche_technique(conn: sqlite3.Connection, identifiant: str) -> bool:
    return (
        db.fetch_one(
            conn,
            "SELECT 1 FROM document WHERE composant_id = ? AND archive = 0"
            " AND type_document = 'Fiche technique'",
            (identifiant,),
        )
        is not None
    )


def list_actions(conn: sqlite3.Connection, composant: dict, valeurs_attributs: dict) -> list[dict]:
    """Actions du composant (ligne de v_composant) : {code, texte, onglet}, dans l'ordre affiché."""
    actions = []
    vides = obligatoires.manquants(conn, composant, valeurs_attributs)
    if vides:
        texte = f"Champs obligatoires à remplir : {', '.join(vides.values())}"
        actions.append({"code": "obligatoire", "texte": texte, "onglet": "modifier"})
    if composant["a_chiffrer"]:
        actions.append({"code": "a_chiffrer", "texte": "Prix à relever", "onglet": "modifier"})
    for message in saisie.a_verifier(composant):
        actions.append({"code": "saisie", "texte": message, "onglet": "modifier"})
    ecart = composant["ecart_affectation"]
    if composant["nb_ensembles"] > 0 and ecart > 0:
        texte = f"{ecart} pièce(s) du besoin affectée(s) à aucun ensemble"
        actions.append({"code": "affectation", "texte": texte, "onglet": "ensembles"})
    if composant["mode_appro"] == MODE_ACHAT and not _a_une_fiche_technique(conn, composant["id"]):
        texte = "Aucune fiche technique jointe"
        actions.append({"code": "fiche_technique", "texte": texte, "onglet": "documents"})
    return actions
