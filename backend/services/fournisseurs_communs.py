"""Fournisseurs communs à un organisme : liste de référence, renommages, union au rangement.

La liste vit dans la référence de l'organisme (`org-<organisme>`), où seuls ses
administrateurs la règlent. Elle se recopie dans chaque projet rangé d'un de ses dossiers,
dans la même transaction que les autres réglages imposés (services/propagation.py), la
référence d'organisme attachée sous le schéma `org`.

Un fournisseur est identifié par son nom, et un renommage passe aux composants et commandes
par ON UPDATE CASCADE. La synchronisation ne devine donc pas un renommage : elle rejoue le
journal des renommages de la référence (`renommage_fournisseur`, identifiants aléatoires),
chaque projet gardant ceux déjà rejoués chez lui (`renommage_applique`). Un projet qui entre
dans l'organisme les marque tous rejoués : ils ne le concernent pas. Les noms se comparent
normalisés (casse, accents, espaces), comme partout ailleurs.
"""

import logging
import sqlite3
from pathlib import Path

from backend import db
from backend.services import journal, suppressions
from backend.services.fournisseurs_liste import cle_nom
from backend.services.propagation import (
    Rapport,
    Table,
    _accorder,
    _canonique,
    _inserer,
    _lignes,
    _mettre_a_jour,
    _supprimer,
)

journal_log = logging.getLogger(__name__)

FOURNISSEUR = Table(
    "fournisseur",
    ("nom",),
    (
        "type",
        "base_prix_defaut",
        "pays",
        "site_web",
        "numero_compte",
        "categorie",
        "contact",
        "delai_moyen_j",
        "commentaire",
        "archive",
        "statut",
    ),
)


def contenu(conn: sqlite3.Connection, schema: str) -> list[list]:
    """Liste du schéma, triée : part de l'empreinte des réglages imposés."""
    lignes = _lignes(conn, schema, FOURNISSEUR)
    return [
        [_canonique(ligne[c]) for c in (*FOURNISSEUR.cle, *FOURNISSEUR.colonnes)]
        for _, ligne in sorted(lignes.items())
    ]


def _noms(conn: sqlite3.Connection, schema: str) -> set[str]:
    # Schéma choisi parmi deux noms écrits dans ce module.
    requete = {"main": "SELECT nom FROM main.fournisseur", "org": "SELECT nom FROM org.fournisseur"}
    return {ligne[0] for ligne in conn.execute(requete[schema]).fetchall()}


def _renommer(conn: sqlite3.Connection, ancien: str, nouveau: str, rapport: Rapport) -> None:
    """Renomme dans le projet (les citations suivent), ou fusionne si le nouveau nom y est."""
    if nouveau in _noms(conn, "main"):
        for requete in (
            "UPDATE composant SET fournisseur_nom = ? WHERE fournisseur_nom = ?",
            "UPDATE commande SET fournisseur_nom = ? WHERE fournisseur_nom = ?",
        ):
            conn.execute(requete, (nouveau, ancien))
        journal.write_journal(conn, "fournisseur", ancien, "fusion", ancien, nouveau)
        rapport.signalements.append(f"Fournisseur « {ancien} » fusionné dans « {nouveau} ».")
    else:
        conn.execute("UPDATE fournisseur SET nom = ? WHERE nom = ?", (nouveau, ancien))
        journal.write_journal(conn, "fournisseur", ancien, "nom", ancien, nouveau)
    rapport.modifiees += 1


def _rejouer_renommages(conn: sqlite3.Connection, rapport: Rapport) -> None:
    lignes = conn.execute(
        "SELECT id, ancien, nouveau FROM org.renommage_fournisseur"
        " WHERE id NOT IN (SELECT id FROM main.renommage_applique) ORDER BY rang"
    ).fetchall()
    for ligne in lignes:
        if ligne["ancien"] in _noms(conn, "main"):
            _renommer(conn, ligne["ancien"], ligne["nouveau"], rapport)
        conn.execute("INSERT INTO main.renommage_applique (id) VALUES (?)", (ligne["id"],))


def _normaliser(conn: sqlite3.Connection, rapport: Rapport) -> None:
    """« FARNELL » du projet est le « Farnell » de l'organisme : il en prend le nom."""
    references = {cle_nom(nom): nom for nom in _noms(conn, "org")}
    for nom in sorted(_noms(conn, "main")):
        voulu = references.get(cle_nom(nom))
        if voulu is not None and voulu != nom:
            _renommer(conn, nom, voulu, rapport)


def _retirer(conn: sqlite3.Connection, nom: str, ligne: dict, rapport: Rapport) -> None:
    """Absent de la liste : supprimé s'il n'est cité nulle part (archivés compris), ou archivé."""
    if suppressions.raison_fournisseur(conn, nom) is None:
        _supprimer(conn, FOURNISSEUR, (nom,), ligne)
        rapport.supprimees += 1
    elif not ligne["archive"]:
        _mettre_a_jour(conn, FOURNISSEUR, (nom,), {"archive": 1})
        journal.write_journal(conn, "fournisseur", nom, "archive", 0, 1)
        rapport.desactivees += 1
        rapport.signalements.append(
            f"Fournisseur « {nom} » retiré de la liste : archivé, il est cité."
        )


def synchroniser(conn: sqlite3.Connection, rapport: Rapport) -> None:
    """Accorde la liste du projet (main) à celle de l'organisme (org) ; dans une transaction."""
    _normaliser(conn, rapport)
    _rejouer_renommages(conn, rapport)
    voulues = _lignes(conn, "org", FOURNISSEUR)
    actuelles = _lignes(conn, "main", FOURNISSEUR)
    for cle, ligne in voulues.items():
        if cle not in actuelles:
            _inserer(conn, FOURNISSEUR, ligne)
            journal.write_journal(conn, "fournisseur", cle[0], "creation", None, "liste commune")
            rapport.modifiees += 1
        else:
            _accorder(conn, FOURNISSEUR, cle, ligne, actuelles[cle], rapport)
    for cle, ligne in actuelles.items():
        if cle not in voulues:
            _retirer(conn, cle[0], ligne, rapport)


# --- Référence d'organisme ----------------------------------------------------------------------


def unir(organisme: Path, projet: Path, auteur: str) -> int:
    """Ajoute à la liste de l'organisme les fournisseurs du projet qu'elle n'a pas.

    Comparaison par nom normalisé ; pour un nom déjà présent, la fiche de l'organisme gagne.
    La première union d'une référence neuve la marque initialisée. Renvoie le nombre ajouté.
    """
    conn = db.connect(organisme, auteur, creer=False)
    try:
        conn.execute("ATTACH DATABASE ? AS projet", (f"{projet.resolve().as_uri()}?mode=ro",))
        with db.transaction(conn):
            connus = {cle_nom(nom) for nom in _noms_ref(conn)}
            ajoutes = 0
            for ligne in _lignes(conn, "projet", FOURNISSEUR).values():
                if cle_nom(ligne["nom"]) in connus:
                    continue
                _inserer(conn, FOURNISSEUR, ligne)
                journal.write_journal(
                    conn, "fournisseur", ligne["nom"], "creation", None, "rangement"
                )
                connus.add(cle_nom(ligne["nom"]))
                ajoutes += 1
            conn.execute("UPDATE reglages_imposes SET initialisee = 1 WHERE id = 1")
        conn.execute("DETACH DATABASE projet")
    finally:
        conn.close()
    journal_log.info(
        "Liste de %s : %d fournisseur(s) repris de %s",
        organisme.parent.name,
        ajoutes,
        projet.parent.name,
    )
    return ajoutes


def _noms_ref(conn: sqlite3.Connection) -> set[str]:
    return {ligne[0] for ligne in conn.execute("SELECT nom FROM main.fournisseur").fetchall()}


def marquer_renommages(projet: Path, organisme: Path) -> None:
    """Projet qui entre dans l'organisme : les renommages passés ne le concernent pas."""
    conn = db.connect(projet, creer=False)
    try:
        conn.execute("ATTACH DATABASE ? AS org", (f"{organisme.resolve().as_uri()}?mode=ro",))
        with db.transaction(conn):
            conn.execute(
                "INSERT OR IGNORE INTO main.renommage_applique (id)"
                " SELECT id FROM org.renommage_fournisseur"
            )
        conn.execute("DETACH DATABASE org")
    finally:
        conn.close()
