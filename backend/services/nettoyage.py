"""Écran nettoyage : contrôles de qualité des composants et des commandes.

Les contrôles simples sont calculés par la vue v_qualite_composant ; les doublons probables
viennent du moteur de l'import (import_doublons), réutilisé tel quel.
"""

import sqlite3
from difflib import SequenceMatcher

from backend import db
from backend.services import import_doublons, suppressions

# Contrôles de v_qualite_composant, dans l'ordre d'affichage, avec leur libellé.
CONTROLES: dict[str, str] = {
    "designation_courte": "Désignation vide ou trop courte",
    "fonction_vide": "Fonction vide",
    "achat_sans_prix": "Achat sans prix relevé",
    "achat_sans_fournisseur": "Achat sans fournisseur",
    "besoin_nul": "Quantité de besoin nulle",
    "lien_invalide": "Lien produit invalide",
    "doublon": "Doublon probable",
    "valeur_desactivee": "Valeur de liste désactivée",
    "fournisseur_archive": "Fournisseur archivé",
}
CONTROLES_COMMANDE: dict[str, str] = {
    "sans_ligne": "Aucune ligne",
    "sans_fournisseur": "Sans fournisseur",
}


def _candidat(a: import_doublons.Empreinte, b: import_doublons.Empreinte) -> bool:
    """Préfiltre rapide : écarte les paires que le moteur ne pourrait pas proposer de fusionner.

    quick_ratio() majore le ratio de similarité : sous le seuil de fusion, inutile de le
    calculer. La décision reste celle du moteur (import_doublons.compare).
    """
    if a.reference and a.reference == b.reference:
        return True
    if any(c in b.texte for c in a.codes) or any(c in a.texte for c in b.codes):
        return True
    return any(
        x and y and SequenceMatcher(None, x, y).quick_ratio() >= import_doublons.SEUIL_FUSION
        for x, y in ((a.libelle, b.libelle), (a.designation, b.designation))
    )


def _doublons(composants: list[dict]) -> dict[str, list[dict]]:
    """Doublons probables entre composants actifs : ceux que l'import proposerait de fusionner."""
    empreintes = [import_doublons.empreinte(c["id"], c) for c in composants if not c["archive"]]
    resultat: dict[str, list[dict]] = {}
    for rang, a in enumerate(empreintes):
        for b in empreintes[rang + 1 :]:
            if not _candidat(a, b):
                continue
            trouve = import_doublons.compare(a, b)
            if trouve and trouve["fusion"]:
                resultat.setdefault(a.cle, []).append({"id": b.cle, "motif": trouve["motif"]})
                resultat.setdefault(b.cle, []).append({"id": a.cle, "motif": trouve["motif"]})
    return resultat


def list_controles_composants(conn: sqlite3.Connection) -> dict:
    """Chaque composant, archivés compris, avec ses anomalies et sa possibilité de suppression."""
    lignes = db.fetch_all(conn, "SELECT * FROM v_qualite_composant ORDER BY archive, id")
    doublons = _doublons(lignes)
    composants = []
    for ligne in lignes:
        controles = [
            cle
            for cle in CONTROLES
            if (ligne["id"] in doublons if cle == "doublon" else ligne[cle])
        ]
        composants.append(
            {
                "id": ligne["id"],
                "bloc_code": ligne["bloc_code"],
                "fonction": ligne["fonction"],
                "designation": ligne["designation"],
                "ref_fabricant": ligne["ref_fabricant"],
                "mode_appro": ligne["mode_appro"],
                "fournisseur_nom": ligne["fournisseur_nom"],
                "archive": ligne["archive"],
                "controles": controles,
                "doublons": doublons.get(ligne["id"], []),
                "raison_refus": suppressions.raison_composant(ligne),
            }
        )
    return {"controles": CONTROLES, "composants": composants}


def list_controles_commandes(conn: sqlite3.Connection) -> dict:
    """Commandes et devis, archivés compris, avec leurs anomalies et leur supprimabilité."""
    lignes = db.fetch_all(
        conn,
        "SELECT c.numero, c.type, c.statut, c.fournisseur_nom, c.date_demande, c.date_commande,"
        " c.archive,"
        " (SELECT COUNT(*) FROM ligne_commande l WHERE l.commande_numero = c.numero)"
        " AS nb_lignes,"
        " (SELECT COUNT(*) FROM document d WHERE d.commande_numero = c.numero) AS nb_documents,"
        " v.total_ht"
        " FROM commande c LEFT JOIN v_commande v ON v.numero = c.numero"
        " ORDER BY c.archive, c.numero",
    )
    for ligne in lignes:
        controles = []
        if ligne["nb_lignes"] == 0:
            controles.append("sans_ligne")
        if ligne["fournisseur_nom"] is None:
            controles.append("sans_fournisseur")
        ligne["controles"] = controles
        ligne["raison_refus"] = suppressions.raison_commande(conn, ligne["numero"])
    return {"controles": CONTROLES_COMMANDE, "commandes": lignes}
