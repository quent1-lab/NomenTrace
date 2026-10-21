"""Nouveau projet repris d'un autre : ses réglages propres, jamais ses données.

Un projet créé dans un dossier reçoit déjà les réglages imposés par le dossier. Repris d'un
projet modèle du même dossier, il reçoit en plus ce qui reste propre à chaque projet et
vaut d'une équipe à l'autre : les valeurs des listes locales (statuts d'appro et de choix)
et l'arborescence des ensembles actifs (code, nom, ordre, parent, description). Rien de ce
qui appartient à l'équipe du modèle n'est repris : ni composants, ni affectations, ni
commandes, ni stock, ni responsables, ni budgets, ni avancement du montage.
"""

import logging
import sqlite3
from pathlib import Path

from backend import db
from backend.services import journal

journal_log = logging.getLogger(__name__)

LISTES_LOCALES: tuple[str, ...] = ("statut_appro", "statut_choix")


def _ensembles_ordonnes(conn: sqlite3.Connection) -> list[dict]:
    """Ensembles actifs du modèle, chaque parent avant ses enfants."""
    lignes = db.fetch_all(
        conn,
        "SELECT code, nom, ordre, parent_code, description FROM modele.ensemble"
        " WHERE archive = 0 ORDER BY ordre, code",
    )
    actifs = {ligne["code"] for ligne in lignes}
    ordonnes: list[dict] = []
    places: set[str] = set()
    restants = lignes
    while restants:
        suivants = []
        for ligne in restants:
            parent = ligne["parent_code"]
            if parent is None or parent not in actifs or parent in places:
                ordonnes.append({**ligne, "parent_code": parent if parent in actifs else None})
                places.add(ligne["code"])
            else:
                suivants.append(ligne)
        if len(suivants) == len(restants):  # cycle impossible en base ; garde-fou
            break
        restants = suivants
    return ordonnes


def copier_reglages_propres(modele: Path, cible: Path, auteur: str | None) -> dict:
    """Copie dans le projet cible (neuf) les listes locales et les ensembles du modèle."""
    conn = db.connect(cible, auteur, creer=False)
    try:
        conn.execute("ATTACH DATABASE ? AS modele", (f"{modele.resolve().as_uri()}?mode=ro",))
        with db.transaction(conn):
            valeurs = 0
            for ligne in db.fetch_all(
                conn,
                "SELECT liste, code, libelle, ordre, actif FROM modele.valeur_liste"
                " WHERE liste IN ('statut_appro', 'statut_choix') AND systeme = 0",
            ):
                # Une valeur déjà là (vocabulaire de départ) prend libellé, ordre et état du modèle.
                conn.execute(
                    "INSERT INTO main.valeur_liste (liste, code, libelle, ordre, actif)"
                    " VALUES (:liste, :code, :libelle, :ordre, :actif)"
                    " ON CONFLICT (liste, code) DO UPDATE SET libelle = excluded.libelle,"
                    " ordre = excluded.ordre, actif = excluded.actif",
                    ligne,
                )
                cle = f"{ligne['liste']}:{ligne['code']}"
                journal.write_journal(conn, "valeur_liste", cle, "creation", None, "reprise")
                valeurs += 1
            ensembles = _ensembles_ordonnes(conn)
            for ligne in ensembles:
                conn.execute(
                    "INSERT INTO main.ensemble (code, nom, ordre, parent_code, description)"
                    " VALUES (:code, :nom, :ordre, :parent_code, :description)",
                    ligne,
                )
                journal.write_journal(conn, "ensemble", ligne["code"], "creation", None, "repris")
        conn.execute("DETACH DATABASE modele")
    finally:
        conn.close()
    journal_log.info("Projet %s repris de %s", cible.parent.name, modele.parent.name)
    return {"valeurs_de_liste": valeurs, "ensembles": len(ensembles)}
