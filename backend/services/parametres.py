"""Paramètres de l'instance : nom du projet, préfixe d'identifiant, budget, TVA par défaut,
champs obligatoires des composants, coordonnées de l'établissement (demandes de devis),
taille maximale d'un document joint."""

import sqlite3
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import journal

CLES: frozenset[str] = frozenset(
    {
        "nom_projet",
        "prefixe_id",
        "budget_ht",
        "taux_tva_defaut",
        "champs_obligatoires",
        "champs_obligatoires_portee",
        "etablissement_nom",
        "adresse_livraison",
        "adresse_facturation",
        "contact_achats_nom",
        "contact_achats_mail",
        "contact_achats_tel",
        "taille_max_document_mo",
    }
)


def list_parametres(conn: sqlite3.Connection) -> dict[str, str | None]:
    """Renvoie tous les paramètres connus, None pour ceux qui ne sont pas renseignés."""
    lignes = dict(conn.execute("SELECT cle, valeur FROM parametre").fetchall())
    return {cle: lignes.get(cle) for cle in sorted(CLES)}


def get_parametre(conn: sqlite3.Connection, cle: str) -> str | None:
    """Renvoie la valeur d'un paramètre, ou None."""
    ligne = db.fetch_one(conn, "SELECT valeur FROM parametre WHERE cle = ?", (cle,))
    return ligne["valeur"] if ligne else None


def get_taux_tva_defaut(conn: sqlite3.Connection) -> float:
    """Taux de TVA par défaut ; 0,2 si le paramètre n'est pas renseigné."""
    valeur = get_parametre(conn, "taux_tva_defaut")
    return float(valeur) if valeur is not None else 0.2


def get_prefixe_id(conn: sqlite3.Connection) -> str:
    """Préfixe des identifiants de composant ; refuse de deviner s'il manque."""
    prefixe = get_parametre(conn, "prefixe_id")
    if not prefixe:
        raise ErreurMetier(
            "Le paramètre « préfixe d'identifiant » n'est pas renseigné : impossible de "
            "générer un identifiant de composant."
        )
    return prefixe


def patch_parametres(
    conn: sqlite3.Connection, modifications: dict[str, Any], plafond_mo: int | None = None
) -> dict:
    """Modifie les paramètres fournis, avec une ligne de journal par valeur changée.

    `plafond_mo` : plafond d'envoi du serveur, que la taille d'un document ne peut dépasser
    (absent pour la recopie des réglages d'un dossier, déjà contrôlés à leur saisie)."""
    with db.transaction(conn):
        for cle, valeur in modifications.items():
            if cle not in CLES:
                raise ErreurMetier(f"Paramètre inconnu : {cle}.")
            if cle == "taille_max_document_mo" and plafond_mo and (valeur or 0) > plafond_mo:
                raise ErreurMetier(
                    f"La taille d'un document ne peut dépasser le plafond du serveur,"
                    f" {plafond_mo} Mo."
                )
            # Une liste (champs obligatoires) est rangée en texte, séparée par des virgules.
            if isinstance(valeur, list):
                texte = ",".join(valeur) or None
            else:
                texte = None if valeur is None else str(valeur)
            ancienne = get_parametre(conn, cle)
            if ancienne == texte:
                continue
            conn.execute(
                "INSERT INTO parametre (cle, valeur) VALUES (?, ?)"
                " ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur",
                (cle, texte),
            )
            journal.write_journal(conn, "parametre", cle, "valeur", ancienne, texte)
    return list_parametres(conn)
